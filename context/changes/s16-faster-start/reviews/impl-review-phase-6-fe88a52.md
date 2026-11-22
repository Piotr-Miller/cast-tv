<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: A faster-starting release file (Nuitka)

- **Plan**: context/changes/s16-faster-start/plan.md
- **Scope**: Phase 6 (phases 1–7)
- **Session**: fresh
- **Base**: 3ea354243e70f1c34847bcf60c25ea64afc65306 (end of Phase 5, parent of the Phase 6 Progress commit)
- **Head**: fe88a5250f93d34a73c8835b2cc71fdde1a39a8c
- **Worktree**: excluded (clean at review start)
- **Checks ran at**: fe88a5250f93d34a73c8835b2cc71fdde1a39a8c (temporary detached checkout)
- **Manual acceptance**: 0 of 1 confirmed at the reviewed revision — pending: 6.4. Later acceptance on the current branch is 1 of 1, as detailed below.
- **Date**: 2026-11-22
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — README overstates when the cache is cleaned up

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: README.md:356
- **Detail**: README says cast-tv removes all eligible old folders “at every start.” The only production call to `prune_old_caches()` is `_on_shown()` in `castlib/cli.py:364`, matching the plan. A browser fallback or `--no-window` launch never reaches that callback. On desktop starts the pruner can leave old folders in place when it cannot establish age or process state, or cannot rename them. The install and paths sections also say one folder per version, but a rebuilt version has a separate `<version>-gh<run>.<attempt>` folder.
- **Fix**: Describe one folder per build and say that after the desktop window opens, cast-tv tries to prune older unused build folders when it can do so safely.
- **Decision**: FIXED — corrected all three README sections on branch head `36329d6`; siblings: README install text, storage table and Limitations fixed, no other live documentation made the same claims; reopened: 7.13.

## Review Notes

- **Bookkeeping in diff**: context/changes/s16-faster-start/change.md, context/changes/s16-faster-start/plan.md.
- Branch and PR inspection confirmed draft PR [#111](https://github.com/Piotr-Miller/cast-tv/pull/111) at `36329d63427562e1e56bc41a2b2a8b1fe49a451e`. The diff from the reviewed commit to that head is limited to plan, change, research and handoff records. Two of six lessons directly apply to this review (written manual evidence and branch/PR inventory). All six were read and the repository's credential rule was followed.
- The workflow builds exactly two Nuitka files under the existing release names, runs smoke on each, and makes tag publication depend on both builds. The tag job names the two executable assets explicitly and leaves build-info with the CI artifacts. The PyInstaller spec was deleted. `packaging/startup_time.py` already had no reference to that spec, so no diff was needed there. Its PyInstaller comparison remains needed for Phase 5 evidence. The build and smoke script edits only update descriptions and examples to match the release names.
- **6.1**: `python -m pytest tests/test_smoke.py tests/test_build_nuitka.py -q` — exit 0, `33 passed in 0.46s`.
- **6.2**: `python -m pytest` — exit 0, `675 passed, 6 skipped in 118.59s`. Supplemental `python -m pyflakes castlib tests packaging` — exit 0, no output. [Test run 44821655716](https://github.com/Piotr-Miller/cast-tv/actions/runs/44821655716) also passed both OS jobs at the reviewed revision.
- **6.3 (paid)**: not run (paid) — existing [release run 44821655658](https://github.com/Piotr-Miller/cast-tv/actions/runs/44821655658) checked. Both build, smoke and upload steps passed at `fe88a52`. The tag publication job was skipped for the PR. Downloaded both named artifacts and their provenance sidecars. The Linux executable (artifact `14672886018`) is 154,876,120 bytes, SHA-256 `589725070ad5bbc9ae63d0469519b1f79b27e8324d7d6e8a468a2224617921de`. The Windows executable (artifact `14673365065`) is 18,296,320 bytes, SHA-256 `4718832ca88d7973886e06884992ed5936593e0a11cfad86860d8da90df7514e`. Both hashes match research.md. The artifact binaries were hashed without inspecting embedded contents.
- **6.4**: the shared acceptance script exited 0 in the detached checkout and reports the row pending there. The same script exited 0 at the current branch head and reports 6.4 current at `27556cc7f39ceaeda83143851d4d0ad323ee9bfd`. The owner confirmation and observations are in change.md and in research.md under “Phase 6: the published files against the measured ones” and “Phase 5 on Windows 11 again.” The current script also reports all six Phase 5 rows current. Historical Phase 6 Progress lacks the final commit suffixes and the recorded CI and manual confirmation that later bookkeeping adds.
- Independently compared both Phase 6 sidecars to the measured Nuitka pair from [run 44812632302](https://github.com/Piotr-Miller/cast-tv/actions/runs/44812632302). On each platform the full Python version, Nuitka 4.3.5 and dependency lists match, and all four dependency digests recompute. The only options that differ are the cache identity and output filename. GitHub reports no changed files between the two PR merge refs and their respective heads (Phase 5 `c35ddc9` / `eed2a5b`, Phase 6 `d0c7842` / `fe88a52`). The planned filtered source comparison found only the build script docstring and CLI help changes. That supports equivalence as defined by 6.4. The measured cold/warm ratios were 0.633/0.706 on Fedora and 0.828/0.734 on Windows, within the recorded bars of 1.00/0.75.
- Earlier-phase interaction: row 1.7 on the current branch is unverifiable because its declared surface still includes the deleted `packaging/cast-tv.spec`, absent at both its acceptance revision and branch HEAD. The observation itself is recorded for the earlier PyInstaller artifact per the later owner decision. The script state is recorded here for follow-up. Row 1.7 is outside the Phase 6 acceptance count.
- Mutation testing skipped. The missing-native-library and OS-divergence risks map to the release switch, but the repository configures no mutation tool. No product code or Progress rows were edited.
