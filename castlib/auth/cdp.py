"""A client-side WebSocket subset and a Chrome DevTools Protocol session over it, on ``socket`` alone.

The GoPro hand-off (``castlib.auth.browser``) talks to the browser it launched
over the DevTools Protocol, which rides on a WebSocket. This is the least of
that a client needs: the opening handshake, masked client frames, 7/16/64-bit
payload lengths, continuation frames joined until ``FIN``, ``ping`` answered
with ``pong``, and ``call(method, params)`` matched to its answer by ``id``.
Events (messages without an ``id``) are discarded. No dependency, no build
step.

The handshake sends no ``Origin`` header, on purpose: since Chrome 111 the
DevTools endpoint refuses a request whose ``Origin`` is not on
``--remote-allow-origins`` and accepts one that carries none (spike,
2026-09-21). Nothing here logs a payload: a ``Storage.getCookies`` answer
holds the person's session cookie.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time
import urllib.parse

HANDSHAKE_TIMEOUT = 10.0
CALL_TIMEOUT = 10.0
MAX_MESSAGE = 64 << 20          # bytes; a cookie listing is kilobytes
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONTINUATION, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class CdpError(Exception):
    """The session cannot answer: a protocol error from the browser, a closed socket, a timeout.

    ``code`` is ``protocol`` (the browser refused the command; the session
    stays usable), ``closed``, ``timeout``, ``unreachable``, ``refused`` or
    ``bad_url``; ``message`` says what happened, never what was sent.
    """

    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def connect(ws_url: str, timeout: float = HANDSHAKE_TIMEOUT) -> Session:
    """Open the WebSocket at ``ws_url`` (``ws://host:port/path``) and return a ``Session`` over it."""
    parts = urllib.parse.urlsplit(ws_url)
    if parts.scheme != "ws" or not parts.hostname:
        raise CdpError("bad_url", "Not a ws:// address: %s" % ws_url)
    host, port = parts.hostname, parts.port or 80
    path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
    request = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, host, port, key))
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        raise CdpError("unreachable", "Could not connect to %s: %s" % (ws_url, e))
    try:
        sock.sendall(request.encode("ascii"))
        head, rest = _read_head(sock, time.monotonic() + timeout)
        status, headers = _parse_head(head)
        if status != 101:
            raise CdpError("refused", "The DevTools endpoint answered %d to the WebSocket handshake." % status)
        if headers.get("sec-websocket-accept") != accept:
            raise CdpError("refused", "The WebSocket handshake answer did not match the key.")
    except socket.timeout:
        sock.close()
        raise CdpError("timeout", "No answer to the WebSocket handshake within %g s." % timeout)
    except OSError as e:
        sock.close()
        raise CdpError("closed", "The WebSocket handshake failed: %s" % e)
    except CdpError:
        sock.close()
        raise
    return Session(sock, rest)


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise socket.timeout("deadline passed")
    return left


