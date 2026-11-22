---
change_id: s16-faster-start
title: "A faster-starting release file (Nuitka, cached onefile)"
status: archived
outcome: completed
created: 2026-11-18
updated: 2026-11-22
archived_at: 2026-11-22T20:31:34Z
---

## Notes

2026-11-19: reopened 1.7 — was accepted at 894b53ee099cf19b0903d46ddb7682db943f9695; changed: castlib/processes.py, castlib/ui/app.js, packaging/startup_time.py (implementation-review fixes F1–F4). The previous observation remains in research.md; acceptance needs a committed revision and a new watched run.

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->
2026-11-19: owner decision — Windows: an access-denied image query counts as not ours unless WTS names our SID (unelevated, 176 of 451 owners unknown made every listing incomplete); verified with a normal and an elevated cast-tv; plan.md Phase 1, The process lister
2026-11-19: reopened 1.7 — was accepted at 841d889deb84713fc389fe90e1724c027374a218; changed: castlib/bundle.py, castlib/platform.py, castlib/shortcut.py, castlib/window.py (Phase 2: code that runs under either packager).

2026-11-19: Phase 2 implementation review saved in reviews/impl-review-phase-2-8278f85.md. F1–F2 fixed in the working tree (Nuitka data/cache directory and import-time launch-path resolution); pyflakes clean, 617 tests passed and 7 skipped. No Manual acceptance recorded; fixes and review records carried, uncommitted.

2026-11-19: Phase 3 implementation review saved in reviews/impl-review-phase-3-ed90da9.md. F1–F2 fixed using the owner's authorized recommended approaches: fail closed on unreadable cache metadata and refresh retention/process evidence before each deletion. Full suite: 648 passed, 7 skipped; pyflakes clean. Manual acceptance remains pending; phase review leaves status implementing. Review records and fixes are carried, uncommitted; the existing plan SHA write-back is preserved.
2026-11-19: Phase 4 implemented: 8297237 (build_nuitka.py, Cache: line, smoke --nuitka, four-file release.yml) and 658da78 (fix: Windows gave the Nuitka cache folder as an 8.3 short path, C:\Users\RUNNER~1\...\050-GH~1.1, so smoke and pruning failed; bundle.data_dir now expands it with GetLongPathNameW). PR #111 (draft): release run 44628255344 failed on that; run 44630376210 at 658da78 built and smoke-tested all four files green (Nuitka: Linux 154,814,680 B, Windows 18,300,416 B; cache folders 0.5.0-gh44630376210.1), test run 44630376203 green. Phase 5 measures that run's files.

2026-11-20: Phase 4 implementation review APPROVED at 658da78, no findings; report reviews/impl-review-phase-4-7a7eb32.md. Focused phase checks and pyflakes passed in a detached checkout. Existing four-file CI build/smoke results, artifacts and both Nuitka provenance sidecars verified without running a paid build. Phase review leaves status implementing and Manual acceptance pending.

2026-11-20: rows 5.2, 5.4 and 5.6 accepted at 06a16b9f6ae98b7a5509c9e9edc538e18ff76f35 (owner: "Potwierdzam"): Windows 11 cold 4.00 vs 4.05 s (0.988), warm 2.87 vs 3.95 s (0.727, limit 0.75), watched run ready after 2.98 s; research.md, "Phase 5 on Windows 11".
2026-11-20: owner decision — Linux: a refused `/proc/<pid>/exe` counts as not ours (our undumpable processes: systemd --user, sd-pam, kwin_wayland, the polkit agent, two ssh-agent, a zombie made every listing on the Fedora KDE desktop incomplete, so startup_time.py refused and pruning could never run); plan.md Phase 1, The process lister.
2026-11-20: reopened 5.2 — was accepted at 06a16b9f6ae98b7a5509c9e9edc538e18ff76f35; changed: castlib/processes.py (Linux: an undumpable process of ours is not cast-tv). The previous observation remains in research.md; acceptance needs a committed revision and the Windows files of a new release run, measured again or recorded as equivalent.
2026-11-20: reopened 5.6 — was accepted at 06a16b9f6ae98b7a5509c9e9edc538e18ff76f35; changed: castlib/processes.py (the same fix). The previous observation remains in research.md.
2026-11-20: owner decision — the Linux warm bar is 75 % of PyInstaller's, as on Windows (was 50 %; Fedora measured 0.706 on run 44812632302). Chosen from 0.72 / 0.75 / 0.80 for a margin like Windows's; plan.md, Decisions, The bar.

