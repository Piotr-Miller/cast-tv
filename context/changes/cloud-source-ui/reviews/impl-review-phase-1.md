<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cloud Source UI Implementation Plan

- **Plan**: context/changes/cloud-source-ui/plan.md
- **Scope**: Phase 1 of 7
- **Date**: 2026-09-10
- **Verdict**: NEEDS ATTENTION → RESOLVED (all 7 findings fixed 2026-09-10, 46 tests)
- **Findings**: 0 critical, 5 warnings, 2 observations
- **Git scope**: `31d715d^..31d715d`; reviewed current source, identical to that commit. Existing uncommitted checklist SHA annotations were preserved.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | FAIL |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

Plan Adherence is a non-critical FAIL for missing CLI retirement/cleanup and incomplete allowed-host enumeration. No major architectural drift or critical security finding was established.

## Findings

### F1 — Cloud commands ignore CAST_TV

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/cli.py:292, castlib/cli.py:329
- **Detail**: Both cloud parsers default `--tv` to None and now call `cast()` directly. Previously the child cast-tv parser applied `CAST_TV`. With the variable set and no explicit flag, both commands now discover a renderer instead of using the configured one. Mocked both entry points with `CAST_TV=192.0.2.42`; both passed `tv=None` to cast. This can select the wrong TV or fail discovery.
- **Fix**: Give both parsers the existing cast-tv environment default and add coverage for the environment value and explicit flag override.
- **Decision**: FIXED — both cloud parsers default `--tv` to `$CAST_TV`; `test_cli.py::test_cloud_commands_honour_cast_tv`, `::test_explicit_tv_overrides_cast_tv`

### F2 — Rejected UI POST consumes its body twice

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/server.py:166
- **Detail**: The UI dispatch path drains the body before `_check_origin()`, whose rejection path drains it again at line 126. A foreign-origin POST with a nonempty body waits for bytes already consumed, delaying the required 403 until timeout. With pipelining it corrupts the following request. A handler-stream reproduction containing `{}GET /favicon.ico...` left `T /favicon.ico...` after rejection.
- **Fix**: Check the UI origin before draining, ensuring every accepted or rejected request consumes its body exactly once; cover a rejected POST followed by another request.
- **Decision**: FIXED — `_drain()` reads at most once per request (`_drained` flag) and the `/ui` branch checks Origin before draining; `test_server.py::test_rejected_ui_post_drains_body_once`

### F3 — Returning from cast leaves its server running

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: castlib/cli.py:180, castlib/cli.py:222
- **Detail**: After starting the server thread, SOAP failure returns immediately; normal completion and interruption only remove photo temporary files. No path retires the item or calls server shutdown/server_close. The plan explicitly assigns retirement to the CLI, and the refactor exposes casting as an in-process function. Calling it again in that process leaves the previous listener occupying the port and its items active. Process exit masks this in ordinary one-shot shell use.
- **Fix**: Wrap the owned server lifetime in a finally block that retires the video and subtitle and shuts down/closes the server on every exit, including SOAP failure; verify a second call can bind the same port.
  - Strength: Completes phase 1's explicit CLI ownership contract and avoids leaking listeners into callers.
  - Tradeoff: Cleanup must cover startup failures and active transfers without hanging.
  - Confidence: HIGH — all server creation and return paths are visible in cast().
  - Blind spot: Live transfer teardown was not exercised against the TV.
- **Decision**: FIXED — `cast()` wraps `_cast_on()` in `finally`: retires every registered item, `shutdown()` + `server_close()` on every exit path; `test_cli.py::test_cast_releases_port_and_retires_items_on_soap_failure`

### F4 — Allowed hosts omit some local interfaces

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: castlib/discovery.py:82
- **Detail**: The phase 1 security rule requires every local non-loopback IPv4 address. local_addresses() gathers only hostname-resolved addresses and the default-route address; its comment explicitly defers interface enumeration to phase 7. set_host() adds the TV route, but a further local interface can still be missing, causing legitimate UI/API requests through that interface to receive 403. This is an availability gap, not an origin-check bypass.
- **Fix**: Enumerate local interface addresses for the phase 1 allowlist and test a secondary address absent from hostname/default-route results; document any dependency brought forward from phase 7.
  - Strength: Satisfies the explicit boundary contract before API/UI consumers arrive.
  - Tradeoff: Brings a small part of platform work forward.
  - Confidence: HIGH — the current algorithm cannot guarantee the required set.
  - Blind spot: No multi-interface hardware reproduction was performed.
