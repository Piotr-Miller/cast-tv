"""Files the command line handed to this process.

Nothing on disk is browsable from the UI (that is the exposure rule); the
only local items the API can cast are the ones ``cast-tv <files>`` named
when it started, remembered here so the UI can re-cast them or put them in
a show. The source is not listable through ``/api/sources``; its entries
ride on ``/api/status`` as ``session`` under opaque ids, so no filesystem
path leaves the process (plan addendum 2026-09-11).
"""
from __future__ import annotations

import os
import secrets
import threading

from castlib.errors import NotMedia
from castlib.items import MediaItem
from castlib.media import MIME, is_allowed_photo, kind_of_extension
from castlib.sources.base import Entry, Listing


def item_for_path(path: str, title: str | None = None, debug: bool = False) -> MediaItem:
    """A ``MediaItem`` for a local file, or ``NotMedia`` when it is not castable."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise NotMedia("no_such_file", "No such file: %s" % path, source="local", item=path)
    ext = os.path.splitext(path)[1].lower()
    kind = kind_of_extension(ext) or "video"
    if kind == "photo" and not is_allowed_photo(MIME.get(ext)):
        raise NotMedia("photo_not_allowed",
                       "%s is a %s image; the TV is not sent GIF or raw stills."
                       % (os.path.basename(path), ext.lstrip(".").upper()),
                       source="local", item=path)
    return MediaItem(kind=kind, title=title or os.path.splitext(os.path.basename(path))[0],
                     mime=MIME.get(ext, "application/octet-stream"), source="local",
                     source_id=path, path=path, size=os.path.getsize(path), debug=debug)


class LocalSource:
    name = "local"

    def __init__(self):
        self._known: dict[str, MediaItem] = {}
        self._lock = threading.Lock()

    def remember(self, item: MediaItem) -> None:
        """An item the CLI registered; from now on the API may cast it by an opaque ``source_id``.

        The item's ``source_id`` (the path until now) becomes the token, so the
        status, the error ring and the photo cache key all carry the token.
        """
        with self._lock:
            token = secrets.token_urlsafe(9)
            while token in self._known:
                token = secrets.token_urlsafe(9)
            item.source_id = token
            self._known[token] = item

    def entries(self) -> list[Entry]:
        with self._lock:
            items = list(self._known.values())
        return [Entry(source="local", id=i.source_id, name=i.title, kind=i.kind,
                      size=i.size, width=i.width, height=i.height, mime=i.mime)
                for i in items]

    # ---------------------------------------------------------- the contract
    def status(self) -> dict:
        return {"state": "connected", "detail": {"items": len(self._known)}}

    def connect(self, params: dict) -> dict:
        return self.status()

    def disconnect(self) -> None:
        pass

    def list(self, path=None, page=None) -> Listing:
        raise NotMedia("not_listable", "Local files are not browsable from the UI.",
                       source="local")

    def resolve(self, source_id: str, quality: str = "auto") -> MediaItem:
        with self._lock:
            known = self._known.get(source_id)
        if known is None:
            raise NotMedia("unknown_item", "That file was not given to this cast-tv.",
                           source="local", item=source_id)
        try:
            item = item_for_path(known.path, title=known.title, debug=known.debug)
        except NotMedia as e:                # the file went away: say so without the path
            raise NotMedia(e.code, "%s is not castable any more." % known.title,
                           source="local", item=source_id)
        item.source_id = source_id
        return item

    def thumb(self, source_id: str):
        return None
