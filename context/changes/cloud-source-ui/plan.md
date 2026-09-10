# Cloud Source UI Implementation Plan

## Overview

Turn the one-shot `cast-tv` CLI into a long-lived local web UI served by the process that
already runs the HTTP server, with three source tabs behind connection gates (GoPro token,
OneDrive device code, Google Photos loopback OAuth plus the Picker API), photos and
slideshows alongside video, and a `castlib` package installable with pipx on Linux and
Windows. The decisions are in `change.md`; the codebase constraints, verified bugs and
history are in `research.md`; the OAuth spike in that folder proved the Google flow end to
end. This plan sequences the work so that every phase leaves the CLI working and is usable
on Fedora on its own, with Windows last and separable.

## Current State Analysis

Four files, ~1000 lines, standard library only (`cast-tv`, `castcloud.py`, `cast-gopro`,
`cast-photos`). What matters for the plan, with origin marked:

- **One item per process, held in class attributes** (`cast-tv:108-112`, assigned from
  `main()` at `:429-467`). Two bugs live today: relay plus subtitles mutates the class-body
  dict (`:458`), and a second cast replaces `files` mid-stream (`:451`). Seven more become
  bugs once two items coexist (`research.md` §3). Origin: `code`, and the plan replaces it.
- **HTTP/1.1 keep-alive with no framing discipline for new routes**: `send_error` emits
  `text/html` and `Connection: close`; no handler `timeout`; `_range` never clamps `start`,
  never returns 416, and crashes on `bytes=-` (`:143-156`). Origin: `code`.
- **The server binds `0.0.0.0` with no `Host` or `Origin` check** (`:463`). Media paths are
  guessable (`/video/<basename>`). Once `/api` can start a cast, any LAN device and any web
  page in the user's browser can drive the TV. Origin: `product` (decided in `change.md` as
  phase one).
- **Photos cannot be served**: no image MIME (`:19-24`), two different MIME fallbacks
  (`:131` vs `:302`), `upnp:class` hard-coded `videoItem` (`:312`), `transferMode` always
  `Streaming` (`:137`, `:229`), `DLNA_FEATURES` is a video profile applied to everything
  (`:26-27`), no `resolution`/`size` on `<res>`, relay appends `.mp4` to extension-less URLs
  (`:426-427`). Origin: `code`.
- **`castcloud.py` exits instead of raising** (`die()`, `:22-24`), `fetch()` has two return
  shapes (`:40-51`), `cast()` shells out and spawns a second server (`:101-115`), the cache
  is non-atomic (`:118-129`). Origin: `code`.
- **`is_video()` accepts `*/octet-stream`** (`castcloud.py:75-78`). Origin: `product` — history
  (`223eca1`) shows removing it downgrades every GoPro cast to a proxy. Keep.
- **`RelTime` arrives as `0:00:00`**, `TRANSITIONING` is "still an attempt", the relay
  synthesises 206 on the upstream's status, `=dv` leads `SUFFIXES`. Origin: `product`
  (commits `a750b37`, `223eca1`, `582abd0`, `36cf4c8`). Keep all four.
- **The TV is the first renderer discovery returns** (`cast-tv:403`). Origin: `code`; this
  plan makes it the default and adds a picker (Definitions).
- **The stored GoPro token is a five-segment JWE**; its expiry is not readable client-side.
  A probe on 2026-09-09 with the token stored on 2026-09-07 answered 401. Origin: verified
  in this planning session. The only expiry signal is the API's answer.
- **GoPro listing keeps the raw `type` string** (`cast-gopro:87`); its values and the
  thumbnail field shape are unverified (the probe above could not list). Origin: `none`; the
  GoPro phase probes at implementation time.
- **Google Photos Picker** (spike, 2026-09-09): desktop loopback + PKCE mints a
  Picker-scoped token with a refresh token; `baseUrl` answers 206 with `Authorization:
  Bearer` and 403 without; item shape is `mediaFile.{filename,mimeType,baseUrl,
  mediaFileMetadata.{width,height}}` plus top-level `createTime`. Origin: `product`.
- **Microsoft Graph** (sourced 2026-09-09): `@microsoft.graph.downloadUrl` needs no
  authentication and "is invalidated after a short period of time (1 hour)"; children
  list pages at 200 with `@odata.nextLink`; `thumbnails` is a relationship (needs
  `$expand`); device code endpoints are `/{tenant}/oauth2/v2.0/devicecode` and `/token`,
  polling errors `authorization_pending`, `slow_down`, `authorization_declined`,
  `expired_token`, `bad_verification_code`; a public client needs **Allow public client
  flows = Yes** under Authentication → Advanced settings. Origin: `product`.
- **Design canvas** (five artboards, Polish labels): gate → list, grid, cast bar, slideshow
  with queue and "change every", phone view, three gates side by side, and the diagnostic
  states (expired token banner over the still-visible list, no TV found with per-interface
  M-SEARCH counts, TV fetched zero bytes with firewall commands, DTS, source too heavy with
  variant choice, HEIC conversion progress). Its Google gate predates the Picker decision;
  `change.md` wins.
- `context/foundation/` is empty: no lessons file, no roadmap.

## Definitions

| Term | Decided meaning | Origin | On degenerate data (tie, duplicate, empty, boundary, legacy) | Verified by |
| ---- | --------------- | ------ | ------------------------------------------------------------- | ----------- |
| selection / queue | The set of items ticked across tabs, in the order they were ticked; persists across tab switches; cleared explicitly or on process exit | user (2026-09-09) | Same file in two OneDrive folders are two items (identity is `(source, source_id)`); ticking an item twice toggles it; an empty selection disables "Start show" | `test_supervisor.py::test_show_order_is_selection_order`; Phase 3 manual |
| slideshow | Plays the queue in selection order; a photo holds for the interval, counted from a successful `Play`; a video plays to its end, then the show resumes; a manual cast or a new show cancels the running show | user (2026-09-09) | Queue of one photo holds until stopped, no interval; queue of only videos plays them back to back; a video that never starts counts as failed and the show moves on after the 24/40 s budget; a show whose current cast was replaced ends without casting further | `test_supervisor.py::test_show_waits_for_video_end`, `::test_show_skips_failed_item`, `::test_manual_cast_cancels_show`, `::test_single_photo_show_holds_until_stop`, `::test_interval_counts_from_play` |
| interval | Seconds a photo stays on screen, default 8, adjustable in the slideshow bar, remembered in config | user | Lower bound 2 s, upper bound 600 s, invalid values rejected with 400; a missing config key means 8 | `test_api.py::test_settings_interval_bounds` |
| media (listable, castable) | Photo or video as declared by the source's own metadata (Graph `image`/`photo`/`video` facets, Picker `type`, GoPro `type`, local extension); everything else is hidden, including audio, raw and GIF | user | An item whose kind is unknown is hidden and logged once per session; a folder is never an item; a local `.gif` on the CLI is refused with a message; every source runs `is_allowed_photo` on the MIME before listing a photo | `test_media.py::test_kind_from_facets` (incl. `image/gif`), `::test_unknown_kind_hidden`, `test_gopro.py::test_resolve_photo_variant` |
| kind → wire | photo: `image/jpeg` after conversion or `image/jpeg`/`image/png` as is, `object.item.imageItem.photo`, `transferMode: Interactive`, DLNA profile chosen from the prepared file's MIME and dimensions; DIDL, headers and HTTP all read the same `Prepared`; video: as today | product (DLNA guidelines) + code (values verified on the TV in Phase 2) | A photo with EXIF orientation ≠ 1 is re-encoded upright; a photo with no decodable dimensions is refused | `test_media.py::test_didl_photo`, `test_photos.py::test_exif_transpose`; Phase 2 manual on the Samsung |
| connected (GoPro) | A token is stored **and** the last `/media/search` call with it succeeded; the gate shows "token stored N hours ago" | user | No token: gate with paste field; 401 anywhere: state `expired`, banner over the still-visible list; the token pasted twice is de-duplicated as today | `test_gopro.py::test_401_flips_to_expired` |
| connected (OneDrive) | A refresh token is stored and the last Graph call succeeded or was refreshed silently | user | Refresh fails (`invalid_grant`): state `expired`, gate returns; device code expired before sign-in: gate shows "code expired, start again" | `test_onedrive.py::test_refresh_on_401`, `::test_devicecode_expired` |
| connected (Google Photos) | A refresh token is stored; a pick is separate from a connection | user | Restart: connected, no pick, grid empty; refresh fails: gate returns; consent finished on another machine's browser: loopback never fires, connect times out after 5 min with a message | `test_gphotos.py::test_pick_not_persisted`, `::test_connect_timeout` |
| pick | Items from one or more Picker sessions opened in this process, merged by media id (Google keeps the id stable across sessions); sessions are deleted at exit | user (2026-09-09) | The same id picked in two sessions is one entry, placed where it was first picked; its `baseUrl` refreshes through any still-valid session that contains it; "re-pick" appears only when no valid session contains it; pick cancelled: polling stops at `pollingConfig.timeoutIn`, grid unchanged; `RESOURCE_EXHAUSTED`: error on the gate | `test_gphotos.py::test_pick_timeout`, `::test_session_expired_marks_items`, `::test_repick_merges_by_media_id` |
| browse (OneDrive) | The whole drive, starting at root, folder navigation with breadcrumbs, folders always shown, files filtered to media | user | Empty folder: "nothing castable here" plus the folders; more than 200 children: paged, "load more" | `test_onedrive.py::test_list_pages_nextlink` |
| the TV | The renderer selected in the header; default is the first discovered, `--tv`/`CAST_TV` override; several found → dropdown; none → banner with retry and manual IP, casting disabled | user (default origin `code`, kept) | Two renderers with the same name: shown with IP; the selected TV disappears: cast fails with `TVError`, header shows "unreachable, retry" | `test_discovery.py::test_select_and_persist`; Phase 3 manual |
| cast (while playing) | The new cast replaces the current one and cancels a running show; the previous item is retired and stays registered until the TV has not requested it for 60 s and no transfer is open, then is evicted; the item being played is never evicted | user (2026-09-09) | Two devices cast within a second: the request accepted second wins; the first is skipped before sending if its material was still being prepared, or replaced if it already played; both items registered, both evicted later; casting the item already playing restarts it | `test_registry.py::test_evict_after_idle`, `test_supervisor.py::test_replace_keeps_old_item`, `::test_stale_task_skipped_after_prepare` |
| media URL | `http://<host>:<port>/m/<process-token>/<item-id>`; the token is generated per process; paths are exact-match lookups | product (`change.md` Exposure) | Wrong token or unknown id: 404 with no body hint; the old `/video/<name>` paths no longer exist | `test_server.py::test_media_token_required` |
| upstream URL | Resolved when a media request opens, never at listing time; Graph and Google URLs expire after about an hour | product (Graph and Google docs) | Upstream 403/404 on open: re-resolve once, then 502 to the TV and an error on the item | `test_relay.py::test_reresolve_once` |
| error | A `CastError` with `code`, user-facing `message` (the existing `die()` texts, kept verbatim), optional `hint`, `source`, `item`, `at`; shown where it belongs and kept in a ring buffer of 50 | user | Errors older than the buffer are gone; the diagnostics panel is read-only | `test_api.py::test_errors_ring_buffer` |

