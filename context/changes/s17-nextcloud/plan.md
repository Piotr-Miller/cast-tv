# Cast photos and videos from a Nextcloud server Implementation Plan

## Overview

A fourth cloud tab, **Nextcloud**, that works like OneDrive: the owner types the server address,
approves cast-tv in the browser (Login Flow v2, nothing copied), browses folders over WebDAV and
casts photos (HEIC included) and films through cast-tv's relay. Every signed-in tab gains a
**Disconnect** control. A refused remote film is probed through cast-tv's own media address, so the
diagnosis can read a film whose source needs a password.

Revised 2026-11-24 after `reviews/plan-review.md` (F1-F9); each fix is cited where it lands.

## Current State Analysis

The frame (`frame.md`, Confidence HIGH) confirmed the initial framing:

| Dimension | Verdict | Evidence |
| --- | --- | --- |
| Sign-in with Login Flow v2 | STRONG | `research.md` spike 1: poll 200 after 40 s with `appPassword`, `loginName`, `server`; once only; revoke 200, then 401 |
| WebDAV browsing | STRONG | spike 2: `PROPFIND` 207 with type, size, mtime, `oc:fileid`, `nc:has-preview`; `/core/preview` JPEG for JPEG and HEIC, 404 for films |
| Playback through the relay | STRONG | spike 3 route A: an H.264 film, upstream 200 then 13 × 206, played to `Finished.`; route B (direct HTTPS link to the TV) did not play |
| The owner's OM films play | STRONG | verification 2026-11-24 20:00-20:02: three OM MOVs (HEVC Main 10 4K60, PCM) played with picture and sound as **local files**; an OM film through the Nextcloud relay is still unproven (row 3.9) |

The owner wants the OM camera films from this tab (frame, Narrowing Signals).

What exists (origin `code` unless stated):

- The `Source` contract (`castlib/sources/base.py:60-68`), including `resolve(source_id, quality="auto")`.
  Sources are a hand-written dict in `castlib/app.py:187-188`; the routes in `castlib/api.py:228-271`
  serve whatever is in it, `disconnect` included (`api.py:248`).
- `OneDriveSource` (`castlib/sources/onedrive.py`) is the pattern: a generation counter, a sign-in
  thread with a stop event, a connecting/connected/expired/disconnected status, an LRU of listed
  items (4000), crumbs, a thumbnail `Upstream`. It keeps Graph's item order; it does not sort.
- Credentials: `TokenStore` (`castlib/auth/tokens.py:43-44`) treats a file without `refresh_token`
  as absent. `config.write_private` writes mode 0600 on POSIX; on Windows the file sits in the
  per-user profile (`castlib/config.py:54`, `:107`).
- Headers travel: `Upstream.headers` (`castlib/items.py:19-23`) is sent by the relay
  (`castlib/relay.py:31-38`), the photo fetch (`castlib/photos.py:226-231`) and the thumbnail proxy
  (`castlib/api.py:293-297`), through `BEARER_SAFE` unless the upstream brings its own opener.
  `BEARER_SAFE` drops `Authorization` when a **redirect** changes scheme, host or port
  (`castlib/net.py:28`, `:42`); it does not check the first URL. `NO_REDIRECT` refuses redirects
  (`net.py:16`). Neither validates where the first request goes (review F2).
- The refusal probe (`castlib/supervisor.py:336-355`) runs `ffprobe` on `item.resolve().url` and
  drops `Upstream.headers`; `tests/test_supervisor.py:64` asserts that old address.
- The UI (`castlib/ui/app.js`, `castlib/ui/index.html`):
  - three gate steps (`app.js:253-258`): `code`, `consent`, `browser`; no typed input before a flow;
  - **no Disconnect control for any source** (review F1);
  - `metaOf()` shows size, resolution, duration or MIME, **never a date** (`app.js:679`; review F3);
  - Load more appends `items` but keeps the first page's `folders` (`app.js:361`; review F4);
  - `openFolder()` clears the list before the request, so a failed load loses it (`app.js:334`, `:366`; review F5);
  - the tile and show controls have no seek (`index.html:134`); seeking is the TV remote's (`prd.md:82`).
- Photo kinds: `PHOTO_MIMES` = JPEG, PNG, HEIC, HEIF, WebP (`castlib/media.py:32`), a cast-tv
  compatibility list; `kind_from_facets` hides everything for an unknown source (`media.py:124`).
