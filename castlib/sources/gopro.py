"""GoPro cloud: a pasted browser token, the media listing, signed download addresses.

Moved from ``cast-gopro`` with ``die()`` replaced by exceptions (Phase 1); the
``GoProSource`` class puts it on the ``Source`` contract (Phase 4). The module
functions stay as the CLI's building blocks and the source's own.

The token is a five-segment JWE whose expiry cannot be read locally: the only
expiry signal is a 401 from the API, so the source keeps *when it last worked*
and flips to ``expired`` on the first 401 from any call.

Since S-13 the usual way in is the hand-off (``castlib.auth.browser``): a
gopro.com window cast-tv opens on the host, whose session cookie is verified
against the API and stored exactly as a paste is. The source runs it as a
round in the shape of the Google Photos consent - ``connecting`` with
``step: "browser"``, one round at a time, a late result dropped when the
generation moved on. Next to the token, ``gopro-session.json`` keeps what is
known about the session (when and how it was captured, when it last worked,
when it was first refused, the cookie's expiry) and never the token; the first
refusal reports that observed period to Diagnostics through ``report``.
"""
from __future__ import annotations

import json
import os
import re
import textwrap
import threading
import time
import urllib.parse

from castlib import config, net
from castlib.auth import browser
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
SESSION_NAME = "gopro-session"   # + .json: the session's timing fields next to the token, never the token
META_WRITE_EVERY = 60.0       # seconds between sidecar writes for last_success_at (thumbs would rewrite it per request)
META_KEYS = ("captured_at", "captured_by", "cookie", "last_success_at", "first_401_at")
ON_HOST_NOTE = ("The gopro.com window opens on the computer running cast-tv, not on the device "
                "showing this page.")
STANDING_NOTE = ("No publicly documented, self-serve sign-in for third-party applications was found "
                 "(checked 2026-09-20; see README, Limitations).")
# The devtools route, the one source of the steps: the CLI prints them below, the UI's fallback
# block lists them when no gopro.com window can be opened on the host.
TOKEN_STEPS = (
    "open https://gopro.com/media-library/ and sign in",
    "F12 -> Application -> Storage -> Cookies -> https://gopro.com",
    "copy the value of gp_access_token (it starts with eyJ); or: F12 -> Network -> any "
    "api.gopro.com request -> Request Headers -> the part of \"authorization\" after \"Bearer \"",
)


def _numbered(steps) -> str:
    return "\n".join(textwrap.fill(step, width=78, initial_indent="  %d. " % n, subsequent_indent="     ")
                     for n, step in enumerate(steps, 1))


HOW_TO_GET_A_TOKEN = ("\nRun cast-tv, open the GoPro tab and press Open gopro.com. Or, from a signed-in browser:\n\n"
                      + _numbered(TOKEN_STEPS + ("cast-gopro --token eyJhbGc...",)) + "\n\n" + STANDING_NOTE + "\n")


# ---------------------------------------------------------------- the token
def token_file() -> str:
    return os.path.join(config.config_dir(), TOKEN_NAME)


def session_file() -> str:
    return os.path.join(config.config_dir(), SESSION_NAME + ".json")


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


def session_meta(captured_by: str | None, captured_at: float | None = None, cookie: dict | None = None) -> dict:
    """The session's timing fields, every key present: how and when the token was captured, the cookie's
    ``session``/``expires`` (a window capture only), when it last worked, when it was first refused."""
    if isinstance(cookie, dict):
        cookie = {"session": bool(cookie.get("session")), "expires": cookie.get("expires")}
    else:
        cookie = None
    return {"captured_at": captured_at, "captured_by": captured_by, "cookie": cookie,
            "last_success_at": None, "first_401_at": None}


def _token_mtime() -> float | None:
    try:
        return os.path.getmtime(token_file())
    except OSError:
        return None


