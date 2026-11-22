<!-- PLAN-REVIEW-REPORT -->
# Plan Review: A faster-starting release file (Nuitka)

- **Plan**: `context/changes/s16-faster-start/plan.md`
- **Mode**: Deep
- **Date**: 2026-11-18
- **Plan sha256**: 0e176650e8fb276015a1afd627acac2cbc4c8b921b5c49c09111c58f1f061f38
- **Verdict**: RETHINK
- **Findings**: 2 critical, 6 warnings, 1 observation
- **Scope**: Working-tree plan, brief, research and change identity, not their Git versions. Owner decisions dated 2026-11-18 are settled. This review challenges the mechanisms that implement and verify them. No plan edits or triage were requested.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Requirement Definition | PASS |
| End-State Alignment | FAIL |
| Lean Execution | PASS |
| Architectural Fitness | WARNING |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

RETHINK follows the rubric's multiple-FAIL rule: the Ready mechanism can certify an unready UI, and the pruning mechanism can delete files in use. It does not reject Nuitka, the two-system scope, either performance bar, or the owner's retention decision. The required revisions concern those mechanisms and the evidence supporting the release switch.

## Grounding

- **Repository**: fetched; only `origin/main` was listed, no open PR was listed; HEAD is `a85f59d036cbdaea669977ae312028b774b7d5a5`. There is one active plan, read in full. The four change documents are untracked working-tree files; their existing carry entries were read. No pre-existing review was present. The canonical plan lies inside `context/changes/`, outside the archive.
- **Lessons**: all 6 entries read; all 6 considered, with the manual-observation and precise-owner-step rules directly relevant. No secrets or stored tokens were read.
- **Paths**: 29/29 referenced implementation/test/document paths grounded: 23 exist and 6 are explicitly planned creations with existing parents. All 15 distinct explicit surface paths exist or are planned creations. `docs/reference/contract-surfaces.md` is absent.
- **Symbols**: the existing `init`, `refresh`, `shown`, `leave_terminal_tab`, font/CA helpers, `MenuEntry`, `identity`, and smoke ownership/Quit functions were found. New bundle and Ready symbols are correctly prospective. Brief and plan agree on owner decisions, but repeat the cache-identity and unconditional disk-limit claims discussed below.
- **Definitions**: all 9 ledger rows audited against the request. The owner owns the observable Ready state, cold/warm measurement, medians, platform bars and retention rules. Marker selection, process-image detection, cache identity and render scheduling are implementation choices; labelling executable-only detection as `user` does not turn it into the owner's broader no-deletion-while-used guarantee.
- **Progress**: exactly one final Progress block; 7/7 phase headings match; all 19 Automated and 20 Manual criteria map in order to Progress rows (the `None` sentinels are not checks). No checked or malformed n/a rows. The skill's acceptance-state script ran successfully and reports all 20 Manual rows pending. No acceptance was reopened or recorded.
- **Commands**: six distinct runnable commands were re-executed using the repository `.venv` on PATH. Five match their recorded exit status; the full suite now exits 0 rather than recorded 1 (F9). Tests: `test_api` 23 passed; `test_ui` 21 passed; platform/shortcut/window 129 passed; full suite 527 passed, 5 skipped. `node --check castlib/ui/app.js` and `pyflakes castlib tests packaging` exit 0. Node was available. The initial unactivated global Python lacked pytest/pyflakes; those invocations were not treated as project test results. Prospective commands and external/paid CI runs were not executed.
- **Independent verification**: one read-only analysis delegate checked UI ordering, pruning and caller coverage; its main findings were checked in this session. A Node experiment against the actual component confirmed that the second `init()` completes, installs a timer, and still has empty `status.sources` while the first status fetch remains unresolved.

### Vendor evidence and conclusions that are not findings

`N/` below denotes the installed **Nuitka 4.3.5** source directory:

`C:/Users/pmill/AppData/Local/Temp/claude/19786b2095697df4/6a0cacd3-c64f-4eb0-be15-ca8d69a6e413/scratchpad/s16/venv/Lib/site-packages/nuitka/`

