"""The Google Photos source on the ``Source`` contract, against a scripted Google (token endpoint, Picker API and media host on one stub)."""
import base64
import hashlib
import http.client
import http.server
import io
import json
import os
import socketserver
import threading
import time
import urllib.parse
import urllib.request
import urllib.response

import pytest
import sys

from castlib import config, photos
from castlib.auth import loopback
from castlib.errors import AuthError, ConfigError, NotMedia, UpstreamError
from castlib.items import MediaItem
from castlib.sources import gphotos, sharelink
from castlib.sources.gphotos import GPhotosSource
from tests.conftest import request, wait_for
from tests.fixtures.make import jpeg

JPEG = jpeg(64, 48)
PNG_TILE = b"\x89PNG\r\n\x1a\n" + b"\0" * 32      # what Google answers a fetch without the bearer (spike, 2026-09-09)
VIDEO = bytes(range(256)) * 8


def _rfc3339(t: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _item(media_id: str, kind: str = "PHOTO", mime: str = "image/jpeg", name: str | None = None) -> dict:
    """A ``PickedMediaItem`` as the Picker reference shapes it (research 2026-09-09: ``mediaFile.*``, ``createTime``)."""
    meta = {"width": 4032, "height": 3024, "cameraMake": "Google", "cameraModel": "Pixel 8"}
    if kind == "VIDEO":
        meta["videoMetadata"] = {"fps": 30, "processingStatus": "READY"}
    else:
        meta["photoMetadata"] = {"focalLength": 6.9, "apertureFNumber": 1.7, "isoEquivalent": 40}
    return {"id": media_id, "createTime": "2026-08-16T12:34:56Z", "type": kind,
            "mediaFile": {"mimeType": mime, "filename": name or "%s.%s" % (media_id, "mp4" if kind == "VIDEO" else "jpg"),
                          "mediaFileMetadata": meta}}   # baseUrl is stamped per listing by the fake


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, status, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _bearer_ok(self):
        f = self.server.fake
        bearer = (self.headers.get("Authorization") or "")[7:]
        with f.lock:
            return bearer in f.valid and not f.reject_bearers

    def _error(self, status, reason, message):
        return self._send(status, {"error": {"code": status, "message": message, "status": reason}})

    def _redirect(self, path, same=False):
        f = self.server.fake
        self.send_response(302)
        self.send_header("Location", (f.base if same else f.alt_base) + path)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _whole(self):
        """The original's host: the whole file whatever the Range, optionally slowly."""
        f = self.server.fake
        data = f.dl_body
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        if f.dl_no_length:                       # no length: the body ends when the connection does
            self.send_header("Connection", "close")
            self.close_connection = True
        else:
            self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            for i in range(0, len(data), 256):
                self.wfile.write(data[i:i + 256])
                if f.dl_delay:
                    time.sleep(f.dl_delay)
        except (BrokenPipeError, ConnectionResetError):
            return
        with f.lock:
            f.dl_finished.append(time.perf_counter())

    def _video(self):
        data = VIDEO
        rng = self.headers.get("Range")
        if not rng:
            return self._send(200, data, "video/mp4")
        a, b = rng.replace("bytes=", "").split("-")
        start, end = int(a), int(b) if b else len(data) - 1
        chunk = data[start:end + 1]
        self.send_response(206)
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, len(data)))
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)

    def do_POST(self):
        f = self.server.fake
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/token":
            form = dict(urllib.parse.parse_qsl(raw.decode("utf-8")))
            with f.lock:
                f.forms.append(form)
            if form.get("grant_type") == "authorization_code":
                with f.lock:
                    known = f.codes.pop(form.get("code"), None)
                if known is None or form.get("client_id") != "client-test" or form.get("client_secret") != "secret-test":
                    return self._send(400, {"error": "invalid_grant", "error_description": "Bad Request"})
                challenge = base64.urlsafe_b64encode(hashlib.sha256(
                    form.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
                if challenge != known["challenge"] or form.get("redirect_uri") != known["redirect_uri"]:
                    return self._send(400, {"error": "invalid_grant", "error_description": "PKCE mismatch"})
                with f.lock:
                    omit = f.omit_refresh_tokens > 0
                    if omit:
                        f.omit_refresh_tokens -= 1
                return self._send(200, f.issue(refresh=not omit))
            if form.get("grant_type") == "refresh_token":
                if f.refresh == "ok" and (form.get("refresh_token") or "").startswith("rt"):
                    return self._send(200, f.issue(refresh=False))
                if f.refresh == "http500":
                    return self._send(500, {"error": "server_error"})
                return self._send(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
            return self._send(400, {"error": "unsupported_grant_type"})
        if parsed.path == "/v1/sessions":
            if not self._bearer_ok():
                return self._error(401, "UNAUTHENTICATED", "Request had invalid authentication credentials.")
            with f.lock:
                f.session_posts += 1
                if f.exhausted:
                    pass
                else:
                    f.session_n += 1
                    sid = "s%d" % f.session_n
                    f.sessions[sid] = {"items": [], "set": False, "expire_at": time.time() + f.session_ttl}
                    session = f._session_json(sid)
            if f.exhausted:
                return self._error(429, "RESOURCE_EXHAUSTED", "Quota exceeded for quota metric 'Sessions'.")
            return self._send(200, session)
        self._send(404, {})

    def do_DELETE(self):
        f = self.server.fake
        m = self.path.startswith("/v1/sessions/")
        if not m or not self._bearer_ok():
            return self._error(401 if m else 404, "UNAUTHENTICATED", "no")
        sid = urllib.parse.unquote(self.path[len("/v1/sessions/"):])
        with f.lock:
            f.deleted.append(sid)
            gone = f.sessions.pop(sid, None)
        if gone is None:
            return self._error(404, "NOT_FOUND", "Session not found.")
        return self._send(200, {})

    def do_GET(self):
        f = self.server.fake
        parsed = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        with f.lock:
            f.calls.append((parsed.path, q, (self.headers.get("Authorization") or "")[7:]))
        if parsed.path.startswith("/media/"):
            with f.lock:
                f.media_requests.append({"path": self.path, "headers": dict(self.headers)})
            if not self._bearer_ok():
                return self._send(403, PNG_TILE, "image/png")
            # a baseUrl carries no query: the suffix is appended straight to it, as on Google;
            # the fake keeps its per-listing signature as a path segment, /media/<id>/<sig>=<suffix>
            media_id, _, rest = parsed.path[len("/media/"):].partition("/")
            sig_text, _, suffix = rest.partition("=")
            sig = int(sig_text or 0)
            with f.lock:
                live = sig >= f.min_sig
            if not live:
                return self._send(403, PNG_TILE, "image/png")
            if suffix == "dv":        # Google: 302 to a host that ignores Range and needs no bearer (2026-09-13)
                return self._redirect("/dl/%s" % media_id)
            if suffix == "m37":       # Google: 302 to googlevideo, which honours Range
                return self._redirect("/stream/%s" % media_id)
            if suffix == "same":      # a same-host hop: the bearer may stay on it
                return self._redirect("/stream/%s" % media_id, same=True)
            return self._send(200, JPEG, "image/jpeg")       # =d and =w400-h400 alike
        if parsed.path.startswith(("/dl/", "/stream/")):     # the redirect targets: no bearer needed
            with f.lock:
                f.media_requests.append({"path": self.path, "headers": dict(self.headers)})
            return self._video() if parsed.path.startswith("/stream/") else self._whole()
        if parsed.path.startswith("/public/"):                # a share link's stream: no bearer, as on Google's CDN
            with f.lock:
                f.media_requests.append({"path": self.path, "headers": dict(self.headers)})
            return self._video()
        if not self._bearer_ok():
            return self._error(401, "UNAUTHENTICATED", "Request had invalid authentication credentials.")
        if parsed.path.startswith("/v1/sessions/"):
            sid = urllib.parse.unquote(parsed.path[len("/v1/sessions/"):])
            with f.lock:
                if sid not in f.sessions:
                    known = False
                else:
                    known = True
                    f.polls.append(sid)
                    session = f._session_json(sid)
            if not known:
                return self._error(404, "NOT_FOUND", "Session not found.")
            return self._send(200, session)
        if parsed.path == "/v1/mediaItems":
            sid = q.get("sessionId")
            with f.lock:
                if sid not in f.sessions:
                    known = False
                else:
                    known = True
                    f.list_calls.append(sid)
                    f.sig += 1
                    sig = f.sig
                    items = list(f.sessions[sid]["items"])
            if not known:
                return self._error(404, "NOT_FOUND", "Session not found.")
            size = int(q.get("pageSize") or 100)
            start = int(q.get("pageToken") or 0)
            page = []
            for raw in items[start:start + size]:
                raw = json.loads(json.dumps(raw))
                raw["mediaFile"]["baseUrl"] = "%s/media/%s/%d" % (f.base, raw["id"], sig)
                page.append(raw)
            answer = {"mediaItems": page}
            if start + size < len(items):
                answer["nextPageToken"] = str(start + size)
            return self._send(200, answer)
        self._send(404, {})


class FakeGoogle:
    """oauth2.googleapis.com and photospicker.googleapis.com on one stub, plus the media host the baseUrls point at."""

    def __init__(self):
        self.valid = set()
        self.issued = 0
        self.codes = {}                         # auth code -> {challenge, redirect_uri}; minted by the test's "browser"
        self.forms = []                         # token endpoint POSTs
        self.refresh = "ok"                     # or "invalid_grant" / "http500"
        self.omit_refresh_tokens = 0            # how many code exchanges answer without a refresh_token
        self.reject_bearers = False
        self.exhausted = False
        self.session_ttl = 3600.0
        self.session_n = 0
        self.session_posts = 0
        self.sessions = {}                      # sid -> {items, set, expire_at}
        self.deleted = []
        self.polls = []
        self.list_calls = []
        self.calls = []
        self.media_requests = []
        self.sig = 0                            # bumped per mediaItems listing: every listing hands out fresh baseUrls
        self.min_sig = 0                        # baseUrls with an older signature answer 403 (expired)
        self.alt_base = ""                      # the same stub under another host name: a redirect across hosts
        self.dl_body = VIDEO                    # what the original's host serves, whole
        self.dl_delay = 0.0                     # seconds per 256-byte chunk of it
        self.dl_no_length = False               # answer without Content-Length
        self.dl_finished = []                   # perf_counter times its answers finished (the FakeTV's clock)
        self.lock = threading.Lock()
        self.base = ""

    def issue(self, refresh=True) -> dict:
        with self.lock:
            self.issued += 1
            n = self.issued
            self.valid.add("at%d" % n)
        out = {"access_token": "at%d" % n, "expires_in": 3599, "scope": gphotos.SCOPES, "token_type": "Bearer"}
        if refresh:
            out["refresh_token"] = "rt%d" % n
        return out

    def _session_json(self, sid) -> dict:
        s = self.sessions[sid]                  # caller holds lock
        return {"id": sid, "pickerUri": "https://photos.google.com/picker/%s" % sid,
                "pollingConfig": {"pollInterval": "0.02s", "timeoutIn": "%.2fs" % self.pick_timeout},
                "expireTime": _rfc3339(s["expire_at"]), "mediaItemsSet": s["set"]}

    pick_timeout = 600.0

    def set_pick(self, sid, items):
        with self.lock:
            self.sessions[sid]["items"] = list(items)
            self.sessions[sid]["set"] = True

    def expire_session(self, sid):
        with self.lock:
            self.sessions.pop(sid, None)

    def consent(self, auth_url: str, browser_state: str | None = None, error: str | None = None) -> dict:
        """Play the browser: check the consent URL, mint a code and land the redirect. Returns the URL's query."""
        parts = urllib.parse.urlsplit(auth_url)
        q = dict(urllib.parse.parse_qsl(parts.query))
        code = "code-%d" % (len(self.codes) + 1)
        with self.lock:
            self.codes[code] = {"challenge": q["code_challenge"], "redirect_uri": q["redirect_uri"]}
        params = {"state": browser_state if browser_state is not None else q["state"]}
        if error:
            params["error"] = error
        else:
            params["code"] = code
        redirect = q["redirect_uri"] + "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(redirect, timeout=5) as r:
                q["_landing"] = (r.status, r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            q["_landing"] = (e.code, e.read().decode("utf-8", "replace"))
        return q


class _Stub(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = FakeGoogle()
    srv = _Stub(("127.0.0.1", 0), _Handler)
    srv.fake = f
    f.base = "http://127.0.0.1:%d" % srv.server_address[1]
    f.alt_base = "http://localhost:%d" % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    monkeypatch.setattr(loopback, "TOKEN", f.base + "/token")
    monkeypatch.setattr(gphotos, "PICKER", f.base + "/v1")
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.setattr(config, "_CACHE", str(tmp_path / "cache"))
    client = tmp_path / "client.json"
    client.write_text(json.dumps({"installed": {"client_id": "client-test", "client_secret": "secret-test",
                                                "redirect_uris": ["http://localhost"]}}), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_CLIENT_JSON", str(client))
    opened = []
    monkeypatch.setattr(loopback, "open_browser", lambda url: opened.append(url) or True)
    f.opened = opened
    try:
        yield f
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture(autouse=True)
def fresh_downloads(monkeypatch, tmp_path):
    from castlib import downloads
    from castlib.photos import _Cache
    monkeypatch.setattr(downloads, "cache", _Cache(downloads.CACHE_BYTES, downloads.CACHE_ENTRIES))
    monkeypatch.setattr(downloads, "_holders", {})
    monkeypatch.setattr(config, "VIDEO_BASE", str(tmp_path))
    yield
    config.remove_video_tmp_dir()


def _connect(src, fake):
    """Start the consent, play the browser, wait for ``connected``; returns the consent URL's query."""
    d = src.connect({})
    assert d["state"] == "connecting" and d["step"] == "consent"
    q = fake.consent(d["detail"]["auth_url"])
    wait_for(lambda: src.status()["state"] == "connected")
    return q


def _pick(src, fake, items):
    """Open a pick, have Google report it made with ``items``, wait for the grid."""
    d = src.pick({})
    sid = d["pick"]["session_id"]
    fake.set_pick(sid, items)
    wait_for(lambda: (src.status()["detail"]["pick"] or {}).get("state") == "done")
    return sid


def _token_file():
    return os.path.join(config.config_dir(), "google.json")


# ---------------------------------------------------------------- the gate
def test_loopback_pkce_and_state(fake):
    src = GPhotosSource()
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    d = src.connect({})
    detail = d["detail"]
    assert d["step"] == "consent" and detail["step"] == "consent" and detail["note"] == gphotos.ON_HOST_NOTE
    assert 0 < detail["expires_in"] <= 300 and detail["attempt"] == 1
    url = detail["auth_url"]
    assert fake.opened == [url]                                # the server opened the browser itself
    parts = urllib.parse.urlsplit(url)
    assert parts.scheme + "://" + parts.netloc + parts.path == loopback.AUTH
    q = dict(urllib.parse.parse_qsl(parts.query))
    assert q["client_id"] == "client-test" and q["response_type"] == "code"
    assert q["scope"] == gphotos.SCOPES and q["access_type"] == "offline"
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
    assert q["redirect_uri"].startswith("http://127.0.0.1:") and q["redirect_uri"].endswith("/")
    assert len(q["state"]) >= 16 and "prompt" not in q
    again = src.connect({})                                    # while the consent is pending: the same URL
    assert again["detail"]["auth_url"] == url and fake.opened == [url]
    # a redirect with the wrong state is refused and the flow keeps waiting
    wrong = fake.consent(url, browser_state="not-ours")
    assert wrong["_landing"][0] == 400 and "state mismatch" in wrong["_landing"][1]
    assert src.status()["state"] == "connecting"
    good = fake.consent(url)
    assert good["_landing"][0] == 200 and "connected" in good["_landing"][1]
    wait_for(lambda: src.status()["state"] == "connected")
    # the exchange carried the verifier that matches the challenge, the secret and the redirect
    (form,) = [f for f in fake.forms if f.get("grant_type") == "authorization_code"]
    assert form["client_secret"] == "secret-test" and form["redirect_uri"] == q["redirect_uri"]
    assert base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode() \
        == q["code_challenge"]
    s = src.status()
    assert s["state"] == "connected"
    assert s["detail"]["stored"] and s["detail"]["picks"] == 0 and s["detail"]["pick"] is None
    with open(_token_file(), encoding="utf-8") as fh:
        stored = json.load(fh)
    assert stored["access_token"] == "at1" and stored["refresh_token"] == "rt1" and stored["scope"] == gphotos.SCOPES
    assert os.name != "posix" or oct(os.stat(_token_file()).st_mode & 0o777) == "0o600"


def test_connect_timeout(fake, monkeypatch):
    monkeypatch.setattr(loopback, "CONSENT_TIMEOUT", 0.2)
    src = GPhotosSource()
    d = src.connect({})
    port = int(urllib.parse.urlsplit(dict(urllib.parse.parse_qsl(
        urllib.parse.urlsplit(d["detail"]["auth_url"]).query))["redirect_uri"]).port)
    wait_for(lambda: src.status()["state"] == "disconnected", timeout=3)
    s = src.status()
    assert s["detail"]["flow_error"]["code"] == "consent_timeout"
    assert "at this computer" in s["detail"]["flow_error"]["message"]
    assert not fake.forms                                        # no exchange without a code
    # the loopback listener is gone with the flow
    wait_for(lambda: _port_closed(port), timeout=3)
    # a declined consent is its own message, and connect starts a fresh round afterwards
    monkeypatch.setattr(loopback, "CONSENT_TIMEOUT", 30)
    d = src.connect({})
    fake.consent(d["detail"]["auth_url"], error="access_denied")
    wait_for(lambda: src.status()["state"] == "disconnected")
    assert src.status()["detail"]["flow_error"]["code"] == "consent_declined"
    d = src.connect({})
    assert d["step"] == "consent" and "flow_error" not in d["detail"]
    src.connect({"cancel": True})
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}


def _port_closed(port):
    import socket
    s = socket.socket()
    s.settimeout(0.2)
    try:
        s.connect(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def test_refresh_token_missing_retries_with_prompt_consent(fake):
    fake.omit_refresh_tokens = 1                                 # a repeat consent: Google skips the refresh token
    src = GPhotosSource()
    d = src.connect({})
    first = d["detail"]["auth_url"]
    fake.consent(first)
    wait_for(lambda: src.status()["detail"].get("attempt") == 2)
    s = src.status()
    assert s["state"] == "connecting"
    second = s["detail"]["auth_url"]
    assert second != first and fake.opened == [first, second]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(second).query))
    assert q["prompt"] == "consent" and q["access_type"] == "offline"
    fake.consent(second)
    wait_for(lambda: src.status()["state"] == "connected")
    with open(_token_file(), encoding="utf-8") as fh:
        stored = json.load(fh)
    assert stored["refresh_token"] == "rt2" and stored["access_token"] == "at2"
    assert len([f for f in fake.forms if f.get("grant_type") == "authorization_code"]) == 2
    # twice without a refresh token: the connection would not survive an hour, so it is refused
    fake.omit_refresh_tokens = 2
    src2 = GPhotosSource()
    d = src2.connect({"fresh": True})
    fake.consent(d["detail"]["auth_url"])
    wait_for(lambda: src2.status()["detail"].get("attempt") == 2)
    fake.consent(src2.status()["detail"]["auth_url"])
    wait_for(lambda: src2.status()["state"] != "connecting")
    assert src2.status()["detail"]["flow_error"]["code"] == "no_refresh_token"


def test_stored_consent_is_verified_by_a_refresh(fake):
    src = GPhotosSource()
    _connect(src, fake)
    src2 = GPhotosSource()                                       # a restart
    s = src2.status()
    assert s["state"] == "disconnected" and s["detail"]["stored"]
    d = src2.connect({})
    assert d["state"] == "connected" and not fake.opened[1:]     # no browser, no consent round
    refreshes = [f for f in fake.forms if f.get("grant_type") == "refresh_token"]
    assert refreshes == [{"grant_type": "refresh_token", "client_id": "client-test",
                          "client_secret": "secret-test", "refresh_token": "rt1"}]
    # the consent was revoked meanwhile: expired, the gate returns, connect starts a consent round
    fake.refresh = "invalid_grant"
    src3 = GPhotosSource()
    with pytest.raises(AuthError) as err:
        src3.connect({})
    assert err.value.code == "refresh_rejected"
    s = src3.status()
    assert s["state"] == "expired" and s["detail"]["error"]["code"] == "refresh_rejected"
    d = src3.connect({})
    assert d["step"] == "consent"
    src3.connect({"cancel": True})
    assert src3.status()["state"] == "expired"


def test_no_client_file_is_a_config_error(fake, monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_CLIENT_JSON", str(tmp_path / "nope.json"))
    src = GPhotosSource()
    with pytest.raises(ConfigError) as err:
        src.connect({})
    assert err.value.code == "no_google_client" and "Desktop app" in err.value.hint
    assert src.status()["state"] == "disconnected"
    bad = tmp_path / "bad.json"
    bad.write_text('{"web": {"client_id": "x"}}', encoding="utf-8")
    monkeypatch.setenv("GOOGLE_CLIENT_JSON", str(bad))
    with pytest.raises(ConfigError) as err:
        GPhotosSource().connect({})
    assert err.value.code == "bad_google_client"
    assert loopback.load_client(str(_write_client(tmp_path, {"client_id": "a", "client_secret": "b"}))) \
        == {"client_id": "a", "client_secret": "b"}                # a flat file works too


def _write_client(tmp_path, data):
    p = tmp_path / "flat.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------- the pick
def test_pick_polls_until_set(fake):
    src = GPhotosSource()
    _connect(src, fake)
    assert src.list().as_dict() == {"items": [], "folders": [], "next": None, "crumbs": []}
    d = src.pick({})
    pick = d["pick"]
    assert pick["state"] == "waiting" and pick["session_id"] == "s1"
    assert pick["picker_uri"] == "https://photos.google.com/picker/s1" and 0 < pick["expires_in"] <= 600
    assert src.status()["detail"]["pick"]["state"] == "waiting"
    assert src.pick({})["pick"]["session_id"] == "s1"           # pending: the same session, not a second one
    assert fake.session_posts == 1
    wait_for(lambda: len(fake.polls) >= 3)                       # polling at pollInterval, nothing listed yet
    assert not fake.list_calls and src.list().items == []
    items = [_item("a"), _item("b", "VIDEO", "video/mp4"), _item("c", "PHOTO", "image/gif", "anim.gif"),
             _item("d", "PHOTO", "image/heic", "IMG_1.HEIC")]
    fake.set_pick("s1", items)
    wait_for(lambda: (src.status()["detail"]["pick"] or {}).get("state") == "done")
    s = src.status()
    assert s["detail"]["pick"]["count"] == 3 and s["detail"]["picks"] == 3 and s["detail"]["sessions"] == 1
    listing = src.list()
    assert [e.id for e in listing.items] == ["a", "b", "d"]      # the GIF is hidden, order is pick order
    a, b, d_ = listing.items
    assert (a.kind, a.name, a.mime, a.date, a.width, a.height) == ("photo", "a.jpg", "image/jpeg", "2026-08-16", 4032, 3024)
    assert a.thumb == "/api/sources/gphotos/thumb/a" and a.warn is None and a.size is None
    assert (b.kind, b.name, b.mime) == ("video", "b.mp4", "video/mp4")
    assert (d_.kind, d_.mime, d_.name) == ("photo", "image/heic", "IMG_1.HEIC")
    assert listing.as_dict()["items"][0]["source"] == "gphotos"
    # a second pick appends; the picks_seq moved twice (two merges)
    seq = s["detail"]["picks_seq"]
    _pick(src, fake, [_item("e")])
    assert [e.id for e in src.list().items] == ["a", "b", "d", "e"]
    assert src.status()["detail"]["picks_seq"] > seq
    # paging: a session with more than a page of items is listed page by page
    fake.session_ttl = 3600
    many = [_item("m%03d" % i) for i in range(250)]
    _pick(src, fake, many)
    ids = [e.id for e in src.list().items]
    assert ids[4:] == ["m%03d" % i for i in range(250)] and len(ids) == 254
    assert fake.calls[-1][1]["pageToken"] == "200"


def test_pick_timeout(fake):
    fake.pick_timeout = 0.1
    src = GPhotosSource()
    _connect(src, fake)
    d = src.pick({})
    sid = d["pick"]["session_id"]
    wait_for(lambda: (src.status()["detail"]["pick"] or {}).get("state") == "timeout")
    assert src.list().items == []                                # grid unchanged
    wait_for(lambda: sid in fake.deleted)                        # the session is deleted, not left to rot
    assert src.status()["detail"]["sessions"] == 0
    # a cancelled pick: polling stops, the session is deleted, the grid unchanged
    fake.pick_timeout = 600
    d = src.pick({})
    sid2 = d["pick"]["session_id"]
    d = src.pick({"cancel": True})
    assert d["pick"]["state"] == "cancelled"
    wait_for(lambda: sid2 in fake.deleted)
    polls = len(fake.polls)
    time.sleep(0.1)
    assert len(fake.polls) == polls and src.list().items == []
    # too many sessions: an error on the gate, nothing opened
    fake.exhausted = True
    with pytest.raises(UpstreamError) as err:
        src.pick({})
    assert err.value.code == "picker_exhausted" and "disconnect" in err.value.hint


def test_pick_not_persisted(fake):
    src = GPhotosSource()
    _connect(src, fake)
    _pick(src, fake, [_item("a"), _item("b")])
    assert len(src.list().items) == 2
    src2 = GPhotosSource()                                       # a restart: connected, nothing picked
    src2.connect({})
    assert src2.status()["state"] == "connected"
    assert src2.list().items == [] and src2.status()["detail"]["picks"] == 0
    with pytest.raises(NotMedia) as err:
        src2.resolve("a")
    assert err.value.code == "unknown_item"
    assert src2.thumb("a") is None


# ------------------------------------------------------------- the bytes
def test_bearer_on_fetch_and_relay(fake, server, monkeypatch, tmp_path):
    photos.cache.clear()
    src = GPhotosSource()
    _connect(src, fake)
    _pick(src, fake, [_item("p1"), _item("v1", "VIDEO", "video/mp4")])
    assert not fake.list_calls[1:]
    photo = src.resolve("p1")
    assert photo.kind == "photo" and photo.mime == "image/jpeg" and photo.source == "gphotos"
    assert photo.source_id == "p1" and photo.version == "p1" and (photo.width, photo.height) == (4032, 3024)
    up = photo.resolve()
    assert up.url == fake.base + "/media/p1/1=d" and up.headers == {"Authorization": "Bearer at1"}
    assert not fake.list_calls[1:]                               # a young baseUrl is reused, not re-listed
    prep = photos.prepare(photo)
    assert prep.mime == "image/jpeg" and (prep.width, prep.height) == (64, 48)
    assert fake.media_requests[-1]["path"] == "/media/p1/1=d"
    assert fake.media_requests[-1]["headers"]["Authorization"] == "Bearer at1"
    # the original is fetched whole before casting; the 1080p stream relays, the bearer on the
    # first hop only, the TV's range passed through to the stream's host
    video = src.resolve("v1")
    assert video.kind == "video" and video.mime == "video/mp4" and video.download
    assert video.resolve().url == fake.base + "/media/v1/1=dv"
    stream = src.resolve("v1", "stream")
    assert not stream.download and (stream.width, stream.height) == (None, None)
    assert stream.resolve().url == fake.base + "/media/v1/1=m37"
    srv, base = server
    srv.registry.add(stream)
    status, headers, got, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, stream.id), {"Range": "bytes=10-19"})
    assert status == 206 and got == VIDEO[10:20] and headers["Content-Type"] == "video/mp4"
    hop, target = fake.media_requests[-2:]
    assert hop["path"] == "/media/v1/1=m37" and hop["headers"]["Authorization"] == "Bearer at1"
    assert target["path"] == "/stream/v1" and "Authorization" not in target["headers"]   # another host
    assert target["headers"]["Range"] == "bytes=10-19"
    # the thumbnail: the same address family, a size suffix, the bearer
    thumb = src.thumb("p1")
    assert thumb.url == fake.base + "/media/p1/1=w400-h400" and thumb.headers == {"Authorization": "Bearer at1"}
    assert src.thumb("nope") is None and src.thumb("../x") is None
    # the access token is refreshed when stale, and the new one rides on the next open
    src._store._data["expires_at"] = time.time() + 30
    assert video.resolve().headers == {"Authorization": "Bearer at2"}


def test_baseurl_refreshed_after_50min(fake, server):
    src = GPhotosSource()
    _connect(src, fake)
    _pick(src, fake, [_item("p1"), _item("v1", "VIDEO", "video/mp4")])
    video = src.resolve("v1")
    assert video.resolve().url.endswith("/1=dv")
    with src._lock:
        src._picks["v1"]["fetched_at"] = time.time() - 51 * 60  # older than 50 min: re-listed on open
    assert video.resolve().url == fake.base + "/media/v1/2=dv"
    assert fake.list_calls == ["s1", "s1"]
    assert video.resolve().url.endswith("/2=dv")                # fresh again: reused
    # the CDN refuses an address early: the relay asks the source for a new one, once
    stream = src.resolve("v1", "stream")
    fake.min_sig = 3
    srv, base = server
    srv.registry.add(stream)
    status, _, got, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, stream.id), {"Range": "bytes=0-9"})
    assert status == 206 and got == VIDEO[:10]
    paths = [r["path"] for r in fake.media_requests if r["path"].startswith("/media/v1/")][-2:]
    assert paths == ["/media/v1/2=m37", "/media/v1/3=m37"]
    # the same for a photo fetched whole
    photos.cache.clear()
    photo = src.resolve("p1")
    fake.min_sig = 4
    photos.prepare(photo)
    paths = [r["path"] for r in fake.media_requests[-2:]]
    assert paths == ["/media/p1/3=d", "/media/p1/4=d"]
    # and once only: a second refusal is the error
    fake.min_sig = 99
    photos.cache.clear()
    with pytest.raises(UpstreamError) as err:
        photos.prepare(src.resolve("p1"))
    assert err.value.code == "photo_fetch_failed"


def test_session_expired_marks_items(fake):
    src = GPhotosSource()
    _connect(src, fake)
    _pick(src, fake, [_item("a"), _item("b")])
    with src._lock:
        src._sessions["s1"]["expire_at"] = time.time() - 1      # expireTime passed
    listing = src.list()
    assert [(e.id, e.warn) for e in listing.items] == [("a", "re-pick"), ("b", "re-pick")]
    with src._lock:
        assert "s1" not in src._sessions                          # dropped, not merely skipped
        assert src._picks["a"]["sessions"] == set() == src._picks["b"]["sessions"]
    assert src.status()["detail"]["sessions"] == 0
    item = src.resolve("a")
    with src._lock:
        src._picks["a"]["fetched_at"] = 0                        # stale, and no live session to re-list through
    with pytest.raises(UpstreamError) as err:
        item.resolve()
    assert err.value.code == "repick_needed" and "Pick it again" in err.value.message
    assert src.thumb("a") is None
    # a session Google forgot (404 on re-list) is dropped the same way
    src2 = GPhotosSource()
    _pick(src2, fake, [_item("c")])
    fake.expire_session("s2")
    with src2._lock:
        src2._picks["c"]["fetched_at"] = 0
    with pytest.raises(UpstreamError) as err:
        src2.resolve("c").resolve()
    assert err.value.code == "repick_needed"
    assert src2.list().items[0].warn == "re-pick" and src2.status()["detail"]["sessions"] == 0


def test_repick_merges_by_media_id(fake):
    src = GPhotosSource()
    _connect(src, fake)
    s1 = _pick(src, fake, [_item("a"), _item("b")])
    s2 = _pick(src, fake, [_item("b"), _item("c")])
    assert (s1, s2) == ("s1", "s2")
    ids = [e.id for e in src.list().items]
    assert ids == ["a", "b", "c"]                                # b keeps its place, is not duplicated
    with src._lock:
        assert src._picks["b"]["sessions"] == {"s1", "s2"}
        src._sessions["s1"]["expire_at"] = time.time() - 1      # S1 expires
    assert [(e.id, e.warn) for e in src.list().items] == [("a", "re-pick"), ("b", None), ("c", None)]
    with src._lock:
        assert "s1" not in src._sessions and set(src._sessions) == {"s2"}
        assert src._picks["b"]["sessions"] == {"s2"}              # its link to the live session stays
        assert "a" in src._picks and src._picks["a"]["sessions"] == set()   # the medium stays, for "re-pick"
    item = src.resolve("b")
    with src._lock:
        src._picks["b"]["fetched_at"] = 0
    up = item.resolve()                                          # re-listed through S2, the one still holding it
    assert up.url == fake.base + "/media/b/3=dv" if item.kind == "video" else up.url.endswith("/media/b/3=d")
    assert fake.list_calls[-1] == "s2"
    assert [e.id for e in src.list().items] == ["a", "b", "c"]


def test_sessions_deleted_on_disconnect(fake):
    src = GPhotosSource()
    _connect(src, fake)
    _pick(src, fake, [_item("a")])
    _pick(src, fake, [_item("b")])
    src.pick({})                                                 # a third, still waiting
    assert sorted(fake.sessions) == ["s1", "s2", "s3"]
    src.disconnect()
    assert sorted(fake.deleted) == ["s1", "s2", "s3"] and fake.sessions == {}
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    assert src.list().items == [] and not os.path.exists(_token_file())
    # close() (process exit) deletes what is open and keeps the consent
    src2 = GPhotosSource()
    _connect(src2, fake)
    _pick(src2, fake, [_item("c")])
    src2.close()
    assert "s4" in fake.deleted and src2.status()["state"] == "connected"
    assert src2.list().items[0].warn == "re-pick"


def test_a_late_pick_after_disconnect_is_dropped(fake):
    src = GPhotosSource()
    _connect(src, fake)
    d = src.pick({})
    sid = d["pick"]["session_id"]
    src.disconnect()
    fake.sessions[sid] = {"items": [_item("a")], "set": True, "expire_at": time.time() + 600}   # Google still has it
    time.sleep(0.1)
    assert src.list().items == [] and src.status()["detail"] == {"stored": False}


def _in_thread(fn, *args):
    """Run ``fn(*args)`` on a thread; the returned list receives its result or its CastError."""
    out = []

    def run():
        try:
            out.append(fn(*args))
        except (AuthError, ConfigError, UpstreamError) as e:
            out.append(e)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, out


def test_disconnect_while_the_consent_listener_opens(fake, monkeypatch):
    src = GPhotosSource()
    opening, go, flows = threading.Event(), threading.Event(), []
    real_start = loopback.start

    def slow_start(*a, **kw):
        flow = real_start(*a, **kw)
        flows.append(flow)
        opening.set()
        go.wait(5)
        return flow
    monkeypatch.setattr(loopback, "start", slow_start)
    t, out = _in_thread(src.connect, {})
    assert opening.wait(5)
    src.disconnect()                                              # lands before the round is published
    go.set()
    t.join(5)
    assert isinstance(out[0], AuthError) and out[0].code == "cancelled"
    assert flows[0]._done.is_set()                                # the listener it opened is cancelled
    assert src._flow is None and src.status()["state"] == "disconnected"   # not stuck "connecting"


def test_disconnect_while_a_picker_session_opens(fake, monkeypatch):
    src = GPhotosSource()
    _connect(src, fake)
    posted, go = threading.Event(), threading.Event()
    real_call = gphotos.picker_call

    def slow_call(method, path, token, body=None, timeout=30):
        answer = real_call(method, path, token, body, timeout)
        if method == "POST":
            posted.set()
            go.wait(5)
        return answer
    monkeypatch.setattr(gphotos, "picker_call", slow_call)
    t, out = _in_thread(src.pick, {})
    assert posted.wait(5)
    src.disconnect()                                              # lands after Google opened the session
    go.set()
    t.join(5)
    assert isinstance(out[0], AuthError) and out[0].code == "cancelled"
    assert fake.deleted == ["s1"] and fake.sessions == {}         # the session it opened is not left behind
    assert src._sessions == {} and src.status() == {"state": "disconnected", "detail": {"stored": False}}


def test_close_is_bounded_and_final_when_google_does_not_answer(fake, monkeypatch):
    src = GPhotosSource()
    _connect(src, fake)
    _pick(src, fake, [_item("a")])
    src.pick({})                                                  # a second session, still waiting
    hang, calls = threading.Event(), []

    def silent(method, path, token, body=None, timeout=30):
        calls.append((method, timeout))
        hang.wait(timeout)                                        # Google never answers
        raise UpstreamError("picker_unreachable", "timed out", source="gphotos")
    monkeypatch.setattr(gphotos, "picker_call", silent)
    monkeypatch.setattr(gphotos, "CLEANUP_BUDGET", 0.5)
    started = time.monotonic()
    src.close()
    elapsed = time.monotonic() - started
    hang.set()
    assert elapsed < 1.5                                          # one deadline for them all, not 30 s each
    deletes = [c for c in calls if c[0] == "DELETE"]
    assert deletes and all(timeout <= 0.5 for _, timeout in deletes)
    assert src._sessions == {} and src.list().items[0].warn == "re-pick"   # the local state went at once
    for step in (src.pick, src.connect):
        with pytest.raises(ConfigError) as err:
            step({})
        assert err.value.code == "source_closed"                  # nothing new starts after close()
    src.close()                                                   # and a second close is a no-op


def test_a_hanging_cleanup_does_not_keep_the_process_alive(tmp_path):
    import subprocess
    import sys
    import textwrap
    script = textwrap.dedent("""
        import threading, time
        from castlib.sources import gphotos
        gphotos.CLEANUP_BUDGET = 0.3
        src = gphotos.GPhotosSource()
        src._sessions["s1"] = {"expire_at": time.time() + 600, "ids": set(), "picker_uri": "https://x"}
        src._token = lambda force=False: ("at", 0)
        gphotos.picker_call = lambda *a, **kw: threading.Event().wait()   # a DELETE that never returns
        print("ready", flush=True)
    """)                                                          # then the interpreter exits: atexit closes the source
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, HOME=str(tmp_path), PYTHONPATH=root)
    started = time.monotonic()
    done = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=20)
    assert done.returncode == 0 and "ready" in done.stdout, done.stderr
    assert time.monotonic() - started < 10


