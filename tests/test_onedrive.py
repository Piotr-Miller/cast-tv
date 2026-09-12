"""The OneDrive source on the ``Source`` contract, against a scripted Microsoft (login and Graph on one stub)."""
import http.server
import json
import os
import re
import socketserver
import threading
import time
import urllib.parse

import pytest

from castlib import config
from castlib.auth import devicecode
from castlib.errors import AuthError, ConfigError, NotMedia
from castlib.sources import onedrive
from castlib.sources.onedrive import OneDriveSource
from tests.conftest import request, wait_for

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "onedrive")
GRAPH_REAL = "https://graph.microsoft.com/v1.0"


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _all_items():
    items = []
    for name in ("children_root.json", "children_pictures.json", "children_camera_p1.json",
                 "children_camera_p2.json"):
        items.extend(json.loads(_fixture(name))["value"])
    return items


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        f = self.server.fake
        n = int(self.headers.get("Content-Length") or 0)
        form = dict(urllib.parse.parse_qsl(self.rfile.read(n).decode("utf-8")))
        with f.lock:
            f.forms.append((self.path, form))
        if self.path.endswith("/oauth2/v2.0/devicecode"):
            with f.lock:
                f.devicecode_calls += 1
                n = f.devicecode_calls
            return self._send(200, {
                "user_code": "ABCD-1234", "device_code": "dc-%d" % n,
                "verification_uri": "https://microsoft.com/devicelogin",
                "expires_in": f.expires_in, "interval": f.interval,
                "message": "To sign in, use a web browser to open the page "
                           "https://microsoft.com/devicelogin and enter the code ABCD-1234 to authenticate."})
        if self.path.endswith("/oauth2/v2.0/token"):
            if form.get("grant_type") == devicecode.GRANT_DEVICE:
                with f.lock:
                    answer = f.script[0] if len(f.script) == 1 else f.script.pop(0)
                if answer == "ok":
                    if f.before_answer is not None:
                        f.before_answer("token")
                    return self._send(200, f.issue())
                if answer == "http500":
                    return self._send(500, {"error": "server_error"})
                return self._send(400, {"error": answer, "error_description": "AADSTS: " + answer})
            if form.get("grant_type") == "refresh_token":
                if f.refresh == "ok" and (form.get("refresh_token") or "").startswith("rt"):
                    return self._send(200, f.issue())
                if f.refresh == "http500":
                    return self._send(500, {"error": "server_error"})
                return self._send(400, {"error": "invalid_grant",
                                        "error_description": "AADSTS70000: The refresh token has expired."})
        self._send(404, {})

    def do_GET(self):
        f = self.server.fake
        parsed = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        bearer = (self.headers.get("Authorization") or "")[7:]
        with f.lock:
            f.calls.append((parsed.path, q, bearer))
            valid = bearer in f.valid
        if not valid:
            return self._send(401, {"error": {"code": "InvalidAuthenticationToken",
                                              "message": "Access token has expired or is not yet valid."}})
        path = parsed.path
        if path == "/v1.0/me":
            return self._send(200, {"displayName": "Piotr Miller", "userPrincipalName": "piotr@example.com"})
        m = re.match(r"^/v1.0/me/drive/(?:root|items/([^/]+))(/children|/thumbnails)?$", path)
        if not m:
            return self._send(404, {"error": {"code": "itemNotFound", "message": "not found"}})
        item_id, tail = m.group(1), m.group(2)
        if tail == "/children":
            if item_id is None:
                text = _fixture("children_root.json")
            elif item_id == "f-pictures":
                text = _fixture("children_pictures.json")
            elif item_id == "f-camera":
                text = _fixture("children_camera_p2.json" if q.get("$skiptoken") == "p2"
                                else "children_camera_p1.json")
            elif item_id == "f-docs":
                text = '{"value": []}'
            else:
                return self._send(404, {"error": {"code": "itemNotFound", "message": "not found"}})
            body = text.replace(GRAPH_REAL, f.base + "/v1.0").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        item = next((i for i in _all_items() if i["id"] == item_id), None)
        if tail == "/thumbnails":
            if item is None or not item.get("thumbnails"):
                return self._send(200, {"value": []})
            with f.lock:
                f.thumb_sig += 1
                sig = f.thumb_sig
            return self._send(200, {"value": [{"id": "0", "large": {
                "width": 800, "height": 600,
                "url": "https://cdn.test/thumbs/%s/large?sig=%d" % (item_id, sig)}}]})
        if item is None:
            return self._send(404, {"error": {"code": "itemNotFound", "message": "not found"}})
        if "$select" in q:
            # live Graph (probed 2026-09-12): any $select drops the downloadUrl annotation,
            # and a $select that names it yields just the other fields
            wanted = [k.strip() for k in q["$select"].split(",")]
            return self._send(200, {k: v for k, v in item.items() if k in wanted}
                              | ({"thumbnails": item["thumbnails"]} if "thumbnails" in item and "$expand" in q else {}))
        if "folder" in item:
            return self._send(200, item)
        with f.lock:
            f.dl_calls += 1
            sig = f.dl_calls
        return self._send(200, dict(item, **{"@microsoft.graph.downloadUrl": "%s/dl/%s?sig=%d" % (f.download, item_id, sig)}))