- **Windows relaunch**: `N/build/static_src/OnefileBootstrap.c:1065-1132` inspects `NUITKA_ONEFILE_PARENT` in DLL mode and resets startup variables for a new parent; `:1388-1426` establishes the child environment and launches it. Relaunching the outer executable with the onefile role variables removed is supported by this source. Keep `CAST_TV_DETACHED`, the arguments and `CREATE_NO_WINDOW` behavior in `castlib/platform.py:480-520`. Removing only a flag would not fix a wrong executable path; the proposed bundle abstraction addresses that separately, subject to F7. No additional required environment variable was found beyond the planned onefile cleanup.
- **Windows console**: `N/build/static_src/HelpersConsole.c:201-216` hides a console when `GetConsoleWindow()` succeeds and `GetConsoleProcessList()` reports at most one attached process. The bootstrap invokes it before extraction (`OnefileBootstrap.c:1051-1052`), and the child invokes it early too (`MainProgram.c:1685-1686`). This supports using `hide` as the counterpart of hide-early, preserving an existing shell's console. It does not prove Windows Terminal tab handling or fallback behavior; rows 7.1-7.3 are necessary. The vendor [changelog](https://nuitka.net/changelog/Changelog.html) also describes early console hiding; the installed source is the version-specific evidence used here.
- **Cached Windows process images**: do not confuse the new DLL onefile path with this build. `N/options/Options.py:1554-1571` enables DLL onefile by default on Windows only in temporary mode; `:2545-2577` makes the static cache spec non-temporary. The spike's `nuitka-out/entry.onefile-build/scons-debug.py:8` records `dll_mode=false`, `exe_mode=true`. Thus a running cached child normally does have its image inside the cache. DLL mode is not the reason for F2.
- **Roots and foreign names**: `N/build/static_src/HelpersFilesystemPaths.c:1066-1070` expands Windows CACHE_DIR to local app data. Linux `:1385-1395` honors an absolute `XDG_CACHE_HOME`, otherwise HOME/.cache. The Windows root in the plan is correct. The proposed pattern excludes the GoPro `Cache` sibling. Pruning should derive the parent from the actual cache path, as proposed, rather than hard-code HOME/.cache.
- **Shown ordering**: `castlib/window.py:213-220` and `:234` provide a one-shot shown callback. Independently recording it and a valid page-ready mark, then using their maximum, handles either arrival order. pywebview's WinForms shown handler (`.venv/Lib/site-packages/webview/platforms/winforms.py:367-370`) and Qt showEvent (`platforms/qt.py:581-582`) are reasonable visibility proxies. Its event dispatcher runs callbacks on a worker (`webview/event.py:36-61`), despite the app docstring saying GUI thread: these are observed callback times, not an exact compositor timestamp. Preserve the existing CLI shown message at `castlib/cli.py:342-343` when adding the mark.
- **Caller sweep**: all product reads of `getattr(sys, "frozen", ...)`, `getattr(sys, "_MEIPASS", ...)` and `sys.executable` are in the three modules already named by Phase 2: platform, shortcut and window. No omitted product caller was found. `server.py:36` and `shortcut.py:66` derive resources from module `__file__`; those are not additional PyInstaller-only branches. Their packaged data still needs the planned build/smoke verification.

### Independent cache walkthrough

Current D has just started. A and B are other recognized version folders. These cases are independent of the plan's three-version happy-path test:

