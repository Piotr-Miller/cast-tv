# Cloud Source UI — Plan Brief

> Full plan: `context/changes/cloud-source-ui/plan.md`
> Research: `context/changes/cloud-source-ui/research.md`

## What & Why

A local web UI for `cast-tv`: browse GoPro, OneDrive and Google Photos in three tabs, tick
photos and videos from any of them, and cast one or run a slideshow on the Samsung. Today
the tool casts one video per process from a command line; choosing what to cast is typing a
path or a link, and photos do not work at all. The UI is served by the same process and port
the TV already talks to, so the phone on the couch gets it for free.

## Starting Point

Four standard-library scripts, about 1000 lines, built for exactly one item per process.
Research verified two live bugs in that model and seven latent ones, a LAN-exposure problem
that makes an Origin/Host check the first thing to build, and the reasons photos cannot be
served. The OAuth spike (2026-09-09) proved the Google flow end to end and settled the item
shape.

## Desired End State

`cast-tv` with no arguments opens the UI on the laptop and prints the address for the phone.
Each tab connects once (a token paste, a device code, a one-time consent) and then lists or
picks. Any item casts; several become a slideshow that mixes sources, holds photos for eight
seconds, plays videos to the end and converts HEIC on the fly. Failures show where they
happen, with the CLI's existing messages. `cast-tv film.mkv` is unchanged, and `pipx
install` works on Fedora and Windows.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Stack | http.server + Alpine, no build step, no FastAPI | One process, one port, phone access for free | Change |
| Google Photos | Picker API over desktop loopback OAuth | Device flow's scope list excludes the Picker scope; loopback proven by the spike | Change + Research |
| OneDrive | Graph over device code | Only flow that works from a phone with no redirect | Change |
| Photos vs video | Photos fetched whole and materialised; video relayed | HEIC cannot convert while streaming; HEAD/GET must agree | Research |
| Security first | Origin/Host check and media-URL token in Phase 1 | Retrofitting means auditing every route twice | Change |
| Slideshow | Selection order; videos play to the end | The queue is what the user built; mixed clips and stills is the use case | Plan |
| Listable media | Photo and video only, by source metadata; audio, raw, GIF hidden | Never offer what fails on the TV | Plan |
| GoPro "connected" | Verified on tab entry, token age shown, 401 reopens the gate | The token is an opaque JWE; the API's answer is the only signal | Plan |
| New cast while playing | Replace immediately; old item served until idle 60 s | One-remote mental model; fixes the mid-stream 404 | Plan |
| OneDrive browse | Whole drive, root, breadcrumbs, paging | Nothing to configure; Camera Roll is two taps away | Plan |
| The TV | First found by default; picker when several; retry banner when none | Keeps the CLI's rule for the one-TV case | Plan |
| Errors | Structured on item or gate, plus a diagnostics ring buffer | Reuses the messages `castcloud` already wrote | Plan |
| Tests | Pure parts plus an in-process HTTP server; no fake renderer | The verified framing and range bugs become regression tests | Plan |
| Google pick lifetime | Per process; connection persists via refresh token | Matches Picker sessions and 60-minute URLs | Plan |
| Interval | 8 s default, adjustable in the bar, remembered | One control where it is needed | Plan |
| Priority | Security → registry → photos → three tabs → Windows last | Every earlier phase is usable on Fedora alone | Plan |

## Scope

**In scope:** `castlib` package with the CLI on top; item registry; Origin/Host check and
media token; photo pipeline with HEIC and EXIF orientation; cast supervisor and slideshow;
`/api` and the Alpine UI; GoPro, OneDrive, Google Photos sources with their gates; share-link
fallback; pipx packaging, platformdirs paths, multi-interface SSDP, firewall hints,
stay-awake shims, CI on Linux and Windows.

**Out of scope:** desktop app or webview; audio from the UI; raw/GIF stills; browsing local
folders from the UI; persisting Google picks; a play queue separate from the slideshow;
capture-time ordering; background service; PyInstaller; OAuth app verification.

## Architecture / Approach

One `MediaItem` with a kind, registered under an opaque id on one shared map; two pipelines
behind it (materialised photos, relayed video) fed by resolver callables that fetch fresh
upstream URLs on open. A `Source` contract (`status`, `connect`, `list`, `resolve`, `thumb`)
implemented three times; auth helpers for device code and loopback with 0600 token stores. A
supervisor object per cast and a show loop over casts, polled by the UI through `/api/status`.
The server dispatches before lookup: `/m/<token>/<id>` media, `/api`, `/ui`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Foundations | `castlib`, registry, Origin/Host + token, framing fixes, exceptions, pytest with in-process server; CLI unchanged | Regressing a history-hardened behaviour during the move |
| 2. Photos | Image MIME, per-kind DIDL/DLNA, HEIC → JPEG, bounded cache; `cast-tv photo.heic` | The Samsung's image profile is unverified; one evening with `--debug` |
| 3. Server + UI shell | Long-lived process, supervisor, slideshow, `/api`, TV picker, errors, Alpine UI; CLI slideshow | The supervisor's state machine on a real TV |
| 4. GoPro | Gate, listing with kinds, variants, thumbnails if the API has them | Thumbnail shape unknown until probed |
| 5. OneDrive | Device code, refresh, folder browsing with paging, on-demand download URL | Entra registration prerequisite |
| 6. Google Photos | Loopback OAuth, Picker sessions, Bearer fetch/relay, share-link fallback | Consent must happen on the host; session expiry paths |
| 7. Packaging | pyproject + pipx, platformdirs, ifaddr SSDP, firewall, stay-awake, CI, README | Windows only testable on a Windows box |

**Prerequisites:** the Google Cloud client JSON (done); an Entra app registration with public
client flows enabled (before Phase 5); a Windows machine for Phase 7's manual checks.
**Estimated effort:** about 8–10 sessions across 7 phases; Phase 1 and Phase 3 are the big ones.

## Open Risks & Assumptions

- The photo DLNA constants (`JPEG_LRG`, `OP=00`, `Interactive`) are guideline defaults, never
  tried on this TV; Phase 2 keeps them in one place and records what worked.
- GoPro `type` values and thumbnail fields are unverified; Phase 4 probes with a live token.
- The 60 Mbit/s "too heavy" threshold is a heuristic from one file, kept as such.
- Google's Picker sessions and `baseUrl`s expire on Google's schedule; the plan re-lists and
  marks items, but the exact session lifetime is not documented as a number.
- Windows behaviour (firewall prompt, multicast per adapter, sleep inhibition) is planned
  from documentation and can only be verified on a Windows machine.

## Success Criteria (Summary)

- From the phone, connect a tab, tick a photo from OneDrive and a clip from GoPro, press
  "Start show": both play in order on the TV, HEIC included, and the laptop does not sleep.
- Every failure the CLI used to print appears on the item or gate it belongs to.
- `cast-tv film.mkv` works exactly as before, and the test suite passes on both CI runners.