class FakeMicrosoft:
    """login.microsoftonline.com and graph.microsoft.com on one stub: scripted token answers, fixture pages."""

    def __init__(self):
        self.valid = set()                      # access tokens Graph accepts
        self.issued = 0
        self.script = ["authorization_pending", "ok"]   # device-token answers in order; the last one repeats
        self.refresh = "ok"                     # or "invalid_grant" / "http500"
        self.interval = 0.01
        self.expires_in = 600
        self.calls = []                         # Graph GETs: (path, query, bearer)
        self.forms = []                         # login POSTs: (path, form)
        self.devicecode_calls = 0
        self.dl_calls = 0
        self.thumb_sig = 0
        self.download = "https://cdn.test"      # where downloadUrl points; tests aim it at an upstream stub
        self.before_answer = None               # callable(kind), run before an "ok" token answer
        self.lock = threading.Lock()
        self.base = ""

    def issue(self) -> dict:
        with self.lock:
            self.issued += 1
            n = self.issued
            self.valid.add("at%d" % n)
        return {"token_type": "Bearer", "scope": "Files.Read User.Read", "expires_in": 3600,
                "access_token": "at%d" % n, "refresh_token": "rt%d" % n}

    def token_posts(self):
        return [form for path, form in self.forms if path.endswith("/token")]

    def graph(self, path_part):
        return [c for c in self.calls if path_part in c[0]]


