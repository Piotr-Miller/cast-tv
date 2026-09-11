"""The HTTP server the TV and the browser both talk to.

Dispatch happens before any lookup: ``/m/<token>/<id>`` serves registered
media (the token is the only credential the TV can carry); ``/api`` and
``/ui`` sit behind the Origin/Host check so a web page open in the user's
browser cannot drive the TV. Every generated response carries an exact
``Content-Length`` so keep-alive framing stays correct; nothing here calls
``send_error``.
"""
from __future__ import annotations

import http.server
import json
import os
import re
import secrets
import socketserver
import sys
import urllib.parse

from castlib import relay
from castlib.discovery import local_addresses
from castlib.items import Registry
from castlib.media import dlna_headers

CHUNK = 256 * 1024
MEDIA_TIMEOUT = 600        # a paused TV may hold a transfer open this long
MAX_DRAIN = 1 << 20        # request bodies we read and discard before answering

# The UI is four files served from an exact-match map: no directory listing,
# no path traversal, nothing else under /ui/ exists.
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
UI_FILES = {"/ui/": ("index.html", "text/html; charset=utf-8"),
            "/ui/app.js": ("app.js", "application/javascript; charset=utf-8"),
            "/ui/style.css": ("style.css", "text/css; charset=utf-8"),
            "/ui/alpine.min.js": ("alpine.min.js", "application/javascript; charset=utf-8")}