- The release workflow runs on a PR only for `packaging/**` and `release.yml` (`release.yml:11-14`);
  it installs `.[window]` (`release.yml:57`), and `packaging/smoke.py` reads `/api/status` from the binary.
- Baseline in the repository's `.venv` (2026-11-24): `pyflakes` exit 0; `pytest` 675 passed /
  6 skipped; `tests/test_supervisor.py` 33 passed; `tests/test_ui.py` 32 passed; `node --check` exit 0.

### Carried from predecessor

none — no Predecessor line

## Definitions

| Term | Decided meaning | Origin | On degenerate data | Verified by |
| ---- | --------------- | ------ | ------------------ | ----------- |
| Server address | What the owner types. A bare host gets `https://`; a trailing `/` is dropped; a subfolder path is kept; `http://`, userinfo (`user@host`) and a malformed authority are refused with a sentence saying why. The result is the one canonical base: `(scheme, host, effective port)` plus path | user (2026-11-24) | `cloud.example.com` → `https://cloud.example.com`; `https://host/nextcloud/` → `https://host/nextcloud`; `http://192.168.50.10` → refused; `https://a@host` → refused; empty → refused | `test_address_normalised`, `test_http_address_refused`, `test_address_userinfo_refused` |
| Same origin | Every URL that will carry or receive the app password (the flow's `login` and `poll.endpoint`, the poll's returned `server`, every absolute DAV `href`) must equal the canonical base's `(scheme, host, effective port)`; otherwise the flow or answer is refused and no credential is sent there. Outgoing URLs are built from the base plus an encoded path, never taken from the server | plan (review F2) | another host, `:8443` against 443, `http://`, a scheme-relative `//evil/x` href → refused | `test_flow_other_origin_refused`, `test_flow_other_port_refused`, `test_poll_server_other_origin_refused`, `test_href_outside_root_refused` |
| Account | One server and one account at a time. `connect({server})` always starts a fresh flow for that address (cancelling a running one for another address); `connect({})` verifies a stored credential, or starts a flow on the stored server when it is expired; a repeated connect during a flow for the same address returns that flow | plan assumption | a late poll answer after a cancel or a new flow is dropped | `test_connect_verifies_stored`, `test_connect_server_starts_fresh_flow`, `test_late_poll_answer_dropped` |
| Folder root | `/remote.php/dav/files/<user id>/`, the user id read from `/ocs/v2.php/cloud/user`, never assumed equal to the login name, and percent-encoded in every path | product (Nextcloud Login Flow docs warn the login name may differ) | login `pat@example.test`, id `pat` → paths use `pat` | `test_login_name_differs_from_user_id` |
| Photo | A file whose `getcontenttype` is in `PHOTO_MIMES` | code (inherited cast-tv list; `prd.md:175` excludes GIF/raw) | GIF, raw, PDF, no type → hidden, logged once without the record | `test_photo_kinds` |
| Video | A file whose `getcontenttype` starts with `video/` | plan assumption | `video/quicktime` → video; `application/octet-stream` `.mp4` → hidden | `test_video_kinds` |
| Tile date | The UTC date part of `getlastmodified`, shown on Nextcloud tiles only, with the tooltip "last modified" | user (2026-11-24; review F3 placement) | missing or unparsable → no date text; `Sat, 01 Nov 2026 23:59:59 GMT` → `2026-11-01` | `test_tile_date_from_last_modified`, `test_nextcloud_tile_shows_date` |
| Listing order | Folders, then files, each by name case-insensitively; ties keep the server's order | plan assumption (OM names sort by time) | `A.JPG`, `a.jpg` → server order between the two | `test_listing_order` |
| Listing contents | The collection's own response is skipped; only `propstat` blocks with status 200 count; a repeated `oc:fileid` keeps its first record | product (WebDAV multistatus) | self entry, a 404 propstat, a duplicate id → none of them shown twice or at all | `test_multistatus_shapes` |
| Page | Every child folder arrives on the first page; media files come 200 per page from one `PROPFIND` snapshot of the folder; `next` is the media offset; a page-less request takes a new snapshot; a malformed or negative offset is refused | plan (review F4) | 0 media → empty; 200 → no `next`; 201 folders + 450 media → 201 folders and 200 media, then 200, then 50 | `test_listing_pages`, `test_empty_folder`, `test_nextcloud_load_more_keeps_folders` |
| Disconnect | Best effort: revoke the app password on the server (`DELETE /ocs/v2.php/core/apppassword`), then forget it locally even when the revoke fails; a failed revoke is kept in the status (`revoke_error`) until the next connect and shown on the gate | user (2026-11-24) | server unreachable or answers 5xx → local file gone, the note says the entry may remain under Settings → Security | `test_disconnect_revokes_then_forgets`, `test_disconnect_unreachable_still_forgets`, `test_disconnect_shows_revoke_error` |
| Expired | A 401 from the server on a call the source makes itself (OCS, `PROPFIND`, `SEARCH`); there is no refresh. A 401 on media or a preview stays that request's error | product (Login Flow v2 docs) | a folder opened after revocation → expired banner over the **previous** list and crumbs; **Connect again** starts a flow on the stored server | `test_revoked_password_expires`, `test_nextcloud_failed_folder_keeps_list` |

