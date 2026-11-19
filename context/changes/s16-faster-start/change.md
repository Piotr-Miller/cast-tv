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
2026-11-19: reopened 1.7 — was accepted at 185f2062837a293ab9b02b5dfbd00ed4d1cd21d6; changed: castlib/bundle.py, castlib/platform.py, castlib/shortcut.py, castlib/window.py (Phase 2: code that runs under either packager).

2026-11-19: Phase 2 implementation review saved in reviews/impl-review-phase-2-8278f85.md. F1–F2 fixed in the working tree (Nuitka data/cache directory and import-time launch-path resolution); pyflakes clean, 617 tests passed and 7 skipped. No Manual acceptance recorded; fixes and review records carried, uncommitted.

2026-11-19: Phase 3 implementation review saved in reviews/impl-review-phase-3-ed90da9.md. F1–F2 fixed using the owner's authorized recommended approaches: fail closed on unreadable cache metadata and refresh retention/process evidence before each deletion. Full suite: 648 passed, 7 skipped; pyflakes clean. Manual acceptance remains pending; phase review leaves status implementing. Review records and fixes are carried, uncommitted; the existing plan SHA write-back is preserved.
