<!-- PLAN-REVIEW-REPORT -->
# Plan Review: A desktop window for cast-tv (S-12)

- **Plan**: context/changes/s12-desktop-window/plan.md
- **Mode**: Deep
- **Date**: 2026-10-18
- **Plan sha256**: 7f62beb043ced08500e4bf1af1f4e4f218ee6150cf0529c84e5f456b02f75231
- **Plan sha256 after triage**: 9308386f3c44ffc504cf0f1632e07e670015beae1c3f11ef209a4a76a0c941b7
- **Verdict**: REVISE
- **Findings**: 0 critical, 5 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Requirement Definition | PASS |
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | WARNING |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

## Grounding

34 paths checked: 26 exist, 8 intentionally new with existing parents. Brief and plan agree. All four phase names and all 47 criteria match Progress; one Progress heading and no body checkboxes. Read 6/6 lessons; 4 apply to the change (manual observations, session branch check, precise human steps, action-owned UI messages). Nine unique recorded commands were attempted; none could execute lint/tests because available Python environments lack pytest/pyflakes. Exit 1 for the full suite is therefore not confirmation of the recorded flaky-test result. No build or external command was run.

Definitions: seven terms traced to the request/product decisions; no blocking ambiguity found. Address walkthrough: default-route plus alternate interface, duplicate alternate address, and localhost-only input follow App.start's order/deduplication and the plan's empty-panel rule (castlib/app.py:221-234). This relies on the current startup snapshot, not live network monitoring. Read-only delegated verification covered lifecycle, signals, second launch and affected callers. No contract-surfaces file exists.

## Findings

### F1 — Window mode suppresses Google Photos consent browser

- **Severity**: WARNING
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: End-State Alignment
- **Location**: Phase 1 — CLI and app lifecycle
- **Detail**: ui() is planned to call App.start(browser=False) to suppress the UI tab. App.start also assigns that argument to gphotos.open_browser (castlib/app.py:218), which is passed to loopback.start at castlib/sources/gphotos.py:298,331. loopback.start skips opening consent when false (castlib/auth/loopback.py:242-244). Merely selecting the native window therefore changes Google Photos connection behavior.
- **Fix**: Separate opening the main UI from OAuth consent browser policy. Test that normal window mode opens consent and explicit --no-browser suppresses it.
- **Decision**: FIXED — Fix; edited: Phase 1 — The CLI and the app lifecycle, Phase 1 — Automated Verification, Testing Strategy — Unit Tests; reopened: none (acceptance-state.sh exit 0; all Manual rows pending)

### F2 — Destroy during startup can block the main thread

- **Severity**: WARNING
- **Impact**: MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details; Phase 1
- **Detail**: The plan directs SIGTERM to window.destroy even during startup. In inspected pywebview 6.2.1, Window.destroy uses _shown_call (webview/window.py:342-347), which waits up to 20 seconds for shown (:39-44). A signal on the main thread before the native window appears blocks the thread needed to complete startup. The plan also incorrectly describes start(func) as a GUI-thread callback after GUI initialization: webview/__init__.py:294-303 starts a separate Python thread before guilib.create_window.
- **Fix**: Record pending termination before GUI readiness; destroy after readiness, handle failed initialization, and test termination between create_window and shown. Correct the callback-thread description.
  - Strength: Avoids blocking startup and fulfills the early-close guarantee.
  - Tradeoff: Explicit startup/readiness state is needed.
  - Confidence: HIGH — grounded in inspected local dependency source.
  - Blind spot: Initialization failure needs its own test.
- **Decision**: FIXED — Fix; edited: Critical Implementation Details — Timing & lifecycle, Critical Implementation Details — Debug & observability, Phase 1 — The window module, Phase 1 — Automated Verification, Testing Strategy — Unit Tests; reopened: none (acceptance-state.sh exit 0; all Manual rows pending)

### F3 — Console handler does not cover Windows session end after GUI loads

