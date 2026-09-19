# Research: standalone-install

2026-09-19. Claude on the Windows laptop (Windows 11 Pro 26200, Python 3.14.5 from python.org),
the Samsung on the LAN.

## Google: what "any user" costs

- **Google Photos needs verification for general use.** The Google Photos authorization page:
  "If your application accesses the Google Photos APIs, it must pass the OAuth verification
  review." (https://developers.google.com/photos/overview/authorization)
- **What verification asks** (https://support.google.com/cloud/answer/13464321): a home page on a
  domain the developer owns and verifies in Search Console, a privacy policy on the same
  domain, a demonstration video "of your app including the OAuth grant process", a justification
  for each scope, and limited data use. A `github.io` address is GitHub's domain, not ours; the
  page does not say it qualifies. Piotr declined to buy a domain for now (`change.md`).
- **Unverified in production:** "100 new users in total, after the app presents the unverified
  app screen" (https://support.google.com/cloud/answer/7454865). Given the Photos sentence
  above, this is not a route either.
- **Testing mode**, where the `cast-tv` project is today: only the test users listed on the
  consent screen can consent (up to 100), and "A Google Cloud Platform project with an OAuth
  consent screen configured for an external user type and a publishing status of "Testing" is
  issued a refresh token expiring in 7 days" (https://developers.google.com/identity/protocols/oauth2,
  "Refresh token expiration"). The UI already handles the expiry: state `expired`, banner "The
  Google Photos consent expired ... or the test-user token ran out", Connect again
  (`castlib/ui/app.js`, `GATES.gphotos`).
- **A Desktop client's secret is not a secret.** "Installed apps are distributed to individual
  devices, and it is assumed that these apps cannot keep secrets."
  (https://developers.google.com/identity/protocols/oauth2/native-app). Shipping it inside the
  program is the documented model (rclone ships its Google Drive client the same way).
- **But not in the public repo.** GitHub push protection blocks Google OAuth client secrets by
  default ("Secrets from Figma, Google, OpenVSX, and PostHog are now push-protected by default",
  https://github.blog/changelog/2025-04-14-secret-scanning-expands-default-pattern-and-push-protection-support/),
  and a secret found in a public repo is reported to the provider. A revoked secret would break
  every copy at once. So the secret is written into the build by the release workflow from a
  repository secret; the source tree carries none. Anyone can still pull it out of the `.exe` -
  that is what "cannot keep secrets" means - but it is not published as text.

## Microsoft and GoPro

- OneDrive already ships `DEFAULT_CLIENT_ID = "652b2cf9-..."` (the owner's Entra registration)
  against the `consumers` authority; `ONEDRIVE_CLIENT_ID` overrides it. Nothing to copy today.
- GoPro has no public sign-in for apps; the token is pasted in the UI. That is a step in the UI,
  not a file, and stays.

## Spike: PyInstaller on this laptop (2026-09-19, 15:41)

Scratch venv with `pip install -e ".[test]" pyinstaller`, entry `from castlib.cli import main_tv;
main_tv()`:

```
python -m PyInstaller --noconfirm --onefile --name cast-tv --paths C:/Source/cast-tv \
    --collect-data castlib --collect-all pillow_heif entry.py
```

- Built in about 17 s: **`cast-tv.exe`, 22,532,635 bytes**, one file.
- `cast-tv.exe --help` printed the usual usage.
- `cast-tv.exe --no-browser -p 8099`, started hidden: printed its addresses and the firewall
  line, **found `83" OLED (192.168.50.142)`**; `GET /ui/` answered 200 with 30,705 bytes and
  the PR #16 markup (`addLink`); `GET /api/status` gave `gphotos: disconnected`. Stopped.
- Not yet checked in the build: a HEIC converted by `pillow_heif` (native `libheif` inside the
  bundle), a real cast from the `.exe`, Windows' first-run prompts (SmartScreen for an unsigned
  download, the firewall), a Linux build.
- `ffprobe` is optional: `castlib/diagnostics.py` returns nothing when it is missing (every call
  is under `except Exception`), so the bundle does not need it.

## Phase 3.1: Windows, clean account (2026-09-19, about 17:50)

A fresh Windows user account, `casttest`, on this laptop. What follows is the user's report, not
something Claude observed; Claude was shown three screenshots from the run (not committed, they
hold private photos).

- The user's words: "wszystko na tak, wszystko zagrało na TV, około 17:50" ("yes to everything,
  everything played on the TV, around 17:50"), answering the row's checklist item by item:
  - the account had no `%APPDATA%\cast-tv` and Python was not on PATH;
  - `cast-tv-windows-x64.exe` was downloaded from the `v0.3.0-rc1` pre-release in Edge;
    SmartScreen and the firewall prompt were met and accepted;
  - Google Photos: Connect → Google's consent (Piotr's account, a test user) → a photo and a
    video picked, both played on the Samsung;
  - OneDrive: device-code sign-in, a video played;
  - a share link: the video played;
  - closing the console window stopped the TV.
- Screenshots: Google Photos with **4 picked** (3 photos, one 2160×3840 video) while GoPro and
  OneDrive still said "not connected" - so the Google client came from the build, the account
  had no `google-client.json`; later OneDrive signed in and browsing
  `Pictures / OM Workspace / 2026_08_16` (187 items), GoPro "token stored", Google Photos
  "5 picked". The GoPro grid shows "too heavy" (100-121 Mbit/s) on every clip; that is the
  existing bitrate check on these 4K/5.3K files, not a regression, and no GoPro cast was
  claimed.
- The user signed out of `casttest` afterwards.
