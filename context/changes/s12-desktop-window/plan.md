# A desktop window for cast-tv (S-12) Implementation Plan

## Overview

On the host, cast-tv becomes one thing you start, see, return to and close: the existing `/ui/`
in an app window that owns the TV session, with the console's information moved into it, the
console hidden when nobody asked for one, and an icon plus a menu entry the app writes itself.
The phone keeps the web UI unchanged.

The frame's problem statement, which this plan takes as authoritative (`frame.md`, "Reframed"):

> on the host, cast-tv should be one thing you start, see, return to and close. Today that is
> split across a console that owns the TV session and the screen's information, a plain browser
> tab, and a file with no OS presence. Each of the three parts has its own cause, and only one
> of them is about how the UI is drawn.

## Current State Analysis

The frame's Hypothesis Investigation (`frame.md:61-66`) holds; its findings, in short:

- **Lifetime is bound to the console.** The release is a console executable by design
  (`packaging/cast-tv.spec:1-3,24`). The session ends only by Ctrl+C, SIGTERM or closing the
  console (`castlib/app.py:311-324`, `castlib/platform.py:293-354`). Closing the UI tab stops
  nothing, and the UI's "Stop" stops playback only (`castlib/api.py:157-162`). No UI control
  ends the app.
- **The console carries information the UI does not show:** the phone's LAN addresses
  (`app.py:225-235`), the firewall advice and the proactive "blocked" warning (`app.py:236-244`),
  the TV that was found (`app.py:249,257`). The UI already shows the TV in its header and the
  firewall advice after a failed cast (`castlib/ui/index.html:491-499`). `/api/status` already
  returns `addresses` and `firewall_blocked` (`app.py:567-573`). The UI renders neither.
- **The UI opens as a plain tab:** `webbrowser.open` (`app.py:262-266`). A second launch prints
  "already running" and opens another tab (`castlib/cli.py:264-275`). `/favicon.ico` answers
  204 (`castlib/server.py:195-199`), and the repository has no icon.
- **The release** is one PyInstaller onefile per OS, built on `windows-latest` and
  `ubuntu-22.04` with Python 3.12 and smoke-tested (`.github/workflows/release.yml:15-49`,
  `packaging/smoke.py`). The workflow also runs on pull requests that touch `packaging/**`.

What the spikes settled (`research.md`, four sections, 2026-10-15 to 2026-10-18):

- **Windows:** pywebview with WebView2 renders `/ui/` unfrozen and as a 12.8 MB onefile. Edge
  `--app` works too. WebView2 ships with Windows 11.
- **Linux:** the only one-file candidate that rendered on all five distributions and on both
  real desktops is Qt WebEngine through pywebview (`pywebview[pyside6]`). That holds only when
  the bundle leaves out its own `libgbm.so.1` and `libstdc++.so.6`. About 232 MB.
- **pywebview falls back to another backend quietly** when the requested one fails to load. A
  check that only sees a rendered page can pass on the wrong engine (`research.md`, 2026-10-18).
- **pywebview installs its own SIGINT handler** for both backends: Qt quits from a 500 ms timer,
  WinForms sets a flag (`webview/platforms/qt.py:75-89,956-962`,
  `webview/platforms/winforms.py:45-56,814`; read in pywebview 6.2.1 on 2026-10-18).
  `webview.start()` must run on the main thread (`webview/__init__.py:239-240`), and
  `webview.renderer` names the engine that loaded (`edgechromium`, `qtwebengine`; `:161,249`).
- **PyInstaller 6.22's `hide_console`** (Windows, console executables) hides the console "if the
  program owns the console window (i.e., was not launched from existing console window)"
  (`PyInstaller/building/api.py:382-390`, read 2026-10-18).

The cross-system convention (`frame.md:87-98`): two earlier decisions went against embedded
webviews "unless S-12 makes an embedded window a product requirement"
(`context/changes/s13-gopro-auth/plan.md:131-132`). The owner's answers on 2026-10-18 make it
one. `tech-stack.md:51-52` ("The console window stays") is superseded by this plan.

### Carried from predecessor

none — no Predecessor line

## Definitions

The owner settled these on 2026-10-18, in two rounds of questions in this planning session.

| Term | Decided meaning | Origin | On degenerate data (tie, duplicate, empty, boundary, legacy) | Verified by |
| ---- | --------------- | ------ | ------------------------------------------------------------- | ----------- |
| **Closing the window** | The window's X, Alt+F4, log-off or shutdown ends cast-tv the way Ctrl+C does: Stop to the TV, a running show cancelled, sources closed (the GoPro hand-off window closes), server stopped. The phone loses the UI. No confirmation. | user (2026-10-18: "Kończy cast-tv, TV staje") | **Nothing playing:** the app just quits. **Closed while starting** (before discovery finishes): the same clean path. **Log-off or shutdown:** same, without asking. | `test_window.py::test_gui_end_stops_and_closes`, `::test_sigterm_destroys_window`; manual 1.13, 1.14 |
| **The window is available** | The expected engine actually loaded: `edgechromium` on Windows, `qtwebengine` on Linux. Anything else counts as no window. | user (2026-10-18: "WebView2 + Qt, cały Linux"); the check comes from the 2026-10-18 spike finding | **WebView2 removed, or Qt libraries missing:** falls back to the browser tab, says why on the console and in Diagnostics, and shows the console again (Phase 3). **pipx without `[window]`:** tab, as today. **`--no-browser`:** neither window nor tab. | `test_window.py::test_wrong_renderer_falls_back`, `::test_missing_backend_falls_back`, `test_cli.py::test_no_window_extra_keeps_tab`; smoke `--window-check` |
| **Started by double-click** (owns its console) | Windows: launched from Explorer, the Start menu or Run, not from an existing console. The console is hidden. Launched from PowerShell, cmd or Windows Terminal, the console stays and prints as today, and the window opens. Linux: a menu launch has no terminal; a terminal launch prints as today. | user (2026-10-18: "Jeden plik, konsola znika przy dwukliku"); product (PyInstaller `hide_console` semantics, above) | **A brief console flash on double-click** is accepted (hide-early). **The window falls back while the console is hidden:** the console is shown again, so the process can still be ended. | manual 3.10, 3.11, 3.12 |
| **The phone address** | Every LAN address in `status.addresses` except localhost. The default-route address comes first, then the others, each with Copy and its own QR code. | user (2026-10-18: "QR dla każdego adresu") | **No LAN address (offline):** the panel says so and asks to connect Wi-Fi or Ethernet. **VPN or Docker addresses:** listed like any other; the person picks. **Phone UI** (page not on localhost): no panel. | `test_ui.py::test_phone_panel_lists_lan_addresses`, `::test_phone_panel_only_on_localhost`, `::test_phone_panel_offline`; manual 3.6, 3.8 |
| **Second launch** | When cast-tv already runs with a window, a new launch brings that window to the front and exits. When the running one has no window (tab mode), the new launch opens a tab, as today. | user (2026-10-18: "Przywołuje istniejące okno") | **The running one is mid-start** (window not created yet): answers "no window" and the launch opens a tab. **Something else holds the port:** "Cannot bind port", as today. | `test_api.py::test_window_show_is_loopback_only`, `test_cli.py::test_second_launch_asks_for_the_window`; manual 1.15 |
| **Host-only controls** (`/api/window`, `/api/quit`, `/api/shortcut`) | Answer only requests from this machine's loopback address, on top of the existing Host/Origin rule. The phone gets 403. | product (PRD guardrail "The LAN cannot drive the TV through a web page", `prd.md:66-67`, and Access Control, `prd.md:163-165`); the owner's "second launch" and "menu entry" answers name this machine | **A request from the LAN address of this same machine** is refused; only loopback counts. | `test_api.py::test_host_only_routes_refuse_lan` |
| **The menu entry** | A launcher entry pointing at the file that wrote it. Linux: `~/.local/share/applications/cast-tv.desktop` and a hicolor icon. Windows: `cast-tv.lnk` under the Start menu's Programs. Written and removed by a button in the window. No installer. | user (2026-10-18: "Ikona + przycisk 'Dodaj do menu'") | **The file was moved, or another copy wrote the entry:** the UI says "points to another file" and offers Update. **Two copies:** the entry follows the last one that wrote it. **pipx:** points at the pipx launcher. **Remove twice:** a no-op. | `test_shortcut.py::*`; manual 4.7, 4.8, 4.9, 4.10 |

