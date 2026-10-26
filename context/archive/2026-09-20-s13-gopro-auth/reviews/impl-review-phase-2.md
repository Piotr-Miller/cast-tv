<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: GoPro without a hand-pasted token (S-13)

- **Plan**: context/changes/s13-gopro-auth/plan.md
- **Scope**: Phase 2 of 5
- **Date**: 2026-09-23
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 1 warning, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — In-flight connections can undo Disconnect or shutdown

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/gopro.py:820
- **Detail**: The pasted-token branch verifies over the network, then saves and adopts without checking `_gen` or `_closed`. A concurrent `disconnect()` can finish before the paste writes a new token file, leaving the source connected after the user asked to forget it. A paste can also complete after `close()`. The stored-token branch at lines 838–848 captures a generation but does not recheck it before `_adopt`, so its old token can be restored in memory after a disconnect or newer paste. The hand-off path already checks its generation under the lock at lines 707–718; the phase's state-sequencing rule calls for the same protection.
- **Fix**: Capture the generation before each network verification. Under `_lock`, check that the generation is still current and the source is open, then save/adopt the verified paste or adopt the stored token before releasing the lock. Add deterministic tests that pause verification while Disconnect, a newer paste, or `close()` runs.
  - Strength: Applies the generation rule already used by the hand-off and ordinary source calls; prevents a forgotten credential from reappearing.
  - Tradeoff: Requires careful lock scope around the paste's file write and tests of concurrent operations.
  - Confidence: HIGH — the unguarded paths and guarded hand-off are visible in the same module.
  - Blind spot: The exact frequency of this race in normal use has not been measured.
- **Decision**: FIXED (2026-09-23, triage). Both `connect()` branches now capture the generation (and `_check_open`) before the network verification and save/adopt under `_lock` only while it still matches; a superseded paste is dropped and answers the current status, a paste across `close()` raises `source_closed`. `disconnect()` unlinks the token file under the lock so a paste adopted after it cannot lose its file. The `_adopt` wrapper lost its callers and is gone. Five deterministic tests (`before_answer` hook on the verify call, no threads) in `tests/test_gopro.py`: paste vs Disconnect, paste vs newer paste, paste vs `close()`, stored-token re-verify vs Disconnect, stored-token re-verify vs newer paste. All five were red on the unfixed source; the full suite is 333 passed, 1 skipped; pyflakes clean.

## Verification

- `python -m pytest tests/test_gopro.py tests/test_api.py` could not run with system Python (`No module named pytest`). Equivalent project environment command `.venv/bin/python -m pytest tests/test_gopro.py tests/test_api.py`: 53 passed.
- `.venv/bin/python -m pytest`: 328 passed, 1 skipped.
- `.venv/bin/python -m pyflakes castlib tests`: passed with no output.
- Progress row 2.4 is checked. `research.md` records the 2026-09-23 Fedora machine, the POST response, the opened window, and the `browser_closed` status with no fallback. The local and CI test observations are also recorded there.
- Scoped mutation testing skipped: `context/foundation/test-plan.md` §4 lists quality gates and names no risk-critical module touched by this phase.
