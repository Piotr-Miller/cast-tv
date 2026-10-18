<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: A desktop window for cast-tv (S-12)

- **Plan**: context/changes/s12-desktop-window/plan.md
- **Scope**: Phase 1 (phases 1–4)
- **Session**: fresh
- **Base**: da3cfcca5bb4e30930d058a83cac56be02b16df7 (Progress — parent of phase commit)
- **Head**: 108343144a0b91d72cce7bdee1bba28ebf47be97
- **Worktree**: excluded (clean at review start)
- **Checks ran at**: 108343144a0b91d72cce7bdee1bba28ebf47be97 (temporary checkout)
- **Manual acceptance**: 0 of 9 confirmed at recorded head — pending: 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16. Later acceptance records at current main: 5 of 9 confirmed — pending: 1.9, 1.10, 1.12, 1.14.
- **Date**: 2026-10-18
- **Verdict**: REJECTED — local full-suite gate failed; no critical code finding
- **Findings**: 0 critical, 3 warnings, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | FAIL |

## Findings

### F1 — Termination can be lost before the window state exists

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/window.py:137; castlib/cli.py:320
- **Detail**: The CLI installs SIGTERM and console-close handlers that call window.destroy() before session-hook registration and backend import. The wrapper publishes _current only after _webview() returns. Until then destroy() silently discards the request. A SIGTERM during slow backend initialization can therefore leave the app running, or open the browser fallback after an import failure. Controlled reproduction: replace _webview with a function that calls destroy() then raises ImportError('backend unavailable'); run() returns 'unavailable: backend unavailable', rather than 'closed'. The existing tests begin their startup requests after this gap.
- **Fix**: Establish the active termination-request state before installing the window-mode handlers, retain requests through import/initialization, and clear the state on every exit. Test requests during session-hook setup and backend import, including import failure, with no fallback after termination.
  - Strength: Covers the entire interval in which the CLI routes termination to the window and preserves the plan's pending-end precedence.
  - Tradeoff: Requires a small lifecycle boundary change shared by the CLI and wrapper.
  - Confidence: HIGH — deterministic reproduction and direct control-flow evidence.
  - Blind spot: Native signal timing is not exercised by the fake.
- **Decision**: FIXED — Fix now (2026-10-18), uncommitted on fix/s12-phase1-f1; siblings: SIGTERM, ConsoleClose and SessionEnd hook-setup requests fixed through the shared scope; App.quit during scoped startup fixed through the same destroy path; direct run fixed before backend import; tab-mode handlers n/a (KeyboardInterrupt path, no webview startup); reopened: 1.8, 1.11, 1.13, 1.15.

#### F1 fix verification (2026-10-18)

- `python -m pyflakes castlib tests`: exit 0, no findings.
- `python -m pytest tests/test_window.py tests/test_cli.py tests/test_platform.py`: exit 0; 89 passed, 2 skipped in 10.86s. Includes seven new cases for termination during backend import (success/failure), hook setup (SIGTERM/console/session), direct-run cleanup after import failure, and setup exceptions.
- `python -m pytest`: exit 1; 2 failed, 425 passed, 5 skipped in 112.80s. Failures are the same pre-existing CLI App.current initialization race and known OneDrive five-second timeout recorded in F3. F1's targeted checks pass; the overall gate stays failed and F3 remains pending.
- Sibling scan: `rg` for window.run/window.destroy, end_on_sigterm, console_close_ends and on_end across castlib/tests. All window-mode end sources share destroy(); direct calls now own the same pre-import state. Requests remain lock-free and existing native readiness tests pass.
- acceptance-state.sh exited 0 before reopening: 1.8, 1.11, 1.13, 1.15 stale due to uncommitted castlib/cli.py and castlib/window.py; those rows reopened and their old acceptance revision recorded in change.md. 1.16 remains current. No human acceptance was recorded by this fix.
- acceptance-state.sh exited 0 after reopening: 1.8–1.15 pending, 1.16 current; no stale or unverifiable rows remain.
- See follow-ups/review-fixes.md for the next implementation commit's file set. The original review verdict remains tied to its recorded revision; F2 and F3 remain pending.