Ledger: 7 terms checked; all have a `user` origin or follow from one, so none is open.

## Desired End State

- **Windows**, release `.exe` double-clicked: the console flashes at most for a moment, and the
  cast-tv window opens on `/ui/` with its icon.
  - The window shows the phone addresses with QR codes, and a banner when the firewall policy
    blocks the media port.
  - Closing the window stops the TV and ends the process.
  - Clicking the file again brings the window to the front.
  - "Add to Start menu" writes a shortcut that starts it the same way.
  - From PowerShell, `cast-tv-windows-x64.exe film.mkv` and the bare command behave as today,
    and the latter also opens the window.
- **Fedora** (and the other four tested distributions), release Linux binary: the same, with a
  Qt window.
  - "Add to menu" makes cast-tv appear in the GNOME overview with its icon, and grouped with its
    running window.
- **pipx** without the extra: unchanged (tab plus console). With `cast-tv[window]`: the window.
- **When the window cannot open:** cast-tv falls back to today's tab, says why in Diagnostics,
  and keeps a way to end it (a visible console, or the UI's Quit button).
- **The phone UI is unchanged**, apart from not showing the host-only panels.

Verified by the Progress rows below. Manual rows run on the Windows laptop and on the Fedora
desktop, with the evidence written in `research.md` before a row is ticked.

### Key Discoveries:

- `App.start()` already separates "serve" from "block" (`app.py:195-275` vs `:311-324`). The
  window replaces only the blocking half, so `cast()`, `show()` and the CLI's one-shot paths
  keep `run_forever()`.
- `ConsoleClose` interrupts the main thread (`platform.py:327-334`), and `end_on_sigterm`
  raises `KeyboardInterrupt` (`app.py:47-63`). Neither reaches a main thread parked inside a
  Qt or WinForms event loop the way they reach `main_wait`. In window mode both must destroy
  the window instead.
- The GoPro hand-off window is closed by `GoProSource.close()` (`sources/gopro.py:878-890`),
  which `App.close()` already calls (`app.py:348-354`). Closing the main window therefore
  closes it with no new code.
- The release workflow already runs on PRs that touch `packaging/**`
  (`release.yml:9-12`). Phase 2's artifacts can be tested from the PR run without a tag, as
  S-13's were (run 38294412054).
- `tests/ui_driver.js` drives `app.js` in node against scripted `/api` answers
  (`tests/ui_driver.js:1-13`). The phone panel's logic is tested there, with no browser.

## What We're NOT Doing

- **No macOS build or test** — PRD Non-Goal kept (owner, 2026-10-18). Nothing in the window
  path may be Windows- or Linux-only by accident, but nothing proves macOS either.
- **No installers, no auto-update, no code signing** — PRD Non-Goal kept. SmartScreen's
  warning on the unsigned exe stays as today.
- **No tray icon; closing the window never leaves cast-tv running** (owner, 2026-10-18).
- **No confirmation dialog on close** — the owner chose "ends cast-tv" over "asks when
  something plays".
- **No change to the phone's UI or its flows**, beyond hiding the host-only panels there.
- **No programmatic taskbar pinning** — Windows does not allow it; the person pins the running
  window or the Start entry.
- **No Electron, Tauri or Chromium `--app` window** — the spike data chose pywebview with
  WebView2 and Qt (owner, 2026-10-18).
- **No `v0.5.0` tag or release** — tagging needs the owner's go-ahead after Phase 4 and is not
  a row here.
- **No fix for the pre-existing flaky `tests/test_onedrive.py::test_token_file_mode_0600`.** On
  this laptop it failed once in the full suite at planning time and passed 3/3 alone; CI is
  green. Mentioned only so a red run there is not read as this change's. The isolated
  plan-review rerun on 2026-10-18 passed the full suite (382 passed, 5 skipped, exit 0);
  see Testing Strategy — Verification Environment and the dated research note.

## Implementation Approach

The work goes in four phases, ordered by risk.

1. **The window and its lifetime**, in a dev install. The new code paths are proved with a
   fake `webview` in CI and by hand on both machines.
2. **The release**, with the console still visible. Bundling Qt WebEngine with cast-tv's own
   pillow-heif, without the bundle's `libstdc++`, is the largest unknown left, so it comes
   before any UX work.
3. **The console's information moves into the window**, and only then is the console hidden.
   Hiding it earlier would lose the phone address.
4. **Icon and menu entry**, which need the release paths to point at.

pywebview is an optional extra, `cast-tv[window]`. The core install and the test job stay
without PySide6, and the release always installs the extra. The window module imports `webview`
lazily, and every caller falls back to the tab when it is missing.

## Critical Implementation Details

**Timing & lifecycle.** `webview.start()` blocks the main thread, so in window mode the main
thread no longer reaches `main_wait`. Every external end requests termination through the
window wrapper. The request handler records a pending-end flag and returns promptly: it must
not call pywebview's `Window.destroy()` on the main thread before `events.shown`, since that
API waits up to 20 s for the main thread to finish showing the window. A worker observes the
request and readiness, then uses the thread-safe destroy API only once the window is shown.
The code after `webview.start()` returns then runs the existing
`interrupted()` + `close()`. The external ends are:

- SIGTERM (`end_on_sigterm`'s handler);
- Windows console close (`ConsoleClose.handle`), plus GUI session-end messages for log-off
  and shutdown (the Windows hook below);
- `/api/quit`.

Ctrl+C already ends the GUI loop through pywebview's own handler. Raising `KeyboardInterrupt`
inside a Qt slot is swallowed by PySide6 and would leave the TV playing.

The wrapper tracks idle/starting/shown/finished and a separate pending-end flag. A request
while starting is retained through window creation; it is never cleared by initialization.
If termination was requested, `run()` returns `closed` even if backend initialization then
fails, so the CLI stops and closes the app instead of opening a fallback tab. Initialization
failure without a termination request returns `unavailable` as before. All exit paths release
worker waits and clear native-window references; termination requests are idempotent.

**Windows session end.** Once WinForms loads `user32`/`gdi32`, `SetConsoleCtrlHandler` no
longer receives `CTRL_LOGOFF_EVENT` or `CTRL_SHUTDOWN_EVENT`. In window mode, a Windows-only
session hook in `castlib/platform.py` owns a hidden native window and its message loop on a
dedicated thread, installed before starting the webview backend and released on exit or
fallback. Keep its native callback alive for the registration lifetime. `WM_QUERYENDSESSION`
accepts session end without a prompt or starting cleanup; `WM_ENDSESSION` with a true
`wParam` requests actual termination, while false means cancellation and leaves the app
running. Console close remains handled by `ConsoleClose`.

Confirmed session end invokes the same idempotent termination coordinator as normal quit,
with a single total cleanup deadline of at most 4 s: request window closure, cancel playback,
attempt Stop, and release sources/server within that budget. The native callback waits only
up to that deadline for the cleanup worker before returning; it must not depend solely on
the main GUI loop returning before Windows terminates the process. Ordinary GUI teardown
may race this path, so Stop and cleanup run at most once. OS termination or an unreachable
TV can prevent completion; this is a bounded best-effort attempt, not a guarantee that an
unresponsive TV acknowledges Stop. Test query, cancellation, confirmed end, repeated end,
and a non-responsive cleanup worker. Validate a real Windows sign-out in manual row 1.14.
Reference: https://learn.microsoft.com/en-us/windows/console/registering-a-control-handler-function

**State sequencing.** The server must serve before the window loads `/ui/`, as today: `App.start()`
returns only after `serve()`. Discovery can still be running when the window appears. The
window is created with `http://127.0.0.1:<port>/ui/`, not `localhost`. On Windows `localhost`
can resolve to `::1` first, and the server binds `0.0.0.0` (`app.py:207`).

**Debug & observability.** pywebview sets `webview.renderer` before launching its `func`
callback on a separate Python worker thread, before `guilib.create_window`; that callback is
not a GUI-thread or window-readiness hook. It can check the renderer, but must not create a
`QApplication` or perform operations requiring the GUI thread. A wrong engine records
`window_unavailable` with the renderer's name and schedules destruction after `events.shown`.
This internal backend rejection returns `unavailable`; an external pending-end request takes
precedence and returns `closed`. If initialization fails, release the waiting worker directly.
**(owner decision 2026-10-18)** The renderer is checked in `window.events.initialized(renderer)`
instead of `func`: pywebview calls it synchronously inside `start()`, before any native window
exists, and a handler returning False cancels the window and the GUI loop (`webview/window.py:212`,
`webview/__init__.py:276-279`; present in the pinned floor, pywebview 6.2.1). The required
renderer is `edgechromium` on Windows (`qtwebengine` on Linux); any other value returns False.
After `start()` returns, `run()` reports a readable mismatch (`the <got> engine loaded, not
<expected>`) as `unavailable: …`. No wrong-engine window is ever shown, so nothing is destroyed
after `shown` for this case. The fake calls `initialized(renderer)` and honours its cancellation.
`--version` reports the engine that would load, without opening a window: it imports the backend
module (`webview.platforms.qt` / `.winforms`) and, on Windows, asks pywebview whether WebView2
is present. Phase 2's smoke test asserts that line, the guard against the 2026-10-18 silent
fallback.

**Linux identity.** GNOME groups a window with its launcher entry by the Wayland `app_id` / X11
`WM_CLASS`. pywebview's Qt backend reuses an existing `QApplication`
(`webview/platforms/qt.py:954`). cast-tv must therefore create it first with
`setDesktopFileName("cast-tv")`, or the window shows a generic icon apart from the menu entry
(Phase 4).

## Phase 1: The window owns the session

### Overview

`cast-tv` with no source opens `/ui/` in a pywebview window when the `window` extra is installed
and the expected engine loads. Otherwise it opens the tab, as today. Closing the window,
Ctrl+C, SIGTERM, console close and the new Quit control all stop the TV and end the process. A
second launch brings the window forward. The PRD and tech stack record the owner's decisions.

### Changes Required:

#### 1. The window module

**File**: `castlib/window.py` (new)

**Intent**: Own everything pywebview: whether a window can open, opening it on the app's URL,
noticing the wrong engine, and ending it from any thread. The CLI stays free of GUI imports.

**Contract**:
- `expected_renderer() -> str | None` gives `"edgechromium"` on Windows, `"qtwebengine"` on Linux
  and `None` elsewhere. On Linux, `PYWEBVIEW_GUI` is set to `qt` before the import, so a host
  GTK is never picked.
- `describe() -> str` is the `--version` line: `"Window: <renderer>"` or
  `"Window: none (<reason>)"`. It opens nothing.
- `run(app, url) -> str` blocks until the GUI ends. It returns `"closed"` when the window was
  closed or destroyed, and `"unavailable: <reason>"` when no window could open or the engine
  was wrong. In both cases the app is still running; the caller decides.
- `show() -> bool` brings the window forward when one exists (restore, then a brief on-top
  toggle) and is thread-safe.
- `destroy() -> None` requests termination without waiting for window readiness. It is safe
  from a signal handler or another thread and idempotent. During `run()` startup it records
  the request even before a native window exists; once shown, the worker destroys that
  window. Outside an active run it is a no-op. No lock held across GUI initialization or
  destruction may be acquired by the signal handler; it only records the pending request.
- `webview` is imported inside the functions only, so tests inject a fake through
  `sys.modules`.
- `CAST_TV_WINDOW_FAIL=1` (test-only, read by `run()`) makes `run()` return
  `"unavailable: CAST_TV_WINDOW_FAIL"` before creating a window. Manual rows 1.12 and 3.12 use it to
  force the fallback on a machine where the window works.

#### 2. The CLI and the app lifecycle

**Files**:
- `castlib/cli.py:264-286`, `ui()`: window mode.
- `castlib/cli.py:342-343`: the `--no-window` flag.
- `castlib/app.py:47-63`, `:195-275`, `:311-330`: separate UI-tab opening from consent policy,
  end hooks and the quit path.
- `castlib/platform.py`: the Windows session-end hook and its bounded cleanup coordination.

**Intent**: `ui()` starts the app with `open_ui=False` when a window is wanted, retaining
`browser=True` for Google Photos consent unless the user supplied `--no-browser`. It runs
`window.run()` on the main thread, then `interrupted()` + `close()`. When `run()` returns
`unavailable`, it records the reason in the error ring, prints it, opens the tab and goes on with
`run_forever()` as today. `--no-window` forces today's tab path; `--no-browser` still means
neither. On `AlreadyRunning`, the second launch POSTs `/api/window`. On `{"window": true}` it
exits 0; otherwise it opens the tab, as today. The printed hint becomes "Close the window or
press Ctrl+C to end it" in window mode.

**Contract**:
- `App.start(..., browser=True, out=None, *, open_ui=None)` separates the main UI tab from
  consent-browser policy. `open_ui=None` preserves existing callers by following `browser`.
  Only `open_ui` controls the initial `webbrowser.open(app.addresses[0])`; `browser` continues
  to control `gphotos.open_browser`. Normal window mode passes `browser=True, open_ui=False`;
  explicit `--no-browser` passes `browser=False, open_ui=False` and opens neither window nor
  tab nor consent browser. `--no-window` retains the browser-tab and consent behavior.
- `end_on_sigterm()` and `ConsoleClose` take an optional `on_end` callable. In window mode it is
  `window.destroy`; otherwise the behaviour stays the current `KeyboardInterrupt` /
  `interrupt_main`.
- `App.quit()` stops the TV and sets the event that ends `run_forever()`. In window mode it also
  calls `window.destroy()`. It is idempotent, and safe from a handler thread.
- Windows session-end handling follows Critical Implementation Details: keep the GUI message
  hook separate from `ConsoleClose`, and share one idempotent cleanup coordinator with normal
  quit. Carry the session-end deadline through blocking Stop/close work; do not merely start
  an unbounded background cleanup and return from the native callback immediately.

#### 3. Host-only routes

**Files**:
- `castlib/api.py:102-170`, routes `/api/window` and `/api/quit`;
- `castlib/server.py:125-146`, a loopback predicate next to `_check_origin`.

**Intent**: The second launch and the UI's Quit reach the running app; the phone cannot.

**Contract**:
- `POST /api/window` → `{"window": bool}`. It shows the window if there is one.
- `POST /api/quit` → `{"ok": true}`, then `App.quit()` runs after the response is written.
- Both answer 403 `forbidden_host_only` unless the client address is loopback (`127.0.0.1`,
  `::1`).
- `/api/status` gains `"window": bool` and `"host": bool`. `host` is true when this request came
  from loopback, so the UI knows which controls to show.

#### 4. Quit in the UI

**Files**: `castlib/ui/index.html`, `castlib/ui/app.js`

**Intent**: In tab mode there is otherwise no way to end cast-tv from the UI. A process started
from a menu would run on invisibly.

**Contract**: a "Quit cast-tv" control, shown only when `status.host && !status.window`. It
POSTs `/api/quit`, then shows "cast-tv has ended; you can close this tab". Its message is its own
state, not the poll's (lessons.md, "A message from a user action…").

#### 5. The optional dependency

**File**: `pyproject.toml:12-20`

**Intent**: `pipx install "cast-tv[window]"` brings the window; the core install does not.

**Contract**: `window = ["pywebview>=6.2.1,<7", "QtPy>=2.4; sys_platform == 'linux'",
"PySide6>=6.12,<7; sys_platform == 'linux'"]`. On Windows pywebview pulls pythonnet itself.

#### 6. The decisions in the foundation documents

**Files**: `context/foundation/prd.md:59-60,70,154-156,175`, `context/foundation/tech-stack.md:23-52`

**Intent**: Record the owner's 2026-10-18 answers where later work looks.

**Contract**:
- **Platforms:** the Linux family (Fedora, Ubuntu 24.04, Debian 13, Arch, openSUSE tested),
  glibc 2.35+, and Windows 11. macOS stays a Non-Goal.
- **Dependencies:** the four packages, plus the optional `window` extra, which the release
  always carries.
- **Non-Goals:** "installers" stays. A menu entry the app writes on request is allowed.
- **Guardrail:** "closing the window" now means the app window.
- **Tech stack:** the "console window stays" rationale is replaced by the window,
  hide-when-owned, and the reason Qt is used on Linux.

### Success Criteria:

#### Automated Verification:

- Lint passes: `python -m pyflakes castlib tests` — at planning: exit 0
- The window module's tests pass with a fake `webview`, including termination before shown, initialization failure with a pending end request, and Windows session-end coordination through a fake native hook (query/cancel/confirm, repeated end, cleanup deadline): `python -m pytest tests/test_window.py` — not run: needs Phase 1 output (the file is new)
- CLI wiring tests pass, including `test_no_window_extra_keeps_tab`, `test_second_launch_asks_for_the_window`, normal window mode retaining consent-browser opening, and explicit `--no-browser` suppressing UI and consent-browser opening: `python -m pytest tests/test_cli.py` — at planning: exit 0 (baseline only; consent-policy cases are Phase 1 output)
- Host-only routes refuse the LAN, including `test_host_only_routes_refuse_lan` and `test_window_show_is_loopback_only`: `python -m pytest tests/test_api.py` — at planning: exit 0
- The Quit control's logic, through the node driver: `python -m pytest tests/test_ui.py` — at planning: exit 0
- The full suite passes: `python -m pytest` — at planning: exit 1 — `test_onedrive.py::test_token_file_mode_0600` failed under load (pre-existing; passed 3/3 alone; see What We're NOT Doing)
- CI on the PR is green on `ubuntu-latest` and `windows-latest`: `gh pr checks <pr>` — not run: external

#### Manual Verification:

- On the Windows laptop, in a venv with `pip install -e ".[window]"`: in PowerShell, `cast-tv` opens a window titled cast-tv on the UI (not a browser tab), and the console prints the addresses (owner decision 2026-10-18: surface declared) — surface: castlib/window.py, castlib/cli.py, castlib/app.py
- On the Fedora desktop, after `pipx install --force "<checkout>[window]"`: `cast-tv` in a terminal opens a Qt window on the UI (owner decision 2026-10-18: surface declared) — surface: castlib/window.py, castlib/cli.py, castlib/app.py
- With pipx without the extra, on either machine: `cast-tv` opens a browser tab, as today, and the tab shows the Quit control; clicking it stops the TV and ends the process (owner decision 2026-10-18: surface declared) — surface: castlib/cli.py, castlib/app.py, castlib/api.py, castlib/server.py, castlib/ui/app.js, castlib/ui/index.html
- `cast-tv --no-window` opens the tab even with the extra installed (owner decision 2026-10-18: surface declared) — surface: castlib/window.py, castlib/cli.py, castlib/app.py
- A forced fallback: on Fedora, in a terminal, `CAST_TV_WINDOW_FAIL=1 cast-tv` opens the browser tab, not a window. The terminal prints why, and Diagnostics in the tab shows `window_unavailable` (owner decision 2026-10-18: surface declared) — surface: castlib/window.py, castlib/cli.py, castlib/app.py
- With a video playing on the TV: closing the window with X stops the TV within 5 s and the PowerShell prompt returns — surface: castlib/window.py, castlib/cli.py, castlib/app.py
- With a video playing: Ctrl+C in the terminal window running cast-tv stops the TV and closes the window; on Fedora, `kill <pid>` from another terminal does the same. Also on the Windows laptop, with a saved-work session and a video playing from the cast-tv window: Start menu → account menu → Sign out, without closing cast-tv first; observe whether TV playback stops. After signing back in, record the observed result and confirm no cast-tv process remains. This extends row 1.14's intent to real Windows session end; its Progress title stays unchanged — surface: castlib/window.py, castlib/app.py, castlib/platform.py
- With the window open behind another window: running `cast-tv` again in a second terminal brings the window to the front and the second command exits at once — surface: castlib/window.py, castlib/cli.py, castlib/api.py
- From the phone, the UI works as before and shows no Quit control (owner decision 2026-10-18: surface declared) — surface: castlib/api.py, castlib/server.py, castlib/ui/app.js, castlib/ui/index.html

**Implementation Note**: manual rows are run with the exact window named (lessons.md, "A step for
the person names exactly where to act"). Each observation goes into `research.md` before its row
is ticked (lessons.md, "A ticked manual row needs a written observation").

---

## Phase 2: The release carries the window

### Overview

Both release files carry the window: WebView2 through pywebview on Windows, and Qt WebEngine on
Linux without the bundle's `libgbm` and `libstdc++`. The smoke test proves that the expected
engine loads and renders `/ui/` in the built file, and that HEIC still decodes. The console
stays visible in this phase.

### Changes Required:

#### 1. The spec

**File**: `packaging/cast-tv.spec`

**Intent**: Bundle the window's dependencies, and on Linux drop the two libraries that broke
the GPU path.

**Contract**:
- `hiddenimports` gains `castlib.window`, `webview.platforms.winforms` on Windows, and
  `webview.platforms.qt` plus `qtpy` on Linux.
- On Linux, `a.binaries` is filtered to remove entries whose basename is `libgbm.so.1` or
  `libstdc++.so.6`. These are the `noboth` variant of `research.md`, 2026-10-16.
- `excludes` keeps `tkinter` and `pytest`, and adds `gi`, so a host GTK is never collected.
- `console=True` stays.

#### 2. The release workflow

**File**: `.github/workflows/release.yml:26-44`

**Intent**: Install the extra and the Linux build libraries, and run the window check in CI.

**Contract**:
- `pip install ".[window]" pyinstaller`.
- On `ubuntu-22.04`, apt installs the libraries PySide6 needs at build and check time
  (`libegl1 libgl1 libxkbcommon0 libxkbcommon-x11-0 libnss3 libxcomposite1 libxdamage1
  libxrandr2 libxtst6 libxkbfile1 libasound2 xvfb`, as in `research.md`, 2026-10-15).
- The smoke step runs under `xvfb-run -a` on Linux.
- If the Windows runner lacks the WebView2 runtime, the workflow installs it with Microsoft's
  bootstrapper before the smoke test. It never skips the check.

#### 3. The version line and the window check

**Files**:
- `castlib/cli.py:289-302`, `version_text()`;
- `castlib/cli.py:349`, a hidden `--window-check`;
- `packaging/smoke.py:29-60`.

**Intent**: The built file proves its window, not just its server.

**Contract**:
- `--version` gains a fourth line from `window.describe()`.
- `--window-check` starts the app on a spare port with no browser, opens the window on `/ui/`,
  and evaluates `document.title` and `typeof window.Alpine`. It checks `webview.renderer`
  against `expected_renderer()`, prints one `window-check: <renderer> OK` line, and ends the app.
  Exit 0 only on all three.
- `smoke.py` asserts the `Window: edgechromium` / `Window: qtwebengine` line, runs
  `--window-check`, and records the binary's size in its output.

### Success Criteria:

#### Automated Verification:

- Lint passes: `python -m pyflakes castlib tests packaging` — at planning: exit 0
- `version_text()` and `--window-check` argument handling are covered: `python -m pytest tests/test_cli.py` — at planning: exit 0
- The full suite passes: `python -m pytest` — at planning: exit 1 — the same pre-existing flaky test as Phase 1
- The release workflow on the PR builds both files, and the smoke test passes on both (version line, `--self-check` HEIC, `/ui/` and `/api/status`, `--window-check`): `gh pr checks <pr>` — not run: external
- A local Windows build passes the smoke test: `pyinstaller --noconfirm packaging/cast-tv.spec && python packaging/smoke.py dist/cast-tv.exe` — not run: writes (dist/, build/)

#### Manual Verification:

- On the Windows laptop, the PR run's `cast-tv-windows-x64.exe` (downloaded into `Downloads\s12-phase2`), started from PowerShell, opens the window. `--version` shows `Window: edgechromium`. Record the file size and the time from Enter to a rendered UI
- On the Fedora desktop, the PR run's `cast-tv-linux-x64`, after `chmod +x` and a start from a terminal, opens a Qt window with the GPU on (no `--disable-gpu`). `--version` shows `Window: qtwebengine`. Record the size and the start time
- On the Fedora desktop, with that Linux binary: cast a HEIC photo from Google Photos or a local file through the window and see it upright on the TV (pillow-heif without the bundled `libstdc++`)
- On the Ubuntu 24.04 VM from the 2026-10-16 spike, if it still exists: the Linux binary opens its window. Otherwise record that it was not run, and why

---

## Phase 3: The console's information moves into the window, and the console hides

### Overview

On localhost, the window shows the phone addresses with Copy and a QR code each, and a banner
when the firewall policy blocks the media port. The Windows release then hides the console it
owns. When the window falls back while the console is hidden, the console comes back.

### Changes Required:

#### 1. The QR generator, vendored

**Files**: `castlib/ui/qrcode.js` (new), `castlib/server.py:33-37`

**Intent**: Make QR codes in the page, with nothing from a CDN and no build step (`tech-stack.md`,
UI row).

**Contract**:
- `qrcode-generator` 2.0.4 (MIT, published 2025-08-07), its `dist/qrcode.js` copied unchanged,
  with its licence header kept.
- `UI_FILES` gains `/ui/qrcode.js`, and the server's "four files" comment becomes five.

#### 2. The phone panel and the firewall banner

**Files**: `castlib/ui/index.html`, `castlib/ui/app.js`, `castlib/ui/style.css`

**Intent**: The information only the console showed is now in the window.

**Contract**:
- **The panel** is an "Open on your phone" panel, shown only when `status.host`. It lists
  `status.addresses` without the localhost entry, in server order (the default route first).
  Each address has Copy and a QR toggle that renders its SVG. With no LAN address it says
  "This computer has no network address. Connect it to Wi-Fi or Ethernet."
- **The banner** shows `status.firewall_advice` while `status.firewall_blocked` is true. The
  poll may write it, because it is server state.

#### 3. Hide the owned console; show it again on fallback

**Files**: `packaging/cast-tv.spec:17-26`, `castlib/platform.py` (`show_console()` and startup
error reporting helpers), `castlib/cli.py` (the fallback and pre-GUI error paths)

**Intent**: The double-clicked exe shows only the window. A fallback must not leave an invisible
process.

**Contract**:
- `EXE(..., hide_console="hide-early")`.
- `platform.show_console() -> bool` calls `ShowWindow(GetConsoleWindow(), SW_SHOW)` on Windows
  and returns False elsewhere. The CLI calls it when `window.run()` returns `unavailable`.
- Startup failures before a usable GUI exists must also remain visible. Keep the existing
  text and nonzero exit status for errors such as `App.start()` failing to bind the port.
  On Windows, when launched without a visible owned console (Explorer/Start, hidden by
  hide-early), also show a blocking native `MessageBoxW` error titled `cast-tv` before exit,
  independent of pywebview. The message names the failed operation, port when applicable,
  and actual error; it stays until acknowledged. An inherited PowerShell/cmd/Windows Terminal
  session keeps the text-only path and receives no extra dialog. Distinguish inherited
  terminals from an owned hidden console; a hidden pseudoconsole HWND alone does not mean
  double-click. Non-Windows behavior stays text-only. Route pre-GUI fatal startup exceptions
  through this reporting path after cleanup, without turning normal Ctrl+C/cancellation into
  an error or opening a dialog for a successful second launch.

### Success Criteria:

#### Automated Verification:

- The static files include `qrcode.js` and nothing else new: `python -m pytest tests/test_ui.py::test_static_exact_match_only` — at planning: exit 0 (it will be updated to list five files)
- Phone panel logic, through the node driver (`test_phone_panel_lists_lan_addresses`, `test_phone_panel_only_on_localhost`, `test_phone_panel_offline`, `test_firewall_banner_follows_status`): `python -m pytest tests/test_ui.py` — at planning: exit 0
- `show_console()` is a no-op off Windows and calls the two APIs on Windows; startup error reporting uses a fake native adapter to cover owned-hidden console, inherited terminal (including a pseudoconsole), non-Windows behavior, and persistent error dialog contents: `python -m pytest tests/test_platform.py` — at planning: exit 0 (baseline only; startup-error cases are Phase 3 output)
- The full suite passes: `python -m pytest` — at planning: exit 1 — the same pre-existing flaky test
- The release workflow on the PR is green on both OSes: `gh pr checks <pr>` — not run: external

#### Manual Verification:

- In the window on the Windows laptop: the "Open on your phone" panel lists the Wi-Fi address first. Scanning its QR code with the phone's camera opens the cast-tv UI on the phone
- On the phone, the UI shows no phone panel and no Quit control
- With Wi-Fi off on the laptop, the panel says there is no network address
- On the Fedora desktop, the same panel and QR codes work in the Qt window
- On the Windows laptop, double-clicking the PR run's exe in Explorer: at most a brief console flash, then only the window. Closing it stops the TV
- From PowerShell, the same exe prints the addresses in the PowerShell window and opens the window. Ctrl+C in that PowerShell window stops the TV and closes the window
- A forced fallback with a hidden console: in PowerShell, `$env:CAST_TV_WINDOW_FAIL='1'; Start-Process .\cast-tv-windows-x64.exe` (the new process owns a new console, so it is hidden first). The console window reappears next to the browser tab, and closing that console window stops the TV. Clear the test variable with `Remove-Item Env:CAST_TV_WINDOW_FAIL`. Also test an error before GUI startup: with cast-tv stopped, in a separate PowerShell window run `python -m http.server 8895 --bind 127.0.0.1`; double-click the cast-tv exe in Explorer and verify a `cast-tv` error dialog names the occupied port and remains until OK. Run the exe from the original PowerShell too: it prints the bind error, exits nonzero, and shows no dialog. Stop the temporary HTTP server with Ctrl+C in its own PowerShell window. This extends row 3.12's error-path coverage without changing its Progress title

---

## Phase 4: Icon and menu entry

### Overview

cast-tv gets an icon: in the exe, in the window, as the favicon and in the menu entry. A button
in the window adds the entry to, or removes it from, the Linux applications menu or the Windows
Start menu, pointing at this file.

### Changes Required:

#### 1. The icon

**Files**:
- `packaging/make_icon.py` (new);
- `castlib/ui/icon.png` (new, 256 px);
- `castlib/ui/cast-tv.ico` (new, 16-256 px; runtime package resource);
- `pyproject.toml` (verify the existing `castlib = ["ui/*"]` includes both icon resources);
- `castlib/server.py:33-37,195-199`;
- `packaging/cast-tv.spec`.

**Intent**: Give cast-tv one recognisable icon everywhere, generated by a committed script so
the owner can replace the design later.

**Contract**:
- `make_icon.py` draws a simple TV-screen glyph with Pillow and writes `castlib/ui/icon.png`
  and `castlib/ui/cast-tv.ico`. Both are committed package resources; the build does not run
  the script. Keep one canonical ICO under `castlib/ui`, not a packaging-only copy: the
  existing `ui/*` package-data rule includes it in wheel/pipx installs without the repository.
- `/favicon.ico` serves `icon.png` as `image/png` instead of answering 204.
- `UI_FILES` gains `/ui/icon.png`.
- The spec uses the ICO from `castlib/ui/cast-tv.ico` (resolved relative to the spec directory,
  as `../castlib/ui/cast-tv.ico`) and bundles the UI resources for the window. The ICO remains
  a local runtime resource only: do not add a public `/ui/cast-tv.ico` route.

#### 2. The window's identity

**File**: `castlib/window.py`

**Intent**: The running window is grouped with its menu entry and shows the icon.

**Contract**:
- On Linux, create the `QApplication` before `webview.start()`, with
  `setDesktopFileName("cast-tv")` and the window icon from `icon.png`.
- On Windows, a frozen window takes the exe's icon; non-frozen window mode explicitly uses
  the packaged `castlib/ui/cast-tv.ico`, so pipx does not inherit the Python executable's icon.

#### 3. The menu entry

**Files**: `castlib/shortcut.py` (new), `castlib/api.py` (route `/api/shortcut`, host-only),
`castlib/app.py:553-574` (`status.shortcut`)

**Intent**: Write and remove the launcher entry that points at the running file, and say when an
existing entry points elsewhere.

**Contract**:
- `target() -> list[str]` is the command line of this file: `sys.executable` when frozen, the
  `cast-tv` launcher found with `shutil.which` under pipx, and `[sys.executable, "-m",
  "castlib"]` from a checkout.
- For the checkout command, resolve an absolute checkout root from the loaded `castlib`
  module location, never the process's current directory. Write it as `Path=` in the Linux
  desktop entry and `WorkingDirectory` on the Windows shortcut; keep executable and arguments
  separate for `.lnk`. Installed/frozen launcher targets do not depend on the checkout.
  `state().current` compares the required working directory as well as the command, so an
  old checkout shortcut lacking it is offered Update.
- `state() -> {"installed": bool, "current": bool, "path": str}`.
- `install()` writes the entry. On Linux: `cast-tv.desktop` with `Type=Application`,
  `Name=cast-tv`, `Exec=` the quoted target, `Icon=cast-tv`, `Terminal=false`,
  `Categories=AudioVideo;Video;Player;` and `StartupWMClass=cast-tv`, plus the PNG under
  `~/.local/share/icons/hicolor/256x256/apps/`. On Windows: the `.lnk` through PowerShell's
  `WScript.Shell`, with the icon taken from the exe for a frozen release. For pipx/checkout,
  copy the packaged `castlib/ui/cast-tv.ico` to a stable app-owned path under `config_dir()`
  and use that copy, independent of the repository or onefile extraction directory. The same
  `subprocess` pattern the firewall query uses (`platform.py:38-60`).
- `remove()` deletes what `install()` wrote and nothing else.
- `POST /api/shortcut` takes `{"action": "install"|"remove"}` and answers with `state()`.

#### 4. The control in the window

**Files**: `castlib/ui/index.html`, `castlib/ui/app.js`

**Intent**: One button, shown on the host only.

**Contract**:
- "Add to menu" / "Add to Start menu" when the entry is not installed.
- "Remove from menu" when it is installed and current.
- "Update menu entry (points to another file)" when it is installed but not current.
- Errors go to the control's own message (lessons.md, "A message from a user action…").

#### 5. Docs and roadmap

**Files**: `README.md` (install and usage), `context/foundation/roadmap.md:139-147` (S-12 block and
row)

**Intent**: README tells a new user to double-click the file, and shows how to add it to the
menu and where pipx's `[window]` extra applies. The roadmap points S-12 at this change.

**Contract**: README sections "Install" and "Use" are updated, and the console paragraph is
rewritten. The roadmap's S-12 row carries Change ID `s12-desktop-window`.

### Success Criteria:

#### Automated Verification:

- Desktop entry and `.lnk` command contents, idempotence, removal, staleness (including checkout working directory), a path with spaces, packaged ICO availability and checkout launch from an unrelated directory: `python -m pytest tests/test_shortcut.py` — not run: needs Phase 4 output (the file is new)
- `/favicon.ico` serves the PNG and `/api/shortcut` is host-only: `python -m pytest tests/test_ui.py tests/test_api.py` — at planning: exit 0
- The full suite passes: `python -m pytest` — at planning: exit 1 — the same pre-existing flaky test
- The release workflow on the PR is green on both OSes: `gh pr checks <pr>` — not run: external

#### Manual Verification:

- On the Windows laptop, the PR run's exe in Explorer shows the cast-tv icon. Its window and taskbar button show it too
- On the Fedora desktop, the window's dash and taskbar entry shows the cast-tv icon, not a generic one
- On the Fedora desktop, clicking "Add to menu" in the window, then searching "cast-tv" in the GNOME overview: the entry is there with the icon, and starting it opens the window with no terminal. Repeat for a pipx install and a checkout launch: close cast-tv first, launch the entry from GNOME (outside the checkout), and confirm the UI opens. This extends row 4.7's installation variants without changing its Progress title
- On the Windows laptop, clicking "Add to Start menu", then opening Start and typing "cast-tv": the shortcut is there. Starting it opens the window with no visible console. Right-click the taskbar button → "Pin to taskbar", close, and start from the pin. Also verify pipx has an icon without access to `packaging/`, and the checkout shortcut starts from Start with its working directory pointing at the checkout. This extends row 4.8's installation variants without changing its Progress title
- After moving the exe to another folder and starting it from there: the window offers "Update menu entry". After clicking it, the Start entry starts the moved file
- "Remove from menu" on both machines removes the entry, and the overview or Start no longer finds it

---

## Testing Strategy

### Verification Environment:

Run local checks from the repository root in an isolated `.venv` with the `test` extra;
the global Python, installed pipx app and spike venv are not the test environment. The
commands below use PowerShell on Windows and do not require changing its activation policy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
python -c "import sys; print(sys.executable)"
```

The last command must name this checkout's `.venv\Scripts\python.exe`. Keep Node on PATH
for `tests/ui_driver.js`. On Fedora: `python3 -m venv .venv`,
`.venv/bin/python -m pip install -e '.[test]'`, then `source .venv/bin/activate`.
Do not install `[window]` for baseline unit checks; GUI integration belongs to the later
phase gates. CI continues using Python 3.12 from `.github/workflows/test.yml`; the local
review environment uses the available Windows Python 3.14.5. This local run does not replace
the two-OS CI gate. Dependency versions and the nine rerun results are recorded in
`research.md`, "Plan-review triage: verification environment (2026-10-18)". Historical
`at planning` markers above describe the original planning run; this separate dated rerun
records current baseline evidence without claiming the not-yet-written S-12 tests passed.
All nine commands passed on 2026-10-18: both lint commands exit 0; the full suite is
382 passed, 5 skipped, exit 0. The historical full-suite exit 1 was not reproduced.

### Unit Tests:

- **`tests/test_window.py`** (new) uses a fake `webview` module in `sys.modules`.
  - It records `create_window`/`start`, and its `start` returns when the test calls `destroy`.
  - It can set `renderer` to any value, and can raise on import.
  - It covers: the GUI ending stops the TV and closes the app; SIGTERM and console close destroy
    the window; a wrong renderer and a missing backend both give `unavailable` and record
    `window_unavailable`; `show()` with no window is False.
  - A readiness-controlled fake asserts that SIGTERM between `create_window` and `shown`
    returns promptly without calling the native destroy API early; after shown it destroys
    the window and the CLI stops/closes the app exactly once, without a fallback tab.
  - Also cover a request before native creation, repeated requests, initialization failure
    with a pending request (closed, cleanup, no stranded worker), and initialization failure
    without a request (unavailable, normal fallback). The fake models `func` running before
    shown on a worker; renderer rejection waits for shown and remains unavailable unless an
    external termination request takes precedence. **(owner decision 2026-10-18)** The fake
    calls `events.initialized(renderer)` before creating the window and returns from `start()`
    without one when a handler answers False; a wrong renderer is rejected there, never shown.
  - Inject the Windows session hook: query alone and cancelled session end keep playback;
    confirmed end attempts Stop and closes sources/server exactly once even when normal GUI
    teardown races it. A fake clock and stalled cleanup prove the callback's 4 s total bound;
    hook registration/release and callback lifetime are covered with a fake native adapter.
- **`tests/test_cli.py`**: `ui()` takes the tab path with no extra and with `--no-window`. The
  second launch POSTs `/api/window` and opens a tab only on `{"window": false}`. `--version` has
  the fourth line. Cover `App.start`'s separate `open_ui`/`browser` policy through the app's
  Google Photos consent flow with a fake browser opener: normal window mode opens consent
  without opening the main UI tab; explicit `--no-browser` opens neither. Existing callers
  omitting `open_ui` retain the previous `browser` behavior.
- **`tests/test_api.py`**: the three host-only routes return 403 for a non-loopback client
  address, and work from loopback. `/api/status` carries `window` and `host`.
- **`tests/test_ui.py`**, through `ui_driver.js`:
  - the phone panel's address list (default route first, localhost dropped), localhost-only
    visibility and the offline text;
  - the firewall banner follows `firewall_blocked`;
  - the Quit and shortcut controls keep their own messages across polls.
- **`tests/test_shortcut.py`** (new) works in `tmp_path` homes. It covers:
  - the exact `.desktop` text, with a target path containing spaces;
  - the PowerShell command built for the `.lnk`, with a fake runner;
  - `install()` twice is one entry, `remove()` twice is a no-op;
  - the stale-target detection.
  - packaged ICO lookup/copy without `packaging/`, and the wheel package-data selection
    including PNG/ICO resources (the HTTP exact-match map must still not expose the ICO);
  - checkout paths with spaces: parse `Exec`/`Path` and `.lnk` command/`WorkingDirectory`,
    then run the checkout command with its declared working directory from an unrelated
    launcher directory using `--version` (no GUI/network). A missing/wrong required working
    directory makes `state().current` false. Fake PowerShell for platform-independent tests;
    the actual Start/GNOME launch and icons remain manual rows 4.7 and 4.8.
- **`tests/test_platform.py`**: `show_console()` and the `on_end` variants of `ConsoleClose` and
  `end_on_sigterm`. Also cover startup-error routing with a fake native adapter: Explorer's
  owned-hidden console gets the persistent MessageBoxW; inherited terminals (including
  Windows Terminal's pseudoconsole) and non-Windows do not. Verify title/error text. Extend
  `tests/test_cli.py` in Phase 3 with `App.start` raising a bind error before `window.run`:
  reporting is invoked, no window starts, exit remains nonzero; cancellation and a successful
  AlreadyRunning hand-off do not use the fatal-error reporter.

### Integration Tests:

- **The release workflow's smoke test** on both runners (Phase 2 onwards): the version line,
  HEIC self-check, `/ui/` + `/api/status`, and `--window-check` rendering `/ui/` in the built
  file with the expected engine.

### Manual Testing Steps:

The Progress Manual rows, run on the Windows laptop and the Fedora desktop, each recorded in
`research.md` with the date, the machine, the file (PR run id) and what was seen.

## Performance Considerations

- **Release sizes and start times.** Windows grows from 22.8 MB by about 10 MB (pywebview,
  pythonnet). Linux grows from 35.7 MB to about 230-250 MB. A onefile start unpacks it each
  time: about 13 s more on Windows for Qt (2026-10-18), which is why Windows uses WebView2. The
  Linux start is measured in Phase 2 (row 2.7). If it is over about 15 s on the Fedora desktop,
  the owner decides before Phase 3 whether to keep onefile or switch the Linux release to a
  onedir archive.
- **The UI poll** (1.5 s) is unchanged. The window adds no requests beyond the page's own.

## Migration Notes

- **Existing users** of the console exe get the window on the next release. The CLI stays the
  same, so scripts calling `cast-tv film.mkv` keep working.
- **No settings or config files change.** The menu entry is written only on request, so an
  upgrade creates nothing.
- **pipx users** keep the tab until they reinstall with `[window]`. README says so.

## References

- Frame: `context/changes/s12-desktop-window/frame.md`
- Research (four spikes): `context/changes/s12-desktop-window/research.md`
- Spike kit (probe shapes for `--window-check`): `context/changes/s12-desktop-window/spike-kit/probe.py`, `probe_pwq.py`
- Prior app-owned window: `castlib/auth/browser.py` (S-13)
- Console-close handling: `castlib/platform.py:293-354` (#11)
- Lessons applied: 5 of 6 entries in `context/foundation/lessons.md`: written observation, branches first, exact steps, nothing copied by hand (the menu entry is a button, not a file to copy), UI messages owned by the action

## Progress

> Convention: `- [ ]` pending, `- [x]` done, `- [-]` not applicable (` — n/a: <reason>` required). Append ` — <commit sha>` when a step lands. A Manual row takes ` — accepted at <full sha>` when a human confirms it. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: The window owns the session

#### Automated

- [x] 1.1 Lint passes — 1083431
- [x] 1.2 The window module's tests pass with a fake webview — 1083431
- [x] 1.3 CLI wiring tests pass — 1083431
- [x] 1.4 Host-only routes refuse the LAN — 1083431
- [x] 1.5 The Quit control's logic, through the node driver — 1083431
- [x] 1.6 The full suite passes — 1083431
- [x] 1.7 CI on the PR is green on both OSes — 1083431

#### Manual

- [x] 1.8 Windows venv with [window]: cast-tv opens a window on the UI — accepted at d2dd0cac9773909f62f3e10dbc7601369690a337
- [ ] 1.9 Fedora pipx with [window]: cast-tv opens a Qt window
- [ ] 1.10 Without the extra: tab as today, with a working Quit control
- [ ] 1.11 --no-window opens the tab
- [ ] 1.12 A forced fallback opens the tab with window_unavailable in Diagnostics
- [ ] 1.13 X with a video playing stops the TV and ends the process
- [ ] 1.14 Ctrl+C and kill stop the TV and close the window
- [ ] 1.15 A second launch brings the window to the front
- [ ] 1.16 The phone's UI is unchanged and has no Quit control

### Phase 2: The release carries the window

#### Automated

- [ ] 2.1 Lint passes
- [ ] 2.2 version_text and --window-check are covered
- [ ] 2.3 The full suite passes
- [ ] 2.4 The release workflow on the PR builds and smoke-tests both files with the window check
- [ ] 2.5 A local Windows build passes the smoke test

#### Manual

- [ ] 2.6 Windows: the PR exe opens the window; size and start time recorded
- [ ] 2.7 Fedora: the PR Linux binary opens a Qt window with the GPU on; size and start time recorded
- [ ] 2.8 Fedora: a HEIC photo cast through the window shows upright
- [ ] 2.9 Ubuntu 24.04 VM: the Linux binary opens its window, or why not

### Phase 3: The console's information moves into the window, and the console hides

#### Automated

- [ ] 3.1 The static files include qrcode.js and nothing else new
- [ ] 3.2 Phone panel and firewall banner logic
- [ ] 3.3 show_console is covered
- [ ] 3.4 The full suite passes
- [ ] 3.5 The release workflow on the PR is green

#### Manual

- [ ] 3.6 Windows window: the phone panel's QR opens the UI on the phone
- [ ] 3.7 The phone shows no phone panel and no Quit control
- [ ] 3.8 Offline: the panel says there is no network address
- [ ] 3.9 Fedora: the phone panel and QR codes work in the Qt window
- [ ] 3.10 Windows double-click: only the window, closing it stops the TV
- [ ] 3.11 Windows from PowerShell: output there, window opens, Ctrl+C stops both
- [ ] 3.12 A fallback with a hidden console shows the console again

### Phase 4: Icon and menu entry

#### Automated

- [ ] 4.1 Desktop entry and .lnk tests
- [ ] 4.2 favicon serves the PNG and /api/shortcut is host-only
- [ ] 4.3 The full suite passes
- [ ] 4.4 The release workflow on the PR is green

#### Manual

- [ ] 4.5 Windows: the icon on the exe, the window and the taskbar
- [ ] 4.6 Fedora: the window's taskbar entry shows the cast-tv icon
- [ ] 4.7 Fedora: Add to menu, found in the overview, starts with no terminal
- [ ] 4.8 Windows: Add to Start menu, starts with no console, pinning works
- [ ] 4.9 A moved file: Update menu entry repoints the entry
- [ ] 4.10 Remove from menu removes the entry on both machines
