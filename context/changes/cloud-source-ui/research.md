---
date: 2026-09-08T21:06:30+02:00
researcher: Claude (Fable 5.1), with Piotr Miller
git_commit: 1b8d46f61ed4f4ed156f146d08fb69e442cda295
branch: shape-the-cloud-source-ui
repository: Piotr-Miller/cast-tv
topic: "Turning the one-shot cast-tv CLI into a long-lived local web UI: what the existing server, resolvers and history constrain"
tags: [research, codebase, range-handler, relay, dlna, didl, castcloud, gopro, google-photos, onedrive, picker-api, photos, heic, packaging]
status: complete
last_updated: 2026-09-10
last_updated_by: Claude (Fable 5.1)
last_updated_note: "Phase 2: the Samsung accepted the DLNA-guideline photo profile unchanged (Interactive, OP=00, JPEG_SM|MED|LRG, PNG_LRG); Open Question 1 retired. Phase 1 manual verification record below it"
---

# Research: Turning the one-shot cast-tv CLI into a long-lived local web UI

**Date**: 2026-09-08T21:06:30+02:00
**Researcher**: Claude (Fable 5.1), with Piotr Miller
**Git Commit**: 1b8d46f61ed4f4ed156f146d08fb69e442cda295
**Branch**: shape-the-cloud-source-ui
**Repository**: Piotr-Miller/cast-tv

Method: all four source files (`cast-tv`, `castcloud.py`, `cast-gopro`, `cast-photos`, ~1000 lines)
were read in full in the main context. Two independent passes ran alongside: one over the git
history for constraints that live in commit messages rather than code, one adversarial pass over
`RangeHandler` that **executed** the suspicious paths rather than reasoning about them. Where a
finding below says *verified*, it was reproduced, not inferred. Inline references are `file:line`
at the commit above; the Code References section carries permalinks.

## Research Question

How to add a local web UI (`/ui`, `/api`) to the HTTP server `cast-tv` already runs; how to serve
photos alongside video; where HEIC conversion fits in the relay; how to split the three scripts
into a `castlib/` package - and, added mid-research: how the UI actually *gets at* the files in
GoPro, Google Photos and OneDrive.

## Summary

1. **The server is built for exactly one item per process, and that assumption is load-bearing
   everywhere.** `RangeHandler` keeps `files`, `remote`, `opener`, `caption_url` and `debug` as
   *class* attributes assigned from `main()`. Two of the consequences are bugs today (relay +
   subtitles mutates the class default dict; a second cast wipes the first mid-stream), and five
   more become bugs the moment two items coexist. The registry has to become per-item objects on
   one shared map with add/remove semantics. This is the largest single refactor and it is
   unavoidable.

2. **Adding routes is cheap; adding them *correctly* under HTTP/1.1 keep-alive is the part to get
   right.** Every `/api` response must carry an exact `Content-Length` or set `close_connection`,
   `send_error` must not be used for JSON (it emits `text/html` and `Connection: close`), handler
   threads need a `timeout`, and - the one that upgrades from "open question" to blocker - the
   server binds `0.0.0.0` with no `Host`/`Origin` check, so once `/api` can start a cast, any web
   page in the user's browser can drive the TV. Origin validation is required, not optional.

3. **Photos cannot be served today, and the reasons go one level deeper than the change notes
   recorded.** Beyond the empty image MIME table and the hard-coded `videoItem`, the two MIME
   lookups have *different* fallbacks (`didl` says `video/mpeg`, the wire says
   `application/octet-stream` - a live mismatch for any unknown extension, verified for `.heic`),
   `transferMode.dlna.org: Streaming` is sent unconditionally where a still needs `Interactive`,
   `DLNA_FEATURES` is a video profile applied to everything, and the DIDL `<res>` carries no
   `resolution`/`size`. History shows the DLNA flags were never tested against alternatives - they
   are first-commit values that were never edited.

4. **HEIC conversion decides the photo pipeline: photos are fetched whole, videos are relayed.**
   A HEIC cannot be converted while streaming, and a produced body has no size up front - which
   breaks `Content-Length`, `Content-Range`, `Accept-Ranges` and the HEAD-before-GET the TV does.
   Materialising the converted image *before* replying keeps every existing serving path correct.
   That is not a compromise; images are small and the decoded image also yields the
   `resolution` the DIDL needs. Video keeps the relay, whose range-trim logic (`_proxy`) is
   sound and should be reused, not rewritten.

5. **`castcloud.py` cannot run inside a server as written.** `die()` calls `sys.exit()` - in a
   handler thread that silently kills the thread with no HTTP response; `fetch()` has two return
   shapes and one of them is `die`, so the two must be fixed together; `cast()` shells out,
   blocks for the whole playback, and spawns a *second* server that fights for port 8895. Every
   `die()` call site carries a good, user-facing message worth keeping verbatim as an exception
   payload.

6. **Getting at the files differs per source, and one source just changed shape.** GoPro lists
   over its media API behind a pasted token (works today; thumbnails not yet requested). OneDrive
   lists over Graph behind device code (settled in the change notes). Google Photos has, since
   the Library API lockdown, a documented **Picker API**: the user picks - multi-select - in
   Google's own UI (phone included), and the app lists exactly those items with `baseUrl`s.
   Adopted in `change.md`. It is carried by the **desktop loopback flow**: Google's device-flow
   page supports "only" a closed list of seven scopes, none of them the Picker's, and sends
   Linux/Windows applications to the desktop flow (follow-up below). The UX decision did not
   depend on the outcome; the auth decision now has one.

7. **The git history encodes seven constraints a refactor could silently undo.** The TV reports
   `0:00:00`, not `00:00:00`; `octet-stream` acceptance in the probe is what keeps GoPro casts
   at source quality; `TRANSITIONING` was deliberately removed from "started"; the relay
   synthesises `206` on the upstream's *status*, not its headers; `=dv` leads `SUFFIXES` for a
   reason; the relay overrides a generic upstream `Content-Type` from the URL extension; and
   the one-byte range probe exists because HEAD is refused on googleusercontent.

## Detailed Findings

### 1. The server as it stands: one item, one process

`RangeHandler` (`cast-tv:106-283`) is a `BaseHTTPRequestHandler` with `protocol_version =
"HTTP/1.1"` (`:107`). Its state is five **class attributes** (`:108-112`) - `files` (url path ->
disk path), `remote` (url path -> upstream URL), `debug`, `opener`, `caption_url` - all written
from `main()` by assignment on the class (`:429`, `:438`, `:451`, `:458`, `:460`, `:467`).

Dispatch is two dict lookups: `do_GET` (`:263-283`) tries `_remote()` first, then `_resolve()`,
else `send_error(404)`. Both helpers re-parse `self.path` identically and discard the query string
(`:123`, `:160`). `do_HEAD` mirrors it (`:253-261`). There is no routing layer, no access log
(`log_message` is a no-op, `:114-115`), and the only diagnostics are `dbg()` gated on `debug`.

`Server` (`:286-288`) is a bare `ThreadingTCPServer` with `daemon_threads` and
`allow_reuse_address` - both correct - but `RangeHandler.timeout` is unset (stdlib default
`None`), so an idle keep-alive connection holds its thread forever.

`main()` (`:372-518`) is one 147-line function: discovery, control-URL lookup, `--stop`,
argument validation, relay-or-file setup, **then** port bind (`:463`), then SOAP, then a blocking
2-second poll loop that owns stdout (`\r` status line, `:496`) and `Ctrl+C` (`:511-517`).

Two ordering facts matter for the UI:

- **Discovery runs before the missing-source error.** `args.source` is `nargs="?"` (`:374`) and
  the check at `:416-417` comes *after* discovery (`:395-404`) and `control_urls` (`:406`). So
  `cast-tv` with no arguments today spends ~4 s finding the TV and then errors. Repurposing the
  no-argument form for the UI loses nothing and the discovery it needs has already happened.
- **The port is bound after the item is set up.** For a UI the server must start first and
  outlive any cast; the bind moves to the front and items register into a running server.

`local_ip(target)` (`:291-296`) needs a TV address to find the right local interface. Before a TV
is chosen the UI needs another way to print its own LAN address.

### 2. Adding `/ui` and `/api`: what HTTP/1.1 keep-alive demands

*Verified against the stdlib.*

- **Framing.** With `protocol_version = "HTTP/1.1"`, `close_connection` is only flipped by the
  client's `Connection:` header or by explicitly sending one; `send_header` only reacts to the
  literal keyword `connection`. `BaseHTTPRequestHandler` has no chunked encoding. So a route that
  writes a body without an exact `Content-Length` leaves the socket open and the client parses
  the *next* response as the tail of this one. Every `/api` response: exact `Content-Length`, or
  `self.close_connection = True` before `end_headers()`. The code already knows this - `_proxy`
  sets `close_connection` in its unknown-length branch (`:226-227`).
- **`send_error` is wrong for JSON.** It unconditionally emits `Connection: close` and a
  `text/html` body. Under a browser, every 404 (`/favicon.ico`, `/`) tears down a pooled
  connection, and API clients get HTML. The API prefix needs its own `_json_error()`.
- **Thread and fd leak.** Browser (~6 idle keep-alive connections per origin) + TV + no handler
  `timeout` = threads parked forever in `readline()`. `daemon_threads` only helps at process
  exit, which no longer happens. Set `RangeHandler.timeout`; consider `request_queue_size`.
- **HEAD via the relay is a full upstream GET.** `do_HEAD` -> `_proxy(body=False)` -> a plain
  `Request` (GET) that returns without reading (`:232-233`). A UI that HEAD-probes items costs
  one upstream GET each.
- **`_headers` is file-only.** Its signature is `(disk, size, start, end, partial)`; it derives
  `Content-Type` from `splitext(disk)` (`:129-131`) and unconditionally adds the two DLNA headers
  (`:137-138`). It cannot describe generated JSON; the DLNA block and the generic block separate.
- **Security - this is a blocker, not an open question.** `Server(("0.0.0.0", port))` (`:463`)
  with no authentication, no `Host` check, no `Origin` check. Today the exposed surface is "read
  one file whose path you have to guess". Once `/api` can start a cast, browse a folder or
  trigger a resolver, every device on the LAN can drive the TV, and - because there is no Origin
  validation - **any web page open in the user's browser can hit
  `http://<lan-ip>:8895/api/...`** (plain CSRF / DNS rebinding). Media paths are `/video/<basename>`
  (`:450`): guessable, not tokenised. Minimum: validate `Origin`/`Host` on `/api`, and put a
  per-session token in media URLs handed to the TV.

### 3. Many items over a session: the class-attribute bugs

*Two verified today, five latent.*

| # | Where | What | Status |
| --- | --- | --- | --- |
| 3.1 | `:429` vs `:458` | Relay branch never assigns `files`; with `--subs`, `:458` mutates the **class-body dict from `:108`** in place. Local branch rebinds first (`:451`), so the two branches differ. *Verified*: after one relay+subs cast the class default holds the subtitle entry permanently. | **bug today** |
| 3.2 | `:451` | `RangeHandler.files = {...}` **replaces** the map. Start cast B while the TV streams A: A's next `Range` request 404s (`:266-268`), the TV stops. | **bug today** |
| 3.3 | `:429`, `:264` | `remote` is never cleared and is checked *first*. A relay registered an hour ago (signed CDN URL, long dead) shadows a live file on a colliding path. | latent |
| 3.4 | `:112`, `:460`, `:139-140` | `caption_url` set once, never cleared. Cast A with subs, then B without: `CaptionInfo.sec: <A's URL>` is attached to **every** later response - B, images, audio - and after 3.2 that URL 404s. | latent |
| 3.5 | `:111`, `:438`, `:178` | One process-wide `opener`/cookie jar. Cast B's jar overwrites A's while A streams -> A's range requests go out with B's credentials -> 403 mid-playback. `OpenerDirector` is also not documented thread-safe and is shared by every handler thread. | latent |
| 3.6 | `:450` | Keys are `/video/<basename>`: `~/a/IMG_0001.HEIC` and `~/b/IMG_0001.HEIC` collide; second silently replaces first. | latent |
| 3.7 | - | Nothing ever removes an entry. Everything cast in a session stays fetchable, unauthenticated, for the process lifetime. | latent |
| 3.8 | `:451`+`:458` | Two-step registration (video, then subtitle); a TV request between them sees half an item. | latent |
| 3.9 | `:259`, `:269`, `:274` | `getsize`/`open` are outside any `OSError` handler (the `try` at `:273` catches only broken-pipe). File deleted or drive unmounted between listing and request -> traceback, connection dropped with no response, or mid-body after a 200. `main:444` checked `isfile` seconds earlier; a UI cannot rely on that. | latent |

Resolution is one shape: a `MediaItem` object (path-or-upstream, MIME, kind, size, caption,
opener, created-at) registered under a **unique id** on one shared map, published atomically,
removed on stop or eviction. `debug` becomes a per-item or per-request flag, not a class toggle.

