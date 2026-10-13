# Photos through share links — Plan Brief

> Full plan: `context/changes/s09-share-link-photos/plan.md`
> Research: `context/changes/s09-share-link-photos/research.md`

## What & Why

A Google Photos share link to a photo is refused today ("Share links cast videos only"), so a
photo someone shares cannot reach the TV without a sign-in and the picker. Roadmap S-09: a link to
a photo lists a photo tile, and a motion photo's clip plays as Google's H.264 stream (`=m37`),
since the Samsung refused the clip's HEVC 120 fps original.

## Starting Point

`sharelink.resolve()` scrapes a share page for a video stream and refuses a photo page before any
probe. `GPhotosSource.link()` lists every pasted link as a video tile without a thumbnail. The
photo pipeline (`photos.py`) already fetches through a guarded opener and strips a motion photo to
its still.

## Desired End State

In the Google Photos tab, a pasted photo link lists a photo tile with a thumbnail and casts the
photo. A motion photo's tile asks Photo or Clip, and both play. An album recognised by its several
items lists nothing and says album links are not cast yet; a one-item album is handled as its
single item. Video links and `cast-photos` behave as before, except that
`cast-photos` points a photo link to the tab.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Motion photo shape | One photo tile, variants Photo (default) and Clip | Reuses the existing variant chooser; a slideshow treats it as a photo | Plan (Piotr) |
| Albums | An album recognised by its several items is refused (`album_link`); a one-item album is handled as its single item; casting albums is a new proposed roadmap slice | An album page passes for its cover and would be listed as one motion photo | Plan (Piotr) + Research |
| Facts about Google | Measured before planning, not assumed | `=d` public, `=m37` H.264 and the album signals were all unproven | Plan (Piotr) |
| CLI | `cast-photos <link>` stays video-only | S-09 extends link handling in the tab; reworking the `cast-photos <link>` path is out of its scope | Plan (Piotr) |
| Photo address | `og:image` base + `=d` | Public, full size; every page has a second, unidentified base | Research |
| Motion vs plain | Probe base + `=m37`: video → clip, 404 → plain | The two pages are otherwise identical | Research |
| Album signal | More than one distinct `/share/<id>/photo/<item>` link - a heuristic confirmed on samples | Language-independent; 5 against 1 on five pages, one album of five items | Research |
| Clip probe statuses | Only 404 means a plain photo; any other non-video answer (403, 429, 5xx, or a 200/206 such as `text/html`) or a network failure fails the paste | `probe_media()` returns `None` on every HTTP error, so a refusal would hide the clip | Plan (Piotr, after review) |
| Page with no tags | Probed as video, as today; the risk is recorded (below) | Piotr's call after review, with the consequence written out | Plan (Piotr, after review) |

## Scope

**In scope:**
- Photo and motion-photo links as tiles, with thumbnails, cast and in slideshows
- Album recognition and refusal, in the UI and the CLI
- Wording in the UI, README, PRD FR-012 and the roadmap (plus a new album slice)

**Out of scope:**
- Casting albums; photos from `cast-photos <link>`; `=dv`/`=m22`/`=m18` as variants
- Telling a one-item album from a single photo; sizes or dates on link tiles

## Architecture / Approach

`sharelink.shared(link)` reads the page once and answers a small `Shared` record (kind, address,
clip, thumbnail) or refuses an album; `resolve()` stays the CLI's and the video refresh's entry.
`GPhotosSource` stores that record per link and maps it to a photo tile, variants, a photo
`MediaItem` (fetched by `photos.py` behind `sharelink.opener()`) or a relayed clip `MediaItem`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Read a share page | `shared()`, album refusal, CLI wording, tests | Album count regex drifts from the measured page form |
| 2. Photo links in the tab | Photo/motion tiles, variants, thumbs, show default, tests | Photo and clip of one link confused in caches (separate `version`) |
| 3. Wording, documents, TV | UI labels, README/PRD/roadmap, six manual rows on the Samsung | Google changes the page between planning and the TV check |

**Prerequisites:** branch `s09-share-link-photos` from `origin/main`; the four measured links stay
shared; the Samsung reachable for Phase 3.
**Estimated effort:** ~2 sessions across 3 phases.

## Open Risks & Assumptions

- Every Google fact is a measurement from 2026-10-13, not a contract; a changed page breaks it the
  way it would break the video path.
- A page without Open Graph tags is probed as a video: a motion photo without tags may be listed
  as a video with the `=dv` original, without the Photo/Clip choice, and its playback may fail. No
  particular error is promised, and no resilience to a change in Google's page format.
- The album signal is a heuristic confirmed on samples; an album with one item, or with a video
  cover, was not measured.
- The `og:description` "Shared album" text is English; the plan relies on the item-link count.

## Success Criteria (Summary)

- A plain photo link and a motion photo link (both variants) play on the Samsung from the tab.
- An album recognised by its several items is refused under the field; video links still play.
- No document still says share links cast videos only.
