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

What a download may use is measured on the filesystem holding that directory:
one file at most ``CAST_TV_DOWNLOAD_MAX_GB`` GiB (default ``FILE_CAP``, or the
budget when that is smaller); every download together - held, cached and in
flight - at most ``BUDGET_SHARE`` of the filesystem; and no write that would
leave less free than the reserve. All three are checked before every write, so
a missing or false ``Content-Length`` changes nothing, and cached downloads
nobody holds are deleted first when room runs short. Raising the file limit
lifts neither the budget nor the reserve. The reserve is a threshold to stop
at, not a promise - other processes write too - so a full disk (``ENOSPC``)
is reported as ``no_space`` as well.
"""
from __future__ import annotations

import errno
import math
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
GIB = 1024 ** 3
FILE_CAP = 16 * GIB                # one download, unless CAST_TV_DOWNLOAD_MAX_GB says otherwise
BUDGET_SHARE = 0.25                # every download on disk together, as a share of the filesystem
RESERVE_SHARE = 0.05               # a write never leaves less free than this share of the filesystem,
RESERVE_MIN = GIB                  # nor less than this
MAX_ENV = "CAST_TV_DOWNLOAD_MAX_GB"
LIGHTER = 'Cast the "1080p stream" variant from its tile instead, or raise %s (GiB).' % MAX_ENV
RETRY_ON = (401, 403, 404)         # the upstream refused the address it gave us: ask the source once more
TIMEOUT = 30
EXTENSIONS = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/x-matroska": ".mkv",
              "video/webm": ".webm"}

cache = _Cache(max_bytes=CACHE_BYTES, max_entries=CACHE_ENTRIES)
_lock = threading.Lock()           # one download at a time, so the budget has one in flight to count
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


def _limits(directory: str) -> tuple[int, int, int]:
    """``(file, budget, reserve)`` in bytes for the filesystem holding ``directory``."""
    total = shutil.disk_usage(directory).total
    budget = int(total * BUDGET_SHARE)
    reserve = max(RESERVE_MIN, int(total * RESERVE_SHARE))
    raw = os.environ.get(MAX_ENV, "").strip()
    if not raw:
        return min(FILE_CAP, budget), budget, reserve
    try:
        gib = float(raw)
    except ValueError:
        gib = 0.0
    if not (gib > 0 and math.isfinite(gib)):
        raise ConfigError("bad_download_limit", "%s must be a positive number of GiB, not %r." % (MAX_ENV, raw))
    return int(gib * GIB), budget, reserve


def _room(item, directory: str, limits: tuple[int, int, int], got: int, size: int) -> None:
    """Allow ``size`` more bytes after ``got``, or raise: the file limit, the budget, the reserve."""
    file_limit, budget, reserve = limits
    if got + size > file_limit:
        raise ConfigError("too_large", "%s is larger than the %s limit for one download."
                          % (item.title, net.human(file_limit)), hint=LIGHTER,
                          source=item.source, item=item.source_id)
    dropped = False
    while True:
        held = cache.bytes + got + size          # _lock: this is the only download in flight
        free = shutil.disk_usage(directory).free
        if held <= budget and free - size >= reserve:
            return
        if dropped or not cache.drop_unpinned():   # cached downloads nobody holds go first
            break
        dropped = True
    if held > budget:
        raise ConfigError("download_budget", "Fetching %s would take downloads past their %s budget "
                          "(%s already held)." % (item.title, net.human(budget), net.human(cache.bytes)),
                          hint=LIGHTER, source=item.source, item=item.source_id)
    raise ConfigError("no_space", "Not enough room to fetch %s: %s free in %s, %s kept in reserve."
                      % (item.title, net.human(free), directory, net.human(reserve)), hint=LIGHTER,
                      source=item.source, item=item.source_id)


def _write_all(fh, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[fh.write(view):]


def _write_failed(item, directory: str, got: int, e: OSError) -> ConfigError:
    if e.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)):
        return ConfigError("no_space", "The disk filled up while fetching %s (%s written to %s)."
                           % (item.title, net.human(got), directory), hint=LIGHTER,
                           source=item.source, item=item.source_id)
    return ConfigError("download_write_failed", "Could not write %s to %s: %s" % (item.title, directory, e),
                       source=item.source, item=item.source_id)


def _download(item, keep_going, progress) -> Prepared:
    resp = _open(item)
    with resp:
        length = resp.headers.get("Content-Length") or ""
        total = int(length) if length.isdigit() else None
        directory = config.video_tmp_dir()
        limits = _limits(directory)
        if total is not None:
            _room(item, directory, limits, 0, total)   # refused before a file exists
        fd, path = tempfile.mkstemp(prefix="v", suffix=EXTENSIONS.get(item.mime, ".bin"), dir=directory)
        got = 0
        try:
            try:
                # unbuffered: every write reaches the disk before the next one is weighed
                with os.fdopen(fd, "wb", buffering=0) as fh:
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
                        if total is not None and got + len(chunk) > total:
                            raise UpstreamError("download_long", "%s sent more than the %s it announced."
                                                % (item.title, net.human(total)),
                                                source=item.source, item=item.source_id)
                        _room(item, directory, limits, got, len(chunk))
                        _write_all(fh, chunk)
                        got += len(chunk)
                        if total:
                            progress(min(1.0, got / total))
            except OSError as e:                 # the disk refused a write; a failed read is UpstreamError above
                raise _write_failed(item, directory, got, e)
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
