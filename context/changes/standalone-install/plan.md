# Standalone Install Implementation Plan

## Overview

A new Windows PC or Linux machine downloads one file from the GitHub Release, runs it, and
every tab works with nothing installed or copied first. Google Photos connects with a client
built into the release; OneDrive already has one; GoPro stays a token paste; share links need
no sign-in (PR #16). Google Photos is limited to the owner's test users until the Google app is
verified, which this change does not do (`change.md`, decision 1).

## Current State Analysis

- `castlib/auth/loopback.py:58-59` - `client_path()` is `GOOGLE_CLIENT_JSON` or
  `config_dir()/google-client.json`; `load_client()` (`:62`) raises `ConfigError("no_google_client")`
  with `HOW_TO_GET_A_CLIENT` (`:42-46`), which tells the user to create a Cloud project.
- `castlib/sources/onedrive.py:39` - `DEFAULT_CLIENT_ID`, overridden by `ONEDRIVE_CLIENT_ID`:
  the model for Google.
- `pyproject.toml` - three console scripts (`cast-tv`, `cast-gopro`, `cast-photos`); the UI is
  package data (`castlib/ui/*`), found through `castlib/server.py:33` `UI_DIR` next to the module.
- `.github/workflows/` - one `test` workflow (pip install, pyflakes, pytest) on ubuntu-latest and
  windows-latest. No release workflow; no tags; version `0.2.0`.
- README install section: `pipx install` from `main.zip`; Google section: the Cloud-project steps.
- The spike (`research.md`) built a working onefile `cast-tv.exe` with PyInstaller.

## Definitions

| Term | Decided meaning | Origin | On degenerate data | Verified by |
| ---- | --------------- | ------ | ------------------ | ----------- |
| built-in Google client | `{client_id, client_secret}` written into `castlib/auth/_builtin_client.py` by the release workflow from the repository secrets `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`; the source tree carries a stub with `None` | research (push protection) | Stub (a source or pipx install): no built-in client; a half-filled module (one secret empty) counts as none | `test_gphotos.py::test_client_order`, the release smoke step |
| client order | `GOOGLE_CLIENT_JSON`, then `config_dir()/google-client.json`, then the built-in client | plan (OneDrive's model) | An override file that is present but unreadable is an error, never a silent fallback to the built-in one | `test_gphotos.py::test_client_order`, `::test_bad_override_is_an_error` |
| release | A GitHub Release for a tag `v*`, carrying `cast-tv-windows-x64.exe` and `cast-tv-linux-x64` built by CI | user (decision 3) | A build or smoke failure on either OS publishes nothing | the release workflow; Phase 3 manual |
| test user | A Google account the owner listed under Google Auth Platform → Audience → Test users | Google (Testing mode) | Anyone else: Google shows "Access blocked" and never calls back; the gate says why while it waits | Phase 3 manual, a second account |

## Desired End State

- A tagged release on GitHub with a Windows `.exe` and a Linux binary.
- On a PC that never had cast-tv or Python: download, run, the UI opens; Google Photos Connect
  opens Google's consent page (for a test user) and picks cast; OneDrive and GoPro connect as
  today; nothing asks for a file.
- `cast-tv --version` says the version and whether a Google client is built in.
- A pipx or source install behaves as today, with a message that no longer tells users to build
  a Cloud project but says which build has the client.

## What We're NOT Doing

- Google OAuth verification, a domain, a privacy policy page (decision 1, "for now").
- Code signing: an unsigned `.exe` gets SmartScreen's "Windows protected your PC" once; the README
  says "More info → Run anyway".
- Installers (MSI, rpm, AppImage), desktop shortcuts, auto-update, macOS.
- `cast-gopro` and `cast-photos` as standalone binaries: the UI covers both sources; they stay in
  the pipx install.
- Bundling `ffprobe`: diagnostics are optional and already skip it when missing.
- Changing the pipx channel.

## Implementation Approach

Two independent pieces - the client and the build - then a manual run on clean machines.
The secret never enters the repo; the build is the only place it meets the code.

## Phase 1: A Google client that ships with the build

### Changes Required:

#### 1. The built-in client
**File**: `castlib/auth/_builtin_client.py` (new, committed as a stub)
```python
CLIENT_ID = None      # the release workflow writes the owner's Desktop client here
CLIENT_SECRET = None
```
**File**: `castlib/auth/loopback.py`
- `load_client()` follows the client order: the env path or the config file if it exists (read
  errors stay errors), else the built-in module when both values are non-empty strings, else
  `ConfigError("no_google_client")`.
- `client_source()` → `"file"`, `"built-in"` or `None`, for `--version` and the status detail.
- `HOW_TO_GET_A_CLIENT` becomes the no-client message for source installs: "This copy of cast-tv
  has no Google client built in. The release downloads from GitHub have one; a source install
  can point GOOGLE_CLIENT_JSON at a Desktop-app client's JSON."

#### 2. Test users, said where they wait
**File**: `castlib/ui/index.html` (the consent block of the gate)
- One more line while waiting: "Google Photos is in testing: if Google says 'Access blocked',
  the owner of this cast-tv has to add your Google account as a tester."
**File**: `castlib/ui/app.js` - `GATES.gphotos.body` drops "Consent once" wording that implies
  forever: consent is asked again about weekly while the app is in testing.

#### 3. `--version`
**File**: `castlib/cli.py` - `cast-tv --version` prints `cast-tv 0.3.0` and
`Google Photos client: built in | from <path> | none`.
**File**: `pyproject.toml` - version `0.3.0`.

#### 4. Tests
- `test_gphotos.py::test_client_order` - env file beats config file beats built-in; built-in used
  when neither file exists; half-filled built-in counts as none.
- `::test_bad_override_is_an_error` - an unreadable override file raises, even with a built-in.
- `test_cli.py::test_version_names_the_client`.

### Success Criteria:

#### Automated Verification:
- [x] `python -m pyflakes castlib tests` and `python -m pytest` pass on ubuntu and windows CI.
      **Done 2026-09-19, `a16f542`** (PR #20; main run 35447819565; 267 passed locally).
- [x] `git grep GOCSPX` finds nothing but this line. **Done 2026-09-19, `a16f542`.**

#### Manual Verification:
- [ ] None in this phase; the client is exercised from the release in Phase 3.

## Phase 2: The release build

### Changes Required:

#### 1. Build definition
**File**: `packaging/cast-tv.spec` (PyInstaller) and `packaging/entry.py`
- Onefile, console (Ctrl+C and closing the window must still stop the TV, PR #11), name
  `cast-tv`, data `castlib/ui`, `collect_all("pillow_heif")`; the spike's flags as a spec.
**File**: `packaging/write_client.py` - writes `_builtin_client.py` from the two env vars; fails
the build if either is empty.

#### 2. Release workflow
**File**: `.github/workflows/release.yml`
- On `push` of a tag `v*`: a matrix of `windows-latest` and `ubuntu-22.04` (older glibc, so the
  binary runs on newer distributions such as Fedora).
- Steps: checkout, Python 3.12, `pip install . pyinstaller`, `write_client.py` with
  `secrets.GOOGLE_CLIENT_ID` / `secrets.GOOGLE_CLIENT_SECRET`, `pyinstaller packaging/cast-tv.spec`.
- Smoke test of the built file: `--version` says "built in"; start it with `--no-browser -p 8099`,
  `GET /ui/` 200 and `GET /api/status` 200, stop; `--self-check` (hidden, `cli.py`) encodes a
  16×16 image to HEIC in memory with the bundled `pillow_heif`, decodes it back through the photo
  pipeline's opener, and exits 0 - the native `libheif` is inside the bundle.
- A last job creates the Release with both files (`gh release create $TAG`), only if both
  builds passed.

#### 3. Docs
**File**: `README.md` - "Install" leads with the Release download (Windows: SmartScreen → More
info → Run anyway; Linux: `chmod +x`); pipx stays as "from source". The Google section says
the release has the client, Photos is in testing (ask the owner to be added), and how the owner
adds a tester. The Cloud-project steps move under "Your own Google client (optional)".

### Success Criteria:

#### Automated Verification:
- [ ] The release workflow passes on a test tag (e.g. `v0.3.0-rc1`, a pre-release) on both OSes,
      smoke steps included.

#### Manual Verification:
- [ ] The workflow logs never print the secret (GitHub masks it; checked by reading the log).

## Phase 3: Clean machines

### Manual Verification:
- [x] **3.1 Windows, clean**: a Windows user account that never ran cast-tv (no
      `%APPDATA%\cast-tv`), Python not on PATH. Download `cast-tv-windows-x64.exe` from the
      Release in Edge, run it (SmartScreen noted), allow the firewall if asked. Google Photos:
      Connect → consent (Piotr's account, a test user) → pick a photo and a video → both play on
      the Samsung. OneDrive: device-code sign-in, a video plays. Share link: the video link plays.
      Closing the window stops the TV. — 86abd21
- [ ] **3.2 Linux**: the same file on Fedora, `chmod +x`, run; Google Photos Connect and a pick
      cast; a HEIC photo from OneDrive or the picker converts and shows.
- [x] **3.3 Not a tester**: a second Google account that is not a test user: Google shows
      "Access blocked"; the gate's line explains it; Cancel returns to the gate. — 81a7733
- [ ] **3.4 Weekly consent**: about 7 days after 3.1, the tab shows "The Google Photos consent
      expired"; Connect again restores it (recorded when it happens, not waited for).

## Owner steps (Piotr, before the first release)

1. **Done 2026-09-19 14:07 (Piotr; names checked with `gh secret list`).** In the GitHub repo: Settings → Secrets and variables → Actions → New repository secret:
   `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, the two values from the `cast-tv` Desktop client
   JSON (`client_secret_26923464307-….json`). Claude never sees them.
2. Google Auth Platform → Audience → Test users: every Google account that should use Photos.
