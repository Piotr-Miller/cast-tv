# Next steps (2026-11-19, S-16 Phase 1 review fixes left uncommitted)

Branch: `s16-faster-start`, HEAD `0707dac`. No PR exists. The owner requested no commit; all
review fixes and workflow records are in the worktree and recorded in the change's carry file.
Do not discard them or overwrite them by pulling another checkout over this worktree.

## Completed

- Phase 1 was reviewed from explicit base a85f59d through 0707dac, including a558115, 5155ad8,
  fc780be and 7d33c1b. The owner then authorized all recommended fixes.
- Report: `context/changes/s16-faster-start/reviews/impl-review-phase-1-0707dac.md`.
  Findings F1-F7 are fixed; Re-review 2 records the current local verification.
- Ready now follows complete tab setup and successful status assignment, independently of
  `/api/errors`. Tests control the render tick and two separate frames.
- Windows process ownership uses user SIDs rather than desktop-session inference. Unknown
  ownership and API errors make the list incomplete. Failed version probing and failed owned
  shutdown fail the measurement. Three existing test synchronization hazards were corrected.
- Final local checks: 592 passed, 6 skipped; pyflakes and both JavaScript syntax checks pass.
  Linux owner coverage and release build/smoke still need CI.

## Next

1. In the editor/project window for `C:\Source\cast-tv`, inspect the report and `git diff`.
   The original reviewed commits are pushed; these fixes are intentionally not committed or
   pushed. When the owner chooses to commit, keep the fixes with the report, plan reopening,
   change notes, research notes and this handoff. No skill files belong in that commit.
2. Row **1.7 is reopened** because its accepted surface changed. Its original Windows observation
   remains in research.md, but cannot confirm this source. Commit the checked changes before
   recording a new acceptance revision, build that revision, then repeat five warm runs and the
   watched run. In the cast-tv window, the TV button and source tabs must be visible when the
   timing prints in PowerShell; clicking a source tab must respond at that point. Record date,
   device, executable SHA-256, run values and the owner's actual observation in research.md.
3. **Windows measurement limitation:** in the current unelevated PowerShell session, ownership
   of protected processes is hidden, so the corrected tool safely refuses at PID 4. A null SID
   must not be treated as proof of another user. If testing with elevated rights, in Windows
   Start search **PowerShell**, choose **Run as administrator**, and approve the Windows prompt
   for the same account. The resulting PowerShell title should show **Administrator**. Run the
   measuring command there; expect measured runs or an explicit refusal. Elevated success was
   not verified here. A refusal must not be accepted as row 1.7 or bypassed with a guessed list.
4. Continue Phase 2 with the bundle facts and their callers, then Phases 3-4. Phase 3 must keep
   its no-deletion-on-IncompleteListing behavior, including on Windows with hidden ownership.
   The PR must run the packaging release build and smoke test; no passing PR run exists yet.
5. Keep the known `--hold` priming-start correction deferred to Phase 4. Do not switch packagers
   before Phase 5's measured bars and the owner's decision on both systems.
