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
