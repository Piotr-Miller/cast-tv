<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: A faster-starting release file (Nuitka)

- **Plan**: context/changes/s16-faster-start/plan.md
- **Scope**: Phase 3 (phases 1–7)
- **Session**: fresh
- **Base**: c213876766510cdb5b3e033fc8dcc5ef28a94398 (previous phase, including its review fixes)
- **Head**: ed90da9076246a9154c6e1986ab947ab4a3ea941
- **Worktree**: included(context/changes/s16-faster-start/plan.md) — existing Phase 3 SHA write-back only; no excluded changes
- **Checks ran at**: ed90da9076246a9154c6e1986ab947ab4a3ea941
- **Manual acceptance**: none planned for Phase 3
- **Date**: 2026-11-19
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 0 observations

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

### F1 — Unreadable markers can authorize deletion of recently used caches

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/bundle.py:207–211,250–251
- **Detail**: `_mtime` turns every OSError into a missing marker. Permission or I/O errors therefore select the directory-mtime fallback, although the last start time is unknown. A temporary-folder reproduction with a one-day-old marker, a thirty-day-old directory mtime, and an injected PermissionError on marker stat deletes that cache. This violates Phase 3's seven-day guard. An unreadable marker can also change which cache is retained as previous. Failure to write the current marker is likewise ignored, leaving subsequent pruners with stale last-start evidence.
- **Fix**: Distinguish a genuinely absent marker from other metadata failures. Stop pruning when current-marker recording or candidate metadata reads fail; use the directory fallback only for FileNotFoundError.
  - Strength: Preserves the retention contract when the filesystem cannot prove age or previous-build order.
  - Tradeoff: A metadata problem may retain more disk space until a later successful start.
  - Confidence: HIGH — reproduced with the existing pruning fixtures and an injected filesystem error.
  - Blind spot: Real filesystem faults and permissions are represented by injected exceptions.
- **Decision**: FIXED — recommended fix; siblings: current-marker write fixed, candidate marker reads fixed, fallback directory-mtime reads fixed in castlib/bundle.py; castlib/config.py::sweep_stale_video_dirs n/a (failed lstat already skips deletion), castlib/sources/gopro.py::_token_mtime n/a (credential status only; no cache deletion or retention decision); reopened: none (acceptance script exit 0; all Manual rows pending).

### F2 — Later deletions reuse an obsolete process and retention snapshot

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/bundle.py:254–286
- **Detail**: All candidate ages, previous-build selection, and process images are captured before the deletion loop. Recursive removal of one large cache can take time. A different old build can start while that removal runs, yet the next cache is still deleted using the earlier empty process list. A temporary-folder reproduction changes the injected process list during the first removal: both caches are removed, including the second cache now containing a listed executable. A newly updated marker is also ignored. This is an avoidable stale-snapshot interval across deletions, beyond the plan's accepted bootstrap race at a deletion boundary.
- **Fix**: Before each build or leftover deletion, obtain a fresh complete process list and recompute candidate ages and the previous build. Stop further cleanup if the refreshed evidence is incomplete or unreadable. Keep rename-before-remove and the existing bootstrap-race limitation.
  - Strength: Stops a slow first deletion from invalidating the safety decision for later targets; protects both normal builds and leftover directories.
  - Tradeoff: Additional process listings and small directory scans during background housekeeping.
  - Confidence: HIGH — deterministic injected-process reproduction deletes an in-use later target.
  - Blind spot: No exclusion lock with the vendor bootstrap; a process can still start after the final check, as already accepted in the plan.
- **Decision**: FIXED — recommended fix; siblings: normal build deletions fixed, `.removing-*` cleanup fixed in castlib/bundle.py; packaging/startup_time.py::run_series n/a (measurement preflight is already repeated before each individual run, and clear_cache deletes one explicitly selected cold cache rather than batching retention decisions); reopened: none (acceptance script exit 0; all Manual rows pending).

## Review Notes

