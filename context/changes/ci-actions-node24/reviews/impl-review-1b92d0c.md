<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Move the workflows' GitHub actions off Node.js 20

- **Plan**: context/changes/ci-actions-node24/plan.md
- **Scope**: full
- **Session**: fresh
- **Base**: fc59b9dee586d53b3559525880b43f597f3fee90 (merge-base origin/main)
- **Head**: 1b92d0c3a1692919e577159c14671e8a742f0f36
- **Worktree**: excluded (clean at review start; no local changes to include or exclude)
- **Checks ran at**: 1b92d0c3a1692919e577159c14671e8a742f0f36
- **Manual acceptance**: 0 of 1 confirmed — pending: 1.4
- **Date**: 2026-10-26
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

- **Bookkeeping in diff**: context/changes/ci-actions-node24/change.md, context/changes/ci-actions-node24/plan-brief.md, context/changes/ci-actions-node24/plan.md.
- **Boundary**: full review of Phase 1 (phases 1–1). The two commits in scope are `f9b6beb` (Phase 1) and `1b92d0c` (epilogue). The phase's Progress SHA is an ancestor of HEAD. No existing implementation-review report was present. The canonical plan path is inside the active change folder.
- **Lessons**: all 6 entries were read; 1 of 6 explicitly targets implementation review (written observations before manual acceptance). The session-start and owner-step rules were also followed. Row 1.4 remains unchecked; no human observation or acceptance revision is claimed.
- **Review passes**: both performed in this session; the production diff is only six lines across two files. Plan drift: both files MATCH. Safety/quality/patterns: compared the workflows with their base versions and each other; the existing major-tag convention, events, runner matrix, permissions, Python version, inputs and commands are preserved. No unplanned production paths changed.
- **Runtime and compatibility**: the upstream definitions for [checkout v7](https://github.com/actions/checkout/blob/v7/action.yml), [setup-python v7](https://github.com/actions/setup-python/blob/v7/action.yml), [upload-artifact v7](https://github.com/actions/upload-artifact/blob/v7/action.yml) and [download-artifact v8](https://github.com/actions/download-artifact/blob/v8/action.yml) all declare `node24`. Latest-release API results confirm majors 7, 7, 7 and 8 respectively. Upload defaults to zipped artifacts; download preserves `path` and `merge-multiple`, and defaults to extraction with digest mismatch treated as an error. The existing upload/download pairing is compatible by inspection; tag execution remains pending.
- **1.1 — PASS**: ran the plan's `grep`, `sort` and `uniq -c` as separate commands using temporary files (no status-masking pipeline); exit 0 for every command. Output: `2 uses: actions/checkout@v7`, `1 uses: actions/download-artifact@v8`, `2 uses: actions/setup-python@v7`, `1 uses: actions/upload-artifact@v7`. An additional Python Counter assertion checked every `actions/` reference and normalized only version tags before comparing both complete files with the base: exit 0, `PASS: six planned pins; no other workflow content changed`.
- **1.2 — PASS**: `gh pr checks 82`, exit 0. [Test run 40398550422](https://github.com/Piotr-Miller/cast-tv/actions/runs/40398550422) reports success for `test (ubuntu-latest)` and `test (windows-latest)` at the recorded HEAD. Both retain pyflakes and the full pytest suite.
- **1.3 — PASS**: `gh pr checks 82`, exit 0. [Release run 40398550351](https://github.com/Piotr-Miller/cast-tv/actions/runs/40398550351) reports success for both builds at the recorded HEAD. The jobs API confirms PyInstaller, Smoke test and upload-artifact steps succeeded on Windows and Ubuntu 22.04. The tag-only `release` job is skipped as designed.
- **Annotations — PASS**: `gh api repos/Piotr-Miller/cast-tv/check-runs/<id>/annotations?per_page=100`, exit 0 for job IDs `121837959841`, `121837960958`, `121837960371`, `121837960424` and `121839137589`. Four return `[]`; the Ubuntu test job has one unrelated notice about the `ubuntu-latest` migration to Ubuntu 26. No Node.js 20 deprecation annotation appears in any job.
- **Local lint — PASS**: `./.venv/Scripts/python.exe -m pyflakes castlib tests`, exit 0, no output.
- **Local suite — PASS**: `./.venv/Scripts/python.exe -m pytest`, exit 0, `440 passed, 5 skipped in 107.81s (0:01:47)`. Ran in the repository's venv on Windows with Python 3.14.5 and Node on PATH; UI behavior tests executed. Local Python differs from CI's 3.12; the green CI runs supply that evidence.
- **Command evidence**: local checks and PR-check/annotation responses were redirected to files under `%TEMP%/cast-tv-ci-actions-node24-review` before inspection; pass/fail was captured from each command's exit status. `git diff --check fc59b9d HEAD` also exited 0.
- **Manual 1.4 — pending acceptance**: `bash .agents/skills/rune-impl-review/scripts/acceptance-state.sh context/changes/ci-actions-node24/plan.md` (Git for Windows Bash), exit 0, output `1.4\tpending\t-\t.github/workflows/release.yml\t-`. No n/a, stale, unverifiable or malformed rows. The owner chose the next real tag; no trial tag or publication was attempted. Pending acceptance does not lower this review's verdict.
- **Mutation testing**: skipped; no mutation tool is configured in the manifest or test plan. This diff changes action pins, without changing the bundle, secret-writing or application behavior behind the risk-map scenarios.
- **Persistence**: this report and the change status stamp are left uncommitted and recorded in `.git/rune/ci-actions-node24.carry`. Analysis did not edit Progress or production files.