## Desired End State

- On the Nextcloud tab, the owner types `cloud.example.com`, presses **Connect**, opens the gate's
  link (on this computer or the phone) or uses **Copy link**, grants access, and the tab lists the
  root folders without anything copied. The credential sits in `config_dir()/nextcloud.json`, mode
  0600 on POSIX.
- Folders open with crumbs; every child folder is reachable; **Load more** brings more photos and
  films; photo tiles carry the server's preview (HEIC included); films show the placeholder;
  Nextcloud tiles show the last-modified date.
- A cast photo is converted as today; a cast film streams through the relay with Range; a slideshow
  mixes both; seeking works from the Samsung remote.
- Every connected or expired tab has **Disconnect**. On Nextcloud it removes cast-tv's entry from the
  server's Settings → Security when the server answers, and says so when it does not.
- A password revoked on the server turns the tab into the expired banner over the last list;
  **Connect again** works without retyping.
- When the TV refuses a remote film, ffprobe reads it through cast-tv's media address, so its
  diagnosis (when ffprobe is installed and finds a reason) reaches the error for every source.

### Key Discoveries:

- `TokenStore` discards a file without a refresh token (`castlib/auth/tokens.py:43-44`).
- Media headers already travel; the redirect guard is not a first-request guard (`castlib/net.py:28-47`).
- `/m/<token>/<id>` is dispatched before the Host/Origin check (`castlib/server.py:3-5`, `:187-191`),
  and `_never_started()` is evaluated before `_finish` retires the item (`castlib/supervisor.py:322`).
- Four shared UI behaviours need changing for the end state: no Disconnect, no date, folders lost on
  Load more, list lost on a failed folder open (review F1, F3-F5).

## What We're NOT Doing

- Plain-HTTP servers, several servers or several accounts at once.
- EXIF capture dates, video thumbnails, a "too heavy" warning (WebDAV has no bitrate). OneDrive's
  60 Mbit/s warning flags OM films that do play; that heuristic is not changed here.
- Dates on other sources' tiles (owner decision 2026-11-24).
- Handing the TV a Nextcloud direct link (spike 3 route B did not play).
- SSO integrations beyond what Login Flow v2 does in the browser (two-factor login happens there).
- The local-folder source (s18).

## Implementation Approach

Build the engine first and test it against a scripted Nextcloud on localhost, as `test_onedrive.py`
does for Graph; it adds `defusedxml` and proves the release build carries it. Then move the refusal
probe; then the UI (the tab, Disconnect for all, date, paging and failed-navigation fixes); then the
documents. The source is registered in Phase 1, so its routes answer before the tab appears.

All commands run with the repository's `.venv` active (`AGENTS.md`, Commands).

## Critical Implementation Details

- **The password goes only to the canonical origin.** Calls that carry it (`PROPFIND`, `SEARCH`, OCS,
  `DELETE`) use `NO_REDIRECT`; media and previews use `BEARER_SAFE`, which follows a cross-origin
  redirect only after dropping `Authorization`. Both start from URLs cast-tv builds from the base.
- **XML from the server.** Read at most 32 MiB + 1 byte; more is refused before parsing, and a
  truncated prefix is never parsed. Parse with `defusedxml.ElementTree.fromstring(data,
  forbid_dtd=True, forbid_entities=True, forbid_external=True)`: DTD rejection is off by default and
  must be set. `defusedxml` does not replace Expat's own security updates; the runtime's Expat is
  kept current as Python ships it. A parse failure becomes `UpstreamError("nextcloud_xml")` with a
  generic message: no raw answer, no header, no record.
