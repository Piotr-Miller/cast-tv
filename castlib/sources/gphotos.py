"""Google Photos over the Picker API: consent once on the host, then the user picks, we list the pick.

Google Photos cannot be browsed: since 31 March 2025 the Library API only
exposes items the user picked, and the Picker API is how they pick - in
Google's own UI, on any device, multi-select. So the tab is "connect, then
pick": ``connect()`` runs the desktop loopback flow (``castlib.auth.loopback``)
once, in a browser on this machine, and keeps the refresh token in
``config_dir()/google.json``; ``pick()`` opens a Picker session whose
``pickerUri`` can be opened on the phone, a thread polls it until the pick is
made, and the picked items become the grid. The picks live for this process
only; sessions are deleted on disconnect and at exit.

Every ``baseUrl`` needs ``Authorization: Bearer`` and dies after about an hour
(spike, 2026-09-09: 206 with the header, 403 without), so every byte goes
through the host. Photos are fetched whole, and so is a video's original: its
host ignores Range (probed 2026-09-13), so it is downloaded before the TV hears
of it (``castlib.downloads``); Google's 1080p stream (``=m37``) honours Range and
is relayed. An address older than 50 min, or one the CDN refused, is re-listed
through a session that still contains the item. The share-link scraper (``sharelink``) stays reachable from the
same tab for links from other people's libraries.
"""
from __future__ import annotations

import atexit
import collections
import datetime
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from castlib.auth import loopback
from castlib.auth.tokens import REFRESH_MARGIN, TokenStore
from castlib.errors import AuthError, ConfigError, NotMedia, UpstreamError
from castlib.items import MediaItem, Upstream
from castlib.media import kind_from_facets, note_hidden_kind
from castlib.net import NO_REDIRECT
from castlib.sources import sharelink
from castlib.sources.base import Entry, Listing

PICKER = "https://photospicker.googleapis.com/v1"
SCOPES = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
TOKEN_NAME = "google"
PAGE_SIZE = 100
BASEURL_FRESH = 50 * 60         # a baseUrl is reused this long (Google's expire after 60 min), then re-listed
DEFAULT_POLL = 5.0
DEFAULT_PICK_TIMEOUT = 1800.0
CLEANUP_BUDGET = 5.0            # seconds disconnect() and close() wait for the remote DELETEs, all together
THUMB_SUFFIX = "=w400-h400"
STREAM_SUFFIX = "=m37"          # Google's transcode: 1920x1080 H.264, ~2.5 Mbit/s, honours Range (probed 2026-09-13)
LINK_PREFIX = "link-"
ID_RE = re.compile(r"[A-Za-z0-9_\-]{1,512}")   # a Picker media id, checked with fullmatch()
ON_HOST_NOTE = ("The consent page must be opened on the computer running cast-tv: Google sends "
                "the browser back to that machine's own address (127.0.0.1) and nowhere else.")


def good_id(value) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def _when(text) -> float | None:
    """An RFC 3339 timestamp (``2026-09-13T10:00:00Z``, fractional seconds allowed) as epoch seconds."""
    if not isinstance(text, str) or not text:
        return None
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    m = re.match(r"^(.*?)(\.\d+)?([+-]\d\d:\d\d)$", t)
    if m and m.group(2):
        t = m.group(1) + (m.group(2) + "000000")[:7] + m.group(3)   # at most six fractional digits
    try:
        return datetime.datetime.fromisoformat(t).timestamp()
    except ValueError:
        return None