def test_picker_401_refreshes_once_then_expires(fake):
    src = GPhotosSource()
    _connect(src, fake)
    with fake.lock:
        fake.valid.discard("at1")                                # the access token died server-side
    d = src.pick({})
    assert d["pick"]["session_id"] == "s1"                       # 401 on at1, refreshed, retried: the session opened
    refreshes = [f for f in fake.forms if f.get("grant_type") == "refresh_token"]
    assert len(refreshes) == 1 and refreshes[0]["refresh_token"] == "rt1"
    wait_for(lambda: len(fake.polls) >= 1)
    assert {c[2] for c in fake.calls if c[0] == "/v1/sessions/s1"} == {"at2"}
    assert src.status()["state"] == "connected"
    src.pick({"cancel": True})
    # a second 401 after a refresh is the end of the sign-in
    fake.reject_bearers = True
    with pytest.raises(AuthError) as err:
        src.pick({})
    assert err.value.code == "picker_unauthorized"
    assert src.status()["state"] == "expired"
    assert len([f for f in fake.forms if f.get("grant_type") == "refresh_token"]) == 2
    # a 5xx from the refresh keeps the credential and the state
    fake.reject_bearers = False
    src2 = GPhotosSource()
    assert src2.connect({})["state"] == "connected"             # the stored consent, verified by a refresh
    with fake.lock:
        fake.valid.discard(src2._store.load()["access_token"])
    fake.refresh = "http500"
    with pytest.raises(UpstreamError) as err:
        src2.pick({})
    assert err.value.code == "refresh_failed" and src2.status()["state"] == "connected"