| Case | Planned behavior and consequence |
|------|----------------------------------|
| Only D exists | No old folder to delete; sound. |
| A and B have equal newest marker timestamps | The retained previous folder has no specified tie rule; add a stable technical tie-break and a test (F6). |
| A and B lack markers and have equal directory mtimes | Same tie, now on the fallback selector (F6). |
| B is newest marked; A is unmarked with newer directory mtime | Wording keeps B: mtime fallback applies only when no candidate has a marker. Make this intentional in tests. |
| B is previous; A has a live cached child | D, B and A must all remain. Correct protection exceeds two folders; the unconditional end-state/README promise needs the exception (F2). |
| B is previous; A is currently being checked/unpacked by its outer bootstrap | No executable inside A yet; A is eligible for removal while used (F2). |
| A starts after the process snapshot | Snapshot no longer establishes deletion safety (F2). |
| A process disappears during enumeration | Classify process-exited separately from permission-denied/unknown; an incomplete scan must not silently mean unused (F2). |
| A folder ends in an 8-character abbreviated commit | Build can create it, but the exact-7 pattern never prunes it (F6). |
| A second payload has the same version and source commit | It reuses A's identity; CRC can rewrite the first payload's files (F6). |
| Foreign `Cache`, or the spike's legacy `0.5.0` | Both excluded by the proposed pattern. `Cache` exclusion is correct; the experimental legacy cache remains outside this retention policy. |

## Findings

### F1 — Ready can fire before the first status response

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Phase 1, Ready mark; `plan.md:142-151`
- **Detail**:
  The plan attaches Ready after `init()` awaits `refresh()`. The actual page has both `x-data="castTv()"` and `x-init="init()"` (`castlib/ui/index.html:12`), while the vendored Alpine automatically invokes the component's init (`castlib/ui/alpine.min.js:22`, `s.init&&R(e,s.init)`). First init waits in the fetch; second init hits `_refreshing` at `app.js:121`, gets an immediately resolved promise and can schedule Ready on the default status. Two animation frames do not establish that a status response was rendered. Independently, refresh catches errors and resolves normally (`app.js:133-138`), so an unconditional hook can mark a failed first request; a later successful poll would not naturally retry an init-only hook. Conversely refresh can await `/api/errors` after assigning the status (`:126-130,143`), adding unrelated latency after the main controls render. The benchmark can pass while failing the owner's Ready definition.
- **Fix**: Initialize once, and define a success-conditioned, one-shot path tied to the first accepted status and completed component setup. Wait for Alpine's render flush and then the two frames before posting. Failed/skipped refreshes must not mark Ready, and a later successful response must be able to do so.
  - Strength: Implements the agreed observable Ready condition and removes the demonstrated duplicate-init race.
  - Tradeoff: Adds `index.html` to Phase 1 and requires explicit ordering between component setup, successful status application and render scheduling.
  - Confidence: HIGH — reproduced against the current component; both error swallowing and extra awaited work are visible in source.
  - Blind spot: Visual readiness still needs rows 5.3-5.4 on both actual engines. Add tests for duplicate init, delayed/failed initial status, successful retry and delayed errors fetch; a direct successful refresh test alone misses the race.
- **Decision**: FIXED — owner 2026-11-18 (as recommended): `x-init` removed so `init()` runs once; Ready is a one-shot after the first successful assigned status, `$nextTick` + two frames, not awaiting `/api/errors`; failed refreshes do not mark; the review's cases are in Phase 1's test_ui row.

### F2 — Process-image snapshots cannot protect caches throughout launch

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Blind Spots
- **Location**: Phase 3; Critical Implementation Details; Definitions In use; `plan.md:125-128,265-277`
- **Detail**:
  An executable path inside the folder establishes use by an already-running cached main child, on both systems. It does not cover the outer onefile bootstrap, which runs outside the cache while checking/unpacking it (`N/build/static_src/OnefileBootstrap.c:1239-1350`); the child inside the cache is started afterward (`:1394-1426,1472-1492`). In the walkthrough, D's pruner keeps D+B and deletes A while A's external bootstrap is reading/writing A. A new launch after the process snapshot creates another check/delete race. On Windows, a recursive deletion that eventually hits a locked EXE/DLL may already have deleted other files: ignoring that error cannot preserve the running version's unloaded resources. The process-lister contract also needs to distinguish normal disappearing/system processes from permission-denied or otherwise incomplete same-user enumeration. Finally, the owner's retained-active-version exception means more than two folders may remain, contrary to the unconditional end-state/migration/brief promises.
