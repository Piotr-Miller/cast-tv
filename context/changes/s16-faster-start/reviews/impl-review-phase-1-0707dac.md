<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: A faster-starting release file (Nuitka)

- **Plan**: context/changes/s16-faster-start/plan.md
- **Scope**: Phase 1 (phases 1–7)
- **Session**: fresh
- **Base**: a85f59d036cbdaea669977ae312028b774b7d5a5 (explicit)
- **Head**: 0707daca1a5262a34486a8d4543beff62fc3af0e
- **Worktree**: excluded (clean at review start)
- **Checks ran at**: 0707daca1a5262a34486a8d4543beff62fc3af0e
- **Manual acceptance**: 1 of 1 confirmed (1.7 current)
- **Date**: 2026-11-19
- **Verdict**: REJECTED
- **Findings**: 0 critical, 7 warnings, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | FAIL |

## Findings

### F1 — Ready can precede source-tab setup

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: castlib/ui/app.js:108
- **Detail**: `init()` installs the tab watcher only after `refresh()` returns. The first refresh schedules Ready after assigning status, then awaits `/api/errors`. With that request held, Ready posts while the watcher is absent: clicking a connected OneDrive tab cannot invoke `enterTab()` to fetch its list. Removing duplicate `x-init` removes the old second-init path that happened to install the watcher early. This violates Definitions “main controls bound and usable” and plan-review F1's completed component setup. An experiment against the actual component produced Ready=true, watchers=0 and no OneDrive list request. The slow-errors test calls `refresh()` directly and the driver stubs `$watch` away.
- **Fix**: Install the tab watcher before the first awaited refresh, and perform success-conditioned initial source setup before scheduling Ready, independently of errors fetching. Exercise actual `init()` with errors held and a tab action.
  - Strength: Makes the measured point match usable controls without making errors fetching part of startup time.
  - Tradeoff: Source setup ordering changes; preserve once-per-source credential verification and list guards.
  - Confidence: HIGH — reproduced against the actual component and confirmed in source.
  - Blind spot: Actual engine rendering still requires renewed human acceptance.
- **Decision**: FIXED — required handlers and polling setup precede the first refresh; initial source setup follows the first successful status before Ready. Siblings: duplicate init guarded, failed-first-status setup retried, sole castTv component and its refresh/markReady paths checked; reopened: 1.7 (shared authorized fix set).

### F2 — Unknown Windows process state is treated as a complete listing

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/processes.py:97
- **Detail**: `session()` returns None on every ProcessIdToSessionId failure; `_windows()` skips that PID as vanished after an image refusal. A live process whose session lookup fails is therefore omitted without IncompleteListing. [Microsoft documents access requirements and extended error information](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-processidtosessionid); failure does not establish disappearance. In addition, `image()` maps all non-87 OpenProcess errors and all image-query errors to Denied, so a non-access API error can be skipped for another session. Existing fakes encode unknown session as gone and do not test the ctypes boundary.
- **Fix**: Distinguish confirmed disappearance, access denied and other API errors. Skip only confirmed disappearance or an explicit access refusal in a known other session; unknown session and API errors raise IncompleteListing. Test the wrapper boundary as well as listing policy.
  - Strength: Both measurement and the future pruner fail closed on unreadable relevant state.
  - Tradeoff: Conservative refusal when a query cannot establish whether a process remains.
  - Confidence: HIGH — fake reproducer returns an empty successful list for a denied PID with unknown session.
  - Blind spot: Other-session refusals deliberately remain skipped under the requested Windows policy.
- **Decision**: FIXED — unknown owner/error blocks; unsafe session inference replaced under linked F7. Siblings: OpenProcess and QueryFullProcessImageNameW error classification fixed, Linux owner handling n/a (already fails closed), F7 fixed; reopened: 1.7 (shared authorized fix set).

### F3 — Failed shutdown still yields a successful measurement

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: packaging/startup_time.py:179
- **Detail**: `measure_once()` discards `smoke.stop()`'s Boolean result. A run with valid marks and `stop=False` returns a metric, whereas smoke.main rejects that outcome. The last measured run has no subsequent preflight to detect a remaining listener. Ownership checks are retained; the defect is accepting failed cleanup as successful measurement.
- **Fix**: Fail an otherwise successful run when stop returns false or raises, preserving any earlier measurement/refusal/missing-mark exception; test these cases.
- **Decision**: FIXED — false or exceptional cleanup rejects successful measurement without hiding an earlier failure. Siblings: packaging/smoke.py n/a (already checks the Boolean result); sole startup_time measurement-finally path fixed; reopened: 1.7 (shared authorized fix set).