### F2 — The session-end deadline bounds waiting but not cleanup

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: castlib/cli.py:316; castlib/app.py:376; castlib/platform.py:418
- **Detail**: SessionEnd waits at most four seconds for its worker, but session_end() calls app.shutdown() without a deadline. The shutdown worker calls interrupted()/Stop before close(). SOAP has a ten-second timeout (castlib/dlna.py:19), so an unreachable TV can consume the entire sign-out budget before sources/server cleanup is even attempted. This contradicts the explicit plan requirement to carry the deadline through blocking Stop/close work, rather than merely bound a background worker's caller. A controlled stalled interrupted() leaves close() uncalled until the stall is released. The deadline test verifies callback return time only. Successful manual sign-out with a responsive TV does not cover this case.
- **Fix**: Carry one absolute session-end deadline through the shared shutdown coordinator, bound blocking operations against it, and ensure a stalled Stop cannot prevent attempts to cancel playback and release sources/server within the total budget. Add an integration-level fake test for stalled Stop plus competing GUI teardown.
  - Strength: Implements the planned bounded best-effort cleanup while retaining once-only shutdown.
  - Tradeoff: Requires explicit budgets at cleanup boundaries and careful handling of already-running ordinary shutdown.
  - Confidence: HIGH — the callback timer and sequential cleanup are independent, and SOAP's timeout exceeds the total budget.
  - Blind spot: Windows can terminate a process regardless of the remaining best-effort work.
- **Decision**: FIXED — Fix now (2026-10-18), uncommitted on fix/s12-phase1-f1; siblings: normal GUI return and App.quit share the coordinator; cli.ui and App.run_forever interrupt paths fixed to join it instead of issuing independent Stop; each source, cancellation, inhibitor, executor, server shutdown/socket close and temporary-file cleanup receives a share of the same deadline; repeated session end retains its first deadline; reopened: none (1.8–1.15 already pending, 1.16 remains current).

#### F2 fix verification (2026-10-18)

- SessionEnd passes its original absolute monotonic deadline into the CLI and App.shutdown. A later sign-out can shorten ordinary shutdown already waiting on Stop. Stop receives at most half the available time; close divides the remaining budget among independent cleanup attempts. Both shutdown and close are claimed once under the coordinator lock.
- A blocked operation is isolated on a daemon thread; its bounded wait cannot prevent later cancellation/source/server attempts. This does not forcibly abort native calls or promise a TV acknowledgement. Without a session-end deadline, ordinary shutdown still waits for every operation.
- `python -m pyflakes castlib tests`: exit 0.
- Final `python -m pytest tests/test_window.py`: exit 0; 36 passed in 6.31s. New integration cases stall both Stop and a source and verify that cancellation, another source, server.shutdown and server_close are each reached once before the bound; the same applies when ordinary Quit starts first. New GUI/tab interrupt race cases verify one Stop. Fake-clock coverage verifies the original 104.0 absolute deadline is forwarded once, without being reset by repeat end messages.
- Final `python -m pytest`: exit 0; 431 passed, 5 skipped in 110.20s, with Node available and the test-only repository .venv. This verifies the combined uncommitted F1/F2 fixes; no failing tests were excluded. Earlier failures remain recorded. F3's requested passing execution is now available for triage; its Decision remains pending until selected.
- Earlier focused window/CLI/platform/API run: exit 1; 111 passed, 2 skipped, one failure in the existing CLI App.current race from F3. No deadline or cleanup test failed.
- acceptance-state.sh: exit 0 after all F2 edits; 1.8–1.15 pending, 1.16 current. No stale/unverifiable rows and no additional acceptance reopening. No manual confirmation recorded.

### F3 — The local full-suite gate is not green

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: tests/test_cli.py:124; tests/test_onedrive.py:588
- **Detail**: Progress 1.6 requires python -m pytest to pass. Both local executions exited 1: the first hit the pre-existing CLI initialization race; the second hit the known OneDrive five-second timeout explicitly excluded from fixes in this plan. Each run had 419 passes and five skips. Focused phase tests and both PR CI jobs pass, but they do not turn these local executions into passes. This is a verification gap, not evidence that the window implementation introduced either failure.
- **Fix**: Obtain a passing full-suite execution in the documented environment; track stabilization of the existing races separately, keeping the plan's OneDrive exclusion intact. Preserve failed-run evidence alongside any later pass.
  - Strength: Satisfies the repository's gate without misattributing existing failures or broadening this phase silently.
  - Tradeoff: Requires follow-up verification and potentially separate test stabilization work.
  - Confidence: HIGH — both failures have captured exit statuses and tracebacks; the OneDrive flake is already documented.
  - Blind spot: The exact timing conditions producing each intermittent failure were not isolated.
- **Decision**: FIXED — Fix now (owner choice 2026-10-18); full suite exit 0, 431 passed and 5 skipped in 110.20s on the combined uncommitted F1/F2 tree; siblings: CLI initialization race and OneDrive timeout both included in this passing run, stabilization tracked separately in follow-ups/test-stabilization.md; no test exclusions or race fixes applied; reopened: none (verification-only resolution).