## Desired End State

`cast-tv` with no arguments starts the server on 8895, prints the localhost and LAN addresses
and the discovered TV, opens the browser. The UI shows three tabs, each behind its gate.
GoPro lists after a token paste; OneDrive after a device-code sign-in that also works from
the phone; Google Photos after a one-time consent on the host, then "Pick" opens Google's
picker on any device and the picked items land in the grid. Any photo or video from any
tab can be cast; ticking several and pressing "Start show" runs a slideshow that mixes
sources, holds photos for the interval, plays videos to the end, converts HEIC on the fly,
and survives the laptop's idle timer. Every failure the CLI used to print appears on the
item or gate it belongs to, and in the diagnostics panel. `cast-tv film.mkv` still works
exactly as today. `pipx install` puts `cast-tv`, `cast-gopro` and `cast-photos` on the path
on Fedora and on Windows.

Verification: the automated suite passes on both CI runners; the manual checklists in each
phase pass against the Samsung QE83S85F.

### Key Discoveries:

- `_proxy`'s trim logic (`cast-tv:191-249`) is sound and is reused unchanged in spirit;
  only the upstream request grows an `Authorization` header and a resolver callable.
- `castcloud.is_video()`'s octet-stream acceptance (`castcloud.py:75-78`) is load-bearing.
- The poll loop's constraints (`cast-tv:486-518`): `RelTime` is `0:00:00`; `started` latches
  on `PLAYING`/`PAUSED_PLAYBACK` only; budget 40 s in `TRANSITIONING`, 24 s otherwise.
- `discover()` runs before the no-source error today (`cast-tv:395-417`), so the
  no-argument form can be repurposed without changing any working invocation.
- Graph `@microsoft.graph.downloadUrl` needs no auth (the relay sends none); Picker
  `baseUrl` needs Bearer (the relay must send it). One `Upstream(url, headers)` shape
  covers both.
- `platformdirs.user_config_dir("cast-tv")` resolves to `~/.config/cast-tv` on Linux, the
  path used today, so no migration is needed on Linux; Windows gets `%APPDATA%\cast-tv`.
- `SetThreadExecutionState` is per calling thread; it must be called from a thread that
  lives as long as the cast.

## What We're NOT Doing

- No desktop app, no embedded webview, no GoPro "web wrapper" (`change.md`).
- No FastAPI, no Node, no frontend build step, no WebSockets; transport state is polled.
- No audio casting from the UI (decided 2026-09-09); the CLI keeps casting `.mp3`/`.flac`
  by extension as today.
- No raw, GIF, or other undecodable stills; they are hidden, not greyed.
- No browsing a local folder from the UI (exposure); local files stay CLI-only.
- No persisting a Google pick across restarts, and no on-disk photo store; the conversion
  cache is bounded and lives in the temp dir.
- No confirmation before replacing a running cast; no play queue separate from the slideshow.
- No capture-time ordering of slideshows.
- No fixed OneDrive start folder or "recent" view.
- No fake DLNA renderer in tests; the cast lifecycle is verified manually on the TV.
- No `systemd --user` / Task Scheduler service; the process runs in the foreground.
- No PyInstaller bundle in this change (kept as a later channel).
- No verification of the Google OAuth app; Testing mode with the owner as test user.
- Not fixing the design canvas's `-c:a ac3` (the code's `eac3` is right); the UI uses the
  code's text.

## Implementation Approach

Seven phases. The first two are refactors that keep the CLI behaviour identical and are
verified by tests plus one evening with the TV; the third makes the process long-lived and
gives it a face; four to six add one source each on the same `Source` contract; the last
turns the checkout into a package on two platforms. Every phase ends in a commit on its own,
and nothing under `/api` ships before the Origin/Host check and the media token exist.

Package layout after Phase 1 (grown by later phases):

```
castlib/
  __init__.py  __main__.py  cli.py  config.py  errors.py
  items.py      # MediaItem, Registry, Upstream
  media.py      # MIME, kinds, DIDL, DLNA profiles, probe_media
  server.py     # Handler, Server, routing, JSON helpers, Origin/Host check
  relay.py      # the proxy, moved
  discovery.py  # SSDP, control URLs, renderer selection
  dlna.py       # soap, tag, transport info
  photos.py     # materialise, convert, cache             (Phase 2)
  supervisor.py # Cast, Show                              (Phase 3)
  api.py        # /api handlers                           (Phase 3)
  ui/           # index.html app.js style.css alpine.min.js (Phase 3)
  auth/         # tokens.py devicecode.py loopback.py     (Phases 5, 6)
  sources/      # base.py gopro.py onedrive.py gphotos.py sharelink.py (Phases 4-6)
  platform.py   # interfaces, stay-awake                  (Phase 7)
tests/
cast-tv, cast-gopro, cast-photos   # thin shims: from castlib.cli import ...
pyproject.toml
```

## Critical Implementation Details

- **Framing under keep-alive.** Every `/api` and `/ui` response carries an exact
  `Content-Length`; nothing under `/api` calls `send_error`. The only lengthless body is the
  relay's unknown-length branch, which sets `close_connection` as today.
- **Origin/Host rule.** Compute the allowed host set at start (`localhost`, `127.0.0.1`,
  `::1`, every non-loopback IPv4 of this machine) and refresh it on re-discovery. For `/api`
  and `/ui`: the `Host` header's host must be in the set; if `Origin` is present it must be
  `http://` + the `Host` value; `Sec-Fetch-Site: cross-site` is refused. Mutations are POST.
  Media paths `/m/<token>/...` skip the Origin check (the TV sends none) and rely on the
  token.