class _Stub(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = FakeMicrosoft()
    srv = _Stub(("127.0.0.1", 0), _Handler)
    srv.fake = f
    f.base = "http://127.0.0.1:%d" % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    monkeypatch.setattr(devicecode, "AUTHORITY", f.base)
    monkeypatch.setattr(devicecode, "SLOW_DOWN_STEP", 0.05)
    monkeypatch.setattr(onedrive, "GRAPH", f.base + "/v1.0")
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.setattr(config, "_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("ONEDRIVE_CLIENT_ID", "client-test")
    try:
        yield f
    finally:
        srv.shutdown()
        srv.server_close()


def _sign_in(src, fake):
    d = src.connect({})
    assert d["step"] == "code" and d["state"] == "connecting"
    wait_for(lambda: src.status()["state"] == "connected")
    return d


def _token_file():
    return os.path.join(config.config_dir(), "onedrive.json")


# ---------------------------------------------------------------- the gate
def test_status_before_and_after_connect(fake):
    src = OneDriveSource()
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    d = src.connect({})
    assert d["step"] == "code" and d["state"] == "connecting"
    assert d["detail"]["user_code"] == "ABCD-1234"
    assert d["detail"]["verification_uri"] == "https://microsoft.com/devicelogin"
    assert 0 < d["detail"]["expires_in"] <= 600 and "ABCD-1234" in d["detail"]["message"]
    again = src.connect({})                                   # while the code is pending: the same code
    assert again["step"] == "code" and again["detail"]["user_code"] == "ABCD-1234"
    assert fake.devicecode_calls == 1                         # not a second flow
    wait_for(lambda: src.status()["state"] == "connected")
    s = src.status()
    assert s["detail"]["stored"] and s["detail"]["verified_at"]
    wait_for(lambda: src.status()["detail"]["account"] == "Piotr Miller (piotr@example.com)")
    assert src.status()["detail"]["user"] == {"displayName": "Piotr Miller",
                                              "userPrincipalName": "piotr@example.com"}
    dc = [f for p, f in fake.forms if p.endswith("/devicecode")]
    assert dc == [{"client_id": "client-test", "scope": "Files.Read offline_access User.Read"}]
    polls = fake.token_posts()
    assert len(polls) == 2 and all(f["grant_type"] == devicecode.GRANT_DEVICE for f in polls)
    assert all(f["client_id"] == "client-test" and f["device_code"] == "dc-1" for f in polls)
    # a restart: stored but not "connected" until verified in this process, and no new flow for that
    fresh = OneDriveSource()
    s = fresh.status()
    assert s["state"] == "disconnected" and s["detail"]["stored"]
    assert s["detail"]["account"] == "Piotr Miller (piotr@example.com)"
    d = fresh.connect({})
    assert d["state"] == "connected" and "step" not in d
    assert fake.devicecode_calls == 1 and fake.graph("/me")[-1][2] == "at1"
    fresh.disconnect()
    assert fresh.status() == {"state": "disconnected", "detail": {"stored": False}}
    assert not os.path.exists(_token_file())


def test_devicecode_polling_errors(fake, monkeypatch):
    fake.script = ["authorization_pending", "slow_down", "authorization_pending", "ok"]
    flow = devicecode.start("client-test", onedrive.SCOPES)
    stamps = []
    fake.before_answer = lambda kind: stamps.append(time.monotonic())
    t0 = time.monotonic()
    tokens = devicecode.poll("client-test", flow, stop=threading.Event())
    assert tokens["access_token"] == "at1" and tokens["refresh_token"] == "rt1"
    assert len(fake.token_posts()) == 4
    assert stamps[0] - t0 >= 0.05                              # slow_down added its step before the next polls
    for error in ("authorization_declined", "bad_verification_code"):
        fake.script = [error]
        with pytest.raises(AuthError) as err:
            devicecode.poll("client-test", flow, stop=threading.Event())
        assert err.value.code == error
    fake.script = ["http500"]
    with pytest.raises(Exception) as err:
        devicecode.poll("client-test", flow, stop=threading.Event())
    assert getattr(err.value, "code", "") == "token_refused"
    # through the source: a declined sign-in ends the flow, the gate says why, nothing is stored
    fake.script = ["authorization_declined"]
    src = OneDriveSource()
    src.connect({})
    wait_for(lambda: src.status()["state"] != "connecting")
    s = src.status()
    assert s["state"] == "disconnected" and not s["detail"]["stored"]
    assert s["detail"]["flow_error"]["code"] == "authorization_declined"
    assert not os.path.exists(_token_file())


def test_devicecode_expired(fake):
    fake.script = ["expired_token"]
    src = OneDriveSource()
    src.connect({})
    wait_for(lambda: src.status()["state"] != "connecting")
    s = src.status()
    assert s["state"] == "disconnected" and s["detail"]["flow_error"]["code"] == "expired_token"
    assert "Start again" in s["detail"]["flow_error"]["message"]
    fake.script = ["authorization_pending", "ok"]
    d = src.connect({})                                       # "start again": a new code
    assert d["step"] == "code" and fake.devicecode_calls == 2
    assert d["detail"].get("flow_error") is None
    wait_for(lambda: src.status()["state"] == "connected")
    # the local deadline, for a Microsoft that keeps saying "pending" past expires_in
    fake.script = ["authorization_pending"]
    fake.expires_in = 0.05
    flow = devicecode.start("client-test", onedrive.SCOPES)
    with pytest.raises(AuthError) as err:
        devicecode.poll("client-test", flow, stop=threading.Event())
    assert err.value.code == "expired_token"


def test_refresh_on_401(fake):
    src = OneDriveSource()
    _sign_in(src, fake)
    with fake.lock:
        fake.valid.discard("at1")                             # the access token died server-side
    listing = src.list()
    assert [e.id for e in listing.items] == ["heic-1", "vid-1", "vid-heavy", "png-1"]
    root = fake.graph("/root/children")
    assert [c[2] for c in root] == ["at1", "at2"]             # 401 on the old token, retried on the new one
    refreshes = [f for f in fake.token_posts() if f["grant_type"] == "refresh_token"]
    assert refreshes == [{"grant_type": "refresh_token", "client_id": "client-test",
                          "refresh_token": "rt1", "scope": onedrive.SCOPES}]
    assert src.status()["state"] == "connected"
    with open(_token_file(), encoding="utf-8") as fh:
        stored = json.load(fh)
    assert stored["access_token"] == "at2" and stored["refresh_token"] == "rt2"
    # a token about to expire is refreshed before Graph ever sees it
    src._store._data["expires_at"] = time.time() + 30
    src.list()
    assert fake.graph("/root/children")[-1][2] == "at3"
    assert fake.graph("/root/children")[-2][2] == "at2"       # no 401 in between
    # the refresh token itself is refused: expired, the gate returns, a new flow starts on connect
    fake.refresh = "invalid_grant"
    with fake.lock:
        fake.valid.clear()
    with pytest.raises(AuthError) as err:
        src.list()
    assert err.value.code == "refresh_rejected"
    s = src.status()
    assert s["state"] == "expired" and s["detail"]["error"]["code"] == "refresh_rejected"
    assert s["detail"]["stored"]                              # the credential stays until replaced
    fake.refresh = "ok"
    fake.script = ["ok"]
    d = src.connect({})
    assert d["step"] == "code" and fake.devicecode_calls == 2
    wait_for(lambda: src.status()["state"] == "connected")
    assert src.status()["detail"]["error"] is None
    assert [e.id for e in src.list().items][0] == "heic-1"


def test_invalid_grant_over_the_api_is_401(app, fake):
    from tests.test_api import _json
    src = app.sources["onedrive"]
    _sign_in(src, fake)
    fake.refresh = "invalid_grant"
    with fake.lock:
        fake.valid.clear()
    status, _, d = _json(app.base_url, "GET", "/api/sources/onedrive/list")
    assert status == 401 and d["error"]["code"] == "refresh_rejected"
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["sources"]["onedrive"]["state"] == "expired"


# ------------------------------------------------------------- the listing
def test_folders_and_media_only(fake, capsys, monkeypatch):
    from castlib import media
    monkeypatch.setattr(media, "_hidden_kinds_logged", set())
    src = OneDriveSource()
    _sign_in(src, fake)
    listing = src.list()
    assert [(f.id, f.name, f.count) for f in listing.folders] == [("f-pictures", "Pictures", 2),
                                                                  ("f-docs", "Documents", 0)]
    by_id = {e.id: e for e in listing.items}
    assert list(by_id) == ["heic-1", "vid-1", "vid-heavy", "png-1"]   # pdf, gif and raw are hidden
    err = capsys.readouterr().err
    assert "hiding an item of unknown kind 'image/gif'" in err
    assert "image/x-adobe-dng" in err and "application/pdf" not in err   # a document is quietly not media
    h = by_id["heic-1"]
    assert h.kind == "photo" and h.mime == "image/heic" and (h.width, h.height) == (4032, 3024)
    assert h.date == "2026-07-26" and h.size == 2456789 and h.duration is None   # takenDateTime, not modified
    assert h.thumb == "/api/sources/onedrive/thumb/heic-1" and h.warn is None and h.variants is None
    v = by_id["vid-1"]
    assert v.kind == "video" and v.mime == "video/mp4" and (v.width, v.height) == (3840, 2160)
    assert v.duration == 9.28 and v.size == 13906000 and v.thumb is None     # no thumbnails: a placeholder
    assert v.warn is None and v.date == "2026-07-27"
    heavy = by_id["vid-heavy"]
    assert heavy.warn == "too heavy: 119 Mbit/s" and heavy.variants is None   # no lighter variant to offer
    assert heavy.mime == "video/quicktime" and heavy.thumb == "/api/sources/onedrive/thumb/vid-heavy"
    assert by_id["png-1"].thumb == "/api/sources/onedrive/thumb/png-1"     # medium only: still a thumbnail
    assert listing.next is None
    assert listing.crumbs == [{"id": None, "name": "OneDrive"}]
    q = fake.graph("/root/children")[-1][1]
    assert q == {"$select": "id,name,size,lastModifiedDateTime,folder,file,image,photo,video",
                 "$expand": "thumbnails($select=medium,large)", "$top": "200"}
    pictures = src.list("f-pictures")
    assert [(f.id, f.count) for f in pictures.folders] == [("f-camera", 250)]
    assert [e.id for e in pictures.items] == ["jpg-0"]
    assert pictures.crumbs == [{"id": None, "name": "OneDrive"}, {"id": "f-pictures", "name": "Pictures"}]
    assert fake.graph("/items/f-pictures/children")[-1][1]["$top"] == "200"
    empty = src.list("f-docs")
    assert empty.items == [] and empty.folders == []
    assert empty.crumbs == [{"id": None, "name": "OneDrive"}, {"id": "f-docs", "name": "Documents"}]
    for bad in ("../x", "a b", "x" * 129):
        with pytest.raises(ConfigError) as err:
            src.list(bad)
        assert err.value.code == "bad_path"
    assert listing.as_dict()["folders"][0] == {"id": "f-pictures", "name": "Pictures", "count": 2}


def test_list_pages_nextlink(fake):
    src = OneDriveSource()
    _sign_in(src, fake)
    first = src.list("f-camera")                              # straight into a deep folder
    assert [e.id for e in first.items] == ["cam-1", "cam-2", "cam-3"]
    assert first.next == fake.base + "/v1.0/me/drive/items/f-camera/children?$skiptoken=p2"
    assert first.crumbs == [{"id": None, "name": "OneDrive"}, {"id": "f-pictures", "name": "Pictures"},
                            {"id": "f-camera", "name": "Camera Roll"}]     # looked up, never listed
    lookups = [c for c in fake.calls if c[0].endswith(("/items/f-camera", "/items/f-pictures"))]
    assert [c[0].rsplit("/", 1)[1] for c in lookups] == ["f-camera", "f-pictures"]
    second = src.list("f-camera", page=first.next)
    assert [e.id for e in second.items] == ["cam-4", "cam-5"] and second.next is None
    assert second.crumbs == first.crumbs
    assert fake.graph("/items/f-camera/children")[-1][1]["$skiptoken"] == "p2"
    assert len([c for c in fake.calls if c[0].endswith("/items/f-camera")]) == 1   # the crumb is remembered
    # a page must be Graph's own link: the bearer goes nowhere else
    before = len(fake.calls)
    for bad in ("https://evil.test/v1.0/me/drive/root/children", "p2", "http://" + fake.base[7:] + "/x"):
        with pytest.raises(ConfigError) as err:
            src.list("f-camera", page=bad)
        assert err.value.code == "bad_page"
    assert len(fake.calls) == before
    assert first.items[2].kind == "video" and first.items[2].duration == 22.5
    assert second.items[1].thumb is None                      # cam-5 has no thumbnail set


# --------------------------------------------------------------- resolving
def test_download_url_resolved_on_open(fake, upstream, server):
    body = bytes(range(256)) * 4
    up = upstream(body, ctype="video/mp4")
    fake.download = up.base
    src = OneDriveSource()
    _sign_in(src, fake)
    src.list()
    item = src.resolve("vid-1")
    assert fake.dl_calls == 0                                 # listing and resolve() ask for no address
    assert item.kind == "video" and item.title == "clip.mp4" and item.mime == "video/mp4"
    assert item.source == "onedrive" and item.source_id == "vid-1"
    assert item.version == "2026-07-27T09:31:00Z:13906000"
    assert (item.size, item.width, item.height, item.duration) == (13906000, 3840, 2160, 9.28)
    first = item.resolve()
    assert fake.dl_calls == 1 and first.headers == {} and first.opener is None
    assert first.url == up.base + "/dl/vid-1?sig=1"
    assert fake.graph("/items/vid-1")[-1][1] == {}                # a plain GET: any $select would drop the address
    assert item.resolve().url == up.base + "/dl/vid-1?sig=2"   # fresh on every open
    # through the relay: the TV's range request reaches the pre-authenticated address unadorned
    srv, base = server
    srv.registry.add(item)
    status, headers, got, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id),
                                      {"Range": "bytes=10-19"})
    assert status == 206 and got == body[10:20]
    assert headers["Content-Type"] == "video/mp4"
    assert up.requests[-1]["path"] == "/dl/vid-1?sig=3"
    assert "Authorization" not in up.requests[-1]["headers"]
    assert fake.dl_calls == 3
    photo = src.resolve("heic-1")
    assert photo.kind == "photo" and photo.mime == "image/heic" and photo.width == 4032
    assert photo.resolve().url == up.base + "/dl/heic-1?sig=4"
    # an id this process never listed: one lookup; a folder, an unknown id and a bad id: not media
    unlisted = src.resolve("cam-4")
    assert unlisted.kind == "photo" and unlisted.title == "IMG_1004.JPG"
    assert fake.calls[-1][0].endswith("/items/cam-4") and "parentReference" in fake.calls[-1][1]["$select"]
    for bad_id, code in (("f-pictures", "unknown_item"), ("nope", "unknown_item"), ("../x", "bad_id")):
        with pytest.raises(NotMedia) as err:
            src.resolve(bad_id)
        assert err.value.code == code
    assert not any(c[0].endswith("/items/../x") for c in fake.calls)


