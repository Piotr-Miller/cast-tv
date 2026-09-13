"""Videos whose upstream ignores Range are fetched whole before the TV hears about them.

Google Photos' original video (``baseUrl=dv``) redirects to a host that answers
every request with the whole file: 200, no ``Accept-Ranges``, about 5 s to the
first byte (probed 2026-09-13). This TV probes the end of an MP4 inside
``SetAVTransportURI``, so relaying such a file means reading everything up to
the tail within the TV's 10 s SOAP window, and the cast times out. An item
marked ``download=True`` is therefore fetched into a per-process directory
first; the server then serves it as a local file, ranges and all.

Files live in a bounded LRU like converted photos, pinned while an item holds
them (``release`` is called when the item leaves the registry, or when its
cast ends before registering), and go with their directory at exit.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import urllib.error
import urllib.request

from castlib import config, net
from castlib.errors import CastError, ConfigError, UpstreamError
from castlib.net import BEARER_SAFE
from castlib.photos import Prepared, _Cache

CACHE_BYTES = 4 * 1024 ** 3        # unpinned downloads kept for a re-cast; pinned ones always stay
CACHE_ENTRIES = 16
CHUNK = 1024 * 1024
SPACE_MARGIN = 256 * 1024 * 1024   # left free on the disk after a download
RETRY_ON = (401, 403, 404)         # the upstream refused the address it gave us: ask the source once more
TIMEOUT = 30
EXTENSIONS = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/x-matroska": ".mkv",
              "video/webm": ".webm"}

cache = _Cache(max_bytes=CACHE_BYTES, max_entries=CACHE_ENTRIES)
_lock = threading.Lock()           # one download at a time; the playback executor has one worker anyway
_holders: dict[int, tuple] = {}    # id(item) -> (item, key) for every item holding one pin
_holders_lock = threading.Lock()


class _Abandoned(Exception):
    """The cast that asked for the file was superseded; the partial file is dropped."""


def cache_key(item) -> tuple:
    return (item.source, item.source_id, item.version or "")


def _open(item):
    """Open the upstream, re-resolving once (through ``refresh`` when there is one) after a refusal."""
    for attempt in (1, 2):
        up = (item.refresh or item.resolve)() if attempt == 2 else item.resolve()
        req = urllib.request.Request(up.url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
        for name, value in up.headers.items():
            req.add_header(name, value)
        try:
            return (up.opener or BEARER_SAFE).open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in RETRY_ON and attempt == 1:
                continue
            raise UpstreamError("download_refused", "The source answered %d for %s." % (e.code, item.title),
                                source=item.source, item=item.source_id)
        except CastError:
            raise
        except Exception as e:
            raise UpstreamError("download_failed", "Could not fetch %s: %s" % (item.title, e),
                                source=item.source, item=item.source_id)


def _download(item, keep_going, progress) -> Prepared:
    resp = _open(item)
    with resp:
        length = resp.headers.get("Content-Length") or ""
        total = int(length) if length.isdigit() else None
        directory = config.video_tmp_dir()
        if total is not None:
            free = shutil.disk_usage(directory).free
            if free < total + SPACE_MARGIN:
                raise ConfigError("no_space", "Not enough room to fetch %s: %s needed, %s free in %s."
                                  % (item.title, net.human(total), net.human(free), directory),
                                  source=item.source, item=item.source_id)
        fd, path = tempfile.mkstemp(prefix="v", suffix=EXTENSIONS.get(item.mime, ".bin"), dir=directory)
        got = 0
        try:
            with os.fdopen(fd, "wb") as fh:
                while True:
                    if not keep_going():
                        raise _Abandoned()
                    try:
                        # read1: whatever has arrived, up to CHUNK - a plain read() blocks for the
                        # whole megabyte, so a slow link would freeze the progress and the abandon check
                        chunk = resp.read1(CHUNK) if hasattr(resp, "read1") else resp.read(CHUNK)
                    except OSError as e:
                        raise UpstreamError("download_failed", "Fetching %s broke off after %s: %s"
                                            % (item.title, net.human(got), e),
                                            source=item.source, item=item.source_id)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if total:
                        progress(min(1.0, got / total))
            if got == 0 or (total is not None and got != total):
                raise UpstreamError("download_short", "Fetching %s ended after %s of %s."
                                    % (item.title, net.human(got), net.human(total)),
                                    source=item.source, item=item.source_id)
        except BaseException:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
    return Prepared(path=path, mime=item.mime, size=got, width=item.width or 0,
                    height=item.height or 0, profile="")


def fetch_whole(item, keep_going=lambda: True) -> Prepared | None:
    """Fetch the item's upstream into a file and point ``item.path`` at it; ``None`` when abandoned.

    ``keep_going()`` is asked between chunks: once it answers false the
    partial file is removed and nothing is set. ``item.progress`` runs from 0
    to 1 while bytes arrive. One item holds one pin, as in ``photos.prepare``.
    Raises ``UpstreamError`` or ``ConfigError``.
    """
    key = cache_key(item)
    with _holders_lock:
        holds = id(item) in _holders
    if holds and item.path and cache.get(key) is not None:
        return cache.get(key)
    cache.pin(key)                       # before the file exists: no window for eviction
    try:
        prep = cache.get(key)
        if prep is None:
            with _lock:
                prep = cache.get(key)
                if prep is None:
                    item.progress = 0.0
                    prep = _download(item, keep_going,
                                     lambda share: setattr(item, "progress", round(share, 3)))
                    cache.put(key, prep)
    except _Abandoned:
        cache.unpin(key)
        item.progress = None
        return None
    except BaseException:
        cache.unpin(key)
        item.progress = None
        raise
    item.path, item.size, item.progress = prep.path, prep.size, None
    with _holders_lock:
        _holders[id(item)] = (item, key)
    return prep


def release(item) -> None:
    """The item no longer needs its file; the cache may drop it under pressure."""
    with _holders_lock:
        held = _holders.pop(id(item), None)
    if held is not None:
        cache.unpin(held[1])


def attach(registry) -> None:
    """Release downloads as items leave the registry, next to whatever it already releases."""
    before = registry.on_remove

    def on_remove(item):
        if before is not None:
            before(item)
        release(item)
    registry.on_remove = on_remove