- **Decision**: FIXED — `discovery.interface_addresses()` asks the kernel per interface (`SIOCGIFADDR`, Linux) and uses `ifaddr` when installed (Phase 7 dependency, brought forward as optional); `test_discovery.py::test_allowed_hosts_cover_every_interface_address` checks against `/proc/net/fib_trie`

### F5 — Cookie-backed relay uses a nonexistent opener method

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/relay.py:35
- **Detail**: When Upstream.opener is an OpenerDirector, `_open()` calls its nonexistent urlopen method. A real build_opener() reproduces AttributeError before any network request; proxy converts that failure to 502. Cookie-backed cast-tv and cast-photos relay requests therefore cannot work. This defect is inherited: the parent cast-tv:178 contains the same call. It is included because the phase explicitly promises cookie relay behavior and introduces the typed Upstream opener contract; it is not attributed to this refactor as a regression. Existing relay tests supply no opener.
- **Fix**: Use up.opener.open when an opener exists, otherwise urllib.request.urlopen, and cover a real cookie-enabled opener against the local upstream fixture.
- **Decision**: FIXED — `relay._open()` calls `opener.open()`; `test_relay.py::test_cookie_opener_is_used_for_upstream` sends a real Netscape jar through the relay and sees the `Cookie` header upstream

### F6 — Media timeout persists into idle keep-alive

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/server.py:195
- **Detail**: _media() sets the connection timeout to 600 seconds and never restores Handler.timeout (30). After even a HEAD response, an idle reused connection can retain its worker for ten minutes instead of the planned thirty seconds. The longer timeout is useful during a transfer, but also remains active between requests.
- **Fix**: Restore the handler timeout in the media finally block after ending the transfer, and verify the post-response timeout.
- **Decision**: FIXED — `_media()` restores `Handler.timeout` in `finally`; `test_server.py::test_idle_timeout_restored_after_media_transfer`

### F7 — Completed manual checklist lacks playback evidence

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/cloud-source-ui/plan.md:1156
- **Detail**: Manual items 1.5 and 1.6 are checked and cite the implementation commit. Automated tests support the origin/token behavior, but the diff and research notes contain no observable record of real subtitle playback, relay playback/debug output, or the second-machine LAN check. This review did not repeat those manual checks. A commit reference alone cannot establish their outcome; this does not assert they were never performed.
- **Fix**: Add a short verification note identifying the samples, machine/TV, date and observed results for the completed manual checks.
- **Decision**: FIXED — verification note added to `research.md` (follow-up 2026-09-10): samples, TV, addresses, observed output; the LAN check ran from the laptop itself (`localhost`), not a second machine, and says so

## Verification

| Check | Result / actual output |
|-------|------------------------|
| python -m pytest tests/ | System Python lacks pytest. Re-ran with the existing project .venv; sandbox socket restrictions required escalation. Final result: **38 passed in 1.51s**, Python 3.14.7, pytest 9.1.1. |
| python -m pyflakes castlib tests | System Python lacks pyflakes. `.venv/bin/python -m pyflakes castlib tests`: exit 0, no output. |
| ./cast-tv --list | Outside socket sandbox: exit 0; `192.168.50.142   83" OLED`. |
| ./cast-tv --stop | Outside socket sandbox: exit 0; `Found: 83" OLED (192.168.50.142)` and `Stopped.` |
| Two registered items serve their own bytes | test_second_item_does_not_replace_first passed in the full suite. |
| Targeted read-only reproductions | Both cloud commands passed tv=None despite CAST_TV; real cookie opener raised AttributeError; rejected UI POST consumed the first two bytes of the next request. |
| Manual 1.5 / 1.6 | Recorded complete in Progress; live playback and second-machine checks not repeated. See F7. |
| Mutation testing | Skipped: no context/foundation/test-plan.md or designated section 4 risk areas exist. |

## Scope assessment

Phase 1 Progress is 6/6 complete; whole-plan Progress is 6/38, with Phase 2 next. change.md was implementing, updated 2026-09-10; this review stamps impl_reviewed as required without editing Progress. No lessons.md or applicable AGENTS.md was found.

Package/shims, exception model, shared media helpers, registry methods, token routes, local range fixes, relay resolver/Bearer/retry behavior, config/cache and all named phase 1 regression tests are present. The additional net.py, test_config.py, package marker files and ignore entries support planned extraction/testing and do not constitute scope creep. Deferred source UI, photo pipeline and platform packaging were not treated as missing phase 1 work.

The two parallel passes covered plan drift and safety/pattern compliance. Findings were reconciled against the parent commit; in particular F5 is explicitly inherited. Source code was not changed during review.
