<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cloud Source UI Implementation Plan

- **Plan**: context/changes/cloud-source-ui/plan.md
- **Scope**: Phase 2 of 7
- **Date**: 2026-09-10
- **Verdict**: NEEDS ATTENTION → RESOLVED (all 4 findings fixed 2026-09-10; manual rows 2.3–2.5 still owned by the human)
- **Findings**: 0 critical, 3 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Findings

### F1 — Completed preparation can deadlock

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/photos.py:219
- **Detail**: `_submit` holds the non-reentrant `_pending_lock` when attaching `done` at line 231. If the worker has already finished, `add_done_callback` invokes `done` inline, which acquires the same lock at line 227. A fast success or failure can therefore hang preparation and block subsequent submissions. A subprocess using an already-completed Future timed out after two seconds; the current concurrency test deliberately slows conversion and misses this ordering.
- **Fix**: Register the callback after releasing `_pending_lock`, publish the cache result before removing the pending entry, and add a deterministic completed-Future regression check.
- **Decision**: FIXED — `_submit` releases `_pending_lock` before `add_done_callback`; the callback publishes to the cache first, then un-pends; `test_photos.py::test_submit_with_completed_future_does_not_deadlock` uses an already-completed Future

### F2 — Cache eviction deletes registered photo files

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: castlib/photos.py:79
- **Detail**: LRU insertion unlinks victims at lines 87–89 without consulting Registry ownership or transfers. The server still serves `item.prepared.path` at server.py:205. Preparing/registering A, then preparing B with a one-entry cache leaves A registered and unretired but its prepared file absent. The normal 200-entry/256-MB limits produce the same failure under cache pressure: subsequent HEAD/GET returns 404 despite the phase-1 lifetime guarantee. Cache hits also need protection between preparation and registry publication. The cache test currently verifies deletion without checking active routes.
- **Fix**: Coordinate prepared-file ownership with registry lifetime: reserve files through preparation/publication, retain them while registered or transferring, and release when registry eviction permits; define backpressure when retained files consume the budget.
  - Strength: Preserves the existing active/retired media URL contract and the bounded-resource intent.
  - Tradeoff: Adds lifecycle coordination and requires a policy when all capacity is retained.
  - Confidence: HIGH — reproduced missing file with an active Registry entry.
  - Blind spot: Phase 3 supervisor and prefetch integration are not implemented yet.
- **Decision**: FIXED — ownership: `prepare()` pins the prepared file for the item, `release(item)` unpins, `photos.attach(registry)` makes `Registry.remove`/`evict` call it (`Registry.on_remove` hook). Pinned entries are never deleted; their bytes still count, so the bound is enforced on the unpinned set and preparation never refuses under a fully retained budget (backpressure policy: the registry's own eviction is what frees space). `test_registered_photo_survives_cache_pressure`, `test_prepare_twice_pins_once`

### F3 — Preparation failures escape the application error model

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/photos.py:159
- **Detail**: The decode exception handler omits Pillow's `DecompressionBombError`; the temp creation/write block at lines 205–209 also lets `OSError` escape and can leave a partial file. The CLI catches only `CastError` around preparation. These expected rejection/resource-failure paths produce a traceback instead of the promised actionable preparation error. Lowering Pillow's pixel threshold and decoding a 20×20 JPEG reproduced `DecompressionBombError` with `isinstance(error, CastError) == False` without allocating a huge image.
- **Fix**: Translate decode-limit and temporary-file failures into an appropriate `CastError` with item context, clean partial output, and test both failure paths without sending SOAP.
- **Decision**: FIXED — `Image.DecompressionBombError` → `NotMedia("photo_too_many_pixels")`; temp-file `OSError` → `ConfigError("photo_write_failed")` with the partial file unlinked; `test_decompression_bomb_is_cast_error`, `test_write_failure_is_cast_error_without_partial_file`, `test_bomb_sends_no_soap`

### F4 — Oriented PNG output differs from the conversion contract

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/photos.py:187
- **Detail**: The plan says any oriented image is re-encoded to JPEG quality 92. The PNG branch instead saves PNG after transposition. An orientation-6 PNG produced image/png at 48×64: orientation works, but the output format differs from the explicit contract. No Samsung playback failure is established for this deviation.
- **Fix**: Preserve PNG output only when orientation is 1; route oriented PNG through the JPEG quality-92 branch.
- **Decision**: FIXED — PNG output only when orientation is 1 and it fits; anything transposed or scaled goes through the JPEG quality-92 branch; `test_oriented_png_becomes_jpeg`

## Scope and plan coverage

- Reviewed the uncommitted working tree over `d82a507`, the phase-1 review-fix baseline. No phase-2 commit exists yet.
- Expected tracked changes: `castlib/cli.py`, `castlib/items.py`, `castlib/media.py`, `castlib/server.py`, `pyproject.toml`, `tests/test_media.py`; new `castlib/photos.py`, `tests/test_photos.py`, and generated-fixture helpers under `tests/fixtures/`.
- `MediaItem.version` supports the planned cache key. `.gitignore` additions for build/egg-info artifacts support packaging verification. Progress checkbox updates are administrative. No unrelated feature scope was found.
- Dependencies, photo MIME filtering, Prepared-based DIDL/headers, source-field preservation, remote authorization headers, preparation-before-registration/SOAP, video-only diagnostics, and the named phase-2 tests match the plan.
- Existing config temp-directory creation/cleanup is reused. No repository AGENTS.md, foundation lessons, or foundation test-plan exists. Mutation testing was skipped because no section-4 risk area is defined.
- Canonical Progress: 8/38 checks complete overall; phase 2 is 2/5 complete and contains the first pending check. Samsung manual items remain unchecked, with no rubber-stamped completion.

## Verification

| Check | Result | Evidence |
|-------|--------|----------|
| `.venv/bin/python -m pytest tests/` | PASS | 68 passed in 4.90s, Linux / Python 3.14.7 |
| `.venv/bin/python -m pip install . --target /tmp/cast-tv-phase2-review-install` | PASS | Built cast-tv 0.2.0; installed pillow 12.3.0 and pillow-heif 1.7.0. Initial sandbox DNS failure; approved network retry succeeded. |
| Completed-Future edge-case probe | BUG REPRODUCED | Subprocess timed out after 2s in `_submit`. |
| Registered-photo cache-pressure probe | BUG REPRODUCED | A remained registered/unretired after preparing B, but A's prepared path no longer existed. |
| Decode-limit exception probe | BUG REPRODUCED | `DecompressionBombError` escaped as a non-CastError. |
| Oriented PNG probe | DRIFT CONFIRMED | Upright 48×64 result retained image/png. |

Manual checks 2.3–2.5 remain pending: JPEG/HEIC/PNG/portrait display on the Samsung, debug HEAD/GET agreement and recorded DLNA values in research.md, and real-TV video regression. Passing automated tests does not establish TV compatibility. No production code or Progress checkboxes were changed by this review.