def test_resolve_after_expiry_flips_to_expired(fake):
    src = OneDriveSource()
    _sign_in(src, fake)
    src.list()
    item = src.resolve("vid-1")
    fake.refresh = "invalid_grant"
    with fake.lock:
        fake.valid.clear()
    with pytest.raises(AuthError):
        item.resolve()                                        # the relay's re-resolve lands here
    assert src.status()["state"] == "expired"


def test_thumb_uses_the_listing_then_asks_again(fake):
    src = OneDriveSource()
    _sign_in(src, fake)
    src.list()
    assert src.thumb("heic-1").url == "https://cdn.test/thumbs/heic-1/large?sig=1"
    assert src.thumb("heic-1").headers == {}                  # pre-authenticated
    assert src.thumb("png-1").url == "https://cdn.test/thumbs/png-1/medium?sig=1"
    assert src.thumb("vid-1") is None                         # listed without a thumbnail set
    assert not fake.graph("/thumbnails")
    with src._lock:                                           # the listing aged past THUMB_FRESH
        src._thumbs["heic-1"] = (src._thumbs["heic-1"][0], time.time() - onedrive.THUMB_FRESH - 1)
    assert src.thumb("heic-1").url == "https://cdn.test/thumbs/heic-1/large?sig=1"
    assert fake.graph("/items/heic-1/thumbnails")[-1][1] == {"$select": "medium,large"}
    assert src.thumb("heic-1").url == "https://cdn.test/thumbs/heic-1/large?sig=1"   # fresh again: cached
    assert len(fake.graph("/thumbnails")) == 1
    assert src.thumb("cam-4").url == "https://cdn.test/thumbs/cam-4/large?sig=1"   # unlisted: one item lookup
    assert src.thumb("nope") is None and src.thumb("../x") is None


