"""A fake Chromium-family browser for the hand-off tests: a DevTools endpoint on 127.0.0.1 and a fake process.

``FakeBrowser.launch(args, **kwargs)`` stands in for ``subprocess.Popen``: it
records the command line, writes ``DevToolsActivePort`` into the
``--user-data-dir`` it finds there (unless told to stay ``silent`` or to
``exit_at_once``), and returns a ``FakeProcess`` whose ``poll()`` follows the
fake's life. The endpoint answers ``/json/version``, upgrades to a WebSocket
(server side: client frames must be masked, and are unmasked), and replies to
``Storage.getCookies`` from ``cookies`` (a list the test may swap between
polls) and to ``Browser.close`` by ending the process, as Chrome does. Extra
methods go in ``handlers``; ``split``, ``pad``, ``ping_first`` and ``stall``
shape the answers for the framing tests.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import threading
import uuid

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def cookie(value, domain=".gopro.com", name="gp_access_token", session=False, expires=1790000000.0):
    """A ``Network.Cookie`` as ``Storage.getCookies`` returns one (fields observed 2026-09-21)."""
    return {"name": name, "value": value, "domain": domain, "path": "/", "expires": -1 if session else expires,
            "size": len(name) + len(value), "httpOnly": True, "secure": True, "session": session,
            "sameSite": "Lax", "priority": "Medium", "sourceScheme": "Secure", "sourcePort": 443}


def _frame(opcode, payload, fin=True):
    """A server frame: never masked; 7/16/64-bit length by size."""
    n = len(payload)
    head = bytes([(0x80 if fin else 0) | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack("!H", n)
    else:
        head += bytes([127]) + struct.pack("!Q", n)
    return head + payload


def _exact(conn, buf, n):
    while len(buf) < n:
        chunk = conn.recv(65536)
        if not chunk:
            raise OSError("closed")
        buf += chunk
    return buf[:n], buf[n:]


def _read_frame(conn, buf):
    """``(fin, opcode, masked, payload, rest)`` of the next client frame."""
    head, buf = _exact(conn, buf, 2)
    fin, opcode = bool(head[0] & 0x80), head[0] & 0x0F
    masked, length = bool(head[1] & 0x80), head[1] & 0x7F
    if length == 126:
        raw, buf = _exact(conn, buf, 2)
        length = struct.unpack("!H", raw)[0]
    elif length == 127:
        raw, buf = _exact(conn, buf, 8)
        length = struct.unpack("!Q", raw)[0]
    key = None
    if masked:
        key, buf = _exact(conn, buf, 4)
    payload, buf = _exact(conn, buf, length)
    if key:
        payload = bytes(b ^ key[i & 3] for i, b in enumerate(payload))
    return fin, opcode, masked, payload, buf


class FakeProcess:
    """What ``launch`` returns: ``poll``, ``wait``, ``terminate``, ``kill`` bound to the fake's life."""

    def __init__(self, fake):
        self._fake = fake
        self.pid = 4242
        self.returncode = None

    def poll(self):
        if self._fake.exited.is_set():
            self.returncode = self._fake.exit_code
        return self.returncode

    def wait(self, timeout=None):
        if not self._fake.exited.wait(timeout):
            raise subprocess.TimeoutExpired("fake-browser", timeout)
        return self.poll()

    def terminate(self):
        self._fake.terminated += 1
        self._fake.end(-15)

    def kill(self):
        self._fake.killed += 1
        self._fake.end(-9)