- **The app password is never printed, logged, returned, or put on a command line.** The probe's
  media URL carries cast-tv's per-run media token, not a provider credential (`server.py:385`).
- **A failed folder open keeps the old list** (shared `openFolder`): the new path, items, folders and
  crumbs replace the old ones only after a successful answer.

## Phase 1: The Nextcloud engine

### Overview

Login Flow v2, the credential file and a WebDAV source on the `Source` contract, registered in the
app, with `defusedxml` as a dependency the release build is proven to carry; no UI yet.

### Changes Required:

#### 1. Login Flow v2 and app-password calls

**File**: `castlib/auth/loginflow.py`

**Intent**: The network half of the sign-in, with no state: start a flow, poll it, read the user id,
revoke a password; and the address rule.

**Contract**: `normalise(address) -> Base` (scheme, host, port, path; `ConfigError("http_refused" |
"bad_address")`); `same_origin(base, url) -> bool` over `(scheme, host, effective port)`;
`start(base) -> {login, endpoint, token, expires_at}` (`POST <base>/index.php/login/v2`, User-Agent
`cast-tv`; `login` and `endpoint` must be same-origin); `poll(flow, stop) -> {server, loginName,
appPassword}` (every 2 s, 20 min; the returned `server` must be same-origin; `AuthError("cancelled" |
"flow_expired")`); `user(base, login, password) -> {id, displayname}` (`GET
/ocs/v2.php/cloud/user?format=json`, `OCS-APIRequest: true`); `revoke(base, login, password)`.
`AuthError` on 401, `UpstreamError` otherwise; no message carries a response body or header.

#### 2. The credential file

**File**: `castlib/auth/apppassword.py`

**Intent**: Keep `{server, login, user_id, password, account}` in `config_dir()/nextcloud.json` via
`config.write_private`, in memory after the first read.

**Contract**: `AppPasswordStore(name)` with `load()`, `exists()`, `save(record)`, `clear()`; a file
missing `server`, `login`, `user_id` or `password` counts as absent.

#### 3. The source

**Files**:
- `castlib/sources/nextcloud.py` — `NextcloudSource`, `name = "nextcloud"`; imports `defusedxml` at module level.
- `castlib/media.py` — a `"nextcloud"` branch in `kind_from_facets`, from `getcontenttype`.
- `castlib/app.py` — the registry entry.
- `castlib/items.py` — the `source` comment names `nextcloud`.

