---
change_id: s12-desktop-window
title: "Run cast-tv as a desktop window on Windows and Linux"
status: implementing
created: 2026-10-15
updated: 2026-10-18
archived_at: null
---

## Notes

Run cast-tv as a desktop window on Windows and Linux (roadmap S-12)

2026-10-18: owner decision — the window engine is checked in pywebview's events.initialized(renderer) and a wrong one cancels the window before it shows (not func + destroy after shown); plan.md Critical Implementation Details — Debug & observability, Testing Strategy — Unit Tests
2026-10-18: owner decision — Phase 1 Manual rows 1.8-1.12 and 1.16 get explicit "— surface:" lists (the fallback surface could not parse the Files lines); plan.md Phase 1 — Manual Verification
2026-10-18: PR #61 was merged by rebase: a33a8a0 is 1083431 on main (Progress 1.1-1.7 rewritten); the bookkeeping commit d2dd0ca was rebased to 894aa80, so 1.8 (accepted at d2dd0cac9773909f62f3e10dbc7601369690a337) is unverifiable until re-confirmed
2026-10-18: re-confirmed 1.8 — was accepted at d2dd0cac9773909f62f3e10dbc7601369690a337; accepted at ffa982c46ad1f1bd5ea9b81a9283f941dac2690b
