# Photos through share links Implementation Plan

## Overview

A Google Photos share link to a photo is refused today (`photo_link`: "Share links cast videos
only"). After this change it lists a photo tile in the Google Photos tab and casts the photo. A
motion photo's tile also offers its clip, as Google's H.264 stream `=m37`, because the Samsung
refused the clip's original `=dv` (HEVC at 120 fps, row 6.5). A link to an album is recognised and
refused with its own message; casting albums becomes a separate roadmap slice. Roadmap: S-09
(`context/foundation/roadmap.md`, "### S-09"); the idea is recorded in
`context/archive/2026-09-07-cloud-source-ui/follow-ups/review-fixes.md`.

## Current State Analysis

- `sharelink.resolve(link, cookies_path)` (`castlib/sources/sharelink.py`) fetches the page through
  the guarded `opener()`, raises `photo_link` when `page_kind()` says `photo` (before any probe),
  and otherwise probes `candidates()` with `probe_media(kinds=("video",))`, returning the first
  stream address. It serves both `cast-photos <link>` (`castlib/cli.py:554`) and the UI
  (`GPhotosSource.link()`, and the refresh `again()` in `_link_item`).
- `GPhotosSource.link()` (`castlib/sources/gphotos.py:754-775`) keeps each pasted link in
  `self._links` (`{link, url, name, resolved_at}`, id `link-N`), deduplicated by the link text.
  `_link_entry()` always makes a `kind="video"` tile with no thumbnail; `_link_item()` always makes a
  video `MediaItem` relayed through `sharelink.opener()`; `thumb()` returns `None` for links.
- The photo path is ready for an address behind a guarded opener: `photos._fetch()` opens
  `Upstream.url` with `Upstream.opener` (`castlib/photos.py:204-244`), retries once through
  `MediaItem.refresh` on 401/403/404, and `announces_extra_images()` re-encodes a Pixel Ultra HDR /
  motion-photo JPEG to its primary image (the "green frame" fix). The thumbnail route uses
  `Upstream.opener` too (`castlib/api.py:259-299`).
- A tile with `variants` opens the "Cast which variant?" chooser (`castlib/ui/index.html:383-387`,
  `castNow()` in `castlib/ui/app.js:425`); the chosen `quality` reaches `source.resolve()` through
  `/api/cast`. A show sends no quality, so every item resolves with `"auto"` (`castlib/api.py:136`).
- Precedent: a GoPro livephoto resolves to its still only (`castlib/sources/gopro.py:390`); picked
  Google Photos videos offer `original`/`stream` variants (`gphotos.entry_for()`).

Facts about Google, measured on 2026-10-13 (origin: measurement, `research.md`), not guaranteed
by Google:

- `og:image` base + `=d` serves the full photo without cookies (206 `image/jpeg`).
- On a motion photo, base + `=m37` is H.264 High 1440×1080, 30 fps, AAC (206 `video/mp4`, via
  `googlevideo.com`, honours Range); on a plain photo it answers 404.
- An album page passes `page_kind()` as `photo` (its `og:image` is the cover); it carries more than
  one distinct `/share/<share id>/photo/<item id>` link (5 against 1 on every single-item page) and
  `og:description` "Shared album · Tap to view!". The item-link count is a **heuristic confirmed on
  samples** (five pages, one album of five items), not a documented page structure.

### Carried from predecessor

none — no Predecessor line

## Definitions

| Term | Decided meaning | Origin | On degenerate data (tie, duplicate, empty, boundary, legacy) | Verified by |
| ---- | --------------- | ------ | ------------------------------------------------------------- | ----------- |
| share link to a photo | a share page with `og:image` and no `og:video`, holding one item | user (S-09 outcome) | a page with no Open Graph tags at all is probed as a video, as today (decided 2026-10-13): no candidate address on it → `no_media`; candidates, none answering as video → `no_stream`; known risk below | 1.1 (`test_share_page_photo_*`, `test_no_stream_points_photos_to_the_tab`) |
| motion photo | a photo page whose `og:image` base answers `=m37` as video | user (one tile with a choice; the probe rule, both decided 2026-10-13); detection measured | **only 404** means a plain photo (no clip variant); any other answer that is not video - an HTTP error status (403, 429, 5xx) or a 200/206 of another type (e.g. `text/html`) - or a network failure on that probe fails the paste, naming what came back | 1.1 (`test_share_page_motion_*`), 2.1 |
| the clip | the motion photo's `=m37` stream only; `=dv` is never offered | product (roadmap S-09: the TV refused `=dv`) | — | 2.1 (`test_link_motion_photo_*`) |
| motion-photo tile | one `kind="photo"` tile, variants Photo (default) and Clip; a show casts the photo | user (decided 2026-10-13) | `quality` `"auto"` or `"photo"` → the still; `"clip"` on a plain photo, or any other value → `bad_quality` | 2.1 (`test_link_photo_in_show`, `test_link_motion_photo_*`) |
| album link | a share link with more than one distinct item behind it, recognised by a heuristic confirmed on samples (more than one distinct item link); refused with `album_link` | user ("wiele zdjęć/filmów za jednym linkiem", decided 2026-10-13) | **an album recognised by its several items is refused; a one-item album is handled as its single item** (not measured); an album whose cover is a video is refused too (checked before `page_kind`) | 1.1 (`test_share_link_album_*`) |

## Desired End State

- Pasting a link to a plain photo in the Google Photos tab lists one photo tile with a thumbnail;
  Cast puts the photo on the TV.
- Pasting a link to a motion photo lists one photo tile; Cast opens the chooser with Photo
  (default) and Clip; Photo casts the still, Clip plays the H.264 clip. In a slideshow the tile is
  the still.
- Pasting a link to an album recognised by its several items lists nothing and shows, under the
  link field, that album links are not cast yet. A one-item album is handled as its single item.
- Video links behave as before. `cast-photos <link>` still casts videos only; for a photo link it
  says to paste the link into the Google Photos tab instead, and refuses an album link (recognised
  by its several items) the same way as the UI.
- README, PRD FR-012 and the roadmap say so; casting an album is a new proposed roadmap slice.

### Key Discoveries:

- The `og:image` base is the one to use: every page carries two bases or more, the `og:image`
  base first (`research.md`, "The page"). `candidates()` would also return the unidentified second.
- `probe_media()` returns `None` on any HTTP error and on a success of another type, and raises
  `UpstreamError` on a network failure (`castlib/media.py:178-218`). It cannot tell a plain photo's
  404 on `=m37` from a refusal or an unexpected answer, so the clip probe needs its own status
  handling (Phase 1).
- `net.fetch()` returns the final URL (`castlib/net.py:71-82`); the share id is its path segment
  after `/share/`, which the album check needs.
- `_scripted_links()`, `_page_with()`, `PHOTO_HEAD`, `VIDEO_HEAD`, `PROBED`, `MEDIA_BASE` and
  `SHARE_PAGE` in `tests/test_gphotos.py:1063-1500` script a share page and its probes without the
  network; new tests extend them.

## What We're NOT Doing

- Casting albums: refused with a message; a new roadmap slice (proposed) records it.
- Casting photos from `cast-photos <link>` (CLI): S-09 extends link handling in the tab; reworking
  the `cast-photos <link>` path is out of its scope (decided 2026-10-13). It is a scope line, not a
  technical limit: `--pick` already casts a `MediaItem` through `_cast_item()`.
- Offering the motion photo's `=dv` original, or `=m22`/`=m18`, as variants.
- Telling a one-item album from a single shared photo (not measured; it behaves as its item).
- Sizes or dates on a link tile: the page offers none reliably (`og:image:width` is the 600×315
  preview).
- Changing how a link is deduplicated (by its text) or named (the last path segment).

## Implementation Approach

Split `sharelink` into one page read and two callers. A new `sharelink.shared(link, cookies_path)`
reads the page once, refuses an album, and answers what the link holds: a video (the stream
address, found as today) or a photo (its `=d` address, its thumbnail address, and its `=m37` clip
address when the base answers that as video). `resolve()` keeps its contract for the CLI and the
video refresh: a stream address, or `photo_link` before any probe. `GPhotosSource` stores what
`shared()` answered per link and turns it into a photo tile, a variant chooser for a motion photo,
a photo `MediaItem` (fetched by `photos.py` through the guarded opener) or a clip `MediaItem`
(relayed, as a picked video's stream). Wording, README, PRD and roadmap follow last.

**Known risk (accepted 2026-10-13):** a page without Open Graph tags is still probed as a video,
as today. A motion photo whose page lost its tags may therefore be listed as a video with the
`=dv` original, without the Photo/Clip choice, and its playback may fail. The plan promises no
particular error in that case, and no resilience to a change in Google's page format.

## Phase 1: Read a share page as video, photo, motion photo or album

### Overview

`sharelink` tells the four apart and answers a structured result; the CLI path keeps its
behaviour except for an album and the photo message.

### Changes Required:

#### 1. Share-page classification

**File**: `castlib/sources/sharelink.py`

**Intent**: Read a share page once and say what it holds, so a photo link can be listed instead of
refused, and an album is not mistaken for its cover.

**Contract**:
- New `album_items(html, final_url) -> int`: the count of distinct item ids in
  `/share/<share id>/photo/<item id>` links, where `<share id>` is taken from `final_url`'s path;
  `0` when the final URL is not a `/share/` page. Counted on the page text as fetched (the measured
  form), not on `unescape_google()` output.
- New `og_image_base(html) -> str | None`: the `og:image` content up to its first `=`, only when
  `allowed()` and `MEDIA_HOST` accept it.
- New `shared(link, cookies_path=None) -> Shared`, a small frozen dataclass:
  `kind` (`"video"` | `"photo"`), `url` (the video stream address, or the photo's base + `=d`),
  `clip` (base + `=m37` or `None`), `thumb` (base + `=w400-h400` or `None`). Order: the same
  `allowed()` / media-address / page-status checks as `resolve()`; then **album first**: more than
  one item → `NotMedia("album_link", …)` naming that album links are not cast yet and that a single
  photo or video can be shared instead (one line first: the UI shows only the first line); then a
  `photo` page → probe base + `=d` with `kinds=("photo",)` (no answer → `NotMedia("no_media")`) and
  base + `=m37` for the clip; otherwise the existing video candidate probing, unchanged.
  "No answer" on `=d` is `probe_media()` returning `None` (an HTTP error, or an answer that is
  not a photo) → `no_media`; a network failure or timeout there raises
  `UpstreamError("probe_failed")` and fails the paste (owner decision 2026-10-13; review
  `reviews/impl-review-phase-1-aed13dc.md`).
- The clip probe tells statuses apart, which `probe_media()` does not (it returns `None` on every
  `HTTPError`, `castlib/media.py:200`): a video answer → clip; **404 → no clip**; any other HTTP
  status, or a 200/206 whose type is not video, → `UpstreamError("clip_probe_failed")` naming the
  status and type; a network failure →
  `UpstreamError` as `probe_media()` raises today. `probe_media()`'s behaviour for its other callers
  does not change.
- `resolve()` keeps its signature and answer (a stream address) and its "no probe on a photo
  page" rule; it gains the album refusal (before `photo_link`). `PHOTO_LINK` becomes the CLI's
  wording: `cast-photos` casts videos from links; to cast the photo, paste the link into the Google
  Photos tab of cast-tv's page. The `no_stream` text drops "Share links cast videos only" and says
  a photo link is cast from the Google Photos tab.
- A media address pasted as a link keeps today's behaviour in both functions (video variants).

#### 2. Tests for the classification

**File**: `tests/test_gphotos.py`

**Intent**: Pin each page shape to its outcome without the network, using the measured page
heads.

**Contract**: An `ALBUM_HEAD` (the measured `og:description` "Shared album · Tap to view!") and a
page body helper that emits N `/share/<id>/photo/<item>` links; new tests named
`test_share_link_album_*` (refused on a photo-cover and on a video-cover page, through both
`shared()` and `resolve()`, with nothing probed), `test_share_page_photo_*` (plain photo: `=d`
probed, `=m37` 404 → `clip is None`, `thumb` set; a page with no tags still probed as video) and
`test_share_page_motion_*` (`=m37` answering video → `clip` set; 404 → `clip is None`; 403, 429
and 503 each raise `clip_probe_failed` naming the status; a 200 `text/html` raises
`clip_probe_failed` too; a network failure on that probe raises). Two existing tests change with
the wording: `test_share_link_to_a_photo_says_so_before_any_probe` keeps its name, its message
assertion moved to the new `PHOTO_LINK` text; `test_no_stream_says_share_links_are_video_only`
(`tests/test_gphotos.py:1525`) is renamed `test_no_stream_points_photos_to_the_tab` and asserts the
new `no_stream` text (no "videos only"). A test for a no-tags page without any candidate address
pins `no_media`.

### Success Criteria:

#### Automated Verification:

- The new classification tests pass: `.venv/bin/python -m pytest tests/test_gphotos.py -q -p no:cacheprovider -k "share_link_album or share_page_photo or share_page_motion"` — at planning: exit 5 — expected until Phase 1 (no such tests yet)
- The whole suite passes: `.venv/bin/python -m pytest -q -p no:cacheprovider` — at planning: exit 0
- Pyflakes is clean: `.venv/bin/python -m pyflakes castlib tests` — at planning: exit 0

**Implementation Note**: Phase 1 has no manual rows; the TV checks are in Phase 3.

---

## Phase 2: List and cast photo links in the Google Photos tab

### Overview

`GPhotosSource` turns a photo answer into a photo tile with a thumbnail, a motion photo into a
tile with Photo/Clip variants, and resolves each to the right `MediaItem`.

### Changes Required:

#### 1. Photo links in the source

**File**: `castlib/sources/gphotos.py`

**Intent**: Store what `sharelink.shared()` answered for each pasted link and serve photo links
through the existing photo path, so a link photo casts and joins a slideshow like a picked one.

**Contract**:
- `link()` calls `sharelink.shared()`; the `_links` record gains `kind`, `clip` and `thumb`
  (`url` stays the address to fetch). Deduplication, ids and names are unchanged.
- `_link_entry()`: a video link as today; a photo link → `kind="photo"`, `mime="image/jpeg"`,
  `thumb="/api/sources/gphotos/thumb/<lid>"`; with a clip, `variants` = `photo` (label "Photo",
  `default: True`) and `clip` (label "Clip", note that it is Google's 1080p H.264 stream).
- `resolve(lid, quality)` for a photo link: `"auto"`/`"photo"` → a `kind="photo"` `MediaItem`
  whose `resolve` gives `Upstream(url, opener=sharelink.opener())` and whose `refresh` re-runs
  `shared()` and updates the record; `"clip"` with a clip → a `kind="video"` `MediaItem`
  (`mime="video/mp4"`, `download=False`, relayed) over `clip`, refreshed the same way; anything
  else → `ConfigError("bad_quality")`. `version` distinguishes the two (link + `=d` / `=m37`) so the
  photo cache and the registry never confuse them. Video links ignore `quality`, as today.
- `thumb(lid)`: a photo link's `thumb` address behind `sharelink.opener()`; `None` for video links
  and unknown ids, as today. Today `thumb()` returns `None` for every `link-` id before anything
  else; that early return is narrowed to video links.
- The refresh path of a video link (`again()`) keeps calling `sharelink.resolve()`.

#### 2. Tests for the source

**File**: `tests/test_gphotos.py`

**Intent**: Prove the tile shapes, the variant resolution, the thumbnail guard and the show
default.

**Contract**: New tests named `test_link_photo_tile_*` (plain photo: one `kind="photo"` tile with a
thumb and no variants; `resolve("link-1")` is a photo `MediaItem` whose upstream opener carries
`_GooglePhotosOnly`; `thumb("link-1")` goes through the guard), `test_link_motion_photo_*` (Photo
and Clip variants; `"clip"` → a relayed video item on the `=m37` address; `"clip"` on a plain photo
and an unknown quality → `bad_quality`) and `test_link_photo_in_show` (a `POST /api/show` with a
photo link and no quality resolves to the still). Existing video-link tests keep passing.

### Success Criteria:

#### Automated Verification:

- The new source tests pass: `.venv/bin/python -m pytest tests/test_gphotos.py -q -p no:cacheprovider -k "link_photo_tile or link_motion_photo or link_photo_in_show"` — at planning: exit 5 — expected until Phase 2 (no such tests yet)
- The whole suite passes: `.venv/bin/python -m pytest -q -p no:cacheprovider` — at planning: exit 0
- Pyflakes is clean: `.venv/bin/python -m pyflakes castlib tests` — at planning: exit 0

**Implementation Note**: Phase 2 has no manual rows; the TV checks are in Phase 3.

---

## Phase 3: Wording, documents, and the TV

### Overview

The UI, README, PRD and roadmap stop saying "videos only"; the owner checks every link shape on
the Samsung.

### Changes Required:

#### 1. The link field

**File**: `castlib/ui/index.html`

**Intent**: The two link fields invite photos too.

**Contract**: The labels at the gate ("Or a video from a shared link, no sign-in needed:") and
under the grid ("A video from a shared link:") name a photo or a video. Nothing in `app.js`
changes: the album refusal arrives as `linkNote` like every other refused link.

#### 2. Documents

**Files**: `README.md`, `context/foundation/prd.md`, `context/foundation/roadmap.md` — README's
"Share links" paragraph (photos and a motion photo's clip from links in the tab; `cast-photos`
casts videos from links; albums refused); PRD FR-012's share-link clause; roadmap: S-09's `Open:`
line answered (albums refused, see the new slice), and a new `proposed` slice
(`phase:post-mvp`, prerequisite S-09, FR-012) "cast an album from a share link", with the album
page facts from `research.md` as its starting point.

**Intent**: The documents describe what the app does after this change.

**Contract**: Text only; the roadmap's At-a-glance table and its slice section stay in the existing
row and section format.

### Success Criteria:

#### Automated Verification:

- No document still says share links cast videos only: `! git grep -n -i "videos only" -- README.md context/foundation/prd.md castlib/ui` — at planning: exit 1 — expected until Phase 3 (README.md:203 still says it)
- The whole suite passes: `.venv/bin/python -m pytest -q -p no:cacheprovider` — at planning: exit 0

#### Manual Verification:

Run from a branch build: in a terminal on the Fedora PC, `cast-tv` from this branch's checkout;
the UI open on the phone; the Samsung on. Write each result in `research.md` (row, date, link,
what the TV showed) before ticking the row.

- In the Google Photos tab, paste `https://photos.app.goo.gl/QT9rQWxXYDDfSpKD8` (plain photo) into the link field and press Add link: one photo tile with a thumbnail appears; tap its play button: the photo shows on the TV, upright and in normal colours.
- Paste `https://photos.app.goo.gl/Nj2VHaD5bqKviYhq6` (motion photo): one photo tile; tap play: "Cast which variant?" offers Photo and Clip; Photo shows the still on the TV (not a green rectangle); Clip plays the 1.8 s clip on the TV.
- Paste `https://photos.app.goo.gl/PpeVYpY5J4QkpYm99` (album of several items): no tile appears; under the link field a line says album links are not cast yet.
- Paste `https://photos.app.goo.gl/KwhGzcxkNtQpudc46` (video): it still lists as a video tile and plays on the TV.
- Tick the plain-photo and motion-photo tiles, start the slideshow: both show as stills on the TV, one after the other.
- In the terminal, `cast-photos https://photos.app.goo.gl/QT9rQWxXYDDfSpKD8 --url-only`: it prints that cast-photos casts videos from links and to paste the link into the Google Photos tab — surface: castlib/sources/sharelink.py

**Implementation Note**: Manual checks are acceptance. `/rune-implement` commits the phase once
its automated verification passes, then asks the owner about these.

---

## Testing Strategy

### Unit Tests:

- Page classification on scripted pages: plain photo, motion photo, video, album (several items)
  with a photo cover, album with a video cover, no tags (probed as video); nothing probed for an album or for `resolve()` on a
  photo page.
- The motion-photo clip probe: 206 video → clip; 404 → none; 403, 429, 503 and a 200 `text/html`
  → the paste fails naming what came back; network failure → the paste fails.
- Source: tile shapes, thumbnails behind the guard, `quality` mapping including `bad_quality`, the
  show default, and the photo/clip `version` split.

### Integration Tests:

- `POST /api/sources/gphotos/link` then `POST /api/show` over the test app with a scripted share
  page (as `test_pick_and_link_over_api` does for video).

### Manual Testing Steps:

1. Plain photo link → tile → TV.
2. Motion photo link → chooser → Photo and Clip on the TV.
3. Album link → refusal under the field.
4. Video link → unchanged.
5. Slideshow of the two photo tiles.

## Performance Considerations

A photo paste costs the page fetch plus two one-byte probes (`=d`, `=m37`), against up to
four for a video today. The photo itself is fetched whole by `photos.py`, as for a picked photo.

## References

- Research (measurements): `context/changes/s09-share-link-photos/research.md`
- Source idea: `context/archive/2026-09-07-cloud-source-ui/follow-ups/review-fixes.md`
- Green-frame fix: `context/archive/2026-09-07-cloud-source-ui/research.md:842-857`
- Picked-video variants to mirror: `castlib/sources/gphotos.py:175-194`, `:814-851`

## Progress

> Convention: `- [ ]` pending, `- [x]` done, `- [-]` not applicable (` — n/a: <reason>` required). Append ` — <commit sha>` when a step lands. A Manual row takes ` — accepted at <full sha>` when a human confirms it. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Read a share page as video, photo, motion photo or album

#### Automated

- [x] 1.1 The new classification tests pass — aed13dc
- [x] 1.2 The whole suite passes — aed13dc
- [x] 1.3 Pyflakes is clean — aed13dc

### Phase 2: List and cast photo links in the Google Photos tab

#### Automated

- [x] 2.1 The new source tests pass — 9111645
- [x] 2.2 The whole suite passes — 9111645
- [x] 2.3 Pyflakes is clean — 9111645

### Phase 3: Wording, documents, and the TV

#### Automated

- [x] 3.1 No document still says share links cast videos only — 2c1c9f5
- [x] 3.2 The whole suite passes — 2c1c9f5

#### Manual

- [ ] 3.3 Plain photo link casts the photo
- [ ] 3.4 Motion photo link offers Photo and Clip, both play
- [ ] 3.5 Album link (several items) is refused under the field
- [ ] 3.6 Video link still plays
- [ ] 3.7 Slideshow of two link photos shows both stills
- [ ] 3.8 cast-photos points a photo link to the tab