**Intent**: Map WebDAV onto the contract as Definitions say: `connect` per the Account row (step
`"login"` with `login_url`, `expires_in`, `server`); `disconnect` per the Disconnect row; `list` per
the Listing contents, Order and Page rows, crumbs from the path's segments; `resolve(source_id,
quality="auto")` returning a `MediaItem` whose `resolve` gives `Upstream(<url built from base +
encoded href path>, {"Authorization": "Basic …"})`; `thumb` returning the
`/index.php/core/preview?fileId=<id>&x=512&y=512&a=1` upstream when `nc:has-preview` is true, else `None`.

**Contract**:
- `path` is relative to the files root: no leading `/`, no `.`/`..` segment, no control character
  (`ConfigError("bad_path")`). A decoded `href` must lie under the root at a segment boundary.
- A file id is its `oc:fileid` (digits only); its href lives in an LRU of 4000; an unknown id is
  looked up once with `SEARCH` on `oc:fileid`, else `NotMedia("unknown_item")`.
- `version` = `getetag`; `mime` = `getcontenttype`; `size` = `getcontentlength`; `date` per Tile date.
- A 401 on the source's own calls raises `AuthError("nextcloud_unauthorized")` and sets `expired`.
- Status: `connecting` (`detail.step = "login"`, `login_url`, `expires_in`, `server`); `connected` /
  `expired` (`detail.account` = `displayname (login)`, `server`); `disconnected` may carry
  `detail.revoke_error` and `detail.server` (the last address, to prefill the form).

#### 4. The dependency and the release check

**Files**:
- `pyproject.toml` — `defusedxml` in `dependencies`, with the version floor current on the day it lands.
- `packaging/smoke.py` — `/api/status` must list a `nextcloud` source (the module and `defusedxml` loaded in the binary).
- `.github/workflows/release.yml` — `pyproject.toml` joins the `pull_request` paths, so a dependency change builds the release on its PR.

**Intent**: The shipped Nuitka file carries `defusedxml` and starts with the new source; a later
dependency change is checked the same way.

**Contract**: the smoke line reads `/ui/ 200, /api/status 200, gphotos <state>, nextcloud <state>`.

#### 5. Tests

**Files**: `tests/test_nextcloud.py`, `tests/fixtures/nextcloud` — a scripted Nextcloud on localhost
(Login Flow, OCS, `PROPFIND`/`SEARCH`, preview, `DELETE`), fixture XML in the spike's shapes (folders
with `oc:size`, JPEG, HEIC, `video/quicktime`, GIF, PDF, a name with a space and `Ł`, the collection's
self entry, a 404 propstat, a duplicate id), plus hostile XML fixtures.

**Intent**: Every Definitions row's named test, and:
- XML: an internal DTD, an internal entity, an external entity, malformed XML, 32 MiB + 1 byte, and a
  valid answer with unusual namespace prefixes — the hostile ones refused, the valid one parsed;
- the password: inject a synthetic password into the scripted server's error bodies, then assert it
  appears in no `as_dict()`, status, API response, error-ring entry, captured stdout/stderr, or
  mocked `subprocess` argument;
- `resolve` sending Basic and Range, and the relay serving a 206 from the scripted server;
- the file mode 0600 on POSIX (skipped on Windows, as `test_config.py:76` does).

**Contract**: the Definitions' test names, plus `test_xml_dtd_refused`, `test_xml_entities_refused`,
`test_xml_malformed_refused`, `test_xml_oversize_refused`, `test_xml_namespaces_parsed`,
`test_password_never_exposed`, `test_resolve_sends_basic_and_range`, `test_credential_file_private`,
`test_unknown_file_id_found_by_search`, `test_thumb_none_without_preview`.

### Success Criteria:

#### Automated Verification:

- The Nextcloud tests pass: `python -m pytest tests/test_nextcloud.py` — not run: needs Phase 1 output
- The whole suite passes: `python -m pytest` — at planning: exit 0
- pyflakes is clean: `python -m pyflakes castlib tests` — at planning: exit 0
- (external) The release build and smoke test pass on the pull request: GitHub Actions `release.yml` on Ubuntu and Windows — not run: external

---

## Phase 2: Probe a refused remote film through cast-tv's own address

### Overview

The refusal probe reads a remote film from `app.server.media_url(item)`, so the relay adds the
source's headers; local files and downloaded items keep their path.

### Changes Required:

#### 1. The probe target

**File**: `castlib/supervisor.py`

**Intent**: In `_never_started`, a video without `item.path` is probed at its registered media URL
instead of `item.resolve().url`. One path for every remote source; no provider credential on a
command line (the URL carries only cast-tv's media token).

**Contract**: `explain_failure(target)` receives `item.path` when set (local and `download=True`
items), else `app.server.media_url(item)` while `item.id` is set; with no id, no probe. A diagnosis
stays best effort: no ffprobe, no TV request, or no matching heuristic still gives no reason.

#### 2. Tests

**File**: `tests/test_supervisor.py`

**Intent**: Prove the composition, not only the argument: the diagnostic double really GETs a range
of the URL it is given, from a stub upstream that answers 401 without the expected Basic header.

**Contract**: update the existing assertion at `tests/test_supervisor.py:64` (it expects the upstream
address); add `test_refusal_probe_reads_media_url` (bytes received, the header seen upstream, the
hint, the item still registered during the probe), `test_refusal_probe_custom_opener_and_refresh`,
`test_refusal_probe_downloaded_item_uses_path`, `test_refusal_probe_local_path_unchanged`.

### Success Criteria:

#### Automated Verification:

- The supervisor tests pass: `python -m pytest tests/test_supervisor.py` — at planning: exit 0 (33 passed; the new tests are not written yet)
- The whole suite passes: `python -m pytest` — at planning: exit 0
- pyflakes is clean: `python -m pyflakes castlib tests` — at planning: exit 0

---

## Phase 3: The Nextcloud tab, Disconnect, and the shared list fixes

### Overview

The tab and its gate; a Disconnect control on every signed-in tab; the Nextcloud date on tiles;
folders kept across Load more; the last list kept when a folder open fails.

### Changes Required:

#### 1. The Nextcloud gate

**Files**:
- `castlib/ui/app.js` — `SOURCES` and `GATES` entries; `serverInput`; `connecting()` accepts `step === "login"`; the hint line.
- `castlib/ui/index.html` — the address form before a flow, and the `login` step.

**Intent**: Before a flow: an address field (prefilled from `detail.server`) and **Connect**. During
it: "Open this link on any device, sign in to Nextcloud and grant access", the link
(`target="_blank"`), **Copy link** (copies `login_url`, not a code), **Cancel**, minutes left. A
refused address answers in `gateNote` (lesson: a user-action message is not owned by the poll). The
gate's note says cast-tv gets its own app password, listed and revocable under the server's
Settings → Security.

**Contract**: `POST /api/sources/nextcloud/connect` with `{server}`, `{}` for **Connect again**,
`{cancel: true}`.

#### 2. Disconnect on every signed-in tab (review F1)

**Files**: `castlib/ui/app.js`, `castlib/ui/index.html` — a **Disconnect** control in the list
header of a connected or expired tab, and on the expired gate as well (an expired tab with no list
shows the gate, not the header: `listVisible`, `app.js:329-332`; review re-review F10), for all four sources.

**Intent**: Post `/api/sources/<name>/disconnect`; then clear that source's list and its tiles from
the selection, forget `_verified[name]`, refresh the status, and show the gate. On Nextcloud the gate
shows `detail.revoke_error` when present.

**Contract**: the existing route (`castlib/api.py:248`); the gate becomes visible because the list is
cleared (`listVisible`, `app.js:329`).

#### 3. Date, paging and failed navigation (review F3-F5)

**Files**: `castlib/ui/app.js`, `castlib/ui/index.html` (the tile metadata spans gain the tooltip binding)

**Intent**: `metaOf` adds the date for a Nextcloud tile, with the tooltip "last modified"; Load more
appends folders as well as items (Nextcloud sends them all on page one, others are unaffected);
`openFolder` replaces path, items, folders and crumbs only after a successful answer, and
`nextcloud_unauthorized` joins the codes that refresh the status at once (`app.js:368`).

**Contract**: no change to `/api/sources/<name>/list`.

#### 4. UI tests

**File**: `tests/test_ui.py`

**Intent**: In `node`, against scripted answers.

**Contract**: `test_nextcloud_gate_posts_server`, `test_nextcloud_login_step_shows_link`,
`test_nextcloud_copy_link_copies_login_url`, `test_nextcloud_address_note_survives_poll`,
`test_nextcloud_connect_again_posts_empty`, `test_disconnect_every_source` (for each of the four
sources: connected, expired with a list, expired without a list — the control is rendered and posts
the same request),
`test_disconnect_clears_list_and_selection`, `test_disconnect_shows_revoke_error`,
`test_nextcloud_tile_shows_date` (and no date text without one),
`test_nextcloud_load_more_keeps_folders`, `test_nextcloud_failed_folder_keeps_list` (populated list,
open a folder that answers 401: same items and crumbs, expired banner), `test_onedrive_open_folder_unchanged`.

### Success Criteria:

#### Automated Verification:

- app.js parses: `node --check castlib/ui/app.js` — at planning: exit 0
- The UI tests pass (node on the path): `python -m pytest tests/test_ui.py` — at planning: exit 0 (32 passed; the new tests are not written yet)
- The whole suite passes: `python -m pytest` — at planning: exit 0
- pyflakes is clean: `python -m pyflakes castlib tests` — at planning: exit 0

#### Manual Verification:

Setting for every Fedora row: in a terminal on the laptop, the agent starts cast-tv from this branch
with `python -m castlib -d` (the debug log prints each request the TV makes); the cast-tv window opens.
The agent drives that window and Chrome; the owner watches the Samsung and does what needs their
account. Each result goes into `research.md` (row, date, device, material, what was seen) before its
row is ticked. No row shows the contents of `nextcloud.json`.

- In the cast-tv window, click the **Nextcloud** tab, type the server address, click **Connect**; the gate shows a link and **Copy link**. Click the link: the Nextcloud login opens in the system browser (if nothing opens, click **Copy link**, paste into Chrome's address bar, press Enter). The owner signs in and clicks **Grant access**; within 5 s the window's tab lists the root folders. In the terminal, `stat -c %a ~/.config/cast-tv/nextcloud.json` prints `600` — surface: castlib/auth/loginflow.py, castlib/auth/apppassword.py, castlib/sources/nextcloud.py, castlib/ui/app.js, castlib/ui/index.html, castlib/window.py
- In Chrome, on the server, open Settings → Security, the "Devices & sessions" list: an entry for cast-tv is there; record its name as shown — surface: castlib/auth/loginflow.py
- In the window's Nextcloud tab, click the folder buttons `Pictures`, `OM Workspace`, `2026_11_01`: the crumbs read `Nextcloud / Pictures / OM Workspace / 2026_11_01`; the JPEG tiles (e.g. `PB014004.JPG`) show real previews and the date `2026-11-01`; click `video`: `PB014001.MOV` and `PB014042.MOV` show the film placeholder and a date — surface: castlib/sources/nextcloud.py, castlib/ui/app.js, castlib/ui/index.html
- Click the crumb `Pictures`, then `Test_Pictures`; on the tile `shelf-christmas-decoration.heic` click the tile's ▶ button (tooltip "Cast now"): the owner sees the photo upright on the Samsung — surface: castlib/sources/nextcloud.py, castlib/photos.py
- In `Pictures / OM Workspace / 2026_11_01 / video`, click the tile's ▶ button (tooltip "Cast now") on `PB014001.MOV`: the terminal shows `upstream: 200` then `206`s; the owner sees picture and hears sound; at about 0:15 the owner presses the Samsung remote's forward/seek button once: playback resumes later in the film with picture and sound, and runs to the end; the window shows the cast finished — surface: castlib/sources/nextcloud.py, castlib/relay.py
- In `2026_11_01`, tick three JPEG tiles, then in `video` tick `PB014001.MOV`; click **Start show**: the owner sees the three photos and the film on the Samsung in that order; the window shows the show finished — surface: castlib/sources/nextcloud.py, castlib/supervisor.py, castlib/ui/app.js
- Phone sign-in: in the window's Nextcloud tab click **Disconnect** first (the gate with the address field appears). On the phone, scan the QR code under **Open on your phone** in the window (or type the address shown there), open the **Nextcloud** tab, type the server address, tap **Connect**, tap the link, sign in and grant access in the phone's browser; back in the cast-tv page on the phone, the tab lists the root folders — surface: castlib/sources/nextcloud.py, castlib/ui/app.js, castlib/ui/index.html
- Revocation: with the tab listing `Pictures`, in Chrome on Settings → Security click the cast-tv entry's menu and **Revoke**; in the window click the folder `OM Workspace`: the expired banner appears over the `Pictures` list and crumbs, which stay; click **Connect again**: the link step appears without the address field, for the same server — surface: castlib/sources/nextcloud.py, castlib/ui/app.js, castlib/ui/index.html
- Reconnect (grant access), then click **Disconnect** on the Nextcloud tab: the gate appears without a revoke note; Chrome's Settings → Security no longer lists cast-tv; in the terminal, `ls ~/.config/cast-tv/nextcloud.json` reports no such file — surface: castlib/auth/loginflow.py, castlib/sources/nextcloud.py, castlib/ui/app.js
- Disconnect on the other tabs: on each of the **GoPro**, **OneDrive** and **Google Photos** tabs, click **Disconnect**: that tab shows its own gate; then connect it again by its usual button and see its list or picks return — surface: castlib/ui/app.js, castlib/ui/index.html
- Windows (next Windows visit): on Windows 11, start this branch's cast-tv window; on the **Nextcloud** tab type the server address, click **Connect**, click the link (or **Copy link** and paste into Edge); grant access; the tab lists the root folders. Close the window, start cast-tv again: the tab lists the folders without a new sign-in. Click **Disconnect**: the gate appears — surface: castlib/auth/loginflow.py, castlib/auth/apppassword.py, castlib/sources/nextcloud.py, castlib/ui/app.js, castlib/ui/index.html, castlib/window.py

---

## Phase 4: Documents

### Overview

The PRD, the roadmap and the README name the new source and the Disconnect control.

### Changes Required:

#### 1. Product and roadmap

**Files**:
- `context/foundation/prd.md` — an FR line for Nextcloud next to FR-010…FR-013, and the Disconnect control.
- `context/foundation/roadmap.md` — an S-17 row in `## At a glance` and an `### S-17` block (Change ID `s17-nextcloud`), status as the change stands when the phase lands.

