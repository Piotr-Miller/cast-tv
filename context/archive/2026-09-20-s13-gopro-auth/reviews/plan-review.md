<!-- PLAN-REVIEW-REPORT -->
# Plan Review: GoPro without a hand-pasted token (S-13)

- **Plan**: `context/changes/s13-gopro-auth/plan.md`
- **Mode**: Deep
- **Date**: 2026-09-21
- **Verdict**: REVISE
- **Findings**: 1 critical, 2 warnings, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Requirement Definition | WARNING |
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | FAIL |

## Grounding

10/10 existing paths verified; 5 planned paths are explicitly new. Brief and plan agree. The Progress section matches the five phases and their success criteria. `docs/reference/contract-surfaces.md` is absent.

## Findings

### F1 — `CAST_TV_BROWSER` semantics contradict the fallback tests

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Phase 1 browser contract; Phase 3 and Phase 5 fallback tests
- **Detail**: The contract puts `CAST_TV_BROWSER` first but also restricts candidates to existing files (`plan.md:219-224`). Manual tests set it to `/nonexistent` and expect a paste fallback (`plan.md:509-511,643-645`). Under the stated candidate rules, that path is skipped and Chrome or Edge is selected, so the tests cannot produce the expected result. The override's intended semantics are also unresolved in Definitions.
- **Fix**: Define `CAST_TV_BROWSER` as an exclusive override when set. Preserve an invalid configured value as a launch failure so the UI presents `browser_failed` and the fallback block.
- **Decision**: ACCEPTED — 2026-09-21, applied to `plan.md`: `candidates()` treats a set `CAST_TV_BROWSER` as the only candidate, used even if missing (the `GOOGLE_CLIENT_JSON` rule, `loopback.py:69-71`); `describe()` names it with "(not found)"; a new Definitions row "the override"; tests `test_env_override_is_exclusive`, `test_missing_override_is_browser_failed`, and a `--version` case in `test_cli.py`. Rows 3.5, 5.6, 5.10 now exercise the fallback as written.

### F2 — Window-capture metadata is lost after restart

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: End-State Alignment
- **Location**: Phase 2 timing fields and Migration Notes
- **Detail**: `captured_at`, `captured_by`, `cookie`, `last_success_at`, and `first_401_at` are described as in-memory fields (`plan.md:341-350`). The token remains in the existing raw token file (`plan.md:710-713`). After restarting cast-tv, the source cannot distinguish a window capture from a paste or reconstruct the observed period. The promised header and Diagnostics data disappear or become “token stored”.
- **Fix**: Persist non-secret session metadata in an atomic private sidecar under `config_dir()`, load it with the token, remove it during `disconnect()`, and add restart coverage.
  - Strength: Keeps the observation and capture source available across normal restarts.
  - Tradeoff: Adds a small storage and migration contract.
  - Confidence: HIGH — the plan defines only in-memory fields and a raw token file.
  - Blind spot: Metadata behavior when a token is replaced outside cast-tv needs a rule.
- **Decision**: ACCEPTED — 2026-09-21, applied to `plan.md` Phase 2: `config_dir()/gopro-session.json` via `write_private`, holding `captured_at`, `captured_by`, `cookie`, `last_success_at`, `first_401_at` and `token_mtime`, never the token; written by `save_token` (so the paste and `cast-gopro --token` are marked `paste`) and by the hand-off; trusted only while `token_mtime` equals the token file's mtime (a token replaced by hand → `captured_by: "unknown"`, `age` from the mtime as today — the rule for the blind spot); `GOPRO_TOKEN` keeps metadata in memory; `last_success_at` written at most once per 60 s and always on the first 401; removed with the token. Tests `test_session_metadata_survives_a_restart`, `test_a_replaced_token_file_drops_the_metadata`, `test_env_token_keeps_metadata_in_memory`, `test_last_success_write_is_throttled`; Migration Notes and the README "Where files live" row updated.

### F3 — Diagnostics behavior is promised but not concretely implemented

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 3 overview; Phase 5 rows 5.3 and 5.12
- **Detail**: The plan promises Diagnostics cards containing the observed period, cookie expiry, last success, and first refusal. Phase 3 specifies gate markup and helpers but no Diagnostics markup, binding, error-recording path, or card test. The current panel renders recorded errors and hints (`castlib/ui/index.html:436-478`), while source status is separate. The implementer must decide how the metadata reaches the panel.
- **Fix**: Specify the exact Diagnostics data path and UI location, then add a test for the rendered observed-period text.
  - Strength: Makes the promised result implementable and testable.
  - Tradeoff: Requires a small additional UI change and an explicit status-to-panel binding.
  - Confidence: HIGH — the current Diagnostics panel reads recorded errors, not source status.
  - Blind spot: The desired presentation before the first 401 is not specified.
- **Decision**: ACCEPTED (variant) — 2026-09-21, applied to `plan.md`. The finding is stronger than written: a 401 from a source route never reaches the ring today (`api.py:57-59` answers JSON; only `app.py:206` and `supervisor.py:273,366` push). Fix: a `report` seam on `GoProSource`, set by `App.__init__` to `errors.push` (like `open_browser`, `app.py:173`), called by `_call` once on the transition to `expired` with the observed-period `hint`; the panel's generic hint template (`index.html:475-477`) renders it, no markup change. Before the first 401: the header's `age` only; raw fields API-only (`GET /api/sources/gopro`, row 5.3); the banner carries no times (the owner's round-2 answer). Test `test_api.py::test_first_401_lands_one_diagnostics_card`, `test_gopro.py::test_first_401_reports_once`. Known double card: a 401 during a cast also arrives through the supervisor; accepted.

## Triage

2026-09-21, in the planning session that wrote the plan. Accepted: F1, F2, F3 (all applied to
`plan.md` and `plan-brief.md`). Skipped: none. Dismissed: none. The plan's Definitions table
also had its Phase 5 row numbers corrected to match `## Progress` (5.4→5.6, 5.8→5.10 and so on),
noticed while applying F1.
