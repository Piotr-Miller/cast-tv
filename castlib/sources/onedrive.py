"""OneDrive over Microsoft Graph: device code sign-in, folder browsing, download addresses on open.

The sign-in is the device code flow (``castlib.auth.devicecode``): it works
the same from the laptop and the phone because nothing redirects anywhere.
The refresh token lives in ``config_dir()/onedrive.json`` (mode 0600) and is
good for about 90 days rolling; the access token is refreshed silently a
minute before it expires and once more on a 401. ``@microsoft.graph.downloadUrl``
is pre-authenticated and short-lived (about an hour), so it is resolved when
the media opens and never at listing time - from a plain ``GET /me/drive/items/{id}``,
because Graph omits the annotation as soon as a ``$select`` is present.

The Entra application id is not a secret; the owner's registration ships as
``DEFAULT_CLIENT_ID`` and ``ONEDRIVE_CLIENT_ID`` overrides it. The
registration must allow personal Microsoft accounts and public client flows.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from castlib.auth import devicecode
from castlib.auth.tokens import TokenStore
from castlib.errors import AuthError, ConfigError, NotMedia, UpstreamError
from castlib.items import MediaItem, Upstream
from castlib.media import kind_from_facets, note_hidden_kind
from castlib.sources.base import Entry, Folder, Listing

GRAPH = "https://graph.microsoft.com/v1.0"
TENANT = "consumers"
SCOPES = "Files.Read offline_access User.Read"
DEFAULT_CLIENT_ID = "652b2cf9-87f7-4d48-a6cf-67ed3ad8c9b6"   # the owner's Entra registration (not a secret); ONEDRIVE_CLIENT_ID overrides it
TOKEN_NAME = "onedrive"
PAGE_SIZE = 200
LIST_SELECT = "id,name,size,lastModifiedDateTime,folder,file,image,photo,video"
LIST_EXPAND = "thumbnails($select=medium,large)"
ME_SELECT = "displayName,userPrincipalName"
THUMB_FRESH = 30 * 60           # a listing's thumbnail address is reused this long, then fetched again
HEAVY_MBIT = 60.0               # above this bitrate the TV is likely to refuse the file
CRUMB_HOPS = 32
ID_RE = re.compile(r"^[A-Za-z0-9!_.\-]{1,128}$")
ROOT_CRUMB = {"id": None, "name": "OneDrive"}
HOW_TO_REGISTER = (
    "Register an app once at https://entra.microsoft.com (App registrations -> New): "
    "supported account types including personal Microsoft accounts, platform "
    "\"Mobile and desktop applications\", and Authentication -> Advanced settings -> "
    "\"Allow public client flows\" = Yes. Then start cast-tv with "
    "ONEDRIVE_CLIENT_ID=<Application (client) ID>.")


def client_id() -> str:
    cid = (os.environ.get("ONEDRIVE_CLIENT_ID") or DEFAULT_CLIENT_ID).strip()
    if not cid:
        raise ConfigError("no_client_id", "No Entra application id is configured for OneDrive.",
                          hint=HOW_TO_REGISTER, source="onedrive")
    return cid


# ---------------------------------------------------------------- Graph
class _Unauthorized(Exception):
    """Graph answered 401: the access token is stale; the caller refreshes and retries once."""


def graph_get(url: str, token: str) -> dict:
    """One authenticated GET; the JSON object, ``_Unauthorized`` on 401, ``UpstreamError`` otherwise."""
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, raw = r.status, r.read(8 << 20)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(1 << 20)
    except Exception as e:
        raise UpstreamError("graph_unreachable", "Could not reach OneDrive: %s" % e, source="onedrive")
    if status == 401:
        raise _Unauthorized()
    try:
        data = json.loads(raw.decode("utf-8", "replace")) if raw.strip() else {}
    except ValueError:
        data = None
    if status >= 400:
        detail = ""
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            detail = data["error"].get("message") or data["error"].get("code") or ""
        raise UpstreamError("graph_http", "OneDrive answered %d: %s" % (
            status, detail or raw[:300].decode("utf-8", "replace")), source="onedrive")
    if not isinstance(data, dict):
        raise UpstreamError("graph_not_json", "OneDrive's answer is not JSON.", source="onedrive")
    return data


def _children_url(folder_id: str | None) -> str:
    base = (GRAPH + "/me/drive/root/children" if folder_id is None
            else GRAPH + "/me/drive/items/%s/children" % folder_id)
    return "%s?$select=%s&$expand=%s&$top=%d" % (base, LIST_SELECT, LIST_EXPAND, PAGE_SIZE)


def _item_url(item_id: str) -> str:
    return "%s/me/drive/items/%s?$select=%s,parentReference&$expand=%s" % (
        GRAPH, item_id, LIST_SELECT, LIST_EXPAND)


def _download_url_url(item_id: str) -> str:
    # No ``$select``: live Graph (personal drives, probed 2026-09-12) drops the
    # ``@microsoft.graph.downloadUrl`` annotation whenever any ``$select`` is present,
    # so the whole item document (a few KB) is fetched and the annotation read from it.
    return "%s/me/drive/items/%s" % (GRAPH, item_id)


def _thumbnails_url(item_id: str) -> str:
    return "%s/me/drive/items/%s/thumbnails?$select=medium,large" % (GRAPH, item_id)


# ---------------------------------------------------------------- shapes
def _dims(facet: dict) -> tuple[int | None, int | None]:
    w, h = facet.get("width"), facet.get("height")
    if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
        return w, h
    return None, None


def _duration_seconds(video: dict) -> float | None:
    d = video.get("duration")                 # milliseconds
    if isinstance(d, (int, float)) and not isinstance(d, bool) and d > 0:
        return d / 1000.0
    return None


def bitrate_mbit(video: dict, size, duration) -> float | None:
    b = video.get("bitrate")                  # bits per second
    if isinstance(b, (int, float)) and not isinstance(b, bool) and b > 0:
        return b / 1e6
    if size and duration:
        return size * 8 / duration / 1e6
    return None


def thumb_url(item: dict) -> str | None:
    """The ``large`` (else ``medium``) thumbnail address a Graph item carries, or ``None``."""
    sets = item.get("thumbnails")
    if not isinstance(sets, list) or not sets:
        return None
    first = sets[0] if isinstance(sets[0], dict) else {}
    for size in ("large", "medium"):
        t = first.get(size)
        if isinstance(t, dict) and t.get("url"):
            return str(t["url"])
    return None


def account_line(user: dict | None) -> str | None:
    if not user:
        return None
    name, upn = user.get("displayName"), user.get("userPrincipalName")
    if name and upn and name != upn:
        return "%s (%s)" % (name, upn)
    return name or upn or None


def entry_for(item: dict, kind: str) -> Entry:
    """The grid tile for a Graph driveItem of a known kind."""
    file = item.get("file") or {}
    mime = file.get("mimeType") or None
    size = item.get("size") if isinstance(item.get("size"), int) else None
    width = height = duration = None
    warn = None
    if kind == "video":
        video = item.get("video") or {}
        width, height = _dims(video)
        duration = _duration_seconds(video)
        mbit = bitrate_mbit(video, size, duration)
        if mbit is not None and mbit > HEAVY_MBIT:
            warn = "too heavy: %d Mbit/s" % round(mbit)
    else:
        width, height = _dims(item.get("image") or {})
    taken = (item.get("photo") or {}).get("takenDateTime") or item.get("lastModifiedDateTime") or ""
    item_id = str(item.get("id"))
    return Entry(source="onedrive", id=item_id, name=item.get("name") or item_id, kind=kind,
                 date=taken[:10] or None, width=width, height=height, duration=duration, size=size,
                 thumb="/api/sources/onedrive/thumb/%s" % urllib.parse.quote(item_id, safe="")
                 if thumb_url(item) else None,
                 warn=warn, variants=None,
                 mime=mime or ("video/mp4" if kind == "video" else "image/jpeg"))


def version_of(item: dict) -> str:
    """What the photo cache keys the bytes by: the content changes with the modified time or size."""
    return "%s:%s" % (item.get("lastModifiedDateTime") or "", item.get("size") or "")


# ---------------------------------------------------------------- source
class OneDriveSource:
    """The ``Source`` contract over Graph: a device-code gate, folder listings, on-demand download URLs.

    One credential, one generation counter: a verified sign-in and a
    disconnect bump the generation, every request captures it, and an
    outcome touches the state only while its generation is current (the
    GoPro rules from the Phase 4 review). A refresh that Microsoft rejects
    sets ``expired``; a plain success never restores ``connected`` - only a
    verification (``connect``) or a finished device flow does.
    """

    name = "onedrive"

    def __init__(self):
        self._lock = threading.Lock()
        self._flow_lock = threading.Lock()       # one device flow is started at a time
        self._store = TokenStore(TOKEN_NAME)
        self._gen = 0
        self._flow: dict | None = None           # the device flow in progress, or None
        self._flow_stop: threading.Event | None = None
        self._flow_error: dict | None = None     # why the last flow ended without a token
        self._verified_at: float | None = None
        self._expired_at: float | None = None
        self._error: dict | None = None
        self._raw: dict[str, dict] = {}          # file id -> driveItem as Graph returned it
        self._thumbs: dict[str, tuple[str | None, float]] = {}   # file id -> (large url, when)
        self._parents: dict[str, tuple[str | None, str]] = {}    # folder id -> (parent id, name)

    # ------------------------------------------------------- credential
    def _refresh(self, refresh_token: str) -> dict:
        return devicecode.refresh(client_id(), refresh_token, SCOPES, TENANT)

    def _mark_expired(self, err: AuthError, gen: int) -> None:
        if err.code == "no_token":
            return                               # nothing stored: disconnected, not expired
        with self._lock:
            if gen == self._gen:
                self._expired_at = time.time()
                self._error = err.as_dict()

    def _token(self, force: bool = False) -> tuple[str, int]:
        with self._lock:
            gen = self._gen
        try:
            return self._store.get_access_token(self._refresh, force=force), gen
        except AuthError as e:
            self._mark_expired(e, gen)
            raise

    def _call(self, fn):
        """Run ``fn(access_token)``; a 401 from Graph refreshes the token once and retries."""
        tok, gen = self._token()
        try:
            return fn(tok)
        except _Unauthorized:
            pass
        tok, gen = self._token(force=True)
        try:
            return fn(tok)
        except _Unauthorized:
            err = AuthError("graph_unauthorized",
                            "OneDrive refused the sign-in even after a refresh. Connect again.",
                            source="onedrive")
            self._mark_expired(err, gen)
            raise err

    def _adopt(self, user: dict | None) -> None:
        """A verified credential: new generation, connected, the account remembered."""
        with self._lock:
            self._gen += 1
            self._verified_at, self._expired_at, self._error = time.time(), None, None
            self._flow_error = None
        self._store.set_account(user)

    def _me(self, token: str) -> dict | None:
        data = graph_get(GRAPH + "/me?$select=" + ME_SELECT, token)
        user = {k: data.get(k) for k in ("displayName", "userPrincipalName") if data.get(k)}
        return user or None

    # --------------------------------------------------------- the flow
    def _start_flow(self) -> dict:
        cid = client_id()
        with self._flow_lock:
            with self._lock:
                running = self._flow
            if running is None:
                flow = devicecode.start(cid, SCOPES, TENANT)
                stop = threading.Event()
                record = {"user_code": flow["user_code"], "verification_uri": flow["verification_uri"],
                          "expires_at": time.time() + flow["expires_in"], "message": flow["message"]}
                with self._lock:
                    self._flow, self._flow_stop, self._flow_error = record, stop, None
                    gen = self._gen
                threading.Thread(target=self._wait_for_token, args=(cid, flow, record, stop, gen),
                                 name="onedrive-devicecode", daemon=True).start()
        return dict(self.status(), step="code")

    def _wait_for_token(self, cid: str, flow: dict, record: dict, stop: threading.Event, gen: int) -> None:
        try:
            tokens = devicecode.poll(cid, flow, TENANT, stop)
        except (AuthError, UpstreamError) as e:
            with self._lock:
                if self._gen == gen and self._flow is record:
                    self._flow, self._flow_stop = None, None
                    if e.code != "cancelled":
                        self._flow_error = e.as_dict()
            return
        with self._lock:
            if self._gen != gen or self._flow is not record:
                return                           # disconnected or restarted meanwhile: drop it
            self._store.save(tokens, scope=SCOPES)
            self._flow, self._flow_stop, self._flow_error = None, None, None
            self._gen += 1
            gen = self._gen
            self._verified_at, self._expired_at, self._error = time.time(), None, None
            self._raw.clear()
            self._thumbs.clear()
            self._parents.clear()
        try:
            user = self._me(tokens["access_token"])
        except Exception:
            user = None
        with self._lock:
            if self._gen != gen:
                return
        self._store.set_account(user)

    def _cancel_flow(self) -> None:
        with self._lock:
            stop, self._flow, self._flow_stop = self._flow_stop, None, None
        if stop is not None:
            stop.set()

    # ---------------------------------------------------------- contract
    def status(self) -> dict:
        with self._lock:
            flow, flow_error = self._flow, self._flow_error
            expired, verified, error = self._expired_at, self._verified_at, self._error
        stored = self._store.exists()
        if flow is not None:
            return {"state": "connecting", "detail": {
                "stored": stored, "step": "code", "user_code": flow["user_code"],
                "verification_uri": flow["verification_uri"],
                "expires_in": max(0, int(flow["expires_at"] - time.time())),
                "message": flow["message"]}}
        if not stored:
            detail: dict = {"stored": False}
            if flow_error:
                detail["flow_error"] = flow_error
            return {"state": "disconnected", "detail": detail}
        user = self._store.account()
        if expired is not None:
            state = "expired"
        elif verified is not None:
            state = "connected"
        else:
            state = "disconnected"               # stored but not yet verified in this process
        detail = {"stored": True, "account": account_line(user), "user": user,
                  "verified_at": verified, "error": error}
        if flow_error:
            detail["flow_error"] = flow_error
        return {"state": state, "detail": detail}

    def connect(self, params: dict) -> dict:
        """Verify the stored sign-in, or start a device code flow and return its code.

        ``{}`` with a stored, unexpired credential verifies it against ``/me``
        (refreshing silently); with nothing stored, or after ``expired``, or
        with ``{"fresh": true}``, it starts a new flow and answers
        ``{step: "code", ...}``; ``{"cancel": true}`` ends a running flow.
        """
        params = params if isinstance(params, dict) else {}
        if params.get("cancel"):
            self._cancel_flow()
            return self.status()
        with self._lock:
            running, expired = self._flow is not None, self._expired_at is not None
        if running:
            return dict(self.status(), step="code")   # the same code, not a second flow
        if self._store.exists() and not expired and not params.get("fresh"):
            user = self._call(self._me)
            self._adopt(user)
            return self.status()
        return self._start_flow()

    def disconnect(self) -> None:
        """Forget the sign-in: the file, the account, any flow in progress."""
        self._cancel_flow()
        with self._lock:
            self._gen += 1
            self._verified_at = self._expired_at = self._error = self._flow_error = None
            self._raw.clear()
            self._thumbs.clear()
            self._parents.clear()
            self._store.clear()

    def _folder_id(self, path) -> str | None:
        if path is None or path == "":
            return None
        if not isinstance(path, str) or not ID_RE.match(path):
            raise ConfigError("bad_path", "Not a OneDrive folder id: %r" % (path,), source="onedrive")
        return path

    def list(self, path=None, page=None) -> Listing:
        folder_id = self._folder_id(path)
        if page:
            # a page is Graph's own @odata.nextLink; the bearer goes nowhere else
            if not isinstance(page, str) or not page.startswith(GRAPH + "/"):
                raise ConfigError("bad_page", "Not a OneDrive page link.", source="onedrive")
            url = page
        else:
            url = _children_url(folder_id)
        data = self._call(lambda tok: graph_get(url, tok))
        values = data.get("value")
        if not isinstance(values, list):
            raise UpstreamError("graph_shape", "Unfamiliar answer from OneDrive (keys: %s)."
                                % ", ".join(data)[:200], source="onedrive")
        folders, items = [], []
        now = time.time()
        for item in values:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            item_id = str(item["id"])
            name = item.get("name") or item_id
            if isinstance(item.get("folder"), dict):
                count = item["folder"].get("childCount")
                folders.append(Folder(id=item_id, name=name,
                                      count=count if isinstance(count, int) else None))
                with self._lock:
                    self._parents[item_id] = (folder_id, name)
                continue
            kind = kind_from_facets("onedrive", item)
            if kind is None:
                mime = (item.get("file") or {}).get("mimeType") or ""
                if "image" in item or "photo" in item or mime.startswith("image/"):
                    note_hidden_kind("onedrive", mime or name)   # a still the TV is not sent (GIF, raw)
                continue
            with self._lock:
                self._raw[item_id] = item
                self._thumbs[item_id] = (thumb_url(item), now)
            items.append(entry_for(item, kind))
        nxt = data.get("@odata.nextLink")
        return Listing(items=items, folders=folders,
                       next=nxt if isinstance(nxt, str) and nxt else None,
                       crumbs=self._crumbs(folder_id))

    def _crumbs(self, folder_id: str | None) -> list[dict]:
        """``[{id, name}]`` from the drive root down to ``folder_id``; unknown folders are looked up."""
        crumbs = []
        current = folder_id
        for _ in range(CRUMB_HOPS):
            if current is None:
                break
            with self._lock:
                known = self._parents.get(current)
            if known is None:
                known = self._lookup_folder(current)
                if known is None:
                    break
            parent, name = known
            crumbs.append({"id": current, "name": name})
            current = parent
        crumbs.append(dict(ROOT_CRUMB))
        crumbs.reverse()
        return crumbs

    def _lookup_folder(self, folder_id: str) -> tuple[str | None, str] | None:
        try:
            item = self._call(lambda tok: graph_get(
                "%s/me/drive/items/%s?$select=id,name,parentReference" % (GRAPH, folder_id), tok))
        except UpstreamError:
            return None
        ref = item.get("parentReference") or {}
        parent = None if (ref.get("path") or "/drive/root:") == "/drive/root:" else ref.get("id")
        known = (str(parent) if parent else None, item.get("name") or folder_id)
        with self._lock:
            self._parents[folder_id] = known
        return known

    def _raw_of(self, item_id: str) -> dict | None:
        """The driveItem behind an id: this process's listing, else one ``GET /me/drive/items/{id}``."""
        with self._lock:
            raw = self._raw.get(item_id)
        if raw is not None:
            return raw
        try:
            raw = self._call(lambda tok: graph_get(_item_url(item_id), tok))
        except UpstreamError:
            return None                          # 404 and the like: not an item of this drive
        if not isinstance(raw, dict) or str(raw.get("id")) != item_id:
            return None
        with self._lock:
            self._raw[item_id] = raw
            self._thumbs[item_id] = (thumb_url(raw), time.time())
        return raw

    def resolve(self, source_id: str, quality: str = "auto") -> MediaItem:
        """An unregistered item whose ``resolve`` callable asks Graph for a fresh download address."""
        if not isinstance(source_id, str) or not ID_RE.match(source_id):
            raise NotMedia("bad_id", "Not a OneDrive item id.", source="onedrive",
                           item=str(source_id)[:64])
        raw = self._raw_of(source_id)
        kind = kind_from_facets("onedrive", raw) if raw is not None else None
        if kind is None:
            raise NotMedia("unknown_item", "That item is not a photo or video in this OneDrive.",
                           source="onedrive", item=source_id)
        entry = entry_for(raw, kind)
        source = self
        url = _download_url_url(source_id)

        def fresh() -> Upstream:
            data = source._call(lambda tok: graph_get(url, tok))
            address = data.get("@microsoft.graph.downloadUrl")
            if not address:
                raise UpstreamError("no_download_url", "OneDrive gave no download address for %s."
                                    % entry.name, source="onedrive", item=source_id)
            return Upstream(str(address))        # pre-authenticated: no headers, honours Range

        return MediaItem(kind=kind, title=entry.name, mime=entry.mime, source="onedrive",
                         source_id=source_id, version=version_of(raw), resolve=fresh,
                         size=entry.size, width=entry.width, height=entry.height,
                         duration=entry.duration)

    def thumb(self, source_id: str) -> Upstream | None:
        """The ``large`` thumbnail: the listing's address while it is young, else a fresh one from Graph."""
        if not isinstance(source_id, str) or not ID_RE.match(source_id):
            return None
        if self._raw_of(source_id) is None:
            return None
        with self._lock:
            cached = self._thumbs.get(source_id)
        if cached is not None and time.time() - cached[1] < THUMB_FRESH:
            return Upstream(cached[0]) if cached[0] else None
        data = self._call(lambda tok: graph_get(_thumbnails_url(source_id), tok))
        url = thumb_url({"thumbnails": data.get("value") or []})
        with self._lock:
            self._thumbs[source_id] = (url, time.time())
        return Upstream(url) if url else None