def test_thumb_route_serves_the_graph_thumbnail(app, upstream, fake):
    up = upstream(b"\x89PNG\r\n\x1a\n" + b"\0" * 16, ctype="image/png")
    src = app.sources["onedrive"]
    _sign_in(src, fake)
    from tests.test_api import _json
    _, _, d = _json(app.base_url, "GET", "/api/sources/onedrive/list")
    assert d["items"][0]["thumb"] == "/api/sources/onedrive/thumb/heic-1"
    with src._lock:
        src._thumbs["heic-1"] = (up.base + "/thumbs/heic-1/large?sig=1", time.time())
    status, headers, body, _ = request(app.base_url, "GET", "/api/sources/onedrive/thumb/heic-1")
    assert status == 200 and headers["Content-Type"] == "image/png" and body.startswith(b"\x89PNG")
    assert up.requests[-1]["path"] == "/thumbs/heic-1/large?sig=1"
    status, _, _, _ = request(app.base_url, "GET", "/api/sources/onedrive/thumb/vid-1")
    assert status == 404


# ------------------------------------------------------------- the store
def test_token_file_mode_0600(fake):
    src = OneDriveSource()
    _sign_in(src, fake)
    path = _token_file()
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    with open(path, encoding="utf-8") as fh:
        stored = json.load(fh)
    assert stored["access_token"] == "at1" and stored["refresh_token"] == "rt1"
    assert stored["scope"] == onedrive.SCOPES and stored["expires_at"] > time.time() + 3000
    wait_for(lambda: json.load(open(path, encoding="utf-8")).get("account"))
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["account"] == {"displayName": "Piotr Miller",
                                            "userPrincipalName": "piotr@example.com"}
    with fake.lock:
        fake.valid.discard("at1")
    src.list()                                                # a refresh rewrites the file
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["access_token"] == "at2"
    src.disconnect()
    assert not os.path.exists(path)


