<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Photos through share links

- **Plan**: context/changes/s09-share-link-photos/plan.md
- **Scope**: Phase 1 (phases 1–3)
- **Session**: fresh
- **Base**: ccca7cb98c85181b7a9178a22985337cd0d1eee4 (merge-base; also parent of phase 1 Progress SHA)
- **Head**: aed13dc6b1eb16a6e342d793ceb63f93942f2877
- **Worktree**: included(context/changes/s09-share-link-photos/plan.md)
- **Checks ran at**: aed13dc6b1eb16a6e342d793ceb63f93942f2877
- **Manual acceptance**: none planned for phase 1
- **Date**: 2026-10-13
- **Verdict**: APPROVED
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

### F1 — Clip probe accepts unsupported success statuses

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/sources/sharelink.py:243
- **Detail**: Phase 1 requires rejecting HTTP statuses other than 200/206, with 404 alone indicating no clip. `_clip()` records the status but accepts any normally returned response whose type is `video/*` or `application/mp4`. The scripted urllib transport reproduced `shared()` returning a non-null clip for both 202 and 204 labelled `video/mp4`, including an empty 204 response. This can offer a Clip variant when the endpoint has no playable response. The new error cases cover 403/429/503 and 200 HTML, but leave this status branch untested. The other classification contracts match the plan.
- **Fix**: Require status 200 or 206 as well as a video type before returning the clip; add scripted 202/204 cases asserting `clip_probe_failed` and the returned status/type in the message.
- **Decision**: FIXED — require 200/206 plus a video MIME type; siblings: none (searched clip probes and video MIME checks throughout castlib and tests; castlib/media.py n/a, its general probe contract is explicitly unchanged by this plan; castlib/relay.py n/a, it forwards already-resolved media and supplies a MIME fallback rather than detecting clips); reopened: none.

## Verification

All commands ran against the recorded head's unchanged code in the current checkout; only the plan's three Progress SHA suffixes differed from HEAD.

| Progress row | Command | Exit | Actual output |
|-------------|---------|------|---------------|
| 1.1 | `.venv/bin/python -m pytest tests/test_gphotos.py -q -p no:cacheprovider -k "share_link_album or share_page_photo or share_page_motion"` | 0 | `18 passed, 56 deselected in 0.29s` |
| 1.2 | `.venv/bin/python -m pytest -q -p no:cacheprovider` | 0 | `357 passed, 1 skipped in 30.75s` |
| 1.3 | `.venv/bin/python -m pyflakes castlib tests` | 0 | No output. |

Stdout/stderr were captured before inspecting output: `/tmp/s09-review-p1-classification.log`, `/tmp/s09-review-p1-suite.log`, `/tmp/s09-review-p1-pyflakes.log`. Exit statuses came from each command, not a pipeline.

The additional read-only reproduction used `tests/test_gphotos.py` through `runpy`, its `_scripted_links` helper, and a temporary `pytest.MonkeyPatch` context. A normal photo page and valid still were followed by an empty clip answer labelled `video/mp4`: 200, 206, 202 and 204 each returned a clip. No production code or test files were edited.

## Review Notes

- **Bookkeeping in diff**: context/changes/s09-share-link-photos/change.md, context/changes/s09-share-link-photos/plan-brief.md, context/changes/s09-share-link-photos/plan.md, context/changes/s09-share-link-photos/research.md, context/foundation/roadmap.md.
- Local changes included: plan.md's SHA write-back for rows 1.1–1.3. No local changes excluded. The report and carry updates were created after verification.
- Phase 1 rows 1.1–1.3 carry the current commit, establishing implementation evidence. Phases 2 and 3 remain pending; change.md's `implementing` status agrees with that state. No malformed or n/a rows, and no paid checks, in this scope.
- Acceptance script exited 0. Phase 1 has no Manual rows. Out-of-scope phase 3 rows 3.3–3.8 are all pending; no confirmation inferred from automated checks.
- Lessons: read all 6 entries; 1 of 6 explicitly selects impl-review (`A ticked manual row needs a written observation`). No manual rows in the reviewed phase.
- Both review passes ran in this session because the substantive diff contains only two files. Plan drift checked every Phase 1 contract. Pattern comparisons used the existing shared fetch/probe helpers in castlib/net.py and castlib/media.py, source HTTP handling in castlib/sources/gphotos.py and castlib/sources/onedrive.py, and the existing scripted share-link tests.
- Album refusal precedes cover classification in both callers; distinct-item counting, one-item albums, guarded og:image selection, photo/thumbnail results, 404 handling, network failures and redirect refusal match the plan. Existing video probing and direct-media behavior are preserved. No changes to probe_media(), CLI photo casting, or the excluded motion-photo variants.
- Mutation testing skipped: no mutation tool is configured in the manifest or test plan. No live Google requests or TV acceptance checks were performed.
- Overall APPROVED with one minor warning, as allowed by the skill's verdict rules; F1 was subsequently fixed in triage below. This verdict covers phase 1 only.

## Triage verification (2026-10-13)

