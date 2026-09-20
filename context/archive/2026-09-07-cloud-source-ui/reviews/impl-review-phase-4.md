<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cloud Source UI Implementation Plan

- **Plan**: context/changes/cloud-source-ui/plan.md
- **Scope**: Phase 4 of 7 — GoPro tab
- **Date**: 2026-09-12
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 0 observations
- **Git scope**: ed66f75..58a8896; implementation fcffb7e, verification notes 58a8896. Working tree was clean at review start.
- **Progress**: 24/40 overall; Phase 4 is 5/6, with manual row 4.6 pending. Current phase remains 4.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING — phone verification pending |

The two warnings affect the required token-recovery path and are substantive, so approval is withheld despite passing automated criteria. No missing planned component or critical defect was found.

## Findings

### F1 — An environment token overrides a successful paste

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/gopro.py:445
- **Detail**: `connect()` verifies and saves the fresh pasted token and reports connected, but subsequent list, thumbnail and resolve operations call `token()`, which prefers `GOPRO_TOKEN` over the saved file (lines 55–56). Starting the app with an expired environment token therefore makes a successful re-paste immediately fail again on the next listing. An offline mocked reproduction confirmed connected after the paste, the old effective credential, then expired on listing. This breaks the phase's recovery behavior for a supported credential source.
- **Fix**: Give the source one effective session credential initialized from the existing environment/file lookup; a successfully verified paste replaces it for subsequent operations. Cover replacement of an expired environment credential and consistent disconnect behavior.
  - Strength: Verification and all subsequent requests use the same credential while preserving startup environment support.
  - Tradeoff: Credential ownership must be coordinated with CLI compatibility and disconnect behavior.
  - Confidence: HIGH — deterministic reproduction and direct call-site evidence.
  - Blind spot: The failure was reproduced offline, not with a live expired environment credential.
- **Decision**: FIXED (2026-09-12), with Piotr's three rules. `GoProSource` owns one session credential: read from `GOPRO_TOKEN` or the file on first use, replaced by a verified paste (`_adopt`), cleared by `disconnect()` together with the file; after a disconnect this process never falls back to the environment (`_loaded` stays set), while `token()` - the CLI and a new process - still reads it. Every request goes through `_call(fn)` with the session credential. `test_env_token_is_replaced_by_a_verified_paste` walks the whole scenario: expired env token → verify 401 → paste → list/thumb/resolve send the paste → disconnect → `no_token`, nothing sent with the env token, `token()` still answers for a new process.

### F2 — A stale request can expire a fresh connection

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/gopro.py:383
- **Detail**: `_call()` updates shared authentication state unconditionally after the network operation. An old-token listing or thumbnail request can return 401 after `connect()` has verified and saved a fresh token, overwriting its connected state with expired. The lock only serializes writes; it does not associate a result with the credential it used. A deterministic offline reproduction held an old request with threading events, completed a fresh connection, then released the old AuthError and observed expired. An older success can likewise clear a later expiry.
- **Fix**: Capture credential identity/generation with each request and reject stale authentication-state updates after reconnect/disconnect; preserve a newer expiry against older successful requests. Add controlled concurrent-response regression coverage.
  - Strength: Keeps concurrent thumbnail/list requests from undoing a successful recovery; complements F1's credential ownership.
  - Tradeoff: Requires coordinated request bookkeeping and ordering tests across connection operations.
  - Confidence: HIGH — deterministic concurrent reproduction and unconditional writes at the reported location.
  - Blind spot: Timing was controlled offline; the race was not forced against the live CDN/API.
- **Decision**: FIXED (2026-09-12), together with F1 and per Piotr's rules: a verified connection and a disconnect bump a generation; each request captures token and generation together; a 401 sets `expired` only while its generation is current; a plain list/thumb/resolve success never restores `connected` - only a successful verification (`connect`) does. Deterministic tests with `FakeGoPro.before_answer` holding an answer on a threading event: `test_stale_401_cannot_expire_a_fresh_connection`, `test_answer_after_disconnect_changes_nothing`, `test_older_success_cannot_clear_a_newer_expiry`. Three of the four new tests fail on the pre-fix code; `test_answer_after_disconnect_changes_nothing` passed there because the old `status()` read the deleted file, and stays as a guard on the new `_loaded` semantics.

## Verification

| Criterion | Result and evidence |
|-----------|---------------------|
| 4.1 Test suite | PASS: `.venv/bin/python -m pytest tests/` — 151 passed in 16.77s, Python 3.14.7 on Linux. |
| 4.2 Live listing | PASS: `.venv/bin/python cast-gopro -n 5` — exit 0, seven output lines. |
| 4.2 Live resolution | PASS: `.venv/bin/python cast-gopro 1 --url-only` — exit 0, signed HTTPS URL returned; URL suppressed from review output. |
| 4.3 Token gate/list/age | Existing written observation in research.md:650; live stored-token verification and thumbnails, invalid paste, valid literal paste against scripted API. No fresh browser run in this review. |
| 4.4 Heavy proxy/source | Existing real-TV observation in research.md:651: proxy played; source never started and failed after budget. Subsequent diagnostic hint change is explicitly unit-tested only. |
| 4.5 Expiry/recovery | Existing observation in research.md:652: live 401 preserved list; recovery via restored token and `connect {}`. Literal banner paste used scripted API. These limits are disclosed, not treated as proof of the concurrency/env cases above. |
| 4.6 Phone paste/cast | PENDING, correctly unchecked. No phone observation supplied. |

Initial direct shim invocation used the system Python, which lacked `pillow_heif`; rerunning through the project's virtual environment resolved that environment mismatch. Live API checks initially hit sandbox DNS restrictions and passed after an escalated rerun. The listing check refreshes the normal CLI metadata cache. No token was changed or playback started by this review.

Mutation testing skipped: no `context/foundation/test-plan.md` exists to designate a §4 risk area.

## Scope and evidence assessment

- The Source/Entry/Listing contract in `castlib/sources/base.py` already existed from Phase 3; no missing change there.
- Source registration, API raster sniffing, media probe changes, CSS and supervisor diagnostics support Phase 4. Thumbnail/octet-stream rules, bare-id resolution and heavy defaults are documented in the plan Addenda and research.
- Kind mapping, unknown filtering, photo/source ranking, livephoto still selection, signed-URL re-resolution, CLI behavior, pagination and variant selection match the phase intent.
- Real API probes and sanitized fixtures are recorded. LivePhoto was unavailable in the account; its fixture is openly synthetic.
- Verify-before-save behavior is explicitly documented in research.md:658 and covered by a regression test; retaining a working token after a bad paste is a justified adjustment.
- The accepted lessons rule was checked against the manual notes; checked rows have written observations with the limitations above. Progress checkboxes were not altered by this review.

## Triage

Both findings await a decision. No application code was edited. Resume with `/10x-impl-review context/changes/cloud-source-ui/reviews/impl-review-phase-4.md`.

## Triage (2026-09-12)

| Outcome | Findings |
|---|---|
| Fixed | F1, F2 (one change: the session credential with a generation) |
| Skipped / accepted / dismissed | none |

Suite after triage: 155 passed (151 before; 4 new tests), `pyflakes` clean.