**Intent**: The product record names the source and its limits: HTTPS only, last-modified dates,
no video thumbnails, best-effort revoke.

**Contract**: the next free FR id; the roadmap table's columns.

#### 2. README

**File**: `README.md`

**Intent**: How to connect a Nextcloud server and how to remove cast-tv's access (Disconnect, or
Settings → Security), in the window-and-control form of the other sources.

**Contract**: a section beside the OneDrive one.

### Success Criteria:

#### Automated Verification:

- pyflakes is clean: `python -m pyflakes castlib tests` — at planning: exit 0

#### Manual Verification:

- The owner opens `README.md` and `context/foundation/prd.md` on GitHub's PR page ("Files changed"), reads the Nextcloud section and the FR line, and confirms they say: HTTPS only, the last-modified date, no film thumbnails, Disconnect revokes when the server answers — surface: README.md, context/foundation/prd.md

---

## Testing Strategy

### Unit Tests:

- `tests/test_nextcloud.py`: every Definitions row on degenerate data, the origin rules, hostile XML,
  the password's absence from every output sink.
- `tests/test_supervisor.py`: the probe target and its real authenticated read.

### Integration Tests:

- Through the scripted Nextcloud: `resolve` → relay with Basic and Range; `thumb` → the API's
  thumbnail proxy (raster check unchanged); a photo cast → the photo pipeline with headers.