- **Bookkeeping in diff**: context/changes/s16-faster-start/plan.md.
- All 6 of 6 lessons were read. Stage filtering directly selects 2 of 6 (manual evidence and session-start branch/PR inspection); the remaining four were checked where their scope applies. No lesson, licensed skill, credential, or stored token was edited or inspected.
- `git fetch`, remote branches, PR list (empty), and every active plan were checked. This reviews and fixes the existing `s16-faster-start` phase; it does not start a new change or branch from an open PR.
- Plan drift pass: bundle marker, grammar, current/previous selection, age guard, incomplete-list refusal, rename-before-remove, leftover cleanup, and the CLI's Nuitka-only background shown hook are implemented. F1–F2 weaken the retention intent. No unplanned product changes; CLI hook tests are relevant coverage.
- Safety/pattern pass: compared cleanup with `castlib/config.py::sweep_stale_video_dirs`, failure boundaries with `castlib/processes.py`, and CLI/window callbacks and tests with their existing siblings. No further substantive finding.
- Acceptance script: Git Bash `scripts/acceptance-state.sh` exited 0. No Phase 3 Manual rows exist. All 21 Manual rows across the plan remain pending (1.7; 5.1–5.6; 6.4; 7.1–7.13); no confirmation is implied by this review.
- No n/a or paid Phase 3 rows. Mutation testing skipped: no mutation tool is configured in the test plan or project manifest. The cross-platform path risk maps to this phase's pruning logic; injected process, rename, and deletion tests cover its logic. Real retention on Windows/Fedora remains row 7.10.
- Default system `python` lacks pytest and pyflakes; its initial check attempts exited 1 with missing-module errors. Checks were restarted with the existing `.venv/Scripts/python.exe`.
- Baseline 3.1: `.venv/Scripts/python.exe -m pytest tests/test_bundle.py -q` — exit 0; `36 passed, 1 skipped in 1.65s`.
- Baseline 3.2: `.venv/Scripts/python.exe -m pyflakes castlib tests packaging` — exit 0; no output.
- Baseline 3.3: `.venv/Scripts/python.exe -m pytest` — exit 0; `639 passed, 7 skipped in 122.54s (0:02:02)`. Commands redirect stdout/stderr to temporary logs and preserve the command's exit status.
- Owner instruction in this session authorizes fixing all findings with the recommended approach. Both findings have one recommended fix; no additional triage question is needed. The skill leaves review and fix files uncommitted.

## Triage and verification

- Fixed F1 and F2 using the recommended approaches. The verdict above describes the original reviewed revision, not the uncommitted fixes.
- `_mtime` now falls back only on FileNotFoundError. Other metadata errors stop pruning. Failure to record the current start also stops cleanup.
- `_prune_targets` centralizes the existing retention rules. Each deletion refreshes the process list, then retention metadata and previous-build selection. A later incomplete listing or metadata failure stops remaining cleanup. Prior removals cannot be undone; an initially incomplete listing still removes nothing.
- The first regression run against the original implementation failed all 9 added failure/concurrency scenarios. A non-applicable tenth parameter combination was removed rather than counted as coverage. The remaining tests exercise unreadable markers, an unknown previous-build marker, failed current-marker recording, and process/marker/incomplete-list changes during the first removal, for both normal builds and leftovers where applicable. The concurrency cases do not assume directory iteration order.
- Focused check: `.venv/Scripts/python.exe -m pytest tests/test_bundle.py tests/test_cli.py -q` — exit 0; `85 passed, 3 skipped in 11.95s`.
- Post-fix `.venv/Scripts/python.exe -m pyflakes castlib tests packaging` — exit 0; no output.
- Post-fix acceptance-state script — exit 0; every Manual row remains pending. No Progress or acceptance declaration was edited by this review. The existing plan SHA write-back is preserved.
- Post-fix full suite: `.venv/Scripts/python.exe -m pytest` — exit 0; `648 passed, 7 skipped in 125.00s (0:02:05)`.
- Final regression-harness check after making concurrency tests independent of directory iteration order: `.venv/Scripts/python.exe -m pytest tests/test_bundle.py -q` — exit 0; `45 passed, 1 skipped in 2.16s`. Final pyflakes — exit 0; no output. `git diff --check` — exit 0.
- Triage complete: fixed F1, F2; no pending findings, skipped findings, or new lessons. Real-device acceptance is still pending; the agreed bootstrap race remains. No packaging or workflow files changed, so this fix does not trigger the packaging PR gate.