def test_disconnect_during_the_flow_drops_a_late_token(fake):
    fake.script = ["ok"]
    held, release = threading.Event(), threading.Event()

    def hold(kind):
        held.set()
        release.wait(5)
    fake.before_answer = hold
    src = OneDriveSource()
    src.connect({})
    assert held.wait(5)                                       # Microsoft is about to hand over the token
    src.disconnect()
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    release.set()
    time.sleep(0.1)
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    assert not os.path.exists(_token_file())                  # the late token was dropped
    # cancelling from the gate ends the poll without a token or an error
    fake.before_answer = None
    fake.script = ["authorization_pending"]
    src.connect({})
    assert src.status()["state"] == "connecting"
    src.connect({"cancel": True})
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    n = len(fake.token_posts())
    time.sleep(0.1)
    assert len(fake.token_posts()) <= n + 1                   # the poll loop stopped


def test_no_client_id_is_a_config_error(app, fake, monkeypatch):
    monkeypatch.delenv("ONEDRIVE_CLIENT_ID")
    monkeypatch.setattr(onedrive, "DEFAULT_CLIENT_ID", "")
    src = OneDriveSource()
    with pytest.raises(ConfigError) as err:
        src.connect({})
    assert err.value.code == "no_client_id" and "ONEDRIVE_CLIENT_ID" in err.value.hint
    assert fake.devicecode_calls == 0
    from tests.test_api import _json
    status, _, d = _json(app.base_url, "POST", "/api/sources/onedrive/connect", {})
    assert status == 400 and d["error"]["code"] == "no_client_id"