- The release smoke test: the binary lists the `nextcloud` source.

### E2E Tests:

- None: the `node` UI tests cover the UI logic; the real window, browser and TV are manual rows.

### Manual Testing Steps:

1. Phase 3's Fedora rows, in order, in one sitting with the Samsung on.
2. The Windows row at the next Windows visit.
3. Phase 4's reading row on the PR page.

## Performance Considerations

A folder is one `PROPFIND` (the spike: 0.14-0.95 s), kept as a snapshot while its pages are read;
previews are one request per visible tile. 32 MiB bounds the wire answer, not the parsed tree's
memory. A folder with thousands of child folders puts them all on page one.

## Migration Notes

None: a new file in `config_dir()`; existing sources keep their data. Their tabs gain Disconnect.

## References

- Frame: `context/changes/s17-nextcloud/frame.md`
- Research: `context/changes/s17-nextcloud/research.md`
- Review: `context/changes/s17-nextcloud/reviews/plan-review.md`
- Similar implementation: `castlib/sources/onedrive.py`, `tests/test_onedrive.py`
- Login Flow v2: https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html
- WebDAV: https://docs.nextcloud.com/server/latest/developer_manual/client_apis/WebDAV/basic.html
- Python XML security: https://docs.python.org/3/library/xml.html#xml-security