### F4 — Failed version probing can skip cold-cache deletion

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: packaging/startup_time.py:241
- **Detail**: The script ignores the --version exit status. With exit 7 and empty stdout, it passes an empty version to run_series, treats the cache as absent/PyInstaller and can return exit 0 with a cold median. Failed metadata retrieval is not evidence of a legacy build without a Cache line. Reproduced in memory without launching a binary.
- **Fix**: Require a successful --version result before measuring; convert failed, timed-out or unlaunchable probes to RunFailed/exit 1. Test that no series runs and no output JSON is written after a failed probe, retaining successful legacy no-Cache support.
- **Decision**: FIXED — nonzero, timed-out and unlaunchable version probes stop before measurement; legacy successful no-Cache probe still reaches missing-mark detection. Siblings: packaging/smoke.py run() n/a (already rejects nonzero probe exits); reopened: 1.7 (shared authorized fix set).

### F5 — Ready tests do not protect the rendering barrier

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: tests/ui_driver.js:59
- **Detail**: Replacing the production $nextTick/two-frame chain with immediate post() leaves all five new behavioral Ready tests green (temporary copied app.js experiment). The tests check eventual requests but cannot observe render phases. Current production barrier code itself matches the plan. The harness also reads held responses from mutable scripted state on release rather than capturing the response at request time, so it does not faithfully model overlapping responses.
- **Fix**: Add controlled next-tick and frame queues, capture scripted responses on request, and assert no Ready POST before the tick and both distinct frame advances. Exercise real watcher callbacks for F1. Keep asynchronous test failures visible when exiting the driver.
- **Decision**: FIXED — controlled tick/frame checkpoints, watcher callbacks, captured response state and started-task error reporting added. Siblings: default timed rendering retained for older tests, awaited call path retains failure reporting, held-response and background-rejection regression tests added; reopened: none (test-only fix).

### F6 — The full-suite gate fails on test synchronization

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: tests/test_api.py:109, tests/test_cli.py:125, tests/test_onedrive.py:588
- **Detail**: Full suite exits 1: 3 failed, 562 passed, 6 skipped. Conditional Quit asserts the side effect immediately after receiving the response, although the handler calls quit after writing it. The CLI predicate reads current from an App published before initialization finishes, raising AttributeError. The OneDrive test polls a file while the account writer atomically replaces it on Windows, and uses an unclosed open() in the polling expression. Targeted rerun: first two pass, OneDrive fails again; baseline a85f59d temporary checkout also reproduces the OneDrive failure. These are existing test hazards, not evidence of a new product regression, but Phase 1 explicitly requires the full suite to exit 0.
- **Fix**: Wait for the Quit side effect; tolerate an incompletely initialized App in the CLI predicate; await account completion through the source/store lock before opening and asserting the fake credential file. Keep production behavior unchanged and rerun the full gate.
- **Decision**: FIXED — all three synchronization hazards corrected; final full suite exits 0. Siblings: no other json.load(open(...)) polling or half-initialized App.current predicates remain in tests; conditional Quit side-effect assertion now waits; reopened: none (test-only fix).

### F7 — Desktop-session equality does not establish process ownership

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: castlib/processes.py:121 (reviewed head)
- **Detail**: Follow-up to F2 during authorized triage: on the actual Windows 11 desktop, ProcessIdToSessionId failed with access denied for protected processes, including PID 4. A native WTS snapshot identified 159 refused images in session 0 and seven in our session 1. A desktop session includes Windows system accounts; it is not the user's security logon identity. Merely refusing unknown sessions makes measurement unusable here; treating other desktop sessions as different users can also miss the same account in another session. The plan's original contract is owner-based on both OSes. The initial implementation's claim that no own-session process refused on this machine was not established by its failing session queries.
- **Fix**: Replace the Windows session heuristic with positive user-SID ownership from WTSEnumerateProcessesW and EqualSid. Skip only a known different owner, regardless of desktop session. An unreadable same-user process or unknown owner remains IncompleteListing unless disappearance is confirmed; all other API errors remain blocking. Test owner comparison, missing identity, enumeration failure and native buffer cleanup.
  - Strength: Implements the planned same-user rule and permits normal system processes without a permissive unknown-state shortcut.
  - Tradeoff: Adds one native ownership snapshot when there are image refusals. WTS may not enumerate all other users without administrator rights; an absent live PID is unknown and conservatively blocks.
  - Confidence: HIGH — native experiment provides sessions and owner SIDs without opening protected processes; official [WTS enumeration](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/nf-wtsapi32-wtsenumerateprocessesw), [process-info structure](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wts_process_infow) and [EqualSid](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-equalsid) contracts checked on 2026-11-19.
  - Blind spot: A native snapshot cannot exclude a new process starting after it; no new cross-process launch lock is introduced.
