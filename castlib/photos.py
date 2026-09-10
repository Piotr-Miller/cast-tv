"""Photos are fetched whole, decoded, converted where the TV cannot, and materialised.

A HEIC cannot be converted while streaming and a produced body has no size
up front, which breaks ``Content-Length`` and the HEAD-before-GET this TV
does. So a photo is prepared *before* the TV hears about it: the bytes land
in a per-process temp directory, HEAD and GET are served from that one file,
and the DIDL describes the prepared file, not the source.
"""
from __future__ import annotations

import collections
import io
import os
import tempfile
import threading
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

from castlib import config
from castlib.errors import ConfigError, NotMedia, UpstreamError
from castlib.media import PHOTO_MAX, is_allowed_photo, photo_profile

pillow_heif.register_heif_opener()

CACHE_BYTES = 256 * 1024 * 1024
CACHE_ENTRIES = 200
JPEG_QUALITY = 92
FETCH_LIMIT = 200 * 1024 * 1024
_MIME_OF_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png", "HEIF": "image/heic",
                   "WEBP": "image/webp", "GIF": "image/gif"}


@dataclass(frozen=True)
class Prepared:
    """The file the TV fetches: its MIME, size, dimensions and DLNA profile."""
    path: str
    mime: str
    size: int
    width: int
    height: int
    profile: str


class _Cache:
    """LRU over prepared files, bounded by bytes and entries, evicted on insert.

    A *pinned* entry is one whose item is registered (or about to be): its
    file is never deleted, however the budget looks. Pinned bytes still count,
    so the bound is enforced on the unpinned set, and a process whose whole
    budget is retained keeps preparing rather than refusing - the registry
    releases the pins as items leave.
    """

    def __init__(self, max_bytes=CACHE_BYTES, max_entries=CACHE_ENTRIES):
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._items: collections.OrderedDict = collections.OrderedDict()   # unpinned, LRU
        self._retained: dict = {}          # pinned: key -> Prepared
        self._pins: dict = {}              # key -> count
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            prep = self._retained.get(key)
            if prep is None:
                prep = self._items.get(key)
                if prep is not None:
                    self._items.move_to_end(key)
            if prep is not None and not os.path.exists(prep.path):   # temp dir removed
                self._forget(key, prep)
                return None
            return prep

    def _forget(self, key, prep):
        self._bytes -= prep.size
        self._items.pop(key, None)
        self._retained.pop(key, None)
        self._pins.pop(key, None)

    def _trim(self):
        """Drop unpinned entries, oldest first, until the budget holds. Returns the victims."""
        evicted = []
        while self._items and (self._bytes > self.max_bytes
                               or len(self._items) + len(self._retained) > self.max_entries):
            _, victim = self._items.popitem(last=False)
            self._bytes -= victim.size
            evicted.append(victim)
        return evicted

    def put(self, key, prep: Prepared):
        evicted = []
        with self._lock:
            old = self._retained.get(key) or self._items.get(key)
            if old is not None:
                if old.path == prep.path:
                    if key in self._items:
                        self._items.move_to_end(key)
                    return
                self._bytes -= old.size
                self._items.pop(key, None)
                self._retained.pop(key, None)
                evicted.append(old)
            if self._pins.get(key):
                self._retained[key] = prep
            else:
                self._items[key] = prep
            self._bytes += prep.size
            for victim in self._trim():
                if victim is prep:               # never evict what was just inserted
                    self._items[key] = prep
                    self._bytes += prep.size
                else:
                    evicted.append(victim)
        _unlink_all(evicted)

    def pin(self, key):
        with self._lock:
            self._pins[key] = self._pins.get(key, 0) + 1
            prep = self._items.pop(key, None)
            if prep is not None:
                self._retained[key] = prep

    def unpin(self, key):
        evicted = []
        with self._lock:
            n = self._pins.get(key, 0) - 1
            if n > 0:
                self._pins[key] = n
                return
            self._pins.pop(key, None)
            prep = self._retained.pop(key, None)
            if prep is not None:
                self._items[key] = prep          # back into the LRU, as the newest
                evicted = self._trim()
        _unlink_all(evicted)

    def pinned(self, key) -> bool:
        with self._lock:
            return self._pins.get(key, 0) > 0

    def clear(self):
        with self._lock:
            items = list(self._items.values()) + list(self._retained.values())
            self._items.clear()
            self._retained.clear()
            self._pins.clear()
            self._bytes = 0
        _unlink_all(items)

    @property
    def bytes(self):
        return self._bytes

    def __len__(self):
        return len(self._items) + len(self._retained)


def _unlink_all(preps):
    for prep in preps:
        try:
            os.unlink(prep.path)
        except OSError:
            pass


cache = _Cache()
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="photo")
_pending: dict = {}
_pending_lock = threading.Lock()
_active = 0
_active_peak = 0
_active_lock = threading.Lock()


def cache_key(item) -> tuple:
    version = item.version
    if version is None and item.path:
        try:
            st = os.stat(item.path)
            version = "%d:%d" % (st.st_mtime_ns, st.st_size)
        except OSError:
            version = ""
    return (item.source, item.source_id, version or "")