def _read_head(sock: socket.socket, deadline: float) -> tuple[str, bytes]:
    """The handshake answer up to the blank line, and whatever frame bytes followed it."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        sock.settimeout(_remaining(deadline))
        chunk = sock.recv(4096)
        if not chunk:
            raise CdpError("closed", "The DevTools endpoint closed the connection during the handshake.")
        buf += chunk
        if len(buf) > 65536:
            raise CdpError("refused", "The WebSocket handshake answer is too long.")
    head, _, rest = buf.partition(b"\r\n\r\n")
    return head.decode("iso-8859-1"), rest


def _parse_head(head: str) -> tuple[int, dict]:
    lines = head.split("\r\n")
    words = lines[0].split(" ", 2)
    try:
        status = int(words[1])
    except (IndexError, ValueError):
        raise CdpError("refused", "Not an HTTP answer to the WebSocket handshake.")
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    return status, headers


def _mask(payload: bytes, key: bytes) -> bytes:
    n = len(payload)
    if not n:
        return payload
    full = (key * (n // 4 + 1))[:n]
    return (int.from_bytes(payload, "big") ^ int.from_bytes(full, "big")).to_bytes(n, "big")


class Session:
    """One DevTools connection: ``call()`` sends a command and returns its ``result``; ``close()`` ends it.

    One call at a time (a lock): the caller is the reader, so nothing consumes
    messages in the background. An answer is matched by ``id``; anything else
    (events, answers to nothing) is discarded. After a timeout or a closed
    socket the session is unusable and closed for good.
    """

    def __init__(self, sock: socket.socket, buffered: bytes = b""):
        self._sock = sock
        self._buf = buffered
        self._lock = threading.Lock()
        self._id = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def call(self, method: str, params: dict | None = None, timeout: float = CALL_TIMEOUT) -> dict:
        """The ``result`` of ``method``; ``CdpError`` on a protocol error, a closed socket or a timeout."""
        with self._lock:
            if self._closed:
                raise CdpError("closed", "The DevTools connection is closed.")
            self._id += 1
            mid = self._id
            body = json.dumps({"id": mid, "method": method, "params": params or {}}).encode("utf-8")
            deadline = time.monotonic() + timeout
            try:
                self._send(OP_TEXT, body)
                while True:
                    data = self._message(deadline)
                    try:
                        msg = json.loads(data.decode("utf-8"))
                    except ValueError:
                        continue
                    if not isinstance(msg, dict) or msg.get("id") != mid:
                        continue                 # an event, or an answer to nothing
                    error = msg.get("error")
                    if error is not None:
                        detail = error.get("message") if isinstance(error, dict) else None
                        raise CdpError("protocol", "%s failed: %s" % (method, detail or "no detail"))
                    result = msg.get("result")
                    return result if isinstance(result, dict) else {}
            except socket.timeout:
                self._drop()
                raise CdpError("timeout", "%s: no answer within %g s." % (method, timeout))
            except OSError as e:
                self._drop()
                raise CdpError("closed", "The DevTools connection ended: %s" % e)
            except CdpError as e:
                if e.code != "protocol":
                    self._drop()
                raise

    def close(self) -> None:
        """Send a close frame (best effort) and close the socket; a second close is a no-op."""
        with self._lock:
            if self._closed:
                return
            try:
                self._send(OP_CLOSE, struct.pack("!H", 1000))
            except OSError:
                pass
            self._drop()

    # ------------------------------------------------------------ frames
    def _drop(self) -> None:
        self._closed = True
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()

    def _send(self, opcode: int, payload: bytes) -> None:
        key = os.urandom(4)
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack("!Q", n)
        self._sock.sendall(head + key + _mask(payload, key))

    def _exact(self, n: int, deadline: float) -> bytes:
        while len(self._buf) < n:
            self._sock.settimeout(_remaining(deadline))
            chunk = self._sock.recv(65536)
            if not chunk:
                raise CdpError("closed", "The browser closed the DevTools connection.")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _frame(self, deadline: float) -> tuple[bool, int, bytes]:
        head = self._exact(2, deadline)
        fin, opcode = bool(head[0] & 0x80), head[0] & 0x0F
        masked, length = bool(head[1] & 0x80), head[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._exact(2, deadline))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._exact(8, deadline))[0]
        if length > MAX_MESSAGE:
            raise CdpError("protocol", "A %d-byte frame is more than this client reads." % length)
        key = self._exact(4, deadline) if masked else None
        payload = self._exact(length, deadline)
        if key:                                  # a server does not mask; unmasking costs nothing
            payload = _mask(payload, key)
        return fin, opcode, payload

    def _message(self, deadline: float) -> bytes:
        """One whole data message: continuation frames joined, control frames handled on the way."""
        parts: list[bytes] = []
        size = 0
        while True:
            fin, opcode, payload = self._frame(deadline)
            if opcode == OP_PING:
                self._send(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                raise CdpError("closed", "The browser closed the DevTools connection.")
            if opcode in (OP_TEXT, OP_BINARY):
                parts, size = [payload], len(payload)
            elif opcode == OP_CONTINUATION:
                if not parts:
                    raise CdpError("protocol", "A continuation frame arrived with nothing to continue.")
                parts.append(payload)
                size += len(payload)
            else:
                raise CdpError("protocol", "Unknown WebSocket opcode %d." % opcode)
            if size > MAX_MESSAGE:
                raise CdpError("protocol", "A message grew past %d bytes." % MAX_MESSAGE)
            if fin:
                return b"".join(parts)