- The owner selected Fix now for F1. The fix is uncommitted on top of aed13dc6b1eb16a6e342d793ceb63f93942f2877; this section records verification of that worktree, not a new review of a committed revision.
- Changed castlib/sources/sharelink.py: accept a clip only for 200/206 with a video MIME type; make the failure message accurate for unsupported statuses carrying a video MIME type.
- Changed tests/test_gphotos.py: reject 202/204 for both video/mp4 and application/mp4, assert status and MIME in error messages, and exercise both 200 and 206 on the redirected successful clip path.
- Regression proof before the production edit: `.venv/bin/python -m pytest tests/test_gphotos.py -q -p no:cacheprovider -k 'share_page_motion'` exited 1: `4 failed, 8 passed, 67 deselected in 0.65s`. All four new 202/204 cases failed because UpstreamError was not raised. Output: `/tmp/s09-review-f1-red.log`.
- Phase 1 classification command exited 0: `23 passed, 56 deselected in 0.27s`. Output: `/tmp/s09-review-f1-classification.log`.
- Whole-suite command exited 0: `362 passed, 1 skipped in 30.76s`. Output: `/tmp/s09-review-f1-suite.log`.
- Pyflakes command exited 0 with no output. Output: `/tmp/s09-review-f1-pyflakes.log`. `git diff --check` also exited 0.
- Acceptance script exited 0 after the edits; rows 3.3–3.8 remain pending. No stale checked Manual rows, no reopening, and no Progress edits by triage.
- Follow-up disposition: F1 applied and verified in follow-ups/review-fixes.md; no pending findings. No commit made by this review.

## Review-note resolutions (2026-10-13)

The owner requested adjudication of the review notes, specifically whether a network failure on `=d` should be `probe_failed` or `no_media`. These resolutions supplement the recorded review; they do not replace its revision boundary or count as manual acceptance. No production code, tests or Progress rows were changed for this adjudication.

### Network failure while probing the still (`=d`)

- **Decision**: `UpstreamError("probe_failed")` is correct; treating a transport failure as `NotMedia("no_media")` is dismissed as a misreading of the helper's contract. No implementation defect found.
- **Plan evidence**: Phase 1 uses `probe_media(base + "=d", kinds=("photo",))` and maps “no answer” to `NotMedia("no_media")`. The plan's Key Discoveries explicitly states that this helper returns `None` for HTTP errors or successful answers of another type, and raises `UpstreamError` for network failures. Its behavior for other callers must remain unchanged. “No answer” in that clause therefore means a returned `None`, not every failure to obtain media.
- **Implementation evidence**: castlib/media.py:178–204 defines and implements that distinction. castlib/sources/sharelink.py:252–261 invokes the helper directly: only a falsy returned result reaches `_no_media()`; a network exception propagates as `probe_failed`. The paste fails before the motion-clip probe. Calling this `no_media` would incorrectly classify an untested photo as absent during a temporary outage.
- **HTTP distinction**: HTTP 404/403/503 and an answered non-photo MIME type at `=d` currently produce `no_media`, because the unchanged generic helper returns `None`. This matches the Phase 1 contract; the stricter HTTP-status treatment is specific to `=m37`, where only 404 establishes that a photo has no clip. This resolution does not claim that `=d` HTTP 503 proves the underlying photo does not exist.
- **Verification**: an additional read-only script used the existing `_scripted_links` transport and temporary MonkeyPatch contexts. Connection reset and timeout each yielded `UpstreamError("probe_failed")`, with the `=d` URL and cause in the message. HTTP 404/403/503 and 206 HTML each yielded `NotMedia("no_media")`. All six scenarios asserted exactly the page/redirect/`=d` requests and no `=m37` request. Exit 0; output: `/tmp/s09-review-d-probe-resolution.log`. No live requests were sent.

### Remaining review notes

| Note | Resolution |
|------|------------|
| F1: unsupported success statuses at `=m37` | FIXED and verified during triage above; remains uncommitted. The original finding and revision verdict are retained as history. |
| Album classification and cover ordering | No drift: refuse several distinct items before classifying their cover, in both callers. The limited sample heuristic and treating a one-item album as its item are explicit plan decisions, not missing implementation. |
| Missing Open Graph tags | Accepted limitation recorded in the plan on 2026-10-13: retain video probing. A possible motion-photo `=dv` fallback is not an additional finding against this scope. |
| Phase 1 automated evidence | All three gates passed, including after F1's fix. The six additional `=d` scenarios establish the disputed behavior; no further suite run is needed for this documentation-only adjudication. |
| Manual acceptance and TV behavior | No Manual rows in phase 1. Phase 3 rows remain pending and require the owner's observations; this review does not confirm or reopen them. |
| Bookkeeping and local Progress suffixes | Workflow records, not scope creep. No excluded local edits or unexplained code files in the reviewed diff. |
| Lessons and pattern checks | No additional substantive violation identified. The manual-observation lesson has no phase 1 row to enforce. |
| Mutation and live testing | Justified omissions: no configured mutation tool; live Google/TV acceptance is not a phase 1 automated gate. |

- **Resolution outcome**: no new findings; F1 is FIXED and all review-note questions are resolved. Phase 1 remains APPROVED, with the historical warning and uncommitted fix documented. Phases 2–3 remain outside this approval.