- **Decision**: FIXED — Windows ownership uses WTS user SIDs and EqualSid, with buffer-lifetime and failure tests. Siblings: Linux owner rule unchanged and fail-closed; same-user processes in other desktop sessions no longer receive a foreign-user exemption; unknown/missing owner still blocks unless exit is confirmed; reopened: 1.7 (shared authorized fix set). Native unelevated scan intentionally refuses at unknown protected ownership; this is documented, not reported as complete.

## Review Notes

- **Bookkeeping in diff**: context/changes/s16-faster-start/change.md, plan-brief.md, plan.md, research.md, reviews/plan-review.md (all under that change folder).
- **Boundary**: implementation a558115, watched-run support 5155ad8, observation fc780be and acceptance 7d33c1b reviewed. 0707dac changes only temp_steps.md; that owner handoff file is excluded from the implementation scope. No later phase is implemented.
- **Context**: canonical plan is active; the only active plan was read fully. Fetched remote branches; origin/main and origin/s16-faster-start; gh pr list and branch run list are empty. All 6 of 6 lessons were read and considered; manual observation and poll-owned state are directly relevant. Phase 1 Automated 1.1–1.6 have ancestor SHA a558115; no unsuffixed or malformed n/a rows.
- **Acceptance**: skill acceptance-state script exits 0; 1.7 is current at fc780beb1660330a543a6c0bf9fd41036f840f2c. research.md records date, Windows 11 device, instrumented PyInstaller SHA-256, five warm values, median and owner's observed tab response. Pending rows in later phases are outside this review's denominator. Analysis did not alter Progress.
- **Checks at recorded head**: repository .venv Python 3.14.5; Node 24.15.0 available. `python -m pytest tests/test_api.py -q`: exit 0, 24 passed in 7.50s. `python -m pytest tests/test_ui.py -q`: exit 0, 27 passed in 5.65s. `python -m pytest tests/test_processes.py tests/test_startup_time.py -q`: exit 0, 31 passed, 1 skipped in 0.45s (Linux owner case on Windows). `node --check castlib/ui/app.js`: exit 0, no output. `python -m pyflakes castlib tests packaging`: exit 0, no output. `python -m pytest`: exit 1, 3 failed, 562 passed, 6 skipped in 120.55s; F6 names failures. Commands captured stdout/stderr in separate temporary log files and preserved exit status, without command pipelines. Baseline comparison checkout was removed.
- **Matched contracts**: assigned successful host status gates one-shot marking; failed/delayed status and host=False suppress it; actual production scheduling is $nextTick plus two frames and does not await errors. HOST_ONLY remains POST/loopback and no LAN timestamp metadata is exposed. App first timestamps use its existing lock. Window wrapper keeps the once-only shown callback and CLI shown message. No unintended product behavior change beyond F1 was found. Linux owner logic fails closed on same-owner refusal; the read-only safety pass additionally checked a nondumpable same-user process under WSL. Explicit Windows other-session access refusals remain the intended policy; this is a session policy, not cross-session SID ownership.
- **Script**: preflight precedes priming and every measured run; validated cold paths are direct build folders; max(ui_ready_at, shown_at)-launch is correct. BUILD_ID/cache helpers are necessary Phase 1 support for shared validation, not premature Phase 2 implementation. Ownership-checked smoke.stop is reused. Known --hold on priming is documented and deferred to Phase 4; no finding and no requested correction here. Invalid user arguments such as zero runs were not added as speculative findings.
- **Mutation gate**: skipped — no mutation tool is configured in the test plan, manifest or repository. The targeted rendering-barrier experiment is evidence for F5, not a configured mutation gate.
- **Release validation**: packaging changed, so PR release build/smoke must pass under AGENTS.md. No PR or branch run exists yet; no claim of a passing release gate is made. Opening/committing a PR was not requested, and this review never commits.
- **Delegation**: two bounded read-only passes (plan drift; safety/quality/patterns). Concrete findings were checked against source and reproducers in this session.
- **Triage authorization**: owner 2026-11-19: “fix all findings in recommended ways.” Apply the listed fixes without another approval question; do not commit.

