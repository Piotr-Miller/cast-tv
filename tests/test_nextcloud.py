"""The Nextcloud source on the ``Source`` contract, against a scripted Nextcloud on localhost.

One stub plays the whole server: Login Flow v2, OCS (the user, the app-password
revoke), WebDAV ``PROPFIND``/``SEARCH``, file downloads with Range, and the
preview endpoint. The fixture XML is in the shapes the spike recorded
(``context/changes/s17-nextcloud/research.md``).
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import http.server
import json
import os
import socketserver
import subprocess
import threading
import urllib.parse

import pytest

from castlib import config
from castlib.auth import loginflow
from castlib.auth.apppassword import AppPasswordStore
from castlib.errors import AuthError, ConfigError, NotMedia, UpstreamError
from castlib.sources import nextcloud
from castlib.sources.nextcloud import NextcloudSource
from tests.conftest import request, wait_for

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "nextcloud")
LOGIN = "pat@example.test"
USER_ID = "pat"
ROOT = "/remote.php/dav/files/pat/"


def _fixture(name) -> bytes:
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()


def multistatus(entries, user=USER_ID) -> bytes:
    """A ``PROPFIND`` answer: ``entries`` are ``(path, kind, file id, mime, modified, preview)``; kind "dir" or "file"."""
    parts = ['<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" '
             'xmlns:nc="http://nextcloud.org/ns">']
    for path, kind, file_id, mime, modified, preview in entries:
        href = "/remote.php/dav/files/%s/%s" % (user, urllib.parse.quote(path))
        props = "<oc:fileid>%s</oc:fileid>" % file_id
        if kind == "dir":
            href += "/" if path else ""
            props += "<d:resourcetype><d:collection/></d:resourcetype>"
        else:
            props += "<d:resourcetype/><d:getcontenttype>%s</d:getcontenttype>" % mime
            props += "<d:getcontentlength>1000</d:getcontentlength><d:getetag>\"e%s\"</d:getetag>" % file_id
            props += "<nc:has-preview>%s</nc:has-preview>" % ("true" if preview else "false")
        if modified:
            props += "<d:getlastmodified>%s</d:getlastmodified>" % modified
        parts.append("<d:response><d:href>%s</d:href><d:propstat><d:prop>%s</d:prop>"
                     "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>" % (href, props))
    parts.append("</d:multistatus>")
    return "".join(parts).encode("utf-8")


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, status, body=b"", ctype="application/json", headers=()):
        f = self.server.fake
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        if status >= 400 and f.leaky:                # a careless server echoes the credential back
            body = body + (" password=%s auth=%s" % (f.last_password, self.headers.get("Authorization"))).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if status >= 400 and f.leaky:
            self.send_header("X-Debug", "pw=%s" % f.last_password)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _auth(self) -> bool:
        f = self.server.fake
        value = self.headers.get("Authorization") or ""
        if not value.startswith("Basic "):
            return False
        login, _, password = base64.b64decode(value[6:]).decode("utf-8").partition(":")
        with f.lock:
            return login == f.login_name and password in f.valid

    def _record(self, body=b""):
        f = self.server.fake
        with f.lock:
            f.calls.append({"method": self.command, "path": self.path, "headers": self.headers,   # case-insensitive
                            "body": body})

    def do_POST(self):
        f = self.server.fake
        body = self._body()
        self._record(body)
        if self.path == "/index.php/login/v2":
            with f.lock:
                f.starts += 1
                n = f.starts
            here = "http://" + self.headers["Host"]          # the server answers for the name it was asked by
            return self._send(200, {"poll": {"token": "tok-%d" % n,
                                             "endpoint": f.endpoint or here + "/index.php/login/v2/poll"},
                                    "login": f.login_url or "%s/login/v2/flow/flow-%d" % (here, n)})
        if self.path == "/index.php/login/v2/poll":
            with f.lock:
                answer = f.script[0] if len(f.script) == 1 else f.script.pop(0)
            if answer == "pending":
                return self._send(404, {})
            if answer == "http500":
                return self._send(500, b"oops")
            if f.before_answer is not None:
                f.before_answer()
            return self._send(200, {"server": f.server_field or "http://" + self.headers["Host"],
                                    "loginName": f.login_name,
                                    "appPassword": f.issue()})
        self._send(404, {})

    def do_GET(self):
        f = self.server.fake
        self._record()
        parsed = urllib.parse.urlsplit(self.path)
        if not self._auth():
            return self._send(401, {"ocs": {"meta": {"status": "failure", "statuscode": 997}}})
        if parsed.path == "/ocs/v2.php/cloud/user":
            assert self.headers.get("OCS-APIRequest") == "true"
            return self._send(200, {"ocs": {"meta": {"status": "ok", "statuscode": 200},
                                            "data": {"id": f.user_id, "displayname": "Pat Example"}}})
        if parsed.path == "/index.php/core/preview":
            if f.preview_status != 200:
                return self._send(f.preview_status, b"preview failed")
            return self._send(200, b"\xff\xd8\xff\xe0" + b"\0" * 32, ctype="image/jpeg")
        if parsed.path.startswith(ROOT):
            rel = urllib.parse.unquote(parsed.path[len(ROOT):])
            data = f.blobs.get(rel)
            if data is None or f.media_status != 200:
                return self._send(f.media_status if data is not None else 404, b"no such file")
            rng = self.headers.get("Range")
            if rng:
                a, b = rng.replace("bytes=", "").split("-")
                start, end = int(a), int(b) if b else len(data) - 1
                return self._send(206, data[start:end + 1], ctype="video/quicktime",
                                  headers=[("Content-Range", "bytes %d-%d/%d" % (start, end, len(data)))])
            return self._send(200, data, ctype="video/quicktime")
        self._send(404, {})

    def do_PROPFIND(self):
        f = self.server.fake
        self._record(self._body())
        if not self._auth():
            return self._send(401, b"<d:error/>", ctype="application/xml")
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if not path.startswith("/remote.php/dav/files/%s/" % f.user_id):
            return self._send(404, b"<d:error/>", ctype="application/xml")
        rel = path[len("/remote.php/dav/files/%s/" % f.user_id):].rstrip("/")
        answer = f.folders.get(rel)
        if answer is None:
            return self._send(404, b"<d:error>no such folder</d:error>", ctype="application/xml")
        return self._send(207, answer, ctype="application/xml; charset=utf-8")

    def do_SEARCH(self):
        f = self.server.fake
        body = self._body()
        self._record(body)
        if not self._auth():
            return self._send(401, b"<d:error/>", ctype="application/xml")
        text = body.decode("utf-8")
        wanted = text.split("<d:literal>", 1)[1].split("</d:literal>", 1)[0]
        with f.lock:
            f.searches.append(wanted)
        found = [e for e in f.search_index if e[2] == wanted]
        return self._send(207, multistatus(found, f.user_id), ctype="application/xml; charset=utf-8")

    def do_DELETE(self):
        f = self.server.fake
        self._record()
        if self.path != "/ocs/v2.php/core/apppassword":
            return self._send(404, {})
        if not self._auth():
            return self._send(401, {})
        if f.revoke_status != 200:
            return self._send(f.revoke_status, b"revoke broke")
        value = self.headers["Authorization"]
        password = base64.b64decode(value[6:]).decode("utf-8").partition(":")[2]
        with f.lock:
            f.valid.discard(password)
            f.revoked.append(password)
        return self._send(200, {"ocs": {"meta": {"status": "ok"}, "data": []}})


class FakeNextcloud:
    """A Nextcloud server: scripted Login Flow answers, fixture folders, files and previews."""

    def __init__(self):
        self.lock = threading.Lock()
        self.base = ""
        self.login_name = LOGIN
        self.user_id = USER_ID
        self.valid = set()                    # app passwords the server accepts
        self.revoked = []
        self.issued = 0
        self.last_password = None
        self.script = ["pending", "ok"]       # poll answers in order; the last one repeats
        self.starts = 0
        self.calls = []
        self.searches = []
        self.login_url = None                 # overrides for the start answer
        self.endpoint = None
        self.server_field = None              # override for the poll answer's "server"
        self.before_answer = None
        self.revoke_status = 200
        self.preview_status = 200
        self.media_status = 200
        self.leaky = False
        self.folders = {"": _fixture("root.xml"), "Pictures": _fixture("pictures.xml"),
                        "Documents": multistatus([("Documents", "dir", "12", None, None, False)]),
                        "odd": _fixture("prefixes.xml")}
        self.blobs = {"Pictures/PB014001.MOV": bytes(range(256)) * 8}
        self.search_index = [("Pictures/OM Workspace/2026_11_01/PB014004.JPG", "file", "9001", "image/jpeg",
                              "Sat, 01 Nov 2026 12:00:00 GMT", True),
                             ("Pictures/OM Workspace/2026_11_01/video/PB014042.MOV", "file", "9002",
                              "video/quicktime", "Sat, 01 Nov 2026 12:30:00 GMT", False)]

    def issue(self) -> str:
        with self.lock:
            self.issued += 1
            password = "SECRETpw-%d-abcdefghijklmnopqrstuvwxyz0123456789" % self.issued
            self.valid.add(password)
            self.last_password = password
        return password

    def of(self, method):
        with self.lock:
            return [c for c in self.calls if c["method"] == method]


class _Stub(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _serve(fake):
    srv = _Stub(("127.0.0.1", 0), _Handler)
    srv.fake = fake
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    return srv


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = FakeNextcloud()
    srv = _serve(f)
    f.base = "http://127.0.0.1:%d" % srv.server_address[1]
    f.srv = srv
    monkeypatch.setattr(loginflow, "SCHEMES", ("https", "http"))   # the stub speaks plain HTTP on loopback
    monkeypatch.setattr(loginflow, "POLL_INTERVAL", 0.01)
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.setattr(config, "_CACHE", str(tmp_path / "cache"))
    try:
        yield f
    finally:
        srv.shutdown()
        srv.server_close()


def _sign_in(src, fake):
    d = src.connect({"server": fake.base})
    assert d["step"] == "login" and d["state"] == "connecting"
    wait_for(lambda: src.status()["state"] == "connected")
    return d


def _cred_file():
    return os.path.join(config.config_dir(), "nextcloud.json")


def _ids(listing):
    return [e.id for e in listing.items]


# ------------------------------------------------------------ the address
def test_address_normalised():
    cases = {"cloud.example.com": "https://cloud.example.com",
             "  Cloud.Example.com/  ": "https://cloud.example.com",
             "https://host/nextcloud/": "https://host/nextcloud",
             "https://host:443/": "https://host",
             "https://host:8443/nc": "https://host:8443/nc",
             "host.example:8443": "https://host.example:8443"}
    for typed, url in cases.items():
        assert loginflow.normalise(typed).url == url
    base = loginflow.normalise("https://host:443/nextcloud")
    assert base.origin == ("https", "host", 443) and base.path == "/nextcloud"
    for bad in ("", "   ", None, "ftp://host", "https://", "https://host?x=1", "https://ho st",
                "https://host:99999", "https://host/../x", "https://-bad-"):
        with pytest.raises(ConfigError) as err:
            loginflow.normalise(bad)
        assert err.value.code == "bad_address" and err.value.message


def test_http_address_refused():
    for typed in ("http://192.168.50.10", "HTTP://cloud.example.com/nextcloud"):
        with pytest.raises(ConfigError) as err:
            loginflow.normalise(typed)
        assert err.value.code == "http_refused" and "HTTPS" in err.value.message


def test_address_userinfo_refused():
    for typed in ("https://a@host", "https://user:pw@host/nc", "a@host"):
        with pytest.raises(ConfigError) as err:
            loginflow.normalise(typed)
        assert err.value.code == "bad_address" and "user name" in err.value.message


# ------------------------------------------------------- same origin
def test_flow_other_origin_refused(fake):
    fake.login_url = "https://evil.test/login/v2/flow/x"
    src = NextcloudSource()
    with pytest.raises(UpstreamError) as err:
        src.connect({"server": fake.base})
    assert err.value.code == "nextcloud_origin"
    assert src.status()["state"] == "disconnected"
    assert not fake.of("GET")                                 # nothing was sent anywhere with a password


def test_flow_backslash_userinfo_refused(fake):
    # urlsplit reads the host after "@"; a browser reads "\\" as "/" and opens evil.test
    fake.login_url = fake.base.replace("://", "://evil.test\\@") + "/login/v2/flow/x"
    src = NextcloudSource()
    with pytest.raises(UpstreamError) as err:
        src.connect({"server": fake.base})
    assert err.value.code == "nextcloud_origin"
    base = loginflow.normalise("cloud.example.com")
    assert loginflow.same_origin(base, "https://cloud.example.com/login")
    for url in ("https://evil.test\\@cloud.example.com/login", "https://u@cloud.example.com/login",
                "https://evil.test\\.cloud.example.com/x", "https://cloud.example.com\t/x"):
        assert not loginflow.same_origin(base, url), url


def test_flow_other_port_refused(fake):
    port = int(fake.base.rsplit(":", 1)[1])
    fake.endpoint = "http://127.0.0.1:%d/index.php/login/v2/poll" % (port + 1)
    with pytest.raises(UpstreamError) as err:
        NextcloudSource().connect({"server": fake.base})
    assert err.value.code == "nextcloud_origin"
    fake.endpoint = "https://127.0.0.1:%d/index.php/login/v2/poll" % port   # the same port, another scheme
    with pytest.raises(UpstreamError):
        NextcloudSource().connect({"server": fake.base})
    base = loginflow.normalise("https://cloud.example.com")
    assert loginflow.same_origin(base, "https://cloud.example.com:443/x")
    assert not loginflow.same_origin(base, "https://cloud.example.com:8443/x")
    assert not loginflow.same_origin(base, "http://cloud.example.com/x")
    assert not loginflow.same_origin(base, "//cloud.example.com/x")
    assert not loginflow.same_origin(base, "https://cloud.example.com.evil.test/x")


def test_poll_server_other_origin_refused(fake):
    fake.server_field = "https://evil.test"
    fake.script = ["ok"]
    src = NextcloudSource()
    src.connect({"server": fake.base})
    wait_for(lambda: src.status()["state"] != "connecting")
    s = src.status()
    assert s["state"] == "disconnected" and s["detail"]["flow_error"]["code"] == "nextcloud_origin"
    assert not os.path.exists(_cred_file())
    assert not fake.of("GET")                                 # the password was never used
    assert fake.revoked == [fake.last_password]               # but revoked where it was issued


def test_href_outside_root_refused(fake):
    port = int(fake.base.rsplit(":", 1)[1])
    good = multistatus([("x", "dir", "1", None, None, False), ("x/ok.jpg", "file", "51", "image/jpeg", None, True)])
    hostile = []
    for href in ("//evil.test/remote.php/dav/files/pat/x/a.jpg",
                 "https://evil.test/remote.php/dav/files/pat/x/b.jpg",
                 "http://127.0.0.1:%d/remote.php/dav/files/pat/x/c.jpg" % (port + 1),
                 "/remote.php/dav/files/patrick/x/d.jpg",                       # not at a segment boundary
                 "/remote.php/dav/files/other/x/e.jpg",
                 "/remote.php/dav/files/pat/x/../../other/f.jpg",
                 "remote.php/dav/files/pat/x/g.jpg"):
        hostile.append("<d:response><d:href>%s</d:href><d:propstat><d:prop><d:resourcetype/>"
                       "<d:getcontenttype>image/jpeg</d:getcontenttype><oc:fileid>6%d</oc:fileid>"
                       "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
                       % (href, len(hostile)))
    same = "%s/remote.php/dav/files/pat/x/same-origin.jpg" % fake.base
    hostile.append("<d:response><d:href>%s</d:href><d:propstat><d:prop><d:resourcetype/>"
                   "<d:getcontenttype>image/jpeg</d:getcontenttype><oc:fileid>70</oc:fileid>"
                   "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>" % same)
    fake.folders["x"] = good.replace(b"</d:multistatus>", "".join(hostile).encode() + b"</d:multistatus>")
    src = NextcloudSource()
    _sign_in(src, fake)
    listing = src.list("x")
    assert [(e.id, e.name) for e in listing.items] == [("51", "ok.jpg"), ("70", "same-origin.jpg")]
    item = src.resolve("70")
    assert item.resolve().url == fake.base + ROOT + "x/same-origin.jpg"   # built from the base, not the href


# ------------------------------------------------------------ the account
def test_connect_verifies_stored(fake):
    src = NextcloudSource()
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    d = _sign_in(src, fake)
    assert d["detail"]["login_url"] == fake.base + "/login/v2/flow/flow-1"
    assert d["detail"]["server"] == fake.base and 0 < d["detail"]["expires_in"] <= 1200
    s = src.status()
    assert s["detail"]["account"] == "Pat Example (pat@example.test)" and s["detail"]["server"] == fake.base
    start = fake.of("POST")[0]
    assert start["path"] == "/index.php/login/v2" and start["headers"]["User-Agent"] == "cast-tv"
    # a restart: stored, not verified until connect({}), which asks the server and starts no flow
    fresh = NextcloudSource()
    assert fresh.status()["state"] == "disconnected" and fresh.status()["detail"]["stored"]
    before = len(fake.of("GET"))
    d = fresh.connect({})
    assert d["state"] == "connected" and "step" not in d
    gets = fake.of("GET")[before:]
    assert fake.starts == 1 and [g["path"] for g in gets] == ["/ocs/v2.php/cloud/user?format=json"]
    # a stored password the server no longer accepts: connect({}) says so and the tab is expired
    with fake.lock:
        saved = set(fake.valid)
        fake.valid.clear()
    stale = NextcloudSource()
    with pytest.raises(AuthError) as err:
        stale.connect({})
    assert err.value.code == "nextcloud_unauthorized" and stale.status()["state"] == "expired"
    with fake.lock:
        fake.valid |= saved
    # nothing stored and no address: the gate asks for one
    fresh.disconnect()
    with pytest.raises(ConfigError) as err:
        NextcloudSource().connect({})
    assert err.value.code == "no_server"


def test_connect_server_starts_fresh_flow(fake):
    fake.script = ["pending"]
    src = NextcloudSource()
    first = src.connect({"server": fake.base})
    again = src.connect({"server": fake.base + "/"})           # the same address: the same flow
    assert again["detail"]["login_url"] == first["detail"]["login_url"] and fake.starts == 1
    assert src.connect({})["detail"]["login_url"] == first["detail"]["login_url"]
    other = src.connect({"server": "http://localhost:%s" % fake.base.rsplit(":", 1)[1]})
    assert fake.starts == 2 and other["detail"]["server"].startswith("http://localhost:")
    assert other["detail"]["login_url"].endswith("/flow-2")
    with pytest.raises(ConfigError) as err:
        src.connect({"server": "https://a@b"})
    assert err.value.code == "bad_address"
    assert src.status()["state"] == "connecting"              # a refused address leaves the running flow
    src.connect({"cancel": True})
    assert src.status()["state"] == "disconnected"
    # signed in, then a new address: a fresh flow even while the password is good
    fake.script = ["ok"]
    _sign_in(src, fake)
    d = src.connect({"server": fake.base})
    assert d["step"] == "login" and fake.starts == 4


def _flow_threads_done(before):
    """Wait for the sign-in threads this test started; ``before`` is ``set(threading.enumerate())`` at its start."""
    wait_for(lambda: not any(t.name == "nextcloud-loginflow" and t.is_alive() and t not in before
                             for t in threading.enumerate()))


def test_late_poll_answer_dropped(fake):
    before = set(threading.enumerate())
    held, release = threading.Event(), threading.Event()

    def hold():
        held.set()
        release.wait(5)
    fake.before_answer = hold
    fake.script = ["ok"]
    src = NextcloudSource()
    src.connect({"server": fake.base})
    assert held.wait(5)
    src.connect({"cancel": True})                             # cancelled while the answer is on its way
    release.set()
    _flow_threads_done(before)
    first = fake.last_password
    assert fake.issued == 1 and fake.revoked == [first]       # handed over once, so revoked at once
    assert src.status() == {"state": "disconnected", "detail": {"stored": False, "server": fake.base}}
    assert not os.path.exists(_cred_file())
    # a Disconnect while a newer flow's answer is late: that answer is dropped and revoked too
    held.clear()
    release.clear()
    src.connect({"server": fake.base})
    assert held.wait(5)
    fake.before_answer = None
    src.disconnect()
    release.set()
    _flow_threads_done(before)
    assert fake.issued == 2 and fake.revoked == [first, fake.last_password]
    assert not src._store.exists() and src.status()["state"] == "disconnected"


def test_new_flow_late_answer_revoked(fake):
    before = set(threading.enumerate())
    held, release = threading.Event(), threading.Event()

    def hold():
        held.set()
        release.wait(5)
    fake.before_answer = hold
    fake.script = ["ok"]
    src = NextcloudSource()
    src.connect({"server": fake.base})
    assert held.wait(5)
    fake.before_answer = None
    other = "http://localhost:%s" % fake.base.rsplit(":", 1)[1]
    src.connect({"server": other})                            # a new flow replaces the one being answered
    release.set()
    wait_for(lambda: src.status()["state"] == "connected")
    _flow_threads_done(before)
    late, kept = sorted(fake.revoked), src._store.load()["password"]
    assert fake.issued == 2 and len(late) == 1 and late[0] != kept and kept in fake.valid


def test_fresh_sign_in_revokes_the_replaced_password(fake):
    before = set(threading.enumerate())
    src = NextcloudSource()
    port = fake.base.rsplit(":", 1)[1]
    src.connect({"server": "http://localhost:%s" % port})    # the old sign-in on one address ...
    wait_for(lambda: src.status()["state"] == "connected")
    old = fake.last_password
    src.connect({"server": fake.base})                        # ... replaced through the API on another
    wait_for(lambda: src._store.load()["password"] != old)
    _flow_threads_done(before)
    assert fake.revoked == [old] and old not in fake.valid
    assert src._store.load()["password"] == fake.last_password in fake.valid
    deletes = fake.of("DELETE")
    assert [c["headers"]["Host"] for c in deletes] == ["localhost:%s" % port]   # at the old server


def test_failed_account_check_revokes_even_after_cancel(fake, monkeypatch):
    before = set(threading.enumerate())
    held, release = threading.Event(), threading.Event()
    real = loginflow.user

    def slow(*args):
        held.set()
        release.wait(5)
        raise UpstreamError("nextcloud_http", "boom", source="nextcloud")
    monkeypatch.setattr(loginflow, "user", slow)
    fake.script = ["ok"]
    src = NextcloudSource()
    src.connect({"server": fake.base})
    assert held.wait(5)
    src.connect({"cancel": True})                             # cancelled while the account check runs
    release.set()
    _flow_threads_done(before)
    monkeypatch.setattr(loginflow, "user", real)
    assert fake.revoked == [fake.last_password] and src.status()["state"] == "disconnected"


def test_login_name_differs_from_user_id(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    with open(_cred_file(), encoding="utf-8") as fh:
        stored = json.load(fh)
    assert stored["login"] == "pat@example.test" and stored["user_id"] == "pat"
    src.list()
    propfind = fake.of("PROPFIND")[-1]
    assert propfind["path"] == "/remote.php/dav/files/pat/"
    login = base64.b64decode(propfind["headers"]["Authorization"][6:]).decode().split(":")[0]
    assert login == "pat@example.test"                       # Basic carries the login name, the path the id
    # a user id that needs encoding is encoded in every path
    fake.user_id = "pat smith"
    fake.folders = {"": multistatus([("", "dir", "2", None, None, False)], user="pat%20smith")}
    src.disconnect()
    _sign_in(src, fake)
    assert src._store.load()["user_id"] == "pat smith"
    src.list()
    assert fake.of("PROPFIND")[-1]["path"] == "/remote.php/dav/files/pat%20smith/"


# ------------------------------------------------------------ the listing
def test_photo_kinds(fake, capsys, monkeypatch):
    from castlib import media
    monkeypatch.setattr(media, "_hidden_kinds_logged", set())
    for mime, kind in (("image/jpeg", "photo"), ("image/heic", "photo"), ("image/png", "photo"),
                       ("image/webp", "photo"), ("image/heif", "photo"), ("IMAGE/JPEG; charset=binary", "photo"),
                       ("image/gif", None), ("image/x-adobe-dng", None), ("application/pdf", None), ("", None)):
        assert media.kind_from_facets("nextcloud", {"getcontenttype": mime}) == kind
    src = NextcloudSource()
    _sign_in(src, fake)
    listing = src.list("Pictures")
    kinds = {e.name: e.kind for e in listing.items}
    assert kinds == {"PB014001.MOV": "video", "PB014004.JPG": "photo",
                     "shelf-christmas-decoration.heic": "photo", "Łódź zimą.jpg": "photo"}
    err = capsys.readouterr().err
    for hidden in ("'image/gif'", "'application/pdf'", "'no type'", "'application/octet-stream'"):
        assert "nextcloud: hiding an item of unknown kind %s" % hidden in err
    assert "party.gif" not in err and "receipt" not in err    # the kind is logged, never the record
    src.list("Pictures")
    assert capsys.readouterr().err == ""                      # once per session


def test_video_kinds(fake):
    from castlib import media
    for mime, kind in (("video/quicktime", "video"), ("video/mp4", "video"), ("video/x-matroska", "video"),
                       ("application/octet-stream", None), ("audio/mpeg", None)):
        assert media.kind_from_facets("nextcloud", {"getcontenttype": mime}) == kind
    src = NextcloudSource()
    _sign_in(src, fake)
    mov = next(e for e in src.list("Pictures").items if e.id == "103")
    assert mov.kind == "video" and mov.mime == "video/quicktime" and mov.size == 268748800
    assert mov.thumb is None                                  # no server preview for films: the placeholder
    assert "108" not in _ids(src.list("Pictures"))            # an .mp4 labelled octet-stream stays hidden


def test_tile_date_from_last_modified(fake):
    assert nextcloud.tile_date("Sat, 01 Nov 2026 23:59:59 GMT") == "2026-11-01"
    assert nextcloud.tile_date("Sun, 02 Nov 2026 00:30:00 +0100") == "2026-11-01"   # the UTC date part
    for bad in (None, "", "yesterday", "Sat, 99 Nov 2026 10:00:00 GMT"):
        assert nextcloud.tile_date(bad) is None
    src = NextcloudSource()
    _sign_in(src, fake)
    by_id = {e.id: e for e in src.list("Pictures").items}
    assert by_id["101"].date == "2026-11-01" and by_id["102"].date == "2025-12-06"
    assert by_id["106"].date is None                          # its getlastmodified came in a 404 propstat


def test_listing_order(fake):
    fake.folders["o"] = multistatus([
        ("o", "dir", "1", None, None, False),
        ("o/b.jpg", "file", "31", "image/jpeg", None, True),
        ("o/Zulu", "dir", "32", None, None, False),
        ("o/A.JPG", "file", "33", "image/jpeg", None, True),
        ("o/alpha", "dir", "34", None, None, False),
        ("o/a.jpg", "file", "35", "image/jpeg", None, True),
        ("o/C.mov", "file", "36", "video/quicktime", None, False)])
    src = NextcloudSource()
    _sign_in(src, fake)
    listing = src.list("o")
    assert [f.name for f in listing.folders] == ["alpha", "Zulu"]       # case-insensitive
    assert [e.name for e in listing.items] == ["A.JPG", "a.jpg", "b.jpg", "C.mov"]   # ties keep the server's order
    root = src.list()
    assert [(f.id, f.name, f.count) for f in root.folders] == [("Documents", "Documents", None),
                                                               ("Pictures", "Pictures", None)]


def test_multistatus_shapes(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    listing = src.list("Pictures")
    assert [f.id for f in listing.folders] == ["Pictures/OM Workspace", "Pictures/Test_Pictures"]
    assert _ids(listing) == ["103", "101", "102", "106"]       # the self entry, 404 props and duplicates are out
    assert "107" not in _ids(listing)                          # its type came only in a 404 propstat
    jpg = next(e for e in listing.items if e.id == "101")
    assert jpg.name == "PB014004.JPG" and jpg.thumb == "/api/sources/nextcloud/thumb/101"
    assert jpg.size == 7340122 and jpg.mime == "image/jpeg" and jpg.source == "nextcloud"
    assert listing.crumbs == [{"id": None, "name": "Nextcloud"}, {"id": "Pictures", "name": "Pictures"}]
    deep = multistatus([("Pictures/OM Workspace", "dir", "22", None, None, False)])
    fake.folders["Pictures/OM Workspace"] = deep
    sub = src.list("Pictures/OM Workspace")
    assert sub.items == [] and sub.folders == []
    assert sub.crumbs == [{"id": None, "name": "Nextcloud"}, {"id": "Pictures", "name": "Pictures"},
                          {"id": "Pictures/OM Workspace", "name": "OM Workspace"}]
    assert fake.of("PROPFIND")[-1]["path"] == "/remote.php/dav/files/pat/Pictures/OM%20Workspace/"
    assert fake.of("PROPFIND")[-1]["headers"]["Depth"] == "1"
    for bad in ("/Pictures", "Pictures/", "Pictures//x", "../x", "Pictures/..", ".", "a\x00b", "a\nb"):
        with pytest.raises(ConfigError) as err:
            src.list(bad)
        assert err.value.code == "bad_path"
    with pytest.raises(UpstreamError) as err:
        src.list("Missing")
    assert err.value.code == "nextcloud_http" and src.status()["state"] == "connected"


def test_listing_pages(fake):
    entries = [("big", "dir", "1", None, None, False)]
    entries += [("big/d%03d" % i, "dir", str(1000 + i), None, None, False) for i in range(201)]
    entries += [("big/m%03d.jpg" % i, "file", str(5000 + i), "image/jpeg", None, True) for i in range(450)]
    fake.folders["big"] = multistatus(entries)
    src = NextcloudSource()
    _sign_in(src, fake)
    first = src.list("big")
    assert len(first.folders) == 201 and len(first.items) == 200 and first.next == "200"
    second = src.list("big", "200")
    assert second.folders == [] and len(second.items) == 200 and second.next == "400"
    third = src.list("big", "400")
    assert third.folders == [] and len(third.items) == 50 and third.next is None
    assert [e.name for e in third.items][-1] == "m449.jpg"
    assert len(fake.of("PROPFIND")) == 1                       # one snapshot serves every page
    src.list("big")
    assert len(fake.of("PROPFIND")) == 2                       # a page-less request takes a new one
    for bad in ("-1", "x", "1e3", "2.5", " 200"):
        with pytest.raises(ConfigError) as err:
            src.list("big", bad)
        assert err.value.code == "bad_page"
    fake.folders["two"] = multistatus([("two", "dir", "1", None, None, False)] +
                                      [("two/m%03d.jpg" % i, "file", str(7000 + i), "image/jpeg", None, True)
                                       for i in range(200)])
    exact = src.list("two")
    assert len(exact.items) == 200 and exact.next is None
    # a page of a folder whose snapshot is gone (a restart) takes a new snapshot
    other = NextcloudSource()
    other.connect({})
    assert len(other.list("big", "400").items) == 50


def test_big_folder_files_found_without_search(fake, monkeypatch):
    # a folder larger than the LRU: every tile of every page still resolves from the folder's snapshot
    monkeypatch.setattr(nextcloud, "CACHE_ITEMS", 50)
    entries = [("huge", "dir", "1", None, None, False)]
    entries += [("huge/IMG_%06d.jpg" % i, "file", str(20000 + i), "image/jpeg", None, True) for i in range(500)]
    fake.folders["huge"] = multistatus(entries)
    src = NextcloudSource()
    _sign_in(src, fake)
    first = src.list("huge")
    assert len(src._files) == 50 and first.items[0].id not in src._files   # page 1 fell out of the LRU
    for entry in first.items:
        assert src.thumb(entry.id) is not None
    assert src.resolve(first.items[0].id).title == "IMG_000000.jpg"
    last = src.list("huge", "400")
    assert src.resolve(last.items[-1].id).title == "IMG_000499.jpg"
    assert fake.searches == []
    src.list("Documents")
    assert src.thumb(first.items[1].id) is not None and fake.searches == []   # an older snapshot still counts


def test_empty_folder(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    listing = src.list("Documents")
    assert listing.items == [] and listing.folders == [] and listing.next is None
    assert listing.as_dict()["crumbs"][-1] == {"id": "Documents", "name": "Documents"}


# ------------------------------------------------------------ disconnect
def test_disconnect_revokes_then_forgets(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    password = fake.last_password
    src.disconnect()
    assert fake.revoked == [password] and password not in fake.valid
    delete = fake.of("DELETE")[-1]
    assert delete["path"] == "/ocs/v2.php/core/apppassword" and delete["headers"]["OCS-APIRequest"] == "true"
    assert not os.path.exists(_cred_file())
    assert src.status() == {"state": "disconnected", "detail": {"stored": False, "server": fake.base}}
    with pytest.raises(AuthError):
        src.list()
    src.disconnect()                                          # nothing stored: nothing to revoke
    assert len(fake.of("DELETE")) == 1


def test_disconnect_unreachable_still_forgets(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    fake.srv.shutdown()
    fake.srv.server_close()
    src.disconnect()
    assert not os.path.exists(_cred_file()) and not src._store.exists()
    s = src.status()
    assert s["state"] == "disconnected" and s["detail"]["revoke_error"]["code"] == "revoke_failed"
    assert "Settings -> Security" in s["detail"]["revoke_error"]["message"]


def test_disconnect_shows_revoke_error(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    fake.revoke_status = 503
    src.disconnect()
    s = src.status()
    assert not os.path.exists(_cred_file())
    assert s["detail"]["revoke_error"]["code"] == "revoke_failed" and s["detail"]["server"] == fake.base
    assert src.status()["detail"]["revoke_error"]                # kept until the next connect
    fake.revoke_status = 200
    fake.script = ["pending"]
    d = src.connect({"server": fake.base})
    assert "revoke_error" not in d["detail"]
    src.connect({"cancel": True})
    assert "revoke_error" not in src.status()["detail"]
    # a 401 on the revoke: the password is already gone, which is what Disconnect wanted
    fake.script = ["ok"]
    _sign_in(src, fake)
    fake.valid.clear()
    src.disconnect()
    assert "revoke_error" not in src.status()["detail"]


def test_revoked_password_expires(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    src.list("Pictures")
    item = src.resolve("103")
    fake.valid.clear()                                        # revoked on the server's Settings -> Security
    fake.media_status = 200
    up = item.resolve()                                       # building the address asks nothing
    assert up.headers["Authorization"].startswith("Basic ")
    with pytest.raises(AuthError) as err:
        src.list("Pictures/OM Workspace")
    assert err.value.code == "nextcloud_unauthorized"
    s = src.status()
    assert s["state"] == "expired" and s["detail"]["error"]["code"] == "nextcloud_unauthorized"
    assert s["detail"]["stored"] and s["detail"]["server"] == fake.base
    # Connect again: a fresh flow on the stored server, no address typed
    fake.script = ["ok"]
    d = src.connect({})
    assert d["step"] == "login" and d["detail"]["server"] == fake.base and fake.starts == 2
    wait_for(lambda: src.status()["state"] == "connected")
    assert src.status()["detail"]["error"] is None
    assert _ids(src.list("Pictures"))[0] == "103"


def test_media_401_is_not_expiry(fake, upstream, server):
    src = NextcloudSource()
    _sign_in(src, fake)
    src.list("Pictures")
    fake.preview_status = 401
    srv, base = server
    item = srv.registry.add(src.resolve("103"))
    fake.media_status = 401
    status, _, _, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id), {"Range": "bytes=0-9"})
    assert status == 502 and src.status()["state"] == "connected"


# ------------------------------------------------------------ hostile XML
def test_xml_dtd_refused():
    with pytest.raises(UpstreamError) as err:
        nextcloud.parse_xml(_fixture("hostile_dtd.xml"))
    assert err.value.code == "nextcloud_xml" and "DOCTYPE" not in err.value.message


def test_xml_entities_refused():
    for name in ("hostile_entity.xml", "hostile_external.xml"):
        with pytest.raises(UpstreamError) as err:
            nextcloud.parse_xml(_fixture(name))
        assert err.value.code == "nextcloud_xml" and "passwd" not in err.value.message


def test_xml_malformed_refused(fake):
    with pytest.raises(UpstreamError) as err:
        nextcloud.parse_xml(_fixture("malformed.xml"))
    assert err.value.code == "nextcloud_xml"
    fake.folders["bad"] = _fixture("malformed.xml")
    fake.folders["dtd"] = _fixture("hostile_dtd.xml")
    src = NextcloudSource()
    _sign_in(src, fake)
    for folder in ("bad", "dtd"):
        with pytest.raises(UpstreamError) as err:
            src.list(folder)
        assert err.value.code == "nextcloud_xml"
        assert err.value.message == "The Nextcloud server's answer is not readable WebDAV."


def test_xml_oversize_refused(fake, monkeypatch):
    big = b"<d:multistatus xmlns:d=\"DAV:\">" + b" " * (nextcloud.XML_LIMIT + 1 - 46) + b"</d:multistatus>"
    assert len(big) == nextcloud.XML_LIMIT + 1
    with pytest.raises(UpstreamError) as err:
        nextcloud.parse_xml(big)
    assert err.value.code == "nextcloud_too_large"
    assert nextcloud.parse_xml(big[:40] + big[41:]).tag == "{DAV:}multistatus"   # exactly the limit parses
    monkeypatch.setattr(nextcloud, "XML_LIMIT", 4096)
    fake.folders["huge"] = multistatus([("huge", "dir", "1", None, None, False)] +
                                       [("huge/m%03d.jpg" % i, "file", str(8000 + i), "image/jpeg", None, True)
                                        for i in range(100)])
    src = NextcloudSource()
    _sign_in(src, fake)
    with pytest.raises(UpstreamError) as err:
        src.list("huge")                                      # read to the limit plus one byte, never parsed
    assert err.value.code == "nextcloud_too_large"


def test_xml_namespaces_parsed(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    listing = src.list("odd")
    assert [(e.id, e.name, e.kind, e.mime) for e in listing.items] == [
        ("301", "IMG_0001.JPG", "photo", "image/jpeg"), ("302", "VID_0002.mp4", "video", "video/mp4")]
    assert listing.items[0].date == "2025-03-05" and listing.items[0].thumb == "/api/sources/nextcloud/thumb/301"
    assert listing.items[1].thumb is None


# ------------------------------------------------------------ files
def test_resolve_sends_basic_and_range(fake, server):
    src = NextcloudSource()
    _sign_in(src, fake)
    src.list("Pictures")
    item = src.resolve("103")
    assert (item.kind, item.title, item.mime, item.source, item.source_id) == (
        "video", "PB014001.MOV", "video/quicktime", "nextcloud", "103")
    assert item.version == "71aa0c3e5b" and item.size == 268748800 and item.path is None
    up = item.resolve()
    assert up.url == fake.base + ROOT + "Pictures/PB014001.MOV" and up.opener is None
    expected = "Basic " + base64.b64encode(("%s:%s" % (LOGIN, fake.last_password)).encode()).decode()
    assert up.headers == {"Authorization": expected}
    # through the relay: the TV's range reaches the server with Basic and Range, a 206 comes back
    srv, base = server
    srv.registry.add(item)
    status, headers, got, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id),
                                      {"Range": "bytes=10-19"})
    body = fake.blobs["Pictures/PB014001.MOV"]
    assert status == 206 and got == body[10:20]
    assert headers["Content-Type"] == "video/quicktime"
    sent = fake.of("GET")[-1]
    assert sent["path"] == ROOT + "Pictures/PB014001.MOV"
    assert sent["headers"]["Authorization"] == expected and sent["headers"]["Range"] == "bytes=10-19"
    photo = src.resolve("106")
    assert photo.kind == "photo" and photo.title == "Łódź zimą.jpg"
    assert photo.resolve().url == fake.base + ROOT + "Pictures/%C5%81%C3%B3d%C5%BA%20zim%C4%85.jpg"
    for bad_id, code in (("../x", "bad_id"), ("12a", "bad_id"), ("", "bad_id"), ("104", "unknown_item")):
        with pytest.raises(NotMedia) as err:
            src.resolve(bad_id)
        assert err.value.code == code
    src.disconnect()
    with pytest.raises(AuthError):
        item.resolve()                                        # a forgotten password is never sent again


def test_unknown_file_id_found_by_search(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    item = src.resolve("9002")                                # never listed in this process
    assert item.kind == "video" and item.title == "PB014042.MOV"
    assert item.resolve().url == fake.base + ROOT + "Pictures/OM%20Workspace/2026_11_01/video/PB014042.MOV"
    search = fake.of("SEARCH")[-1]
    assert search["path"] == "/remote.php/dav/" and fake.searches == ["9002"]
    assert b"<d:href>/files/pat</d:href>" in search["body"] and b"infinity" in search["body"]
    src.resolve("9002")
    assert fake.searches == ["9002"]                          # remembered after the one lookup
    with pytest.raises(NotMedia) as err:
        src.resolve("424242")
    assert err.value.code == "unknown_item" and fake.searches == ["9002", "424242"]


def test_thumb_none_without_preview(fake, app):
    src = NextcloudSource()
    _sign_in(src, fake)
    src.list("Pictures")
    up = src.thumb("101")
    assert up.url == fake.base + "/index.php/core/preview?fileId=101&x=512&y=512&a=1"
    assert up.headers["Authorization"].startswith("Basic ")
    assert src.thumb("102") is not None                       # HEIC: the server converts it
    assert src.thumb("103") is None                           # a film: no preview, the placeholder
    assert src.thumb("../x") is None and src.thumb("x") is None
    assert src.thumb("9001").url.endswith("fileId=9001&x=512&y=512&a=1")   # unlisted: one SEARCH
    # through the API's thumbnail proxy, with the raster check
    asrc = app.sources["nextcloud"]
    _sign_in(asrc, fake)
    from tests.test_api import _json
    _, _, d = _json(app.base_url, "GET", "/api/sources/nextcloud/list?path=Pictures")
    assert d["items"][1]["thumb"] == "/api/sources/nextcloud/thumb/101"
    status, headers, body, _ = request(app.base_url, "GET", "/api/sources/nextcloud/thumb/101")
    assert status == 200 and headers["Content-Type"] == "image/jpeg" and body.startswith(b"\xff\xd8\xff")
    status, _, _, _ = request(app.base_url, "GET", "/api/sources/nextcloud/thumb/103")
    assert status == 404


# ------------------------------------------------------------ the store
def test_credential_file_private(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    path = _cred_file()
    if os.name == "posix":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    with open(path, encoding="utf-8") as fh:
        stored = json.load(fh)
    assert set(stored) == {"server", "login", "user_id", "password", "account"}
    assert stored["server"] == fake.base and stored["password"] == fake.last_password
    for missing in ("server", "login", "user_id", "password"):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in stored.items() if k != missing}, fh)
        assert AppPasswordStore("nextcloud").load() is None    # an incomplete file counts as absent
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert not AppPasswordStore("nextcloud").exists()


# ------------------------------------------------------------ the app
def test_connect_and_browse_over_the_api(app, fake):
    from tests.test_api import _json
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["sources"]["nextcloud"] == {"state": "disconnected", "detail": {"stored": False}}
    for address in ("https://pat@cloud.test", "https://[broken", "https://host\uff1a443"):
        status, _, d = _json(app.base_url, "POST", "/api/sources/nextcloud/connect", {"server": address})
        assert status == 400 and d["error"]["code"] == "bad_address"
    status, _, d = _json(app.base_url, "POST", "/api/sources/nextcloud/connect", {"server": fake.base})
    assert status == 200 and d["step"] == "login" and d["detail"]["login_url"].startswith(fake.base)

    def connected():
        _, _, s = _json(app.base_url, "GET", "/api/status")
        return s["sources"]["nextcloud"]["state"] == "connected"
    wait_for(connected)
    status, _, d = _json(app.base_url, "GET", "/api/sources/nextcloud/list?path=Pictures")
    assert status == 200 and [f["name"] for f in d["folders"]] == ["OM Workspace", "Test_Pictures"]
    assert [e["date"] for e in d["items"]][:2] == ["2026-11-01", "2026-11-01"]
    status, _, d = _json(app.base_url, "GET", "/api/sources/nextcloud/list?path=..%2Fx")
    assert status == 400 and d["error"]["code"] == "bad_path"
    fake.valid.clear()
    status, _, d = _json(app.base_url, "GET", "/api/sources/nextcloud/list?path=Pictures")
    assert status == 401 and d["error"]["code"] == "nextcloud_unauthorized"
    status, _, d = _json(app.base_url, "POST", "/api/sources/nextcloud/disconnect", {})
    assert status == 200 and d["state"] == "disconnected" and not os.path.exists(_cred_file())


def test_password_never_exposed(app, fake, capfd, monkeypatch):
    """A server that echoes the password in every error body and header: it reaches no output."""
    from tests.test_api import _json
    seen_args = []
    real_popen, real_run = subprocess.Popen, subprocess.run

    def popen(args, *a, **kw):
        seen_args.append(repr(args))
        return real_popen(args, *a, **kw)

    def run(args, *a, **kw):
        seen_args.append(repr(args))
        return real_run(args, *a, **kw)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", run)
    fake.leaky = True
    answers = []

    def call(method, path, body=None):
        status, _, d = _json(app.base_url, method, path, body)
        answers.append(json.dumps(d))
        return status, d
    call("POST", "/api/sources/nextcloud/connect", {"server": fake.base})
    wait_for(lambda: app.sources["nextcloud"].status()["state"] == "connected")
    password = fake.last_password
    assert password
    call("GET", "/api/sources/nextcloud/list")
    call("GET", "/api/sources/nextcloud/list?path=Pictures")
    call("GET", "/api/sources/nextcloud/list?path=Missing")            # a 404 with the password in its body
    fake.preview_status = 500
    status, _, body, _ = request(app.base_url, "GET", "/api/sources/nextcloud/thumb/101")
    answers.append(body.decode("utf-8", "replace"))
    fake.media_status = 500
    status, d = call("POST", "/api/cast", {"source": "nextcloud", "id": "103"})
    wait_for(lambda: app.current is not None and app.current.as_dict().get("state") in
             ("failed", "finished", "playing", "stopped"), timeout=5)
    item = app.server.registry.items()[-1] if app.server.registry.items() else None
    if item is not None:
        status, _, body, _ = request(app.base_url, "GET", "/m/%s/%s" % (app.server.media_token, item.id),
                                     {"Range": "bytes=0-9"})
        answers.append(body.decode("utf-8", "replace"))
    call("POST", "/api/stop", {})
    fake.valid.clear()                                                  # revoked: 401s from now on
    call("GET", "/api/sources/nextcloud/list?path=Pictures")
    call("POST", "/api/sources/nextcloud/connect", {})
    call("POST", "/api/sources/nextcloud/connect", {"cancel": True})
    fake.valid.add(password)
    fake.revoke_status = 500
    call("POST", "/api/sources/nextcloud/disconnect", {})
    call("GET", "/api/status")
    call("GET", "/api/errors")
    out, err = capfd.readouterr()
    sinks = {"answers": "\n".join(answers), "status": json.dumps(app.status()),
             "source status": json.dumps(app.sources["nextcloud"].status()),
             "errors": json.dumps(app.errors.list()), "stdout": out, "stderr": err,
             "subprocess": "\n".join(seen_args)}
    encoded = base64.b64encode(("%s:%s" % (LOGIN, password)).encode()).decode()
    for name, text in sinks.items():
        assert password not in text, name
        assert encoded not in text, name
    assert "password=" not in sinks["answers"]                          # no error carried the server's body


def test_registered_in_the_app(app):
    assert isinstance(app.sources["nextcloud"], NextcloudSource)
    assert app.sources["nextcloud"].name == "nextcloud"


@pytest.mark.parametrize("action", ["cancel", "disconnect", "close"])
def test_pending_login_start_can_be_cancelled(fake, monkeypatch, action):
    src = NextcloudSource()
    entered, release = threading.Event(), threading.Event()
    original = loginflow.start

    def delayed(base):
        flow = original(base)
        entered.set()
        assert release.wait(5)
        return flow

    monkeypatch.setattr(loginflow, "start", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(src.connect, {"server": fake.base})
        try:
            assert entered.wait(5)
            if action == "cancel":
                src.connect({"cancel": True})
            else:
                getattr(src, action)()
        finally:
            release.set()
        with pytest.raises(AuthError) as err:
            future.result(timeout=5)
    assert err.value.code == "cancelled"
    assert src.status()["state"] == "disconnected" and not src._store.exists()
    assert len(fake.of("POST")) == 1                          # the abandoned start never starts polling


@pytest.mark.parametrize("method", ["PROPFIND", "SEARCH"])
@pytest.mark.parametrize("replacement", ["disconnect", "sign_in"])
def test_late_dav_answer_cannot_publish_old_account(fake, monkeypatch, method, replacement):
    src = NextcloudSource()
    _sign_in(src, fake)
    entered, release = threading.Event(), threading.Event()
    original = loginflow.call

    def delayed(verb, *args, **kwargs):
        answer = original(verb, *args, **kwargs)
        if verb == method:
            entered.set()
            assert release.wait(5)
        return answer

    monkeypatch.setattr(loginflow, "call", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(src.list, "Pictures") if method == "PROPFIND" else pool.submit(src.resolve, "9001")
        try:
            assert entered.wait(5)
            src.disconnect()
            if replacement == "sign_in":
                fake.user_id = "other"
                _sign_in(src, fake)
        finally:
            release.set()
        with pytest.raises(AuthError) as err:
            future.result(timeout=5)
    assert err.value.code == "cancelled"
    assert not src._files and not src._snapshots
    if replacement == "sign_in":
        assert src._store.load()["user_id"] == "other"


def test_resolved_media_does_not_rebind_to_a_new_account(fake):
    src = NextcloudSource()
    _sign_in(src, fake)
    src.list("Pictures")
    item = src.resolve("102")
    src.disconnect()
    fake.user_id = "other"
    _sign_in(src, fake)
    with pytest.raises(AuthError) as err:
        item.resolve()
    assert err.value.code == "cancelled"


def test_preview_does_not_mix_a_cached_record_with_a_new_account(fake, monkeypatch):
    src = NextcloudSource()
    _sign_in(src, fake)
    src.list("Pictures")
    original = src._file

    def switched(file_id):
        rec = original(file_id)
        src.disconnect()
        fake.user_id = "other"
        _sign_in(src, fake)
        return rec

    monkeypatch.setattr(src, "_file", switched)
    with pytest.raises(AuthError) as err:
        src.thumb("101")
    assert err.value.code == "cancelled"


@pytest.mark.parametrize("replacement", ["disconnect", "sign_in"])
def test_late_verification_cannot_restore_old_credentials(fake, monkeypatch, replacement):
    src = NextcloudSource()
    _sign_in(src, fake)
    entered, release = threading.Event(), threading.Event()
    original, first = loginflow.user, True

    def delayed(*args):
        nonlocal first
        who = original(*args)
        if first:
            first = False
            who["id"] = "corrected-old-id"
            entered.set()
            assert release.wait(5)
        return who

    monkeypatch.setattr(loginflow, "user", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(src.connect, {})
        try:
            assert entered.wait(5)
            src.disconnect()
            if replacement == "sign_in":
                fake.user_id = "other"
                _sign_in(src, fake)
        finally:
            release.set()
        future.result(timeout=5)
    record = src._store.load()
    if replacement == "sign_in":
        assert record["user_id"] == "other" and src.status()["state"] == "connected"
    else:
        assert record is None and src.status()["state"] == "disconnected"


def test_slow_disconnect_does_not_erase_a_new_sign_in(fake, monkeypatch):
    src = NextcloudSource()
    _sign_in(src, fake)
    entered, release = threading.Event(), threading.Event()
    original = loginflow.revoke

    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(loginflow, "revoke", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(src.disconnect)
        try:
            assert entered.wait(5)
            fake.user_id = "other"
            _sign_in(src, fake)
        finally:
            release.set()
        future.result(timeout=5)
    assert src._store.load()["user_id"] == "other" and src.status()["state"] == "connected"
    assert src.status()["detail"].get("revoke_error") is None


@pytest.mark.parametrize("address", ["https://[broken", "https://host\uff1a443", "https://[invalid]"])
def test_malformed_authority_is_a_validation_error(address):
    with pytest.raises(ConfigError) as err:
        loginflow.normalise(address)
    assert err.value.code == "bad_address" and err.value.message
    assert not loginflow.same_origin(loginflow.normalise("https://host"), address)


@pytest.mark.parametrize("kinds", [("dir", "dir"), ("dir", "file"), ("file", "dir")])
def test_first_file_id_wins_for_folders_and_files(fake, kinds):
    fake.folders[""] = multistatus([(name, kind, "51", "image/jpeg", None, False)
                                     for name, kind in zip(("first", "second"), kinds)])
    src = NextcloudSource()
    _sign_in(src, fake)
    listing = src.list()
    assert [e.name for e in listing.folders + listing.items] == ["first"]
