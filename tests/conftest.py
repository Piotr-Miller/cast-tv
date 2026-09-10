"""Shared fixtures: an in-process cast-tv server, and a scriptable upstream for the relay."""
from __future__ import annotations

import http.client
import http.server
import socketserver
import threading

import pytest

from castlib.items import MediaItem
from castlib.server import Server


@pytest.fixture
def server():
    """A ``Server`` on 127.0.0.1:0 in a thread; yields ``(server, base_url)``."""
    srv = Server(("127.0.0.1", 0))
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield srv, "http://127.0.0.1:%d" % srv.port
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def local_file(tmp_path):
    """A 500-byte file of distinct bytes and a registered video item for it."""
    def make(server, name="clip.mp4", data=None):
        data = bytes(range(256)) * 2 if data is None else data
        data = data[:500] if len(data) > 500 else data
        path = tmp_path / name
        path.write_bytes(data)
        item = server.registry.add(MediaItem(kind="video", title=name, mime="video/mp4",
                                             source="local", source_id=str(path),
                                             path=str(path), size=len(data)))
        return item, data
    return make


def request(base_url, method, path, headers=None, conn=None):
    """One request, the whole response read; returns ``(status, headers, body, conn)``."""
    if conn is None:
        host = base_url.split("://", 1)[1]
        conn = http.client.HTTPConnection(host, timeout=5)
    conn.request(method, path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    return resp.status, resp.headers, body, conn


class _StubHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        self._answer(True)

    def do_HEAD(self):
        self._answer(False)

    def _answer(self, body):
        spec = self.server.spec
        self.server.requests.append({"path": self.path, "headers": dict(self.headers)})
        status = spec["statuses"].get(self.path)
        if status is None:
            status = 200
        data = spec["body"]
        if status >= 400:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        rng = self.headers.get("Range")
        if rng and spec["honour_range"]:
            a, b = rng.replace("bytes=", "").split("-")
            start = int(a)
            end = int(b) if b else len(data) - 1
            chunk = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, len(data)))
        else:
            chunk = data
            self.send_response(200)
        self.send_header("Content-Type", spec["ctype"])
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        if body:
            self.wfile.write(chunk)


class StubUpstream(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture
def upstream():
    """``upstream(body, honour_range=True, ctype=..., statuses={path: code})`` -> stub server."""
    servers = []

    def make(body=b"", honour_range=True, ctype="video/mp4", statuses=None):
        srv = StubUpstream(("127.0.0.1", 0), _StubHandler)
        srv.spec = {"body": body, "honour_range": honour_range, "ctype": ctype,
                    "statuses": statuses or {}}
        srv.requests = []
        srv.base = "http://127.0.0.1:%d" % srv.server_address[1]
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                         daemon=True).start()
        servers.append(srv)
        return srv
    yield make
    for srv in servers:
        srv.shutdown()
        srv.server_close()


# ---------------------------------------------------------------- Phase 3
class FakeTV:
    """A scripted renderer behind ``dlna.soap``: records every action, answers transport states.

    Each ``SetAVTransportURI`` starts a fresh script chosen by the item's
    kind: a photo reports ``PLAYING`` for ever (as the Samsung does), a video
    walks ``video_script`` one state per ``GetTransportInfo`` and repeats the
    last one. ``fail`` makes every call raise, as an unplugged TV would.
    """

    def __init__(self, registry_getter):
        self._registry = registry_getter
        self.video_script = ["TRANSITIONING", "PLAYING", "PLAYING", "STOPPED"]
        self.photo_script = ["PLAYING"]
        self.play_delay = 0.0
        self.faults = {}         # action -> UPnP error code to answer with, e.g. {"Play": "701"}
        self.fail = False
        self.calls = []          # (action, body, t_start, t_end)
        self.uris = []
        self._script = []
        self._index = 0
        self._lock = threading.Lock()

    def soap(self, url, svc, action, body=""):
        import re
        import time
        from xml.sax.saxutils import unescape
        if self.fail:
            raise OSError("unreachable")
        t0 = time.monotonic()
        answer = ""
        with self._lock:
            if action == "SetAVTransportURI":
                m = re.search(r"<CurrentURI>(.*?)</CurrentURI>", body)
                uri = unescape(m.group(1)) if m else ""
                self.uris.append(uri)
                item = self._registry().get(uri.rsplit("/", 1)[-1])
                self._script = list(self.photo_script if item is not None and item.kind == "photo"
                                    else self.video_script)
                self._index = 0
            elif action == "GetTransportInfo":
                if self._script:
                    state = self._script[min(self._index, len(self._script) - 1)]
                    self._index += 1
                else:
                    state = "STOPPED"
                answer = "<CurrentTransportState>%s</CurrentTransportState>" % state
            elif action == "GetPositionInfo":
                answer = "<RelTime>0:00:01</RelTime><TrackDuration>0:00:10</TrackDuration>"
        if action == "Play" and self.play_delay:
            time.sleep(self.play_delay)
        with self._lock:
            self.calls.append((action, body, t0, time.monotonic()))
        if action in self.faults:
            import io
            import urllib.error
            code = self.faults[action]
            desc = {"701": "Transition not available", "716": "Resource not found"}.get(code, "Fault")
            fault = ("<s:Envelope><s:Body><s:Fault><detail><UPnPError>"
                     "<errorCode>%s</errorCode><errorDescription>%s</errorDescription>"
                     "</UPnPError></detail></s:Fault></s:Body></s:Envelope>" % (code, desc)).encode()
            raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, io.BytesIO(fault))
        return answer

    def actions(self):
        with self._lock:
            return [c[0] for c in self.calls]

    def times(self, action):
        """``[(t_start, t_end)]`` for every call of ``action``."""
        with self._lock:
            return [(c[2], c[3]) for c in self.calls if c[0] == action]

    def uri_ids(self):
        with self._lock:
            return [u.rsplit("/", 1)[-1] for u in self.uris]


@pytest.fixture
def fast_supervisor(monkeypatch):
    """Poll and budget constants scaled so a whole cast lifecycle takes well under a second."""
    from castlib import supervisor
    monkeypatch.setattr(supervisor, "POLL_INTERVAL", 0.02)
    monkeypatch.setattr(supervisor, "BUDGET_TRANSITIONING", 0.6)
    monkeypatch.setattr(supervisor, "BUDGET_OTHER", 0.3)
    monkeypatch.setattr(supervisor, "TICK", 0.02)
    monkeypatch.setattr(supervisor, "check_codecs", lambda path: ([], None))


@pytest.fixture
def app(server, monkeypatch, tmp_path, fast_supervisor):
    """An ``App`` on the in-process server, talking to a ``FakeTV``; yields the app (``app.tv_fake`` is the TV)."""
    from castlib import config, dlna
    from castlib.app import App
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    srv, base = server
    a = App(srv)
    tv = FakeTV(lambda: srv.registry)
    monkeypatch.setattr(dlna, "soap", tv.soap)
    a.use_tv("127.0.0.1", "http://127.0.0.1:1/avt", "Fake TV")
    a.tv_fake = tv
    a.base_url = base
    try:
        yield a
    finally:
        a.close()


def wait_for(predicate, timeout=5.0, step=0.01):
    """Poll ``predicate`` until true; fail loudly otherwise."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    raise AssertionError("condition not met within %.1fs" % timeout)