- **Fix**: Specify and verify a launch/deletion exclusion protocol that covers outer bootstraps as well as running children before enabling removal. Resolve how it works with the unmodified vendor bootstrap; an app-only lock acquired after extraction is insufficient. Fail closed on unresolvable activity or incomplete relevant enumeration, and never treat a partial recursive removal as safe. Carry the active-version exception into the end state, README contract and brief.
  - Strength: Preserves the owner's no-delete-while-used rule across the actual lifecycle rather than only its steady state.
  - Tradeoff: Needs a bounded feasibility check of the chosen exclusion mechanism; pruning must be deferred if that mechanism cannot establish safety. A second image snapshot alone does not close the race.
  - Confidence: HIGH — extraction-before-child ordering is explicit in installed 4.3.5 sources; recursive deletion is not transactional.
  - Blind spot: No safe cross-platform exclusion mechanism is established by this plan. Add deterministic interleaving tests for extraction, scan, launch and removal, permission failures, and Windows partial-delete behavior, plus the existing manual active-version check.
- **Decision**: FIXED — owner 2026-11-18 chose the age guard + safe delete: removable only when ≥ 7 days since the last start marker and no running image inside; incomplete listing removes nothing; rename to `.removing-<pid>` first (Windows fails if locked), then delete; residual bootstrap race recorded under What We're NOT Doing; end state, README and brief carry the exception.

### F3 — Released v0.5.0 cannot emit the new measurement marks

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 Overview and Manual Verification; row 1.7; `plan.md:134-135,190`
- **Detail**:
  The plan says the script works on today's released PyInstaller files and explicitly requires the v0.5.0 EXE. That immutable binary lacks `/api/ready`, `ui_ready_at` and `shown_at`: current `castlib/api.py:113` returns only id/pid/parent_pid and `cli.py:version_text` has no Cache line. Editing the checkout does not instrument an already-released binary. The run will time out rather than produce the required Ready median. Phase 5 correctly compares two newly built artifacts of one commit; Phase 1 must use the same principle.
- **Fix**: Build an instrumented PyInstaller artifact from Phase 1's source for row 1.7; name that artifact and build/run provenance, and remove the claim of compatibility with the untouched v0.5.0 EXE. Define a missing-mark diagnostic for unsupported old binaries.
- **Decision**: FIXED — row 1.7 uses a PyInstaller build of Phase 1's commit; the script exits 3 with a clear message for a file without the Ready mark.

### F4 — Acceptance surfaces omit the code and build inputs they certify

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Phases 5-7 surface declarations; `plan.md:388-393,454-466`
- **Detail**:
  Running Phase 7 after Phase 6 is sound, but it does not repair incomplete declarations. Phase 5 timing rows omit `castlib/platform.py`, `castlib/shortcut.py`, the PyInstaller spec, dependency configuration and `release.yml`, even though they affect startup/build contents; F1 also adds index.html. Phase 6 changes the workflow and removes the spec, so simply omitting them lets old timings remain mechanically current without proving the final artifacts equivalent. Phase 5 bar rows track only research.md and can remain current when the measured implementation changes. In Phase 7, row 7.4 omits cli/app/window/platform (shutdown), 7.5 omits cli/api/window (second launch), 7.9 names only build_nuitka despite testing UI/server/QR, and 7.10 omits the builder's cache layout. Similar gaps affect the other packaged behavior rows. The acceptance script uses only the declared paths and criterion; it cannot infer these dependencies. A later behavior fix can leave earlier ticks apparently current.
