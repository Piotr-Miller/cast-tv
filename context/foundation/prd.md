---
project: "cast-tv"
version: 1
status: active
created: 2026-09-19
context_type: brownfield
product_type: desktop-cli-with-local-web-ui
target_scale:
  users: small
  qps: low
  data_volume: small
timeline_budget:
  mvp_weeks: null
  hard_deadline: null
  after_hours_only: true
---

# cast-tv — Product Requirements Document

> Written 2026-09-19 from the shipped product and its change folders; the requirements below
> are the ones the work was actually held to, with their sources.

## Vision & Problem Statement

The media worth watching on the living-room TV lives in three clouds and on a laptop: GoPro
clips in GoPro's cloud library, photos and videos in Google Photos, files in OneDrive, films on
a local disk. Getting any of it onto the TV meant typing a path or a link into a command line,
one item per process, and photos did not work at all (`cloud-source-ui/plan-brief.md`).

The TV does expose a UPnP/DLNA renderer: tell it a URL and it plays it. cast-tv is the missing
half - it finds the TV, serves or relays the material with `Range` support, and tells the TV to
play. Video is not transcoded: the TV pulls the original bytes. A local web UI on the same
process browses the three clouds, so the phone on the couch can choose what plays.

Originally stated (2026-09-07, `cloud-source-ui/change.md`): "UI do tej apki, ładowane pliki z
GoPro, Google Photos i OneDrive (mogą być osobne taby) i później ich castowanie na TV Samsunga."
(A UI for this app, files loaded from GoPro, Google Photos and OneDrive, separate tabs are fine,
and then casting them to the Samsung TV.)

## User & Persona

**Primary - the owner.** Piotr: a Samsung QE83S85F, a Fedora machine and a Windows 11 laptop,
a GoPro cloud library, a personal OneDrive and a Google Photos library. Picks
from the phone while the laptop streams.

**Secondary - anyone with a DLNA TV** who downloads the release (2026-09-19: "It should be plan
for any of your PCs and any user."). Not technical: must not install Python, copy config files
or create cloud projects.

## Success Criteria

### Primary

- **Pick on the phone, watch on the TV.** From any of the three clouds or a local file, a photo
  or a video chosen in the UI plays on the Samsung; several run as a slideshow that mixes sources.

### Secondary

- **A new PC works after one download** (Windows `.exe`, Linux binary), nothing else installed
  or copied (`standalone-install`).
- **The command line still works**: `cast-tv film.mkv` finds the TV and plays, as it did before
  the UI.

### Guardrails

- **The LAN cannot drive the TV through a web page**: `/api` and `/ui` answer only requests whose
  `Host` is this machine and whose `Origin` matches; media URLs carry a per-process token.
- **No secret in the public repository**: tokens live in the per-user config dir (0600 on
  Linux); the Google client secret enters only release builds.
- **Nothing stays on screen or on disk by accident**: Ctrl+C or closing the window stops the TV;
  converted photos and downloaded videos are per-process and removed at exit.
- **Linux and Windows both**: nothing that works on Fedora may break for Windows, and back.

## User Stories

### US-01: Cast a video from a cloud

- **Given** a connected source (GoPro, OneDrive or Google Photos) and the TV on the LAN
- **When** the user ticks a video in the UI and casts it
- **Then** the TV plays the original, and seeking with the TV remote works

#### Acceptance Criteria

- A source the TV cannot decode (e.g. DTS audio) is flagged with the reason and the fix
- A heavy original offers the lighter variant the source has (GoPro proxy, Google's 1080p)
- A new cast replaces the running one without a confirmation

### US-02: A slideshow of photos and videos

- **Given** a selection ticked across tabs
- **When** the user presses Start show
- **Then** items play in the order ticked: photos hold for the interval (default 8 s), videos
  play to their end

#### Acceptance Criteria

- HEIC, WebP and rotated photos are converted to an upright JPEG on the fly
- Pause, next, previous and stop work from the slideshow bar
- The laptop does not sleep during a show

### US-03: Choose from the phone

- **Given** cast-tv running on a laptop
- **When** the user opens the printed LAN address on a phone on the same network
- **Then** the same UI works there, including sign-ins that finish on the phone (OneDrive's
  device code) and Google's picker

### US-04: Run on a new PC

- **Given** a Windows or Linux PC that never had cast-tv or Python
- **When** the user downloads the release file and runs it
- **Then** the UI opens and every tab can connect with no file to copy (Google Photos for the
  owner's test users while the Google app is in testing)

### US-05: Cast from the command line

- **Given** a file, several files (a slideshow) or an http(s) address
- **When** the user runs `cast-tv <it>` (or `cast-gopro`, `cast-photos` from the pipx install)
- **Then** it plays on the TV, and the running UI shows it for that session

## Functional Requirements

### Discovery & the TV
- FR-001: Discover renderers over SSDP on every network interface; choose the first, the
  remembered one, or `-t`/`$CAST_TV`; offer a dropdown for several and a manual address for none.
- FR-002: Show the TV's state and a clear banner when it is unreachable.

### Sources
- FR-010: GoPro lists the cloud library after a session handed over from a browser window on the
  host, or after a token pasted in the UI when no such window can be opened; a refused token
  keeps the list with a banner.
- FR-011: OneDrive browses the whole drive by folder after a device-code sign-in (refresh ~90 days).
- FR-012: Google Photos lists what the user picked in Google's picker after a one-time consent on
  the host; share links from other people's libraries cast videos with no sign-in.
- FR-013: Local files are cast from the command line only (no folder browsing from the LAN).

### Casting
- FR-020: Video is served or relayed untouched with `Range`; expiring cloud URLs are re-resolved
  on demand, never cached.
- FR-021: Photos are fetched whole, made upright, converted when the TV cannot show them, and
  cached per process (bounded).
- FR-022: A slideshow mixes sources in selection order; the interval is adjustable and remembered.
- FR-023: Every failure appears on the item or source it belongs to and in a diagnostics panel
  (last 50).

### Install
- FR-030: A tagged release carries a Windows `.exe` and a Linux binary with the Google client
  built in; pipx from source remains for development.

## Non-Functional Requirements

- **Platforms:** Fedora (current) and Windows 11; the Linux binary targets glibc 2.35+.
- **No transcoding, no TV app**; the process stays in the foreground while it streams.
- **Dependencies:** standard library plus pillow, pillow-heif, ifaddr, platformdirs; no web
  framework, no frontend build step.
- **Latency:** a 20-megapixel HEIC reaches the TV in about 6 s from the click (README).
- **Language:** repository, code, docs and UI in English.

## Access Control

- The UI has no accounts: whoever reaches this machine's own address (localhost, or its LAN
  address from a phone) can use it; cross-origin pages cannot.
- Cloud credentials belong to the person running cast-tv and never leave their config dir.

## Non-Goals

- No transcoding; audio codecs the TV cannot decode are reported, not converted.
- No audio casting from the UI; no GIF or raw stills.
- No browsing local folders from the UI.
- No Google OAuth verification for now (no domain; decision 2026-09-19).
- No GoPro-sanctioned client: no publicly documented, self-serve sign-in for third-party
  applications was found (checked 2026-09-20); the connection is the person's own browser session.
- No code signing, installers, auto-update or macOS for now.
- No background service; no persistence of Google picks across restarts.

## Open Questions

- Google verification: when a domain exists, verification lifts the test-user limit and the
  weekly re-consent (`standalone-install/change.md`).
- Photos through share links (a follow-up of `cloud-source-ui`): scope, and whether albums count.
