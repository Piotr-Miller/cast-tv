# A desktop window for cast-tv (S-12) — Plan Brief

> Full plan: `context/changes/s12-desktop-window/plan.md`
> Frame brief: `context/changes/s12-desktop-window/frame.md`
> Research: `context/changes/s12-desktop-window/research.md`

## What & Why

> On the host, cast-tv should be one thing you start, see, return to and close. Today that is
> split across a console that owns the TV session and the screen's information, a plain browser
> tab, and a file with no OS presence. Each of the three parts has its own cause, and only one
> of them is about how the UI is drawn.

The owner's three complaints are:

1. two things to keep track of (a console and a tab);
2. it looks like a web page;
3. no icon, and no way back except through the browser.

This plan answers all three. The phone keeps the web UI.

## Starting Point

The release is a console executable. The console is the only stop switch, and the only place
showing the phone's address and the "firewall blocks you" warning. The UI opens as a browser
tab; a second launch opens another tab, and there is no icon anywhere. Four spikes (2026-10-15
to 2026-10-18) measured the candidate windows on Fedora, five distributions, an Ubuntu 24.04
VM and the Windows laptop.

## Desired End State

- **Opening:** double-clicking the release file (Windows or Linux) opens one cast-tv window,
  with an icon, on the existing UI. On Windows the console is hidden.
- **What the window shows:** the phone's addresses with QR codes, and the firewall warning.
- **Closing:** closing the window stops the TV and ends the app.
- **Coming back:** clicking the file again brings the window forward, and a button adds cast-tv
  to the Linux menu or the Windows Start menu.
- **Unchanged:** the command line (`cast-tv film.mkv`) and the phone UI work as before.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Replace or wrap the UI | Wrap `/ui/`; the phone keeps the web UI | One UI for both; the phone flow is the north star | Frame |
| Windows engine | pywebview + WebView2 | Passed unfrozen and as a 12.8 MB onefile; WebView2 ships with Windows 11 | Research / Plan |
| Linux engine and scope | pywebview + Qt WebEngine, the whole Linux family | The only one-file candidate that rendered on 5/5 distributions and both real desktops, once the bundle drops its `libgbm` and `libstdc++` | Research / Plan |
| macOS | Stays a Non-Goal | No Mac to test on | Plan |
| OS presence | Icon, plus an "Add to menu" button the app runs itself; no installer | Fixes "starting and coming back" and keeps the PRD's no-installers rule | Plan |
| Closing the window | Ends cast-tv, stops the TV, no confirmation, no tray | One thing to keep track of; the same as closing the console today (#11) | Plan |
| The console | One file; hidden when the program owns it (double-click, menu), kept when launched from a terminal | The CLI keeps working from one download | Plan |
| The phone address | Every LAN address, each with Copy and its own QR; default route first | A VPN or Docker address can come first; the person picks | Plan |
| Second launch | Brings the running window forward | "Coming back" without a second tab | Plan |
| pipx dependency | Optional `cast-tv[window]`; the release always has it | The core install and CI stay without PySide6's ~600 MB | Plan |
| Engine check | The loaded renderer must be the expected one, or cast-tv falls back to the tab | pywebview falls back quietly; the 2026-10-18 run caught it | Research |

## Scope

**In scope:**

- the window and its lifetime (X, Ctrl+C, SIGTERM, console close, Quit);
- the second launch bringing the window forward;
- host-only API routes;
- the release builds on both OSes, with a real window check in CI;
- the phone panel with QR codes, and the firewall banner;
- hiding the owned console, and showing it again on fallback;
- the icon, the menu entry button, and the PRD, tech-stack and README updates.

**Out of scope:**

- macOS, installers, code signing, auto-update;
- a tray icon, and a confirmation on close;
- Electron, Tauri or Chromium `--app`;
- any change to the phone UI;
- the `v0.5.0` tag (the owner's call after Phase 4);
- the pre-existing flaky OneDrive test.

## Architecture / Approach

`castlib/window.py` wraps pywebview and is imported lazily. `cli.ui()` starts the app as
today, then runs the window on the main thread instead of `run_forever()`. When the GUI loop
ends, it calls the existing `interrupted()` + `close()`. Every other end destroys the window:
SIGTERM, console close and `/api/quit`. Windows log-off/shutdown uses a separate session-message
hook with a bounded, idempotent cleanup attempt; GUI loading prevents the console handler
from receiving those events. Host-only routes (`/api/window`, `/api/quit`,
`/api/shortcut`) answer loopback only. The UI learns from `status.host` and `status.window` which
panels to show. The release spec adds the backend per OS and filters two libraries on Linux.
The smoke test runs `--window-check` in the built file.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. The window owns the session | The window in a dev or pipx install; closing it stops the TV; Quit; second launch; PRD recorded | Signals reaching a main thread parked in the Qt or WinForms loop |
| 2. The release carries the window | Both release files open the window; CI proves the engine and renders `/ui/` | Qt WebEngine plus pillow-heif without the bundled `libstdc++`; WebView2 on the Windows runner; the Linux file's size and start time |
| 3. Console info into the window; console hidden | Phone panel with QR codes, firewall banner, hidden console, console back on fallback | An invisible process if the fallback misses a path |
| 4. Icon and menu entry | Icon everywhere; Add/Update/Remove menu entry on Linux and Windows | GNOME grouping (`desktopFileName`); the `.lnk` through PowerShell |

**Prerequisites:**

- Phase 1 merged before Phase 2 is built;
- the Windows laptop and the Fedora desktop for the manual rows;
- optionally the Ubuntu 24.04 VM from the 2026-10-16 spike.

**Estimated effort:** about 4-6 sessions: one or two per phase. Each phase has a round of
manual checks on both machines.

## Open Risks & Assumptions

- **The Linux release grows from about 36 MB to about 230-250 MB**, with a slower onefile
  start. If the start is over about 15 s on Fedora (row 2.7), the owner decides between onefile
  and a onedir archive before Phase 3.
- **Removing the bundled `libstdc++`** was proved only with the spike probe. pillow-heif in the
  real build is checked by the CI self-check and by row 2.8.
- **The Windows runner may lack the WebView2 runtime.** The workflow then installs it; it never
  skips the check.
- **The icon is a simple generated glyph** (`packaging/make_icon.py`). The owner can replace
  it later; this is an assumption, not asked.
- **The Qt exe without the VC++ runtime, and SmartScreen on a downloaded unsigned exe, stay
  unchecked** (`research.md`, 2026-10-18).

## Success Criteria (Summary)

- **Windows:** a double-click on the downloaded file shows only the cast-tv window. Closing it
  stops the TV, and a second click brings it back to the front.
- **Fedora:** cast-tv starts from the GNOME menu with its icon and no terminal, in a Qt window
  with the GPU on.
- **The phone:** it opens the UI by scanning a QR code in the window. `cast-tv film.mkv` in a
  terminal works as before.