# ------------------------------------------------------------------- the CLI
def test_cast_photos_pick_over_the_cli(fake, monkeypatch, capsys):
    from castlib import cli
    casts = []
    monkeypatch.setattr(cli, "find_tv", lambda tv: ("127.0.0.1", "http://127.0.0.1:1/avt", "Fake"))
    monkeypatch.setattr(cli, "_cast_item", lambda item, tv, port, debug, subtitle=None: casts.append((item, tv, port)) or 0)
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")

    def browser(url):                                            # the "user" consents as soon as the page opens
        threading.Thread(target=fake.consent, args=(url,), daemon=True).start()
        return True
    monkeypatch.setattr(loopback, "open_browser", browser)
    def driven():
        """A source whose picks Google makes at once; pick_photos closes it on the way out, for good."""
        src = GPhotosSource()
        real_pick = src.pick

        def pick(params):
            d = real_pick(params)
            if not params.get("cancel"):
                fake.set_pick(d["pick"]["session_id"], [_item("a"), _item("b", "VIDEO", "video/mp4")])
            return d
        monkeypatch.setattr(src, "pick", pick)
        return src
    assert cli.pick_photos(tv="127.0.0.1", port=18895, source=driven()) == 0
    out = capsys.readouterr().out
    assert "Consent:" in out and "Google Photos: connected." in out
    assert "https://photos.google.com/picker/s1" in out
    assert "  1. a.jpg" in out and "  2. b.mp4" in out
    (item, tv, port) = casts[0]
    assert item.kind == "video" and item.source_id == "b" and port == 18895
    assert "s1" in fake.deleted                                  # closed on the way out
    # --url-only prints the bearer-less address (the bearer is a header, never in the URL)
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")
    assert cli.pick_photos(url_only=True, source=driven()) == 0
    assert capsys.readouterr().out.strip().endswith("=d")
    monkeypatch.setattr(cli, "pick_photos", lambda **kw: kw)  # wired through the parser
    assert cli.main_photos(["--pick", "--url-only", "-p", "1234"]) == {"tv": None, "port": 1234, "url_only": True}
    with pytest.raises(SystemExit):
        cli.main_photos([])                                      # a link or --pick is required


