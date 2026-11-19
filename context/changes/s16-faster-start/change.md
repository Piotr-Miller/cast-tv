---
change_id: s16-faster-start
title: "A faster-starting release file (Nuitka, cached onefile)"
status: implementing
created: 2026-11-18
updated: 2026-11-20
archived_at: null
---

## Notes

2026-11-19: reopened 1.7 — was accepted at fc780beb1660330a543a6c0bf9fd41036f840f2c; changed: castlib/processes.py, castlib/ui/app.js, packaging/startup_time.py (implementation-review fixes F1–F4). The previous observation remains in research.md; acceptance needs a committed revision and a new watched run.

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->
2026-11-19: owner decision — Windows: an access-denied image query counts as not ours unless WTS names our SID (unelevated, 176 of 451 owners unknown made every listing incomplete); verified with a normal and an elevated cast-tv; plan.md Phase 1, The process lister
2026-11-19: reopened 1.7 — was accepted at 185f2062837a293ab9b02b5dfbd00ed4d1cd21d6; changed: castlib/bundle.py, castlib/platform.py, castlib/shortcut.py, castlib/window.py (Phase 2: code that runs under either packager).

2026-11-19: Phase 2 implementation review saved in reviews/impl-review-phase-2-8278f85.md. F1–F2 fixed in the working tree (Nuitka data/cache directory and import-time launch-path resolution); pyflakes clean, 617 tests passed and 7 skipped. No Manual acceptance recorded; fixes and review records carried, uncommitted.

2026-11-19: Phase 3 implementation review saved in reviews/impl-review-phase-3-ed90da9.md. F1–F2 fixed using the owner's authorized recommended approaches: fail closed on unreadable cache metadata and refresh retention/process evidence before each deletion. Full suite: 648 passed, 7 skipped; pyflakes clean. Manual acceptance remains pending; phase review leaves status implementing. Review records and fixes are carried, uncommitted; the existing plan SHA write-back is preserved.
2026-11-19: Phase 4 implemented: 9dfd306 (build_nuitka.py, Cache: line, smoke --nuitka, four-file release.yml) and 7a7eb32 (fix: Windows gave the Nuitka cache folder as an 8.3 short path, C:\Users\RUNNER~1\...\050-GH~1.1, so smoke and pruning failed; bundle.data_dir now expands it with GetLongPathNameW). PR #111 (draft): release run 44628255344 failed on that; run 44630376210 at 7a7eb32 built and smoke-tested all four files green (Nuitka: Linux 154,814,680 B, Windows 18,300,416 B; cache folders 0.5.0-gh44630376210.1), test run 44630376203 green. Phase 5 measures that run's files.

2026-11-20: Phase 4 implementation review APPROVED at 7a7eb32, no findings; report reviews/impl-review-phase-4-7a7eb32.md. Focused phase checks and pyflakes passed in a detached checkout. Existing four-file CI build/smoke results, artifacts and both Nuitka provenance sidecars verified without running a paid build. Phase review leaves status implementing and Manual acceptance pending.

2026-11-20: rows 5.2, 5.4 and 5.6 accepted at 67084d10952c3d4e7f3902d6ececac8e367d1488 (owner: "Potwierdzam"): Windows 11 cold 4.00 vs 4.05 s (0.988), warm 2.87 vs 3.95 s (0.727, limit 0.75), watched run ready after 2.98 s; research.md, "Phase 5 on Windows 11".