def parse_range(header, size):
    """``(start, end, partial)`` for a ``Range`` header against ``size`` bytes.

    ``None`` means unsatisfiable (answer 416). A malformed or multi-range header
    is treated as no range at all: the full body, status 200.
    """
    if not header:
        return 0, size - 1, False
    m = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", header)
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return 0, size - 1, False
    a, b = m.group(1), m.group(2)
    if a == "":                       # bytes=-N (tail of the file)
        n = int(b)
        if n == 0:
            return None
        start, end = max(0, size - n), size - 1
    else:
        start = int(a)
        end = min(int(b), size - 1) if b else size - 1
        if start >= size:
            return None
        if end < start:
            return 0, size - 1, False
    return start, end, True


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30              # idle keep-alive connections do not pin a thread
    server_version = "cast-tv"
    sys_version = ""

    def log_message(self, *a):
        pass

    def dbg(self, item, msg):
        if item is not None and item.debug:
            sys.stderr.write("\n   [tv] %s\n" % msg)
            sys.stderr.flush()

    # ---------------------------------------------------------------- replies
    def _json(self, status, obj, headers=()):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json_error(self, status, code, message, hint=None):
        self._json(status, {"error": {"code": code, "message": message, "hint": hint}})

    def plain_error(self, status):
        """An empty error response that keeps the connection usable."""
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _drain(self):
        """Consume a request body we are not going to use, so keep-alive stays in sync.

        Safe to call more than once per request: only the first call reads.
        """
        if getattr(self, "_drained", False):
            return
        self._drained = True
        length = self.headers.get("Content-Length", "")
        if not length.isdigit():
            return
        n = int(length)
        if n > MAX_DRAIN:
            self.close_connection = True
            return
        while n > 0:
            chunk = self.rfile.read(min(CHUNK, n))
            if not chunk:
                break
            n -= len(chunk)

    # ------------------------------------------------------------- the rule
    def _check_origin(self):
        """Refuse requests a foreign page or a foreign name could have sent.

        ``Host`` must name this machine; an ``Origin``, when present, must be
        exactly ``http://`` plus that ``Host``; a cross-site fetch is refused.
        Answers 403 JSON and returns False on failure.
        """
        host_header = (self.headers.get("Host") or "").strip()
        host = _host_only(host_header)
        allowed = self.server.allowed_hosts
        ok = bool(host) and host.lower() in allowed
        origin = self.headers.get("Origin")
        if ok and origin is not None and origin.strip() != "http://" + host_header:
            ok = False
        if ok and (self.headers.get("Sec-Fetch-Site") or "").strip().lower() == "cross-site":
            ok = False
        if not ok:
            self._drain()
            self._json_error(403, "forbidden",
                             "This address may only be used from the cast-tv UI on this network.")
        return ok

    # ------------------------------------------------------------- dispatch
    def do_GET(self):
        self._dispatch(body=True)

    def do_HEAD(self):
        self._dispatch(body=False)

    def do_POST(self):
        self._dispatch(body=True)

    def _dispatch(self, body):
        self._drained = False
        raw_path, _, query = self.path.partition("?")
        path = urllib.parse.unquote(raw_path)
        if path.startswith("/m/"):
            self._drain()
            seg = path[3:].split("/")
            item = None
            if len(seg) == 2 and seg[0] == self.server.media_token:
                item = self.server.registry.get(seg[1])
            if item is None or self.command == "POST":
                self._json_error(404, "not_found", "Not found.")
                return
            self._media(item, body)
            return
        if path == "/api" or path.startswith("/api/"):
            if not self._check_origin():
                return
            app = self.server.app
            if app is None:
                self._drain()
                self._json_error(404, "not_found", "Not found.")
                return
            app.api(self, path, query)
            return
        if path == "/ui" or path.startswith("/ui/"):
            if not self._check_origin():
                return
            self._drain()
            self._static(path, body)
            return
        self._drain()
        if path == "/" and self.command != "POST":
            self.send_response(302)
            self.send_header("Location", "/ui/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/favicon.ico" and self.command != "POST":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._json_error(404, "not_found", "Not found.")

    # --------------------------------------------------------------- static
    def _static(self, path, body):
        if self.command == "POST":
            self._json_error(404, "not_found", "Not found.")
            return
        if path == "/ui":
            self.send_response(302)
            self.send_header("Location", "/ui/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        entry = UI_FILES.get(path)
        if entry is None:
            self._json_error(404, "not_found", "Not found.")
            return
        try:
            with open(os.path.join(UI_DIR, entry[0]), "rb") as fh:
                data = fh.read()
        except OSError:
            self._json_error(404, "not_found", "Not found.")
            return
        self.send_response(200)
        self.send_header("Content-Type", entry[1])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if body:
            self.wfile.write(data)

    # ---------------------------------------------------------------- media
    def _media(self, item, body):
        registry = self.server.registry
        registry.touch(item.id)
        registry.begin(item.id)
        try:
            self.connection.settimeout(MEDIA_TIMEOUT)
            if item.kind == "photo":
                # the route never converts: a photo is prepared before the TV
                # is told about it, or it is not served
                prep = item.prepared
                if prep is None:
                    self._json_error(404, "not_found", "Not found.")
                else:
                    self._serve_file(item, prep.path, prep.mime, body)
            elif item.path is None and item.resolve is not None:
                relay.proxy(self, item, body)
            else:
                self._serve_file(item, item.path, item.mime, body)
        finally:
            registry.end(item.id)
            try:
                self.connection.settimeout(self.timeout)   # back to the idle budget
            except OSError:
                pass

    def _serve_file(self, item, disk, mime, body):
        if not disk:
            self._json_error(404, "not_found", "Not found.")
            return
        try:
            fh = open(disk, "rb")
        except OSError:
            self._json_error(404, "not_found", "Not found.")
            return
        with fh:
            try:
                size = os.fstat(fh.fileno()).st_size
            except OSError:
                self._json_error(404, "not_found", "Not found.")
                return
            rng = parse_range(self.headers.get("Range"), size)
            if rng is None:
                self.dbg(item, "%s %s  Range=%s -> unsatisfiable /%d" % (
                    self.command, self.path, self.headers.get("Range", "-"), size))
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start, end, partial = rng
            self.dbg(item, "%s %s  Range=%s -> %d-%d/%d" % (
                self.command, self.path, self.headers.get("Range", "-"), start, end, size))
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            if partial:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            for name, value in dlna_headers(item):
                self.send_header(name, value)
            if item.caption:
                self.send_header("CaptionInfo.sec", item.caption[1])
            self.end_headers()
            if not body:
                return
            remaining = end - start + 1
            try:
                fh.seek(start)
                while remaining > 0:
                    chunk = fh.read(min(CHUNK, remaining))
                    if not chunk:
                        # the file shrank under us: the promised length cannot
                        # be honoured, so the connection must not be reused
                        self.close_connection = True
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True   # the TV seeked elsewhere or went away
            except OSError:
                self.close_connection = True


def _host_only(host_header):
    """The host part of a ``Host`` header: ``[::1]:8895`` -> ``::1``, ``x:8895`` -> ``x``."""
    if not host_header:
        return ""
    if host_header.startswith("["):
        return host_header[1:host_header.find("]")] if "]" in host_header else ""
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler=Handler, registry=None, allowed_hosts=None):
        super().__init__(address, handler)
        self.registry = registry or Registry()
        self.media_token = secrets.token_urlsafe(16)
        self.allowed_hosts = {h.lower() for h in (allowed_hosts or local_addresses())}
        self.app = None
        self.host = address[0]     # what media URLs name; the CLI sets the LAN address

    def handle_error(self, request, client_address):
        """A client that drops its keep-alive connection is not an error worth a traceback."""
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)

    @property
    def port(self):
        return self.server_address[1]

    def set_host(self, host):
        self.host = host
        self.allowed_hosts.add(host.lower())

    def media_url(self, item):
        return "http://%s:%d/m/%s/%s" % (self.host, self.port, self.media_token, item.id)