### 4. Photos: every place that assumes video

Confirming and extending `change.md`'s four-row table:

- `MIME` (`:19-24`) has **zero** image types. *Verified.*
- **The two fallbacks differ.** `_headers:131` -> `MIME.get(ext, "application/octet-stream")`;
  `didl:302` -> `MIME.get(ext, "video/mpeg")`. For any extension outside the table the TV is
  told `video/mpeg` in `protocolInfo` and handed `application/octet-stream` on the wire.
  *Verified for `.heic`*; already true for `.mts`, `.3gp`, `.ogv`. A `protocolInfo`/`Content-Type`
  mismatch is exactly the kind of thing that makes a Samsung refuse silently. History is silent
  on why they differ - treat as unintended.
- `upnp:class` hard-coded `object.item.videoItem` (`:312`). Note it is already wrong for the audio
  types the table *does* carry (`.mp3`, `.flac`, `.m4a`).
- `transferMode.dlna.org: Streaming` unconditional (`:137`, `:229`). A still image should be
  `Interactive`. Expected per DLNA guidelines; **not yet verified on this TV**.
- `DLNA_FEATURES` (`:26-27`) is one string - `OP=01` (byte-seek) plus a streaming flag word -
  sent as the header (`:138`, `:230`) and embedded in `protocolInfo` (`:313`). Photos want
  `OP=00` and the interactive flag; Samsungs commonly also want a `DLNA.ORG_PN=JPEG_LRG` profile
  token, absent entirely. **History shows these values were never edited after the first commit
  and no alternative was ever tried** - unknown territory, not proven ground.
- `CaptionInfo.sec` guard is "extension not in the four subtitle types" (`:139`), so `.jpg`
  qualifies; combined with 3.4 an image gets a caption header pointing at a dead subtitle.
- `didl` emits no `resolution="WxH"` or `size=` on `<res>` (`:313`); Samsung photo rendering
  generally wants both. `didl`'s `disk` argument is used only for `splitext`; in relay mode
  `main:441` passes a bare basename, so there is no file to measure - the dimensions have to come
  from the decoded image (section 5) or the source's metadata (Graph `image` facet, Picker
  `mediaMetadata.width/height`).
- **Relay appends `.mp4` to extension-less URLs** (`:426-427`). Graph `downloadUrl`s and Picker
  `baseUrl`s have no extension. A photo relayed through this path is named `.mp4` and announced
  as video. The kind must come from the source, never from the URL.
- `check_codecs` (`:354-368`) would run `ffprobe` per still (harmless, pointless).
  `explain_failure` (`:319-351`) would tell the user a 4032x3024 photo has an "unusual aspect"
  and suggest `-q proxy`. Fine in a CLI footnote; wrong-looking in a UI. Both need a
  `kind == video` guard.

### 5. Transforming bytes in flight: why photos are materialised

- `os.path.getsize(disk)` (`:259`, `:269`) is the **source** size, and every downstream number
  derives from it: `_range` clamps `end` to it (`:156`), `_headers` sends `Content-Length` and
  `Content-Range` from it (`:132`, `:135`). A converted JPEG is a different length. Smaller ->
  the loop at `:276-281` exhausts the producer and `break`s short of the promised length; under
  keep-alive the client reads the next response as the missing tail. Larger -> surplus.
- `Accept-Ranges: bytes` is unconditional (`:133`) and the code's own comment (`:188-190`)
  records that this TV seeks to the MP4 index offset and "would quietly stop" if it gets the
  start instead. A produced body cannot seek.
- Samsung HEADs before it GETs; the HEAD needs the *converted* size (`:259-261`).

The two honest routes are (a) materialise the conversion to memory or a temp file before
replying, after which `_range`, `_headers`, HEAD and the byte loop work untouched; or (b) drop
`Content-Length` and use `close_connection` as end-of-body, the acknowledged degradation already
at `:226-227`. DLNA renderers given a lengthless still usually refuse it. **(a) is the design**,
and it is not a compromise: images are megabytes, the decode also yields `resolution`, and a
converted-output cache keyed by `(source, mtime, size)` serves the HEAD and the GET from one
decode. Conversion needs a work bound - a UI rendering a 200-photo folder must not spawn 200
decoders on an unbounded `ThreadingTCPServer`.

Three `_range` bugs, *verified* against a 500-byte resource, that become routine once bodies are
small or generated:

- `bytes=99999-` -> `Content-Length: -99499`, `Content-Range: bytes 99999-499/500`. `_range`
  clamps `end` but never `start` and never returns `416` (unlike `_proxy:203-206`). Today masked
  because the TV knows the real size of a large video.
- `bytes=-` -> `int("")` raises `ValueError` at `:152`; no response, traceback, connection drop.
- `bytes=0-99,200-299` -> `206` for the first range only, no `multipart/byteranges`. Browsers
  send multi-range.

`_proxy`'s trim logic (`:191-249`) is **sound and is the precedent** for both "upstream ignored
my Range" and "unknown length". Reuse it for video relay; do not rewrite it.

### 6. Getting at the files, per source

The mid-research question - how the UI "pulls" files from the three clouds - splits into two
layers, and both differ by source.

**Access and listing**

| Source | Auth | Listing | Item -> bytes | Thumbnails |
| --- | --- | --- | --- | --- |
| GoPro | bearer token pasted from a browser; expires in hours; no public OAuth | `GET /media/search` with `fields=id,filename,captured_at,content_title,file_size,type,resolution,duration`, paged (`cast-gopro:73-92`) | `GET /media/{id}/download` -> ranked variations (`library_url`, `cast-gopro:114-142`); `type` field already distinguishes photo/video | **not requested today**; API shape for thumbnail URLs unverified - probe the JSON, per the repo's own "send it over and the parser can be adjusted" style |
| OneDrive | Graph, device code, `Files.Read offline_access`, refresh ~90 days | `/me/drive/root:/<path>:/children?$expand=thumbnails`; `folder`/`file`/`image`/`photo`/`video` facets | `@microsoft.graph.downloadUrl`, pre-authenticated, `Range` OK, **expires ~1 h - resolve on demand** | `$expand=thumbnails` |
| Google Photos | today: none (share link) or a Netscape cookie jar; **Picker API**: OAuth, scope `photospicker.mediaitems.readonly` | today: cannot list; **Picker**: `POST photospicker.googleapis.com/v1/sessions` -> `pickerUri`; user picks (multi-select, on any device) -> poll `GET /v1/sessions/{id}` until `mediaItemsSet` (honouring `pollingConfig.pollInterval`) -> `GET /v1/mediaItems?sessionId=` (paged, <=100) | today: scrape page, probe candidates with a one-byte range (`cast-photos:83-119`); **Picker**: `PickedMediaItem` with `type: PHOTO/VIDEO`, `mediaMetadata` (width, height, creationTime), `filename`, `mediaFile.baseUrl` - suffix `=d` / `=dv` as in `SUFFIXES` today; **fetch needs `Authorization: Bearer`; expires after 60 min - re-list, never cache the URL** | Picker: `baseUrl` with `=w…-h…` |

The Picker API's `sessions.create` takes a `requestId` (UUID v4) "to enable the streamlined
picking experience for applications using the OAuth 2.0 flow for limited-input devices" - which
reads as device code. But Google's limited-input-device documentation
(developers.google.com/identity/protocols/oauth2/limited-input-device) allows only selected
scopes and does not list `photospicker.mediaitems.readonly`, and recommends the desktop
(loopback) flow for Linux/Windows applications. The device-flow page's wording is a closed
allow-list - "supported only for the following scopes" - so the `requestId` sentence has no
authorisation path behind it for this scope. Loopback it is (follow-up below). The Photos tab
shows a grid of picked items rather than a paste field either way. For the MVP, Google
authorisation runs once in a browser on the host; the `pickerUri` can still be opened on the
phone. Cost: a Google Cloud project, an OAuth client and a consent screen, configured once
(testing mode is fine for personal use). Sessions should be deleted after use to stay under the
quota. This does **not** restore browsing the library in our own UI - it moves the pick into
Google's UI and brings the result back. It also deprecates the share-link scraper, which the
repo itself describes as "written defensively because neither format is documented". Keep the
scraper as a fallback for links from other people's libraries, where no picker session exists.

**Fetch or relay, by kind**

Section 5 forces the rule, and it is the same for all three sources:

- **Photo**: fetch whole -> decode (convert HEIC -> JPEG if needed) -> serve from memory or a
  temp file with exact `Content-Length`, `resolution`, `size`. Images are small; the whole
  object is needed for conversion anyway; and the TV's HEAD-then-GET is answered from one decode.
  "Nothing touches the disk" softens to "nothing *persists*" - a bounded, evicted cache.
- **Video**: relay, as today. Do not buffer. The downloadUrl / baseUrl expiry means the relay
  must re-resolve the upstream when it (re)opens, not cache the URL at listing time.

**Resolver contract.** `castcloud.is_video()` (`castcloud.py:54-82`) must become `is_media()`
returning a kind, and must **keep** accepting `*/octet-stream` and video extensions - history
shows tightening it to `video/*` silently downgrades every GoPro cast to a 4 MB proxy. It must
also stop conflating "not media" with "network failure" (`except Exception: return None`,
`:81-82`): in a UI, reporting the wrong cause is worse than no cause.

### 7. `castcloud.py` inside a server process

