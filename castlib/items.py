"""What the server serves: one ``MediaItem`` shape, registered under an opaque id.

The registry replaces the class attributes the one-shot script kept: several
items coexist, each is published atomically, nothing is replaced under a
running transfer, and removal is explicit (``remove``) or time-based
(``evict``) for items the supervisor has retired.
"""
from __future__ import annotations

import secrets
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Upstream:
    """What a resolver returns: the address to fetch, fresh on every open."""
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    opener: urllib.request.OpenerDirector | None = None


@dataclass
class MediaItem:
    kind: str                 # "video" | "photo" | "audio" | "subtitle"
    title: str
    mime: str
    source: str               # "local" | "link" | "gopro" | "onedrive" | "gphotos"
    source_id: str            # identity within the source; (source, source_id) is unique
    version: str | None = None   # etag or id the source gives the bytes; local files use mtime+size
    path: str | None = None   # local file, or None
    resolve: Callable[[], Upstream] | None = None   # for remote items
    size: int | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    caption: tuple[str, str] | None = None          # (subtitle path, subtitle url)
    debug: bool = False
    id: str = ""              # assigned by the registry
    created: float = 0.0
    last_request: float = 0.0
    requests: int = 0
    in_flight: int = 0        # open media transfers, maintained by the handler
    retired_at: float | None = None   # set when the item leaves playback
    parent: str | None = None         # the video id for a subtitle item
    prepared: Any = None              # Phase 2: the converted photo


class Registry:
    """One dict of items under one lock; ids are opaque and never reused."""

    def __init__(self):
        self._items: dict[str, MediaItem] = {}
        self._lock = threading.Lock()
        self.on_remove: Callable[[MediaItem], None] | None = None   # e.g. photos.release

    def _removed(self, items):
        if self.on_remove is not None:
            for item in items:
                try:
                    self.on_remove(item)
                except Exception:
                    pass

    def add(self, item: MediaItem) -> MediaItem:
        """Assign an id and publish the item atomically; returns the same object."""
        with self._lock:
            new_id = secrets.token_urlsafe(12)
            while new_id in self._items:
                new_id = secrets.token_urlsafe(12)
            now = time.time()
            item.id = new_id
            item.created = now
            item.last_request = now
            self._items[new_id] = item
            return item

    def get(self, item_id: str) -> MediaItem | None:
        with self._lock:
            return self._items.get(item_id)

    def remove(self, item_id: str) -> MediaItem | None:
        with self._lock:
            item = self._items.pop(item_id, None)
        if item is not None:
            self._removed([item])
        return item

    def items(self) -> list[MediaItem]:
        with self._lock:
            return list(self._items.values())

    def retire(self, item_id: str) -> None:
        """The item left playback; it stays served until ``evict`` finds it idle.

        Retiring a video retires its subtitle too.
        """
        now = time.time()
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                return
            item.retired_at = now
            for other in self._items.values():
                if other.parent == item_id:
                    other.retired_at = now

    def evict(self, idle_seconds: float) -> list[MediaItem]:
        """Remove retired items nobody has asked for in ``idle_seconds`` and with no open transfer."""
        now = time.time()
        with self._lock:
            gone = [i for i in self._items.values()
                    if i.retired_at is not None and i.in_flight == 0
                    and now - i.last_request > idle_seconds]
            for i in gone:
                del self._items[i.id]
        self._removed(gone)
        return gone

    def touch(self, item_id: str) -> None:
        with self._lock:
            item = self._items.get(item_id)
            if item is not None:
                item.last_request = time.time()
                item.requests += 1

    def begin(self, item_id: str) -> None:
        with self._lock:
            item = self._items.get(item_id)
            if item is not None:
                item.in_flight += 1

    def end(self, item_id: str) -> None:
        with self._lock:
            item = self._items.get(item_id)
            if item is not None and item.in_flight > 0:
                item.in_flight -= 1
