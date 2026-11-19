---
change_id: s16-faster-start
title: "A faster-starting release file (Nuitka, cached onefile)"
status: implementing
created: 2026-11-18
updated: 2026-11-19
archived_at: null
---

## Notes

2026-11-19: reopened 1.7 — was accepted at fc780beb1660330a543a6c0bf9fd41036f840f2c; changed: castlib/processes.py, castlib/ui/app.js, packaging/startup_time.py (implementation-review fixes F1–F4). The previous observation remains in research.md; acceptance needs a committed revision and a new watched run.

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->
2026-11-19: owner decision — Windows: an access-denied image query counts as not ours unless WTS names our SID (unelevated, 176 of 451 owners unknown made every listing incomplete); verified with a normal and an elevated cast-tv; plan.md Phase 1, The process lister