- **`die()` calls `sys.exit()`** (`castcloud.py:22-24`). In the main thread it kills the app. In
  a handler thread, `threading` swallows `SystemExit`: the thread dies, **no HTTP response is
  sent**, the reason goes only to stderr. Call sites: `opener_for:35`, `fetch:51`, `cast:115`,
  `cast-photos:93,100,102,107,117`, `cast-gopro:42,63,66,70,79,128,154,184`. Every one is a
  recoverable, user-facing condition with a good message ("Google asked for a login", "GoPro
  rejected the token (401) - expired or incomplete"). Keep the messages; raise them.
- **`fetch()` has two return shapes** (`:40-51`): `HTTPError` -> tuple; any other exception ->
  `die()`. The instant `die` stops exiting, `fetch` falls through and returns `None`, and every
  caller unpack-crashes (`cast-photos:98`). Fix both together.
- **`cast()` shells out and blocks for the whole playback** (`:101-115`), spawning a **second
  HTTP server** in the child (`cast-tv:463`) that fights the long-lived one for 8895 whenever
  `port` is `None` - the default path for `cast-photos` (`:138`). No handle is kept, so the parent
  cannot stop the child. Becomes an in-process call; `cast_tv_path()` (`:94-98`) becomes moot.
- `opener_for` and `die` print to stdout/stderr (`:36`, `:23`); a server has no console the user
  watches. Structured results.
- `cache_write` (`:118-121`) is truncate-then-write, unlocked; `cache_read` swallows the resulting
  `ValueError`, so a race corrupts the cache invisibly. Write to a temp file and `os.replace`.
  `name` is joined into a path unvalidated (`:120`, `:126`) - safe while callers pass literals,
  unsafe the moment a UI identifier reaches it.
- Network calls block 20-30 s with no cancellation (`:45-46`, `:63-64`); `explain_failure`'s
  ffprobe blocks up to 90 s (`cast-tv:326`). Bounded, but a request thread parked for 30 s with no
  way for the UI to abandon it.

### 8. Lifecycle: from poll loop to supervised casts

The poll loop (`cast-tv:486-518`) holds per-cast state in locals (`started`, `waited`), writes a
carriage-return status line, and treats `KeyboardInterrupt` as Stop. For the UI it becomes one
supervised task per active cast with that state on the object, and the status delivered over
`/api` (polled at 1-2 s, as `change.md` already decided). Three constraints from history carry
over unchanged:

- `RelTime` arrives as `0:00:00` - **not zero-padded**. Never compare against `"00:00:00"`.
- `started` is `PLAYING`/`PAUSED_PLAYBACK` only; `TRANSITIONING` is "still an attempt". Wait
  budget 40 s in `TRANSITIONING`, 24 s otherwise (`:498-505`).
- `explain_failure` runs only after the budget expires - keep that, and add the "TV fetched zero
  bytes" branch for the firewall case (`change.md` already asks for it). A per-item request
  counter on the `MediaItem` is what makes that branch decidable.

One small inconsistency to carry into the design: `check_codecs` suggests `-c:a eac3`
(`cast-tv:367`); the mockup's DTS card shows `-c:a ac3`. The code is right.

## Code References

Permalinks at `1b8d46f`.

- [`cast-tv#L106-L112`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L106-L112) - `RangeHandler` class-attribute state
- [`cast-tv#L122-L124`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L122-L124), [`#L159-L161`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L159-L161) - the two dict-lookup dispatchers
- [`cast-tv#L126-L141`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L126-L141) - `_headers`: octet-stream fallback, unconditional DLNA headers, caption guard
- [`cast-tv#L143-L156`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L143-L156) - `_range`: unclamped start, `bytes=-` crash, single-range only
- [`cast-tv#L163-L251`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L163-L251) - `_proxy`: relay, 206 synthesis, Content-Type override, unknown-length degradation - **reuse**
- [`cast-tv#L253-L283`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L253-L283) - `do_HEAD`/`do_GET`, unguarded `getsize`/`open`
- [`cast-tv#L286-L296`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L286-L296) - `Server`, `local_ip`
- [`cast-tv#L300-L316`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L300-L316) - `didl`: `video/mpeg` fallback, hard-coded `videoItem`, no `resolution`/`size`
- [`cast-tv#L319-L368`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L319-L368) - `explain_failure`, `check_codecs` (video-only advice; `eac3`)
- [`cast-tv#L372-L417`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L372-L417) - `main()`: discovery before the no-source error
- [`cast-tv#L423-L468`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L423-L468) - item setup, `.mp4` suffix on extension-less URLs, class assignments, late bind
- [`cast-tv#L486-L518`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-tv#L486-L518) - poll loop
- [`castcloud.py#L22-L24`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/castcloud.py#L22-L24) - `die()`
- [`castcloud.py#L40-L51`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/castcloud.py#L40-L51) - `fetch()` two return shapes
- [`castcloud.py#L54-L82`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/castcloud.py#L54-L82) - `is_video()`: load-bearing octet-stream acceptance
- [`castcloud.py#L94-L115`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/castcloud.py#L94-L115) - `cast()`: blocking subprocess, second server
- [`castcloud.py#L118-L129`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/castcloud.py#L118-L129) - non-atomic cache
- [`cast-gopro#L73-L92`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-gopro#L73-L92) - `list_media`: the fields requested today
- [`cast-gopro#L107-L142`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-gopro#L107-L142) - `_rank`, `library_url`: variant ranking learned from the API
- [`cast-photos#L20`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-photos#L20) - `SUFFIXES`: `=dv` first is a quality preference
- [`cast-photos#L83-L119`](https://github.com/Piotr-Miller/cast-tv/blob/1b8d46f61ed4f4ed156f146d08fb69e442cda295/cast-photos#L83-L119) - `resolve`: the scraper the Picker API would replace

## Architecture Insights

- **One `MediaItem`, three sources, two pipelines.** The object carries kind, MIME, size,
  resolution, caption, opener, and either a disk path or an upstream resolver (a callable, so
  expiring URLs re-resolve). Photos materialise; videos relay. Registration is atomic on one
  shared map under a unique id; removal happens on stop or eviction.
- **Dispatch before lookup.** One parser of `self.path` (keeping the query), then
  `/api` -> JSON with exact lengths and Origin check, `/ui` -> static with no traversal (the
  exact-match lookup that makes today's server traversal-proof is the property to preserve),
  media -> the existing item paths.
- **Two header blocks, not one.** Generic (`Content-Type`, `Content-Length`, `Content-Range`,
  `Accept-Ranges`) and DLNA (`transferMode`, `contentFeatures`, `CaptionInfo.sec`), the latter
  per-kind and per-item.
- **Exceptions, not exits; results, not prints.** `castcloud` becomes a library whose failure
  messages survive as exception payloads the API renders.
- **Reuse what history hardened.** `_proxy`'s trim, the one-byte probe, the octet-stream
  acceptance, the `TRANSITIONING` budget, the `=dv`-first ordering.

## Historical Context (from prior changes)

`context/changes/` holds only this change and `context/archive/` is empty, so the history lives
in git. Constraints a refactor could silently undo, with the commit that established each:

- `cf2a839` - the relay exists because the TV accepts an HTTPS URL over SOAP and then sits in
  `STOPPED`; handing cloud URLs straight to `SetAVTransportURI` fails with no error anywhere.
- `cf2a839` - `DLNA_FEATURES`, `transferMode`, `videoItem`, `sec:CaptionInfoEx` all arrived
  together and **were never edited**; no alternative flag values are evidenced.
- `a750b37` - the TV reports `RelTime` as `0:00:00`; a zero-padded literal comparison ended
  every playback on the first tick. Replaced by the `started` latch.
- `a750b37` - the one-byte `Range` probe instead of HEAD, because HEAD is refused on
  googleusercontent; total size is read from `Content-Range`.
- `582abd0` - the relay synthesises `206` when the upstream answers `200` to a range request;
  trigger is the upstream's **status**. Without it the TV asks for the MP4 index offset, gets the
  file start, and stops "without a word - the failure looked like a codec problem and was
  neither". `--debug` came with it.
- `223eca1` - GoPro serves sources as `binary/octet-stream`; the probe's acceptance of it is
  what keeps casts at source quality. `files[]` entries are 1280 px proxies, not sources.
  `TRANSITIONING` removed from "started". Relay overrides a generic upstream `Content-Type` from
  the extension. The camera original (HEVC 3840x3360, 119 Mbit/s) is refused - hence `-q proxy`
  and the 60 Mbit/s heuristic in `explain_failure` (a heuristic from one file, not a tested
  cutoff).
- `36cf4c8` - on a live share page, eight candidates, `=dv` (the original) is the one that
  answers as video; `SUFFIXES` order is a quality preference.

## Related Research

- `context/changes/cloud-source-ui/change.md` - the decisions this research tests; sections 4
  and 6 above extend its photo table and Google Photos entry.
- Design canvas (clickable mockups): https://claude.ai/code/artifact/0673495b-4537-4e06-9f72-5ae5511d14fa

## Open Questions

1. **DLNA image profile on this Samsung.** `transferMode: Interactive`, `OP=00`, `DLNA.ORG_PN`
   and `<res resolution size>` are expected per the guidelines and untested here. One evening
   with `--debug` and three JPEGs settles it.
2. **GoPro thumbnails.** `/media/search` is not asked for them today; the response shape for
   thumbnail URLs is unverified. Probe the JSON.
3. **Google Photos stills via the scraper** (`=d` vs `=w…-h…`) - only matters while the
   scraper stays as the fallback path.

Retired since first write: adopting the Picker API (decided in `change.md`); `baseUrl`
mechanics (settled by Google's access-media-items guide: Bearer required, 60-minute expiry);
Origin/Host validation (now phase one of the plan in `change.md`); the OAuth spike (both
halves done - see the 2026-09-09 follow-up below).

## Follow-up Research 2026-09-08T22:52:34+02:00

**OAuth spike, documentary half.** Question: can the limited-input-device (device code) flow
carry `photospicker.mediaitems.readonly`?

- `developers.google.com/identity/protocols/oauth2/limited-input-device` states: **"The OAuth
  2.0 flow for devices is supported only for the following scopes"** and lists exactly seven -
  OpenID Connect `email`, `openid`, `profile`; Drive `drive.appdata`, `drive.file`; YouTube
  `youtube`, `youtube.readonly`. Google Photos and the Picker are not mentioned on the page. It
  adds that an app on "Android, iOS, macOS, Linux, or Windows ... that has access to the browser
  and full input capabilities" should "use the OAuth 2.0 flow for mobile and desktop
  applications". `client_secret` is required at the token-polling step of the device flow.
- `developers.google.com/photos/picker/get-started-picker` names no client type or flow at all.
  The only flow-adjacent sentence anywhere in the Picker docs is `sessions.create`'s `requestId`
  note "for applications using the OAuth 2.0 flow for limited-input devices". With a closed
  allow-list on the other page, that sentence has no authorisation path behind it for this
  scope.
- **Verdict:** desktop loopback flow, run once in a browser on the host. The `pickerUri` it
  yields is device-independent and can be opened on the phone.

**Empirical half, pending a client.** `POST https://oauth2.googleapis.com/device/code` was
probed with a placeholder `client_id` and three scopes (Picker, `drive.file`, `openid email`):
all three return `401 invalid_client` - Google validates the client before it looks at the
scope, so nothing about the scope can be learned without a real "TVs and Limited Input
devices" client. `spike-picker-oauth.py` in this folder runs either flow end to end and ends
in the proof that matters - `POST /v1/sessions` succeeding - with `--pick` continuing to
`mediaItems.list` and a one-byte range fetch of `baseUrl` with and without the Bearer header.
Standard library only; tokens are printed as their last four characters and nothing is stored.

## Follow-up Research 2026-09-09T22:34:17+02:00

**OAuth spike, empirical half - done.** Run on the host against a fresh Cloud project
(`cast-tv`, consent screen External/Testing, the account as its only test user, Photos Picker
API enabled, one "Desktop app" OAuth client). Three runs; the last one clean end to end:

| step | result |
|---|---|
| `GET accounts.google.com/o/oauth2/v2/auth` (loopback `127.0.0.1:<random>`, PKCE S256, `access_type=offline`) | consent page rendered for the Picker scope; redirect received |
| `POST oauth2.googleapis.com/token` (authorization_code + `code_verifier` + `client_secret`) | HTTP 200, `scope` echoed as `photospicker.mediaitems.readonly`, `expires_in 3599`, **refresh_token issued** |
| `POST photospicker.googleapis.com/v1/sessions` | HTTP 200, `pickerUri` + `pollingConfig.pollInterval 5s` |
| pick in Google's UI, then `GET /v1/mediaItems?sessionId=` | HTTP 200, one `PHOTO`, `mediaFile.mimeType image/jpeg`, `mediaFile.baseUrl` present |
| `baseUrl=d`, `Range: bytes=0-3`, **with** `Authorization: Bearer` | **HTTP 206**, `image/jpeg`, bytes `ff d8 ff e0` (JPEG SOI) |
| `baseUrl=d`, same range, **without** the header | **HTTP 403**, body is a `image/png` error tile (`89 50 4e 47`) |
| `DELETE /v1/sessions/{id}` | ok |

What this settles for the plan:

- **Loopback is the flow, and it works with a plain Desktop-app client.** No device-code
  client is needed; nothing about "TVs and Limited Input devices" enters the design. The
  refresh token means the "connect once" promise in `change.md` holds: with
  `access_type=offline` the host can mint fresh access tokens without another browser round.
- **`baseUrl` must be fetched by the host with the Bearer header, and it honours `Range`.**
  The 403 without the header closes the "hand the URL to the TV or to the browser" option for
  good - both the still path (fetch whole, materialise) and the video relay go through the
  host, exactly as `change.md` already assumes. The 206 with `Range` means the relay can pass
  the TV's range requests straight through, as it does for Graph's `downloadUrl` today.
- **Video `=dv` was not probed** - only a photo was picked. Google's access-media-items guide
  gives the same Bearer/expiry rules for both suffixes, and nothing in the plan hinges on the
  difference, so this is not re-opened as a question.
- **Field shapes, per the Picker `mediaItems` reference** (`developers.google.com/photos/picker/reference/rest/v1/mediaItems`): `PickedMediaItem{id, createTime, type, mediaFile}` and
  `mediaFile{baseUrl, mimeType, filename, mediaFileMetadata{width, height, cameraMake,
  cameraModel, photoMetadata|videoMetadata}}`. These are **not** the Library API names
  (`mediaMetadata`, `creationTime`, top-level `filename`) that `change.md:113` uses - the plan
  should read the Picker names. The first two runs printed no filename because the script read
  it at the top level; fixed in the script, unverified in the run.
- **Two practical lessons for the real implementation**, learned by tripping over them: the
  consent URL contains `&`, so anything that prints it for the user to open must quote it or
  open the browser itself; and the console's "OAuth configuration is incomplete" banner on the
  Audience page is about publishing (home page, privacy policy, authorized domain), not about
  Testing mode - a test user authorises fine with it showing.

Console-side facts for whoever repeats this: the OAuth pieces (consent screen, client, Picker
API) are always-free and need no billing account; the new "Google Auth Platform" wizard renders
wider than the window on this GNOME/Chrome setup and needs `Ctrl -` to reach the Next button.

## Follow-up 2026-09-10 — Phase 1 manual verification (plan rows 1.5, 1.6)

Recorded here because the Phase 1 implementation review (F7) asked for observable evidence
behind the ticked manual rows. Machine: the Fedora laptop at `192.168.50.198`; renderer:
Samsung `83" OLED` at `192.168.50.142`; code: `31d715d` plus the review fixes.

| check | material | observed |
|---|---|---|
| local file with subtitles, `--debug` (row 1.5) | `~/Videos/cast-tv-smoke/smoke.mp4` (ffmpeg `testsrc` 1280x720, 15 s, libopenh264 + AAC, 1 026 026 bytes) and `smoke.srt` (one cue, 1-5 s) | `[tv] HEAD` then `GET` of the video, `GET` of the subtitle item (51 bytes), four ranged `GET`s (`bytes=0-`, `1025898-`, `1015082-`, `98352-`), `PLAYING` ticks through `0:00:14`, `STOPPED`, `Finished.`; the caption rendered on screen |
| relay, `--debug` (row 1.5) | `https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_1MB.mp4` (969 201 bytes) | `upstream: 200 video/mp4` on the TV's rangeless HEAD/GET, `upstream: 206` on `bytes=0-`, `bytes=969073-` (128 bytes) and two more `bytes=0-`; `relaying through http://192.168.50.198:8895 -> 192.168.50.142`; played to `Finished.` |
| foreign Origin (row 1.6) | `curl -i -H 'Origin: http://evil' http://localhost:8895/api/status` while the smoke clip played | `HTTP/1.1 403 Forbidden`, `Content-Type: application/json; charset=utf-8`, `Content-Length: 127`, body `{"error": {"code": "forbidden", ...}}` |
| wrong media token (row 1.6) | `curl -i http://localhost:8895/m/zlytoken/cokolwiek` | `HTTP/1.1 404 Not Found`, JSON body `{"error": {"code": "not_found", "message": "Not found.", "hint": null}}` |

Two things the rows promise that this evening did **not** cover: the Origin/token curls ran
on the laptop itself (`localhost`), not from a second machine on the LAN, and the relay was
not exercised with a cookie jar (`-c`). The cookie path is covered by
`test_relay.py::test_cookie_opener_is_used_for_upstream` after review finding F5, which found
that the inherited `opener.urlopen` call had never worked.

The URL handed to the TV is now `http://<host>:8895/m/<token>/<id>` with no file extension;
the Samsung accepted it for both the local file and the relay, so the `.mp4` suffix the
one-shot script appended to extension-less relay names is not needed for playback.

## Follow-up 2026-09-10 — Phase 2: the Samsung's photo profile (Open Question 1, closed)

Manual rows 2.3–2.5 passed on the Samsung `83" OLED` (192.168.50.142) from the Fedora laptop
(192.168.50.198), photos cast with `.venv/bin/python -m castlib <file> -d`. The values below
are the DLNA-guideline defaults the plan proposed; **the TV accepted them unchanged**, so no
iteration over `PHOTO_FEATURES`/`transferMode` was needed. Retire research Open Question 1.

| on the wire | value |
|---|---|
| `upnp:class` | `object.item.imageItem.photo` |
| `protocolInfo` | `http-get:*:<prepared mime>:DLNA.ORG_PN=<profile>;DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000` |
| `<res>` attributes | `resolution="WxH"` and `size="N"` of the **prepared** file |
| `transferMode.dlna.org` | `Interactive` |
| `contentFeatures.dlna.org` | the same `DLNA.ORG_PN…` string as in `protocolInfo` |
| profile | `JPEG_SM` ≤ 640×480, `JPEG_MED` ≤ 1024×768, `JPEG_LRG` ≤ 4096×4096, `PNG_LRG` for PNG; larger sources are downscaled to fit 4096×4096 first |
| media URL | `http://<host>:8895/m/<token>/<id>`, no extension, as for video |

What was shown and what the TV did (`--debug`):

| file | prepared as | TV requests | on screen |
|---|---|---|---|
| `photo.jpg` 1920×1080 (stored as fetched) | `image/jpeg`, `JPEG_LRG`, 59 788 B | HEAD, then full GETs with no `Range`; no 416, no partial requests; `PLAYING 0:00:00 / 0:00:00` for as long as the process runs | correct |
| `photo.heic` 1920×1080 | converted to `image/jpeg`, `JPEG_LRG`, 60 862 B | same pattern | correct |
| `photo.png` 1920×1080 (stored as fetched) | `image/png`, `PNG_LRG` | same pattern | correct |
| `portrait.jpg` 1600×1200 with EXIF orientation 6 | re-encoded upright `image/jpeg` 1200×1600, `JPEG_LRG` | same pattern | upright, text readable |
| `smoke.mp4` + `smoke.srt` (row 2.5) | video path untouched | HEAD, GET, ranged GETs, `Finished.` | as in Phase 1 |

Two things worth knowing for Phase 3: the TV reports a still as `PLAYING` with
`0:00:00 / 0:00:00`, so the supervisor's `started` latch works unchanged for photos and the
slideshow interval must be the laptop's clock, not the TV's position; and the TV re-fetches
the whole photo (HEAD + GET, sometimes twice) rather than ranging into it, so a prepared
file must stay served for as long as the photo is on screen - which is what pinning in
`photos.py` (Phase 2 review F2) guarantees.

## Follow-up 2026-09-10 — Phase 3: two SOAP faults the Samsung answers with

Seen during manual rows 3.4 and 3.6 on the `83" OLED` (192.168.50.142) from the Fedora laptop,
with the supervisor sending `SetAVTransportURI` then `Play` exactly as the one-shot script did.
Both are HTTP 500 on the SOAP call; the UPnP code sits in the fault body, and the supervisor now
reports it (`describe_soap_error`).

| when | the TV answers | what it means | supervisor |
|---|---|---|---|
| `Play` for a still, after the TV already HEAD+GET the photo during `SetAVTransportURI` | `701 Transition not available` | the transport is already `PLAYING`; there is no transition to make. Not deterministic: the same photo sometimes gets `Play` accepted (the fetch had not finished yet), which is what Phase 2 saw | on 701, ask `GetTransportInfo`; `PLAYING`/`TRANSITIONING`/`PAUSED_PLAYBACK` means the cast is fine, anything else is a refusal |
| `SetAVTransportURI` with port 8895 rejected by firewalld | `716 Resource not found`, immediately, no request ever reaches the server | the TV probes the URL inside `SetAVTransportURI` and gives up when the port is closed; the "wait the budget, then see zero requests" path never runs | 716 with `item.requests == 0` is the `tv_fetched_nothing` diagnosis with the firewall command; 716 after a request is `tv_rejected` |

The `requests == 0` budget path stays for renderers that accept the URI and never come for it.

### Manual rows 3.3, 3.5 and 3.7 — evidence (written 2026-09-11, Phase 3 review F9)

Run on 2026-09-10 from the Fedora laptop (192.168.50.198) against the `83" OLED`
(192.168.50.142), together with rows 3.4 and 3.6 above; confirmed by Piotr on 2026-09-11 when
this note was written, one day after the run.

| row | material | observed |
|---|---|---|
| 3.3 | laptop browser and phone, `http://192.168.50.198:8895/ui/` | the UI opened on both; the header showed `83" OLED` (192.168.50.142) |
| 3.5 | a CLI cast running, server started with `--debug` | Stop from the UI stopped it; a replace from the UI (a session item) took over; `--debug` showed no 404 for the replaced item's URL |
| 3.7 | the TV switched off / disconnected while selected | the header flipped to unreachable; retry (Search again, the TV back on) recovered it |

## Follow-up 2026-09-12 — Phase 4: the GoPro API, probed

Both probes the plan asked for, run with a fresh browser token against the live library
(1 503 items, `HERO11 Black`), from `castlib.sources.gopro.api` on the Fedora laptop. The
recorded shapes are the fixtures under `tests/fixtures/gopro/` (ids and the user id replaced).

### Listing: `GET /media/search`

- Without a `fields` filter an entry has 69 keys. The ones that matter: `id`, `filename`,
  `content_title` (often `null`), `captured_at`, `file_size`, `type`, `width`, `height`,
  `source_duration`, `thumbnail_available`, `play_as`, `item_count`, `available_labels`.
- **There is no `duration` field** (the old `fields=…,duration` was silently ignored).
  `source_duration` is **milliseconds as a string** (`"9280"` for a 9.28 s clip of 136 MB, which
  is the README's 117 Mbit/s 5.3K case; `"0"` for a burst; `null` for a photo).
- `resolution` is `"3360p"` or `"12000000"` and is useless; `width`/`height` carry the frame.
- `_pages` is `{current_page, per_page, total_items, total_pages}`; `per_page=100` works.
- Types seen: `Video`, `Photo`, `Burst`, `TimeLapseVideo`, `MultiClipEdit` (an edit: no
  `file_size`, empty `filename`). **No `LivePhoto` in this library**, so the livephoto fixture
  is synthetic and marked so; `Audio`-like kinds were not seen either.
- **Thumbnails**: `thumbnail_available: true` on every item, but no URL anywhere in the entry
  (`thumbnail_url`, `image_url`, `_links`, `sprites` are absent or empty) and
  `/media/{id}/thumbnails` is 404. What exists: `GET /media/{id}/download?labels=large`
  answers one `large` **JPEG still for videos** (1280×1120 / 96 KB for the 5.3K clip,
  3840×2160 / 338 KB for a timelapse), on the CDN, **no auth needed**. For photos and bursts
  the only image is the multi-MB `source`, so the grid shows a placeholder for stills.
- `GET /media/{id}` returns the full entry (200), so a bare id from the command line resolves
  without a listing.

### Download: `GET /media/{id}/download`

| type | `variations` (label · type · size) | `files` | `sidecar_files` |
|---|---|---|---|
| Video | `edit_proxy` mp4 1024×896, `audio_proxy` m4a 0×0, `source` mp4 3840×3360, `high_res_proxy_mp4` mp4 1280×1120 | the proxy again, `item_number: 1` | `gpmf`, `gpx`, `mediainfo` |
| TimeLapseVideo | same four | same | `gpmf` |
| MultiClipEdit | `baked_source` mp4 2880×2160 | same | `edl_mce` json |
| Photo | `source` jpg 4000×3000 | the same jpg | `mediainfo` |
| Burst | `source` jpg 5568×4872 | **30 frames**, `item_number` 1..30 | `zip` |

- The `label` names the ranking knows (`source`, `high_res_proxy_mp4`, `edit_proxy`) are all
  there; `baked_source` is new and ranks with `source`; `audio_proxy` (`m4a`) and the sidecars
  are never candidates.
- **The CDN labels JPEGs `binary/octet-stream`** (a photo's `source`, a timelapse's `large`);
  a video's `large` came back `image/jpeg`. So the still probe accepts octet-stream by
  extension, exactly as the video probe has since `223eca1`, and the thumbnail proxy types its
  answer from the bytes (JPEG/PNG/WebP/GIF signature), never from the upstream's word.
- A burst's `source` is the frame the library shows; frames 2..n are not stand-ins for it.

### Row 4.2, live (2026-09-12)

`cast-gopro -n 5` listed five 3840×3360 clips with sizes and dates; `cast-gopro 1 --url-only`
printed `quality: high_res_proxy_mp4 (binary/octet-stream, 9 MB)` and the signed proxy address
(the clip is 117 Mbit/s, so proxy is the default); `-q source` printed the 130 MB source
address. `cast-gopro 6984c6c105a9120ae811790b --url-only` (a `Photo` named by its bare id,
never listed in that process) printed the signed `source/default/1.jpg` address through the
`GET /media/{id}` fallback.

### Manual rows 4.3, 4.4 and 4.5 — evidence (2026-09-12, run by Claude at Piotr's request)

Laptop only (Fedora, Chrome driven through the extension, navigated same-site so the
Origin/Host check let it in); the real server (`.venv/bin/python -m castlib --no-browser
--debug`, port 8895), the real GoPro API with a token pasted that morning, and the `83" OLED`
(192.168.50.142). **The phone was not exercised** (no phone in the loop); that part stays open.

| row | material | observed |
|---|---|---|
| 4.3 | the stored token; the gate with the paste field | On entering the tab the stored token was verified (`connect {}`) and the list appeared: 100 tiles per page, "Load more" for page 2, real JPEG stills on all 74 videos (loaded through the proxy from the CDN's octet-stream), placeholders on the 26 photos, "too heavy: 118–122 Mbit/s" on every HERO11 clip; tab hint and list header read "token stored 14 min ago". The paste itself: garbage pasted in the gate answered "GoPro rejected the token (401)" under the field, saved nothing, and the tab stayed "not connected"; a valid paste through the same field was exercised earlier the same day against the scripted API (demo server) with the list appearing straight after. |
| 4.4 | `GX011767.MP4`, 9 s, 3840×3360, 130 MB, 118 Mbit/s | The play button opened the two-button choice with Proxy marked recommended. Proxy: the TV fetched the 9.2 MB `high_res_proxy_mp4` (HEAD, GET, ranged GETs in `--debug`), `started` latched, `duration 0:00:09`, played to the end and stopped. Source: the TV fetched the 136 MB source in ranged GETs (10 requests), never left `STOPPED`, and `tv_never_started` was reported after the 24 s budget in the bottom bar ("GX011767.MP4: The TV never started playing.", Details, Diagnostics badge 1). The hint was empty at that point; `_never_started` now probes a relayed item by its fresh address, so the "118 Mbit/s … try a lighter variant" hint appears (unit-tested, not re-run on the TV). |
| 4.5 | a garbage token written into `gopro-token`, then Refresh | The real 401 flipped the tab to "token expired" and the banner ("The GoPro token expired … paste a fresh token") sat above the list, which stayed on screen with its thumbnails. Recovery: the real token restored on disk and `POST connect {}` sent from the page (a paste of the real token was not typed, to keep it out of the transcript): the banner went, the list stayed, the header read "token stored 19 min ago". The literal banner paste was exercised against the scripted API earlier the same day. |

Two changes came out of the run: a pasted token is verified before it is saved (a bad paste
used to overwrite a working stored token), and the never-started probe reads the relayed
address instead of the media id.


## Follow-up 2026-09-12 — Phase 5: OneDrive, built on doc-shaped Graph before any live call

No Entra registration existed when the phase was built (nothing under `~/.config/cast-tv`, no
client id anywhere in the repo), so the code and tests were written without a live call to
Microsoft; the client id arrived at the end of the session (below). What that means, honestly:

- **The Graph fixtures are hand-written from the docs, not recorded.** `tests/fixtures/onedrive/`
  follows the `driveItem` reference (`file`/`folder`/`image`/`photo`/`video` facets,
  `thumbnails[0].{medium,large}.url` via `$expand`, `parentReference.{id,path}`,
  `@odata.nextLink` with `$skiptoken`). The first live listing should be checked against them,
  field by field: `video.duration` (milliseconds), `video.bitrate` (bit/s), `photo.takenDateTime`,
  the thumbnail set shape, and `parentReference.path == "/drive/root:"` for children of the
  root (the crumbs rely on it to stop). Anything that differs is a fixture fix, not a design one.
- **Client id.** Piotr registered the app during this session and handed over the Application
  (client) ID `652b2cf9-87f7-4d48-a6cf-67ed3ad8c9b6`; it ships as
  `castlib/sources/onedrive.py:DEFAULT_CLIENT_ID` (not a secret) and `ONEDRIVE_CLIENT_ID`
  overrides it. With the default emptied, the gate's Connect answers `400 no_client_id` with the
  registration steps as the hint (personal accounts, "Mobile and desktop applications", "Allow
  public client flows = Yes").
- **The device code endpoints, error names and refresh grant** are exactly the ones the plan
  sourced on 2026-09-09; `tests/test_onedrive.py::FakeMicrosoft` scripts them and the same stub
  plays Graph, so the tests cover the full path from code to listing to download address.

Decisions taken while implementing (also in the plan's Addenda):

| what | decided |
|---|---|
| `connect({})` | stored and not expired → verify against `/me` (refreshing silently) and report `connected`; nothing stored, or `expired`, or `{"fresh": true}` → start a device flow and answer `{step: "code", user_code, verification_uri, expires_in, message}`; a flow already pending → the same code again, never a second flow; `{"cancel": true}` ends it |
| the poll thread | saves the token and flips to `connected` under the source lock **only** if no disconnect or restart happened since the flow started (generation + identity of the flow record); a token that arrives after `disconnect()` is dropped (`test_disconnect_during_the_flow_drops_a_late_token`) |
| `page` | must be Graph's own `@odata.nextLink` (`startswith(GRAPH + "/")`), else `400 bad_page` before any request: the bearer never travels to another host |
| `path` | a folder id matching `^[A-Za-z0-9!_.\-]{1,128}$`, else `400 bad_path` |
| crumbs | from a per-process `folder id -> (parent id, name)` map filled by listings; a folder never listed (a deep `?path=` on entry) is looked up with `GET /me/drive/items/{id}?$select=id,name,parentReference` and walked to the root, at most 32 hops |
| thumbnails | the listing's `large` (else `medium`) address is reused for 30 min, then `GET /me/drive/items/{id}/thumbnails` fetches a fresh one; an item with no thumbnail set gets the placeholder tile |
| photo cache `version` | `lastModifiedDateTime:size`, both already in the `$select` list |
| heavy video | `warn` from `video.bitrate` (or size×8/duration when absent) above 60 Mbit/s; **no `variants`**, OneDrive has no lighter file to offer, so the tile warns and casts the one file |
| hidden kinds | a still that fails `is_allowed_photo` (GIF, raw) is logged once per session; a document (PDF) is quietly not media |

Row 5.1 evidence (2026-09-12): `python -m pytest tests/` → 170 passed (155 before, 15 new in
`tests/test_onedrive.py`); `pyflakes castlib tests` clean.

UI smoke (2026-09-12, Claude, Chrome through the extension, laptop only): on the real server
(`-p 8896`, no client id) the OneDrive gate answered Connect with "No Entra application id is
configured for OneDrive." plus the registration hint; on a stub-backed server (`-p 8897`,
`FakeMicrosoft` from the tests behind `devicecode.AUTHORITY`/`onedrive.GRAPH`) the gate showed
`ABCD-1234` with the `microsoft.com/devicelogin` link, "waiting for confirmation…", Copy code
and Cancel; after the stub confirmed, the list replaced it with "signed in as Piotr Miller
(piotr@example.com)" in the header, the two folders, the four media tiles (GIF, DNG and PDF
hidden, "too heavy: 119 Mbit/s" on the MOV), Pictures → Camera Roll with the breadcrumb
`OneDrive / Pictures / Camera Roll`, "Load more" appending page two (3 → 5 tiles), and the root
crumb back to the top. No console errors. One observation worth knowing: a tab in a background
Chrome window has `visibilityState: hidden`, so the 1.5 s status poll pauses by design and the
flip to `connected` shows on the next foreground refresh.

Live probe of the registration (2026-09-12, right after the id arrived): `devicecode.start()`
with the shipped client id against the real `login.microsoftonline.com/consumers` answered
200 with a user code, `verification_uri` **`https://www.microsoft.com/link`** (Microsoft's
current page; the older `microsoft.com/devicelogin` is only a fallback in the code, the UI shows
whatever the API returns), `expires_in` 900 and `interval` 5. The code was left unused. So the
registration allows public client flows and personal accounts; nothing beyond that was
exercised, no sign-in happened.

### Live Graph, first contact (2026-09-12) — one fixture assumption was wrong

`GET /me/drive/items/{id}?$select=id,@microsoft.graph.downloadUrl` answers `{"id": …}` and
**nothing else** on this personal drive: any `$select` drops the annotation, whether it names
it or not. A plain `GET /me/drive/items/{id}` carries `@microsoft.graph.downloadUrl` (a
1 061-character `my.microsoftpersonalcontent.com` address), and `GET …/content` answers 302
to the same address. The resolver now fetches the item without `$select` (a few KB) and the
stub mirrors Graph: with a `$select` it answers only the named fields. Everything else the
fixtures assumed held: `folder.childCount`, `image.width/height`, `photo.takenDateTime`,
`video.{bitrate,duration,width,height}` (duration in ms), `thumbnails[0].large.url`
pre-authenticated, `@odata.nextLink` with `$skiptoken`, `parentReference.path`
`/drive/root:` for children of the root; the item ids look like `480EBB28A7DFE5BB!4309` or
`480EBB28A7DFE5BB!s<32 hex>` and pass `ID_RE`.

### Manual rows 5.2–5.5 — evidence (2026-09-12, run by Claude at Piotr's request)

Laptop: Fedora, `.venv/bin/python -m castlib --no-browser --debug` on 8895, Chrome through the
extension for the UI (same-origin navigation; a background window pauses the poll, so
`refresh()` was forced by hand where noted); the Samsung `83" OLED` (192.168.50.142); Piotr's
real OneDrive (`pmiller.software@gmail.com`); client id `652b2cf9-…c9b6`.

| row | material | observed |
|---|---|---|
| 5.2 | code `RAKYC2NX` from the real endpoint, shown in the laptop gate; Piotr signed in on `www.microsoft.com/link` **on the phone** (confirmed by Piotr, 2026-09-12) | the server's poll thread flipped to `connected` with `account: Piotr Miller (pmiller.software@gmail.com)`; `~/.config/cast-tv/onedrive.json` written mode 0600 (2 095 bytes); the laptop UI, refreshed, replaced the gate with the drive root (7 folders, "Nothing castable here", header "signed in as …"). After each of the three server restarts that followed, `POST connect {}` verified the stored sign-in against `/me` and answered `connected` with no new code. |
| 5.3 | `Pictures / OM Workspace / 2026_08_16`, 374 JPEGs (Olympus, 5184×3888) | page 1: 200 items in 2.1 s with `next`; page 2: 174 items in 1.3 s, `next` null; 374 unique ids; crumbs `OneDrive / Pictures / OM Workspace / 2026_08_16` on entry (looked up, the folder was opened by id). UI: "Load more" appended page 2 (200 → 374); thumbnails proxied through `/api/sources/onedrive/thumb/<id>` — `200 image/jpeg`, 137 863 bytes, `nosniff`, `private, max-age=3600` — and real stills in the grid once the tab loaded them (`naturalWidth` 800). |
| 5.4 | **no HEIC and no 4K video existed in this drive** (60 folders walked to depth 3: 43 photos, all JPEG/PNG; 1 video, 2560×1440), so material was made. 4K: the sync mirror (`~/.onedrive-sync`, download-only) holds Olympus `.MOV` clips in `Pictures/OM Workspace/<date>/video/` that the depth-3 walk had missed; `P7242629.MOV` is HEVC 3840×2160 59.94 fps, 134 Mbit/s, 16.5 s, 287 MB — the listing flagged it `too heavy` from Graph's `video.bitrate` facet. HEIC: two files encoded with pillow_heif 1.7.0 / libheif 1.23.3 from `P8163285.JPG` (5184×3888) into `Pictures/OM Workspace/2026_09_12/`, uploaded by Piotr from the phone (the mirror is `download_only`, the app's token is `Files.Read`): `IMG_HEIC_landscape.HEIC` 12.8 MB, and `IMG_HEIC_portrait_orient6.HEIC` 12.7 MB stored sideways (`ispe` 3888×5184) with `irot` 270° CCW and EXIF orientation 6, the way a phone writes a portrait. | **4K video** (2026-09-12, before the HEIC upload): `preparing` → `starting` at 3 s → `PLAYING` at 6 s; the TV opened the relay with `Range=-` → `upstream: 200 video/quicktime, 287249920 bytes`, then thirteen ranged GETs (`bytes=0-`, tail probes, `bytes=116033591-` …) → `upstream: 206`; position advanced; the four quality variants were listed and `auto` was cast. **HEIC** (17:06 portrait, 17:07 landscape): both files listed as `photo … image/heic` with real thumbnails; each cast went `preparing` → `starting` at 6 s → `PLAYING` at 8 s, `converted: true`; the TV HEAD/GET'd the prepared JPEG six or seven times (`Range=-`, 4 360 402 and 4 360 546 bytes, both 4096×3072, EXIF stripped). The portrait file came out on the TV as the source rotated 180° — **a fixture error, not an app one**: its pixels had been rotated 90° CW where EXIF 6 / `irot` 270 expect 90° CCW, and `irot` and EXIF agree with each other, so every HEIF-spec viewer shows the same thing. pillow_heif applies `irot` in libheif and resets the EXIF orientation to 1 (keeping it as `info['original_orientation']`), which is what keeps `photos._convert` from rotating twice; a HEIC carrying EXIF orientation but no `irot` would show as stored, per spec. A corrected `IMG_HEIC_portrait_irot.HEIC` (pixels 90° CCW, `irot` 270, EXIF 6) decodes to the source (mean abs diff 0.04/255); uploaded by Piotr from the phone and cast at 18:17: listed as `image/heic` with a real thumbnail but `width`/`height` null (Graph had not built the `image` facet yet), `preparing` → `starting` at 6 s → `TRANSITIONING` at 8 s → `PLAYING` at 10 s, `converted: true`; the TV HEAD/GET'd the prepared JPEG six times (4 360 212 bytes, 4096×3072, EXIF stripped) and that JPEG matches the source photo (mean abs diff 0.14/255) — upright on screen, the same way round as the landscape one. **Not exercised: the one-hour pause before a seek.** The re-resolve path stays covered by `test_relay.py::test_reresolve_once` and `test_download_url_resolved_on_open`. *Phase 5 review (F9, 2026-09-13): row 5.4 counts as partially verified; the tests are auxiliary evidence only, and the live hour-pause seek is now row 7.5.* |
| 5.5 | **simulated**, not revoked in the Microsoft account: `refresh_token` and `access_token` in `onedrive.json` replaced with garbage, server restarted | `POST connect {}` → `401 refresh_rejected`, message "The OneDrive sign-in is no longer valid (invalid_grant). Connect again.", hint Microsoft's `AADSTS7000012 …`; status `expired`, `stored: true`; `GET list` → the same 401; the laptop UI showed the banner "The OneDrive sign-in expired … Connect again" over the still-visible 374-tile list, and the gate with "Connect again" plus the message once the list was cleared; `connect {}` while expired started a **new** device flow (code `RY47XHN8`), cancelled with `{"cancel": true}` → back to `expired`. The real file restored, restart, `connect {}` → `connected`, root lists 7 folders. A real revoke answers the same `invalid_grant` on refresh, so the path is the one exercised, but the account-side step itself was not. *Phase 5 review (F9, 2026-09-13): the tick was withdrawn; row 5.5 stays open until the app is revoked in the Microsoft account or the criterion is explicitly changed to this simulation.* |

Left running after the run: the server on 8895 with the real sign-in, for Piotr to try the phone.

## Follow-up 2026-09-13 — Phase 6: Google Photos, built on the spike plus the Picker reference

The consent half was proven live on 2026-09-09 (the follow-up above: loopback + PKCE, refresh
token issued, `sessions.create` 200, `baseUrl` 206 with the bearer and 403 without). The
listing and session shapes in `tests/test_gphotos.py::FakeGoogle` are **doc-shaped, not
recorded**: the Picker `mediaItems` reference (`PickedMediaItem{id, createTime, type,
mediaFile{baseUrl, mimeType, filename, mediaFileMetadata{width, height, …}}}`), the
`sessions` reference (`pickerUri`, `pollingConfig{pollInterval, timeoutIn}` as protobuf
Durations like `"5s"`, `expireTime` RFC 3339, `mediaItemsSet`), and the `mediaItems.list`
paging (`pageSize`, `pageToken`, `nextPageToken`). The one live pick of 2026-09-09 confirmed
`type`, `mediaFile.mimeType` and `mediaFile.baseUrl`; the first live pick through the tab
should be checked against the fake field by field, `videoMetadata` in particular (the code
reads a `duration` or `durationMillis` there if present and otherwise leaves the duration
unknown). Anything that differs is a fixture fix, not a design one.

Decisions taken while implementing (also in the plan's Addenda):

| what | decided |
|---|---|
| `connect({})` with a stored consent | one **forced refresh** at the token endpoint proves the refresh token still stands (the Picker has no cheap read that does not open a session); `invalid_grant` → `expired`, the gate returns. A restart therefore answers `connected` with an empty grid, the definition of "connected (Google Photos)" |
| the consent round | `{state: "connecting", step: "consent", detail: {auth_url, expires_in, attempt, note}}`; the server opens the browser itself (`loopback.open_browser`, off under `--no-browser`) and the UI shows the link for copying with the on-host note; a redirect with the wrong `state` answers 400 and the round keeps waiting; `access_denied` → `consent_declined`; no redirect in 5 min → `consent_timeout` and the listener closes; a token answer without `refresh_token` starts a second round with `prompt=consent` (`attempt: 2`), and a second miss is `no_refresh_token` |
| `pick()` | `POST /api/sources/gphotos/pick {}` opens a session and answers `{pick: {session_id, picker_uri, state, expires_in, count}}`; the same object rides on `status().detail.pick`; a second `pick` while one waits answers the same session; `{"cancel": true}` stops the poll thread and deletes the session; the poll thread honours `pollInterval`, gives up at `timeoutIn` (`state: timeout`, session deleted, grid unchanged), and merges only while its generation is current |
| picks and sessions | `picks` is an ordered dict by media id (first-pick order; a re-picked id keeps its place, takes the newer `baseUrl`, gains the session); `sessions` map id → `expire_at` + the ids it holds; `status().detail.picks_seq` moves on every merge, drop or pasted link, and the UI refetches the list when it changes |
| `baseUrl` freshness | reused for 50 min (`BASEURL_FRESH`), then re-listed through a live session holding the id; the relay's and the photo fetch's one retry after an upstream 401/403/404 call the item's new **`MediaItem.refresh`** hook, which re-lists regardless of age; no live session left → `repick_needed` (502) and the tile shows `warn: "re-pick"`; a session Google answers 404 for is dropped |
| `MediaItem.refresh` (new, generic) | optional second resolver; `relay._open` and `photos._fetch` use it on their retry and fall back to `resolve`; `photos._fetch` gained the one retry the relay already had, so a OneDrive photo whose download address died is asked for again too |
| the bearer | `Upstream(baseUrl + "=d" \| "=dv", {"Authorization": "Bearer …"})`, the token fetched at open time (refreshed when within 60 s of expiry); thumbnails are `baseUrl + "=w400-h400"` with the same header, proxied by `/api/sources/gphotos/thumb/<id>` |
| share links | `POST /api/sources/gphotos/link {link}` runs `sharelink.resolve` once and lists the result as a video tile with id `link-<n>` after the picks; the stream address is reused on every open and re-scraped only through `refresh`; pasting the same link twice is one entry; links go with `disconnect()` |
| the API | `_SOURCE` accepts `pick` and `link` as POST steps a source may offer (`SOURCE_EXTRAS`); a source without the method answers `404 not_found` |
| exit | `App.close()` calls `close()` on every source that has one; `GPhotosSource.close()` deletes the open sessions and keeps the consent; `atexit` does the same for the CLI |
| `cast-photos --pick` | connects if needed (prints the consent URL quoted, because it holds `&`), opens a pick, prints the `pickerUri`, waits, lists numbered, asks for a number on stdin, casts it through `cli._cast_item`; `--url-only` prints the `=d`/`=dv` address (the bearer is a header, never in the URL); the sessions are deleted on every exit path |
| the client file | `config_dir()/google-client.json` (or `GOOGLE_CLIENT_JSON`), the console's `client_secret_*.json` for a Desktop app (`installed` or `web` wrapper, or a flat `{client_id, client_secret}`); missing → `400 no_google_client` with the console steps as the hint |
| `MediaItem.version` | the media id (Google keeps it stable and the bytes do not change), so the photo cache holds one conversion per picked photo per process |

Row 6.1 evidence (2026-09-13): `python -m pytest tests/` → 200 passed (182 before, 18 new in
`tests/test_gphotos.py`); `pyflakes castlib tests` clean; `node --check castlib/ui/app.js` ok.
The eleven test names the plan lists exist, plus `test_stored_consent_is_verified_by_a_refresh`,
`test_no_client_file_is_a_config_error`, `test_a_late_pick_after_disconnect_is_dropped`,
`test_picker_401_refreshes_once_then_expires`, `test_share_link_paste_lists_a_video`,
`test_pick_and_link_over_api`, `test_cast_photos_pick_over_the_cli`. One hazard found while
writing them: a stub `baseUrl` that carried a query string made `baseUrl + "=d"` land the
suffix after the query; real `baseUrl`s carry no query, so the fake now keeps its per-listing
signature as a path segment. `test_ui_is_self_contained` also refused an `https://` in the
link input's placeholder; the placeholder reads `a photos.app.goo.gl link` now.

UI smoke (2026-09-13, Claude, Chrome through the extension, laptop only, stub-backed server on
8898 with `FakeGoogle` behind `loopback.TOKEN`/`gphotos.PICKER` and a `FakeTV`; the extension's
navigations are cross-site, so the page was reached from a same-site link page on 18898 as in
Phases 4 and 5): the Google Photos gate showed "Connect Google Photos" with the scope note;
Connect flipped it to "waiting for consent… valid 5 min" with the on-host note, Copy link and
Cancel, and the tab hint read "waiting for consent…"; the fake's browser landed the redirect
(200, "Google Photos is connected.") and the tab showed the pick bar ("Pick in Google Photos"),
"Nothing picked yet…" and the share-link paste; Pick showed "Open the picker", "waiting for
your pick… valid 10 min", Copy link and Cancel; a fake pick of three photos and a video landed as
four tiles with thumbnails proxied through `/api/sources/gphotos/thumb/<id>`, the header count 4,
the hint "4 picked" and the button relabelled "Pick more"; casting `beach.jpg` from the tile
went `preparing` → `playing` with the bottom bar "beach.jpg · on screen", the photo fetched from
the stub with the bearer and converted. No console errors. A tab in a background Chrome window
has `visibilityState: hidden` and pauses the poll, so `refresh()` was forced by hand where the
flip had to be observed, as in Phase 5.

**Not exercised: anything against the real Google.** The consent on the host, the pick from
the phone, the 60-minute re-list and the real share link are rows 6.2–6.5 and need
`~/.config/cast-tv/google-client.json` (the Desktop-app JSON downloaded on 2026-09-09 sits in
`~/Downloads/client_secret_26923464307-….json`; copy it there, mode 0600).

### Manual rows 6.2 and 6.3 (first attempt) — evidence (2026-09-13, Piotr at the TV, Claude on the laptop)

Laptop: Fedora, `.venv/bin/python -m castlib --debug` on 8895 (later `--no-browser --debug`,
restarted by Claude); the Samsung `83" OLED` (192.168.50.142); Piotr's Google account as the
test user of the `cast-tv` Cloud project; client file copied from
`~/Downloads/client_secret_26923464307-….json` to `~/.config/cast-tv/google-client.json` (0600).

| row | observed |
|---|---|
| 6.2 | Piotr pressed Connect in the Google Photos tab on the laptop and consented in the laptop's browser (confirmed by Piotr, 14:21). `status`: `connected`; `~/.config/cast-tv/google.json` mode 0600, 525 bytes, keys `access_token, account, expires_at, refresh_token, scope`, scope `…/auth/photospicker.mediaitems.readonly`, **refresh token present**, access token valid ~58 min. Server restarted (14:25): before any call `disconnected` with `stored: true`, `picks: 0`; `POST connect {}` (what the tab does on entry) → `connected` with no consent round; `GET list` → `{"items": []}`. Connected, grid empty. |
| 6.3, first pick | Piotr picked **five photos** (no video) on the phone; all five landed in the grid (`picks: 5`, session `mediaItemsSet: true`, `expireTime` +7 days). |

**Live Picker shape vs the test fake (the check the Phase 6 follow-up asked for).** Five
`PickedMediaItem`s fetched with the stored token: top-level keys exactly `createTime, id,
mediaFile, type`; `createTime` with milliseconds (`2026-09-04T13:00:51.646Z`); `mediaFile` keys
exactly `baseUrl, filename, mediaFileMetadata, mimeType`; `mediaFileMetadata` carries
`width`/`height` as JSON integers plus `cameraMake`, `cameraModel` and `photoMetadata`
(`focalLength, apertureFNumber, isoEquivalent, exposureTime`); `baseUrl` carries no query
string (so `baseUrl + "=d"` is right, and the fake's path-segment signature matches). The
session answer is `{id, mediaItemsSet, expireTime}` plus `pickerUri`, with `pollingConfig`
absent once the pick is set. All as the fake has it. **`videoMetadata` is still unseen**: no
video was picked yet.

**The green frame (6.3, first cast).** `PXL_20260904_125850108.MP.jpg` (3000×4000,
5 178 290 bytes) cast from the grid went `preparing` → `starting` → `PLAYING`; the TV
HEAD/GET'd the full file six times (`0-5178289/5178290`); **the screen showed a plain green
portrait-shaped rectangle** (Piotr's photo of the TV, 15:07). The photo had been passed through
untouched (JPEG, orientation 1, under 4096 px: the Phase 2 rule). Its structure: a Pixel
"Ultra HDR" motion photo — the primary JPEG ends at byte 3 754 860, then a second JPEG, the
**gain map** (124 833 bytes, listed in XMP `Container:Directory` as `GainMap`), then an **MP4**
(`ftyp` at 3 879 699, `GCamera:MotionPhoto="1"`); the header announces them with an **MPF** APP2,
an **ISO 21496-1** APP2 and `hdrgm:` XMP. Pillow reads it as a single 3000×4000 JPEG. Which of
these trips the Samsung's decoder was **not isolated**. What rules one explanation out: the
Olympus JPEGs cast in Phase 5 carry ~400 KB after their EOI too, with no MPF and no gain map,
and showed correctly — so unannounced trailing bytes alone are not it.

Fix: `photos.announces_extra_images()` — a JPEG whose header carries an MPF or ISO 21496-1 APP2,
or XMP with `hdrgm:` / `GCamera:MotionPhoto` / `GCamera:MicroVideo` / `Container:Directory`, is
re-encoded (quality 92) to the primary image alone. The real file: flagged, re-encoded in
0.21 s to 4 286 753 bytes, 3000×4000, no MPF, no `ftyp`, ends at its EOI; two Olympus files:
not flagged, still passed through byte for byte. **The re-encoded file on the TV is not yet
seen** (the restart that loaded the fix drops the picks; the re-pick below is that check).

**An orphaned session and a plain `kill`.** Restarting the server with `kill -TERM` left the
first pick's session alive at Google (`GET /v1/sessions/10b5…` → `mediaItemsSet: true` after the
process was gone): SIGTERM bypassed both `App.close()` and `atexit`. Deleted by hand (`DELETE`
200, then `GET` 404). `App.run_forever()` now turns SIGTERM into the Ctrl+C path
(`test_sigterm_closes_sources_like_ctrl_c`); the next restart printed "Stopped." on its way out.

### Row 6.3, second attempt — the show failed on the video (2026-09-13, 16:02)

Piotr picked five Pixel photos and one video (`PXL_20260205_143617434.mp4`, 3840×2160, 33.9 s,
183 983 754 bytes) and started a show on the laptop, interval 8 s, with the video first. Piotr
reported "all is working"; **the server says otherwise**: the show ended `finished` with
`skipped: 6` of 6, and the error ring holds, in order, `tv_rejected … timed out` (16:02:54,
the video) and seven `tv_rejected … UPnP 701: Transition not available` (16:03:03–16:03:36,
the video twice more, then each photo within two seconds). The TV answered `STOPPED` afterwards,
its last track the video with duration `0:00:33`.

What happened, from the log and from direct probes with the stored token:

| request | answer |
|---|---|
| `baseUrl=dv` with the bearer | **302** to `video-downloads.googleusercontent.com` (no query on the `Location`) |
| that target, with `Range: bytes=0-3`, `bytes=183983626-`, `bytes=1000000-1000003`, or none; with or without the bearer | **200, the whole 183 983 754 bytes, no `Accept-Ranges`**, 4.6–8.6 s to the first byte |
| the same download, measured | first byte after 5.4 s, then 59 MB/s (473 Mbit/s): about 13 s for the whole file |
| `baseUrl=dv` **without** the bearer | 403 (the bearer is needed on the first hop only) |
| `baseUrl=m37` with the bearer | 302 to `rr…googlevideo.com`; the target honours Range (206) without the bearer; ffprobe: H.264 1920×1080 30 fps, AAC, 33.9 s, 2.5 Mbit/s, 10.6 MB |
| `baseUrl=m18` | the same host, 206; H.264 640×360, 0.8 Mbit/s, 3.2 MB |
| `baseUrl=m22` | 206 on a byte range (13.5 MB) but ffprobe could not read it |
| `baseUrl=d` on the video (its still) and on photos | 206 for bounded and open-ended ranges, no redirect |

So the relay could not answer the TV's tail probe (`Range: bytes=183983626-`; this MP4 keeps its
index at the end) without reading 184 MB from the start, inside `SetAVTransportURI`, whose SOAP
call times out at 10 s. The TV stayed mid-transition and refused the next calls with 701, so the
show skipped every item in a few seconds. The relay also copied `Authorization` onto the
cross-host redirect (the default urllib redirect handler copies every header).

**Decision (Piotr, 2026-09-13):** "Original, downloaded first", with Google's 1080p stream offered
as the lighter choice on the tile. Implemented:

- `MediaItem.download` (and `progress`); `castlib/downloads.py` fetches such an item into a
  per-process directory under `/var/tmp` (disk: on this machine `/tmp` is a 15.6 GB tmpfs,
  `/var/tmp` is on the btrfs root with 348 GB free) **before** `SetAVTransportURI`, then the
  server serves it as a local file. Bounded LRU (4 GiB, 16 entries) reusing the photo cache's
  pinning; `release` on registry removal and on a cast that ends unregistered; the directory goes
  at exit. A newer cast or show abandons the download between reads (`read1`, so a slow link does
  not freeze the progress or the abandon check); refused once → re-listed through `refresh`,
  refused twice → `download_refused`; not enough room (`free < size + 256 MB`) → `no_space`.
- Google video tiles carry `variants`: **Original** (`WxH, downloads first`, default) and
  **1080p stream** (`=m37`, relayed). `quality: "auto"`, a show, and `cast-photos --pick` take
  the original.
- `net.BEARER_SAFE`: the opener the relay, the photo fetch, the thumbnail proxy and the download
  use; it follows redirects but drops `Authorization` when the host changes.
- The UI's cast bar reads "downloading NN%" while a video is fetched.

Tests: 209 passed (six new in `tests/test_gphotos.py`: variants, fetched whole before the TV is
told with the bearer kept off the second host, abandoned by a newer cast with the partial file
removed, refused once/twice, no room, same-host vs cross-host bearer). The fake now mirrors
Google: `=dv` and `=m37` answer 302 to the stub under the name `localhost` (another host), the
`=dv` target ignores Range. **Not yet seen on the TV: the downloaded original playing, and a
show that plays through.**

### Row 6.3 — evidence (2026-09-13, 17:25 and 18:03, Piotr at the TV)

The six items of Piotr's third pick (phone, 16:24): `PXL_20260205_143617434.mp4` (3840×2160,
33.9 s, 184 MB) and five Pixel photos, all `.MP.jpg` Ultra HDR motion photos (4000×3000 /
3000×4000), among them `PXL_20260904_125850108.MP.jpg`, the one that had shown as a green frame.
Shows started from the laptop UI (17:25, by Claude in Chrome, the real Start show button,
`/api/show` → 202) and through the API (18:03, at Piotr's request, so he could watch it), both
interval 8 s, the video first.

| show | server | TV (Piotr) |
|---|---|---|
| 17:25 | the original downloaded before `SetAVTransportURI`, then `PLAYING` 0:01 → 0:31 of 0:33; the five photos 17:25:44 → 17:26:40, each held for the interval; `finished`, **skipped 0**, no new errors | — (not remembered) |
| 18:03 | video 18:03:36 → 18:04:10 (served from the download cache, no second download); photos at 18:04:12, :22, :30, :38, :46; `finished` 18:04:52, **skipped 0**, no new errors | **"All ok"**: the video played to its end, the five photos showed as photos, upright, the formerly green one included |

Piotr's own Start show on the phone (before 17:22) never reached the server (no show was
created, no error logged); the laptop UI's identical click did. Not diagnosed; the likeliest
reading is that no tile was ticked, since the Start show bar only appears with a selection.

Open, not blocking 6.3: the single photo cast at 16:26 (`…130719574.MP.jpg`, from a tile) was
recorded as `tv_rejected … UPnP 701` although the TV showed it and still reported `PLAYING` on
that URI an hour later: the 701-on-`Play` exemption (Phase 3) asks `GetTransportInfo`, and that
answer did not read as playing at that moment.

### Row 6.5 — evidence (2026-09-13, about 18:14, Piotr at the TV)

Piotr made a share link in Google Photos on the phone (Share → Create link) for a video and pasted
it into the tab's link field: it was listed as tile `link-1` (`KwhGzcxkNtQpudc46`, video,
`video/mp4`, after the six picks). Cast from the tile: **the video played to its end** (Piotr:
"Link dodany, video odtworzone"); the server's cast ended `stopped` with no error, duration
`0:00:08`, seven TV requests. The scraper's stream answered like the picked original: **200 and
the whole file whatever the Range** (3 553 136 bytes), so the relay trimmed every range itself
(`bytes=3553008-` among them). It works because the file is small; a long shared video would meet
the same 10 s SOAP window the picked 4K video did. Share links still relay (the plan's "plays as
before"); fetching them whole like picked originals is a one-line change left for Piotr to decide.

**The first two casts of the link failed** (18:14:18 and 18:14:21, `tv_rejected … UPnP 701:
Transition not available`, item `link-1`); the third played. Together with the photo at 16:26
that is three casts refused by the 701-on-`Play` rule although the TV went on to play: the
Phase 3 exemption asks `GetTransportInfo` once, right after the fault, and the answer at that
moment did not read as playing. Fix in progress (below).

### The 701 fix (2026-09-13, written into the working tree at 18:20, deployed after row 6.4)

Three casts in this session were marked `tv_rejected … UPnP 701` although the TV went on to play
them: the photo at 16:26 (still `PLAYING` on its URI an hour later) and the share link twice at
18:14 (the third attempt played). The Phase 3 rule asked `GetTransportInfo` once, right after the
701 on `Play`. The state it saw was not recorded, so the exact reading is unknown; the fix makes
the next one visible.

`Cast._settles_playing`: after a 701 on `Play`, `GetTransportInfo` is asked every 0.5 s for up to
4 s (`PLAY_701_GRACE`, `PLAY_701_STEP`); `PLAYING`, `TRANSITIONING` or `PAUSED_PLAYBACK` means the
cast is fine; still not playing at the end → `Play` once more; refused again → one last look, then
`tv_rejected` whose message now ends with the states seen (`after it the TV reported STOPPED,
STOPPED, …, Play refused again, STOPPED`). A stop or a newer cast inside the window sends no second
`Play`; `_promote` handles it as before. Tests: 212 passed (three new in `test_supervisor.py`: the
TV starts by itself after a 701, starts after the second `Play`, a stop in the window sends no
second `Play`; the existing 701 test now also checks the retry and the reported states). The fake
TV gained `faults_once`.

### Row 6.4 — evidence, server side (2026-09-13)

Material: `PXL_20260904_125023968.MP.jpg` (Pixel Ultra HDR motion photo, 4000×3000, 5 587 717 bytes
at Google), picked from the phone into its own session at 18:18:59, never prepared or cast by this
server process before. Its address as Google listed it was saved at 18:23 (it answered `206` then).

| time | observed |
|---|---|
| 20:19:43 | the server prepared the photo: `/tmp/cast-tv-photos-gts3hedd/pwrpxz64m.jpg`, 4 386 210 bytes — byte for byte the size `photos._convert` gives the file downloaded fresh from Google (re-encoded: it announces a gain map), 121 minutes after the pick |
| 20:19:44 | the address saved at 18:23 answers **`403`**: expired. So the fetch a second earlier used an address the server had just re-listed (the 50-minute rule), not the one from the pick |
| 20:21:41 | cast again through the API for Piotr to watch: `preparing` → `starting` → `PLAYING` at 20:21:46, six TV requests, served from that prepared file |

The same minutes show why Piotr "did not know which photo was on": between 20:19:43 and 20:20:10
his taps on three other tiles drew nine `tv_rejected … UPnP 701` (the old rule, still running on
this process; the fix above is deployed after this row), and the TV had gone quiet at 19:32
(`tv_unreachable`), presumably its own standby.

TV side (Piotr, 20:22): **"Potwierdzam"** — the landscape photo on screen was the one described
to him from the prepared file (a brown one-storey wooden building with a red roof, a round conifer
in front on a paved square, a green picket fence with a red spring-rider horse on the lawn, a lake
and a willow behind), upright and in normal colours. Row 6.4 ticked.

### Row 6.5 — re-check after the Phase 6 review fixes (2026-09-13, 22:16–22:23, Piotr at the TV)

Server restarted on `cdbdb0f` (share-link host allowlist, redirect guard on every hop, guarded
relay). Three links pasted:

- `link-1` `Nj2VHaD5bqKviYhq6` and `link-2` `Vdc9XaAhsYEedMAa8` — share links to a **photo** (a
  motion photo). Resolved through the allowlist (`=dv` on `lh3.googleusercontent.com` →
  `video-downloads.googleusercontent.com`); the answer is the photo's embedded clip, 2 969 708 bytes
  (ffprobe: 1.78 s HEVC 1440×1080 at 120 fps, a second HEVC 2048×1536 still track, two data
  tracks). The TV fetched it (9 requests) and stayed `STOPPED`: `tv_never_started` at 22:16:23 and
  22:20:58. Share links are video-only by design (`plan.md:995`), so not a regression; follow-ups
  in `follow-ups/review-fixes.md`.
- `link-3` `cMSPYewNYdYXjrJq6` — a share link to a **video**: **played to its end** (Piotr: "po
  wklejeniu video 6.5 działa"); cast `stopped` with no error, duration `0:00:08`, seven TV
  requests, 3 553 136 bytes relayed whole-per-request as before (`bytes=3553008-` trimmed by the
  relay). The earlier known-good link `KwhGzcxkNtQpudc46` also still resolves to the same H.264
  file with the new code (checked off the TV).

### Row 6.3 — re-check after the Phase 6 review fixes (2026-09-13, 22:27, Piotr at the TV)

Same server (`cdbdb0f`, pid 726890), after Connect with the stored consent and a pick on the
phone: `VID_20240830_220448.mp4` (1920×1080) cast as **Original**. It was fetched whole first —
6 132 233 bytes into `/var/tmp/cast-tv-videos-726890-d6d3zl1_/` (the new pid-named directory; the size is well inside the per-file
limit, the budget and the reserve) — and the TV's ranges were answered from the local file
(`Range=bytes=6132105- -> 6132105-6132232/6132233`, no relay trimming). **The video played**
(Piotr: "6.3 zrobione, film zagrał"); cast `stopped` with no error, duration `0:00:11`, six TV
requests. The file stays in the download LRU after the cast (for a re-cast) and goes on eviction
or at exit.

## Follow-up 2026-09-13 — Phase 7: packaging and the Linux stay-awake

### Row 7.2 — `pipx install .` on Fedora (2026-09-13, 23:21, Claude on the laptop)

pipx was not installed on the laptop and `~/.local/bin/cast-{tv,gopro,photos}` are the symlinks
into the checkout, so the install was made into the session scratchpad rather than over them:
pipx 1.x in its own venv, `PIPX_HOME` and `PIPX_BIN_DIR` pointing into the scratchpad,
`pipx install .` from the working tree (Python 3.14.7). Result: "installed package cast-tv 0.2.0
… These apps are now available: cast-gopro, cast-photos, cast-tv"; the three entries in
`PIPX_BIN_DIR` link into the pipx venv; `cast-tv --list` through that entry point printed
`192.168.50.142   83" OLED`; `cast-gopro --help` and `cast-photos --help` answered. Run from `/`,
the venv's `castlib` is the one in its own `site-packages` (not the checkout) and carries
`ui/{alpine.min.js,app.js,index.html,style.css}`; `ifaddr` and `platformdirs` were pulled in as
dependencies. **On the path (23:31, Piotr's condition for ticking the row):** in a shell whose `PATH` starts
with the scratchpad `PIPX_BIN_DIR`, working directory `/` (outside the checkout), `command -v
cast-tv` answered `<scratchpad>/bin/cast-tv`, which `readlink -f` resolves to
`<scratchpad>/pipx/venvs/cast-tv/bin/cast-tv`; `cast-gopro` and `cast-photos` resolved to the
same `bin`; `cast-tv --list` printed `192.168.50.142   83" OLED` and exited 0. **Not done:** replacing the symlinks in `~/.local/bin` with a real pipx install -
that changes Piotr's own environment and waits for him.

### The inhibitor on Fedora 44 (2026-09-13, 23:19, Claude on the laptop)

`StayAwake(SystemdInhibit())`: after `start()`, `systemd-inhibit --list` showed
`cast-tv 1000 piotrmiller … systemd-inhibit sleep:idle casting to the TV block`; after `stop()`,
nothing with `cast-tv`. A child process that took the lock and was then `SIGKILL`ed left no
`cast-tv` line either: the pipe closed, `cat` ended and logind dropped the lock. The laptop's
GNOME power settings suspend after 900 s idle on AC and on battery
(`sleep-inactive-{ac,battery}-timeout`, type `suspend`), so row 7.4's 30-minute show is a real
test: without the lock the laptop would suspend halfway through.

Real discovery through the new per-interface sockets, same evening: `[{'name': 'wlo1', 'ip':
'192.168.50.198', 'responses': 1}]`, the TV found as before, 4.0 s.

### Row 7.1 — the CI matrix (2026-09-14, GitHub Actions, workflow `test`)

Three runs on PR #1, each on `ubuntu-latest` and `windows-latest` with Python 3.12
(`pip install -e .[test]`, pyflakes, pytest):

| Run | Commit | Ubuntu | Windows | What it found |
| --- | --- | --- | --- | --- |
| 34865489954 | `471ca16` | 250 passed | 2 failed, 244 passed, 4 skipped | `SO_REUSEADDR` let a second cast-tv bind 8895 on Windows (`test_addrinuse_attaches_to_running_instance`); the fakes' `monotonic()` stamps tied at Windows' ~15 ms tick |
| 34866064345 | `6d682f6` | 1 failed, 249 passed | passed | a SIGINT inside `run_forever`'s `signal.signal` escaped as a bare `KeyboardInterrupt` (`test_ui_prints_addresses_and_exits_cleanly_on_sigint`) |
| 34866545503 | `92bdfc2` | **252 passed** | **248 passed, 4 skipped** | nothing |

The four Windows skips are the three signal-driven subprocess tests and the Linux-only
`fib_trie` cross-check, as the plan addendum lists. Python on the runners: 3.12.14 (Ubuntu),
3.12.10 (Windows).

### Row 7.4 — first attempt (2026-09-14, 20:11–20:43, Claude on the laptop, the Samsung showing) — row stays open

`cast-tv <20 Olympus JPEGs from ~/.onedrive-sync> -i 120 --show` on 8895 (the live server stopped
for it), on AC power; SIGINT delivered with the default handler, as Ctrl+C in a terminal does.
Logged once a minute: GNOME's idle time (`org.gnome.Mutter.IdleMonitor.GetIdletime`), the
`cast-tv` lines in `systemd-inhibit --list`, and `/api/status`.

- **The lock held throughout:** one `cast-tv … systemd-inhibit sleep:idle casting to the TV
  block` line at every one of the 32 samples; the show reached photo 16 of 20, every cast
  `playing`, the TV `ready`.
- **Ctrl+C released it:** SIGINT at 20:43:24 → the show printed `Stopped.`, exit code 0; at
  20:43:26 `systemd-inhibit --list` had no `cast-tv` line.
- **No suspend:** the journal from 20:11:24 has no suspend, sleep or lid entry.
- **Not proven: "without sleep".** The longest idle stretch was 528 s (20:31–20:40); GNOME
  registered input around 20:13–20:21, 20:27, 20:31 and 20:41. The suspend timeout is 900 s, so
  the laptop would not have slept without the lock either. The only suspend earlier that day
  (19:55) was a lid close, not idle, so there is no idle-suspend baseline yet.

### Row 7.4 — second attempt, part 1: the control (2026-09-14, 20:54–21:10)

With Piotr's consent, GNOME's `sleep-inactive-ac-timeout` was set to 120 s for the test (it was
900). With nothing casting and no `cast-tv` lock, the laptop suspended by itself at 21:01:44
(`PM: suspend entry (s2idle)`; the last idle reading before it was 111 s) and returned at 21:10:05
when Piotr woke it. **So idle suspend works on this laptop**, and a show that keeps it awake
through idle stretches past 120 s is a real test.

The show that followed never started: it was launched at 21:10:07, two seconds after the wake,
before Wi-Fi was back, and SSDP found nothing (`No DLNA renderer answered`). This was a fault of
the test script, not of cast-tv. The same script killed its own parent shell with a `pgrep -f`
pattern (exit 144); its `finally` still restored the timeout to 900 at 21:10:38 and brought the UI
server back. The show part was run again with `-t 192.168.50.142`, a wait for the TV, and process
matching on exact `argv` (below).

### Row 7.4 — second attempt, part 2: the show (2026-09-14, 21:11:36–21:41:38) — passed

`cast-tv <the same 20 Olympus JPEGs> -i 90 --show -t 192.168.50.142`, on AC, suspend timeout 120 s
(the control above showed the laptop suspends at that setting with nothing casting). Sampled every
30 s:

- **Idle and awake:** GNOME idle time climbed without a break from 15.6 s to **1786 s** (nobody
  touched the laptop for the whole show): nearly fifteen times the 120 s timeout in force, and
  twice the usual 900 s. The laptop never suspended: the journal from 21:11:36 has no suspend,
  sleep or lid entry, and the samples ran uninterrupted.
- **The lock:** one `cast-tv … systemd-inhibit sleep:idle casting to the TV block` line at every
  sample; the show went through all 20 photos (photo 20 `playing` at the end), each cast
  `preparing` → `starting` → `playing`, the TV showing them.
- **Ctrl+C:** SIGINT at 21:41:37 with the default handler → `Stopped.`, exit code 0; at 21:41:38
  `systemd-inhibit --list` had no `cast-tv` line.
- Afterwards the suspend timeout was restored to 900 (checked with `gsettings get`) and the UI
  server brought back (pid 881551).

### Row 7.5 — OneDrive video paused over an hour, then a seek (2026-09-14 23:42 – 2026-09-15 00:48, Claude on the laptop, the Samsung playing) — passed

Criterion as changed by Piotr (plan addendum): no film longer than an hour exists on the drive
(whole-drive walk: 1372 folders, 18 videos, longest 180 s), so the seek is within the clip.
Material: `/Dokumenty/Videos/Przejazd - SuperCars.mp4` (180 s, 2560x1440, 414 615 615 bytes),
cast through `POST /api/cast` on the live server (Phase 7 code, `--debug`); Pause, Seek and Play
sent as SOAP from a script (`row75.py`), as the remote would.

- 23:42:17 OneDrive `connect` → `connected`; the stored Graph access token expired at **00:36:05**.
- 23:42:55 the TV at `PLAYING 0:00:30.145 / 0:02:59`; 23:42:58 Pause → `PAUSED_PLAYBACK 0:00:30.145`,
  the cast `paused`.
- Every 5 min for 65 min: the TV still `PAUSED_PLAYBACK 0:00:30.145`, the cast `paused` - the
  Samsung holds a DLNA pause for over an hour. The token passed its expiry at 00:36 during the
  pause.
- 00:47:58 Seek `REL_TIME 0:02:00` → `SeekResponse` (no fault); the TV resumed playback on the
  seek by itself, so the `Play` sent after it was answered with HTTP 500 (already playing - a TV
  answer to a redundant command, not a cast-tv path; cast-tv sends no Seek).
- The seek's request, from the `--debug` log: `GET /m/<token>/<item>  Range=bytes=269885526-` →
  `upstream: 206 video/mp4, 144730089 bytes`. That request needed a fresh download address, and
  getting one needed the expired access token refreshed: after it the token's expiry read
  **01:47:57**, so the refresh happened silently at the seek, and no error reached the UI.
- 00:48:04 the TV at `PLAYING 0:02:07.415`, the cast `playing`; 20 s later `PLAYING 0:02:29.255`
  - playback continued past the seek target. Stopped through `/api/stop` at 00:48:24.

The relay's re-resolve-on-403 path did not fire (no `resolving again` line): OneDrive's resolver
fetches a new address on every open, so the TV's post-pause request never met a dead one.

### Row 4.6 — first attempt (2026-09-15, 00:51–00:53, Piotr with the phone, Claude watching the laptop) — the cast passed, the paste did not count

Watched every 3 s: the peers connected to 8895 (`ss`), the GoPro source's state and the cast.
The phone is `192.168.50.140` (`Pixel-9-Pro-Fold` in DNS, `Android_UH2L45TJ.local` over mDNS); the
laptop's own address is `192.168.50.198` (`wlo1`); the TV is `.142`.

- 00:52:20 `.198` connected (a browser on the laptop, via the LAN address); the stored token from
  2026-09-12 was checked and refused: GoPro state `expired` (`token_rejected`, 401).
- 00:52:23 a fresh token was stored and verified (`connected`, "token stored just now") while
  **only `.198` was connected**: the paste was made on the laptop, as Piotr confirmed. It does not
  count for this row.
- 00:52:41 the phone `.140` connected; 00:53:02 a GoPro cast (`6a6e66e18c0501028937540b`, 2:02)
  started while laptop, phone and TV were connected - ambiguous; `playing` at 00:53:11.
- 00:53:20 the laptop's browser went; 00:53:26 a second GoPro cast (`69bd8021dcdf0360fdd164fd`,
  0:56) started with **only the phone and the TV connected**: `starting` → `TRANSITIONING` →
  `playing` at 00:53:35, 8 TV requests. **The cast from the phone works.** No error in the ring.

The paste is redone from the phone: the source was disconnected through the API (the token file
removed) and the same token pasted again on the phone (below).

### Row 4.6 — second attempt: paste and cast from the phone (2026-09-15, 00:54–00:56) — passed

The GoPro source was disconnected through `POST /api/sources/gopro/disconnect` at 00:54 (state
`disconnected`, `stored: false`, the token file gone); Piotr closed the UI on the laptop and
reloaded it on the phone. Watched every 2 s as before:

- 00:54:52 the only peer on 8895 was the phone `192.168.50.140`.
- **00:56:13 the token pasted on the phone was stored and verified** (`connected`, "token stored
  just now") with **only `.140` connected**.
- 00:56:20 a GoPro cast (`6a6e5e39bbf79a2b637bd876`, 0:14) from the phone, with only the phone and
  the TV (`.142`) connected: `starting` → `TRANSITIONING` → `playing` at 00:56:30 (8 TV requests);
  the clip ran to its end, `STOPPED` at 00:56:42.

Together with the first attempt's second cast (00:53:26, phone and TV only), the gate and the
cast both work from the phone.

**One more observation from the second attempt (read afterwards from `/api/errors`).** At
00:56:19 the ring got `tv_rejected` for the same clip (`6a6e5e39bbf79a2b637bd876`): "The TV
rejected the request: HTTP Error 500 (UPnP 701: Transition not available)", with no "after it
the TV reported …" suffix - so the 701 answered `SetAVTransportURI`, not `Play`
(`supervisor.py`: a 701 on `Play` goes through `_settles_playing`, which records states). Piotr
tapped Cast twice: the first tap's cast went out and played; the second reached the TV while it
was still `TRANSITIONING`, its `SetAVTransportURI` was refused, and that cast ended `failed`
while the first kept playing. Here it was harmless (the same clip), but it contradicts the
`cast (while playing)` definition in the plan ("the request accepted second wins"): with two
different items the second would fail with an error and the TV would stay on the first. Recorded
as a follow-up (`follow-ups/review-fixes.md`).
**Fixed the same night (2026-09-15, Piotr's decision):** a 701 on `SetAVTransportURI` now waits
for the transport to leave `TRANSITIONING` and retries once, and the UI disables Cast while a
request is in flight (plan addendum, Phase 7). Not yet re-run on the TV.
