<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Photos through share links

- **Plan**: context/changes/s09-share-link-photos/plan.md
- **Scope**: Phase 2 (phases 1–3)
- **Session**: fresh
- **Base**: aed13dc6b1eb16a6e342d793ceb63f93942f2877 (Progress: previous phase's commit)
- **Head**: 9111645ffb5007c270744539794e749a931be019
- **Worktree**: included(context/changes/s09-share-link-photos/plan.md)
- **Checks ran at**: 9111645ffb5007c270744539794e749a931be019
- **Manual acceptance**: none planned for phase 2
- **Date**: 2026-10-14
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

## Verification

Commands ran in the current checkout at the recorded head. The only included local edit adds the phase 2 commit suffix to Progress rows 2.1–2.3; production code and tests match that head. Each command's stdout/stderr was captured to its own file before inspection; exits below are the command's status, without a pipeline.

| Progress row | Command | Exit | Actual output |
|-------------|---------|------|---------------|
| 2.1 | `.venv/bin/python -m pytest tests/test_gphotos.py -q -p no:cacheprovider -k "link_photo_tile or link_motion_photo or link_photo_in_show"` | 0 | `11 passed, 79 deselected in 0.42s` |
| 2.2 | `.venv/bin/python -m pytest -q -p no:cacheprovider` | 0 | `373 passed, 1 skipped in 31.01s` |
| 2.3 | `.venv/bin/python -m pyflakes castlib tests` | 0 | No output. |

Logs: `/tmp/cast-tv-phase2-review.bS8q6e/source.log`, `/tmp/cast-tv-phase2-review.bS8q6e/suite.log`, `/tmp/cast-tv-phase2-review.bS8q6e/pyflakes.log`. `git diff --check aed13dc 9111645` also exited 0.

## Review Notes

- **Bookkeeping in diff**: context/changes/s09-share-link-photos/change.md, context/changes/s09-share-link-photos/follow-ups/review-fixes.md, context/changes/s09-share-link-photos/plan.md, context/changes/s09-share-link-photos/reviews/impl-review-phase-1-aed13dc.md.
- Local changes included: plan.md's SHA write-back for rows 2.1–2.3. No local changes excluded. The report and carry record were saved after verification. change.md's updated date is already 2026-10-14; its implementing status remains appropriate for this phase review.
- Rows 1.1–1.3 and 2.1–2.3 have ancestor commit suffixes, establishing implementation evidence for phases 1–2. Phase 3 remains pending. No malformed, n/a or paid rows in phase 2.
- Acceptance script exited 0. Phase 2 has no Manual rows; out-of-scope phase 3 rows 3.3–3.8 are all pending. No TV acceptance inferred from the scripted tests.
- Lessons: read all 6 entries; 1 of 6 explicitly applies to impl-review (A ticked manual row needs a written observation). There are no Manual rows to confirm in this phase.
- Both review passes ran in this session because the substantive diff has three files. Pattern comparisons used picked-media variants and refresh closures in gphotos.py, OneDrive's MediaItem/Upstream and thumbnail paths, the existing guarded video-link tests, and the scripted share-page transport.
- Every phase 2 contract matches: shared() records kind/url/clip/thumb; plain photos list with a guarded thumbnail and no variants; motion photos offer Photo by default and Clip as the 1080p H.264 stream. auto/photo resolves to the still, clip resolves to a relayed video with download=False, and invalid choices raise bad_quality. Versions distinguish =d from =m37. Photo refresh rereads shared(), updates the stored addresses and refuses a changed kind or missing selected clip. Video refresh still uses resolve() and video quality handling is unchanged. Deduplication, ids and names are preserved.
- The API thumbnail test proves an off-Google redirect is refused without contacting its target. The photo fetch test proves retry after an expired address, and the POST /api/show integration proves an unqualified motion-photo link resolves to its still and sends a media URI to the fake TV. Existing video-link and share-page regression tests pass in the full suite.
- sharelink.py is outside phase 2's planned file list but contains the documented, owner-selected phase 1 F1 fix carried into this commit: only HTTP 200/206 with a video MIME type is accepted. The associated tests exercise valid 200/206 and reject 202/204 for video/mp4 and application/mp4. This is authorized review follow-up work, not unexplained scope expansion. The phase 1 report retains its historical boundary and verdict.
- Mutation testing skipped: no mutation tool is configured in pyproject.toml or the test plan. Expiring cloud addresses map to the new refresh behavior through this plan, but no configured mutation gate exists. No live Google requests or TV acceptance checks were performed.
- Report and change.md are carried for the next workflow commit. No production edits, Progress edits or commits made by this review.
