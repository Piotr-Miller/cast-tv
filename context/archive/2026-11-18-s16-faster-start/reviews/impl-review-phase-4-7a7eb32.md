<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: A faster-starting release file (Nuitka)

- **Plan**: context/changes/s16-faster-start/plan.md
- **Scope**: Phase 4 (phases 1–7)
- **Session**: fresh
- **Base**: b1384bf42ff93edfe49f7d1e6b5f9f70d4038775 (previous phase, including Phase 3 review fixes)
- **Head**: 658da785d91ac01687c0d3c2735a8a891870a256
- **Worktree**: excluded — clean at review start; no local changes to include or exclude
- **Checks ran at**: 658da785d91ac01687c0d3c2735a8a891870a256 (temporary detached checkout)
- **Manual acceptance**: none planned for Phase 4
- **Date**: 2026-11-20
- **Verdict**: APPROVED
- **Findings**: 0 critical, 0 warnings, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

None.

## Review Notes

- **Bookkeeping in diff**: context/changes/s16-faster-start/plan.md.
- The reviewed commits are 8297237 (Phase 4 implementation) and 658da78 (Windows long-path correction). Current checkout HEAD 19067f7d968c0e97df2a5664a7e873a24e27c0ea adds only change/plan/procedure documentation; those later changes are outside the product revision reviewed here. No product code was edited during the review.
- Both bounded, read-only review passes ran in parallel: plan drift and safety/quality/pattern compliance. Their conclusions were checked against the source and verification evidence. All nine changed product/workflow/test files were reviewed. Supporting comparisons included packaging/cast-tv.spec, packaging/entry.py, packaging/startup_time.py, pyproject.toml, and existing platform/cleanup conventions.
- All 6 lessons were read. The stage/session selection directly applies 2 of 6 (manual evidence and branch/PR inspection); credential/shipping rules also apply to packaging, and no live credential or stored token was read. `git fetch`, remote branches, the active plan and draft PR #111 were checked before reviewing the existing branch.
- Plan adherence: build identities use the shared grammar, explicit/CI/local precedence, and the versioned cached-onefile spec. The builder pins Nuitka 4.3.5, includes the planned packages/data/backends, applies OS-specific exclusions and Fontconfig data, and records identity, versions, dependency hash, commit and exact options in a sidecar. The CLI names the cache; smoke validates the packager-specific Cache line. The workflow builds/smoke-tests/uploads four assets while explicitly publishing only the two PyInstaller assets on tags.
- Supporting scope adjustment: castlib/bundle.py expands Windows 8.3 data/cache paths so the identity grammar and cache-parent checks recognize the real folder. This addresses the observed failed CI run 44628255344 and preserves the earlier data/cache contract; PyInstaller is unchanged. Coverage includes injected expansion on both operating systems and a native Windows short-path case. It is justified supporting work, not scope creep.
- Acceptance-state script ran from the detached phase checkout using the installed skill's Git Bash script: exit 0. Phase 4 has no Manual rows. All 21 Manual rows in the plan are still pending (1.7; 5.1–5.6; 6.4; 7.1–7.13). No acceptance or Progress row was modified. Automated 4.1–4.3 have implementation evidence; the current plan's suffixes point to the reviewed revision.
- **4.1**: `C:/Source/cast-tv/.venv/Scripts/python.exe -m pytest tests/test_smoke.py tests/test_build_nuitka.py tests/test_cli.py -q` — exit 0; `74 passed, 2 skipped in 10.52s`.
- **4.2**: `C:/Source/cast-tv/.venv/Scripts/python.exe -m pyflakes castlib tests packaging` — exit 0; no output.
- **4.3 (paid)**: not run (paid) — existing [release run 44630376210](https://github.com/Piotr-Miller/cast-tv/actions/runs/44630376210), its four artifacts and both Nuitka build-info sidecars checked. The run's head SHA is 658da78; all four build jobs, smoke steps and artifact uploads succeeded. The release job was correctly skipped for a PR. No paid build/watch command was executed.
- Artifact inventory: cast-tv-linux-x64 (artifact 14581855635), cast-tv-windows-x64.exe (14580849049), cast-tv-linux-x64-nuitka (14581796516), cast-tv-windows-x64-nuitka.exe (14580208995); all unexpired. The two Nuitka archives were downloaded into the temporary checkout to inspect their sidecars; binaries were not executed or inspected for embedded contents. PyInstaller evidence is the artifact inventory plus successful build/smoke/upload steps.
- Both Nuitka sidecars name identity `0.5.0-gh44630376210.1` and Nuitka 4.3.5. Platform options match the reviewed builder, apart from runner-specific absolute output paths. Dependency-list SHA-256 values recompute correctly. Linux: Python 3.12.16, dependency hash `d0b80e2f2ba311fc6dd079dbeeae4013dd9762b04615b3d01d2f9f8558ac60be`; Windows: Python 3.12.10, dependency hash `4e2a97f748eafcf0b5ca79f300a445f382cd6979859adf52c3ba113ebb6165a6`.
- Provenance records PR merge commit `97a5ec002a30200cc243f4f46649766c23c03f0c` on both systems. GitHub's compare API reports one merge commit and no changed files against 658da78, establishing source-tree equivalence to the reviewed phase. The sidecar correctly records the actual checkout rather than inventing the PR head SHA.
- Downloaded Linux Nuitka binary: 154,814,680 bytes, SHA-256 `e3cc14a4ee6b8b10abd229ed020d4a9b3ef136660c035a0e149791e79d8211a5`. Windows Nuitka binary: 18,300,416 bytes, SHA-256 `7d044dfdffda52e52d3912c2f4f581f909ce47d0a1662366e6a20cdefaeeda99`.
- The existing [test run 44630376203](https://github.com/Piotr-Miller/cast-tv/actions/runs/44630376203) at 658da78 passed on Windows and Ubuntu. PR #111 also has green four-way release checks at the later documentation-only head; that later run is supplemental, not the recorded phase evidence.
- Mutation testing skipped: no mutation tool is configured in the project manifest or test plan. Relevant risk-map scenarios (missing native libraries and Windows/Linux divergence) map through the phase's packaging/backend/path contracts; smoke jobs and cross-platform tests provide the planned response. No n/a or paid command was treated as a passing local execution.
- Local checks used the existing venv as an interpreter with the detached checkout as the working directory; an import-path probe confirmed castlib loaded from that checkout. Stdout/stderr were captured to temporary log files; exit statuses were preserved.
- Repository-wide verification at the same phase revision: `C:/Source/cast-tv/.venv/Scripts/python.exe -m pytest` — exit 0; `673 passed, 7 skipped in 123.71s (0:02:03)`. No new code changes or triage fixes were needed. Review records remain uncommitted and carried for the next workflow commit.
