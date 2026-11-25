<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cast photos and videos from a Nextcloud server

- **Plan**: context/changes/s17-nextcloud/plan.md
- **Scope**: Phase 1 (phases 1–4)
- **Session**: fresh
- **Base**: d15ca6ae424dcffa7aad0dde6eac06416803a576 (merge-base with origin/main; change base for Phase 1)
- **Head**: e931d9ecf83313f3f7f34185f9112446f0769d35
- **Worktree**: included(context/changes/s17-nextcloud/plan.md) — existing SHA write-back for rows 1.1–1.3; no other local changes existed at the review boundary
- **Checks ran at**: e931d9ecf83313f3f7f34185f9112446f0769d35 (current checkout; included plan bookkeeping only)
- **Manual acceptance**: none planned for Phase 1
- **Date**: 2026-11-24
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING — local gates pass; external release gate pending |

## Findings

### F1 — A pending login start can undo Disconnect or Cancel

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/nextcloud.py:212
- **Detail**: `_start_flow()` performs the initial HTTP call before registering a flow or capturing its generation (lines 212–219). Disconnect during that call clears credentials and increments `_gen`, but the delayed start then installs its flow with the new generation. Its completed poll can persist a credential after Disconnect returned. Cancel also cannot invalidate a start that has not registered `_flow`; `_cancel_flow()` only clears the registered flow and stop event. A deterministic synthetic reproduction blocked `loginflow.start()`, called Disconnect, then released the start and supplied a successful synthetic poll/user response. Observed `disconnected` before release, then `connected; credential persisted = True`. This violates the account/cancellation intent and the source's stated rule that old-generation answers change nothing. Existing late-poll coverage begins after the flow is registered.
- **Fix**: Establish an identity for the pending start before the network call, invalidate it on Cancel/Disconnect, and check it before installing or completing the flow. Add event-controlled tests for both actions during the initial start request.
  - Strength: Covers cancellation before and after `_flow` exists without making Cancel wait for the network request.
  - Tradeoff: Adds a lifecycle state/epoch that must remain consistent with the existing flow identity and generation.
  - Confidence: HIGH — independently reproduced by two reviewers with temporary stores and synthetic callbacks.
  - Blind spot: Real server timing and browser consent remain manual acceptance in Phase 3.
- **Decision**: FIXED — recommended fix: pending-start cancellation epoch checked before flow publication, with atomic Disconnect detachment; siblings: castlib/sources/onedrive.py fixed, castlib/sources/gphotos.py fixed (Cancel during listener start), castlib/sources/gopro.py n/a (handoff registered under the source lock before asynchronous work); reopened: none.

### F2 — Late DAV answers mix old paths with the new account

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/nextcloud.py:457
- **Detail**: `_snapshot()` captures `gen` but writes each record to `_files` without checking it (lines 457–458); only `_snapshots` is guarded. `_search()` repeats the unchecked cache write and returns the old record (lines 514–516). A delayed response from account A can therefore repopulate caches after account B's sign-in cleared them. Reproduction switched the credential and incremented `_gen` while the old DAV call was outstanding, then returned A's file `51`, `old.jpg`. Observed `stale file cached = True`; `resolve('51').resolve().url` became `https://new.test/remote.php/dav/files/new/old.jpg`. This can show old account metadata or cast a different file at the same path in the new account. Suppressing only the snapshot write does not suppress the stale return or file cache.
- **Fix**: Associate DAV results and their cache/return paths with the captured account generation; reject stale listing/SEARCH results before publishing records, and prevent resolved items from silently rebinding an old path to another account. Add delayed-PROPFIND and delayed-SEARCH account-switch tests.
  - Strength: Preserves account identity across listing, lookup, and deferred media resolution.
  - Tradeoff: Requires choosing a consistent stale-operation error and checking the deferred `MediaItem.resolve` boundary as well as cache writes.
  - Confidence: HIGH — both unchecked writes are visible, and the wrong-account target was reproduced independently.
  - Blind spot: Real TV playback while switching accounts was not exercised.
- **Decision**: FIXED — recommended fix: generation-checked cache publication and returns, with deferred Nextcloud media bound to its generation; siblings: Nextcloud SEARCH, cached pagination and previews fixed, castlib/sources/onedrive.py fixed (listing, item/parent lookup, thumbnails and deferred resolution), castlib/sources/gopro.py fixed (listing and item cache writes), castlib/sources/gphotos.py n/a (Picker publication already checks generation; shared links do not use account-relative DAV paths), castlib/sources/local.py n/a (no cloud account); reopened: none.