def _seconds(text, default: float) -> float:
    """A protobuf Duration in JSON (``"5s"``, ``"1800.5s"``) as seconds."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text) if text > 0 else default
    if isinstance(text, str) and text.endswith("s"):
        try:
            value = float(text[:-1])
        except ValueError:
            return default
        return value if value > 0 else default
    return default


# ---------------------------------------------------------------- Picker API
class _Unauthorized(Exception):
    """The Picker answered 401: the access token is stale; the caller refreshes and retries once."""


def picker_call(method: str, path: str, token: str, body: dict | None = None, timeout: float = 30) -> dict:
    """One authenticated call; the JSON object, ``_Unauthorized`` on 401, ``UpstreamError`` otherwise."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(PICKER + path, data=data, method=method, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json",
        **({"Content-Type": "application/json"} if data is not None else {})})
    try:
        with NO_REDIRECT.open(req, timeout=timeout) as r:   # a 3xx would carry the bearer elsewhere
            status, raw = r.status, r.read(8 << 20)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(1 << 20)
    except Exception as e:
        raise UpstreamError("picker_unreachable", "Could not reach Google Photos: %s" % e, source="gphotos")
    if status == 401:
        raise _Unauthorized()
    try:
        parsed = json.loads(raw.decode("utf-8", "replace")) if raw.strip() else {}
    except ValueError:
        parsed = None
    if status >= 300:
        err = parsed.get("error") if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict) else {}
        reason = str(err.get("status") or "")
        detail = err.get("message") or reason or raw[:300].decode("utf-8", "replace")
        if status == 404:
            raise UpstreamError("picker_not_found", "Google Photos knows no such session (%s)." % detail,
                                source="gphotos")
        if status == 429 or reason == "RESOURCE_EXHAUSTED":
            raise UpstreamError("picker_exhausted",
                                "Google Photos refused to open another picker session (%s)." % detail,
                                hint="Too many sessions are open; disconnect and connect again, "
                                     "or wait a while.", source="gphotos")
        if status == 403:
            raise UpstreamError("picker_forbidden", "Google Photos refused the request: %s" % detail,
                                hint="Check that the Photos Picker API is enabled on the Cloud project "
                                     "and that the consent granted the picker scope.", source="gphotos")
        raise UpstreamError("picker_http", "Google Photos answered %d: %s" % (status, detail), source="gphotos")
    if not isinstance(parsed, dict):
        raise UpstreamError("picker_not_json", "Google Photos' answer is not JSON.", source="gphotos")
    return parsed


# ---------------------------------------------------------------- shapes
def _media_file(item: dict) -> dict:
    mf = item.get("mediaFile")
    return mf if isinstance(mf, dict) else {}


def _dims(item: dict) -> tuple[int | None, int | None]:
    meta = _media_file(item).get("mediaFileMetadata")
    meta = meta if isinstance(meta, dict) else {}
    w, h = meta.get("width"), meta.get("height")
    try:
        w, h = int(w), int(h)                 # the reference types them as int32; the wire may carry strings
    except (TypeError, ValueError):
        return None, None
    return (w, h) if w > 0 and h > 0 else (None, None)


def _duration(item: dict) -> float | None:
    meta = _media_file(item).get("mediaFileMetadata")
    video = (meta or {}).get("videoMetadata") if isinstance(meta, dict) else None
    if not isinstance(video, dict):
        return None
    for key in ("duration", "durationMillis"):
        v = video.get(key)
        if v is None:
            continue
        if key == "durationMillis":
            try:
                ms = float(v)
            except (TypeError, ValueError):
                continue
            return ms / 1000.0 if ms > 0 else None
        return _seconds(v, 0.0) or None
    return None


def entry_for(item: dict, kind: str, sessions_left: bool) -> Entry:
    """The grid tile for a picked item of a known kind."""
    mf = _media_file(item)
    media_id = str(item.get("id"))
    width, height = _dims(item)
    mime = mf.get("mimeType") or ("video/mp4" if kind == "video" else "image/jpeg")
    created = item.get("createTime") or ""
    variants = None
    if kind == "video":
        dims = "%dx%d, " % (width, height) if width and height else ""
        variants = [
            {"quality": "original", "label": "Original", "note": dims + "downloads first", "default": True},
            {"quality": "stream", "label": "1080p stream", "note": "starts at once, lighter", "default": False},
        ]
    return Entry(source="gphotos", id=media_id, name=mf.get("filename") or media_id, kind=kind,
                 date=created[:10] or None, width=width, height=height,
                 duration=_duration(item) if kind == "video" else None, size=None,
                 thumb="/api/sources/gphotos/thumb/%s" % urllib.parse.quote(media_id, safe="")
                 if mf.get("baseUrl") else None,
                 warn=None if sessions_left else "re-pick", variants=variants, mime=mime)


