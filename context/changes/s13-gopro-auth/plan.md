# GoPro without a hand-pasted token (S-13) Implementation Plan

## Overview

The GoPro tab stops sending its user to the browser's devtools. Pressing **Open gopro.com** makes
cast-tv launch a Chromium-family browser that is already on the host (Chrome, Chromium, Edge,
Brave) in a window the app owns - its own profile, a random local DevTools port - wait for the
person to sign in there as they normally do, read the `gp_access_token` cookie over the Chrome
DevTools Protocol (CDP), prove the value against `api.gopro.com`, store it exactly as a paste is
stored today, and close the window. Nothing about cast-tv's standing with GoPro changes: the
session is still the person's own browser session, and the README says so in a dated paragraph.
The paste survives only as a fallback for the cases where the hand-off is unavailable or failed.

Decided 2026-09-21 (frame addendum, `frame.md:142-173`): plan the hand-off only; the standing
problem is a stated limitation. The bookmarklet is out (`frame.md:62-65`); the extension and an
embedded webview were weighed and declined in this planning session (Definitions and "What We're
NOT Doing").

## Current State Analysis

- **The gate is a paste with three steps** (`castlib/ui/app.js:14-27`, `castlib/ui/index.html:204-215`),
  and the 401 banner is a second copy of the same field (`index.html:269-281`). The steps' text
  lives twice: `GATES.gopro.steps` in `app.js:23-26` and `HOW_TO_GET_A_TOKEN` in
  `castlib/sources/gopro.py:37-46` (which the CLI prints). Both say "lasts a few hours"; so do
  `README.md:128` and `README.md:280`. The frame forbids assuming that (`frame.md:122`).
- **The source verifies before it saves** (`gopro.py:482-496`: `search(tok, 1)`, then
  `save_token`, then `_adopt`), keeps one credential with a generation counter (`gopro.py:366-433`),
  and knows the states `disconnected` / `connected` / `expired` (`gopro.py:459-480`). It has no
  `connecting` state and no thread. The token file is `config_dir()/gopro-token`, mode 0600
  (`gopro.py:50-84`, `config.py:107-128`). Origin: `code`, kept.
- **The multi-step pattern already exists**: Google Photos runs its consent in a daemon thread
  under `_flow_lock`, reports `{"state": "connecting", "detail": {"step": "consent", "expires_in",
  "note": ON_HOST_NOTE}}`, answers a second `connect({})` with the same round, ends it with
  `{"cancel": true}`, and drops a late result whose generation moved on
  (`castlib/sources/gphotos.py:291-363,366-435`). The UI renders that step with a waiting line,
  a phone note and Cancel (`index.html:219-231`, `app.js:218-236`). `App.close()` calls `close()`
  on every source that has one (`castlib/app.py:302-308`), which is how a window opened by a
  source is shut on Ctrl+C. Origin: `code` (a precedent the owner accepted on 2026-09-21).
- **Google's consent is already a host-only step** (`castlib/auth/loopback.py:10-12`,
  `README.md:157-158`); the phone sees a note. The hand-off inherits that exception, not a new
  one (`frame.md:158-168`). Origin: `product`.
- **The route surface needs nothing new**: `POST /api/sources/gopro/connect` passes the body as
  one dict (`castlib/api.py:215-219`), `disconnect` exists (`api.py:220-225`) though no tab has a
  UI control for it, `GET /api/status` aggregates `status()` (`app.py:513`).
- **Only Chromium-family browsers speak CDP**: Firefox disabled CDP in 129 and removed it in 141
  (2025-07-22; `research.md`, spike of 2026-09-21). Windows 11 always carries Edge; this Fedora
  has Chrome 153 and Firefox. Chrome 136+ ignores `--remote-debugging-port` on the default
  profile, so a non-default `--user-data-dir` is mandatory - which the design needs anyway.
- **Proven locally on 2026-09-21** (research.md, "Spike: an app-owned Chrome window"): Chrome
  with `--user-data-dir=<dir> --remote-debugging-port=0` writes the port to
  `<dir>/DevToolsActivePort` within 0.3 s; a WebSocket client written on `socket` alone (no
  `Origin` header) calls `Storage.getCookies` and gets HttpOnly cookies back with `httpOnly`,
  `session` and `expires`; `Browser.close` ends the process with exit code 0. Not yet proven: a
  real gopro.com sign-in inside such a window (Phase 5).
- **The release build runs for a pull request that touches `packaging/**`**
  (`.github/workflows/release.yml:8-12`) and uploads `cast-tv-windows-x64.exe` as a workflow
  artifact without publishing. Phase 1 touches `packaging/smoke.py`, so every push on the PR
  yields the Windows binary Phase 5 tests.
- **Lessons that bind this plan**: a ticked manual row needs a written observation
  (`lessons.md:5-10`); a step names the window and the control (`lessons.md:20-25`); nothing the
  app needs is a file the user copies (`lessons.md:27-32`); no provider secret in the repository
  and the agent never reads a token (`lessons.md:34-39`); a user-action message is not owned by
  the poll (`lessons.md:41-46`).

## Definitions