# --------------------------------------------------------------- share links
def test_share_link_paste_lists_a_video(fake, monkeypatch, server):
    src = GPhotosSource()
    _connect(src, fake)
    resolved = []
    monkeypatch.setattr(sharelink, "resolve", lambda link, cookies_path=None: resolved.append(link) or fake.base + "/public/x=dv")
    fake.sig = 0
    with pytest.raises(ConfigError):
        src.link({"link": "photos.app.goo.gl/abc"})
    d = src.link({"link": "https://photos.app.goo.gl/AbCdEf"})
    assert d["item"]["id"] == "link-1" and d["item"]["kind"] == "video" and d["item"]["name"] == "AbCdEf"
    assert d["item"]["source"] == "gphotos" and d["item"]["thumb"] is None
    assert src.link({"link": "https://photos.app.goo.gl/AbCdEf"})["item"]["id"] == "link-1"   # pasted twice: one entry
    assert resolved == ["https://photos.app.goo.gl/AbCdEf"]
    _pick(src, fake, [_item("a")])
    assert [e.id for e in src.list().items] == ["a", "link-1"]  # picks first, then links
    item = src.resolve("link-1")
    assert item.kind == "video" and item.resolve().url.endswith("/public/x=dv") and item.resolve().headers == {}
    assert any(isinstance(h, sharelink._GooglePhotosOnly) for h in item.resolve().opener.handlers)   # relayed behind the guard
    assert resolved == ["https://photos.app.goo.gl/AbCdEf"]     # resolved once, reused on every open
    srv, base = server
    srv.registry.add(item)
    status, _, got, _ = request(base, "GET", "/m/%s/%s" % (srv.media_token, item.id), {"Range": "bytes=0-3"})
    assert status == 206 and got == VIDEO[:4]
    assert "Authorization" not in fake.media_requests[-1]["headers"]
    assert src.thumb("link-1") is None
    with pytest.raises(NotMedia):
        src.resolve("link-9")
    src.disconnect()
    assert src.list().items == []