# ---------------------------------------------------------------- source
class GPhotosSource:
    """The ``Source`` contract over the Picker: a consent gate, picks as the listing, Bearer on every byte.

    One credential, one generation counter, as in the GoPro and OneDrive
    sources: a finished consent and a disconnect bump the generation, every
    thread captures it, and an outcome touches the state only while its
    generation is current. A refresh Google rejects sets ``expired``; a plain
    success never restores ``connected`` - only a verification does.

    ``disconnect()`` and ``close()`` first take everything out under the lock -
    the generation moves on, the flow, the waiting pick and every session are
    detached, and ``close()`` marks the source closed for good - and only then,
    outside it, cancel the flow and delete the remote sessions against one
    deadline. A consent or a picker session that finishes opening after that
    finds its generation gone and is cancelled or deleted, never published.
    """

    name = "gphotos"

    def __init__(self):
        self._lock = threading.Lock()
        self._flow_lock = threading.Lock()       # one consent flow is started at a time
        self._store = TokenStore(TOKEN_NAME)
        self._gen = 0
        self.open_browser = True                 # the app's --no-browser turns this off
        self._client: dict | None = None
        self._flow: dict | None = None           # the consent in progress: {auth_url, expires_at, attempt, flow}
        self._flow_error: dict | None = None
        self._verified_at: float | None = None
        self._expired_at: float | None = None
        self._error: dict | None = None
        self._picks: collections.OrderedDict[str, dict] = collections.OrderedDict()   # media id -> {raw, sessions, fetched_at}
        self._sessions: dict[str, dict] = {}     # session id -> {expire_at, ids, poll, timeout_at, state, picker_uri}
        self._pick: dict | None = None           # the pick in progress (also kept as the last one, for its outcome)
        self._pick_stop: threading.Event | None = None
        self._picks_seq = 0                      # bumped whenever the listing changes
        self._links: collections.OrderedDict[str, dict] = collections.OrderedDict()   # share links pasted this process
        self._closed = False                     # close() is final: nothing new starts after it
        atexit.register(self._delete_sessions_quietly)

    # ------------------------------------------------------- credential
    def _client_of(self) -> dict:
        with self._lock:
            client = self._client
        if client is None:
            client = loopback.load_client()
            with self._lock:
                self._client = client
        return client

    def _refresh(self, refresh_token: str) -> dict:
        return loopback.refresh(self._client_of(), refresh_token)

    def _mark_expired(self, err: AuthError, gen: int) -> None:
        if err.code == "no_token":
            return
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
        """Run ``fn(access_token)``; a 401 from the Picker refreshes the token once and retries."""
        tok, gen = self._token()
        try:
            return fn(tok)
        except _Unauthorized:
            pass
        tok, gen = self._token(force=True)
        try:
            return fn(tok)
        except _Unauthorized:
            err = AuthError("picker_unauthorized",
                            "Google Photos refused the sign-in even after a refresh. Connect again.",
                            source="gphotos")
            self._mark_expired(err, gen)
            raise err

    # --------------------------------------------------------- the flow
    def _check_open(self) -> None:
        """Raise once ``close()`` has run (caller holds ``_lock``): a closed source starts nothing new."""
        if self._closed:
            raise ConfigError("source_closed", "Google Photos is shutting down.", source="gphotos")

    def _start_flow(self) -> dict:
        client = self._client_of()
        with self._flow_lock:
            with self._lock:
                self._check_open()
                running, gen = self._flow, self._gen
            if running is None:
                flow = loopback.start(client, SCOPES, browser=self.open_browser)
                record = {"auth_url": flow.auth_url, "expires_at": time.time() + loopback.CONSENT_TIMEOUT,
                          "attempt": 1, "flow": flow}
                with self._lock:
                    stale = self._gen != gen or self._closed
                    if not stale:
                        self._flow, self._flow_error = record, None
                if stale:                        # disconnected or closed while the listener opened
                    flow.cancel()
                    raise AuthError("cancelled", "The sign-in was cancelled while it was starting.",
                                    source="gphotos")
                threading.Thread(target=self._wait_for_consent, args=(client, record, gen),
                                 name="gphotos-consent", daemon=True).start()
        return dict(self.status(), step="consent")

    def _wait_for_consent(self, client: dict, record: dict, gen: int) -> None:
        try:
            self._finish_flow(client, record, gen)
        except Exception as e:                   # the thread must not die with the gate still waiting
            err = UpstreamError("flow_failed", "The sign-in could not be completed: %s" % e, source="gphotos")
            with self._lock:
                if self._gen == gen and self._flow is record:
                    self._flow, self._flow_error = None, err.as_dict()

    def _finish_flow(self, client: dict, record: dict, gen: int) -> None:
        flow = record["flow"]
        try:
            tokens = flow.exchange(flow.wait(loopback.CONSENT_TIMEOUT))
            if not tokens.get("refresh_token"):
                # a repeat consent: Google hands out the refresh token once unless asked again
                with self._lock:
                    if self._gen != gen or self._flow is not record:
                        return
                flow = loopback.start(client, SCOPES, prompt="consent", browser=self.open_browser)
                with self._lock:
                    if self._gen != gen or self._flow is not record:
                        flow.cancel()
                        return
                    record.update(auth_url=flow.auth_url, expires_at=time.time() + loopback.CONSENT_TIMEOUT,
                                  attempt=2, flow=flow)
                tokens = flow.exchange(flow.wait(loopback.CONSENT_TIMEOUT))
                if not tokens.get("refresh_token"):
                    raise AuthError("no_refresh_token",
                                    "Google issued no refresh token, so the connection would not survive "
                                    "an hour. Remove cast-tv from your Google account's third-party access "
                                    "and connect again.", source="gphotos")
        except (AuthError, UpstreamError, ConfigError) as e:
            with self._lock:
                if self._gen == gen and self._flow is record:
                    self._flow = None
                    if e.code != "cancelled":
                        self._flow_error = e.as_dict()
            return
        with self._lock:
            if self._gen != gen or self._flow is not record:
                return                           # disconnected or restarted meanwhile: drop it
            self._store.save(tokens, scope=SCOPES)
            self._flow, self._flow_error = None, None
            self._gen += 1
            self._verified_at, self._expired_at, self._error = time.time(), None, None

    def _cancel_flow(self) -> None:
        with self._lock:
            record, self._flow = self._flow, None
        if record is not None:
            record["flow"].cancel()

    # ---------------------------------------------------------- contract
    def status(self) -> dict:
        with self._lock:
            self._prune_expired()
            flow, flow_error = self._flow, self._flow_error
            expired, verified, error = self._expired_at, self._verified_at, self._error
            picks, seq = len(self._picks) + len(self._links), self._picks_seq
            sessions = sum(1 for s in self._sessions.values() if s["expire_at"] > time.time())
            pick = self._public_pick()
        stored = self._store.exists()
        if flow is not None:
            return {"state": "connecting", "detail": {
                "stored": stored, "step": "consent", "auth_url": flow["auth_url"],
                "expires_in": max(0, int(flow["expires_at"] - time.time())),
                "attempt": flow["attempt"], "note": ON_HOST_NOTE}}
        if not stored:
            detail: dict = {"stored": False}
            if flow_error:
                detail["flow_error"] = flow_error
            return {"state": "disconnected", "detail": detail}
        if expired is not None:
            state = "expired"
        elif verified is not None:
            state = "connected"
        else:
            state = "disconnected"               # stored but not yet verified in this process
        detail = {"stored": True, "account": None, "verified_at": verified, "error": error,
                  "picks": picks, "picks_seq": seq, "sessions": sessions, "pick": pick}
        if flow_error:
            detail["flow_error"] = flow_error
        return {"state": state, "detail": detail}

    def _public_pick(self) -> dict | None:
        pick = self._pick                        # caller holds _lock
        if pick is None:
            return None
        out = {k: pick[k] for k in ("session_id", "picker_uri", "state", "started_at", "count")}
        out["expires_in"] = max(0, int(pick["timeout_at"] - time.time()))
        if pick.get("error"):
            out["error"] = pick["error"]
        return out

    def connect(self, params: dict) -> dict:
        """Verify the stored consent, or run the loopback flow and answer its URL.

        ``{}`` with a stored, unexpired credential refreshes it (proving the
        refresh token still works) and reports ``connected``; with nothing
        stored, or after ``expired``, or with ``{"fresh": true}``, it starts a
        consent round and answers ``{step: "consent", ...}`` with the URL under
        ``detail``; ``{"cancel": true}`` ends a running round.
        """
        params = params if isinstance(params, dict) else {}
        if params.get("cancel"):
            self._cancel_flow()
            return self.status()
        with self._lock:
            self._check_open()
            running, expired = self._flow is not None, self._expired_at is not None
        if running:
            return dict(self.status(), step="consent")   # the same round, not a second browser tab
        if self._store.exists() and not expired and not params.get("fresh"):
            _, gen = self._token(force=True)     # the one cheap proof the consent still stands
            with self._lock:
                self._check_open()
                if self._gen == gen:             # not if a disconnect came in while it was refreshing
                    self._gen += 1
                    self._verified_at, self._expired_at, self._error, self._flow_error = time.time(), None, None, None
            return self.status()
        return self._start_flow()

    def disconnect(self) -> None:
        """Forget the consent: the file, every session, every pick, any round in progress.

        Everything local goes at once, under the lock; the remote sessions are
        deleted afterwards within ``CLEANUP_BUDGET``, with the credential as it
        was, and a DELETE that fails or times out changes nothing here.
        """
        with self._lock:
            self._gen += 1
            flow, stop, sids = self._detach()
            credential = self._store.load()
            self._verified_at = self._expired_at = self._error = self._flow_error = None
            self._picks.clear()
            self._links.clear()
            self._pick = None
            self._picks_seq += 1
            self._store.clear()
        self._release(flow, stop, sids, lambda force: self._token_of(credential, force))

    def close(self) -> None:
        """Process exit: nothing new starts, and the sessions are deleted (Google keeps them for a day otherwise).

        Final: marked closed under the lock that detaches the flow, the pick and
        the sessions; the DELETEs follow within ``CLEANUP_BUDGET``. The consent
        stays stored.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._gen += 1
            flow, stop, sids = self._detach()
            self._picks_seq += 1
        self._release(flow, stop, sids, lambda force: self._token(force)[0])

    def _detach(self) -> tuple:
        """Take the flow, the waiting pick's poller and every session out of the state (caller holds ``_lock``)."""
        flow, self._flow = self._flow, None
        stop, self._pick_stop = self._pick_stop, None
        if self._pick is not None and self._pick["state"] == "waiting":
            self._pick["state"] = "cancelled"
        sids, self._sessions = list(self._sessions), {}
        for pick in self._picks.values():
            pick["sessions"].clear()
        return flow, stop, sids

    def _release(self, flow, stop, sids: list[str], token) -> None:
        """Outside ``_lock``: stop the poller, cancel the consent round, delete the remote sessions."""
        if stop is not None:
            stop.set()
        if flow is not None:
            flow["flow"].cancel()
        self._delete_remote(sids, token)

    def _token_of(self, credential: dict | None, force: bool) -> str:
        """An access token from a credential already gone from the store: its own while fresh, else refreshed."""
        if not credential or not credential.get("refresh_token"):
            raise AuthError("no_token", "Not signed in.", source="gphotos")
        if (not force and credential.get("access_token")
                and (credential.get("expires_at") or 0) - time.time() > REFRESH_MARGIN):
            return credential["access_token"]
        return self._refresh(credential["refresh_token"])["access_token"]

    def _delete_sessions_quietly(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # -------------------------------------------------------------- pick
    def pick(self, params: dict) -> dict:
        """Open a Picker session and answer its URL; a thread waits for the pick.

        ``{"cancel": true}`` stops waiting and deletes the pending session.
        A second ``pick()`` while one is pending answers the same session.
        """
        params = params if isinstance(params, dict) else {}
        if params.get("cancel"):
            self._cancel_pick()
            with self._lock:
                return {"pick": self._public_pick()}
        with self._lock:
            self._check_open()
            pending = self._pick if self._pick is not None and self._pick["state"] == "waiting" else None
            if pending is not None:
                return {"pick": self._public_pick()}
            gen = self._gen
        used: list[str] = []                     # the bearer that opened it, to delete it with if it goes stale
        session = self._call(lambda tok: used.append(tok) or picker_call("POST", "/sessions", tok, {}))
        sid, uri = session.get("id"), session.get("pickerUri")
        if not isinstance(sid, str) or not sid or not isinstance(uri, str) or not uri.startswith("https://"):
            raise UpstreamError("picker_shape", "Google Photos opened no usable picker session (keys: %s)."
                                % ", ".join(session)[:200], source="gphotos")
        polling = session.get("pollingConfig") if isinstance(session.get("pollingConfig"), dict) else {}
        now = time.time()
        record = {"session_id": sid, "picker_uri": uri, "state": "waiting", "started_at": now, "count": 0,
                  "poll": _seconds(polling.get("pollInterval"), DEFAULT_POLL),
                  "timeout_at": now + _seconds(polling.get("timeoutIn"), DEFAULT_PICK_TIMEOUT),
                  "error": None}
        stop = threading.Event()
        with self._lock:
            stale = self._gen != gen or self._closed
            if not stale:
                self._sessions[sid] = {"expire_at": _when(session.get("expireTime")) or now + 86400.0,
                                       "ids": set(), "picker_uri": uri}
                self._pick, self._pick_stop = record, stop
        if stale:                                # disconnected or closed while the session opened: not ours to keep
            try:
                self._delete_remote([sid], lambda force: used[-1])
            except Exception:
                pass                             # best effort; the cancellation is what the caller hears
            raise AuthError("cancelled", "Sign-in changed while the picker was opening.", source="gphotos")
        threading.Thread(target=self._wait_for_pick, args=(record, stop, gen),
                         name="gphotos-pick", daemon=True).start()
        with self._lock:
            return {"pick": self._public_pick()}

    def _wait_for_pick(self, record: dict, stop: threading.Event, gen: int) -> None:
        sid = record["session_id"]
        try:
            while True:
                if stop.wait(record["poll"]):
                    return                       # cancelled: the canceller cleans up
                if time.time() > record["timeout_at"]:
                    self._end_pick(record, gen, "timeout", None)
                    self._drop_session(sid, delete=True)
                    return
                session = self._call(lambda tok: picker_call("GET", "/sessions/" + urllib.parse.quote(sid, safe=""), tok))
                if session.get("mediaItemsSet"):
                    break
            items = self._list_session(sid)
            with self._lock:
                if self._gen != gen or self._pick is not record:
                    return
                record["count"] = self._merge(sid, items)
            self._end_pick(record, gen, "done", None)
        except (AuthError, UpstreamError, ConfigError) as e:
            self._end_pick(record, gen, "error", e.as_dict())
            if e.code == "picker_not_found":
                self._drop_session(sid, delete=False)
        except Exception as e:
            err = UpstreamError("pick_failed", "Waiting for the pick failed: %s" % e, source="gphotos")
            self._end_pick(record, gen, "error", err.as_dict())

    def _end_pick(self, record: dict, gen: int, state: str, error: dict | None) -> None:
        with self._lock:
            if self._gen == gen and self._pick is record:
                record["state"], record["error"] = state, error
                self._pick_stop = None

    def _cancel_pick(self) -> None:
        with self._lock:
            record, stop = self._pick, self._pick_stop
            if record is None or record["state"] != "waiting":
                return
            record["state"], self._pick_stop = "cancelled", None
        if stop is not None:
            stop.set()
        self._drop_session(record["session_id"], delete=True)

    def _list_session(self, sid: str) -> list[dict]:
        """Every picked item of a session, all pages."""
        items: list[dict] = []
        token = None
        for _ in range(200):                     # 20 000 items is more than a pick can hold
            query = {"sessionId": sid, "pageSize": PAGE_SIZE}
            if token:
                query["pageToken"] = token
            data = self._call(lambda tok: picker_call("GET", "/mediaItems?" + urllib.parse.urlencode(query), tok))
            page = data.get("mediaItems")
            if isinstance(page, list):
                items.extend(i for i in page if isinstance(i, dict) and i.get("id"))
            token = data.get("nextPageToken")
            if not token:
                break
        return items

    def _merge(self, sid: str, items: list[dict]) -> int:
        """Fold a session's items into the picks (caller holds ``_lock``); returns how many it added or refreshed."""
        now = time.time()
        session = self._sessions.get(sid)
        count = 0
        for raw in items:
            media_id = str(raw["id"])
            if not good_id(media_id):
                continue
            kind = kind_from_facets("gphotos", raw)
            if kind is None:
                note_hidden_kind("gphotos", (raw.get("type"), _media_file(raw).get("mimeType")))
                continue
            known = self._picks.get(media_id)
            if known is None:
                self._picks[media_id] = {"raw": raw, "kind": kind, "sessions": {sid}, "fetched_at": now}
            else:                                # seen before: keep its place, take the newer address
                known.update(raw=raw, kind=kind, fetched_at=now)
                known["sessions"].add(sid)
            if session is not None:
                session["ids"].add(media_id)
            count += 1
        self._picks_seq += 1
        return count

    # ---------------------------------------------------------- sessions
    def _prune_expired(self) -> None:
        """Forget sessions past their ``expireTime`` (caller holds ``_lock``): expired, they are of no use.

        No DELETE for them. Their media stay in the grid - flagged "re-pick"
        once no live session holds them - and lose only their links to the
        expired sessions; links to live ones are kept.
        """
        now = time.time()
        gone = [sid for sid, session in self._sessions.items() if session["expire_at"] <= now]
        for sid in gone:
            del self._sessions[sid]
            for pick in self._picks.values():
                pick["sessions"].discard(sid)
        if gone:
            self._picks_seq += 1

    def _live_sessions(self, media_id: str) -> list[str]:
        """Session ids that hold ``media_id`` and have not expired (caller holds ``_lock``)."""
        now = time.time()
        pick = self._picks.get(media_id)
        if pick is None:
            return []
        return [sid for sid in pick["sessions"]
                if sid in self._sessions and self._sessions[sid]["expire_at"] > now]

    def _drop_session(self, sid: str, delete: bool) -> None:
        with self._lock:
            gone = self._sessions.pop(sid, None)
            for pick in self._picks.values():
                pick["sessions"].discard(sid)
            if gone is not None:
                self._picks_seq += 1
        if delete and gone is not None:
            try:
                self._call(lambda tok: picker_call("DELETE", "/sessions/" + urllib.parse.quote(sid, safe=""), tok))
            except (AuthError, UpstreamError, ConfigError):
                pass                             # gone anyway, or will expire on its own

    def _delete_remote(self, sids: list[str], token) -> None:
        """DELETE ``sids`` against one ``CLEANUP_BUDGET`` deadline; the local state is already gone.

        The requests run on a daemon thread and the caller waits for it until
        the deadline at most, so a DELETE that hangs neither holds the caller
        nor keeps the process alive. ``token(force)`` supplies the bearer; one
        refresh is allowed for the lot. Nothing here raises.
        """
        if not sids:
            return
        deadline = time.monotonic() + CLEANUP_BUDGET
        done = threading.Event()

        def work():
            try:
                tok, refreshed = token(False), False
                for sid in sids:
                    path = "/sessions/" + urllib.parse.quote(sid, safe="")
                    while time.monotonic() < deadline:
                        try:
                            picker_call("DELETE", path, tok, timeout=max(0.05, min(30.0, deadline - time.monotonic())))
                        except _Unauthorized:
                            if not refreshed:
                                tok, refreshed = token(True), True
                                continue
                        except (AuthError, UpstreamError, ConfigError):
                            pass                 # gone already, or it expires on its own
                        break
            except Exception:
                pass                             # best effort: nothing here can undo the local state
            finally:
                done.set()
        try:
            threading.Thread(target=work, name="gphotos-cleanup", daemon=True).start()
        except RuntimeError:                     # an interpreter that is shutting down starts no thread
            work()
            return
        done.wait(max(0.0, deadline - time.monotonic()))

    def _refresh_base(self, media_id: str, force: bool = False) -> tuple[str, dict]:
        """``(baseUrl, raw)`` for a pick, re-listed through a live session when stale or ``force``."""
        with self._lock:
            pick = self._picks.get(media_id)
            if pick is None:
                raise NotMedia("unknown_item", "That item is not among this session's picks.",
                               source="gphotos", item=media_id)
            fresh = time.time() - pick["fetched_at"] < BASEURL_FRESH
            base = _media_file(pick["raw"]).get("baseUrl")
            if fresh and base and not force:
                return base, pick["raw"]
            self._prune_expired()
            candidates = self._live_sessions(media_id)
        for sid in candidates:
            try:
                items = self._list_session(sid)
            except UpstreamError as e:
                if e.code == "picker_not_found":
                    self._drop_session(sid, delete=False)
                    continue
                raise
            with self._lock:
                self._merge(sid, items)
                pick = self._picks.get(media_id)
                base = _media_file(pick["raw"]).get("baseUrl") if pick and sid in pick["sessions"] else None
            if base:
                return base, pick["raw"]
            self._drop_session(sid, delete=False)   # the session no longer holds it
        raise UpstreamError("repick_needed",
                            "The Google Photos address for this item expired and no picker session "
                            "still holds it. Pick it again.", source="gphotos", item=media_id)

    def _bearer(self) -> dict:
        tok, _ = self._token()
        return {"Authorization": "Bearer " + tok}

    # ------------------------------------------------------ share links
    def link(self, params: dict) -> dict:
        """A pasted share link: scraped now, listed as a video item of this tab."""
        params = params if isinstance(params, dict) else {}
        link = params.get("link")
        if not isinstance(link, str) or not link.strip():
            raise ConfigError("bad_link", "Paste a Google Photos link.", source="gphotos")
        link = link.strip()
        if not sharelink.allowed(link):          # before anything is fetched: no address off Google
            raise ConfigError("bad_link", "That is not a Google Photos link (https://photos.app.goo.gl/... "
                              "or https://photos.google.com/...).", source="gphotos")
        with self._lock:
            for lid, known in self._links.items():
                if known["link"] == link:
                    return {"item": self._link_entry(lid, known).as_dict()}
        url = sharelink.resolve(link)
        name = urllib.parse.urlsplit(link).path.rstrip("/").rsplit("/", 1)[-1] or "Google Photos"
        with self._lock:
            lid = LINK_PREFIX + str(len(self._links) + 1)
            known = {"link": link, "url": url, "name": name, "resolved_at": time.time()}
            self._links[lid] = known
            self._picks_seq += 1
            return {"item": self._link_entry(lid, known).as_dict()}

    @staticmethod
    def _link_entry(lid: str, known: dict) -> Entry:
        return Entry(source="gphotos", id=lid, name=known["name"], kind="video", thumb=None,
                     mime="video/mp4", warn=None)

    def _link_item(self, lid: str) -> MediaItem:
        with self._lock:
            known = self._links.get(lid)
        if known is None:
            raise NotMedia("unknown_item", "That link was not pasted in this session.", source="gphotos", item=lid)
        source = self

        def fresh() -> Upstream:                 # played through the same guard: no redirect off Google
            with source._lock:
                return Upstream(source._links[lid]["url"], opener=sharelink.opener())

        def again() -> Upstream:
            url = sharelink.resolve(known["link"])
            with source._lock:
                source._links[lid].update(url=url, resolved_at=time.time())
            return Upstream(url, opener=sharelink.opener())

        return MediaItem(kind="video", title=known["name"], mime="video/mp4", source="gphotos",
                         source_id=lid, version=known["link"], resolve=fresh, refresh=again)

    # ------------------------------------------------------------ list
    def list(self, path=None, page=None) -> Listing:
        """The picks of this process, in first-pick order, then the pasted links."""
        with self._lock:
            self._prune_expired()
            entries = []
            for media_id, pick in self._picks.items():
                entries.append(entry_for(pick["raw"], pick["kind"], bool(self._live_sessions(media_id))))
            for lid, known in self._links.items():
                entries.append(self._link_entry(lid, known))
        return Listing(items=entries, folders=[], next=None, crumbs=[])

    def resolve(self, source_id: str, quality: str = "auto") -> MediaItem:
        """An unregistered item whose ``resolve`` hands out ``baseUrl=d``/``=dv`` with the Bearer header."""
        if isinstance(source_id, str) and source_id.startswith(LINK_PREFIX):
            return self._link_item(source_id)
        if not good_id(source_id):
            raise NotMedia("bad_id", "Not a Google Photos item id.", source="gphotos",
                           item=str(source_id)[:64])
        with self._lock:
            pick = self._picks.get(source_id)
            if pick is None:
                raise NotMedia("unknown_item", "That item is not among this session's picks.",
                               source="gphotos", item=source_id)
            raw, kind = pick["raw"], pick["kind"]
            self._prune_expired()
            live = bool(self._live_sessions(source_id))
        entry = entry_for(raw, kind, live)
        if kind == "video" and quality not in ("auto", "original", "stream"):
            raise ConfigError("bad_quality", "A Google Photos video is cast as \"original\" or \"stream\".",
                              source="gphotos", item=source_id)
        stream = kind == "video" and quality == "stream"
        suffix = "=d" if kind == "photo" else (STREAM_SUFFIX if stream else "=dv")
        source = self

        def fresh() -> Upstream:
            base, _ = source._refresh_base(source_id)
            return Upstream(base + suffix, source._bearer())

        def again() -> Upstream:
            base, _ = source._refresh_base(source_id, force=True)
            return Upstream(base + suffix, source._bearer())

        return MediaItem(kind=kind, title=entry.name, mime=entry.mime, source="gphotos",
                         source_id=source_id, version=source_id + (suffix if kind == "video" else ""),
                         resolve=fresh, refresh=again,
                         # the original ignores Range: fetched whole before casting; the stream is relayed
                         download=kind == "video" and not stream,
                         width=None if stream else entry.width, height=None if stream else entry.height,
                         duration=entry.duration)

    def thumb(self, source_id: str) -> Upstream | None:
        if not good_id(source_id) or source_id.startswith(LINK_PREFIX):
            return None
        with self._lock:
            if source_id not in self._picks:
                return None
        try:
            base, _ = self._refresh_base(source_id)
        except UpstreamError:
            return None
        return Upstream(base + THUMB_SUFFIX, self._bearer())