def test_connect_and_browse_over_the_api(app, fake):
    from tests.test_api import _json
    status, _, d = _json(app.base_url, "POST", "/api/sources/onedrive/connect", {})
    assert status == 200 and d["step"] == "code" and d["state"] == "connecting"
    assert d["detail"]["user_code"] == "ABCD-1234"
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["sources"]["onedrive"]["state"] == "connecting"
    assert s["sources"]["onedrive"]["detail"]["verification_uri"] == "https://microsoft.com/devicelogin"

    def connected():
        _, _, s = _json(app.base_url, "GET", "/api/status")
        return s["sources"]["onedrive"]["state"] == "connected"
    wait_for(connected)
    status, _, d = _json(app.base_url, "GET", "/api/sources/onedrive/list")
    assert status == 200 and [f["name"] for f in d["folders"]] == ["Pictures", "Documents"]
    assert [e["id"] for e in d["items"]] == ["heic-1", "vid-1", "vid-heavy", "png-1"]
    assert d["crumbs"] == [{"id": None, "name": "OneDrive"}]
    status, _, d = _json(app.base_url, "GET", "/api/sources/onedrive/list?path=f-camera")
    assert status == 200 and [c["name"] for c in d["crumbs"]] == ["OneDrive", "Pictures", "Camera Roll"]
    assert d["next"].startswith(fake.base)
    status, _, d2 = _json(app.base_url, "GET", "/api/sources/onedrive/list?path=f-camera&page="
                          + urllib.parse.quote(d["next"], safe=""))
    assert status == 200 and [e["id"] for e in d2["items"]] == ["cam-4", "cam-5"] and d2["next"] is None
    status, _, d = _json(app.base_url, "GET", "/api/sources/onedrive/list?path=..%2Fx")
    assert status == 400 and d["error"]["code"] == "bad_path"
    status, _, d = _json(app.base_url, "GET", "/api/sources/onedrive/list?page=https://evil.test/")
    assert status == 400 and d["error"]["code"] == "bad_page"
    status, _, d = _json(app.base_url, "POST", "/api/sources/onedrive/disconnect", {})
    assert status == 200 and d == {"state": "disconnected", "detail": {"stored": False}}
