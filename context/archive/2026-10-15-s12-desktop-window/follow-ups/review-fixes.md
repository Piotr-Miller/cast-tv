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

## Phases 2–4 review fixes (2026-11-17)

The owner approved all recommended fixes in session on 2026-11-16. Verification completed
2026-11-17 on branch `s12-review-fixes`. See `../reviews/impl-review-phase-2-4-ee74c2c.md`.

| Finding | Disposition |
| --- | --- |
| F1 startup cleanup | Applied; construction/serve failures and invalid TV after serving covered; cancellation and second launch preserved |
| F2 smoke ownership | Applied; per-run port, loopback identity, same TCP connection for recheck and conditional Quit, owned-tree fallback |
| F3 launcher layout | Applied; separate host-panel/launcher classes, including the sign-in-help sibling collision |
| F4 shortcut freshness | Applied; background refresh and obsolete-read protection for install/remove |
| F5 URL wrapping | Applied to source errors and sibling diagnostic/action-message containers |
| F6 repeated shown | Applied; callback runs once across repeated shown events |
| F7 Fontconfig | Applied; private rules bundled and selected before Qt; standard installed fonts and explicit overrides retained; A/B diagnostics 45 to zero |
| F8 stale acceptance | Applied by reopening affected rows, without substituting automated checks for human confirmation |

### Verification

- Windows full suite: 524 passed, 5 skipped, exit 0, isolated test-only venv with the earlier
  repository dependency versions. A current-dependency run reproduced the known OneDrive
  account timeout; that excluded test was not changed, and no dependency cause is established.
- Linux full suite: 525 passed, 4 skipped, exit 0, WSL Ubuntu 26.04, test-only venv and Node.
- One final malformed-JSON guard and regression case followed those full runs; all 11 smoke
  regression tests then passed on both OSes, and both binaries passed the final smoke script.
- Pyflakes, JavaScript syntax, whitespace checks, and Chrome layout at 1180 px / 420 px pass.
- Fresh Windows/Linux builds pass HEIC decoding, HTTP serving, owned shutdown and expected
  window engines. Local build credentials are synthetic and settings/cache paths isolated.
- The old release's parser is Fontconfig 2.13.1. Upstream 2.18.3 rules reproduce exactly 45
  diagnostics; private configuration removes them while qtwebengine still renders.
- Logs and scratch artifacts: `.git/rune/s12-fixes/`.

### Still required

1. Commit source, tests, packaging changes and workflow records together, including reopened
   plan rows and change.md notes. The review skill leaves its edits uncommitted; ownership is
   recorded in `.git/rune/s12-desktop-window.carry`.
2. Run the PR's test and release workflows on that commit. Both test OSes and both build/smoke
   jobs must pass. Local WSL uses glibc 2.43 / Python 3.14.4 and does not replace the release's
   Ubuntu 22.04 / Python 3.12 compatibility build. The owner merges; the agent never merges.
3. Use the new PR artifacts for real-device acceptance, not run 42097549651 or the local builds
   with synthetic credentials.
4. Re-confirm reopened rows through `$rune-implement s12-desktop-window` after committing the
   fix and records. Pending: 1.9–1.12, 1.16, 2.7–2.9, 3.9, 4.5–4.10. The 11 existing short/combined
   acceptance suffixes remain unverifiable; re-confirm them rather than expanding SHAs without
   a human observation. For reviewed Phases 2–4: 10 pending, 7 unverifiable, 0/17 current.

### Focused real-device checks

- **Fedora 45, Terminal running the new PR binary:** start cast-tv without FONTCONFIG_FILE/PATH
  overrides. Expect no Fontconfig error/warning lines and readable Latin/Polish UI text with
  appropriate fallback fonts. Use X in the cast-tv window; expect it to close and Terminal to
  print `Stopped.`. Standard installed font directories remain available; arbitrary host/user
  rule snippets are not imported by default. Explicit configuration overrides still work.
- **Windows, cast-tv window:** Add to Start menu sits below Open on your phone, without floating
  over the header. Click the TV pill; expect only the TV chooser to open as a dropdown. Exercise
  Add, Update and Remove after the commit, as rows 4.8–4.10 require.
- **Windows, cast-tv window with networking off:** open the GoPro tab and reproduce the fetch
  error. Expect the complete URL to wrap without a page-wide scroll bar, including in a narrow
  window. Restore networking afterward.
- **Fedora, Terminal running cast-tv:** cover the window, then start cast-tv in a second Terminal.
  Expect the first window to come forward and its startup instruction to remain a single line.
- **Windows, PowerShell after closing cast-tv:** start the new artifact with an invalid TV
  argument using an owned/hidden-console launch. While the persistent cast-tv error dialog is
  open, check port 8895 from a separate PowerShell window; expect it to be free before OK. Unit
  tests already prove cleanup precedes the reporter callback; this checks the native dialog.

No real-TV, sign-in, native font-rendering or Windows sign-out confirmation was newly recorded
by these automated checks.