- **Fix**: Declare the real per-row implementation, UI and packaging/dependency surfaces, using directory surfaces where appropriate. Define a final-artifact verification step: after Phase 6, either repeat affected performance measurements or demonstrate and record that the final build has equivalent measured code/options/dependency inputs except documented naming/bookkeeping changes. Tie bar acceptance to the measured surfaces as well as its evidence. Any material change during Phase 7 must reopen affected measurements and behavior rows.
  - Strength: Makes the plan's existing acceptance-currency mechanism reflect what the owner actually inspected.
  - Tradeoff: Broader surfaces can require re-confirmation; record a reasoned equivalence rather than hiding a real dependency to avoid staleness.
  - Confidence: HIGH — the script ran successfully and its selected path lists match the omissions above.
  - Blind spot: The exact workflow diff and any Phase 7 fixes do not exist yet; the plan must specify how to handle them rather than assert no later surface change.
- **Decision**: FIXED — Phase 5 and 7 rows use directory surfaces (castlib/, packaging/, pyproject.toml, release.yml); row 6.4 records equivalence of published vs measured files and re-confirms 5.1-5.6, or re-measures.

### F5 — Cold measurement checks only one port instead of the closed-process precondition

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Phase 1 measuring-script contract; `plan.md:158-172`
- **Detail**:
  The owner requires every cast-tv process closed before a cold run. Refusing only when 127.0.0.1:8895 answers cannot establish that: cast-tv supports `-p`, and a copy on another port or an extracting bootstrap can still be running. Then the script deletes the Cache path from --version without a specified independent safety check. That can invalidate the experiment or delete a live cache. After a run, a free HTTP port alone also does not prove the onefile process and its bootstrap exited, although `packaging/smoke.py:105-128` already waits for its launched process as part of stop.
- **Fix**: Define an independent preflight and deletion guard that enforce the agreed no-running-cast-tv condition across ports and relevant process roles, reusing the safe lifecycle work from F2. Preserve the smoke helper's process-exit wait and ownership checks, validate that the reported cache is the intended version folder, and test an existing instance on a nondefault port plus a live bootstrap.
  - Strength: Aligns the benchmark with the settled cold definition and protects the actual cache being removed.
  - Tradeoff: Measurement now needs explicit process-liveness and path-validation behavior, including conservative refusal when it cannot establish safety.
  - Confidence: HIGH — custom ports and separate bootstrap/child ownership are already used by cli.py and smoke.py.
  - Blind spot: A complete preflight depends on F2's process-role strategy; a default-port check cannot substitute for it.
- **Decision**: FIXED — process-wide preflight via `castlib/processes.py` (any port, bootstrap, the measured file); incomplete listing refuses; the cold folder is validated against the cache root and the identity grammar; smoke's stop() waits for process and port.

### F6 — Cache identity and selection do not cover the claimed build space

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architectural Fitness
- **Location**: Phase 3 selector; Phase 4 cache spec; plan-brief Key Decisions Cache path
- **Detail**:
  `<version>-<commit7>` does not prove the brief's promise that two builds never rewrite each other's running files. Re-running the same commit can change unpinned Nuitka/dependencies or the release-injected client while keeping that same key. Nuitka's cached CRC loop then rewrites differing payload files (`N/build/static_src/OnefileBootstrap.c:1294-1300`). In addition, `git rev-parse --short=7 HEAD` requests a minimum seven characters, but the pruner accepts exactly seven; a lengthened abbreviation creates a folder it will never prune. Finally, equal marker timestamps or equal fallback mtimes have no stable selection rule or tests. These are implementation gaps in the chosen retention rule, not reasons to ask the owner to choose it again.
- **Fix**: Choose a cache identity that distinguishes different build payloads (for example a release build ID including rerun attempt, or a pre-packaging payload identity), and make the builder and pruner share its grammar. Pin the vendor version whose runtime behavior is relied on and record dependency/build provenance. Specify a deterministic tie-break for equal marker/fallback times and test mixed marked/unmarked folders, missing markers and identity collisions/longer abbreviations.
  - Strength: Makes isolation and pruning agree for every artifact the build can actually produce.
  - Tradeoff: More distinct rebuilds can create more cache folders; retention still applies under the same owner policy. Any identity grammar change must be reflected in cold-deletion validation and documentation.
  - Confidence: HIGH — the builder uses source identity, while the vendor validates payload bytes; Git abbreviation length and marker ties are directly testable.
  - Blind spot: Exact reproducibility of the packaged payload is not demonstrated; do not assume it to justify reusing a source-only key.