class _Transport(urllib.request.BaseHandler):
    """Answers every http(s) request from ``routes`` and records it: nothing reaches the network."""

    handler_order = 100                          # ahead of urllib's own HTTP and HTTPS handlers

    def __init__(self, routes):
        self.routes, self.seen = routes, []

    def _answer(self, req):
        self.seen.append(req.full_url)
        status, headers, body = self.routes.get(req.full_url, (404, {}, b""))
        msg = http.client.HTTPMessage()
        for name, value in headers.items():
            msg[name] = value
        resp = urllib.response.addinfourl(io.BytesIO(body), msg, req.full_url, status)
        resp.msg = http.client.responses.get(status, "")
        return resp

    http_open = https_open = _answer


def _scripted_links(monkeypatch, routes) -> _Transport:
    """``sharelink.opener()`` as shipped, with ``routes`` standing in for the network behind it."""
    transport, real = _Transport(routes), sharelink.opener

    def opener(cookies_path=None):
        op = real(cookies_path)
        op.add_handler(transport)
        return op
    monkeypatch.setattr(sharelink, "opener", opener)
    return transport


LINK = "https://photos.app.goo.gl/AbCdEf"
SHARE_PAGE = "https://photos.google.com/share/AF1Qip?key=k1"
MEDIA_BASE = "https://lh3.googleusercontent.com/pw/" + "A" * 30
DL = "https://video-downloads.googleusercontent.com/v1"
PROBED = (206, {"Content-Type": "video/mp4", "Content-Range": "bytes 0-1/100"}, b"\0\0")


