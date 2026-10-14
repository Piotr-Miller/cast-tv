<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Photos through share links

- **Plan**: context/changes/s09-share-link-photos/plan.md
- **Scope**: full
- **Session**: fresh
- **Base**: ccca7cb98c85181b7a9178a22985337cd0d1eee4 (merge-base: origin/main)
- **Head**: 17b54efec9bb6f80011cf28292b1c871ad4cddf0
- **Worktree**: excluded (clean at the review boundary; no local changes to include or exclude)
- **Checks ran at**: 17b54efec9bb6f80011cf28292b1c871ad4cddf0
- **Manual acceptance**: 0 of 6 confirmed — pending: 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
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

Each applicable automated criterion was matched to its Progress row. Shared commands ran once against the final revision, satisfying their rows across phases. Stdout and stderr were captured to separate files before inspection; exit statuses below belong to the commands, without a pipeline.

| Progress rows | Command | Exit | Actual output |
|---------------|---------|------|---------------|
| 1.1 | `.venv/bin/python -m pytest tests/test_gphotos.py -q -p no:cacheprovider -k "share_link_album or share_page_photo or share_page_motion"` | 0 | `23 passed, 67 deselected in 0.32s` |
| 2.1 | `.venv/bin/python -m pytest tests/test_gphotos.py -q -p no:cacheprovider -k "link_photo_tile or link_motion_photo or link_photo_in_show"` | 0 | `11 passed, 79 deselected in 0.39s` |
| 1.2, 2.2, 3.2 | `.venv/bin/python -m pytest -q -p no:cacheprovider` | 0 | `373 passed, 1 skipped in 32.13s` |
| 1.3, 2.3 | `.venv/bin/python -m pyflakes castlib tests` | 0 | No output. |
| 3.1 | `! git grep -n -i "videos only" -- README.md context/foundation/prd.md castlib/ui` | 0 | No matches. |

Additional checks: `git diff --check ccca7cb HEAD` exited 0 with no output. The acceptance-state script exited 0 and returned `pending` for all six Manual rows. Each phase's recorded implementation commit (`aed13dc`, `9111645`, `2c1c9f5`) is an ancestor of the recorded head. No malformed, n/a, or paid rows exist in this scope.

Logs: `/tmp/cast-tv-s09-full-review.8BWmbO/classification.log`, `source.log`, `suite.log`, `pyflakes.log`, `wording.log`, `diff-check.log`, and `acceptance.log` in the same directory.

## Review Notes

- **Bookkeeping in diff**: context/changes/s09-share-link-photos/change.md, context/changes/s09-share-link-photos/follow-ups/review-fixes.md, context/changes/s09-share-link-photos/plan-brief.md, context/changes/s09-share-link-photos/plan.md, context/changes/s09-share-link-photos/research.md, context/changes/s09-share-link-photos/reviews/impl-review-phase-1-aed13dc.md, context/changes/s09-share-link-photos/reviews/impl-review-phase-2-9111645.md, context/foundation/roadmap.md.
- Both independent, read-only review passes completed: plan drift and safety/quality/pattern compliance. All substantive changed files are planned; app.js and the generic media probe are unchanged. The earlier reports cover individual phases, so this full report neither supersedes them nor resumes their triage.
- Lessons: 1 of 6 entries explicitly applies to impl-review (A ticked manual row needs a written observation). All six entries were read; the UI-message, secret, and manual-instruction rules were also considered where relevant. No manual row is claimed complete without an observation.
- Phase 1 contracts match: frozen Shared result; one guarded page fetch; album refusal before cover classification; distinct item counts from fetched text; validated og:image base; still probe and thumbnail; strict motion-clip status handling; unchanged video/direct-media paths and CLI photo refusal. The no-tags video fallback and one-item album behavior are explicit accepted limitations, not missing implementation.
- The phase-1 F1 fix is present in the final code and verified by regression cases: only HTTP 200/206 with a video MIME type yields a clip; 202/204 are rejected for both video/mp4 and application/mp4. No additional findings against that fix.
- Phase 2 contracts match: link records store kind/url/clip/thumb; plain photos list as photo tiles with guarded thumbnails; motion photos offer Photo by default and Clip as the H.264 stream; auto/photo selects the still; unavailable clip and unknown quality produce bad_quality. Photo and clip versions differ by =d/=m37, and clip items are relayed with download=False. Refresh rereads the page, updates addresses, and refuses a changed kind or a missing selected clip. Video refresh, deduplication, ids, and names remain as planned.
- Integration evidence includes an off-Google thumbnail redirect refused before its target is contacted, expired-photo address refresh through the page, selected clip refresh, and a POST /api/show resolving a motion-photo link to its still and sending a URI to the fake TV. Existing photo conversion, API thumbnail raster validation, and UI chooser/show paths are reused.
- Phase 3 contracts match: both link-field labels invite photos and videos; README and FR-012 describe photo/clip casting from the tab and CLI video-only handling; S-09's album question is answered and proposed S-15 records album casting, its prerequisite, and measured starting facts.
- Pattern comparisons covered picked Google Photos variants/refresh, OneDrive refresh/thumbnail paths, GoPro MediaItem construction, existing scripted share-link tests, and the guarded fetch/probe helpers. No substantive mismatch identified.
- Mutation testing skipped: no mutation tool is configured in pyproject.toml or the test plan. The expiring-cloud-address risk maps to the new photo/clip refresh closures through Phase 2, but there is no configured mutation gate to run.
- Manual acceptance remains pending for 3.3–3.8: plain photo, motion photo/clip, album refusal, video playback, two-photo slideshow, and the CLI message. No live Google requests or Samsung checks were performed; scripted tests do not establish real-TV playback.
- The review writes this report and stamps change.md as impl_reviewed; both are carried for the next workflow commit. No production edits, Progress edits, or commits were made.