### F3 — A stale verification can restore a removed credential

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/nextcloud.py:351
- **Detail**: `connect({})` guards its verification-state update with `self._gen == gen`, but saves a corrected user id outside that guard (lines 351–352). If Disconnect or another sign-in occurs while `loginflow.user()` is running and the returned id differs from the stored one, the old credential is saved even though the generation no longer matches. Reproduction called the real `disconnect()` from the synthetic user callback, then returned a changed user id: `credential restored = True; reported stored = True`. It can also overwrite a newer account's record. Even when remote revocation succeeds, the locally forgotten password is written back.
- **Fix**: Make the generation check, credential correction, and verification-state update one atomic adoption under the source lock; drop a stale verification result. Add tests for Disconnect and a newer sign-in during verification with a changed user id.
  - Strength: Keeps the credential and status in the same accepted generation, using the adoption pattern already present in `_finish_flow()`.
  - Tradeoff: The private-file write must share the guarded adoption section; capture the credential and generation consistently before the request too.
  - Confidence: HIGH — the unconditional save and credential resurrection were reproduced independently.
  - Blind spot: Real user-id changes were not required or exercised; all reproduction data was synthetic.
- **Decision**: FIXED — recommended fix: credential correction and verified-state adoption guarded together using an atomically captured credential/generation; siblings: Nextcloud slow Disconnect cleanup fixed, castlib/sources/onedrive.py fixed (verification adoption and post-flow account write), castlib/sources/gopro.py n/a (paste/stored verification adoption already guarded under the source lock), castlib/sources/gphotos.py n/a (TokenStore version guards credential writes and verification checks generation); reopened: none.

### F4 — Malformed authorities escape address validation

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/auth/loginflow.py:73
- **Detail**: The address contract requires malformed authorities to produce `ConfigError('bad_address')` with an explanatory message. `urllib.parse.urlsplit(text)` is outside the `ValueError` handling. Both `https://[broken` and a host followed by a fullwidth colon and `443` raise raw `ValueError` (confirmed directly), so the API's generic exception handler returns HTTP 500 `internal` instead of a validation error. The same-origin helper should also fail closed for malformed server URLs rather than raising an unrelated exception.
- **Fix**: Catch URL-parser `ValueError` at address-validation boundaries, return `bad_address` for typed input and `False` for malformed same-origin candidates, and add malformed-authority cases.
- **Decision**: FIXED — recommended fix: parser ValueError becomes bad_address and malformed origin candidates fail closed; siblings: castlib/net.py::_origin fixed for every shared origin/redirect check, castlib/sources/sharelink.py::validate n/a (already catches parser ValueError); API regression coverage confirms HTTP 400 instead of 500; reopened: none.

### F5 — Folder entries bypass the first-file-id rule

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/sources/nextcloud.py:446
- **Detail**: The Definitions require a repeated `oc:fileid` to keep its first record. Collection responses append a `Folder` and `continue` before the `seen` check, which only covers media records. A synthetic multistatus containing `first/` and `second/` with the same folder file id `51` returned both folders. A repeated id spanning a folder and a file also bypasses the shared first-record rule. Existing duplicate-id coverage only exercises media.
- **Fix**: Apply first-record file-id deduplication before branching into folder/media handling, and cover duplicate folders plus a folder/file id collision.
- **Decision**: FIXED — recommended fix: first valid file id wins before the folder/media branch; siblings: folder/folder and both folder/file orderings fixed, SEARCH n/a (lookup rather than child listing), other providers n/a (the WebDAV multistatus rule does not apply); reopened: none.

## Review Notes

- **Bookkeeping in diff**: context/changes/s17-nextcloud/change.md, context/changes/s17-nextcloud/frame.md, context/changes/s17-nextcloud/plan-brief.md, context/changes/s17-nextcloud/plan.md, context/changes/s17-nextcloud/research.md, context/changes/s17-nextcloud/reviews/plan-review.md.
- **Scope comparison**: All planned Phase 1 production/dependency/release paths and fixtures were implemented. `tests/test_api.py` is an additional, justified registry-expectation update. No scope creep. Phases 2–4 were not reviewed as implemented work; their missing UI/probe/docs changes are not findings.
- **Lessons**: All 6 of 6 ledger entries were read as required by AGENTS.md; 4 apply to this review's session baseline, acceptance audit, setup/error behavior, and secret handling. The owner-step and polled-UI rules were considered; there is no Phase 1 manual instruction or UI implementation to assess against them.
- **Progress**: Rows 1.1–1.3 carry ancestor `e931d9e`; row 1.4 is still pending, so Phase 1 has not completed every automated gate. No malformed n/a marks or unproven checked automated rows remain in the included plan. Other phases are pending. `change.md` remains `implementing`, appropriate for this phase-scoped review.
- **Acceptance script**: `bash .agents/skills/rune-impl-review/scripts/acceptance-state.sh context/changes/s17-nextcloud/plan.md` exited 0. All 11 Phase 3 manual rows (3.5–3.15) and Phase 4 row 4.2 are `pending`; none belongs to the reviewed phase. No confirmed, stale, unverifiable, or n/a manual rows. Progress was not edited by this review.
- **1.1**: `.venv/bin/python -m pytest tests/test_nextcloud.py` exited 0. Output: `35 passed in 2.91s`. Captured stdout/stderr: `/tmp/cast-tv-nextcloud-tests.pejvCm`.
- **1.2**: `.venv/bin/python -m pytest` exited 0. Output: `710 passed, 6 skipped in 55.13s` (716 collected). Captured stdout/stderr: `/tmp/cast-tv-full-suite.ma987p`. Node UI tests ran; no UI files changed.
- **1.3**: `.venv/bin/python -m pyflakes castlib tests` exited 0, no diagnostics. Captured stdout/stderr: `/tmp/cast-tv-pyflakes.MFLDhz`.
- **1.4 external**: PR #117's [release run](https://github.com/Piotr-Miller/cast-tv/actions/runs/45483432115) targets the exact reviewed head. At the final CI inspection during this review, both Windows and Ubuntu 22.04 jobs were still building with Nuitka; smoke tests had not run. This is pending evidence, not a failed execution or a passing gate. No publication or new workflow run was triggered. The separate [test run](https://github.com/Piotr-Miller/cast-tv/actions/runs/45483432075) passed on Windows and Ubuntu.
- **Reproductions**: Reviewers ran isolated Python scripts with temporary config directories and synthetic callbacks; no real stored credential or provider token was read or printed. The primary reviewer independently reproduced F1–F5. Existing automated tests do not catch these cases; no implementation or test files were edited.
- **Mutation check**: Skipped — the change touches the test plan's secret/config and release risks, but no mutation tool is configured in the manifest or test plan. No full-directory mutation command was run.
- **Uncommitted workflow output**: This report and `change.md` are carried for the next implementation commit. The pre-existing local plan SHA write-back remains untouched.

