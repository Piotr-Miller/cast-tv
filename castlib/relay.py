"""Relay a remote stream to the TV: we fetch over HTTPS, the TV gets plain HTTP.

The trim logic is the script's, unchanged in spirit: an upstream that ignores
``Range`` and hands back the whole file is compensated for by skipping to the
offset ourselves and synthesising the 206 the TV expects. New here: the
upstream comes from ``item.resolve()`` on every open (signed URLs expire), its
headers travel with every request, and a 401/403/404 re-resolves once.
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

from castlib.errors import CastError
from castlib.media import dlna_headers

CHUNK = 256 * 1024
RERESOLVE_ON = (401, 403, 404)


def _open(item, wanted, handler):
    """Open the upstream, re-resolving once when it refuses the address it gave us."""
    last = None
    for attempt in (1, 2):
        up = item.resolve()
        req = urllib.request.Request(up.url, headers={"User-Agent": "Mozilla/5.0",
                                                       "Accept": "*/*"})
        for name, value in up.headers.items():
            req.add_header(name, value)
        if wanted:
            req.add_header("Range", wanted)
        try:
            return up, (up.opener or urllib.request).urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in RERESOLVE_ON and attempt == 1:
                handler.dbg(item, "upstream answered %d, resolving again" % e.code)
                continue
            raise
        except CastError:
            raise
    raise last


def proxy(handler, item, body=True):
    wanted = handler.headers.get("Range")
    start = end = None
    m = re.match(r"bytes=(\d+)-(\d*)", wanted or "")
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else None

    handler.dbg(item, "%s %s  Range=%s" % (handler.command, handler.path, wanted or "-"))
    try:
        up, resp = _open(item, wanted, handler)
    except Exception as e:
        sys.stderr.write("\n   ! upstream refused: %s\n" % e)
        handler.plain_error(502)
        return

    with resp:
        length = resp.headers.get("Content-Length")
        handler.dbg(item, "upstream: %s %s, %s bytes" % (
            resp.status, resp.headers.get("Content-Type", "?"), length or "?"))

        # The upstream may ignore Range and hand back the whole file. The TV
        # is waiting for bytes at an offset, would receive the start of the
        # file instead, and would quietly stop - so trim the range ourselves.
        trim = start is not None and resp.status != 206
        total = int(length) if (length or "").isdigit() else None
        # Samsung is fussy about Content-Type: when the upstream says
        # something generic, name the item's own type instead.
        ctype = resp.headers.get("Content-Type") or ""
        if not ctype.startswith("video/") and item.mime:
            ctype = item.mime

        if trim and total:
            last = min(end if end is not None else total - 1, total - 1)
            if start > last:
                handler.send_response(416)
                handler.send_header("Content-Range", "bytes */%d" % total)
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            handler.send_response(206)
            if ctype:
                handler.send_header("Content-Type", ctype)
            handler.send_header("Content-Range", "bytes %d-%d/%d" % (start, last, total))
            handler.send_header("Content-Length", str(last - start + 1))
            handler.send_header("Accept-Ranges", "bytes")
            to_send = last - start + 1
            handler.dbg(item, "trimming range on upstream's behalf: %d-%d/%d"
                        % (start, last, total))
        else:
            handler.send_response(resp.status)
            if ctype:
                handler.send_header("Content-Type", ctype)
            for h in ("Content-Length", "Content-Range", "Accept-Ranges"):
                if resp.headers.get(h):
                    handler.send_header(h, resp.headers[h])
            if not resp.headers.get("Accept-Ranges"):
                handler.send_header("Accept-Ranges", "bytes")
            to_send = None
            if trim or not (length or "").isdigit():
                # unknown length: all we can do is run on and close afterwards
                handler.close_connection = True

        for name, value in dlna_headers(item):
            handler.send_header(name, value)
        if item.caption:
            handler.send_header("CaptionInfo.sec", item.caption[1])
        handler.end_headers()
        if not body:
            return

        try:
            if trim:                       # skip to the requested offset
                left = start
                while left > 0:
                    chunk = resp.read(min(CHUNK, left))
                    if not chunk:
                        return
                    left -= len(chunk)
            while to_send is None or to_send > 0:
                chunk = resp.read(CHUNK if to_send is None else min(CHUNK, to_send))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                if to_send is not None:
                    to_send -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            handler.close_connection = True