- **One playback owner, one executor.** `App` holds at most one owner (`Cast` or `Show`)
  and a `generation` counter; every `App.cast()` / `App.show()` increments it and cancels the
  previous `Show` (state `cancelled`). Playback commands run on a single-worker executor in
  acceptance order: a task prepares its material (photo conversion, upstream resolve),
  checks that its generation is still current, registers the item, sends `SetAVTransportURI`
  + `Play` without interleaving with any other task, then marks the previous `Cast`
  `replaced`. A stale task is skipped before it sends anything. Never remove the previous
  item from the registry in that sequence; eviction is time-based (60 s without a request).
  This executor is not a play queue: it never holds more than the tasks in flight.
- **Google consent must run on the host.** The loopback redirect goes to `127.0.0.1` of the
  browser that opened the consent URL. The server calls `webbrowser.open()` itself and shows
  the URL as copy text; a phone opening it cannot complete the flow, and the UI says so.
- **Bearer on the relay.** `Upstream.headers` is sent with every upstream request, including
  the range re-requests the TV makes an hour into a film; the resolver is called again when
  an upstream answers 401/403/404, once.
- **`SetThreadExecutionState`** applies to the calling thread. The stay-awake shim on Windows
  runs in a dedicated thread that lives while any cast or show is active.

---

## Phase 1: Foundations — castlib package, item registry, security boundary

### Overview

Move the server into `castlib/`, replace the class-attribute state with a registry of
`MediaItem`s under unique ids, add the Origin/Host check and tokenised media URLs, fix the
framing and range bugs research verified, turn `die()` into exceptions, and stand up pytest
with an in-process server. `cast-tv film.mkv`, `cast-tv <url> -c cookies.txt`, `--subs`,
`--stop`, `--list` behave exactly as before.

### Changes Required:

#### 1. Package skeleton and shims

**Files**: `castlib/__init__.py`, `castlib/__main__.py`, `castlib/cli.py`, `cast-tv`,
`cast-gopro`, `cast-photos`, `pyproject.toml`, `tests/conftest.py`

**Intent**: Make the code importable and testable without changing how it is launched.
The three root scripts become two-line shims calling `castlib.cli`; `cast-gopro` and
`cast-photos` keep their argument parsers but call `castlib` functions in-process instead
of `subprocess`.

**Contract**: `pyproject.toml` declares the package, `pytest` config and an optional
`test` extra only (entry points and runtime deps arrive in Phases 2 and 7). `python -m
pytest` from the repo root imports `castlib`. `castcloud.py` is removed; its contents move
to `castlib/` and `cast-gopro`/`cast-photos` import from there.

#### 2. Errors instead of exits

**File**: `castlib/errors.py`

**Intent**: Replace `die()` with exceptions the server can render and the CLI can print;
keep every existing message verbatim.

**Contract**: `class CastError(Exception)` with `code: str`, `message: str`, `hint: str |
None`, `source: str | None`, `item: str | None`; subclasses `AuthError` (the source needs
reconnecting), `UpstreamError` (network or HTTP failure talking to a cloud), `NotMedia`,
`TVError`, `ConfigError`. The CLI prints `message` (and `hint`) to stderr and exits 1 where
`die()` used to.

#### 3. MediaItem, Upstream and the Registry

**File**: `castlib/items.py`

**Intent**: One shape for everything the server can serve, registered atomically under an
opaque id, removed on stop or eviction. This is what fixes research §3.1–3.9.

**Contract**:

```python
@dataclass
class Upstream:            # what a resolver returns, fresh on every open
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    opener: urllib.request.OpenerDirector | None = None

@dataclass
class MediaItem:
    id: str                # secrets.token_urlsafe(12), assigned by the registry
    kind: str              # "video" | "photo"
    title: str
    mime: str
    source: str            # "local" | "link" | "gopro" | "onedrive" | "gphotos"
    source_id: str         # identity within the source; (source, source_id) is unique
    path: str | None       # local file, or None
    resolve: Callable[[], Upstream] | None   # for remote items
    size: int | None; width: int | None; height: int | None; duration: float | None
    caption: tuple[str, str] | None          # (subtitle path, subtitle url)
    created: float; last_request: float; requests: int; debug: bool
    in_flight: int         # open media transfers, maintained by the handler
    retired_at: float | None  # set by the supervisor when the item leaves playback
    parent: str | None     # the video id for a subtitle item
    prepared: Prepared | None  # Phase 2: the converted photo; the source fields above stay as fetched
```

`Registry` holds one `dict[str, MediaItem]` under a lock: `add(item) -> MediaItem` (assigns
`id`, publishes atomically, returns the same object), `get(id)`, `remove(id)`,
`retire(id)` (sets `retired_at`; called by the CLI/supervisor when a cast becomes
`replaced`, `stopped`, `failed` or `cancelled`; retiring a video retires its subtitle),
`evict(idle_seconds)` (removes only items with `retired_at` set, `in_flight == 0` and
`last_request` older than `idle_seconds`; an item still owned by a cast is never removed,
however long the TV pauses), `touch(id)` (called on every media request; bumps
`last_request` and `requests`), `begin(id)` / `end(id)` (bracket a transfer; `in_flight`).
No two-step registration: a subtitle is registered as its own item before the video that
references it, with `parent` pointing at the video.

#### 4. Media table, kinds and probe

**File**: `castlib/media.py`

**Intent**: One MIME table with one fallback, kind detection, the DIDL builder taking a
`MediaItem`, and `probe_media()` replacing `is_video()` with its octet-stream acceptance
intact and network failure distinguished from "not media".

**Contract**: `MIME` (video, audio, subtitles as today; images arrive in Phase 2);
`kind_of_extension(ext) -> "video" | "audio" | "photo" | None`; `didl(item, url) -> str`
emits `upnp:class` per kind and, when known, `resolution` and `size` on `<res>`;
`probe_media(url, headers=None, opener=None) -> tuple[str, str, int | None] | None`
returns `(kind, content_type, size)` or `None` for not-media and raises `UpstreamError` on
network failure. DLNA header values per kind live here as `dlna_headers(item)`.

#### 5. The server

**File**: `castlib/server.py`

**Intent**: Dispatch before lookup, correct HTTP/1.1 framing, the security boundary, and the
registry-backed media paths. No `/api` handlers yet, but the plumbing they need.

**Contract**: `Handler(BaseHTTPRequestHandler)` with `protocol_version = "HTTP/1.1"`,
`timeout = 30`, one `_parse()` of `self.path` keeping the query, routes in order: `/m/<token>/
<id>` → media; `/api/...` → `self.server.app.api(...)` (Phase 3); `/ui/...` →
static (Phase 3); `/` → 302 to `/ui/`; `/favicon.ico` → 204; else 404 via `_json_error`.
Helpers: `_json(status, obj)` and `_json_error(status, code, message, hint=None)` with
exact `Content-Length`; `_check_origin()` per the rule in Critical Implementation Details,
returning 403 JSON on failure. `Server(ThreadingTCPServer)` carries `registry`,
`media_token` (`secrets.token_urlsafe(16)`), `allowed_hosts`, `app` (Phase 3), and
`media_url(item) -> str`. `_range(size)` clamps `start`, returns 416 with `Content-Range:
bytes */size` when `start >= size`, treats a malformed or multi-range header as no range
(200 full body). `getsize`/`open` failures answer 404 before headers are sent, or drop the
connection after.

#### 6. The relay

**File**: `castlib/relay.py`

**Intent**: Move `_proxy` with its trim logic intact; feed it from `item.resolve()` and
send `Upstream.headers`; re-resolve once on 401/403/404 from the upstream.

**Contract**: `proxy(handler, item, body=True)`. The `.mp4` suffix on extension-less names
(`cast-tv:426-427`) is gone: `Content-Type` comes from `item.mime`, and the upstream's
generic type is overridden by it as today. `transferMode`/`contentFeatures` come from
`media.dlna_headers(item)`.

#### 7. Discovery and DLNA moved

**Files**: `castlib/discovery.py`, `castlib/dlna.py`

**Intent**: `discover`, `service_control_url`, `control_urls`, `local_ip` move to
`discovery.py`; `soap`, `tag` and a `transport_state(avt) -> (state, reltime, duration)`
helper move to `dlna.py`. No behaviour change in this phase.

#### 8. Config and cache

**File**: `castlib/config.py`

**Intent**: Replace `castcloud.CONFIG`/`CACHE` with functions, make cache writes atomic, and
validate names.

**Contract**: `config_dir()`, `cache_dir()` (hard-coded to today's paths until Phase 7 swaps
in platformdirs; holds metadata only, today the GoPro listing cache, never media bytes);
`photo_tmp_dir()` returns the per-process temp directory from Phase 2 and registers its
removal; `cache_write(name, data)` writes to a temp file in the same directory and
`os.replace`s; `cache_read(name)`; both reject any `name` that is not a bare filename.
`write_private(path, text)` creates with mode 0600 (used by token stores later). All
`open()` calls pass `encoding="utf-8"`.

