"""GoPro cloud: a pasted browser token, the media listing, signed download addresses.

Moved from ``cast-gopro`` with ``die()`` replaced by exceptions (Phase 1); the
``GoProSource`` class puts it on the ``Source`` contract (Phase 4). The module
functions stay as the CLI's building blocks and the source's own.

The token is a five-segment JWE whose expiry cannot be read locally: the only
expiry signal is a 401 from the API, so the source keeps *when it last worked*
and flips to ``expired`` on the first 401 from any call.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse

from castlib import config, net
from castlib.errors import AuthError, ConfigError, NotMedia, UpstreamError
from castlib.items import MediaItem, Upstream
from castlib.media import kind_from_facets, note_hidden_kind, probe_media
from castlib.sources.base import Entry, Listing

API = "https://api.gopro.com"
MEDIA_ACCEPT = "application/vnd.gopro.jk.media+json; version=2.0.0"
TOKEN_NAME = "gopro-token"
# Probed 2026-09-12 (research.md, Phase 4): there is no ``duration`` field; ``source_duration``
# is milliseconds as a string, ``resolution`` is "3360p" / "12000000", the size is in
# ``width``/``height``; ``thumbnail_available`` says whether ``?labels=large`` has a still.
LIST_FIELDS = ("id,filename,captured_at,content_title,file_size,type,width,height,"
               "source_duration,thumbnail_available")
THUMB_LABEL = "large"         # /media/{id}/download?labels=large: a JPEG still of a video
PAGE_SIZE = 100               # entries per /media/search page
HEAVY_MBIT = 60.0             # above this average bitrate the TV is likely to refuse the source
HOW_TO_GET_A_TOKEN = """
The token comes from a logged-in browser and lasts a few hours:

  1. open https://gopro.com/media-library/ and sign in
  2. F12 -> Application -> Storage -> Cookies -> https://gopro.com
  3. copy the value of gp_access_token (it starts with eyJ)
     or: F12 -> Network -> any api.gopro.com request -> Request Headers ->
         the part of "authorization" after "Bearer "
  4. cast-gopro --token eyJhbGc...