## Triage (2026-11-24)

- **Owner decision**: “1 and apply all recommended fixes” — F1–F5 and their affected sibling paths were applied in the working tree. No commit or push was made by this review.
- **Recorded revision**: The original verdict above still describes `e931d9ecf83313f3f7f34185f9112446f0769d35`; fixed decisions describe the subsequent uncommitted edits, not a new approval of that commit.
- **Sibling scope**: Targeted fixes in GoPro, OneDrive and Google Photos address the same defect classes found in F1–F3. They are covered by `tests/test_source_races.py`; no unrelated source behavior was added.
- **Disconnect ordering**: Local Nextcloud state and its credential are detached under the source lock before best-effort remote revocation. The revoke uses the captured credential. Its late result cannot clear a newer sign-in or overwrite its revoke note. This intentionally refines the plan's sequential “revoke, then forget” implementation detail to make concurrent Disconnect safe; the observable completed-disconnect contract stays the same.
- **Regression evidence**: 18 added Nextcloud cases failed against the original source, then all 53 Nextcloud tests passed. Sibling checks initially reproduced 8 failures; the existing Google Photos Disconnect guard passed the ninth case. The shared address tests also confirm malformed API input returns `bad_address` with HTTP 400.
- **Affected-suite verification**: `.venv/bin/python -m pytest tests/test_nextcloud.py tests/test_source_races.py tests/test_onedrive.py tests/test_gphotos.py tests/test_gopro.py -q -W error::pytest.PytestUnhandledThreadExceptionWarning` exited 0: `222 passed in 14.43s`. Output: `/tmp/cast-tv-triage-sources-final.gVogmp`.
- **Compatibility**: OneDrive still permits a request waiting on refresh to use a newer sign-in's token, as the existing `test_late_refresh_does_not_overwrite_a_new_sign_in` requires. HTTP results now carry the generation of the credential they actually used. The GoPro late-success test now additionally asserts cancellation and an empty cache while retaining its disconnected-state assertion.
- **Lint**: `.venv/bin/python -m pyflakes castlib tests` exited 0 with no diagnostics. Output: `/tmp/cast-tv-triage-pyflakes.PUWV3Z`.
- **Full-suite verification**: `.venv/bin/python -m pytest -W error::pytest.PytestUnhandledThreadExceptionWarning` exited 0: `737 passed, 6 skipped in 52.91s` (743 collected), with no thread-exception warnings. Output: `/tmp/cast-tv-triage-full.gQCDi5`. `git diff --check` passed.
- **Manual acceptance after fixes**: The acceptance-state script exited 0 after all source edits; all manual rows remain pending. No stale/confirmed rows exist, so no rows were reopened and no confirmations were written.
- **External gate update**: The original reviewed commit's release build and smoke test subsequently passed on both Windows and Ubuntu 22.04 in run `45483432115`. That evidence covers the recorded commit, not these uncommitted fixes. The plan's row 1.4 was updated by another writer during triage and was preserved; this review did not edit Progress.
- **Handoff**: Applied fixes and their file set are recorded in `follow-ups/review-fixes.md` and carried for the next implementation commit.
- **Triage complete**: F1–F5 FIXED; no pending, skipped, or accepted-risk findings. The original recorded-head verdict is retained; these fixes have not been committed or re-reviewed as a new revision.
