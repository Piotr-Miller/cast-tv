---
change_id: s12-desktop-window
title: "Run cast-tv as a desktop window on Windows and Linux"
status: implementing
created: 2026-10-15
updated: 2026-10-28
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