- **Decision**: FIXED — identity `<version>-gh<run>.<attempt>` or `-local<timestamp>`, one grammar shared; Nuitka pinned 4.3.5; build-info provenance; tie-break by name; mixed/missing marker tests.

### F7 — Making original argv0 absolute can select the wrong launcher

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architectural Fitness
- **Location**: Phase 2 `started_file()`; `plan.md:216-217`
- **Detail**:
  The contract says to make `__compiled__.original_argv0` absolute. On Linux a PATH launch can supply only a basename. The bootstrap preserves that original value in `NUITKA_ORIGINAL_ARGV0` (`N/build/static_src/OnefileBootstrap.c:1390`), and MainProgram copies it back into original_argv0 (`:1906-1915`). With `/opt/cast-tv/cast-tv-linux-x64` on PATH and cwd `/tmp`, abspath("cast-tv-linux-x64") produces a nonexistent `/tmp/cast-tv-linux-x64`. The proposed shortcut target would then name the wrong file. This is not an omitted sys.executable caller; it is an incomplete replacement contract.
- **Fix**: Specify resolution for absolute paths, cwd-relative paths and PATH-only argv0, using verified launcher facts such as the onefile containing directory and/or PATH resolution while preserving the intended launcher/symlink identity. Capture the result before any cwd change. Add a PATH launch from a different cwd, a relative launch and a spaced-path test.
- **Decision**: FIXED — `started_file()` resolves absolute, cwd-relative (cwd captured at import) and bare PATH names, keeps symlinks, returns None when missing; tests named in Phase 2.

### F8 — Several manual rows lack executable steps and required test artifacts

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 7 Manual Verification and Manual Testing Steps 3; `plan.md:454-466,509-511`
- **Detail**:
  The plan claims each row names the window, control and expected result, but rows such as "a forced fallback" and "a cold start killed during unpacking" give no forcing/stopping command or precise process target. The simultaneous-version retention check needs three distinct cache identities, while the Phase 4 PR supplies only one Nuitka build per system; renaming that EXE does not change its embedded cache key. Referencing S-12 row numbers helps expected behavior but does not supply the new cache fixtures or prove that the same fallback procedure reaches the Nuitka path. These gaps leave the owner to invent the experiment.
- **Fix**: Add concrete per-system runbooks, exact fallback and interruption procedures, and a provisioned three-identity artifact fixture for 7.10. Name the terminal/Explorer/UI control, expected visible result and evidence to write in research.md for each row. Preserve real sign-in/TV checks as pending manual acceptance.
- **Decision**: FIXED — Phase 7 rows carry per-system steps, the fallback (`CAST_TV_WINDOW_FAIL`) and interruption procedures, and a three-identity fixture from PR run attempts for 7.10.

### F9 — The recorded full-suite baseline no longer matches

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Automated Verification in Phases 1, 2, 3 and 6
- **Detail**:
  The plan repeatedly records full-suite exit 1 for the intermittent CLI test. Re-execution on this working tree using the repository venv exits 0: 527 passed, 5 skipped in 127.53 seconds. This does not disprove the historical flake; it means the current baseline should not normalize exit 1 as an acceptable implementation gate. The other five distinct recorded commands match exit 0.
- **Fix**: Append the dated current passing baseline and retain the earlier intermittent result as history. State that each phase requires a passing suite; a future failure needs investigation/reproduction rather than being waved through as the known planning failure.
- **Decision**: FIXED — the baseline records both results; every phase requires exit 0.

## Review outcome

Triaged by the owner on 2026-11-18 (Claude applied the fixes): all nine findings FIXED in plan.md and plan-brief.md; no commit was created. Priorities are F1 and F2, then correcting the measurement artifact and acceptance provenance before implementation proceeds.
