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

