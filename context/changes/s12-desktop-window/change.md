---
change_id: s12-desktop-window
title: "Run cast-tv as a desktop window on Windows and Linux"
status: implementing
created: 2026-10-15
updated: 2026-11-05
archived_at: null
---

## Notes

Run cast-tv as a desktop window on Windows and Linux (roadmap S-12)

2026-10-18: owner decision — the window engine is checked in pywebview's events.initialized(renderer) and a wrong one cancels the window before it shows (not func + destroy after shown); plan.md Critical Implementation Details — Debug & observability, Testing Strategy — Unit Tests
2026-10-18: owner decision — Phase 1 Manual rows 1.8-1.12 and 1.16 get explicit "— surface:" lists (the fallback surface could not parse the Files lines); plan.md Phase 1 — Manual Verification
2026-10-18: PR #61 was merged by rebase: a33a8a0 is 1083431 on main (Progress 1.1-1.7 rewritten); the bookkeeping commit d2dd0ca was rebased to 894aa80, so 1.8 (accepted at d2dd0cac9773909f62f3e10dbc7601369690a337) is unverifiable until re-confirmed
2026-10-18: re-confirmed 1.8 — was accepted at d2dd0cac9773909f62f3e10dbc7601369690a337; accepted at ffa982c46ad1f1bd5ea9b81a9283f941dac2690b
2026-10-18: reopened 1.8, 1.11, 1.13, 1.15 — was accepted at ffa982c46ad1f1bd5ea9b81a9283f941dac2690b; changed: castlib/cli.py, castlib/window.py (F1 startup termination fix)
2026-10-26: reopened 1.8, 1.11, 1.13, 1.15 — was accepted at 104dd710afda592c1e16666eec224c232e2a2479; changed: castlib/cli.py (Phase 2: the --version window line and --window-check)
2026-10-26: reopened 1.9, 1.10, 1.12 — was accepted at f04dfcb7fd9105f6a570c29579c1b34240fb5b74; changed: castlib/cli.py (Phase 2: the --version window line and --window-check)
2026-10-26: owner decision — Phase 2 Manual rows 2.6-2.9 get explicit "— surface:" lists (the fallback surface could not parse `.github/workflows/release.yml:26-44`); plan.md Phase 2 — Manual Verification
2026-10-26: PR #80 was squash-merged as 7eb63db (c4be482 and 9c85a46 in one commit; Progress 2.1-2.5 rewritten); row 2.6 accepted at 7eb63db, whose code is the tree the PR run's exe was built from
2026-10-26: re-confirmed 2.6 — was accepted at 7eb63dbbd1faf0303914b0a008356097a0a327ae; accepted at 70d37b737dc4e4124e1d66eba984f227bb290a27 (release.yml changed by ci-actions-node24; exe from run 40398550351)
2026-10-27: reopened 1.14 — was accepted at f04dfcb7fd9105f6a570c29579c1b34240fb5b74; changed: castlib/platform.py (Phase 3: show_console, the startup error box)
2026-10-27: reopened 1.16 — was accepted at ffa982c46ad1f1bd5ea9b81a9283f941dac2690b; changed: castlib/server.py, castlib/ui/app.js, castlib/ui/index.html (Phase 3: the phone panel, the firewall banner, qrcode.js)
2026-10-27: reopened 2.6, 2.7, 2.9 — were accepted at 70d37b737dc4e4124e1d66eba984f227bb290a27 (2.6) and 1239dcb5b8e77e1c992512ef56028a23c5345e51 (2.7, 2.9); changed: castlib/cli.py, packaging/cast-tv.spec (Phase 3: hide-early, the startup error path, Ctrl+C ignored after the window closed)
2026-10-27: reopened 2.8 — was accepted at 1239dcb5b8e77e1c992512ef56028a23c5345e51; changed: packaging/cast-tv.spec (Phase 3: hide-early)
2026-10-27: owner decision — Phase 3 Manual rows 3.6-3.12 get explicit "— surface:" lists (the fallback surface could not parse `castlib/server.py:33-37`); plan.md Phase 3 — Manual Verification
2026-10-27: owner decision — the icon design is the approved draft in icon/make_icon.py (amber TV with the cast mark on a dark rounded square); plan.md Phase 4 — 1. The icon
2026-10-28: owner decision — row 3.8's finding (Windows keeps a disconnected adapter's address as Deprecated, and the phone panel listed it) is fixed on PR #89: the address list and discovery skip IPv4 addresses that are not Preferred (castlib/discovery.py stale_addresses, castlib/app.py); rows 3.6 and 3.8 get castlib/app.py and castlib/discovery.py in their surfaces. 3.9 stays accepted: off Windows nothing is stale, so the Linux list is unchanged (test_stale_addresses_only_on_windows)
2026-10-28: owner decision — row 3.12's side finding is fixed on PR #89: the console prints "Close the window or press Ctrl+C" only once the window is shown (window.run's on_shown), so a fallback prints only "No cast-tv window ...; Ctrl+C ends it" (castlib/cli.py, castlib/window.py, castlib/app.py). No accepted row's surface is newly touched: 1.8-1.16 and 2.6-2.9 are already reopened, 3.9 lists only the UI and server files
2026-11-04: owner decision — row 3.10's finding (on Windows 11's default terminal a double-click opens the console in Windows Terminal, and hide-early cannot hide that window) is fixed on PR #89: the release, double-clicked into a Windows Terminal console, starts a copy of itself without a console and exits (castlib/platform.py leave_terminal_tab, castlib/cli.py). The copy gets a new console on a fallback and a message box on a startup failure. Rows 3.10-3.12 run again on the new exe; 3.6 and 3.7 do not list castlib/cli.py or castlib/platform.py and stay accepted
2026-11-05: PR #89 was merged by rebase (main 46d5d76): every PR commit has a new SHA with the same tree; Progress 3.1-3.12, research.md and temp_steps.md rewritten (8f75b06 -> 46d5d76, 7415a17 -> d607d09, efac3c5 -> 05508af, ...). Rows 3.6 and 3.7 were accepted at the branch's merge commit 2bab65f, which has no counterpart on main; its tree is 55a1e9b's, so they are accepted at 55a1e9b. 3.9's efac3c5 and 05508af differ only in .ai-toolkit/config.json and README.md (the ai-toolkit pins)
2026-11-05: reopened 3.6, 3.7 — was accepted at 55a1e9b; changed: castlib/api.py, castlib/app.py, castlib/server.py, castlib/ui/app.js, castlib/ui/index.html (Phase 4: the menu entry, the favicon)
2026-11-05: reopened 3.8 — was accepted at d607d09; changed: castlib/api.py, castlib/app.py, castlib/server.py, castlib/ui/app.js, castlib/ui/index.html (Phase 4)
2026-11-05: reopened 3.9 — was accepted at 05508af6cee36a67c599bd9328b1878089d63bf9; changed: castlib/api.py, castlib/server.py, castlib/ui/app.js, castlib/ui/index.html (Phase 4)
2026-11-05: reopened 3.10, 3.11, 3.12 — was accepted at d607d09; changed: castlib/window.py, packaging/cast-tv.spec (Phase 4: the window's icon, the exe's icon). 3.6-3.8 and 3.10-3.12 carried short SHAs, which the acceptance script reports unverifiable; git diff from those commits shows their surfaces changed, so they are reopened with 3.9 and confirmed again in temp_steps step 15a
2026-11-05: owner decision — Phase 4 Manual rows 4.5-4.10 get explicit "— surface:" lists (the Files lines, e.g. castlib/server.py:33-37,195-199, cannot be parsed); plan.md Phase 4 — Manual Verification
2026-11-05: PR #97 was merged by rebase (main d8b7ee4): every PR commit has a new SHA whose tree differs from the branch's only in context/foundation/roadmap.md (S-16, a978a30, on main first); Progress 4.1-4.10, research.md and temp_steps.md rewritten (c4ce4e1 -> 89735ba, 1a281a2 -> 134266b, fa0071f -> c4a4e5a, 2d032a3 -> 9376efd, 204e31b -> f971be5, ...)