def write_session(meta: dict) -> None:
    """Persist ``meta`` next to the token (mode 0600, atomic), stamped with the token file's mtime.

    The stamp is what ties the sidecar to *this* token: a token file replaced
    outside cast-tv has another mtime, and ``read_session`` then ignores the
    sidecar rather than describe a session it knows nothing about. Nothing
    here is secret; the token never enters the file.
    """
    data = {k: meta.get(k) for k in META_KEYS}
    data["token_mtime"] = _token_mtime()
    config.write_private(session_file(), json.dumps(data))


def read_session() -> dict | None:
    """The sidecar's fields, or ``None`` when there is none or it belongs to another token file."""
    try:
        with open(session_file(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    mtime = _token_mtime()
    if not isinstance(data, dict) or mtime is None or data.get("token_mtime") != mtime:
        return None
    meta = session_meta(data.get("captured_by"), data.get("captured_at"), data.get("cookie"))
    meta["last_success_at"], meta["first_401_at"] = data.get("last_success_at"), data.get("first_401_at")
    return meta


def store_token(value: str, meta: dict | None = None) -> str:
    """Write the token (mode 0600) and its session metadata; returns the path. ``meta`` defaults to a paste made now."""
    config.write_private(token_file(), value)
    write_session(meta if meta is not None else session_meta("paste", time.time()))
    return token_file()


def save_token(value: str, meta: dict | None = None) -> str:
    """Store a pasted token (mode 0600); returns the path. A double paste is folded to one copy."""
    value, doubled = fold_double_paste(value)
    if not value:
        raise ConfigError("bad_token", "Paste the token first.", source="gopro")
    if doubled:
        print("The token was pasted twice - storing one copy.")
    return store_token(value, meta)


def forget_token() -> None:
    """Remove the token file and its sidecar; nothing to do when they are absent."""
    for path in (token_file(), session_file()):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def stored_at() -> float | None:
    """When the token file was written, or ``None`` (no file, or the token comes from the environment)."""
    if os.environ.get("GOPRO_TOKEN"):
        return None
    return _token_mtime()


def age_text(since: float | None, now: float | None = None, what: str = "token stored") -> str | None:
    """``"token stored 3 h ago"`` / ``"session captured 3 h ago"`` for the header line; ``None`` with no time to show."""
    if since is None:
        return None
    seconds = max(0.0, (now or time.time()) - since)
    if seconds < 90:
        return "%s just now" % what
    if seconds < 3600:
        return "%s %d min ago" % (what, round(seconds / 60))
    if seconds < 48 * 3600:
        return "%s %d h ago" % (what, round(seconds / 3600))
    return "%s %d days ago" % (what, round(seconds / 86400))


def _stamp(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def _span(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return "%d day%s %d h" % (days, "" if days == 1 else "s", hours)
    if hours:
        return "%d h %d min" % (hours, minutes)
    if minutes:
        return "%d min" % minutes
    return "%d s" % seconds


def observed_period(meta: dict, stored_at: float | None = None, now: float | None = None) -> str:
    """The first refusal's Diagnostics text: what was observed, never a lifetime.

    "Session captured 2026-09-21 20:10. Worked for at least 6 h 12 min (last
    successful call). First refusal 9 h 40 min after capture. Cookie expires:
    2026-10-21 12:00 (persistent)." A token with no success on record says so;
    a session cookie says so; a paste says "Token pasted"; a token file with no
    sidecar dates itself by its mtime.
    """
    now = now or time.time()
    by = meta.get("captured_by") or "unknown"
    captured = meta.get("captured_at") or (stored_at if by == "unknown" else None)
    lead = {"window": "Session captured", "paste": "Token pasted",
            "env": "Token from GOPRO_TOKEN since"}.get(by, "Token stored")
    parts = ["%s %s." % (lead, _stamp(captured)) if captured else "Capture time unknown."]
    last = meta.get("last_success_at")
    if last and captured:
        parts.append("Worked for at least %s (last successful call)." % _span(last - captured))
    elif last:
        parts.append("Last successful call %s." % _stamp(last))
    else:
        parts.append("No successful call recorded.")
    first = meta.get("first_401_at") or now
    if captured:
        parts.append("First refusal %s after capture." % _span(first - captured))
    else:
        parts.append("First refusal %s." % _stamp(first))
    cookie = meta.get("cookie")
    if isinstance(cookie, dict):
        expires = cookie.get("expires")
        if cookie.get("session"):
            parts.append("Session cookie (no expiry set).")
        elif isinstance(expires, (int, float)) and not isinstance(expires, bool) and expires > 0:
            parts.append("Cookie expires: %s (persistent)." % _stamp(expires))
    return " ".join(parts)


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
    """The ``Source`` contract over the module: a token gate, a listing, on-demand signed URLs.

    The source owns **one session credential**: read once from ``GOPRO_TOKEN``
    or the token file on first use, replaced by a verified paste, cleared by
    ``disconnect()`` (which never falls back to the environment again in this
    process; a new process may still start from ``GOPRO_TOKEN``). Every
    request captures the credential *and its generation* together; a verified
    connection and a disconnect bump the generation, and a request's outcome
    touches the state only while its generation is still current. A 401 sets
    ``expired``; a plain list/thumb/resolve success never restores
    ``connected`` - only a successful verification does (p4 review F1, F2).

    The hand-off is a **round** (``_flow``): ``connect()`` starts one when
    nothing is stored, after ``expired``, or on ``{"fresh": true}``; a second
    ``connect({})`` meanwhile answers the same round, ``{"cancel": true}`` ends
    it. The round's ``Handoff`` verifies each cookie value through ``_verify``
    (``search(tok, 1)``; a 401 is a stale value, not an expiry of the session),
    and its result is adopted under the lock only while the generation it
    started with is current - a disconnect, a paste or ``close()`` in between
    drops it, the window being closed already. ``no_browser`` and
    ``browser_failed`` set ``_fallback`` (the paste's cue for the UI); a closed
    window, a timeout or a cancel only end the round.

    The session's timing fields (``_meta``) mirror ``gopro-session.json``: a
    success moves ``last_success_at`` (written at most once a minute), the
    first 401 stamps ``first_401_at``, writes at once and reports the observed
    period through ``report`` - once per transition to ``expired``, never per
    thumbnail. ``GOPRO_TOKEN`` keeps them in memory only.
    """

    name = "gopro"

    def __init__(self):
        self._lock = threading.Lock()
        self._raw: dict[str, dict] = {}          # id -> raw listing entry, for resolve() and thumb()
        self._token: str | None = None           # the session credential
        self._from_env = False                   # it came from GOPRO_TOKEN (no file age to show)
        self._loaded = False                     # the first lookup happened (disconnect sets it too)
        self._gen = 0                            # bumped by a verified connection and by disconnect
        self._verified_at: float | None = None   # when the session credential was last verified
        self._expired_at: float | None = None    # the first 401 on it, until a new one is verified
        self._error: dict | None = None
        self._flow: dict | None = None           # the round in progress: {started_at, expires_at, handoff, gen}
        self._flow_error: dict | None = None     # how the last round ended, until the next one starts
        self._fallback: dict | None = None       # {reason, steps}: no window can open here; the paste applies
        self._meta: dict = session_meta(None)    # the session's timing fields (see session_meta)
        self._meta_written: float | None = None  # monotonic time of the last throttled sidecar write
        self._started = time.time()              # what GOPRO_TOKEN's "captured_at" reads
        self._closed = False                     # close() is final: no round starts after it
        self.report = None                       # set by the App to errors.push: the first refusal lands in Diagnostics

    # ---------------------------------------------------------- bookkeeping
    def _credential(self) -> tuple[str | None, int]:
        """``(token, generation)`` of the session; the first call reads the environment or the file, and the sidecar."""
        with self._lock:
            if not self._loaded:
                self._loaded = True
                self._from_env = bool(os.environ.get("GOPRO_TOKEN"))
                try:
                    self._token = token()
                except AuthError:
                    self._token = None
                self._meta = self._load_meta()
            return self._token, self._gen

    def _load_meta(self) -> dict:
        """The timing fields for the credential just read (caller holds ``_lock``)."""
        if self._token is None:
            return session_meta(None)
        if self._from_env:
            return session_meta("env", self._started)
        return read_session() or session_meta("unknown")   # no sidecar, or one of another token file

    def _stored_at(self) -> float | None:
        return None if self._from_env else _token_mtime()

    def _no_token(self) -> AuthError:
        return AuthError("no_token", "No GoPro token stored." + HOW_TO_GET_A_TOKEN, source="gopro")

    def _check_open(self) -> None:
        """Raise once ``close()`` has run (caller holds ``_lock``): a closed source starts nothing new."""
        if self._closed:
            raise ConfigError("source_closed", "GoPro is shutting down.", source="gopro")

    def _call(self, fn):
        """Run ``fn(token)`` with the session credential.

        A 401 marks the source ``expired`` - but only if no verified connection
        or disconnect happened since the request captured its credential, so a
        stale answer cannot undo a recovery. A success moves
        ``last_success_at`` under the same rule and restores nothing else.
        """
        tok, gen = self._credential()
        if tok is None:
            raise self._no_token()
        try:
            result = fn(tok)
        except AuthError as e:
            self._refused(e, gen)
            raise
        self._succeeded(gen)
        return result

    def _succeeded(self, gen: int) -> None:
        with self._lock:
            if gen != self._gen:
                return
            self._meta["last_success_at"] = time.time()
            if self._from_env:
                return
            mono = time.monotonic()
            if self._meta_written is None or mono - self._meta_written >= META_WRITE_EVERY:
                self._meta_written = mono
                self._write_meta()

    def _refused(self, e: AuthError, gen: int) -> None:
        """A 401 on the session credential: ``expired``, the observed period as the error's hint, one report."""
        report = None
        with self._lock:
            if gen != self._gen:
                return
            now = time.time()
            first = self._expired_at is None
            self._expired_at = now
            if self._meta.get("first_401_at") is None:
                self._meta["first_401_at"] = now
            e.hint = observed_period(self._meta, self._stored_at(), now)
            self._error = e.as_dict()
            if first:
                if not self._from_env:
                    self._meta_written = time.monotonic()
                    self._write_meta()
                report = self.report
        if report is not None:
            try:
                report(e)
            except Exception:
                pass

    def _write_meta(self) -> None:
        """The sidecar (caller holds ``_lock``); a read-only config dir loses nothing but the record."""
        try:
            write_session(self._meta)
        except OSError:
            pass

    def _adopt_locked(self, tok: str, from_env: bool, meta: dict | None) -> None:
        """A verified credential becomes the session's: new generation, connected (caller holds ``_lock``)."""
        self._token, self._from_env, self._loaded = tok, from_env, True
        self._gen += 1
        self._verified_at, self._expired_at, self._error = time.time(), None, None
        self._flow_error = self._fallback = None
        if meta is not None:                     # a new capture; a re-verified token keeps its history
            self._meta, self._meta_written = meta, None

    # ----------------------------------------------------------- the round
    def _start_flow(self) -> dict:
        with self._lock:
            self._check_open()
            if self._flow is None:
                handoff = browser.Handoff()
                now = time.time()
                record = {"started_at": now, "expires_at": now + browser.HANDOFF_TIMEOUT,
                          "handoff": handoff, "gen": self._gen}
                self._flow, self._flow_error = record, None
                handoff.start(self._verify, timeout=browser.HANDOFF_TIMEOUT)   # returns at once; its own thread
                threading.Thread(target=self._finish_flow, args=(record,),
                                 name="gopro-handoff", daemon=True).start()
        return dict(self.status(), step="browser")

    def _verify(self, tok: str) -> bool:
        """The hand-off's proof: ``search(tok, 1)`` answers 200.

        A 401 is ``False`` (a stale value in the profile; the engine waits for
        the next one). Anything else propagates, and the engine tries the value
        again on its next poll. Nothing here touches the session's state.
        """
        try:
            search(tok, 1)
        except AuthError:
            return False
        return True

    def _finish_flow(self, record: dict) -> None:
        handoff, gen = record["handoff"], record["gen"]
        try:
            result = handoff.wait()
        except AuthError as e:
            self._end_flow(record, e)
            return
        except Exception as e:                   # the thread must not die with the gate still waiting
            self._end_flow(record, AuthError("browser_failed", "The gopro.com window failed: %s" % e,
                                             source="gopro"))
            return
        value = result.get("token") if isinstance(result, dict) else None
        if not isinstance(value, str) or not value:
            self._end_flow(record, AuthError("browser_failed", "The gopro.com window yielded no session.",
                                             source="gopro"))
            return
        meta = session_meta("window", result.get("captured_at") or time.time(), result.get("cookie"))
        with self._lock:
            if self._gen != gen or self._flow is not record:
                return                           # disconnected or replaced meanwhile: dropped; the window is closed
            try:
                store_token(value, meta)
            except OSError as e:
                self._flow = None
                self._flow_error = ConfigError("token_unwritable", "Could not store the GoPro session: %s" % e,
                                               source="gopro").as_dict()
                return
            self._flow = None
            self._adopt_locked(value, False, meta)

    def _end_flow(self, record: dict, err: AuthError) -> None:
        with self._lock:
            if self._flow is not record:
                return                           # cancelled, disconnected or closed: already detached
            self._flow = None
            self._flow_error = err.as_dict()
            if err.code in ("no_browser", "browser_failed"):
                self._fallback = {"reason": err.message, "steps": list(TOKEN_STEPS)}

    def _cancel_flow(self) -> None:
        with self._lock:
            record, self._flow = self._flow, None
        if record is not None:
            record["handoff"].cancel()           # closes the window; a no-op when the round already ended

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
            raw = self._call(lambda tok: api("/media/%s" % media_id, tok))
        except UpstreamError:
            return None                            # 404 and the like: not an item of this library
        if not isinstance(raw, dict) or raw.get("id") != media_id:
            return None
        with self._lock:
            self._raw[media_id] = raw
        return raw

    # ------------------------------------------------------------ contract
    def status(self) -> dict:
        tok, _ = self._credential()
        with self._lock:
            flow, flow_error, fallback = self._flow, self._flow_error, self._fallback
            expired, verified, error, from_env = (self._expired_at, self._verified_at,
                                                  self._error, self._from_env)
            meta = dict(self._meta)
        if flow is not None:
            return {"state": "connecting", "detail": {
                "stored": tok is not None, "step": "browser",
                "expires_in": max(0, int(flow["expires_at"] - time.time())), "note": ON_HOST_NOTE}}
        if tok is None:
            detail: dict = {"stored": False}
            if flow_error:
                detail["flow_error"] = flow_error
            if fallback:
                detail["fallback"] = fallback
            return {"state": "disconnected", "detail": detail}
        since = None if from_env else _token_mtime()
        if expired is not None:
            state = "expired"
        elif verified is not None:
            state = "connected"
        else:
            state = "disconnected"                 # stored but not yet verified this session
        detail = {"stored": True, "stored_at": since, "verified_at": verified,
                  "age": self._age(meta, since), "error": error,
                  "captured_at": meta["captured_at"], "captured_by": meta["captured_by"],
                  "last_success_at": meta["last_success_at"], "first_401_at": meta["first_401_at"],
                  "cookie": meta["cookie"]}
        if flow_error:
            detail["flow_error"] = flow_error
        if fallback:
            detail["fallback"] = fallback
        return {"state": state, "detail": detail}

    @staticmethod
    def _age(meta: dict, since: float | None) -> str | None:
        """The header line: "session captured N ago" for a window capture, "token stored N ago" otherwise."""
        by = meta.get("captured_by")
        if by == "window":
            return age_text(meta.get("captured_at"), what="session captured")
        if by == "env":
            return None
        if by == "paste":
            return age_text(meta.get("captured_at") or since)
        return age_text(since)

    def connect(self, params: dict) -> dict:
        """Verify a pasted token and save it, verify the stored one, or run the hand-off.

        ``{"token": ...}`` is the paste, verified *before* it is saved, so a
        bad paste leaves the stored token (and the source's state) exactly as
        they were; a disconnect, a newer paste or ``close()`` landing during
        the verification wins, and the paste is dropped. ``{}`` with a
        stored, unexpired token verifies it without a window (under the same
        rule); with nothing stored, or after ``expired``, or with
        ``{"fresh": true}``, it starts a round and answers ``{step:
        "browser", ...}``; while a round runs, ``{}`` answers that round.
        ``{"cancel": true}`` ends a running round.
        """
        params = params if isinstance(params, dict) else {}
        pasted = params.get("token")
        if pasted is not None:
            if not isinstance(pasted, str) or not pasted.strip():
                raise ConfigError("bad_token", "Paste the token first.", source="gopro")
            tok, _ = fold_double_paste(pasted)
            with self._lock:
                self._check_open()
                gen = self._gen
            search(tok, 1)                         # a 401 propagates; nothing changes here
            meta = session_meta("paste", time.time())
            record = None
            with self._lock:
                self._check_open()                 # closed meanwhile: nothing is adopted after close()
                if self._gen == gen:               # else disconnected or replaced meanwhile: the later action stands
                    save_token(pasted, meta)
                    self._adopt_locked(tok, False, meta)   # from now on every request uses the paste
                    record, self._flow = self._flow, None  # a window still open has nothing left to hand over
            if record is not None:
                record["handoff"].cancel()
            return self.status()
        if params.get("cancel"):
            self._cancel_flow()
            return self.status()
        tok, gen = self._credential()
        with self._lock:
            self._check_open()
            running, expired = self._flow is not None, self._expired_at is not None
        if running:
            return dict(self.status(), step="browser")   # the same round, not a second window
        if tok is not None and not expired and not params.get("fresh"):
            try:
                search(tok, 1)                     # the stored token, proven without a window
            except AuthError as e:
                self._refused(e, gen)
                raise
            with self._lock:
                if self._gen == gen:               # else disconnected or replaced meanwhile: the later action stands
                    self._adopt_locked(tok, self._from_env, None)
            return self.status()
        return self._start_flow()

    def disconnect(self) -> None:
        """Forget the session: the credential, the file and its sidecar, the browser profile, any round in progress.

        This process never reads GOPRO_TOKEN again. The round is cancelled
        (its window closed) before the profile is removed, so the browser is
        never writing into a directory that is going away.
        """
        with self._lock:
            record, self._flow = self._flow, None
            self._token, self._from_env, self._loaded = None, False, True
            self._gen += 1
            self._verified_at = self._expired_at = self._error = None
            self._flow_error = self._fallback = None
            self._meta, self._meta_written = session_meta(None), None
            self._raw.clear()
            forget_token()                       # under the lock: a paste adopted after this cannot lose its file
        if record is not None:
            record["handoff"].cancel()
        browser.remove_profile()

    def close(self) -> None:
        """Process exit: a round in progress is cancelled, so Ctrl+C closes the window it opened. Final."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            record, self._flow = self._flow, None
            self._gen += 1                       # a capture landing after this is dropped
        if record is not None:
            record["handoff"].cancel()

    def list(self, path=None, page=None) -> Listing:
        if page is None or page == "":
            n = 1
        elif str(page).isdigit() and int(page) >= 1:
            n = int(page)
        else:
            raise ConfigError("bad_page", "Not a page number: %r" % (page,), source="gopro")
        media = self._call(lambda tok: search(tok, PAGE_SIZE, n))
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
            return Upstream(source._call(lambda tok: picker(source_id, tok, quality)))

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
        _, variants = self._call(lambda tok: download_options(source_id, tok, THUMB_LABEL))
        for v in variants:
            if _is_image_variant(v):
                return Upstream(v["url"])       # the CDN needs no auth; it may say octet-stream
        return None
