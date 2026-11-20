# Implementation review fixes

## Phase 2 — 2026-11-19

Source: ../reviews/impl-review-phase-2-8278f85.md. Owner authorized all recommended fixes in the review session.

- F1 applied: derive Nuitka data/cache locations from the main module's __file__; distinguish launcher and unpack directories in bundle and platform fixtures.
- F2 applied: anchor relative/empty PATH entries to the startup directory; capture the default launch-path result at import while retaining injected lookups; regress changed-CWD and immutable launch identity cases.
- Focused gates: 154 passed, 1 skipped; pyflakes clean. Final full suite: 617 passed, 7 skipped (exit 0); details in the review report.
- All Manual rows remain pending; no acceptance was recorded.
- The review skill leaves these fixes and records uncommitted. Include the carried files in the next implementation commit before claiming a new accepted revision.
