# Implementation review fixes

## F1 — Retain termination during window startup

- Report: reviews/impl-review-phase-1-1083431.md
- Owner selected Fix now on 2026-10-18.
- Applied on branch fix/s12-phase1-f1; uncommitted, for the next rune-implement commit.
- The CLI enters a termination scope before installing handlers. Direct run() uses the same scope before backend imports. Early requests beat fallback, and every scope exit clears the state.
- Sibling paths checked: SIGTERM, console close, session end and App.quit all route to window.destroy; the shared scope covers their hook-setup/import interval. Direct run() has its own scope; tab-mode handlers retain the existing KeyboardInterrupt behavior.
- Tests cover successful/failing backend import with SIGTERM, all three hook-setup end sources, direct-run state reuse after failure, and hook-registration exceptions. Existing readiness tests cover native destroy after shown.
- Reopened manual rows: 1.8, 1.11, 1.13, 1.15. The acceptance script identified edits to castlib/cli.py and castlib/window.py in those rows' surfaces; 1.16 remains current.
- Verification: pyflakes exit 0; focused window/CLI/platform tests exit 0 (89 passed, 2 skipped). Full suite exit 1 (2 failed, 425 passed, 5 skipped): the pre-existing CLI App.current race and known OneDrive timeout from F3. No fix for either test was applied during F1 triage.

## F2 — Carry the session-end deadline through cleanup

- Report: reviews/impl-review-phase-1-1083431.md
- Owner selected Fix now on 2026-10-18. Applied on the same uncommitted branch as F1.
- SessionEnd supplies its original absolute monotonic deadline. App.shutdown can shorten an in-flight ordinary shutdown; Stop gets half the remaining time, followed by per-operation cleanup shares. Stalled external calls are isolated on daemon workers so the remaining operations are attempted. Normal shutdown without a deadline still waits for completion.
- Siblings: GUI return and Quit already use the coordinator; the UI and tab Ctrl+C paths now join it too. Close has a separate once-only claim so competing close calls do not duplicate cleanup. Sources and both server shutdown/socket close calls have independent attempts.
- Tests: 36 window tests pass, including blocked Stop plus blocked source, prior ordinary Quit, repeated session end, fake-clock absolute deadline and GUI/tab interrupt races. Earlier focused aggregate has only F3's existing CLI App.current failure (111 passed, 2 skipped).
- Acceptance script exit 0: 1.8–1.15 pending, 1.16 current. No additional rows reopened. A fresh real Windows sign-out remains part of pending 1.14.
- Final verification: pyflakes exit 0, 36 window tests pass; full suite exit 0, 431 passed and 5 skipped in 110.20s, with no test deselection. F3 now has passing-run evidence for triage. Preserve the earlier failed runs in the review.

## F3 — Resolve the local verification gap

- Owner selected Fix now on 2026-10-18 after the passing F2 full-suite run.
- Resolved using existing evidence: pyflakes exit 0; full suite exit 0, 431 passed and 5 skipped in 110.20s. No additional source/test edits or rerun were required for this decision.
- Both intermittently failing tests were included. Earlier failed-run evidence remains in the report; stabilization is tracked separately in test-stabilization.md and is not part of these fixes.
- All three review findings are now FIXED. Changes remain uncommitted for rune-implement; manual rows remain pending as recorded in plan.md.
