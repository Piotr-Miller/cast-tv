<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: GoPro without a hand-pasted token

- **Plan**: context/changes/s13-gopro-auth/plan.md
- **Scope**: Phase 3 of 5
- **Date**: 2026-09-23
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Failed GoPro reconnect loses the cached list

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/ui/app.js:272
- **Detail**: Phase 3 adds a reconnect button to the expired GoPro banner. `connect()` marks the cached list unloaded as soon as the connect API accepts `{fresh: true}` or `{cancel: true}`. If the browser round is canceled, closed, times out, or fails to launch, GoPro remains expired, but `listVisible()` then returns false. The last fetched list and its banner disappear, although the banner is intended to sit over that list. The reset predates Phase 3, but this phase makes the browser round reachable from the banner.
- **Fix**: Keep the cached list marked loaded during a GoPro browser round and its cancellation; invalidate it only after a new token is verified, then fetch the new list. Cover an expired list followed by an unsuccessful reconnect in a UI interaction check.
- **Decision**: FIXED (2026-09-23, triage). Accepted as stated, and the fix is generic rather than GoPro-only because the transition rule is needed for the hand-off's success anyway: the captured session arrives through the status poll, not through the `connect` answer, so "invalidate only after a new token is verified" has to watch the poll. `connect()` no longer marks the list unloaded; `refresh()` calls a new `watchSources(s)` before the status lands, which marks a source's list unloaded only when that source goes from not-connected to `connected` (a paste, a stored token verified, a hand-off, a device code, a consent), after which `ensureList` fetches again. A round that ends without a session (`{fresh: true}` then cancelled, closed, timed out or failed to open) leaves `loaded` alone, so `listVisible()` stays true and the expired banner keeps sitting over the last list. OneDrive and Google Photos get the same behaviour for a cancelled consent or device code from their banners (the same shared `connect()`). The interaction check: `tests/ui_driver.js` runs `castTv()` from `app.js` in node against scripted `/api` answers (no browser, no Alpine; the test is skipped without `node`, which both CI runners carry), and `test_ui.py::test_gopro_expired_list_survives_a_failed_reconnect` walks connected → expired → `openWindow` → expired again → connected, asserting the list stays visible after the failed round and is fetched exactly twice. Red on the unfixed `app.js` (the "kept" read was `false`); green after. `tests/test_ui.py`: 10 passed; `node --check castlib/ui/app.js` and pyflakes clean; the full suite in the fix commit's note.

## Verification

- `.venv/bin/python -m pytest tests/test_ui.py`: 9 passed.
- `.venv/bin/python -m pytest`: 336 passed, 1 skipped.
- `.venv/bin/python -m pyflakes castlib tests`: passed (no output).
- `node --check castlib/ui/app.js`: passed (no output).
- Manual rows 3.4 and 3.5 are checked and have dated Fedora observations, including the owner's confirmation, in `research.md` under Phase 3.
- `research.md` records the phase commit's Ubuntu and Windows CI suite pass (run 35916371410).
- Scoped mutation testing skipped: phase 3 touches no file identified as a mutation risk area in `context/foundation/test-plan.md` §4.