def _page(*addresses):
    return 200, {"Content-Type": "text/html"}, "".join('<a href="%s">' % a for a in addresses).encode()


def test_share_link_allowlist(fake, monkeypatch):
    for url in (LINK, SHARE_PAGE, "https://photos.google.com:443/share/x", "https://photos.google.com/share/a@b",
                "https://photos.google.com/share/x?u=a@b", MEDIA_BASE, DL,
                "https://photos.fife.usercontent.google.com/x", "https://rr1---sn-abc.googlevideo.com/v"):
        assert sharelink.allowed(url), url
    for url in ("http://photos.app.goo.gl/AbC", "photos.app.goo.gl/AbC", "https://photos.google.com.evil.test/x",
                "https://evilgoogleusercontent.com/x", "https://other.usercontent.google.com/x",
                "https://user@photos.google.com/x", "https://user:pw@photos.google.com/x",
                "https://photos.google.com:8443/x", "https://photos.google.com:bad/x",
                "https://127.0.0.1/x", "https://localhost/x", "https://192.168.1.1/x"):
        assert not sharelink.allowed(url), url
    transport = _scripted_links(monkeypatch, {})
    src = GPhotosSource()
    for url in ("http://127.0.0.1:9/secret", "https://192.168.1.1/admin"):
        with pytest.raises(ConfigError) as err:
            src.link({"link": url})
        assert err.value.code == "bad_link"
        with pytest.raises(ConfigError):
            sharelink.resolve(url)
    assert transport.seen == []                                 # refused before any request


def test_share_link_follows_redirects_on_google(monkeypatch):
    transport = _scripted_links(monkeypatch, {
        LINK: (302, {"Location": SHARE_PAGE}, b""), SHARE_PAGE: _page(MEDIA_BASE),
        MEDIA_BASE + "=dv": (302, {"Location": DL}, b""), DL: PROBED})
    assert sharelink.resolve(LINK) == MEDIA_BASE + "=dv"
    assert transport.seen == [LINK, SHARE_PAGE, MEDIA_BASE + "=dv", DL]