#### 9. The CLI on the new code

**File**: `castlib/cli.py`

**Intent**: `cast-tv`'s `main()` reassembled on the registry: bind first, register items,
SOAP, the existing poll loop with its constraints. `cast-gopro`/`cast-photos` call sources in
process (their listing and resolving code moves under `castlib/sources/` in Phases 4 and 6;
here it moves as-is into `castlib/sources/gopro.py` and `castlib/sources/sharelink.py` with
`die()` replaced).

**Contract**: All flags and outputs unchanged. `--debug` sets `item.debug`. The URL handed to
the TV is `server.media_url(item)`.

#### 10. Tests

**Files**: `tests/conftest.py`, `tests/test_registry.py`, `tests/test_server.py`,
`tests/test_range.py`, `tests/test_relay.py`, `tests/test_media.py`

**Intent**: The bugs research verified become regression tests; the security rule is
tested; the in-process server fixture is reused by every later phase.

**Contract**: `conftest.py` starts a `Server` on `127.0.0.1:0` in a thread and yields
`(server, base_url)`. Named cases: `test_range.py::test_start_beyond_size_is_416`,
`::test_bare_dash_is_full_body`, `::test_multirange_is_full_body`; `test_server.py::
test_media_token_required`, `::test_api_rejects_foreign_origin`, `::test_api_rejects_foreign_host`,
`::test_404_is_json_and_keeps_connection`, `::test_head_and_get_agree_on_length`; `test_registry.py::
test_add_is_atomic_and_unique`, `::test_evict_after_idle` (only retired items),
`::test_active_item_survives_idle`, `::test_in_flight_blocks_eviction`,
`::test_retire_video_retires_subtitle`, `::test_second_item_does_not_replace_first`;
`test_relay.py::test_206_synthesised_when_upstream_ignores_range` (against a local stub
upstream), `::test_reresolve_once`, `::test_bearer_header_forwarded`; `test_media.py::
test_probe_accepts_octet_stream`, `::test_probe_network_failure_raises`.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/` passes on Fedora.
- `python -m pyflakes castlib tests` reports nothing (or `ruff check` if adopted).
- `./cast-tv --list` prints the TV; `./cast-tv --stop` stops it (against the real TV, but
  scriptable).
- `test_registry.py::test_second_item_does_not_replace_first` registers two items in one
  in-process server and GETs both: each answers 200 with its own bytes, neither is removed.
  (Replacing a running cast by hand needs the long-lived process and is checked in Phase 3.)

#### Manual Verification:

- `cast-tv film.mkv -s film.srt` plays with subtitles as before; `cast-tv <https url>` relays
  as before; `--debug` output unchanged in shape.
- From another machine on the LAN: `curl -H 'Origin: http://evil' http://<lan-ip>:8895/api/status`
  → 403 JSON; a wrong media token → 404.

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 2: Photos — kind-aware serving and the materialised pipeline

### Overview

Photos become first-class: image MIME, per-kind DIDL and DLNA headers, HEIC converted to
JPEG with Pillow, EXIF orientation applied, results materialised in a bounded cache so
HEAD and GET agree. `cast-tv IMG_4823.HEIC` puts the photo on the TV. This is the phase that
verifies the Samsung image profile (research Open Question 1).

### Changes Required:

#### 1. Dependencies

**File**: `pyproject.toml`

**Intent**: Add `pillow` and `pillow-heif` as runtime dependencies. `ffprobe` stays optional.

#### 2. Image types and the photo DLNA profile

**File**: `castlib/media.py`

**Intent**: Extend the table and the header/DIDL builders for photos.

**Contract**: `MIME` gains `.jpg/.jpeg → image/jpeg`, `.png → image/png`, `.heic/.heif →
image/heic`, `.webp → image/webp`; `kind_of_extension` returns `"photo"` for them.
`PHOTO_MIMES = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}` and
`is_allowed_photo(mime) -> bool` are the one filter every source applies before building a
photo `Entry`; `image/gif`, raw and unknown image types fail it and are hidden (logged
once per session, per the `media` definition).
`dlna_headers(item)` returns `transferMode.dlna.org: Interactive` and a `contentFeatures`
built from `PHOTO_FEATURES = "DLNA.ORG_PN={pn};DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000"`
for photos, the existing string for video. `photo_profile(mime, width, height) -> str`
picks `pn` from the **result** of preparation, never from the source extension: `image/jpeg`
→ `JPEG_SM` (≤ 640×480), `JPEG_MED` (≤ 1024×768), `JPEG_LRG` (≤ 4096×4096); `image/png` →
`PNG_LRG` (≤ 4096×4096); anything larger is downscaled by `prepare()` to fit 4096×4096 so
a profile always exists. `didl(item, url)` reads `item.prepared` for photos and emits
`object.item.imageItem.photo`, `resolution="WxH"`, `size="N"` and `protocolInfo` with the
same profile. These photo values are the DLNA-guideline defaults and are **unverified on
this TV**; the manual checklist below is where they get adjusted, and `PHOTO_FEATURES` plus
`photo_profile` are the only places to change.

#### 3. The photo pipeline

**File**: `castlib/photos.py`

**Intent**: Fetch or read whole, decode, transpose by EXIF, convert HEIC (and anything not
JPEG/PNG) to JPEG, learn width/height, and cache the produced bytes so HEAD and GET are
served from one decode. Bound the work.

**Contract**: `prepare(item) -> Prepared(path, mime, size, width, height, profile)`, a
separate frozen object stored on `item.prepared`; the item's own `mime`, `size`, `width`
and `height` stay as the source reported them, so the grid and the diagnostics keep
describing the original while DIDL, DLNA headers and HTTP all read `Prepared`. `path` is a
file in a per-process directory created by `tempfile.mkdtemp(prefix="cast-tv-photos-")`
and removed with `shutil.rmtree` at exit (`atexit`, and in the `KeyboardInterrupt` handler
of the CLI and the app); `cache_dir()` is never used for photo bytes; the cache is an LRU keyed by
`(source, source_id, version)` where `version` is mtime+size for local files and the
source's etag/id otherwise, bounded at 256 MB and 200 entries, evicted on insert; a
`ThreadPoolExecutor(max_workers=2)` bounds concurrent decodes; `prefetch(items)` schedules
without blocking. JPEG and PNG with orientation 1 are stored as fetched (no re-encode); HEIC,
WebP and any oriented image are re-encoded to JPEG quality 92. `pillow_heif.register_heif_opener()`
at import. Remote photos are fetched through `item.resolve()` with `Upstream.headers`.

#### 4. Serving photos

**File**: `castlib/server.py`