## Re-review 2 (2026-11-19)

- **Scope**: Phase 1 (phases 1–7)
- **Session**: fresh (this conversation did not run rune-implement; these fixes were applied during review triage)
- **Base**: 0707daca1a5262a34486a8d4543beff62fc3af0e (previous round)
- **Head**: 0707daca1a5262a34486a8d4543beff62fc3af0e
- **Worktree**: included(castlib/processes.py, castlib/ui/app.js, packaging/startup_time.py, tests/test_api.py, tests/test_cli.py, tests/test_onedrive.py, tests/test_processes.py, tests/test_startup_time.py, tests/test_ui.py, tests/ui_driver.js, context/changes/s16-faster-start/change.md, context/changes/s16-faster-start/plan.md, context/changes/s16-faster-start/research.md, context/changes/s16-faster-start/reviews/impl-review-phase-1-0707dac.md, temp_steps.md)
- **Checks ran at**: 0707daca1a5262a34486a8d4543beff62fc3af0e plus the included worktree fixes; documentation/decision updates after checks do not change tested code.
- **Manual acceptance**: 0 of 1 confirmed — pending: 1.7
- **Verdict**: APPROVED (local code review; manual acceptance and PR release validation remain pending)
- **Findings**: 0 critical, 0 warnings, 0 observations
- **Closes**: F1, F2, F3, F4, F5, F6, F7

None.

### Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

- **Notes**: Bookkeeping in worktree: this report, change.md, plan.md, research.md, and the updated owner handoff in temp_steps.md. No commit, push, PR or merge performed. change.md remains implementing because only Phase 1 is covered. All edits are carried for the next workflow commit.
- **Verification**: `python -m pytest tests/test_api.py -q` exit 0: 24 passed in 6.01s. `python -m pytest tests/test_ui.py tests/test_processes.py tests/test_startup_time.py -q` exit 0: 85 passed, 1 skipped in 6.07s. The combined invocation covers Automated 1.2 and 1.3; the Linux owner test is the Windows skip. `python -m pytest` exit 0: 592 passed, 6 skipped in 118.39s. `python -m pyflakes castlib tests packaging`, `node --check castlib/ui/app.js`, `node --check tests/ui_driver.js`, and `git diff --check` exit 0. Checks captured stdout/stderr and actual statuses. The unchanged Linux owner path was not rerun through Linux pytest: the available WSL Python lacks pytest; CI remains required on both OSes.
- **Adversarial verification**: the render regression test fails on immediate-post, single-frame and missing-nextTick variants; the controls test rejects the original committed init ordering. Only temporary copies were used. The read-only safety delegate rechecked the new WTS layout, SID comparisons, error handling and native buffer lifetime. No configured mutation gate exists.
- **Acceptance**: acceptance-state script exits 0. It first reported 1.7 stale because this fix set changed castlib/processes.py, castlib/ui/app.js and packaging/startup_time.py. The row was reopened, its old accepted revision was recorded in change.md Notes, and a subsequent script run reports pending. research.md retains the original observation and records the automated follow-up separately. No new human confirmation was inferred.
- **Windows limitation**: documented APIs do not provide ownership for arbitrary inaccessible processes to this unelevated caller. A native check therefore refuses at protected PID 4; null/absent SID is never treated as foreign. Elevated rights may provide more information but were not requested or tested. The script correctly returns refusal rather than measuring with an incomplete list; Phase 3 pruning must retain its IncompleteListing no-deletion branch. This replaces the reviewed desktop-session heuristic with the plan's same-user contract and protects the same account across desktop sessions.
- **Release gate**: no PR/run exists for this branch. Required packaging PR release build/smoke validation is pending; local unit checks do not replace it. The known --hold priming behavior remains deferred exactly as requested.