"""


# ---------------------------------------------------------------- the token
def token_file() -> str:
    return os.path.join(config.config_dir(), TOKEN_NAME)


def token(explicit=None) -> str:
    if explicit:
        return explicit.strip()
    if os.environ.get("GOPRO_TOKEN"):
        return os.environ["GOPRO_TOKEN"].strip()
    try:
        with open(token_file(), encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        raise AuthError("no_token", "No GoPro token stored." + HOW_TO_GET_A_TOKEN,
                        source="gopro")


def fold_double_paste(value: str) -> tuple[str, bool]:
    """A token pasted twice in a row is two copies glued together; the symmetry shows it."""
    value = value.strip()
    half = len(value) // 2
    if value and len(value) % 2 == 0 and value[:half] == value[half:]:
        return value[:half], True
    return value, False


def save_token(value: str) -> str:
    """Store the token (mode 0600); returns the path. A double paste is folded to one copy."""
    value, doubled = fold_double_paste(value)
    if not value:
        raise ConfigError("bad_token", "Paste the token first.", source="gopro")
    if doubled:
        print("The token was pasted twice - storing one copy.")
    config.write_private(token_file(), value)
    return token_file()


def forget_token() -> None:
    try:
        os.unlink(token_file())
    except FileNotFoundError:
        pass


def stored_at() -> float | None:
    """When the token file was written, or ``None`` (no file, or the token comes from the environment)."""
    if os.environ.get("GOPRO_TOKEN"):
        return None
    try:
        return os.path.getmtime(token_file())
    except OSError:
        return None


def age_text(since: float | None, now: float | None = None) -> str | None:
    """``"token stored 3 h ago"`` for the header line; ``None`` when there is no time to show."""
    if since is None:
        return None
    seconds = max(0.0, (now or time.time()) - since)
    if seconds < 90:
        return "token stored just now"
    if seconds < 3600:
        return "token stored %d min ago" % round(seconds / 60)
    if seconds < 48 * 3600:
        return "token stored %d h ago" % round(seconds / 3600)
    return "token stored %d days ago" % round(seconds / 86400)


# ------------------------------------------------------------------ the API
def api(path: str, tok: str, params: str | None = None) -> dict:
    url = API + path + ("?" + params if params else "")
    status, body, _ = net.fetch(url, headers={
        "Authorization": "Bearer " + tok, "Accept": MEDIA_ACCEPT})
    if status == 401:
        raise AuthError("token_rejected",
                        "GoPro rejected the token (401) - expired or incomplete."
                        + HOW_TO_GET_A_TOKEN, source="gopro")
    if status >= 400:
        raise UpstreamError("gopro_http", "GoPro answered %d:\n%s" % (status, body[:400]),
                            source="gopro")
    try:
        return json.loads(body)
    except ValueError:
        raise UpstreamError("gopro_not_json", "GoPro's answer is not JSON:\n%s" % body[:400],
                            source="gopro")


def search(tok: str, per_page: int, page: int = 1, fields: str = LIST_FIELDS) -> list[dict]:
    """One page of ``/media/search`` as the API returns it (raw entries)."""
    data = api("/media/search", tok, params=(
        "fields=%s&order_by=captured_at&per_page=%d&page=%d" % (fields, per_page, page)))
    media = data.get("_embedded", {}).get("media")
    if media is None:
        raise UpstreamError("gopro_shape",
                            "Unfamiliar answer from GoPro (keys: %s).\n"
                            "Send it over and the parser can be adjusted."
                            % ", ".join(data)[:200], source="gopro")
    return media


def list_media(tok: str, count: int) -> list[dict]:
    """The CLI listing: ``count`` newest entries, cached so ``cast-gopro <n>`` can name one."""
    items = []
    for m in search(tok, count):
        width, height = _resolution(m)
        items.append({
            "id": m.get("id"),
            "name": m.get("content_title") or m.get("filename") or m.get("id"),
            "date": (m.get("captured_at") or "")[:10],
            "kind": m.get("type", ""),
            "size": m.get("file_size"),
            "res": "%dx%d" % (width, height) if width and height else "",
            "duration": _duration_seconds(m),   # so cast-gopro <n> knows a heavy clip too
            "thumb": bool(m.get("thumbnail_available")),
        })
    config.cache_write("gopro-list.json", items)
    return items


def cached_listing():
    return config.cache_read("gopro-list.json")


def pick(what: str) -> dict:
    """The listing entry a number names, or a bare media id."""
    items = cached_listing()
    if what.isdigit() and items and 1 <= int(what) <= len(items):
        return items[int(what) - 1]
    if what.isdigit():
        raise ConfigError("no_listing", "No listing cached - run `cast-gopro` first.",
                          source="gopro")
    return {"id": what, "name": what}


# ------------------------------------------------------------- the variants
def _rank(label):
    """Lower is better. The names come from what the API actually returns."""
    return {"source": 0, "baked_source": 0, "high_res_proxy_mp4": 1, "high": 1, "high_res": 1,
            "mobile": 2, "file": 2, "edit_proxy": 3, "low": 4}.get(
        (label or "").lower(), 5)


IMAGE_TYPES = ("photo", "image", "jpg", "jpeg", "png", "webp")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def _is_image_variant(var: dict) -> bool:
    t = (var.get("type") or "").lower()
    if t in IMAGE_TYPES:
        return True
    if t:
        return False
    path = urllib.parse.urlparse(var.get("url") or "").path.lower()
    return path.endswith(IMAGE_EXTENSIONS)


def download_options(media_id: str, tok: str, labels: str | None = None) -> tuple[dict, list[dict]]:
    """``(_embedded, variants)`` of ``/media/{id}/download``: every variation and file with a url.

    ``labels`` narrows the answer (``?labels=large`` yields a video's still);
    ``sidecar_files`` (gpmf, gpx, mediainfo, zip) are never candidates.
    """
    data = api("/media/%s/download" % media_id, tok, params="labels=" + labels if labels else None)
    emb = data.get("_embedded", {}) or {}
    variants = [dict(v) for v in (emb.get("variations") or []) if v.get("url")]
    for f in emb.get("files") or []:
        if f.get("url"):
            variants.append(dict(f, label=f.get("label") or "file", _file=True))
    if not variants:
        raise UpstreamError("gopro_no_download",
                            "No download address in GoPro's answer (keys: %s).\n"
                            "Send the JSON over and the parser can be adjusted."
                            % (", ".join(emb) or "-"), source="gopro", item=media_id)
    return emb, variants


def library_url(media_id: str, tok: str, quality: str = "auto") -> str:
    """Signed mp4 address for a cloud entry; best quality first."""
    _, variants = download_options(media_id, tok)
    options = []
    for var in variants:
        if var.get("_file"):
            # not the source: for the media tested these were 1280 px proxies
            options.append((_rank("file"), "file", var["url"]))
        elif (var.get("type") or "").lower() in ("mp4", "video", ""):
            options.append((_rank(var.get("label")), var.get("label", "?"), var["url"]))
    if not options:
        raise NotMedia("gopro_no_video", "No video variant for this item.",
                       source="gopro", item=media_id)
    options.sort(key=lambda o: o[0])
    if quality == "proxy":          # a deliberately lighter file
        options = [o for o in options if o[0] > 0] or options
    elif quality == "source":
        options = [o for o in options if o[0] == 0] or options
    for _, label, url in options:
        info = _probe(url)
        if info:
            print("  quality: %s (%s, %s)" % (label, info[1], net.human(info[2])))
            return url
    print("  ! no variant confirmed itself as video, taking the first one")
    return options[0][2]


def photo_url(media_id: str, tok: str, quality: str = "auto") -> str:
    """Signed still address: ``source`` first, then the largest by width; a livephoto yields its still.

    A burst's ``files`` are its frames (``item_number`` 1..n); the ``source``
    variation is the frame the library shows, so ``files`` beyond the first
    are not candidates.
    """
    _, variants = download_options(media_id, tok)
    images = [v for v in variants if _is_image_variant(v)
              and not (v.get("_file") and (v.get("item_number") or 1) > 1)]
    if not images:
        raise NotMedia("gopro_no_still", "No still image variant for this item.",
                       source="gopro", item=media_id)

    def key(v):
        return (0 if (v.get("label") or "").lower() == "source" else 1,
                -int(v.get("width") or 0))
    images.sort(key=key)
    if quality == "proxy" and len(images) > 1:
        images = images[1:]
    for var in images:
        info = _probe(var["url"], kinds=("photo",))   # JPEG/PNG/WebP by type, or octet-stream by extension
        if info and info[0] == "photo":
            return var["url"]
    raise NotMedia("gopro_still_not_image",
                   "GoPro's still addresses did not answer with a JPEG or PNG.",
                   source="gopro", item=media_id)


def _probe(url, kinds=("video",)):
    """The one-byte probe, tolerant of a flaky CDN: a network error counts as "not this one"."""
    try:
        return probe_media(url, kinds=kinds)
    except UpstreamError:
        return None


def share_url(url: str) -> str:
    """Public gopro.com/v/... link - the address sits in JSON on the page."""
    _, html, _ = net.fetch(url)
    found = re.findall(r'https?://[^"\'\\ ]+?\.mp4[^"\'\\ ]*', html)
    # longest first: a signed source link is longer than a thumbnail's
    for candidate in sorted(set(found), key=len, reverse=True):
        candidate = candidate.replace("\\u0026", "&").replace("\\/", "/")
        if _probe(candidate):
            return candidate
    raise NotMedia("no_stream", "No stream found on that page.\n"
                   "Check the link is public (Share -> Copy link).", source="gopro")


# ------------------------------------------------------------ the listing
def _resolution(m: dict) -> tuple[int | None, int | None]:
    w, h = m.get("width"), m.get("height")
    if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
        return w, h
    found = re.match(r"^\s*(\d+)\s*[xX×]\s*(\d+)", str(m.get("resolution") or ""))
    if found:                                  # the CLI's cached "WxH"
        return int(found.group(1)), int(found.group(2))
    return None, None


def _duration_seconds(m: dict) -> float | None:
    """Seconds from ``source_duration`` (milliseconds, as a string); ``None`` for stills and unknowns."""
    d = m.get("source_duration")
    if d is None:
        d = m.get("duration")                  # the CLI's cached value, already in seconds
        return float(d) if isinstance(d, (int, float)) and d > 0 else None
    try:
        ms = float(d)
    except (TypeError, ValueError):
        return None
    return ms / 1000.0 if ms > 0 else None


def has_thumb(m: dict, kind: str) -> bool:
    """Only videos have a lighter still (``large``); a photo's only image is its multi-MB source."""
    return kind == "video" and bool(m.get("thumbnail_available"))


def bitrate_mbit(size, duration) -> float | None:
    if not size or not duration:
        return None
    return size * 8 / duration / 1e6


def entry_for(m: dict, kind: str) -> Entry:
    """The grid tile for a raw listing entry of a known kind."""
    width, height = _resolution(m)
    duration = _duration_seconds(m) if kind == "video" else None
    size = m.get("file_size") if isinstance(m.get("file_size"), int) else None
    warn = variants = None
    mbit = bitrate_mbit(size, duration)
    if mbit is not None and mbit > HEAVY_MBIT:
        warn = "too heavy: %d Mbit/s" % round(mbit)
        variants = [
            {"quality": "proxy", "label": "Proxy", "note": "recommended", "default": True},
            {"quality": "source", "label": "Source", "note": "not recommended, %d Mbit/s" % round(mbit),
             "default": False},
        ]
    return Entry(source="gopro", id=str(m.get("id")),
                 name=m.get("content_title") or m.get("filename") or str(m.get("id")),
                 kind=kind, date=(m.get("captured_at") or "")[:10] or None,
                 width=width, height=height, duration=duration, size=size,
                 thumb="/api/sources/gopro/thumb/%s" % urllib.parse.quote(str(m.get("id")), safe="")
                 if has_thumb(m, kind) else None,
                 warn=warn, variants=variants, mime="video/mp4" if kind == "video" else "image/jpeg")


def is_heavy(entry: Entry) -> bool:
    return bool(entry.variants)


# --------------------------------------------------------------- the source
class GoProSource:
    """The ``Source`` contract over the module: a token gate, a listing, on-demand signed URLs."""

    name = "gopro"

    def __init__(self):
        self._lock = threading.Lock()
        self._raw: dict[str, dict] = {}          # id -> raw listing entry, for resolve() and thumb()
        self._verified_at: float | None = None   # the last call that succeeded with this token
        self._expired_at: float | None = None    # the first 401, until a new token is verified
        self._error: dict | None = None

    # ---------------------------------------------------------- bookkeeping
    def _call(self, fn, *args, **kwargs):
        """Run an API-touching function; a 401 flips the source to ``expired`` before it propagates."""
        try:
            result = fn(*args, **kwargs)
        except AuthError as e:
            with self._lock:
                self._expired_at = time.time()
                self._error = e.as_dict()
            raise
        with self._lock:
            self._verified_at = time.time()
            self._expired_at = None
            self._error = None
        return result

    def _raw_of(self, media_id: str) -> dict | None:
        """The listing entry behind an id: this process's listing, the CLI's cached one, else ``/media/{id}``."""
        with self._lock:
            raw = self._raw.get(media_id)
        if raw is not None:
            return raw
        for cached in cached_listing() or []:
            if cached.get("id") == media_id:
                return {"id": media_id, "content_title": cached.get("name"),
                        "type": cached.get("kind"), "file_size": cached.get("size"),
                        "resolution": cached.get("res"), "duration": cached.get("duration"),
                        "captured_at": cached.get("date"),
                        "thumbnail_available": cached.get("thumb")}
        try:                                       # a bare id (cast-gopro <id>): one lookup
            raw = self._call(api, "/media/%s" % media_id, token())
        except UpstreamError:
            return None                            # 404 and the like: not an item of this library
        if not isinstance(raw, dict) or raw.get("id") != media_id:
            return None
        with self._lock:
            self._raw[media_id] = raw
        return raw

    # ------------------------------------------------------------ contract
    def status(self) -> dict:
        has_token = bool(os.environ.get("GOPRO_TOKEN")) or os.path.exists(token_file())
        if not has_token:
            return {"state": "disconnected", "detail": {"stored": False}}
        since = stored_at()
        with self._lock:
            expired, verified, error = self._expired_at, self._verified_at, self._error
        if expired is not None:
            state = "expired"
        elif verified is not None:
            state = "connected"
        else:
            state = "disconnected"                 # stored but not yet verified this session
        return {"state": state,
                "detail": {"stored": True, "stored_at": since, "verified_at": verified,
                           "age": age_text(since), "error": error}}

    def connect(self, params: dict) -> dict:
        """Verify a pasted token and save it, or verify the stored one.

        A paste is verified *before* it is saved, so a bad paste leaves the
        stored token (and the source's state) exactly as they were.
        """
        pasted = params.get("token") if isinstance(params, dict) else None
        if pasted is not None:
            if not isinstance(pasted, str) or not pasted.strip():
                raise ConfigError("bad_token", "Paste the token first.", source="gopro")
            tok, _ = fold_double_paste(pasted)
            search(tok, 1)                         # a 401 propagates; nothing changes here
            save_token(pasted)
            with self._lock:
                self._verified_at, self._expired_at, self._error = time.time(), None, None
            return self.status()
        self._call(search, token(), 1)
        return self.status()

    def disconnect(self) -> None:
        forget_token()
        with self._lock:
            self._verified_at = self._expired_at = self._error = None
            self._raw.clear()

    def list(self, path=None, page=None) -> Listing:
        if page is None or page == "":
            n = 1
        elif str(page).isdigit() and int(page) >= 1:
            n = int(page)
        else:
            raise ConfigError("bad_page", "Not a page number: %r" % (page,), source="gopro")
        media = self._call(search, token(), PAGE_SIZE, n)
        items = []
        for m in media:
            kind = kind_from_facets("gopro", m)
            if kind is None:
                note_hidden_kind("gopro", m.get("type"))
                continue
            with self._lock:
                self._raw[str(m.get("id"))] = m
            items.append(entry_for(m, kind))
        return Listing(items=items, next=str(n + 1) if len(media) >= PAGE_SIZE else None)

    def resolve(self, source_id: str, quality: str = "auto") -> MediaItem:
        """An unregistered item whose ``resolve`` callable ranks the signed variants on every call."""
        if not isinstance(source_id, str) or not re.match(r"^[A-Za-z0-9_-]{1,64}$", source_id):
            raise NotMedia("bad_id", "Not a GoPro media id.", source="gopro", item=str(source_id)[:64])
        raw = self._raw_of(source_id)
        kind = kind_from_facets("gopro", raw) if raw is not None else None
        if kind is None:
            raise NotMedia("unknown_item", "That item is not in the GoPro listing; list first.",
                           source="gopro", item=source_id)
        entry = entry_for(raw, kind)
        if quality not in ("auto", "source", "proxy"):
            quality = "auto"
        if quality == "auto" and is_heavy(entry):
            quality = "proxy"                      # the source would be refused; the UI shows the choice
        picker = library_url if kind == "video" else photo_url
        source = self

        def fresh() -> Upstream:
            return Upstream(source._call(picker, source_id, token(), quality))

        return MediaItem(kind=kind, title=entry.name,
                         mime="video/mp4" if kind == "video" else "image/jpeg",
                         source="gopro", source_id=source_id, resolve=fresh,
                         size=entry.size, width=entry.width, height=entry.height,
                         duration=entry.duration)

    def thumb(self, source_id: str) -> Upstream | None:
        """A fresh signed address of the video's ``large`` still; ``None`` for photos and unknown ids."""
        raw = self._raw_of(source_id)
        kind = kind_from_facets("gopro", raw) if raw is not None else None
        if kind is None or not has_thumb(raw, kind):
            return None
        _, variants = self._call(download_options, source_id, token(), THUMB_LABEL)
        for v in variants:
            if _is_image_variant(v):
                return Upstream(v["url"])       # the CDN needs no auth; it may say octet-stream
        return None
