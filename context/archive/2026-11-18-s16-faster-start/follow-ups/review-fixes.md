# Implementation review fixes

## Phase 2 — 2026-11-19

Source: ../reviews/impl-review-phase-2-8278f85.md. Owner authorized all recommended fixes in the review session.

- F1 applied: derive Nuitka data/cache locations from the main module's __file__; distinguish launcher and unpack directories in bundle and platform fixtures.
- F2 applied: anchor relative/empty PATH entries to the startup directory; capture the default launch-path result at import while retaining injected lookups; regress changed-CWD and immutable launch identity cases.
- Focused gates: 154 passed, 1 skipped; pyflakes clean. Final full suite: 617 passed, 7 skipped (exit 0); details in the review report.
- All Manual rows remain pending; no acceptance was recorded.
- The review skill leaves these fixes and records uncommitted. Include the carried files in the next implementation commit before claiming a new accepted revision.

## Phase 6 — 2026-11-22

The owner chose Fix now for F1 in [the Phase 6 review](../reviews/impl-review-phase-6-fe88a52.md).

- Changed the README install text, storage table and Limitations to describe one cache folder per build and cleanup after the desktop window opens, subject to the safety checks.
- `git diff --check` passed. The shared acceptance script exited 0 and marked 7.13 stale due to README.md. Row 7.13 was reopened, with its earlier observations preserved in research.md. Row 6.4 remains current.
- The changes are uncommitted. Reconfirm 7.13 at the committed revision through `$rune-implement s16-faster-start`, using the recorded Windows and Fedora measurements if they still apply.