- **Severity**: WARNING
- **Impact**: MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Definitions — Closing the window; Phase 1
- **Detail**: The plan routes log-off/shutdown through ConsoleClose. WinForms loads user32, after which Windows does not deliver CTRL_LOGOFF_EVENT/CTRL_SHUTDOWN_EVENT to SetConsoleCtrlHandler. No explicit GUI session-end handling or real session-end test backs the promise. Microsoft documents using window messages instead: https://learn.microsoft.com/en-us/windows/console/registering-a-control-handler-function
- **Fix**: Specify Windows window/session-end handling and bounded Stop/cleanup, with a test and a real laptop session-end check.
  - Strength: Covers the promised path the console handler cannot receive.
  - Tradeoff: Windows backend integration is needed.
  - Confidence: HIGH — documented OS limitation; local WinForms uses user32.
  - Blind spot: Real log-off requires manual validation.
- **Decision**: FIXED — Fix; edited: Critical Implementation Details — Timing & lifecycle, Critical Implementation Details — Windows session end, Phase 1 — The CLI and the app lifecycle, Phase 1 — Automated Verification, Phase 1 — Manual Verification (1.14), Testing Strategy — Unit Tests, plan-brief.md — Architecture / Approach; reopened: none (acceptance-state.sh exit 0; all Manual rows pending)

### F4 — Non-frozen shortcuts lack packaged icon and checkout working directory

- **Severity**: WARNING
- **Impact**: MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architectural Fitness
- **Location**: Phase 4 — Menu entry
- **Detail**: The pipx shortcut copies an .ico, but the plan creates it under packaging/ while pyproject.toml packages only castlib/ui/*; pipx will lack the source icon. The checkout command [sys.executable, -m, castlib] has no working-directory contract, so a menu launch outside the checkout may not find castlib.
- **Fix**: Package the .ico as a runtime resource, and give checkout shortcuts an explicit working directory or installed launcher. Verify launch outside the repository.
  - Strength: Makes declared installation variants self-contained and launchable.
  - Tradeoff: Adds a package resource and launch test.
  - Confidence: HIGH — follows current package-data configuration and Python module resolution.
  - Blind spot: Taskbar pinning still needs manual validation.
- **Decision**: FIXED — Fix; edited: Phase 4 — The icon, Phase 4 — The window's identity, Phase 4 — The menu entry, Phase 4 — Automated Verification, Phase 4 — Manual Verification (4.7, 4.8), Testing Strategy — Unit Tests; reopened: none (acceptance-state.sh exit 0; all Manual rows pending)

### F5 — Hidden console swallows errors before window startup

- **Severity**: WARNING
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 3 — Hide the owned console
- **Detail**: show_console is called only after window.run returns unavailable. Earlier startup errors, such as a port occupied by another application, print and exit in ui() before a native window exists (castlib/cli.py:276-278). With hide-early, double-click users receive no visible error.
- **Fix**: Specify visible reporting for failures before GUI startup, including a double-click test with the port occupied. A restored console must remain readable or use an error dialog.
- **Decision**: FIXED — Fix; edited: Phase 3 — Hide the owned console, Phase 3 — Automated Verification, Phase 3 — Manual Verification (3.12), Testing Strategy — Unit Tests; reopened: none (acceptance-state.sh exit 0; all Manual rows pending)

### F6 — Recorded verification results cannot be reproduced in the current environment

- **Severity**: OBSERVATION
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Automated Verification
- **Detail**: All nine unique recorded local commands were attempted. Python reports missing pytest/pyflakes; the pipx and spike interpreters also lack them. This is an environment limitation, not evidence of an application regression or confirmation of the recorded test results.
- **Fix**: Document the test interpreter/environment setup and rerun the recorded commands there.
- **Decision**: FIXED — Fix; edited: Testing Strategy — Verification Environment, What We're NOT Doing — historical flaky-test note, research.md — Plan-review triage: verification environment (2026-10-18); reopened: none (acceptance-state.sh exit 0; all Manual rows pending)

## Triage summary (2026-10-18)

- **Fixed**: F1, F2, F3, F4, F5, F6.
- **Skipped / Accepted / Dismissed**: none.
- **Verdict after fixes**: SOUND — all six findings addressed in the plan; this records triage completion, not implementation or manual acceptance.
- **Verification**: isolated `.venv` created with `.[test]`; all nine commands exit 0. Full suite: 382 passed, 5 skipped. Earlier OneDrive failure not reproduced. Persistent results and versions are in research.md.
- **Progress**: unchanged; four matching phase names, 47 mapped criteria, all Manual rows pending. No acceptance rows reopened.
- **Implementation**: no application source changes, no build/release and no commit.