@pytest.mark.parametrize("target", [
    "http://127.0.0.1:9/secret", "https://127.0.0.1/secret", "https://10.0.0.1/admin",
    "https://169.254.169.254/latest/meta-data/", "http://photos.google.com/share/x",
    "https://photos.google.com.evil.test/share/x", "https://photos.google.com:8443/share/x",
    "https://other.usercontent.google.com/x"])
def test_share_link_redirect_off_google_is_never_requested(monkeypatch, target):
    transport = _scripted_links(monkeypatch, {LINK: (302, {"Location": target}, b""), target: _page(MEDIA_BASE)})
    with pytest.raises(UpstreamError) as err:
        sharelink.resolve(LINK)
    assert err.value.code == "redirect_refused"
    assert transport.seen == [LINK]                             # the target was never asked


def test_share_link_login_redirect_is_not_followed(monkeypatch):
    login = "https://accounts.google.com/ServiceLogin?continue=x"
    transport = _scripted_links(monkeypatch, {LINK: (302, {"Location": login}, b""), login: _page()})
    with pytest.raises(AuthError) as err:
        sharelink.resolve(LINK)
    assert err.value.code == "login_required" and "cookies" in err.value.message
    assert transport.seen == [LINK]


def test_share_link_probe_redirect_off_google_is_never_requested(monkeypatch):
    evil, secret = "https://video-downloads.googleusercontent.com/evil", "http://127.0.0.1:9/secret"
    transport = _scripted_links(monkeypatch, {
        LINK: _page(evil), evil: (302, {"Location": secret}, b""), secret: PROBED})
    with pytest.raises(NotMedia) as err:
        sharelink.resolve(LINK)
    assert err.value.code == "no_stream"
    assert transport.seen == [LINK, evil]


# ---------------------------------------------------------------- the API
def test_pick_and_link_over_api(fake, app, monkeypatch):
    src = app.sources["gphotos"]
    assert isinstance(src, GPhotosSource)
    status, _, body, conn = request(app.base_url, "POST", "/api/sources/gphotos/pick", {"Content-Type": "application/json"})
    assert status == 401 and json.loads(body)["error"]["code"] == "no_token"
    _connect(src, fake)
    status, _, body, conn = request(app.base_url, "POST", "/api/sources/gphotos/pick", conn=conn)
    assert status == 200
    pick = json.loads(body)["pick"]
    assert pick["state"] == "waiting" and pick["picker_uri"].startswith("https://")
    status, _, body, conn = request(app.base_url, "GET", "/api/status", conn=conn)
    g = json.loads(body)["sources"]["gphotos"]
    assert g["state"] == "connected" and g["detail"]["pick"]["session_id"] == pick["session_id"]
    fake.set_pick(pick["session_id"], [_item("a")])
    wait_for(lambda: src.status()["detail"]["pick"]["state"] == "done")
    status, _, body, conn = request(app.base_url, "GET", "/api/sources/gphotos/list", conn=conn)
    assert [e["id"] for e in json.loads(body)["items"]] == ["a"]
    status, headers, body, conn = request(app.base_url, "GET", "/api/sources/gphotos/thumb/a", conn=conn)
    assert status == 200 and headers["Content-Type"] == "image/jpeg" and body == JPEG
    monkeypatch.setattr(sharelink, "resolve", lambda link, cookies_path=None: fake.base + "/public/x=dv")
    status, _, body, conn = request(app.base_url, "GET", "/api/sources/gphotos/link", conn=conn)
    assert status == 405                                         # a step is a mutation
    import http.client
    c2 = http.client.HTTPConnection(app.base_url.split("://", 1)[1], timeout=5)
    payload = json.dumps({"link": "https://photos.app.goo.gl/Xyz"}).encode()
    c2.request("POST", "/api/sources/gphotos/link", body=payload, headers={"Content-Type": "application/json"})
    r = c2.getresponse()
    assert r.status == 200 and json.loads(r.read())["item"]["id"] == "link-1"
    # a cast through the app resolves through the source
    status, _, body, conn = request(app.base_url, "GET", "/api/sources/gphotos/list", conn=conn)
    assert [e["id"] for e in json.loads(body)["items"]] == ["a", "link-1"]
    item = app.resolve("gphotos", "a")
    assert isinstance(item, MediaItem) and item.kind == "photo"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows cannot deliver SIGINT/SIGTERM to a child's handler")
def test_sigterm_closes_sources_like_ctrl_c(tmp_path):
    """A plain ``kill`` runs the Ctrl+C path: the sources are closed (picker sessions deleted) and the TV stopped."""
    import signal
    import subprocess
    import sys
    code = (
        "import sys, socket; from castlib import app as m, config, dlna\n"
        "config._CONFIG = %r; config._CACHE = %r\n"
        "m.discover = lambda **kw: []\n"
        "dlna.soap = lambda *a, **kw: print('soap', a[2], flush=True) or ''\n"
        "s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()\n"
        "app = m.App.start(port, browser=False)\n"
        "app.use_tv('127.0.0.1', 'http://127.0.0.1:1/avt', 'Fake')\n"
        "app.sources['gphotos'].close = lambda: print('gphotos closed', flush=True)\n"
        "print('ready', flush=True)\n"
        "sys.exit(app.run_forever())\n" % (str(tmp_path / "config"), str(tmp_path / "cache")))
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    while True:
        line = proc.stdout.readline().decode()
        assert line, "the app never came up"
        if line.strip() == "ready":
            break
    proc.send_signal(signal.SIGTERM)
    out = proc.stdout.read().decode()
    assert proc.wait(timeout=10) == 0
    assert "gphotos closed" in out and "soap Stop" in out and "Stopped." in out


# ------------------------------------------------------------ the original video
def _video_source(fake):
    src = GPhotosSource()
    _connect(src, fake)
    _pick(src, fake, [_item("p1"), _item("v1", "VIDEO", "video/mp4")])
    return src


def test_video_offers_original_and_stream(fake):
    src = _video_source(fake)
    p1, v1 = src.list().items
    assert p1.variants is None
    assert [v["quality"] for v in v1.variants] == ["original", "stream"]
    assert v1.variants[0]["default"] and v1.variants[0]["note"] == "4032x3024, downloads first"
    assert src.resolve("v1").download and src.resolve("v1", "original").download
    with pytest.raises(ConfigError) as err:
        src.resolve("v1", "proxy")
    assert err.value.code == "bad_quality"


def test_original_video_is_fetched_whole_before_the_tv_hears_of_it(fake, app):
    from castlib import downloads
    src = app.sources["gphotos"]
    _connect(src, fake)
    _pick(src, fake, [_item("v1", "VIDEO", "video/mp4")])
    fake.dl_body = bytes(range(256)) * 64
    c = app.cast(src.resolve("v1"))
    wait_for(lambda: c.sent.is_set())
    assert c.state != "failed", c.reason
    item = c.item
    assert item.path.startswith(config.video_tmp_dir()) and item.size == len(fake.dl_body)
    assert open(item.path, "rb").read() == fake.dl_body
    hop, dl = [r for r in fake.media_requests if r["path"].startswith(("/media/v1/", "/dl/"))]
    assert hop["path"] == "/media/v1/1=dv" and hop["headers"]["Authorization"] == "Bearer at1"
    assert dl["path"] == "/dl/v1" and "Authorization" not in dl["headers"]      # the bearer stayed home
    (set_uri,) = [call for call in app.tv_fake.calls if call[0] == "SetAVTransportURI"]
    assert fake.dl_finished[0] < set_uri[2]                                     # the whole file, then the TV
    assert 'size="%d"' % len(fake.dl_body) in set_uri[1]
    # the TV's tail probe is answered from the file
    status, _, got, _ = request(app.base_url, "GET", "/m/%s/%s" % (app.server.media_token, item.id),
                                {"Range": "bytes=16000-"})
    assert status == 206 and got == fake.dl_body[16000:]
    assert [r["path"] for r in fake.media_requests].count("/dl/v1") == 1
    # pinned while registered, released when the item leaves
    assert id(item) in downloads._holders
    app.registry.remove(item.id)
    assert id(item) not in downloads._holders