#### F3 updated evidence (2026-10-18)

- During F2 verification, `python -m pytest` exited 0: 431 passed, 5 skipped in 110.20s. No deselection or test-race fix was used. This satisfies the passing-execution part of the proposed fix on the current uncommitted tree, not retroactively on the originally reviewed revision. Stabilization of the pre-existing intermittent tests remains separate from this change; the original failures above are retained.

#### Triage complete (2026-10-18)

- Fixed: F1, F2, F3 (3). No pending decisions, skips, accepted risks or recorded lessons.
- Combined fix validation: pyflakes exit 0; full suite exit 0 (431 passed, 5 skipped). The original verdict and failure evidence remain attached to the originally reviewed revision; a re-review can verify the fixes as a new round.
- Changes remain uncommitted on fix/s12-phase1-f1. The carry record includes the code, tests, review and follow-up records for the next implementation commit.
- Manual acceptance: 1 of 9 current (1.16); 1.8–1.15 pending, including reopened 1.8, 1.11, 1.13, 1.15. No automated result replaces those observations.

## Verification

Commands ran in the detached checkout with the repository's test-only .venv Python 3.14.5 and Node on PATH. Each command's stdout/stderr was captured directly to a log and its exit status checked.

| Progress | Command | Exit | Output |
|---|---|---|---|
| 1.1 | python -m pyflakes castlib tests | 0 | No findings |
| UI syntax | node --check castlib/ui/app.js | 0 | No output |
| 1.2 | python -m pytest tests/test_window.py | 0 | 25 passed in 2.00s |
| 1.3 | python -m pytest tests/test_cli.py | 0 | 29 passed, 2 skipped in 6.44s |
| 1.4 | python -m pytest tests/test_api.py | 0 | 19 passed in 3.70s |
| 1.5 | python -m pytest tests/test_ui.py | 0 | 13 passed in 1.57s |
| 1.6 first run | python -m pytest | 1 | 1 failed, 419 passed, 5 skipped in 113.29s; test_cast_replaced_from_the_ui_keeps_serving: AttributeError: App has no attribute current at tests/test_cli.py:124 |
| 1.6 rerun | python -m pytest | 1 | 1 failed, 419 passed, 5 skipped in 105.32s; test_token_file_mode_0600: condition not met within 5.0s at tests/conftest.py:276 |
| 1.7 | gh pr checks 61 | 0 | test (ubuntu-latest) pass; test (windows-latest) pass |

## Review Notes

- **Bookkeeping in diff**: context/changes/s12-desktop-window/change.md, context/changes/s12-desktop-window/plan-brief.md, context/changes/s12-desktop-window/plan.md, context/changes/s12-desktop-window/research.md, context/changes/s12-desktop-window/reviews/plan-review.md.
- Reviewed phase code at its recorded revision, using the current plan's owner-approved clarifications. No code/test/dependency changes exist between the phase commit and current main 023199b. The temporary checkout is removed after verification.
- acceptance-state.sh exited 0 in the reviewed checkout: all nine Phase 1 Manual rows are pending there. A supplemental invocation against current main also exited 0: 1.8, 1.11, 1.13, 1.15, 1.16 are current at accepted revision ffa982c46ad1f1bd5ea9b81a9283f941dac2690b; their research.md observations were checked. No stale or unverifiable rows. Row 1.14 has Windows observations but awaits Fedora kill acceptance. No acceptance marks changed.
- Lessons: read all 6 entries; 1 explicitly names impl-review (manual evidence). Also applied repository-wide branch inspection, exact manual instructions and secret-handling rules, plus the relevant UI message rule.
- Plan contracts otherwise match: renderer validation, dependency policy, consent/UI split, loopback endpoints, Quit state and foundation updates. version_text's fourth line is Phase 2 work. tests/conftest.py additions isolate the native session hook; no substantive scope expansion.
- Mutation testing skipped: no mutation tool is configured in the manifest or foundation test plan. Touched risks include LAN control and Windows/Linux divergence.
- The first full-suite failure exposes an existing test synchronization race: the same test predicate and early server.app publication before self.current initialization exist at the base revision. The focused CLI gate passed; a full-suite rerun is recorded below. The first failure is retained as evidence, not attributed to the new window paths.
- CI evidence: https://github.com/Piotr-Miller/cast-tv/actions/runs/39120977026 (PR #61, both test jobs pass). Packaging/release workflow was not changed by Phase 1, so no release build was required for this scope.