class FakeBrowser:
    def __init__(self, cookies=None, silent=False, exit_at_once=None):
        self.cookies = list(cookies or [])      # what Storage.getCookies answers; swap it between polls
        self.silent = silent                    # never writes the port file
        self.exit_at_once = exit_at_once        # stderr text: the process exits before writing the port
        self.stall = False                      # answer nothing (a call runs into its timeout)
        self.split = 1                          # frames per answer (continuation frames)
        self.pad = 0                            # extra bytes in every answer (long frames)
        self.ping_first = False                 # send a ping before every answer
        self.handlers = {}                      # method -> callable(params) -> result
        self.requests = []                      # handshake headers of every WebSocket connection
        self.received = []                      # decoded client messages
        self.masked = []                        # whether each client frame carried a mask
        self.pongs = []                         # payloads the client answered our pings with
        self.polls = 0                          # Storage.getCookies calls
        self.closed = 0                         # Browser.close calls
        self.launches = []                      # (args, kwargs) of every launch
        self.port_file_existed = None           # at launch: was a stale DevToolsActivePort there?
        self.terminated = self.killed = 0
        self.exited = threading.Event()
        self.exit_code = None
        self.port = None
        self.uuid = "fake-" + uuid.uuid4().hex
        self.process = FakeProcess(self)
        self._server = None
        self._conns = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------ control
    @property
    def ws_url(self):
        return "ws://127.0.0.1:%d/devtools/browser/%s" % (self.port, self.uuid)

    def serve(self):
        """Start the DevTools endpoint (idempotent); returns the fake."""
        with self._lock:
            if self._server is not None:
                return self
            srv = socket.socket()
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            srv.listen(5)
            self._server = srv
            self.port = srv.getsockname()[1]
        threading.Thread(target=self._accept, name="fake-browser", daemon=True).start()
        return self

    def launch(self, args, **kwargs):
        """The ``subprocess.Popen`` stand-in."""
        self.launches.append((list(args), dict(kwargs)))
        profile = next(a[len("--user-data-dir="):] for a in args if a.startswith("--user-data-dir="))
        port_file = os.path.join(profile, "DevToolsActivePort")
        self.port_file_existed = os.path.exists(port_file)
        if self.exit_at_once is not None:
            err = kwargs.get("stderr")
            if hasattr(err, "write"):
                err.write(self.exit_at_once.encode("utf-8"))
                err.flush()
            self.end(1)
            return self.process
        if not self.silent:
            self.serve()
            with open(port_file, "w", encoding="utf-8") as fh:
                fh.write("%d\n/devtools/browser/%s\n" % (self.port, self.uuid))
        return self.process

    def end(self, code=0):
        """The process exits: every connection drops and the endpoint stops listening."""
        with self._lock:
            if self.exited.is_set():
                return
            self.exit_code = code
        self.exited.set()
        self.stop()

    def close_window(self):
        """The person closed the window: with one app window that is the end of the process."""
        self.end(0)

    def drop_connections(self, close_frame=True):
        """The endpoint ends every WebSocket (a close frame first, unless told not to) but keeps running."""
        with self._lock:
            conns, self._conns = self._conns, []
        for conn in conns:
            try:
                if close_frame:
                    conn.sendall(_frame(0x8, struct.pack("!H", 1001)))
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

    def stop(self):
        self.drop_connections(close_frame=False)
        with self._lock:
            srv, self._server = self._server, None
        if srv is not None:
            try:
                srv.shutdown(socket.SHUT_RDWR)   # wakes the accept() blocked on another thread; close alone does not
            except OSError:
                pass
            try:
                srv.close()
            except OSError:
                pass

    # ---------------------------------------------------------- the server
    def _accept(self):
        while True:
            with self._lock:
                srv = self._server
            if srv is None:
                return
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with self._lock:
                self._conns.append(conn)
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
            head, _, rest = buf.partition(b"\r\n\r\n")
            lines = head.decode("iso-8859-1").split("\r\n")
            path = lines[0].split(" ")[1]
            headers = {}
            for line in lines[1:]:
                name, sep, value = line.partition(":")
                if sep:
                    headers[name.strip().lower()] = value.strip()
            if path == "/json/version":
                body = json.dumps({"Browser": "Chrome/153.0.8010.47", "Protocol-Version": "1.3",
                                   "webSocketDebuggerUrl": self.ws_url}).encode("utf-8")
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n"
                             % len(body) + body)
                return
            if (path != "/devtools/browser/" + self.uuid or headers.get("upgrade", "").lower() != "websocket"
                    or "sec-websocket-key" not in headers):
                conn.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                return
            self.requests.append(headers)
            accept = base64.b64encode(hashlib.sha1((headers["sec-websocket-key"] + GUID).encode("ascii")).digest())
            conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                         b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n")
            self._websocket(conn, rest)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _websocket(self, conn, buf):
        parts = []
        while True:
            fin, opcode, masked, payload, buf = _read_frame(conn, buf)
            self.masked.append(masked)
            if opcode == 0x8:
                return
            if opcode == 0xA:
                self.pongs.append(payload)
                continue
            if opcode == 0x9:
                conn.sendall(_frame(0xA, payload))
                continue
            parts.append(payload)
            if not fin:
                continue
            data, parts = b"".join(parts), []
            msg = json.loads(data.decode("utf-8"))
            self.received.append(msg)
            answer = self._answer(msg)
            if answer is not None:
                self._reply(conn, answer)
            if msg.get("method") == "Browser.close" and "Browser.close" not in self.handlers:
                self.end(0)                      # as Chrome: answered, then the process leaves
                return

    def _answer(self, msg):
        method, params = msg.get("method"), msg.get("params") or {}
        if self.stall:
            return None
        if method in self.handlers:
            result = self.handlers[method](params)
        elif method == "Storage.getCookies":
            self.polls += 1
            result = {"cookies": [dict(c) for c in self.cookies]}
        elif method == "Browser.close":
            self.closed += 1
            result = {}
        else:
            return {"id": msg.get("id"), "error": {"code": -32601, "message": "'%s' wasn't found" % method}}
        if self.pad:
            result = dict(result, padding="x" * self.pad)
        return {"id": msg.get("id"), "result": result}

    def _reply(self, conn, answer):
        data = json.dumps(answer).encode("utf-8")
        if self.ping_first:
            conn.sendall(_frame(0x9, b"still there?"))
        n = max(1, self.split)
        size = max(1, -(-len(data) // n))
        chunks = [data[i:i + size] for i in range(0, len(data), size)] or [b""]
        for i, chunk in enumerate(chunks):
            conn.sendall(_frame(0x1 if i == 0 else 0x0, chunk, fin=i == len(chunks) - 1))