def test_download_is_abandoned_when_a_newer_cast_arrives(fake, app):
    src = app.sources["gphotos"]
    _connect(src, fake)
    _pick(src, fake, [_item("p1"), _item("v1", "VIDEO", "video/mp4")])
    fake.dl_body = bytes(range(256)) * 200
    fake.dl_delay = 0.02                                   # about four seconds in all
    first = app.cast(src.resolve("v1"))
    wait_for(lambda: (first.as_dict()["progress"] or 0) > 0.05)
    d = first.as_dict()
    assert d["state"] == "preparing" and 0 < d["progress"] < 1
    second = app.cast(src.resolve("p1"))
    wait_for(lambda: first.state == "cancelled" and second.sent.is_set())
    assert app.tv_fake.actions().count("SetAVTransportURI") == 1        # only the photo reached the TV
    assert first.item.path is None and first.item.progress is None
    assert os.listdir(config.video_tmp_dir()) == []                     # the partial file is gone


def test_download_refused_once_is_re_listed_twice_is_an_error(fake):
    from castlib import downloads
    src = _video_source(fake)
    fake.min_sig = 2                                       # the listed address (signature 1) is refused
    prep = downloads.fetch_whole(src.resolve("v1"))
    assert prep.size == len(fake.dl_body)
    hops = [r["path"] for r in fake.media_requests if r["path"].startswith("/media/v1/")]
    assert hops == ["/media/v1/1=dv", "/media/v1/2=dv"]
    downloads.cache.clear()
    fake.min_sig = 99
    with pytest.raises(UpstreamError) as err:
        downloads.fetch_whole(src.resolve("v1"))
    assert err.value.code == "download_refused"
    assert os.listdir(config.video_tmp_dir()) == []


def test_download_needs_room(fake, monkeypatch):
    import collections
    from castlib import downloads
    src = _video_source(fake)
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(downloads.shutil, "disk_usage", lambda path: usage(100 * downloads.GIB, 0, 100))
    with pytest.raises(ConfigError) as err:
        downloads.fetch_whole(src.resolve("v1"))
    assert err.value.code == "no_space" and "free" in err.value.message
    assert os.listdir(config.video_tmp_dir()) == []


def _fake_disk(monkeypatch, total, free):
    """``shutil.disk_usage`` as the downloads see it; ``free`` is a number or a function of the directory."""
    import collections
    from castlib import downloads
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(downloads.shutil, "disk_usage",
                        lambda path: usage(total, 0, free(path) if callable(free) else free))


def _on_disk(path):
    return sum(os.path.getsize(os.path.join(path, name)) for name in os.listdir(path))


def _cached(name, size, pin=False):
    from castlib import downloads
    from castlib.photos import Prepared
    path = os.path.join(config.video_tmp_dir(), name)
    with open(path, "wb") as fh:
        fh.write(b"\0" * size)
    key = ("gphotos", name, "")
    if pin:
        downloads.cache.pin(key)                                  # an item still holds it
    downloads.cache.put(key, Prepared(path=path, mime="video/mp4", size=size, width=0, height=0, profile=""))
    return path


def test_download_limit_holds_without_content_length(fake, monkeypatch):
    from castlib import downloads
    src = _video_source(fake)
    fake.dl_no_length = True
    monkeypatch.setenv(downloads.MAX_ENV, "0.000001")             # about 1 KiB; the original is 2 KiB
    with pytest.raises(ConfigError) as err:
        downloads.fetch_whole(src.resolve("v1"))
    assert err.value.code == "too_large" and "1080p stream" in err.value.hint
    assert os.listdir(config.video_tmp_dir()) == []               # the partial file went too


def test_download_limit_refuses_a_known_length_before_writing(fake, monkeypatch):
    from castlib import downloads
    src = _video_source(fake)
    monkeypatch.setenv(downloads.MAX_ENV, "0.000001")
    made = []
    real = downloads.tempfile.mkstemp
    monkeypatch.setattr(downloads.tempfile, "mkstemp", lambda **kw: made.append(kw) or real(**kw))
    with pytest.raises(ConfigError) as err:
        downloads.fetch_whole(src.resolve("v1"))
    assert err.value.code == "too_large" and made == []           # no file was even created
    for bad in ("lots", "0", "-1", "inf", "nan"):
        monkeypatch.setenv(downloads.MAX_ENV, bad)
        with pytest.raises(ConfigError) as err:
            downloads.fetch_whole(src.resolve("v1"))
        assert err.value.code == "bad_download_limit"


def test_download_stops_before_the_reserve(fake, monkeypatch):
    from castlib import downloads
    src = _video_source(fake)
    fake.dl_no_length = True                                      # nothing to weigh up front: every write decides
    _fake_disk(monkeypatch, 10 * downloads.GIB, lambda path: downloads.RESERVE_MIN + 1024 - _on_disk(path))
    with pytest.raises(ConfigError) as err:
        downloads.fetch_whole(src.resolve("v1"))
    assert err.value.code == "no_space" and "reserve" in err.value.message and "1080p stream" in err.value.hint
    assert os.listdir(config.video_tmp_dir()) == []


def test_download_makes_room_from_unheld_cache(fake, monkeypatch):
    from castlib import downloads
    src = _video_source(fake)
    old = _cached("old.mp4", 2000)
    _fake_disk(monkeypatch, 10 * downloads.GIB, lambda path: downloads.RESERVE_MIN + 3000 - _on_disk(path))
    prep = downloads.fetch_whole(src.resolve("v1"))
    assert prep.size == len(fake.dl_body) and not os.path.exists(old)   # the unheld download made way


def test_download_budget_counts_held_downloads(fake, monkeypatch):
    from castlib import downloads
    src = _video_source(fake)
    held = _cached("held.mp4", 2000, pin=True)
    _fake_disk(monkeypatch, 4 * 3000, 100 * downloads.GIB)        # a 3000-byte budget, room to spare
    with pytest.raises(ConfigError) as err:
        downloads.fetch_whole(src.resolve("v1"))
    assert err.value.code == "download_budget" and os.path.exists(held)   # a held file is never dropped
    assert _on_disk(config.video_tmp_dir()) == 2000


def test_download_reports_a_full_disk(fake, monkeypatch):
    import errno
    from castlib import downloads
    src = _video_source(fake)
    real = os.fdopen

    class Full:
        def __init__(self, fh):
            self.fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.fh.close()

        def write(self, data):
            raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(downloads.os, "fdopen",
                        lambda fd, *a, **kw: Full(real(fd, *a, **kw)) if kw.get("buffering") == 0 else real(fd, *a, **kw))
    with pytest.raises(ConfigError) as err:
        downloads.fetch_whole(src.resolve("v1"))
    assert err.value.code == "no_space" and "filled up" in err.value.message
    assert os.listdir(config.video_tmp_dir()) == []


def test_bearer_survives_a_same_host_redirect_only(fake):
    from castlib.net import BEARER_SAFE
    src = _video_source(fake)
    base, _ = src._refresh_base("v1")
    for suffix, crosses in (("=same", False), ("=m37", True)):
        req = urllib.request.Request(base + suffix, headers={"Authorization": "Bearer at1", "Range": "bytes=0-3"})
        with BEARER_SAFE.open(req, timeout=5) as r:
            assert r.status == 206
        last = fake.media_requests[-1]
        assert last["path"] == "/stream/v1" and last["headers"]["Range"] == "bytes=0-3"
        assert ("Authorization" in last["headers"]) is not crosses, suffix


def test_bearer_stays_on_its_origin():
    from castlib.net import _DropAuthAcrossOrigins
    hop = _DropAuthAcrossOrigins()

    def carried(target):
        req = urllib.request.Request("https://lh3.example/a", headers={"Authorization": "Bearer at1"})
        return "Authorization" in hop.redirect_request(req, None, 302, "Found", {}, target).headers
    assert carried("https://lh3.example/b")
    assert carried("https://LH3.example:443/b")              # the default port spelled out, the host's case
    assert not carried("http://lh3.example/b")               # a TLS downgrade
    assert not carried("https://lh3.example:8443/b")         # another port
    assert not carried("https://other.example/b")            # another host
    assert not carried("https://lh3.example:bad/b")          # an unreadable port counts as another origin