## Progress

> Convention: `- [ ]` pending, `- [x]` done, `- [-]` not applicable (` — n/a: <reason>` required). Append ` — <commit sha>` when a step lands. A Manual row takes ` — accepted at <full sha>` when a human confirms it. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: The Nextcloud engine

#### Automated

- [x] 1.1 The Nextcloud tests pass — e931d9e
- [x] 1.2 The whole suite passes — e931d9e
- [x] 1.3 pyflakes is clean — e931d9e
- [x] 1.4 The release build and smoke test pass on the pull request — e931d9e

### Phase 2: Probe a refused remote film through cast-tv's own address

#### Automated

- [ ] 2.1 The supervisor tests pass
- [ ] 2.2 The whole suite passes
- [ ] 2.3 pyflakes is clean

### Phase 3: The Nextcloud tab, Disconnect, and the shared list fixes

#### Automated

- [ ] 3.1 app.js parses
- [ ] 3.2 The UI tests pass
- [ ] 3.3 The whole suite passes
- [ ] 3.4 pyflakes is clean

#### Manual

- [ ] 3.5 Sign-in from the cast-tv window on Fedora
- [ ] 3.6 Settings → Security lists cast-tv's app password
- [ ] 3.7 Browse an OM folder: crumbs, previews, placeholders, dates
- [ ] 3.8 Cast a HEIC photo from Nextcloud
- [ ] 3.9 Cast an OM film from Nextcloud through the relay, seek with the remote
- [ ] 3.10 A mixed slideshow from Nextcloud
- [ ] 3.11 Sign-in from the phone
- [ ] 3.12 A password revoked on the server shows the expired banner over the last list; Connect again
- [ ] 3.13 Disconnect revokes the app password and removes the file
- [ ] 3.14 Disconnect on the GoPro, OneDrive and Google Photos tabs
- [ ] 3.15 Sign-in, restart and Disconnect in the cast-tv window on Windows

### Phase 4: Documents

#### Automated

- [ ] 4.1 pyflakes is clean

#### Manual

- [ ] 4.2 The owner confirms the README and PRD text
