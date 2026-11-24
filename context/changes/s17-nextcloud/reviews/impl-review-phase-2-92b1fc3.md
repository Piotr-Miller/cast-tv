<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cast photos and videos from a Nextcloud server

- **Plan**: context/changes/s17-nextcloud/plan.md
- **Scope**: Phase 2 (phases 1–4)
- **Session**: fresh
- **Base**: d57ddf6 (d57ddf6f5911a798958f17cccd50d7de7df4ca4a; previous phase's commit, the Phase 1 impl-review fixes)
- **Head**: 92b1fc3 (current HEAD)
- **Worktree**: included(context/changes/s17-nextcloud/plan.md) — the Progress SHA write-back for rows 2.1–2.3 only; no other local changes
- **Checks ran at**: 92b1fc3 (current checkout; the included change is plan bookkeeping only)
- **Manual acceptance**: none planned for Phase 2
- **Date**: 2026-11-24
- **Verdict**: APPROVED
- **Findings**: 0 critical, 0 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS (1 observation) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — The probe's own reads appear in the debug log as the TV's requests

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/supervisor.py:346-350 (with castlib/relay.py:58, :68 and castlib/items.py:143)
- **Detail**: The probe now reads `/m/<token>/<id>` through cast-tv's own server, so every ffprobe request runs `Handler._media` → `registry.touch` (`item.requests += 1`) and `relay.proxy`, which writes `[tv] GET /m/… Range=…` and `[tv] upstream: 206 …` when the item is in debug mode (`server.py:83-86`). Scenario: the owner runs `python -m castlib -d` (the setting of every Phase 3 manual row), the TV refuses an OM film; after the transport reports `STOPPED`, the terminal shows a further burst of `[tv]` GETs and upstream 206s that are ffprobe's, not the TV's, with nothing marking where the probe starts or ends. A reader of that log (the research.md observation for a refusal) can conclude the TV kept fetching after it gave up. The inflated `requests` counter itself has no consumer after the failure (`_never_started` checks it before the probe; no UI or CLI reads `as_dict()["requests"]`), so this is diagnosability only, not behaviour.
- **Fix**: In `_never_started`, when `item.debug`, write one line before and one after `explain_failure` (e.g. `[probe] ffprobe reads <id> through cast-tv's relay` / `[probe] done`), so the `[tv]` lines in between are attributable; add a one-line test with a debug item asserting the markers bracket the probe's requests in captured stderr.
- **Decision**: FIXED (owner decision 2026-11-24: fix now) — `Cast._probe_note` writes `[probe] ffprobe reads <id> through cast-tv's relay` (or `from its file`) before `explain_failure` and `[probe] done` after it, only for a debug item; `test_refusal_probe_marked_in_debug_log` asserts every `[tv] GET /m/` line of the probe falls between the markers and no password reaches stderr. Deliberate break (markers silenced) turned it red; restored, green. Gate: `tests/test_supervisor.py` 38 passed; full suite 742 passed, 6 skipped; pyflakes exit 0.

## Review Notes

- **Bookkeeping in diff**: context/changes/s17-nextcloud/plan.md (committed: rows 2.1–2.3 ticked; worktree: their ` — 92b1fc3` suffixes).
- **Plan drift**: `castlib/supervisor.py` — MATCH: a video with `item.path` is probed on the path; else, with `item.resolve` and `item.id`, at `app.server.media_url(item)`; no id, no probe; the old `item.resolve().url` branch and its try/except are gone. `tests/test_supervisor.py` — MATCH: the assertion at old line 64 now expects the media URL and asserts the CDN address is absent; the four named tests exist, and the reading double really GETs `bytes=0-99` from a Basic-gated upstream (bytes, the header seen upstream, hint, registered-and-not-retired during the probe, retired after). No unplanned files; no scope creep.
- **Ordering verified**: `_never_started()` is evaluated inside `_poll` before `_finish` retires the item (`supervisor.py:322`), and `/m/<token>/<id>` is dispatched before the Host/Origin check (`server.py:187-196`), so the probe is served. The server binds `0.0.0.0` in both entry points (`app.py:231`, `cli.py:64`), so ffprobe reaching the LAN address of `media_url` is a local connection. Downloads complete in `_prepare` before registration, so a `download=True` item always has `item.path` at probe time.
- **Credential on the command line**: ffprobe's argument now carries cast-tv's per-run media token instead of the upstream URL. Before, for OneDrive/GoPro that argument was a pre-signed provider URL (`?sig=`-style), so this is a net reduction; the media token is already sent in clear over the LAN to the TV, as the plan accepts (Critical Implementation Details).
- **Behaviour change for every remote source** (intended, plan Desired End State): the probe now reads what the TV was given (relay headers, opener, re-resolve on 401/403/404), at the cost of the probe's bandwidth going through the relay; ffprobe's 90 s timeout bounds it as before. A stop or replace during the probe still does not kill ffprobe — pre-existing, unchanged.
- **Untested guard**: the `item.id` condition (no id, no probe) cannot be reached after `_register()`; it is defensive and has no test. Not a finding.
- **Test helper**: `_BasicUpstream` re-implements part of `tests/conftest.py::_StubHandler` because the shared stub cannot gate on a request header; justified, not a finding. A later change could give the shared stub a `require_headers` option.
- **2.1**: `.venv/bin/python -m pytest tests/test_supervisor.py` exited 0: `37 passed in 12.22s` (33 at planning + 4 new).
- **2.2**: `.venv/bin/python -m pytest` exited 0: `741 passed, 6 skipped in 54.35s`.
- **2.3**: `.venv/bin/python -m pyflakes castlib tests` exited 0, no output.
- **CI**: PR #117's head is still d57ddf6; 92b1fc3 is not pushed, so the Windows runner has not seen the new tests. They use only 127.0.0.1 sockets and `urllib`, nothing OS-specific.
- **Acceptance script**: `bash .claude/skills/rune-impl-review/scripts/acceptance-state.sh context/changes/s17-nextcloud/plan.md` exited 0; rows 3.5–3.15 and 4.2 are `pending`; none belongs to Phase 2. Row 3.10's surface names `castlib/supervisor.py`, which this phase changed; it is unticked, so nothing is stale.
- **Lessons**: 6 of 6 entries read (the ledger is 5 KB); applicable here: the manual-row observation rule (no Phase 2 manual rows) and the secret rule (no provider credential reaches the probe's command line). The owner-step, branch, copied-file and polled-UI rules do not touch this diff.
- **Mutation check**: skipped — the change touches the test plan's risk "The TV refuses or stalls on a source" (supervisor), but no mutation tool is configured in `pyproject.toml` or `context/foundation/test-plan.md` §3.
- **Uncommitted workflow output**: this report is carried for the next implementation commit; `change.md` already reads `updated: 2026-11-24` and stays `implementing` (phase review), so it was not modified. Triage was not run (headless subagent run); F1's decision is PENDING.
