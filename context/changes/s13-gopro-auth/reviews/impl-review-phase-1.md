<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: GoPro without a hand-pasted token (S-13)

- **Plan**: `context/changes/s13-gopro-auth/plan.md`
- **Scope**: Phase 1 of 5
- **Date**: 2026-09-22
- **Verdict**: NEEDS ATTENTION
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

### F1 — A live browser's CDP failure is reported as a closed window

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `castlib/auth/browser.py:367`
- **Detail**: `_poll()` maps every `Storage.getCookies` `CdpError` to `browser_closed` after waiting up to three seconds for the process, without checking whether it actually exited. A live browser can reject the CDP command or lose the socket. The plan reserves `browser_closed` for an exited process; only `browser_failed` gets the token-paste fallback in Phase 2 (`plan.md:396-397`). Thus a failed hand-off can suppress that fallback and tell the person they closed a window they did not close. The existing tests cover process exit, not this branch with a live process.
- **Fix**: After the CDP error, report `browser_closed` only if the process exited; otherwise report `browser_failed` with a sanitized reason, and add a live-process CDP-error test.
  - Strength: Preserves the planned cancel/failure distinction and the fallback path.
  - Tradeoff: A transient CDP error ends the round; retry behavior would need a separate policy.
  - Confidence: HIGH — both the catch and Phase 2's fallback codes are explicit.
  - Blind spot: No real Edge policy failure was exercised in Phase 1.
- **Decision**: ACCEPTED — 2026-09-22, applied to `castlib/auth/browser.py` `_poll()`: after a `CdpError`, `cancelled` if a cancel came in; `browser_closed` only when the process has exited (at once, or within `CLOSE_GRACE`); otherwise `browser_failed` with the `CdpError` message (which never carries a payload) and "it was closed", since `_shutdown()` then closes the browser. No retry. The `Handoff` docstring names the two mechanism-failure codes. Tests: `test_browser.py::test_cdp_failure_with_a_live_browser_is_browser_failed` (a dropped socket with a live process → `browser_failed`, terminated; a refused command → `browser_failed`, `Browser.close`; a process that left → `browser_closed`), with a `Refuse` hook added to `tests/fakes_cdp.py`.

## Verification

- `.venv/bin/python -m pytest tests/test_cdp.py tests/test_browser.py tests/test_cli.py`: PASS, 41 tests in 4.63 s. The plan's bare `python` resolves to `/usr/bin/python`, which lacks pytest here; the project venv contains it.
- `.venv/bin/python -m pyflakes castlib tests`: PASS, no output. The project venv was needed for the same reason.
- Test workflow run `35772205093`: PASS on Ubuntu and Windows.
- Release workflow run `35772205088`: both build jobs PASS. Smoke logs print `GoPro window: /usr/bin/google-chrome` on Ubuntu and a Chrome executable under `C:\Program Files` on Windows.
- Windows artifact `cast-tv-windows-x64.exe`: downloaded successfully from run `35772205088` into `/tmp/s13-gopro-auth-phase1-artifact/`.
- Manual row 1.5: checked. `research.md` records the 2026-09-22 Fedora observation, the owner's confirmation, and the three-line module-form output. It explains that `.venv/bin/cast-tv` is absent because the package is not installed in that venv.
- Mutation check: skipped; Phase 1 files are not a §4 risk area in `context/foundation/test-plan.md`.

## Triage

2026-09-22, by the owner in the implementing session. Accepted: F1 (fix and tests applied, see its
Decision). Skipped: none. Dismissed: none.
