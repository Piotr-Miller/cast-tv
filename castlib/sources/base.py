"""The contract every source implements, and the shapes the grid reads.

A source lists ``Entry`` objects, resolves one of them to an unregistered
``MediaItem`` on demand, and may hand back a thumbnail ``Upstream``. Phases
4 to 6 add GoPro, OneDrive and Google Photos on this contract; ``local``
(CLI-registered files) is the only source in Phase 3.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

from castlib.items import MediaItem, Upstream


@dataclass
class Entry:
    """One tile in the grid."""
    source: str
    id: str
    name: str
    kind: str                       # "video" | "photo"
    date: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    size: int | None = None
    thumb: str | None = None        # /api/sources/<name>/thumb/<id>, or None for a placeholder
    warn: str | None = None
    variants: list | None = None
    mime: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Folder:
    id: str
    name: str
    count: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Listing:
    items: list[Entry] = field(default_factory=list)
    folders: list[Folder] = field(default_factory=list)
    next: str | None = None
    crumbs: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"items": [e.as_dict() for e in self.items],
                "folders": [f.as_dict() for f in self.folders],
                "next": self.next, "crumbs": list(self.crumbs)}


class Source(Protocol):
    name: str

    def status(self) -> dict: ...                       # {state, detail}
    def connect(self, **params) -> dict: ...            # status, or a step of a multi-step flow
    def disconnect(self) -> None: ...
    def list(self, path: str | None, page: str | None) -> Listing: ...
    def resolve(self, source_id: str, quality: str = "auto") -> MediaItem: ...
    def thumb(self, source_id: str) -> Upstream | None: ...
