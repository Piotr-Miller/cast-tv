---
project: cast-tv
version: 1
status: active
created: 2026-09-19
updated: 2026-09-20
prd_version: 1
main_goal: personal-use-then-share
top_blocker: time
---

# Roadmap: cast-tv

> Derived from `context/foundation/prd.md` (v1) and the change folders, 2026-09-19.
> Edit-in-place; archive when superseded. The "At a glance" table is the index.
> **Phase tag:** every slice carries `phase:mvp` (the UI change, `cloud-source-ui`) or
> `phase:post-mvp` (what came after it). New slices must set it.

## Vision recap

Put anything from GoPro's cloud, OneDrive, Google Photos or a local disk on the Samsung TV,
chosen from a phone, with no app on the TV and no transcoding. See `prd.md`.

## North star

**S-02: from the phone, a selection ticked across tabs plays on the TV as one slideshow.** It is
the smallest flow that needs every part at once - the long-lived server, the sources, photo
conversion and the cast supervisor. Delivered with `cloud-source-ui` (PR #1, 2026-09-18).

## At a glance

| ID | Change ID | Outcome (user can …) | Prerequisites | PRD refs | Status |
| --- | --- | --- | --- | --- | --- |
| B-00 | (baseline) | cast a local file, a stream, a GoPro item or a Google Photos share link from the command line | — | US-05 | done (2026-09-07) |
| F-01 | cloud-source-ui, phase 1 | (foundation) castlib package, item registry, Host/Origin check, media-URL token | B-00 | Guardrails | done |
| S-01 | cloud-source-ui, phase 2 | cast a photo; HEIC and rotated photos converted | F-01 | FR-021; US-02 | done |
| S-02 | cloud-source-ui, phase 3 | open the UI on the phone, cast, run a slideshow (NORTH STAR) | F-01, S-01 | US-02, US-03; FR-022, FR-023 | done |
| S-03 | cloud-source-ui, phase 4 | browse GoPro after a token paste | S-02 | FR-010 | done |
| S-04 | cloud-source-ui, phase 5 | browse OneDrive by folder after a device-code sign-in | S-02 | FR-011 | done |
| S-05 | cloud-source-ui, phase 6 | pick in Google Photos and cast the pick; share links | S-02 | FR-012 | done |
| S-06 | cloud-source-ui, phase 7 | install with pipx on Fedora and Windows 11 | S-02 | NFR platforms | done |
| S-07 | (follow-ups, PRs #10-#17) | close the window to stop the TV; see why a managed laptop cannot cast; paste a share link before any sign-in | S-06 | Guardrails; FR-012 | done |
| S-08 | standalone-install | download one file on a new PC and use every tab | S-06 | US-04; FR-030 | in progress (only row 3.4, from 2026-09-26) |
| S-09 | (not opened) | cast a photo or a motion photo's clip from a share link | S-05 | FR-012 | backlog |
| S-10 | (not opened) | connect Google Photos with any Google account, without weekly re-consent | S-08 | US-04 | parked |
| S-11 | s11-screensaver | watch a slideshow or a long film without the TV's screen saver cutting in | S-02 | US-03 | closed 2026-09-20: documented, not built |
| S-12 | (proposed) | run cast-tv as a desktop window on Windows and Linux, not only a browser tab | S-08 | — | proposed |
| S-13 | (proposed) | connect GoPro without copying a token by hand | S-03 | FR-010 | proposed |
| S-14 | (proposed) | cast to Google TV and Chromecast devices, not only DLNA TVs | S-02 | — | proposed |

## Streams

- **Casting core** (B-00, F-01, S-01, S-02, S-11, S-14): discovery, the server, the relay, photos, the supervisor.
- **Sources** (S-03, S-04, S-05, S-09, S-10, S-13): one tab each, each behind its own connection.
- **Platforms & install** (S-06, S-07, S-08, S-12): Fedora, Windows 11, the standalone release.

## Baseline

Before the UI (commits `cf2a839`..`36cf4c8`, 2026-09-07): four standard-library scripts, about
1000 lines - `cast-tv` (local files and streams), `cast-gopro`, `cast-photos` (share links) and a
shared `castcloud` - built for one item per process. Research found two live bugs in that model
and a LAN-exposure problem (`cloud-source-ui/research.md`).

## Slices

### S-08: A new PC works after one download

- **Phase:** phase:post-mvp
- **Change:** `context/changes/standalone-install/`
- **Outcome:** a Windows or Linux PC with no Python downloads one file from GitHub Releases and
  every tab connects; Google Photos through a client built into the release.
- **Status:** Phase 1 (built-in client, `--version`) merged as #20; Phase 2 (PyInstaller spec,
  release workflow, smoke test) merged as #22; repository secrets set 2026-09-19. Both
  pre-releases are out: `v0.3.0-rc1` (2026-09-19) and `v0.3.0-rc2` (the same evening, after
  #27). Phase 2's rows are ticked from the rc2 run - three green jobs, both smoke tests, and a
  log where the secret appears only masked. Phase 3: **3.1 (clean Windows account), 3.2 (Fedora)
  and 3.3 (a non-tester Google account) passed**; only **3.4, the weekly re-consent, is open,
  and not before 2026-09-26 21:46** - seven days after the consent given on Windows, and any
  earlier Connect restarts the week. After it: whether to cut `v0.3.0` without the `-rc`.
- **What row 3.2 caught:** the Linux binary could verify no certificate at all. Built on
  `ubuntu-latest`, it carries that runner's OpenSSL, which looks for CAs under `/usr/lib/ssl`;
  Fedora has no such directory, so Google, OneDrive and GoPro were all unreachable from the
  release on any Fedora machine. Fixed in #27 (`platform.use_system_ca_bundle`) and shipped in
  rc2, where the same laptop signed in, picked and cast. A row done on the real artefact, not
  from source, is what found it.

### S-09: Photos through share links

- **Phase:** phase:post-mvp
- **Change:** not opened; recorded in `cloud-source-ui/follow-ups/review-fixes.md`.
- **Outcome:** a share link to a photo lists a photo tile; a motion photo's clip offers `=m37`
  (H.264 1080p), since the Samsung refused its `=dv` HEVC 120 fps original.
- **Open:** albums are untested; plan first.

### S-10: Google Photos for any account

- **Phase:** phase:post-mvp
- **Outcome:** Google verification of the `cast-tv` app lifts the test-user list and the 7-day
  refresh-token expiry.
- **Parked because:** verification needs an owned domain with a home page and privacy policy, a
  demo video and Google's review; the owner declined to buy a domain for now (2026-09-19).

## Proposed

Raised by the owner on 2026-09-19 (in Polish, quoted with an English gloss). Nothing here is
planned or researched yet; each needs a `research.md` before a plan. The ideas under each are
starting points, not findings.

### S-11: No screen saver during a slideshow or a long film

- **Phase:** phase:post-mvp
- **Owner's words:** "Na TV pokazuje się wygaszacz w trakcie trwania slideshow, czy długiego
  filmu - jak to obejść?" ("The TV shows its screen saver during a slideshow or a long film -
  how do we get around it?")
- **Seen live, 2026-09-19 23:0x** (`standalone-install/research.md`, the rc1 run): a still HEIC
  photo was on screen, the TV's screen saver came on and did not go away, while AVTransport
  still answered PLAYING and cast-tv showed no error. So from our side a covered screen and a
  playing one look identical - the gap is not only cosmetic.
- **To find out:** when exactly the Samsung starts it (idle time, photos only or video too,
  paused vs playing) and whether a TV setting alone avoids it.
- **Ideas:** a periodic harmless key over Samsung's remote-control WebSocket API (ports
  8001/8002, needs a one-time pairing on the TV); a slideshow sent as one video stream instead of
  single photos, so the TV sees playback.
- **Closed 2026-09-20, documented rather than built** (`context/changes/s11-screensaver/`). Measured
  on the TV: a still photo goes dark 124 s after a remote key press, a slideshow at 8 s goes dark
  inside the same window, a moving film survives six minutes - so the trigger is a motionless
  picture, counted from the last remote key. No TV setting is left to change, and no DLNA call
  suppresses it: on this set a fresh `SetAVTransportURI` + `Play` every 8 s did not. The owner
  declined the remote-key workaround (a visible key press every ~100 s) and the encode-as-video one
  (it breaks the no-transcoding boundary, and the evidence that had ruled it out is gone). The
  behaviour is now a paragraph in README's Limitations.

### S-12: A desktop UI on Windows and Linux

- **Phase:** phase:post-mvp
- **Owner's words:** "Desktop UI (Win/Linux) zamiast WebUI" ("a desktop UI (Win/Linux) instead
  of the web UI")
- **To decide:** replace the web UI or wrap it. The phone flow (S-02, the north star) needs the
  web UI, so a wrapper keeps one UI for both.
- **Ideas:** the existing UI in a native window (e.g. pywebview) with the server inside the same
  process; closing the window stops the TV, as the console window does now (#11); a tray icon.

### S-13: GoPro without a hand-pasted token

- **Phase:** phase:post-mvp
- **Owner's words:** "Rozkminka jak uprościć dodawanie tokenu dla GoPro - ręczne wklejanie jest
  jakieś nieprofesjonalne" ("figure out how to simplify adding the GoPro token - pasting it by
  hand looks unprofessional")
- **To find out:** whether GoPro offers any sign-in a third-party app may use; the cloud API
  cast-tv calls is not public.
- **Ideas:** a GoPro sign-in inside an app-owned browser window (pairs with S-12) that keeps the
  resulting cookie; a browser extension or bookmarklet that hands the token to the local server.
  Either way the token stays inside cast-tv and is never shown or logged.

### S-14: Google TV and Chromecast as targets

- **Phase:** phase:post-mvp
- **Owner's words:** "Wyszukiwanie oprócz telewizorów, też Google TV, Chromecast, itd."
  ("discovery of Google TV, Chromecast etc. as well as TVs")
- **To find out:** which formats a Chromecast / Google TV plays straight from a URL (no
  transcoding stays a rule) and how photos show there.
- **Ideas:** mDNS discovery (`_googlecast._tcp`) next to SSDP; the Cast protocol with the
  Default Media Receiver (e.g. `pychromecast`); a target list in the UI that mixes both kinds.

## Open Roadmap Questions

- Archive `cloud-source-ui` to `context/archive/` now that every row and follow-up but S-09 is done?

## Parked

- Google verification (S-10), code signing for the `.exe`, installers (MSI, rpm, AppImage),
  auto-update, macOS.
- Audio casting from the UI; browsing local folders from the UI (exposure); a background service.

## Done

- **cloud-source-ui** (F-01, S-01..S-06): merged as PR #1 on 2026-09-18, every plan row ticked,
  row 7.3 (Windows) last. PRs #2-#8 were a second implementation of the same UI built on `main`
  in another session; PR #9 reverted it in favour of PR #1. Archived 2026-09-20 (#32) →
  `context/archive/2026-09-07-cloud-source-ui/`, where its plan, research and reviews stay
  readable.
- **Follow-ups** (S-07): #10 sleep control recorded, #11 console close stops the TV, #13 managed
  firewall policy detected, #14 photo share links say so, #16 share link before sign-in.