def _fetch(item) -> bytes:
    if item.path:
        try:
            with open(item.path, "rb") as fh:
                return fh.read(FETCH_LIMIT + 1)
        except OSError as e:
            raise NotMedia("photo_unreadable", "Could not read %s: %s" % (item.path, e),
                           source=item.source, item=item.id or item.source_id)
    if item.resolve is None:
        raise NotMedia("photo_no_source", "No file or address behind %s" % item.title,
                       source=item.source, item=item.id or item.source_id)
    up = item.resolve()
    req = urllib.request.Request(up.url, headers={"User-Agent": "Mozilla/5.0",
                                                   "Accept": "*/*"})
    for name, value in up.headers.items():
        req.add_header(name, value)
    try:
        with (up.opener.open(req, timeout=60) if up.opener is not None
              else urllib.request.urlopen(req, timeout=60)) as resp:
            return resp.read(FETCH_LIMIT + 1)
    except Exception as e:
        raise UpstreamError("photo_fetch_failed", "Could not fetch %s: %s" % (item.title, e),
                            source=item.source, item=item.id or item.source_id)


def _convert(item, data: bytes) -> tuple[bytes, str, int, int]:
    """``(bytes, mime, width, height)``: as fetched when the TV can take it, else a JPEG."""
    if len(data) > FETCH_LIMIT:
        raise NotMedia("photo_too_large", "%s is larger than %d MB" % (
            item.title, FETCH_LIMIT // (1024 * 1024)), source=item.source)
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Image.DecompressionBombError as e:
        raise NotMedia("photo_too_many_pixels", "%s has more pixels than is safe to decode: %s"
                       % (item.title, e), source=item.source, item=item.id or item.source_id)
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise NotMedia("photo_undecodable", "%s is not a photo the TV can show: %s"
                       % (item.title, e), source=item.source, item=item.id or item.source_id)
    fmt = (im.format or "").upper()
    mime = _MIME_OF_FORMAT.get(fmt, "")
    if not is_allowed_photo(mime):
        raise NotMedia("photo_not_allowed", "%s is a %s image, which is not cast"
                       % (item.title, fmt or "unknown"), source=item.source,
                       item=item.id or item.source_id)
    orientation = 1
    try:
        orientation = int(im.getexif().get(0x0112, 1) or 1)
    except Exception:
        pass
    width, height = im.size
    fits = width <= PHOTO_MAX and height <= PHOTO_MAX
    if fmt in ("JPEG", "PNG") and orientation == 1 and fits:
        return data, mime, width, height
    if orientation != 1:
        im = ImageOps.exif_transpose(im)
    if not fits:
        im.thumbnail((PHOTO_MAX, PHOTO_MAX), Image.LANCZOS)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue(), "image/jpeg", im.width, im.height


def _prepare_now(item) -> Prepared:
    global _active, _active_peak
    with _active_lock:
        _active += 1
        _active_peak = max(_active_peak, _active)
    try:
        data, mime, width, height = _convert(item, _fetch(item))
        ext = ".png" if mime == "image/png" else ".jpg"
        path = None
        try:
            directory = config.photo_tmp_dir()
            fd, path = tempfile.mkstemp(prefix="p", suffix=ext, dir=directory)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        except OSError as e:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            raise ConfigError("photo_write_failed", "Could not store the converted %s: %s"
                              % (item.title, e), source=item.source,
                              item=item.id or item.source_id)
        return Prepared(path=path, mime=mime, size=len(data), width=width, height=height,
                        profile=photo_profile(mime, width, height))
    finally:
        with _active_lock:
            _active -= 1


def _submit(item) -> Future:
    key = cache_key(item)
    with _pending_lock:
        fut = _pending.get(key)
        if fut is not None:
            return fut
        fut = _pool.submit(_prepare_now, item)
        _pending[key] = fut

    def done(f, key=key):
        # a finished future runs this inline from add_done_callback, so the
        # lock must not be held by the caller: publish first, then un-pend
        if not f.cancelled() and f.exception() is None:
            cache.put(key, f.result())
        with _pending_lock:
            if _pending.get(key) is f:
                del _pending[key]
    fut.add_done_callback(done)
    return fut


def prepare(item) -> Prepared:
    """Fetch, decode, convert and materialise; sets ``item.prepared`` and returns it.

    The item's own ``mime``, ``size``, ``width`` and ``height`` stay as the
    source reported them. The prepared file is pinned for this item until
    ``release(item)`` - which the registry calls when the item leaves it - so
    cache pressure never deletes a file the TV may still fetch. Raises
    ``NotMedia``, ``UpstreamError`` or ``ConfigError``.
    """
    key = cache_key(item)
    if item.prepared is not None and cache.get(key) is item.prepared:
        return item.prepared             # already prepared and pinned for this item
    cache.pin(key)                       # before the file exists: no window for eviction
    try:
        prep = cache.get(key)
        if prep is None:
            prep = _submit(item).result()
            cache.put(key, prep)
    except BaseException:
        cache.unpin(key)
        raise
    item.prepared = prep
    return prep


def release(item) -> None:
    """The item no longer needs its prepared file; the cache may drop it under pressure."""
    if item.prepared is None:
        return
    cache.unpin(cache_key(item))


def attach(registry) -> None:
    """Let the registry release prepared files as items are removed or evicted."""
    registry.on_remove = release


def prefetch(items) -> None:
    """Schedule preparation without blocking; failures surface when ``prepare`` is called."""
    for item in items:
        if item.kind == "photo" and cache.get(cache_key(item)) is None:
            fut = _submit(item)
            fut.add_done_callback(lambda f: f.exception())   # consume, never raise here


def peak_concurrency() -> int:
    return _active_peak