| Term | Decided meaning | Origin | On degenerate data (tie, duplicate, empty, boundary, legacy) | Verified by |
| ---- | --------------- | ------ | ------------------------------------------------------------- | ----------- |
| the hand-off | The `gp_access_token` cookie of a gopro.com session reaches cast-tv from a browser window cast-tv launched, without a devtools trip. | user (`frame.md:93-105`) | No Chromium-family browser, a launch that never yields a DevTools port, or a blocked CDP (Edge policy `RemoteDebuggingAllowed`): the hand-off is *unavailable or failed* and the gate falls back to the paste with the reason. | `test_browser.py::test_no_candidate_is_no_browser`, `::test_failed_launch_is_browser_failed`, manual 5.6, 5.10 |
| captured / connected | A value counts only after `search(tok, 1)` answers 200; finding the cookie is not success. | user (2026-09-21, mechanism answer) | The profile holds a stale cookie: the first value is refused with 401, the window stays open, each distinct value is verified once, the first that answers 200 wins. | `test_browser.py::test_stale_value_waits_for_a_new_one`, `test_gopro.py::test_handoff_connects_after_verification` |
| the paste | The token field appears only when the hand-off is unavailable or failed; `cast-gopro --token` and `GOPRO_TOKEN` stay. | user (2026-09-21, [DEF] answer) | A window closed by the person, a Cancel or a timeout is *not* a failure: the gate shows the button again and no field. The 401 banner follows the same rule. | `test_gopro.py::test_closed_window_is_not_a_fallback`, `test_ui.py::test_gopro_gate_offers_the_window_first`, manual 5.5 |
| the override | `CAST_TV_BROWSER`, when set, is the *only* candidate and is used even if the file does not exist (the `GOOGLE_CLIENT_JSON` rule, `loopback.py:69-71`); a launch that fails is `browser_failed` with the OS reason, so the gate falls back. `--version` names it, with "(not found)" when missing. | review F1, accepted 2026-09-21 | Set to a missing path: no Chrome or Edge is tried; the fallback block appears with the reason (this is how rows 5.6 and 5.10 exercise the fallback). Set to an empty string: treated as unset. | `test_browser.py::test_env_override_is_exclusive`, `::test_missing_override_is_browser_failed`, manual 5.6, 5.10 |
| the profile | A persistent browser profile owned by cast-tv at `config_dir()/gopro-browser` (0700), HTTP cache at `cache_dir()/gopro-browser-cache`, password manager off, removed by `disconnect()`. | user (2026-09-21, [DEF] answer) | Empty on first use (GoPro asks to sign in); present with a live session (the window may close by itself); the user's own Chrome profile is never touched. `disconnect()` with no profile is a no-op. | `test_browser.py::test_profile_is_private_and_cache_is_elsewhere`, `::test_preferences_seeded_once`, `test_gopro.py::test_disconnect_removes_the_profile`, manual 5.9 |
| on this computer | The window opens on the machine running cast-tv, whichever device pressed the button; the phone sees a note that says so. | product (US-03 precedent, `README.md:157-158`) | Pressed from the phone: the window is on the laptop; the phone's tab flips to the list by itself once the value is verified. | `test_gopro.py::test_status_carries_the_on_host_note`, manual 5.8 |
| cancel vs failure | Cancel (the UI's button, the person closing the window, a timeout) ends the round with a note and the button; failure (no browser, launch failed) ends it with the fallback. | user (2026-09-21, edge-case answer) | Cancel while nothing runs is a no-op. Closing the window after the value was captured is fine: the window was being closed anyway. | `test_browser.py::test_process_exit_is_browser_closed`, `::test_cancel_closes_only_our_instance`, manual 5.4, 5.5 |
| one round at a time | A second `connect({})` while a round runs answers the running round; no second window. Timeout 300 s like Google's consent. | product (precedent `gphotos.py:425-426`, `loopback.py:41`; accepted 2026-09-21) | Two devices press within a second: one window. After the timeout the browser is closed and the gate says so. | `test_gopro.py::test_second_connect_joins_the_round`, `test_browser.py::test_timeout_closes_the_browser` |
| the observed period | `captured_at`, `captured_by`, `last_success_at`, `first_401_at` and the cookie's `session` / `expires` are kept next to the token in `config_dir()/gopro-session.json` (no secret in it), survive a restart, and land as one Diagnostics card on the first refusal; reported as "worked for at least N, first refusal after M", never as a lifetime. | user (2026-09-21, measurement answer); persistence and the card path: review F2, F3, accepted 2026-09-21 | A pasted token has `captured_at` = the paste, `captured_by: "paste"`, no cookie metadata. A token file with no matching sidecar (from before this change, or replaced by hand): `captured_by: "unknown"`, `age` from the file's mtime as today. `GOPRO_TOKEN`: `captured_by: "env"`, metadata in memory only. A 401 with no prior success: "no successful call recorded". | `test_gopro.py::test_401_hint_carries_the_observed_period`, `::test_session_metadata_survives_a_restart`, `::test_a_replaced_token_file_drops_the_metadata`, `test_api.py::test_first_401_lands_one_diagnostics_card`, manual 5.12 |
| the wording | Button "Open gopro.com" / "Open gopro.com again"; body "A gopro.com window opens on the computer running cast-tv. Sign in in that window. cast-tv then uses that browser session to access your GoPro media and closes the window."; after a 401 "cast-tv couldn't access your GoPro media with this session. Open gopro.com again to reconnect." The phrase "GoPro sign-in" never names the captured session. | user (2026-09-21, wording answer; `frame.md:118-119`) | The "no public sign-in for other apps" sentence, dated, lives in README and `HOW_TO_GET_A_TOKEN`, not in the gate. | `test_ui.py::test_gopro_gate_texts`, review of README |
| exit closes the window | Ctrl+C, closing the console (Windows) or SIGTERM while a round runs closes the browser instance cast-tv launched; nothing else is touched. | user (2026-09-21, edge-case answer) | A round that already finished: nothing to close. A browser the person opened themselves: never touched (different profile, different process). | `test_gopro.py::test_close_cancels_the_round`, manual 5.7, 5.10 |
| the standing | cast-tv has no permitted way to call `api.gopro.com`; the hand-off borrows the person's own browser session. Recorded as a README limitation with the read date of the sources, like S-11's screen saver. | user (`frame.md:114-122`) | n/a | review of README "Limitations" |

## Desired End State

On Fedora and on Windows 11, the GoPro tab shows one button. Pressing it opens a gopro.com window
on that computer; after the person signs in there, the window closes by itself and the tab lists
the library, with the header saying when the session was captured. When GoPro refuses the token
later, the banner says so and offers the same button. The token field is on screen only when
cast-tv could not run the window, with the reason in one line. `cast-tv --version` names the
browser candidate it would use. The README's GoPro section describes the window, the profile
and, under Limitations, the standing with a date; the PRD's FR-010 names both routes. The
session's metadata survives restarts in a small file next to the token; the first refusal puts
one card in Diagnostics with the observed period, which then goes into `research.md`.

Verification: the automated rows of every phase are green on both CI systems; the manual rows
of Phase 5 have written observations in `research.md` for Fedora (Chrome, from source) and
Windows 11 (Edge, the `.exe` artifact of the PR's release-build run).

### Key Discoveries:

- Chrome writes `"<port>\n/devtools/browser/<uuid>"` to `DevToolsActivePort` in the user data
  dir once the port is bound; `/json/version` returns `webSocketDebuggerUrl` (Chromium
  `devtools_http_handler.cc`, read 2026-09-21; observed locally the same day).
- The DevTools WebSocket rejects only requests that *carry* an `Origin` header outside
  `--remote-allow-origins` (Chrome 111+); a client that sends none connects (Selenium #11750,
  crbug 1422444; read 2026-09-21).
- `Network.Cookie` carries `httpOnly`, `secure`, `session` and `expires` (seconds since the
  epoch, -1 when unset); `Storage.getCookies` at the browser target returns every cookie of the
  context (protocol JSON, read 2026-09-21; HttpOnly observed locally).
- Chrome's `ProcessSingleton` is per user data dir: a fresh `--user-data-dir` always starts a
  new browser process, even while the person's own Chrome runs (Chromium `process_singleton.h`,
  `docs/user_data_dir.md`, read 2026-09-21).
- Edge accepts `--remote-debugging-port`, `--user-data-dir` and `--app=` and speaks the same
  protocol; an enterprise policy `RemoteDebuggingAllowed=false` blocks it - a "failed" case
  (learn.microsoft.com, read 2026-09-21).
- Playwright finds Chrome and Edge on Windows under `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%`
  and `%LOCALAPPDATA%` + `Google\Chrome\Application\chrome.exe` /
  `Microsoft\Edge\Application\msedge.exe`; Chrome's installer also registers
  `App Paths\chrome.exe` (chromium.org installer docs, read 2026-09-21).
- The `gphotos` flow record + generation pattern (`gphotos.py:291-363`) is the shape to copy; the
  `FakeGoPro` fixture (`tests/test_gopro.py:22-113`) already scripts `api.gopro.com` with one
  good token, so verification in tests is "the value equals `fake.good`".
- `packaging/smoke.py` asserts on `cast-tv --version` output (`smoke.py:26-30`); the runners
  `ubuntu-22.04` and `windows-latest` carry Chrome (Windows also Edge), so a static candidate
  line can be asserted there without launching anything.

## What We're NOT Doing

- **No "Forget the session" control in the UI** (declined 2026-09-21). `disconnect()` and its
  route still exist and now also remove the profile; a UI control is a later change if wanted.
- **No bookmarklet** (`frame.md:62-65`), **no browser extension** (a folder to load or a store
  listing, plus an Origin carve-out in the server; declined 2026-09-21), **no embedded webview /
  pywebview** (a dependency and two platform runtimes; revisit only if S-12 makes an embedded
  window a product requirement).
- **No headless "silent retry"** of the profile before showing a window, and **no active probing**
  of `api.gopro.com` to time the token. Passive observation only.
- **No `cast-gopro --connect`**: the CLI's no-token message points at the UI; `--token` stays.
- **No change to the standing**: no Cloud API application, no contact with GoPro, no claim in
  any text that the window is a "GoPro sign-in".
- **No hand-off on the phone** (it opens the window on the host; the phone gets a note), **no
  Firefox** (no CDP since 141), **no reading of the person's own browser profile**, **no Flatpak
  or Snap special-casing** (a wrapper on `PATH` is tried like any candidate; a launch that yields
  no port falls back).
- **`--no-browser` does not touch the hand-off**: the flag means "do not open the UI tab"; the
  window *is* the mechanism, so it opens regardless.
- **No password saved by the app** in any form (ToS §1, `research.md:53`); the profile's
  password manager is off.
- **OneDrive and Google Photos are untouched.**

## Implementation Approach

Copy the Google Photos shape, swap the mechanism. A new module `castlib/auth/browser.py` owns
everything about the window (candidates, profile, launch, the CDP session, the cookie loop,
close); it depends on the small stdlib WebSocket/CDP client in `castlib/auth/cdp.py` and on a
`verify(value) -> bool` callback so it never imports the source. `GoProSource` gains the
`connecting` state with `step: "browser"`, a flow record with the generation, a `close()`, the
session metadata (persisted next to the token), a `report` seam that puts the first refusal in
Diagnostics, the fallback signal, and the profile removal in `disconnect()`. The UI renders
the new step with the texts decided above and shows the paste only on `detail.fallback`. Docs
follow, then both systems are exercised by hand before merge, Windows on the PR's own `.exe`.

The launcher and the CDP session are injectable (a module-level `launch = subprocess.Popen` and a
`connect = cdp.connect` in `browser.py`, replaced in tests the way `loopback.open_browser` is at
`loopback.py:55`), so the engine's tests run against a fake browser: a thread that writes
`DevToolsActivePort`, serves a stdlib WebSocket and answers `Storage.getCookies` from a script.

## Critical Implementation Details

- **Timing & lifecycle** - delete a stale `DevToolsActivePort` before every launch, or the wait
  reads last run's port. Close with `Browser.close` first and only then `terminate()` /
  `kill()` after a grace of 3 s: a killed Chrome may not flush the profile's cookies, which is
  the whole point of a persistent profile. The window opens only from the button (`{}` with
  nothing stored, or `{"fresh": true}`); `enterTab`'s automatic `connect({})` for a stored token
  must keep verifying without a window (`app.js:240-250`).
- **Preferences** - the file `<profile>/Default/Preferences` is read by Chrome when the profile
  is created; it is written by cast-tv only if it does not exist yet (`{"credentials_enable_service":
  false, "profile": {"password_manager_enabled": false}}`), never rewritten afterwards, because
  Chrome owns it from then on. On Linux add `--password-store=basic` so a fresh profile never
  pops a keyring unlock dialog.
- **The WebSocket handshake carries no `Origin` header**, on purpose (Chrome 111 rule above).
- **State sequencing** - the poll thread verifies with `search(tok, 1)` outside the source's
  lock, then adopts under the lock only if the generation is unchanged; a disconnect or a
  second round in between drops the value and closes the window (the `gphotos.py:351-357`
  shape). `last_success_at` is written by `_call` on success only when the generation matches.
- **Debug & observability** - a 401 from a source route never reaches the Diagnostics ring today:
  `api.dispatch` answers it as JSON (`api.py:57-59`) and only `app.py:206` and
  `supervisor.py:273,366` push cards. The source therefore gets a `report` seam (set by the App
  to `errors.push`) and calls it once, on the transition to `expired`, with the observed-period
  text in the error's `hint`; the panel's generic hint template (`index.html:475-477`) renders
  it with no markup change. The status detail carries the raw timestamps for the API. Nothing
  prints or logs the token value or the cookie value (`lessons.md:34-39`), and `--debug` never
  echoes CDP payloads that contain it.
- **Persistence** - the metadata lives in `config_dir()/gopro-session.json`, written with
  `write_private` next to the token; it is trusted only while its `token_mtime` equals the token
  file's mtime, so a token replaced outside cast-tv silently drops it. `last_success_at` is
  written at most once a minute (thumbs would otherwise rewrite it per request) and always on
  the first 401.

## Phase 1: The hand-off engine

### Overview

The two new modules and their tests, plus the `--version` line and its smoke assertion. Nothing
in the source, the API or the UI changes yet; the engine is reachable only from tests.

### Changes Required:

#### 1. The CDP client

**File**: `castlib/auth/cdp.py` (new)

**Intent**: A client-side WebSocket subset and a CDP session over it, on `socket` and `struct`
alone, so the hand-off adds no dependency and no build step. The size estimate in the
planning session ("about a hundred lines") is not a commitment; frames, disconnects and
timeouts each cost their lines.

**Contract**: `connect(ws_url, timeout) -> Session`; `Session.call(method, params=None,
timeout=10.0) -> dict` (the `result`, or `CdpError(code, message)` for a protocol error, a
closed socket or a timeout); `Session.close()`. Handshake with `Sec-WebSocket-Key` and no
`Origin`; client frames masked; 7/16/64-bit lengths; continuation frames joined until `FIN`;
`ping` answered with `pong`; a `close` frame or EOF raises `CdpError("closed")`. Events (messages
without `id`) are discarded. Never logs payloads.

#### 2. The window

**File**: `castlib/auth/browser.py` (new)

**Intent**: Find a Chromium-family browser by trying to launch it, own the profile, run the
cookie loop against a verifier, and close what it opened.

**Contract**:

- `candidates() -> list[str]`: when `CAST_TV_BROWSER` is set and non-empty it is the only
  candidate, used whether or not the file exists (an explicit choice is honoured and its failure
  reported, the `GOOGLE_CLIENT_JSON` rule at `loopback.py:69-71`). Otherwise, on Windows the
  `App Paths` registry values for `chrome.exe` and `msedge.exe` (HKLM, then HKCU; `winreg`) and
  the `%PROGRAMFILES%` / `%PROGRAMFILES(X86)%` / `%LOCALAPPDATA%` paths of Chrome and Edge; on
  other systems `shutil.which` over `google-chrome`, `google-chrome-stable`, `chromium`,
  `chromium-browser`, `microsoft-edge`, `microsoft-edge-stable`, `brave-browser`; existing files
  only, duplicates removed, order kept.
- `describe() -> str`: `CAST_TV_BROWSER=<path>` (plus " (not found)" when the file is missing)
  when the override is set; else the first candidate's path, or `"none found"`; for `--version`
  (no launch).
- `profile_dir() -> str` = `config_dir()/gopro-browser`; `cache_dir_for_profile() -> str` =
  `cache_dir()/gopro-browser-cache`. `prepare_profile()` creates both (profile 0700 on POSIX) and
  seeds `Default/Preferences` once. `remove_profile()` removes both, ignoring absence.
- `class Handoff`: `start(verify, timeout=HANDOFF_TIMEOUT)` launches the first candidate that
  yields a `DevToolsActivePort` within `LAUNCH_TIMEOUT` (15 s) - a candidate whose process exits
  or never writes the file is skipped, its stderr tail kept for the reason - with the flags
  `--user-data-dir`, `--disk-cache-dir`, `--remote-debugging-port=0`, `--no-first-run`,
  `--no-default-browser-check`, `--app=https://gopro.com/media-library/` (plus
  `--password-store=basic` off Windows); then a thread polls `Storage.getCookies` every 1 s,
  keeps cookies named `gp_access_token` whose domain is `gopro.com` or ends with `.gopro.com`,
  and calls `verify(value)` once per distinct value; the first `True` fills `result`
  (`{"token", "captured_at", "cookie": {"session", "expires"}}`) and closes the browser. `wait()`
  blocks for the result or raises `AuthError` with one of `no_browser` (no candidate at all),
  `browser_failed` (every candidate failed to yield a port, reason attached), `browser_closed`
  (the process ended before a value was verified), `browser_timeout` (deadline passed; the
  browser is closed), `cancelled`. `cancel()` closes the browser (`Browser.close`, then
  `terminate` after 3 s, then `kill`) and only ever the process this object launched. A verify
  call that raises something other than `AuthError` leaves the value untried for the next poll.
- The module-level `launch = subprocess.Popen` and `connect = cdp.connect` are the seams tests
  replace.

#### 3. The version line and the smoke test

**File**: `castlib/cli.py` (`version_text`, `cli.py:286-290`)

**Intent**: `cast-tv --version` gains a third line, `GoPro window: <candidate path>` or `GoPro
window: none found (token paste only)`, so a support question can be answered from one command
and CI can see discovery work on Windows.

**Contract**: `browser.describe()` is called; nothing is launched.

**File**: `packaging/smoke.py`

**Intent**: Assert the line is present and names a candidate on the runner (both runner images
carry Chrome). Touching `packaging/` makes the release build run for the PR, which is what
Phase 5 needs for the Windows `.exe`.

**Contract**: after the Google client check (`smoke.py:26-30`), fail if `"GoPro window: "` is
absent or reads `none found`.

#### 4. Tests

**File**: `tests/test_cdp.py` (new), `tests/test_browser.py` (new), `tests/fakes_cdp.py` or a
fixture in `tests/conftest.py`

**Intent**: A fake browser: a Python thread that writes `DevToolsActivePort`, listens on
`127.0.0.1:<port>`, answers `/json/version`, upgrades to WebSocket, and replies to
`Storage.getCookies` from a scripted list that may change over time, to `Browser.close` by
closing the socket and flagging the fake process ended. `launch` is replaced by a callable that
returns a fake `Popen` (with `poll()`, `terminate()`, `kill()`, `wait()`) bound to that thread.

**Contract** (named tests, each a Definitions row's evidence):

- `test_cdp.py`: handshake sends no `Origin`; a masked client frame is unmasked correctly by the
  fake; a 70 000-byte answer (16-bit length) and a 3-frame continuation answer are joined; a
  `ping` gets a `pong`; a server close raises `CdpError`; a call past its timeout raises.
- `test_browser.py::test_candidates_order`, `::test_env_override_is_exclusive` (with the
  override set to an existing fake, no other candidate is consulted; an empty value is unset),
  `::test_missing_override_is_browser_failed` (set to a missing path: no other candidate is
  tried, `browser_failed` names the path and the OS error),
  `::test_no_candidate_is_no_browser`, `::test_failed_launch_is_browser_failed` (first candidate
  exits at once, second is not even present → `browser_failed` with the stderr tail),
  `::test_a_failing_candidate_is_skipped` (first never writes the port, second serves →
  captured), `::test_cookie_name_and_domain_filter` (a `gp_access_token` on `example.com` and a
  `gp_other` on `gopro.com` are ignored), `::test_stale_value_waits_for_a_new_one` (the fake
  serves `eyJold` first; the verifier refuses it; after two polls it serves `eyJgood`; captured
  once; the verifier saw each value once), `::test_two_cookies_each_verified_once`,
  `::test_process_exit_is_browser_closed`, `::test_timeout_closes_the_browser` (the fake got
  `Browser.close`), `::test_cancel_closes_only_our_instance`,
  `::test_profile_is_private_and_cache_is_elsewhere` (0700 on POSIX; the cache dir is under the
  cache root; both in the flags), `::test_preferences_seeded_once` (a second `prepare_profile`
  does not overwrite a changed file), `::test_flags` (`--remote-debugging-port=0`, `--app=`,
  `--user-data-dir` present; `--password-store=basic` off Windows only),
  `::test_stale_port_file_is_removed_before_launch`, `::test_nothing_logs_the_value` (captured
  output contains neither value).
- `tests/test_cli.py`: `--version` prints the `GoPro window:` line from `describe()`, and with
  `CAST_TV_BROWSER=/nonexistent` the line reads `GoPro window: CAST_TV_BROWSER=/nonexistent (not found)`.

### Success Criteria:

#### Automated Verification:

- Unit tests pass on both systems: `python -m pytest tests/test_cdp.py tests/test_browser.py tests/test_cli.py`
- Lint passes: `python -m pyflakes castlib tests`
- The PR's release-build job is green on `windows-latest` and `ubuntu-22.04`, and its smoke
  step prints a `GoPro window:` line naming a browser
- The uploaded artifact `cast-tv-windows-x64.exe` is downloadable from the run

#### Manual Verification:

- On Fedora, in a terminal at the checkout, `.venv/bin/cast-tv --version` prints three lines and
  the third names `/usr/bin/google-chrome`

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful before
proceeding to the next phase. Phase blocks use plain bullets - the corresponding `- [ ]`
checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 2: The source and the API

### Overview

`GoProSource` runs the hand-off as a round, exactly as Google Photos runs its consent; the API
surface is unchanged because the contract already passes any body and any status.

### Changes Required:

#### 1. The round, the states, the timing fields

**File**: `castlib/sources/gopro.py`

**Intent**: Give the source a `connecting` state with `step: "browser"`, start the hand-off from
`connect()`, adopt a verified value under the generation rule, record the observed period, and
make the fallback signal visible to the UI.

**Contract**:

- New instance state: `_flow_lock`, `_flow: dict | None` (`{started_at, expires_at, handoff,
  gen}`), `_flow_error: dict | None`, `_fallback: dict | None` (`{reason, steps}`, kept until a
  hand-off succeeds or `disconnect()`), and the session metadata `_meta: dict` with
  `captured_at`, `captured_by` (`"window" | "paste" | "env" | "unknown"`), `cookie`
  (`{session, expires}` or `None`), `last_success_at`, `first_401_at`. `_expired_at` stays the
  in-process flag; `first_401_at` is the persisted timestamp. `report: Callable[[CastError],
  None] | None = None` is the seam the App sets to `errors.push`.
- The session metadata file: `SESSION_NAME = "gopro-session"`, `session_file() ->
  config_dir()/gopro-session.json`, written with `config.write_private` (0600, atomic) as the
  JSON of `_meta` plus `token_mtime` (the token file's mtime right after `save_token` wrote it).
  It never holds the token or any part of it. `save_token(value, meta=None)` writes the token,
  then the sidecar with `captured_by: "paste"` and `captured_at: now` unless `meta` says
  otherwise (the hand-off passes `captured_by: "window"`, `cookie`); `cast-gopro --token` goes
  through it unchanged. `_credential()`'s first read loads the sidecar and keeps it only if
  its `token_mtime` equals the token file's current mtime; otherwise `_meta` is `{"captured_by":
  "unknown"}` and `age` comes from the file's mtime as today. With `GOPRO_TOKEN` set, `_meta`
  is `{"captured_by": "env", "captured_at": process start}` and nothing is written.
  `last_success_at` is written to disk at most once per 60 s (`META_WRITE_EVERY`), and always
  when `first_401_at` is set. `forget_token()` removes the sidecar with the token.
- `status()`: a running round answers `{"state": "connecting", "detail": {"stored", "step":
  "browser", "expires_in", "note": ON_HOST_NOTE}}` (the note: "The gopro.com window opens on the
  computer running cast-tv, not on the device showing this page."). Otherwise as today plus
  `captured_at`, `captured_by`, `last_success_at`, `first_401_at`, `cookie`, and, when set,
  `flow_error` and `fallback`. `age` reads "session captured N ago" for a window capture and
  "token stored N ago" for a paste (`age_text` takes a verb).
- `connect(params)`: `{"token": ...}` is the paste, unchanged (`gopro.py:488-496`), and clears
  `_fallback` on success; `{"cancel": true}` cancels the round; `{}` with a round running answers
  the round (`dict(status(), step="browser")`); `{}` with a stored, unexpired token verifies it
  without a window (today's `gopro.py:497-510`); `{}` with nothing stored, or `{"fresh": true}`,
  or `{}` after `expired`, starts the round. The round's thread calls
  `Handoff.start(verify=lambda tok: self._verify(tok))` where `_verify` runs `search(tok, 1)`
  and returns `True`, or `False` on `AuthError`, letting other errors propagate; on `wait()`
  success it saves the token, adopts it with `captured_by="window"`, `captured_at` and `cookie`,
  only if the generation is unchanged (else it drops the value and the browser is already
  closed); on `AuthError` it stores `flow_error` (all codes) and, for `no_browser` and
  `browser_failed` only, also `_fallback` with `steps` = the numbered lines of
  `HOW_TO_GET_A_TOKEN` (one source of truth for the devtools steps; `app.js` drops its copy).
- `_call`: on success sets `last_success_at` under the generation rule (disk write throttled
  as above); on `AuthError` (the 401) also sets `e.hint` to the observed-period text ("Session
  captured 2026-09-21 20:10. Worked for at least 6 h 12 min (last successful call). First
  refusal 9 h 40 min after capture. Cookie expires: 2026-10-21 (persistent)." / "no successful
  call recorded" / "session cookie"), and, only on the transition from not-expired to expired
  (the generation rule, `gopro.py:421-426`), calls `self.report(e)` when set - one Diagnostics
  card per refusal, never one per thumbnail. A 401 during a cast still reaches the ring through
  the supervisor as well (`supervisor.py:366`); that one case shows two cards, accepted.
- `disconnect()`: cancels a running round (closing the window), then as today, then
  `browser.remove_profile()`, removes the sidecar, and clears every new field.
- `close()` (new): cancels a running round so `App.close()` shuts the window on Ctrl+C
  (`app.py:302-308`); final, like `gphotos.close()`.
- `HOW_TO_GET_A_TOKEN` loses "lasts a few hours" and gains the dated standing sentence: "GoPro
  publishes no sign-in for other applications (checked 2026-09-20; see README, Limitations)."
  Its first line now points at the UI: "Run cast-tv, open the GoPro tab and press Open
  gopro.com. Or, from a signed-in browser:" followed by the steps as today.

#### 2. The wiring

**File**: `castlib/app.py`

**Intent**: The App hands every source that has a `report` attribute its error ring, the way
it hands Google Photos the `open_browser` flag (`app.py:173`).

**Contract**: in `App.__init__`, after `self.sources` is built: for each source with a `report`
attribute, `src.report = self.errors.push`. No other App change.

#### 3. Tests

**File**: `tests/test_gopro.py`

**Intent**: The round on the `Source` contract with a fake `Handoff` (replacing
`browser.Handoff` the way `loopback.start` is replaced in `test_gphotos.py:862-873`).

**Contract** (named): `test_handoff_connects_after_verification` (status walks `disconnected` →
`connecting/browser` → `connected`; the token file exists, 0600; `captured_by == "window"`,
`captured_at`, `cookie` set; the verifier was called with the value once),
`test_status_carries_the_on_host_note`, `test_second_connect_joins_the_round`,
`test_cancel_ends_the_round_with_no_fallback`, `test_closed_window_is_not_a_fallback`
(`flow_error.code == "browser_closed"`, no `fallback`), `test_no_browser_sets_the_fallback`
(`fallback.steps` equals the lines of `HOW_TO_GET_A_TOKEN`; a paste then clears it),
`test_stored_token_verifies_without_a_window` (`connect({})` with a stored token never starts a
round), `test_expired_then_fresh_starts_the_round`, `test_disconnect_removes_the_profile`
(and cancels a running round), `test_close_cancels_the_round`,
`test_a_late_capture_after_disconnect_is_dropped`, `test_last_success_at_moves_on_list`,
`test_401_hint_carries_the_observed_period` (including the "no successful call recorded"
branch), `test_paste_still_works_and_is_marked_paste`,
`test_session_metadata_survives_a_restart` (a second `GoProSource` over the same config dir
reads `captured_by == "window"`, `captured_at` and `cookie` back; the sidecar holds no
substring of the token), `test_a_replaced_token_file_drops_the_metadata` (the token file
rewritten by hand → `captured_by == "unknown"`, `age` from the mtime),
`test_env_token_keeps_metadata_in_memory` (nothing written with `GOPRO_TOKEN`),
`test_last_success_write_is_throttled` (two successes within a minute → one write; the first
401 writes at once), `test_first_401_reports_once` (a `report` stub sees one call for two
refused lists and a refused thumb, with the hint attached). The existing tests keep passing
unchanged.

**File**: `tests/test_api.py`

**Intent**: The route needs no change; one test asserts `POST /api/sources/gopro/connect` with
`{"fresh": true}` returns `step: "browser"` and `GET /api/status` shows `connecting`; another,
`test_first_401_lands_one_diagnostics_card`, lists twice after the fake refuses the token and
finds exactly one `token_rejected` entry in `GET /api/errors`, whose `hint` carries the
observed-period text.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/test_gopro.py tests/test_api.py` passes on both CI systems
- The full suite passes: `python -m pytest`
- Lint passes: `python -m pyflakes castlib tests`

#### Manual Verification:

- On Fedora, with cast-tv running from the checkout and the old UI still in place: `curl -s
  -H 'Host: localhost:8895' -X POST http://localhost:8895/api/sources/gopro/connect -d '{"fresh": true}'`
  opens a gopro.com window on this machine; `GET /api/status` shows `connecting` with
  `step: browser`; closing the window by hand makes the status show `flow_error.code ==
  "browser_closed"` and no `fallback` (no sign-in is performed in this row)

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful before
proceeding to the next phase.

---

## Phase 3: The UI gate

### Overview

The gate, the banner, the tab hint, the header line and the Diagnostics cards speak the decided
texts; the paste appears only on `detail.fallback`.

### Changes Required:

#### 1. The gate data and helpers

**File**: `castlib/ui/app.js`

**Intent**: Replace the paste gate by the window step, keep the paste as the fallback block, and
route the decided texts.

**Contract**:

- `GATES.gopro`: `title: 'Connect GoPro'`, `body` = the decided body, `cta: 'Open gopro.com'`,
  `again: 'Open gopro.com again'`, `note: 'The session is kept in ~/.config/cast-tv (Windows:
  %APPDATA%\\cast-tv), readable by you only.'`, `window: true`, no `paste`, no `steps`;
  `expired: "cast-tv couldn't access your GoPro media with this session."`, `expiredBody: 'Open
  gopro.com again to reconnect.'`.
- `openWindow(name)` posts `connect(name, {fresh: true})`; `connecting()` also recognises
  `step === 'browser'`; `sourceHint` shows `'gopro.com window open…'` for that step and
  `'reconnect needed'` for `expired` on GoPro; `expiredText` returns the decided sentence;
  `fallback(name)` returns `detail.fallback || null`; `headerLine` shows `d.age` as before (the
  server now says "session captured 3 h ago").
- `cardClass` adds `no_browser`, `browser_failed`, `browser_closed`, `browser_timeout` to the
  `warn` codes.
- **Diagnostics needs no markup change.** The first refusal arrives in the panel as a
  `token_rejected` card pushed by the source (Phase 2), and the existing generic hint template
  (`index.html:475-477`) renders its observed-period text. Before the first refusal the only
  UI presentation of the metadata is the header's `age` ("session captured 3 h ago"); the raw
  fields (`captured_at`, `cookie`, `last_success_at`) are API-only, read from
  `GET /api/sources/gopro` (row 5.3). The expired banner shows the decided sentence and no times.
- `gateNote` stays the user-action message it is (`lessons.md:41-46`); the poll only writes
  `flow_error`-derived text through `flowError()`.

#### 2. The gate markup

**File**: `castlib/ui/index.html`

**Intent**: One `x-if="gate(tab).window"` block next to the existing consent and device-code
blocks, and the banner's second copy of the paste replaced by the button plus the same fallback
rule.

**Contract**:

- Idle: the body text, the **Open gopro.com** button (`busy.connect` → "Opening…"), the note,
  `gateNote`, `flowError` (one line: "The gopro.com window was closed before a session
  appeared." / "No gopro.com window could be opened within 5 minutes." / the reason).
- Connecting (`step === 'browser'`): "A gopro.com window is open on the computer running cast-tv.
  Sign in in that window; this page continues by itself." + the waiting line with
  `expires_in` + the phone line from `detail.note` + **Cancel**.
- Fallback (`fallback(tab)`): under the button, "cast-tv could not open a gopro.com window here:
  <reason>. A token pasted from a signed-in browser works instead:" + the ordered steps from
  `fallback.steps` + the paste form (unchanged form, `saveToken`).
- The expired banner (`index.html:269-281`): title and body from the gate, the **Open gopro.com
  again** button, and the fallback block only when `fallback(tab)`.
- The `<h3>` stays "Connect GoPro" (every tab's heading is "Connect <source>").

#### 3. Tests

**File**: `tests/test_ui.py`

**Intent**: Text-presence tests in the style of `test_ui.py:55-70`.

**Contract**: `test_gopro_gate_offers_the_window_first` (index.html has the `gate(tab).window`
block, the paste form is inside the fallback block only, the banner has "Open gopro.com again"),
`test_gopro_gate_texts` (the decided body, the expired sentence, the phone note; the strings
"GoPro sign-in" and "lasts a few hours" appear nowhere in `app.js` / `index.html`),
`test_gopro_steps_are_not_duplicated_in_the_ui` (`app.js` carries no "F12").

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/test_ui.py` passes
- The full suite passes on both CI systems: `python -m pytest`
- Lint passes: `python -m pyflakes castlib tests`

#### Manual Verification:

- On Fedora, in the cast-tv tab of Chrome (from the checkout, `.venv/bin/python -m castlib`):
  the GoPro tab shows one button "Open gopro.com" and no token field; pressing it opens a
  gopro.com window; pressing **Cancel** on the page closes it and the button returns with no
  field (no sign-in performed in this row)
- Same tab: `CAST_TV_BROWSER=/nonexistent .venv/bin/python -m castlib`, press the button: the
  fallback block appears with the reason and the numbered steps, and the token field accepts a
  paste (a paste of a bad value shows "GoPro rejected the token" in `gateNote`)

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful before
proceeding to the next phase.

---

## Phase 4: Docs, PRD, roadmap, CLI

### Overview

Every text that describes the GoPro connection says what is built, dates the standing claim, and
drops "hours".

### Changes Required:

#### 1. README

**File**: `README.md`

**Intent**: The GoPro section (`README.md:123-129`) describes the window, the profile, the
fallback and the environment variables; "Where files live" (`README.md:236-245`) gains the
profile, its cache and `gopro-session.json` (metadata only, no token); "Limitations"
(`README.md:247-283`) gains the standing paragraph and loses "GoPro tokens last hours, not
days" (`README.md:280`).

**Contract**: the section names `CAST_TV_BROWSER`, `GOPRO_TOKEN`, the profile path, the
password-manager-off fact and the fallback; the Limitations paragraph states, with the read date
2026-09-20 and the URLs from `research.md`, that GoPro publishes no sign-in for other
applications, that its Cloud API beta sits behind a business intake, that its Terms of Use §9
permit access only through GoPro's software or a general web browser, and that cast-tv therefore
borrows the person's own browser session - the same footing as the paste it replaces. No
sentence promises a token lifetime; the observed period, once recorded, may be quoted with its
date.

#### 2. PRD

**File**: `context/foundation/prd.md`

**Intent**: FR-010 (`prd.md:129-130`) names both routes; a Non-Goal records the standing.

**Contract**: "FR-010: GoPro lists the cloud library after a session handed over from a browser
window on the host, or after a token pasted in the UI when no such window can be opened; a
refused token keeps the list with a banner." Non-Goals: "No GoPro-sanctioned client: none is
offered to individuals (checked 2026-09-20); the connection is the person's own browser session."

#### 3. Roadmap

**File**: `context/foundation/roadmap.md`

**Intent**: S-13's row (`roadmap.md:48`) gets its Change ID and status; its section
(`roadmap.md:143-153`) records the decision and the mechanism, and drops the bookmarklet.

**Contract**: row `S-13 | s13-gopro-auth | connect GoPro without copying a token by hand | S-03 |
FR-010 | in progress`; the section gains "**Change:** `context/changes/s13-gopro-auth/`" and a
"Planned 2026-09-21" paragraph: the hand-off only, CDP over a Chromium-family browser on the
host, persistent profile, paste as fallback, standing unchanged and documented.

#### 4. The CLI message

**File**: `castlib/sources/gopro.py` (`HOW_TO_GET_A_TOKEN`, done in Phase 2) and `castlib/cli.py`

**Intent**: `cast-gopro` with no token prints the UI route first (Phase 2's text); `--token`'s
help says "store a token pasted from a signed-in browser (the UI's Open gopro.com is the usual
route)".

**Contract**: `tests/test_cli.py` asserts the no-token message starts with "Run cast-tv".

#### 5. The change folder

**File**: `context/changes/s13-gopro-auth/research.md`

**Intent**: A "Measurements" section with the four fields and the profile question, ready for
Phase 5's observations.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/test_cli.py` passes
- `grep -n "lasts a few hours\|last hours" README.md castlib/ui/app.js castlib/sources/gopro.py` finds nothing
- `grep -n "GoPro sign-in" README.md castlib/ui/*.js castlib/ui/*.html castlib/sources/gopro.py context/foundation/prd.md` finds nothing

#### Manual Verification:

- Read the README's GoPro section and the Limitations paragraph once against `research.md`:
  every claim carries its date or its file:line

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful before
proceeding to the next phase.

---

## Phase 5: Both systems before merge

### Overview

The real thing, on both systems, with a written observation per row in `research.md`
(`lessons.md:5-10`): Fedora with Chrome from the checkout; Windows 11 with Edge on the
`cast-tv-windows-x64.exe` artifact of the PR's latest release-build run (the tested commit's own
binary; no tag). The owner signs in; the agent never sees a credential or a token
(`lessons.md:34-39`).

### Changes Required:

None in code unless a row fails; each row's observation goes to `research.md` under
"Measurements" and "Phase 5 observations" with the date, the machine, the browser version and
what was seen.

### Success Criteria:

#### Automated Verification:

- The full suite is green on both CI systems for the commit under test: `python -m pytest`
- The PR's release-build run for that commit is green and its Windows artifact is the one used
  below (run id noted in `research.md`)

#### Manual Verification:

- 5.3 **Fedora, the full hand-off.** In the cast-tv tab of Chrome on the Fedora machine, GoPro
  tab, press **Open gopro.com**. A gopro.com app window opens on this machine. Sign in there the
  way you normally do (note which: password, Google, Apple; whether 2FA asked). After the
  sign-in the window closes by itself and the tab lists the library; the header reads "session
  captured just now"; Diagnostics shows no new card. Record: Chrome version, sign-in method,
  seconds from the last sign-in click to the list, and `cookie.session` / `cookie.expires` from
  `GET /api/sources/gopro` (values only, never the token)
- 5.4 **Fedora, Cancel.** Press the button, then **Cancel** on the page while the window is open:
  the window closes, the gate shows the button and no token field
- 5.5 **Fedora, the window closed by hand.** Press the button, close the gopro.com window with
  its own close control before signing in: the gate reads "The gopro.com window was closed before
  a session appeared." and shows the button, no token field
- 5.6 **Fedora, the fallback.** Start `CAST_TV_BROWSER=/nonexistent .venv/bin/python -m castlib`,
  press the button: the fallback block appears with the reason and the steps; paste a token
  (yours, from devtools, one last time) and the tab lists; `age` reads "token stored just now"
- 5.7 **Fedora, Ctrl+C mid-round.** Press the button; in the terminal running cast-tv press
  Ctrl+C: it prints `Stopped.` and the gopro.com window closes with it; `pgrep -f gopro-browser`
  prints nothing
- 5.8 **Phone.** On the phone's browser open the LAN address, GoPro tab (after a Disconnect via
  `curl -X POST .../api/sources/gopro/disconnect` so the gate shows), press **Open gopro.com**:
  the window opens on the Fedora machine, the phone shows the on-host note; sign in on the
  machine; the phone's tab lists by itself
- 5.9 **No password bubble.** In rows 5.3 and 5.10 the window offers no "Save password?" bubble
  after the sign-in (Chrome and Edge)
- 5.10 **Windows 11, Edge, the artifact.** Download `cast-tv-windows-x64.exe` from the PR's
  latest release-build run to the laptop; in PowerShell run it; `.\cast-tv-windows-x64.exe
  --version` names Edge (or Chrome; record which and both versions); in the cast-tv tab repeat
  5.3, 5.4, 5.5, 5.6 (`$env:CAST_TV_BROWSER='C:\nonexistent.exe'`), then 5.7 by closing the
  console window while the gopro.com window is open (both close); Task Manager shows no
  `msedge.exe` left from cast-tv's profile
- 5.11 **The profile question** (dated, after the first refusal in use): when the banner "cast-tv
  couldn't access your GoPro media with this session" first appears, press **Open gopro.com
  again** and record whether the window closed without you typing anything (the profile's
  remember-me carried a session) or asked you to sign in
- 5.12 **The observed period** (dated, same moment as 5.11): copy the Diagnostics card's hint
  text - captured, last success, first refusal, cookie expiry - into `research.md`
  "Measurements"; then tick this row

**Implementation Note**: rows 5.11 and 5.12 can only be run when GoPro first refuses a captured
session; the PR may merge with them open and dated, as `standalone-install` row 3.4 is, provided
every other row is ticked with an observation.

---

## Testing Strategy

### Unit Tests:

- `test_cdp.py`: framing (masking, 16-bit length, continuation, ping/pong), handshake without
  `Origin`, close and timeout errors.
- `test_browser.py`: candidate order and `CAST_TV_BROWSER`, launch failure and skipping,
  the port-file wait, the cookie filter, one verification per distinct value, the stale value,
  process exit, timeout, cancel, the profile's mode and cache location, the seeded
  `Preferences`, the flags, no value in any output.
- `test_gopro.py`: the round on the contract (states, generation, late capture dropped),
  cancel vs fallback, stored token verified without a window, `disconnect()` and `close()`,
  the timing fields and the hint text, the paste unchanged.
- `test_ui.py`, `test_cli.py`, `test_api.py`: texts and the `fresh` body.

### Integration Tests:

- The engine against the fake browser end to end (a fake `Popen` + the fake CDP server) in
  `test_browser.py`; the source against a fake `Handoff` in `test_gopro.py`; the API route to
  the source in `test_api.py`. No test launches a real browser or reaches gopro.com.

### Manual Testing Steps:

1. Phase 5 rows 5.3 to 5.10 on Fedora and on the Windows artifact, in that order.
2. Rows 5.11 and 5.12 when the first refusal happens in use.

## Performance Considerations

The window starts in about a second on this machine; the poll is one CDP call per second while
the window is open, nothing afterwards. The profile is small once the HTTP cache lives in
`cache_dir()`. The UI keeps polling `/api/status` every 1.5 s as before; the round's state is
read under the lock without touching the network.

## Migration Notes

A token file from before this change keeps working: it has no sidecar, so `captured_by` reads
`"unknown"` and `age` says "token stored N ago" from the file's mtime, exactly as today. No
file moves. The sidecar appears with the next paste or hand-off; the profile appears only when
the button is first pressed; `disconnect()` removes both. Rolling back the code leaves the
profile directory and `gopro-session.json` behind, harmless and removable by hand (README
"Where files live" names them); an older cast-tv ignores the sidecar.

## References

- Frame brief: `context/changes/s13-gopro-auth/frame.md` (reframed statement `:91-105`,
  addendum `:142-173`)
- Research: `context/changes/s13-gopro-auth/research.md` (the GoPro spikes of 2026-09-20; the
  CDP spike of 2026-09-21 with its sources)
- Pattern to copy: `castlib/sources/gphotos.py:291-363,366-435`; seams for tests
  `castlib/auth/loopback.py:55`, `tests/test_gphotos.py:339-360,862-873`
- The gate today: `castlib/ui/app.js:13-27,240-271`, `castlib/ui/index.html:196-281`
- The source today: `castlib/sources/gopro.py:37-46,366-519`
- Prior decisions: `context/archive/2026-09-07-cloud-source-ui/change.md:179-189`,
  `context/foundation/lessons.md:27-32`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: The hand-off engine

#### Automated

- [x] 1.1 Unit tests pass on both systems: `python -m pytest tests/test_cdp.py tests/test_browser.py tests/test_cli.py` — bec95a4
- [x] 1.2 Lint passes: `python -m pyflakes castlib tests` — bec95a4
- [x] 1.3 The PR's release-build job is green on both runners and its smoke step prints a `GoPro window:` line naming a browser — bec95a4
- [x] 1.4 The artifact `cast-tv-windows-x64.exe` is downloadable from the run — bec95a4

#### Manual

- [x] 1.5 On Fedora, `.venv/bin/cast-tv --version` prints three lines and the third names `/usr/bin/google-chrome` — bec95a4

### Phase 2: The source and the API

#### Automated

- [ ] 2.1 `python -m pytest tests/test_gopro.py tests/test_api.py` passes on both CI systems
- [ ] 2.2 The full suite passes: `python -m pytest`
- [ ] 2.3 Lint passes: `python -m pyflakes castlib tests`

#### Manual

- [ ] 2.4 On Fedora, `POST /api/sources/gopro/connect {"fresh": true}` opens a gopro.com window; status shows `connecting/browser`; closing the window by hand yields `flow_error.code == "browser_closed"` and no `fallback`

### Phase 3: The UI gate

#### Automated

- [ ] 3.1 `python -m pytest tests/test_ui.py` passes
- [ ] 3.2 The full suite passes on both CI systems: `python -m pytest`
- [ ] 3.3 Lint passes: `python -m pyflakes castlib tests`

#### Manual

- [ ] 3.4 On Fedora, the GoPro tab shows one button and no token field; the button opens a window; Cancel closes it and the button returns with no field
- [ ] 3.5 On Fedora with `CAST_TV_BROWSER=/nonexistent`, the button shows the fallback block with the reason, the steps and a working token field

### Phase 4: Docs, PRD, roadmap, CLI

#### Automated

- [ ] 4.1 `python -m pytest tests/test_cli.py` passes
- [ ] 4.2 `grep` finds no "lasts a few hours" / "last hours" in README, app.js, gopro.py
- [ ] 4.3 `grep` finds no "GoPro sign-in" in README, the UI files, gopro.py, prd.md

#### Manual

- [ ] 4.4 The README's GoPro section and Limitations paragraph read against `research.md`: every claim carries its date or file:line

### Phase 5: Both systems before merge

#### Automated

- [ ] 5.1 The full suite is green on both CI systems for the commit under test
- [ ] 5.2 The PR's release-build run for that commit is green; its Windows artifact is the one used below (run id in `research.md`)

#### Manual

- [ ] 5.3 Fedora, the full hand-off (Chrome version, sign-in method, seconds to the list, cookie `session`/`expires` recorded)
- [ ] 5.4 Fedora, Cancel closes the window; button returns, no field
- [ ] 5.5 Fedora, the window closed by hand: "closed before a session appeared", button, no field
- [ ] 5.6 Fedora, the fallback with `CAST_TV_BROWSER=/nonexistent`: reason, steps, a paste works, "token stored just now"
- [ ] 5.7 Fedora, Ctrl+C mid-round closes the window; `pgrep -f gopro-browser` prints nothing
- [ ] 5.8 Phone: the window opens on the Fedora machine, the phone shows the on-host note, then lists by itself
- [ ] 5.9 No "Save password?" bubble in the window on either system
- [ ] 5.10 Windows 11, Edge, the artifact: `--version` names the browser; rows 5.3-5.6 repeated; closing the console closes the window; no `msedge.exe` left
- [ ] 5.11 The profile question, dated: after the first refusal, "Open gopro.com again" closed without typing, or asked to sign in
- [ ] 5.12 The observed period, dated: the Diagnostics hint text copied into `research.md` "Measurements"