**Intent**: Preparation happens before the TV hears about the photo, never inside the HTTP
handler. The order for a photo cast is: `photos.prepare(item)` → (from Phase 3: check the
task's generation is still current) → `registry.add(item)` (the route exists from here) →
`SetAVTransportURI` with DIDL built from `item.prepared` → `Play`. A conversion failure
raises `NotMedia` or `UpstreamError` and ends the task before any SOAP is sent; the error
lands on the item. The media route serves `item.prepared.path` with `Prepared.mime` and
`Prepared.size`, and range requests work on that file as for any local file; a photo item
without `prepared` answers 404, because the route does not convert. Phase 2 applies this
order in `cli.py`; Phase 3 moves it into the executor task unchanged.

#### 5. Video-only diagnostics guarded

**File**: `castlib/cli.py` (and later `supervisor.py`)

**Intent**: `check_codecs` and `explain_failure` run only for `kind == "video"`.

#### 6. Tests

**Files**: `tests/test_photos.py`, `tests/test_media.py`, fixtures under `tests/fixtures/`
(a tiny JPEG with orientation 6, a tiny HEIC, a PNG, a WebP; generated by a script in
`tests/fixtures/make.py` so no binaries are committed blindly)

**Contract**: `test_photos.py::test_heic_becomes_jpeg`, `::test_exif_transpose`,
`::test_head_get_agree_after_conversion`, `::test_cache_evicts_by_bytes`,
`::test_concurrency_bounded`, `::test_tmp_dir_removed_at_exit` (subprocess, `SIGINT`),
`::test_prepared_keeps_source_fields`,
`::test_unprepared_photo_is_404`, `::test_conversion_failure_sends_no_soap` (fake `soap()`
never called); `test_media.py::test_didl_photo` (DIDL values equal `Prepared`),
`::test_photo_profile_from_result` (HEIC → `JPEG_LRG`, small JPEG → `JPEG_SM`, PNG →
`PNG_LRG`), `::test_photo_headers_interactive`,
`::test_kind_from_facets` (pure function over Graph/Picker/GoPro-shaped dicts, used from
Phase 4 on; includes a Graph `image/gif` and a Picker `image/gif` case → hidden),
`::test_unknown_kind_hidden`.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/` passes.
- `pip install .` pulls `pillow` and `pillow-heif` on Fedora.

#### Manual Verification:

- `cast-tv photo.jpg` shows the photo on the Samsung; `cast-tv IMG_4823.HEIC` shows the
  converted photo; a PNG shows with `PNG_LRG`; a portrait phone photo appears upright.
- With `--debug`: the TV HEADs then GETs, both report the converted size; no 416, no
  retries. If the TV refuses the still, iterate `PHOTO_FEATURES`/`transferMode` (try
  dropping `DLNA.ORG_PN`, then `Streaming`) and record the working values in `research.md`.
- `cast-tv film.mkv` unchanged.

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 3: Long-lived server, cast supervisor, slideshow, UI shell

### Overview

The process starts the server first and outlives any cast. One supervised task per cast
with replace semantics and the "TV fetched zero bytes" diagnosis; a slideshow engine on top;
the `/api` routes with the error model and diagnostics; the TV picker; the Alpine UI with
three empty tabs whose gates arrive in Phases 4–6. `cast-tv` with no arguments opens the UI;
`cast-tv a.jpg b.heic c.mp4` runs a slideshow from the CLI through the same engine.

### Changes Required:

#### 1. The application object

**File**: `castlib/app.py`

**Intent**: Everything the handler threads share: registry, server, selected renderer,
supervisor, sources (empty dict this phase), settings, the error ring buffer, allowed hosts.

**Contract**: `App.start(port, tv=None)` binds first (on `EADDRINUSE`, GETs
`http://127.0.0.1:<port>/api/status`; if it answers with our `app` name, opens the browser
to it and exits 0, else exits 1 with today's message), starts discovery in a background
thread, prints `http://localhost:<port>/ui/`, `http://<lan-ip>:<port>/ui/` (from `ifaddr`
list in Phase 7; until then `local_ip()` against the TV or the default route) and the
firewall hint, then `webbrowser.open()`. `App.errors.push(CastError)` keeps the last 50 with
timestamps. Settings persist to `config_dir()/settings.json`: `interval` (8), `tv` (ip).

#### 2. Cast supervisor and slideshow engine

**File**: `castlib/supervisor.py`

**Intent**: The poll loop becomes an object per cast, and a show is a loop over casts.

**Contract**: `Cast(app, item, generation)` with `state` in `preparing | starting | playing |
paused | stopped | failed | replaced | cancelled`, `started` latch on `PLAYING`/`PAUSED_PLAYBACK`,
budget 40 s in `TRANSITIONING` else 24 s, `position`/`duration` strings as the TV reports
them (never compared against a zero-padded literal), `reason: CastError | None` set on
failure: if `item.requests == 0` after the budget → `TVError("tv_fetched_nothing", …)` with
the firewall hint; else for video, `explain_failure()`'s reasons. Every SOAP call and every
upstream fetch has its own timeout; nothing waits on the network unbounded.

Ownership: `App.owner` is the current `Cast` or `Show`, `App.generation` an int. `App.cast(item)`
and `App.show(items, interval)` each take the app lock, increment `generation`, cancel the
previous `Show` if one is running (its state → `cancelled`), and submit a task to the
single-worker playback executor. The task: prepare the material (`photos.prepare()` or the
upstream resolve), then check `generation` is still its own; if not, skip without sending
anything (state `cancelled`); otherwise register the item, send `SetAVTransportURI` +
`Play`, mark the previous `Cast` `replaced` (thread stopped, item left registered). The
executor is what orders concurrent requests: the request accepted second wins, and the
earlier one is either skipped (not yet sent) or replaced (already playing).

`Show(app, items, interval)` runs in its own thread and submits each item through the same
executor: photo → wait `interval`, counted from the moment `Play` returned successfully,
not from the request; video → wait until `state == stopped` after `started`, or `failed`.
Both waits are interruptible: they also end on `replaced` (a manual cast took over) and
`cancelled` (a newer show or `stop`), and then the show ends without casting further. The
0.25 s figure is the reaction time of a wait loop, not a deadline for a thread blocked in a
network call. A queue of one photo holds until `stop`, with no interval. Failed items are
skipped with their error pushed; `prefetch` the next two photos; controls `pause`, `resume`,
`next`, `prev`, `stop`; state `{index, total, current, next, interval, state}` for the API.
Stay-awake hooks are called on start/stop (no-op until Phase 7).

#### 3. API routes

**File**: `castlib/api.py`

**Intent**: The JSON surface the UI polls and drives. Every route runs the Origin/Host check.

**Contract** (all JSON; POST for mutations; errors as `{"error": {code, message, hint}}`):

| Route | Does |
| --- | --- |
| `GET /api/status` | `{app: "cast-tv", version, tv: {ip, name, state}, tvs: [...], cast: {...} \| null, show: {...} \| null, sources: {name: {state, detail}}, addresses: [...]}` |
| `POST /api/tv/discover` | re-runs discovery, returns `tvs` with per-interface counts (Phase 7 fills the interfaces) |
| `POST /api/tv/select` `{ip}` | selects, resolves control URLs, persists |
| `POST /api/cast` `{source, id, quality?}` | resolves the item through the source, registers, casts |
| `POST /api/show` `{items: [{source, id}], interval?}` | starts a show |
| `POST /api/show/<pause\|resume\|next\|prev\|stop>` | controls |
| `POST /api/stop` | stops cast or show, sends `Stop` |
| `GET /api/errors` | the ring buffer |
| `GET /api/settings`, `POST /api/settings` `{interval}` | bounds 2–600 |
| `GET /api/sources/<name>/status`, `POST .../connect`, `POST .../disconnect`, `GET .../list?path=&page=` | delegated to the source (Phases 4–6) |
| `GET /api/sources/<name>/thumb/<source_id>` | calls `Source.thumb()` on every request (so the upstream URL is always fresh) and proxies the bytes with `Cache-Control: private, max-age=3600`; 404 when the source returns `None`, 502 when the upstream refuses; behind the Origin/Host check like every `/api` route, since only the UI asks for it |

A `local` source exists for CLI-registered items only; it is not listable from the API.

#### 4. Static UI

**Files**: `castlib/ui/index.html`, `castlib/ui/app.js`, `castlib/ui/style.css`,
`castlib/ui/alpine.min.js` (vendored, exact version pinned in a comment with its licence)

**Intent**: The five artboards as one page: header (app name, TV name and IP, TV picker
dropdown when several, "no TV found, retry, enter IP" banner when none), three tabs, each
rendering `gate` when its source is not connected and `list` otherwise, a grid with tick
selection that persists across tabs, the cast bar (name, position/duration, stop), the
selection bar (count, clear, interval stepper, "Start show"), the slideshow view (current,
queue, next, HEIC badge, controls), and the diagnostics panel (last errors with time, the
firewall commands for the zero-bytes case, the DTS card with the `eac3` command). Polls
`/api/status` every 1.5 s. Responsive down to phone width. English labels in the repo.

**Contract**: served from an exact-match map of the four files under `/ui/`; no directory
listing, no path traversal possible. Alpine `x-data` holds `selection: [{source, id, name,
kind}]` in memory only.

#### 5. Launch

**File**: `castlib/cli.py`

**Intent**: `cast-tv` with no arguments starts the UI; `cast-tv a.jpg b.heic` (two or more
sources, or one photo with `--show`) starts a show from the CLI and prints its progress;
`python -m castlib ui` for development; a new `-i/--interval` flag.

#### 6. Tests

**Files**: `tests/test_api.py`, `tests/test_supervisor.py`, `tests/test_discovery.py`,
`tests/test_ui.py`

**Contract**: the supervisor is tested against a fake `soap()` returning scripted transport
states (no fake renderer, just the function): `test_supervisor.py::test_started_latch_and_budget`,
`::test_zero_requests_is_firewall_diagnosis`, `::test_replace_keeps_old_item`,
`::test_show_order_is_selection_order`, `::test_show_waits_for_video_end`,
`::test_show_skips_failed_item`, `::test_show_prefetches_next_photos`,
`::test_stale_task_skipped_after_prepare` (a slow prepare finishes after a newer cast: no
SOAP sent), `::test_manual_cast_cancels_show`, `::test_new_show_cancels_show`,
`::test_show_wait_ends_on_replaced`, `::test_single_photo_show_holds_until_stop`,
`::test_interval_counts_from_play` (fake `soap()` sleeps 3 s; a 5 s interval ends 8 s in); `test_api.py::
test_status_shape`, `::test_settings_interval_bounds`, `::test_errors_ring_buffer`,
`::test_mutations_require_post`, `::test_thumb_route_proxies_and_404s` (Phase 4, with the
first source); `test_discovery.py::test_select_and_persist`,
`::test_addrinuse_attaches_to_running_instance`; `test_ui.py::test_static_exact_match_only`,
`::test_root_redirects`.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/` passes.
- `cast-tv` with no arguments prints two addresses and exits cleanly on Ctrl+C with the TV
  stopped (scriptable with a timeout).

#### Manual Verification:

- Open the UI on the laptop and on the phone; both show the TV in the header.
- `cast-tv a.jpg b.heic c.mp4 -i 5`: photos hold 5 s, the video plays to the end, the show
  ends, the TV returns to its input; the UI shows the show's progress meanwhile.
- Start a cast from the CLI, then press Stop in the UI; then cast from the UI while a CLI
  cast plays; the replaced cast does not 404 in `--debug`.
- Block port 8895 in firewalld, cast: within 30 s the UI shows "TV fetched zero bytes" with
  the `firewall-cmd` line.
- Unplug the TV: the header shows it unreachable; retry finds it again.

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 4: GoPro tab

### Overview

The first source on the `Source` contract. Token paste gate, verified on entry, age shown,
401 reopens it over the still-visible list. Listing with kind from the API, variant choice
with the "too heavy" warning, thumbnails probed and used when present.

### Changes Required:

#### 1. The Source contract

**File**: `castlib/sources/base.py`

**Contract**:

```python
class Source(Protocol):
    name: str
    def status(self) -> dict          # {state: "disconnected"|"connecting"|"connected"|"expired", detail: {...}}
    def connect(self, **params) -> dict   # returns status, or a step for multi-step flows
    def disconnect(self) -> None
    def list(self, path: str | None, page: str | None) -> Listing   # Listing(items: [Entry], folders: [Folder], next: str|None, crumbs: [...])
    def resolve(self, source_id: str, quality: str = "auto") -> MediaItem  # unregistered; resolve callable inside
    def thumb(self, source_id: str) -> Upstream | None
```

`Entry` is the grid shape: `{source, id, name, kind, date, width, height, duration, size,
thumb: str | None, warn: str | None, variants: [...] | None}`; `thumb` is the path
`/api/sources/<name>/thumb/<source_id>` when the source can produce one, else `None` and
the grid shows a placeholder tile. `AuthError` from any method flips
`status.state` to `expired`.

#### 2. GoPro source

**File**: `castlib/sources/gopro.py`

**Intent**: `token()`, `save_token()`, `api()`, `list_media()`, `_rank()`, `library_url()`
and `share_url()` from `cast-gopro`, on the contract, without exits.

**Contract**: `connect(token=...)` saves (de-duplicating a double paste as today, mode 0600)
and verifies with `/media/search?per_page=1`; `status()` reports `stored_at` (file mtime)
and `verified_at`. `list(page)` requests the existing fields plus whatever the probe below
finds for thumbnails and dimensions; kind maps `type` values case-insensitively: video-like
(`video`, `mp4`, `multiclipedit`, `timelapsevideo`, `looping`) → `video`; `photo`, `burst`,
`timelapse`, `livephoto` → `photo`; unknown → hidden and logged once. **Probe at
implementation time**: fetch one item without a `fields` filter, record the key names and
any thumbnail link in `research.md`, then wire thumbnails; if none exists, `thumb()` returns
`None` and the grid shows a placeholder tile. **Second probe, same session**: call the
`download` endpoint for one `photo`, one `burst` and one `livephoto` (whichever the account
has) and record the variant shapes in `research.md`; the recorded JSON becomes the fixture
for `test_resolve_photo_variant`. `resolve(id, quality)` for video keeps `library_url()`'s
ranking and the octet-stream acceptance; for photos a new `photo_url()` ranks the image
variants (`source` first, then the largest by `width`), probes the winner with
`probe_media` and accepts it when `is_allowed_photo(content_type)`; a `livephoto` yields its
still, not its clip. The `MediaItem.resolve` callable re-calls `library_url` / `photo_url`
(signed URLs expire). "Too heavy": `warn` is set when `file_size * 8 / duration > 60 Mbit/s`, and
`variants` lists `source` and `proxy` with the source marked "not recommended"; `quality`
defaults to `proxy` for such items and the UI shows the choice, as in the mockup.

#### 3. CLI parity

**File**: `castlib/cli.py`

**Intent**: `cast-gopro` subcommands call the source in process; `--token`, listing, `<n>`,
`-q`, `--url-only`, share links unchanged.

#### 4. UI gate and list

**Files**: `castlib/ui/app.js`, `castlib/ui/index.html`

**Intent**: The GoPro gate (three-step instructions, paste field, "Save token"), the
connected header line ("token stored 3 h ago"), the expired banner over the list, the grid
with duration/size/resolution and the variant chooser on heavy items.

#### 5. Tests

**File**: `tests/test_gopro.py` (recorded JSON fixtures under `tests/fixtures/gopro/`)

**Contract**: `::test_401_flips_to_expired`, `::test_kind_mapping`, `::test_heavy_item_defaults_to_proxy`,
`::test_resolve_reranks_each_call`, `::test_resolve_photo_variant` (over the probed
fixture; a `livephoto` resolves to its still), `::test_double_paste_deduplicated`.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/` passes.
- `cast-gopro` (listing) and `cast-gopro 1 --url-only` work as before with a live token.

#### Manual Verification:

- Paste a token in the gate: the list appears with thumbnails (or placeholders); the header
  says how old the token is.
- Cast a heavy source clip: the proxy is preselected and plays; choose the source: the
  warning shows and the TV's refusal is reported within the budget.
- Wait for the token to expire (or paste garbage): the banner appears, the list stays, a
  new paste restores it without leaving the tab.
- From the phone: paste works, cast works.

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 5: OneDrive tab

### Overview

Device code sign-in that works from laptop and phone alike, tokens refreshed silently,
whole-drive folder navigation with paging and thumbnails, photos and videos only, download
URLs resolved when the media opens.

Prerequisite (one-time, by the owner): an Entra app registration with **Supported account
types** including personal Microsoft accounts, platform **Mobile and desktop applications**,
and **Allow public client flows = Yes** (Authentication → Advanced settings). The
Application (client) ID is not a secret and ships as the default in `castlib/sources/onedrive.py`;
`ONEDRIVE_CLIENT_ID` overrides it.

### Changes Required:

#### 1. Token store and device code flow

**Files**: `castlib/auth/tokens.py`, `castlib/auth/devicecode.py`

**Contract**: `TokenStore(name)` reads/writes `config_dir()/<name>.json` with mode 0600,
fields `access_token`, `expires_at`, `refresh_token`, `account`, `scope`; `get_access_token()`
refreshes when within 60 s of expiry or on demand. `devicecode.start(client_id, scopes,
tenant="consumers") -> {user_code, verification_uri, expires_in, interval, message,
device_code}`; `devicecode.poll(...)` implements the five documented error codes: keep
polling on `authorization_pending`, add 5 s on `slow_down`, stop with `AuthError` on
`authorization_declined`, `expired_token`, `bad_verification_code`. Refresh:
`grant_type=refresh_token` at the same token endpoint; `invalid_grant` → `AuthError`, state
`expired`.

#### 2. OneDrive source

**File**: `castlib/sources/onedrive.py`

**Contract**: scopes `Files.Read offline_access User.Read`; `connect()` starts the device
flow and returns `{step: "code", user_code, verification_uri, expires_in}`; a background
thread polls and the status flips to `connected` with `detail.account` from `/me`
(`displayName`, `userPrincipalName`). `list(path=None|item_id, page=None)` calls
`/me/drive/root/children` or `/me/drive/items/{id}/children` with
`$select=id,name,size,lastModifiedDateTime,folder,file,image,photo,video&$expand=thumbnails($select=medium,large)&$top=200`,
follows `@odata.nextLink` as `page`; folders always listed; kind: `video` facet → video;
`image` or `photo` facet, or `file.mimeType` starting `image/`, **and**
`is_allowed_photo(file.mimeType)` → photo (raw formats have no `image` facet, `image/gif`
fails the filter; both are hidden by `test_kind_from_facets`); others hidden. `resolve(id)`
builds a `MediaItem` whose `resolve` callable GETs `/me/drive/items/{id}?$select=id,@microsoft.graph.downloadUrl`
and returns `Upstream(url)` with no headers; width/height from `image`/`video`, duration
and bitrate from `video`, `warn` from bitrate > 60 Mbit/s as for GoPro. `thumb(id)` returns
the `large` thumbnail URL as an `Upstream` (proxied by the server; the URLs are
pre-authenticated but short-lived).

#### 3. UI gate

**Intent**: The gate shows `verification_uri` and the code large, "waiting for
confirmation…", then "signed in as … — show files"; the phone copy says the code is entered
in that phone's browser. Breadcrumbs and "load more" in the list.

#### 4. Tests

**File**: `tests/test_onedrive.py` (recorded Graph JSON fixtures, a stub token endpoint)

**Contract**: `::test_devicecode_polling_errors`, `::test_devicecode_expired`,
`::test_refresh_on_401`, `::test_list_pages_nextlink`, `::test_folders_and_media_only`,
`::test_download_url_resolved_on_open` (the resolver is called on open, not on list),
`::test_token_file_mode_0600`.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/` passes.

#### Manual Verification:

- Sign in from the phone: enter the code on the phone; the laptop UI flips to connected.
- Browse to a Camera Roll with more than 200 items: "load more" works, thumbnails show.
- Cast a HEIC from OneDrive: upright, converted; cast a 4K video: plays; seek an hour into
  a film after leaving it paused for over an hour: the relay re-resolves and playback
  continues.
- Revoke the app in the Microsoft account: the next call flips the gate to expired with a
  message.

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 6: Google Photos tab

### Overview

Loopback OAuth with PKCE and a refresh token, once, on the host. Then "Pick" opens a Picker
session whose URL can be opened on any device; the picked items land in the grid; photos are
fetched whole and videos relayed, both with the Bearer header; sessions are deleted at exit.
The share-link paste stays as the fallback for links from other people's libraries.

Prerequisite (done 2026-09-09 by the owner): Cloud project `cast-tv`, consent screen
External/Testing with the owner as test user, Photos Picker API enabled, a **Desktop app**
OAuth client. The downloaded `client_secret_*.json` is copied to `config_dir()/google-client.json`
(`GOOGLE_CLIENT_JSON` overrides the path). Google's own docs say installed apps cannot keep
this secret confidential; it is still stored 0600 and never logged.

### Changes Required:

#### 1. Loopback flow

**File**: `castlib/auth/loopback.py`

**Intent**: The spike's `loopback_flow()` as a library function that runs inside the server
process.

**Contract**: `start(client) -> {auth_url, port}` binds `127.0.0.1:0`, builds the consent URL
with `scope=photospicker.mediaitems.readonly`, `access_type=offline`, PKCE S256 and a `state`;
the server calls `webbrowser.open(auth_url)` itself and returns the URL for display with a
note that it must be opened on this machine; `wait(timeout=300)` returns the code or raises
`AuthError("consent_timeout")`; the token exchange sends `client_secret` and `code_verifier`.
If the token response lacks `refresh_token` (a repeat consent), retry once with
`prompt=consent`. Tokens go to `TokenStore("google")`.

#### 2. Google Photos source

**File**: `castlib/sources/gphotos.py`

**Contract**: `connect()` runs the loopback flow (`status` reports `connecting` with the
URL, then `connected`). `pick()` (exposed as `POST /api/sources/gphotos/pick`) POSTs
`/v1/sessions` with `{}` and returns `{pickerUri, session_id}`; a background thread polls
`/v1/sessions/{id}` at `pollingConfig.pollInterval` until `mediaItemsSet` or
`pollingConfig.timeoutIn`, then lists `/v1/mediaItems?sessionId=&pageSize=100` with
`pageToken` and merges `Entry`s by media id (kind from `type`; name from `mediaFile.filename`;
dimensions from `mediaFile.mediaFileMetadata`; date from `createTime`; a `PHOTO` whose
`mediaFile.mimeType` fails `is_allowed_photo` is hidden): the source keeps
`picks: dict[id, Entry]` in first-pick order plus `sessions: dict[session_id, {expireTime,
ids}]`; an id seen again keeps its position and gains the new session. `list()` returns
the accumulated picks for this process. `thumb(id)` → `Upstream(baseUrl + "=w400-h400",
{"Authorization": "Bearer …"})`. `resolve(id)` → photo: `baseUrl=d`; video: `baseUrl=dv`;
both with the Bearer header, the callable re-lists any still-valid session containing the
id for a fresh `baseUrl` when the stored one is older than 50 min or answers 403; a session
that has expired (`expireTime` passed or 404) is dropped, and an item left with no valid
session is marked `warn: "re-pick"`. `disconnect()` and process
exit (`atexit`) DELETE every session. `RESOURCE_EXHAUSTED` → `UpstreamError` on the gate. The
share-link path (`castlib/sources/sharelink.py`, the moved scraper) is reachable from a paste
field on the same tab and yields video items only.

#### 3. UI gate and grid

**Intent**: Gate: "Connect Google Photos" with the copyable URL and the on-host note; once
connected: a "Pick in Google Photos" button that shows the `pickerUri` as a link and QR-less
copy text ("open on this phone" works because the phone is already on the UI), a spinner
while waiting, then the grid of picks; "Pick more" appends; the paste field below.

#### 4. CLI parity

**Intent**: `cast-photos <link>` keeps working through `sharelink`; `cast-photos --pick`
is a new subcommand that connects (if needed), opens a pick, waits, lists, and casts the
chosen number, mirroring `cast-gopro`.

#### 5. Tests

**File**: `tests/test_gphotos.py` (stubbed Picker endpoints and token endpoint)

**Contract**: `::test_loopback_pkce_and_state`, `::test_connect_timeout`,
`::test_refresh_token_missing_retries_with_prompt_consent`, `::test_pick_polls_until_set`,
`::test_pick_timeout`, `::test_pick_not_persisted`, `::test_bearer_on_fetch_and_relay`,
`::test_baseurl_refreshed_after_50min`, `::test_session_expired_marks_items`,
`::test_repick_merges_by_media_id` (S1 and S2 share an id, S1 expires, the item stays
castable through S2 and is not duplicated), `::test_sessions_deleted_on_disconnect`.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/` passes.

#### Manual Verification:

- Connect on the laptop; restart the app: still connected, grid empty.
- Pick five photos and one video on the phone: they appear in the laptop grid within the
  poll interval; a slideshow over them plays photos and the video.
- Leave the app running past 60 min and cast a picked photo: it still plays (re-listed).
- Paste a public share link: the video plays as before.

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 7: Packaging, Linux and Windows

### Overview

`pipx install` on both platforms, config paths via platformdirs, multi-interface SSDP with
per-interface reporting, firewall hints where they help, stay-awake shims, utf-8 everywhere,
a CI matrix, and the README rewritten for the UI.

### Changes Required:

#### 1. Entry points and dependencies

**File**: `pyproject.toml`

**Contract**: `[project.scripts]` `cast-tv = "castlib.cli:main_tv"`, `cast-gopro =
"castlib.cli:main_gopro"`, `cast-photos = "castlib.cli:main_photos"`; dependencies
`pillow`, `pillow-heif`, `ifaddr`, `platformdirs`; package data includes `castlib/ui/*`.
The root shims stay for the symlink install and for development.

#### 2. Paths

**File**: `castlib/config.py`

**Contract**: `config_dir()` = `platformdirs.user_config_dir("cast-tv")`, `cache_dir()` =
`user_cache_dir("cast-tv")`. Linux resolves to the paths used today (no migration);
Windows to `%APPDATA%\cast-tv` and `%LOCALAPPDATA%\cast-tv\Cache`.

#### 3. Discovery across interfaces

**File**: `castlib/discovery.py`

**Contract**: enumerate IPv4 addresses with `ifaddr`, skip loopback and link-local, send
M-SEARCH from a socket bound to each with `IP_MULTICAST_IF`, collect responses across all,
and return `interfaces: [{name, ip, responses}]` alongside the renderers for the UI's "no TV
found" state. `SO_REUSEADDR` only when `sys.platform != "win32"`.

#### 4. Firewall and stay-awake

**Files**: `castlib/platform.py`, `castlib/supervisor.py`, `castlib/app.py`

**Contract**: `firewall_hint()` returns the `netsh advfirewall` line on Windows and the
`firewall-cmd` line on Linux; printed at startup and embedded in the zero-bytes diagnosis.
`StayAwake.start()/stop()`: Linux spawns `systemd-inhibit --what=idle:sleep --who=cast-tv
--why="casting" sleep infinity` when `systemd-inhibit` exists, killed on stop; Windows calls
`SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)` from a
dedicated thread that stays alive until stop, then resets to `ES_CONTINUOUS`. Called by the
supervisor around casts and shows.

#### 5. Encoding audit

**Intent**: every `open()` in `castlib/` passes `encoding="utf-8"` for text; a test greps
for violations.

#### 6. CI and README

**Files**: `.github/workflows/test.yml`, `README.md`

**Contract**: matrix `ubuntu-latest` × `windows-latest`, Python 3.12, `pip install -e .[test]`,
`python -m pytest`. README: install via `pipx install git+…` on both platforms, the UI
section, per-source setup (GoPro token, Entra registration, Google client JSON), firewall
notes, the limitations list updated for photos and HEIC.

#### 7. Tests

**Files**: `tests/test_platform.py`, `tests/test_config.py`

**Contract**: `test_config.py::test_paths_per_platform` (monkeypatched platform),
`::test_utf8_everywhere` (source grep); `test_platform.py::test_multicast_socket_per_interface`
(socket calls mocked), `::test_firewall_hint_text`, `::test_stay_awake_lifecycle` (calls
mocked).

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/` passes on `ubuntu-latest` and `windows-latest` in Actions.
- `pipx install .` on Fedora puts `cast-tv` on the path; `cast-tv --list` works.

#### Manual Verification:

- On a Windows machine: `pipx install git+…`, `cast-tv` opens the UI, the firewall prompt
  is accepted, the TV is found on the Wi-Fi interface (the "no TV found" state lists the
  virtual adapters with 0 responses when it is not), a cast plays, a 30-minute slideshow
  does not let the machine sleep.
- On Fedora: a 30-minute slideshow does not let the laptop sleep; `Ctrl+C` releases the
  inhibitor.

---

## Testing Strategy

### Unit Tests:

- Registry atomicity, uniqueness, eviction; range parsing including the three verified bugs;
  MIME/kind/DIDL per kind; photo conversion, orientation, cache bounds, concurrency bound;
  supervisor state machine on scripted transport states; slideshow ordering and video wait;
  per-source kind mapping over recorded JSON; OAuth flows against stub endpoints; token
  store permissions; config paths per platform.

### Integration Tests:

- The in-process server fixture serves every phase: media token, Origin/Host, JSON framing
  under keep-alive (two requests on one connection), HEAD/GET agreement for converted
  photos, relay 206 synthesis and Bearer forwarding against a local stub upstream, API
  routes end to end with a fake `soap()`.

### Manual Testing Steps:

1. After Phase 2: three JPEGs and one HEIC on the Samsung, `--debug` on; adjust the photo
   DLNA constants if refused; record the outcome in `research.md`.
2. After Phase 3: the slideshow from the CLI, replace-while-playing, the firewall diagnosis,
   the TV picker with the TV off and on.
3. After each source phase: connect from the phone where the flow allows it, cast a photo
   and a video, force the expiry path.
4. After Phase 7: the Windows checklist above.

## Performance Considerations

- Photo conversion is bounded to two workers and prefetches at most two items ahead; a
  200-item folder never spawns 200 decoders.
- Thumbnails are proxied through the host with no caching beyond the browser's; the grid
  requests them lazily (`loading="lazy"`).
- The status poll is one small JSON every 1.5 s per open UI; the supervisor polls the TV
  every 2 s regardless of how many UIs are open.
- Handler `timeout = 30` keeps idle browser keep-alive connections from pinning threads.

## Migration Notes

- Linux config stays at `~/.config/cast-tv`; the GoPro token file is read from its current
  name. Nothing to migrate.
- `castcloud.py` disappears; anyone importing it from outside the repo (nobody, per the
  README) would need to import `castlib` instead.
- The symlink install keeps working through the root shims until pipx replaces it.

## References

- Change notes: `context/changes/cloud-source-ui/change.md`
- Research: `context/changes/cloud-source-ui/research.md` (Code References carry permalinks
  at `1b8d46f`; the 2026-09-09 follow-up has the spike table)
- Spike: `context/changes/cloud-source-ui/spike-picker-oauth.py`
- Design canvas: https://claude.ai/code/artifact/0673495b-4537-4e06-9f72-5ae5511d14fa
- Microsoft device code: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code
- Entra public client setting: https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-app-configuration
- Graph children and driveItem: https://learn.microsoft.com/en-us/graph/api/driveitem-list-children ,
  https://learn.microsoft.com/en-us/graph/api/resources/driveitem
- Picker mediaItems reference: https://developers.google.com/photos/picker/reference/rest/v1/mediaItems
- Relay to reuse: `cast-tv:163-251`; poll loop constraints: `cast-tv:486-518`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Foundations — castlib package, item registry, security boundary

#### Automated

- [x] 1.1 `python -m pytest tests/` passes on Fedora — 31d715d
- [x] 1.2 `python -m pyflakes castlib tests` reports nothing — 31d715d
- [x] 1.3 `./cast-tv --list` prints the TV; `./cast-tv --stop` stops it — 31d715d
- [x] 1.4 Two items in one server both serve; neither replaces the other — 31d715d

#### Manual

- [x] 1.5 `cast-tv film.mkv -s film.srt`, relay, and `--debug` behave as before — 31d715d
- [x] 1.6 Foreign Origin → 403 JSON; wrong media token → 404 — 31d715d

### Phase 2: Photos — kind-aware serving and the materialised pipeline

#### Automated

- [x] 2.1 `python -m pytest tests/` passes
- [x] 2.2 `pip install .` pulls `pillow` and `pillow-heif`

#### Manual

- [x] 2.3 JPEG, HEIC, PNG and a portrait photo show correctly on the Samsung
- [x] 2.4 HEAD and GET agree in `--debug`; photo DLNA values recorded in `research.md`
- [x] 2.5 `cast-tv film.mkv` unchanged

### Phase 3: Long-lived server, cast supervisor, slideshow, UI shell

#### Automated

- [ ] 3.1 `python -m pytest tests/` passes
- [ ] 3.2 `cast-tv` with no arguments prints two addresses and exits cleanly on Ctrl+C

#### Manual

- [ ] 3.3 UI opens on laptop and phone with the TV in the header
- [ ] 3.4 CLI slideshow with photos and a video plays to the end
- [ ] 3.5 Stop from UI, replace from UI, no 404 on the replaced cast
- [ ] 3.6 Firewall block yields the zero-bytes diagnosis with the command
- [ ] 3.7 TV unplugged shows unreachable; retry recovers

### Phase 4: GoPro tab

#### Automated

- [ ] 4.1 `python -m pytest tests/` passes
- [ ] 4.2 `cast-gopro` listing and `--url-only` work with a live token

#### Manual

- [ ] 4.3 Token paste shows the list with thumbnails or placeholders and the token age
- [ ] 4.4 Heavy clip preselects proxy; source choice reports the refusal
- [ ] 4.5 Expired token shows the banner over the list; re-paste restores it
- [ ] 4.6 Paste and cast from the phone

### Phase 5: OneDrive tab

#### Automated

- [ ] 5.1 `python -m pytest tests/` passes

#### Manual

- [ ] 5.2 Device code sign-in completed from the phone
- [ ] 5.3 Folder with more than 200 items pages; thumbnails show
- [ ] 5.4 HEIC and 4K video cast; relay re-resolves after an hour
- [ ] 5.5 Revoked app flips the gate to expired

### Phase 6: Google Photos tab

#### Automated

- [ ] 6.1 `python -m pytest tests/` passes

#### Manual

- [ ] 6.2 Restart keeps the connection, empties the grid
- [ ] 6.3 Pick on the phone lands in the laptop grid; slideshow plays photos and the video
- [ ] 6.4 Picked photo casts after 60 minutes
- [ ] 6.5 Share link still plays

### Phase 7: Packaging, Linux and Windows

#### Automated

- [ ] 7.1 Tests pass on `ubuntu-latest` and `windows-latest`
- [ ] 7.2 `pipx install .` on Fedora puts `cast-tv` on the path

#### Manual

- [ ] 7.3 Windows: pipx install, UI opens, firewall accepted, TV found, cast plays, 30-min slideshow without sleep
- [ ] 7.4 Fedora: 30-min slideshow without sleep; Ctrl+C releases the inhibitor
