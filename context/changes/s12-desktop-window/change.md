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