2026-11-20: rows 5.1, 5.3 and 5.5 accepted at 3d990ec6ccb0d8070d681cc0acf2c46559817e03 (owner: "potwierdzam"): Fedora cold 2.05 vs 3.24 s (0.633), warm 2.16 vs 3.05 s (0.706, limit 0.75 by the owner's decision after the 0.5 miss), watched run ready after 1.85 s; research.md, "Phase 5 on Fedora".
2026-11-20: owner decision — Phase 6 starts before Windows's 5.2 and 5.6 are measured again; Windows is measured once on Phase 6's PR files (dual boot); plan.md Phase 5, Implementation Note.
2026-11-20: reopened 5.5 — was accepted at 3d990ec6ccb0d8070d681cc0acf2c46559817e03; changed: .github/workflows/release.yml, packaging/build_nuitka.py, packaging/cast-tv.spec, packaging/smoke.py (Phase 6: the release switched to Nuitka).
2026-11-20: rows 5.1 and 5.5 accepted at 6d52911465ac4f0ba6a330cb62dda92eda558401 (owner: "potwierdzam 5.1 5.5"): Phase 6's Linux file is equal to the measured one apart from names; research.md, "Phase 6: the published files against the measured ones".
2026-11-20: owner decision — a manual row's "— surface:" line is joined to its bullet (no blank line before it; 6.4's written "— surface:"), so 5.1, 6.4, 7.1, 7.4, 7.6-7.8, 7.10 and 7.11 check their declared surface instead of the phase's File lines (5.1 had fallen back to research.md and went stale on every note); plan.md Phases 5-7, Manual Verification.
2026-11-20: owner decision — row 7.10 uses the PR's three existing Nuitka builds (runs 44630376210, 44812632302, 44821655658) instead of paid reruns; plan.md Phase 7, Manual Verification.
2026-11-20: reopened 5.1 — was accepted at 6d52911465ac4f0ba6a330cb62dda92eda558401; changed: surface declaration.
2026-11-20: rows 5.1, 7.7 and 7.8 accepted at 824a487da0f0b8c966d2ddcb5b5679b4b1af5657 (owner: "potwierdzam 5.1 7.7 7.8"): Fedora measurements; the menu entry added, started from Meta, updated after a move and removed; HEIC upright, OneDrive and Google Photos lists, no Fontconfig line; research.md, "Phase 7 on Fedora".
2026-11-21: owner decision — row 1.7 uses run 44812632302's PyInstaller exe (built at 9b1ced7, every castlib change of Phases 1-5), because Phase 6 deleted `packaging/cast-tv.spec`; its 5 warm runs are row 5.2's PyInstaller warm series of the same file; research.md, "Row 1.7 on run 44812632302".
2026-11-21: rows 1.7, 5.2, 5.6 and 6.4 accepted at 9ad76e4c2d822f984936a0e2521a33492ea3fcc3 (owner: "Wszytsko sie zgadza"): Windows 11 measured again on run 44812632302 (cold 0.828, warm 0.734), run 44821655658's exe equal to it apart from names, the PyInstaller watched run ready after 3.91 s; research.md, "Phase 5 on Windows 11 again" and "Row 1.7 on run 44812632302".
2026-11-22: owner decision — row 7.4's Windows sign-out is not repeated on the Nuitka file ("już raz sprawdzaliśmy to, wylogowanie przerywa film"; observed in S-12); X is covered by 7.1; research.md, "Phase 7 on Windows 11".
2026-11-22: rows 7.1-7.6 and 7.9-7.13 accepted at 878cc8f66700b5e13e7bc8b7e5b5be384adb2fb2 (owner: "potwierdzam 7.1-7.6 7.9-7.13"): Phase 7 on Windows 11 and on Fedora; research.md, "Phase 7 on Windows 11" and "Phase 7 on Fedora".
2026-11-22: reopened 7.13 — was accepted at 878cc8f66700b5e13e7bc8b7e5b5be384adb2fb2; changed: README.md (Phase 6 review F1).
2026-11-22: reopened 1.7 — was accepted at 9ad76e4c2d822f984936a0e2521a33492ea3fcc3; changed: surface declaration (the deleted `packaging/cast-tv.spec` removed, the owner decision of 2026-11-21 written into the Manual Verification text; Phase 6 review note).
2026-11-22: rows 1.7 and 7.13 accepted at f3fb96c7f79bd6830cda924ad98c7abf04f473fb (owner: "potwierdzam 1.7 7.13"): unchanged code under 1.7's corrected surface; the cache sizes against the rewritten README; research.md, "Rows 1.7 and 7.13 after the Phase 6 review".
2026-11-22: PR #111 was merged by rebase (main fc89537): its 53 commits have new SHAs with identical trees and subjects; plan.md Progress, research.md, change.md, the reviews and temp_steps.md rewritten; the review files keep their old names (fc780be -> 894b53e, 185f206 -> 841d889, 9dfd306 -> 8297237, 7a7eb32 -> 658da78, 67084d1 -> 06a16b9, 30cc688 -> 3d990ec, eff390b -> 6d52911, b863e34 -> 824a487, eed2a5b -> 9b1ced7, 27556cc -> 9ad76e4, 41e97ef -> 878cc8f, 4c2cfb7 -> f3fb96c, a558115 -> e0ad84a, 8278f85 -> dbb1b52, ed90da9 -> be8eef9, fe88a52 -> 93ca5b7, 5155ad8 -> 463c368, 99287e6 -> a6452ce, a32a0ea -> 37f8800, 3e67ec8 -> 920bff8, 3a63909 -> 21bb5a8, 0707dac -> 1e20a08, 7d33c1b -> 54c84ea, 962581c -> adb54e4, c213876 -> f7e1cfb, 5780933 -> b1384bf, 07fd85c -> 19067f7, 3ea3542 -> fb9d14b, 36329d6 -> 0e07cab, 5982c46 -> 5fa155c, 9217ad9 -> 549f923, b3bd7f4 -> b4c204f, 2d55047 -> 2c239ca, 78184a5 -> de15238)
