<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: A desktop window for cast-tv (S-12)

- **Plan**: context/changes/s12-desktop-window/plan.md
- **Scope**: Phases 2–4 (phases 1–4 in the plan; Phase 1 excluded)
- **Session**: fresh
- **Base**: c3aefda3a2b641ef813917e46e507f68c5afd866 (Progress: parent of Phase 2 commit 7eb63db)
- **Head**: ee74c2cb3ef723f2f51a1539eeb76cf07ea79081
- **Worktree**: excluded (clean at boundary; no pre-existing edits)
- **Checks ran at**: ee74c2cb3ef723f2f51a1539eeb76cf07ea79081; local release build from a scratch export of this revision with synthetic build credentials only
- **Manual acceptance**: 6 of 17 confirmed — stale: 4.6, 4.8, 4.9, 4.10; unverifiable: 2.6, 3.6, 3.7, 3.8, 3.10, 3.11, 3.12
- **Date**: 2026-11-16
- **Verdict**: REJECTED (automated full-suite gate failed in the required test-only environment; no critical code findings)
- **Findings**: 0 critical, 5 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | FAIL |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | FAIL |

The implementation findings warrant NEEDS ATTENTION independently of the test gate. The overall REJECTED verdict follows the skill's failing-tests rule. The failed tests below are already documented as intermittent; this review does not attribute them to Phases 2–4 or propose changing the explicitly excluded OneDrive test.

## Findings

### F1 — Fatal startup errors reach the blocking dialog before cleanup

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: castlib/app.py:286; castlib/cli.py:301
- **Detail**: Phase 3 explicitly requires reporting pre-GUI fatal startup exceptions after cleanup. App.start() starts serving before select_tv(), but unwinds only KeyboardInterrupt. An invalid --tv or CAST_TV raises ConfigError after serve(); cli.ui() catches it and invokes the blocking Windows startup-error reporter without closing the app. The failed instance can hold its port and continue serving until the person dismisses the dialog. An injected lifecycle probe using the real App.start() and select_tv() recorded bad_ip with calls ['serving'] and no close/interrupted/socket-close call.
- **Fix**: Unwind ordinary startup exceptions before reporting them, retaining the distinction between a bound socket and a running server.
  - Strength: Implements the explicit after-cleanup contract and closes the server and source resources on partially completed startup.
  - Tradeoff: Must preserve AlreadyRunning and cancellation semantics and avoid shutdown() before the HTTP loop exists.
  - Confidence: HIGH — the missing exception branch and lifecycle probe agree.
  - Blind spot: The real Windows dialog with a failure after serve() has not been exercised in this review.
- **Decision**: FIXED — exceptions unwind startup before reporting; siblings: cli.ui OSError/generic paths fixed via App.start; cli._cast_item, cli.show and cli.window_check n/a (no blocking startup-error reporter; existing post-start finally cleanup). reopened: 1.9, 1.10, 1.11, 1.12, 4.7, 4.8.

### F2 — Release smoke cleanup can quit an unrelated cast-tv session

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: packaging/smoke.py:47
- **Detail**: The supposedly spare port is the constant 8099. If an existing cast-tv holds it, the smoke child can take AlreadyRunning and exit while the HTTP assertions validate the existing session. finally unconditionally sends POST /api/quit to that port. An isolated fake-network probe confirmed that stop() sends Quit even when its child has already exited. Running the smoke command locally can therefore stop somebody's active playback and falsely validate the wrong process.
- **Fix**: Use a per-run port and establish that the responder belongs to the spawned instance before HTTP teardown; otherwise clean up only the spawned process tree.
  - Strength: Keeps the necessary Windows bootloader/child cleanup while protecting an existing session and the validity of the smoke assertions.
  - Tradeoff: Requires explicit ownership handling and coverage for occupied ports and early child exit.
  - Confidence: HIGH — the unconditional request is directly reproduced; no live user session was stopped.
  - Blind spot: The ownership mechanism still needs an implementation choice and validation on both OSes.
- **Decision**: FIXED — per-run port, loopback-only process/instance identity, same-connection recheck and conditional Quit; fallback kills only our tree; siblings: self-check/version n/a (no HTTP teardown), window-check n/a (owns App with finally cleanup). reopened: 1.10, 1.16, 3.9, 4.7, 4.8, 4.9, 4.10.

### F3 — The launcher button inherits the TV dropdown layout

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: castlib/ui/index.html:101; castlib/ui/style.css:83
- **Detail**: The new section uses class="phone menu". The existing .menu selector is the TV dropdown: position:absolute, top:40px, right:0, width:300px, z-index:30 and a shadow. The later .phone.menu rule changes only margin and padding. menuVisible() is true whenever a host has shortcut state; it has no click condition and is independent of tvMenu. Consequently Add to Start menu/Add to menu appears as an open-looking floating dropdown even with the TV menu closed, rather than occupying the normal document flow below the phone panel. The research note at research.md:1580 described this as design; the CSS comment at style.css:117 and the selector collision show an implementation defect. Introduced in 89735ba.
- **Fix**: Give the launcher panel its own class and selector, without the TV dropdown's .menu class; verify it stays below the phone panel while the TV dropdown still opens normally. Changing index.html touches rows 4.8–4.10 as the owner noted, and also other rows sharing that file; use the acceptance script after the actual fix.
- **Decision**: FIXED — launcher uses phone-panel launcher; siblings: TV dropdown retains menu, sign-in help retains phone without host-panel styling. reopened: 1.10, 1.16, 3.9, 4.7, 4.8, 4.9, 4.10.

### F4 — Windows shortcut state never refreshes after its first read

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/shortcut.py:251
- **Detail**: cached() starts a Windows background read only while _cached is None. Once the initial read, install() or remove() populates it, subsequent polls never re-read the shortcut, despite the module's refresh-in-background contract. If copy B on another port updates the shared Start-menu entry after A cached current=True, A indefinitely offers Remove instead of Update. A fake-PowerShell two-copy probe returned A.state().current=False but A.cached().current=True; A's stale Remove then deleted B's entry. External deletion likewise leaves an incorrect control. Linux re-reads its small entry on every poll.
- **Fix**: Refresh Windows state asynchronously on a bounded interval or invalidation, and ensure a read started before an install/remove cannot overwrite its newer result.
  - Strength: Restores cross-copy Update behavior while retaining a fast status poll.
  - Tradeoff: Adds refresh timing/invalidation and ordering logic around local mutations.
  - Confidence: HIGH — direct and cached states disagree in a reproduced two-copy case.
  - Blind spot: A real Start-menu change by a second running Windows copy has not been exercised here.
- **Decision**: FIXED — Windows cache refreshes every 5 s with an obsolete-read guard; siblings: Linux n/a (direct state reads), Windows install and remove races both covered. reopened: 4.6, 4.7, 4.8, 4.9, 4.10.

### F5 — Long source errors widen the window instead of wrapping

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/ui/style.css:186; castlib/ui/index.html:436
- **Detail**: Source-list failures are rendered verbatim in .empty.bad. Its styling supplies padding, alignment and color but no wrapping for long unbroken text. With networking disabled, the GoPro fetch error contains the long api.gopro.com/media/search URL and the owner observed a page-wide horizontal scroll bar (research.md:1671–1674, Windows 11, 2026-11-16). The same missing break opportunity exists on shared diagnostic .card .msg text at style.css:264. This is an existing shared-UI presentation defect included explicitly at the owner's request, not claimed as new Phase 2–4 drift.
- **Fix**: Add overflow-wrap:anywhere to the relevant source-error and diagnostic-message containers, checking sibling error/hint fields and narrow windows without truncating the error.
- **Decision**: FIXED — source errors wrap anywhere; siblings: diagnostic messages/hints, gate/picker/link errors, toasts and banners fixed. reopened: none (style.css is absent from existing explicit surfaces; F3 HTML edits reopen shared UI rows).

### F6 — Every shown event repeats the startup instruction

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/window.py:213
- **Detail**: shown() sets current.shown=True and calls on_shown on every event; it does not test the previous state. Qt raises shown again when the window is brought forward, so "Close the window or press Ctrl+C" repeats. The Fedora observation reports three prints (research.md:1571–1574); a fake-webview probe firing three shown events produced three callback calls. The existing test fires only one event and misses the recurrence.
- **Fix**: Guard the first shown transition so readiness is set and on_shown is invoked once per run, and extend the fake to emit repeated shown events.
- **Decision**: FIXED — first shown transition alone invokes the callback; siblings: window_probe loaded n/a (already guarded by its probe lock); repeated events and callback failure tested. reopened: 1.9, 1.11, 1.12, 2.7, 2.9, 4.5, 4.6, 4.7.

### F7 — The Linux release emits Fontconfig configuration warnings on Fedora 45

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: packaging/cast-tv.spec:34; context/changes/s12-desktop-window/research.md:1575
- **Detail**: The 2026-11-07 Fedora 45 run recorded about 45 Fontconfig errors/warnings naming /etc/fonts/conf.d/48-guessfamily.conf ("invalid attribute 'xsi:nil'") and 49-sansserif.conf ("invalid constant used"). Text rendered normally, so the evidence supports noisy startup, not a rendering failure. The notes attribute this to the binary's older bundled Fontconfig reading the host's newer configuration; this Windows review has not independently inspected the loaded Linux library or reproduced that diagnosis. The spec filters only libgbm and libstdc++, with no Fontconfig compatibility policy. Official Fontconfig documentation confirms that FONTCONFIG_FILE/PATH select configuration and FC_DEBUG can reveal details; it does not establish this binary's actual loaded library.
- **Fix**: Run a focused Fedora release-binary probe to establish the loaded Fontconfig and configuration files, then ship a compatible library/configuration pairing and verify normal rendering on the supported distributions.
  - Strength: Addresses the observed mismatch while preserving useful error output and normal installed-font discovery.
  - Tradeoff: Requires a Linux packaging experiment and cross-distribution validation; filtering all stderr would conceal unrelated failures.
  - Confidence: MED — the warnings are recorded, but the precise bundle remedy remains unverified.
  - Blind spot: No Fedora session is available in this review; Windows build success cannot prove Linux font behavior.
- **Decision**: FIXED — frozen Linux ships private compatible font rules selected before Qt; A/B reproduces 45 diagnostics with upstream 2.18.3 rules and zero with the fix; siblings: normal startup, version and window-check fixed via packaging/entry.py; Windows/non-frozen Linux n/a (host stack); explicit FONTCONFIG_FILE/PATH overrides preserved. reopened: 2.7, 2.8, 2.9, 4.5, 4.8. Actual Fedora desktop acceptance remains pending.

### F8 — Four Phase 4 manual confirmations are stale

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/s12-desktop-window/plan.md:885
- **Detail**: The shared acceptance-state.sh script exits 0 and reports 4.6, 4.8, 4.9 and 4.10 stale: changed: castlib/shortcut.py. Their accepted revisions are respectively 9376efdb90d95d37d85e9e9979f5fc117b354d6e, 35ba96c9fbf2302c39f5abda53d443009cbd7cdb, 8e7d001b7da035e9bafeac5da12fe29443fe79d2 and 9376efdb90d95d37d85e9e9979f5fc117b354d6e. Later shortcut changes invalidate the path-based checked surface even where a note argues that an OS-specific branch was unaffected. This does not say the earlier observations were invented or the checks now fail; their recorded acceptance is no longer current.
- **Fix**: Re-confirm at ee74c2cb3ef723f2f51a1539eeb76cf07ea79081 through $rune-implement, or reopen in triage. If fixes land first, confirmation must be for the resulting committed revision.
- **Decision**: FIXED — reopened the four stale rows; siblings: 11 additional rows invalidated by this fix set also reopened, unverifiable rows unchanged. reopened: 1.9, 1.10, 1.11, 1.12, 1.16, 2.7, 2.8, 2.9, 3.9, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10.

## Automated Verification

Checks used Node on PATH and Windows Python 3.14.5. No paid checks exist and no n/a Automated rows exist. All Progress implementation SHAs (7eb63db, 3712375, 89735ba; Phase 1's 1083431 also checked) resolve as ancestors of the recorded head.

| Progress rows | Verification | Result and actual output |
|---|---|---|
| 2.1 | python -m pyflakes castlib tests packaging | PASS, exit 0, no output; both existing .venv and fresh test-only venv |
| 2.2 | tests/test_cli.py, executed within the complete-suite runs | Existing .venv passed the module; fresh rerun result documented below |
| 2.3, 3.4, 4.3 | python -m pytest in existing .venv | PASS, exit 0: 499 passed, 5 skipped in 119.91s |
| 2.3, 3.4, 4.3 | python -m pytest in fresh venv installed with .[test], without webview | FAIL, exit 1: 1 failed, 498 passed, 5 skipped in 119.67s; tests/test_onedrive.py::test_token_file_mode_0600 timed out waiting for account |
| 2.4 | gh pr checks 80 | PASS, exit 0: test on both OSes and build/smoke on Windows and Ubuntu pass; tag-only release job skipped as designed |
| 2.5 | python -m PyInstaller --noconfirm packaging/cast-tv.spec, then python packaging/smoke.py dist/cast-tv.exe | PASS, each exit 0; scratch export with synthetic build credentials and isolated APPDATA/LOCALAPPDATA; no tracked source or stored credentials changed |
| 3.1 | python -m pytest tests/test_ui.py::test_static_exact_match_only | PASS, exit 0: 1 passed in 0.14s |
| 3.2 | tests/test_ui.py within complete suite | PASS: all 21 UI tests, including Node behavior driver, executed rather than skipped |
| 3.3 | tests/test_platform.py within complete suite | PASS: all 41 cases |
| 3.5 | gh pr checks 89 | PASS, exit 0: both build/smoke jobs and both test jobs |
| 4.1 | tests/test_shortcut.py within complete suite | PASS: all 28 cases |
| 4.2 | tests/test_ui.py and tests/test_api.py within complete suite | PASS: 21 UI and 21 API cases |
| 4.4 | gh pr checks 97 | PASS, exit 0: both build/smoke jobs and both test jobs |
| Repository UI rule | node --check castlib/ui/app.js | PASS, exit 0, no output |
| Known flaky failure diagnostic | python -m pytest tests/test_onedrive.py::test_token_file_mode_0600, fresh test-only venv | PASS, exit 0: 1 passed in 0.76s; this does not replace a full-suite gate |

Local Windows smoke output:

    size: 26220948 bytes
    cast-tv 0.4.0
    Google Photos client: built in
    GoPro window: C:\Program Files\Google\Chrome\Application\chrome.exe
    Window: edgechromium
    self-check: HEIC -> image/jpeg 16x16 OK
    /ui/ 200, /api/status 200, gphotos disconnected
    POST /api/quit: ended, port 8099 free
    window-check: edgechromium OK (8.7 s)

Port 8099 was checked free before this invocation. The built-in client was a synthetic fixture written only inside .git/rune/s12-review-ee74c2c/build-source, through the existing writer. This tests packaging and local rendering without exercising a real Google sign-in. PyInstaller 6.22.3, pywebview 6.2.1 and pythonnet 3.2.1 were used. The main checkout's builtin-client stub was untouched.

The existing .venv had the window extra; the fresh test-only environment specifically verified that webview was absent. Fresh dependencies included pytest 9.2.0 and platformdirs 4.14.5; the existing environment used pytest 9.1.1 and platformdirs 4.13.4. Both used Pillow 13.0.0 and pillow-heif 1.8.1. A dependency cause for the differing test outcomes has not been established.

The single full-suite repeat in the fresh test-only environment also failed, exit 1: 2 failed, 497 passed, 5 skipped in 116.17s. It reproduced the OneDrive account wait timeout and tests/test_cli.py::test_cast_replaced_from_the_ui_keeps_serving raised AttributeError because the waiting test observed App before its current attribute was initialized. temp_steps.md already identifies both tests as intermittent on Windows. No further retries or unrelated test fixes were made. Success Criteria remains FAIL; the isolated OneDrive pass and the earlier complete-suite pass are retained as separate evidence.

Complete command output and the three reproduction logs are kept locally under .git/rune/s12-review-ee74c2c/. Commands redirected stdout/stderr to logs and recorded exit status without piping a check into a filtering command.

## Manual Acceptance

Computed with the skill's shared script, not inferred from checkboxes:

    bash .agents/skills/rune-impl-review/scripts/acceptance-state.sh context/changes/s12-desktop-window/plan.md

- **Current (6)**: 2.7, 2.8, 2.9, 3.9, 4.5, 4.7.
- **Stale (4)**: 4.6, 4.8, 4.9, 4.10 — see F8.
- **Unverifiable (7)**: 2.6, 3.6, 3.7, 3.10, 3.11 and 3.12 use "accepted at f68fd5e"; 3.8 uses "accepted at f68fd5e (Windows)". The script reports malformed acceptance revision: a confirmation suffix must contain one full revision, not a short SHA or prose. Written Windows observations exist in research.md; these rows are pending acceptance under the shared contract, not additional findings.
- **Pending unchecked / n/a / malformed n/a**: none.
- **2.9**: the current row records the Ubuntu VM check as not run because the VM was deleted. Its selected criterion explicitly allows "or why not", and research.md records that reason; no Ubuntu run is claimed.
- **Phase 1 interaction**: not re-reviewed. The script also reports 1.8 and 1.13–1.15 unverifiable because of short/combined acceptance revisions; 1.9–1.12 and 1.16 are current. These rows are excluded from the 6/17 denominator.
- **Future fixes**: F3 touches index.html and therefore the explicitly named 4.8–4.10 surfaces, plus other phases' shared UI surfaces. F6 touches window.py. Re-run the script after actual edits, reopen affected stale rows under the skill's rules, leave unverifiable rows unchanged, and never restore a confirmation by automated testing.

## Plan Coverage

- **Phase 2**: backend imports, Linux library exclusions, gi exclusion, console executable, window extra/build libraries, Xvfb, mandatory WebView2 check, fourth version line, renderer/title/Alpine probe, HEIC/HTTP/window smoke and size output implemented. window_probe.py is a justified helper split, not unplanned product scope.
- **Phase 3**: vendored QR generator/license and exact-match route, host-only ordered phone addresses, Copy/QR/offline behavior, polled firewall banner, console hiding/restoration and Windows Terminal relaunch implemented. Later stale-address and console-detachment changes are documented owner decisions. Fatal-error cleanup is missing (F1).
- **Phase 4**: generated packaged PNG/ICO, PNG favicon and unserved ICO, window identity, checkout/pipx/frozen targets and working directories, host-only shortcut route, labels/action-owned messages and README implemented. The launcher panel has the selector collision (F3); Windows status freshness fails the intended cross-copy behavior (F4).
- No substantive scope creep, module-boundary violation, or new secret/authentication issue identified in the reviewed changes.

## Review Notes

- **Bookkeeping in diff**: context/changes/s12-desktop-window/change.md, context/changes/s12-desktop-window/plan.md, context/changes/s12-desktop-window/research.md, context/changes/s12-desktop-window/icon/preview.png, context/foundation/roadmap.md.
- **Scope representation**: one combined subset report for the explicitly requested Phases 2–4, using phase-2-4 in its filename. It is not a full review and does not supersede the separate Phase 1 report. The boundary includes subsequent fixes through the current head, rather than stopping at the original p4 commit.
- **Excluded unrelated changes within the chronological range**: toolkit version pins in .ai-toolkit/config.json and corresponding README edits; the separately reviewed ci-actions-node24 action-major migration in .github/workflows/test.yml/release.yml and its archive records. The release workflow's actual final build behavior was still checked. No pre-existing local changes were excluded.
- **Lessons**: all 6 entries read; 5 directly applied (manual observation, branch/PR inventory, exact manual steps, no files copied by users, action-owned UI messages). Secret handling was additionally enforced under AGENTS.md.
- **Research observations**: Windows 11 and Fedora 45 Step 15a records and Phase 4 device observations were checked. No real-TV, sign-in, Windows sign-out or Fedora acceptance was newly certified by this review.
- **Artifact evidence**: PR #97 run 42097549651 records successful build and smoke steps on both OSes. Its historical branch SHA is no longer local; the research records the rebase mapping to c4a4e5a. git diff c4a4e5a HEAD -- castlib packaging pyproject.toml is empty.
- **Mutation testing**: skipped entirely — the release/native-library, LAN-control and Windows-divergence risks map to the reviewed implementation, but no mutation tool is configured in the manifest or test plan.
- **Lifecycle metadata**: all Automated rows have ancestral SHAs, but change.md still says implementing. This subset review updates only its date, leaving status unchanged as the skill requires; analysis does not reconcile Progress or acceptance suffixes.
- **Fix disposition**: no product code, tests, plan Progress or acceptance were edited; every finding awaits triage. No commit, PR merge, release tag or tracker update was made.
- **Fontconfig primary source**: [Fontconfig configuration reference](https://fontconfig.pages.freedesktop.org/fontconfig/fontconfig-user.html), read 2026-11-16, supports the documented FONTCONFIG_FILE, FONTCONFIG_PATH and FC_DEBUG mechanisms only; the Fedora binary diagnosis remains an inference from the recorded symptoms.
- **CI evidence**: [PR #80](https://github.com/Piotr-Miller/cast-tv/pull/80), [PR #89](https://github.com/Piotr-Miller/cast-tv/pull/89), [PR #97](https://github.com/Piotr-Miller/cast-tv/pull/97), [tested artifact run](https://github.com/Piotr-Miller/cast-tv/actions/runs/42097549651).

## Triage complete (2026-11-17)

The owner approved all recommended fixes in session. F1–F8 are fixed on branch `s12-review-fixes`. Source changes and workflow records remain uncommitted. The original verdict/header above describe the clean recorded HEAD before these fixes, not approval of this worktree.

| Verification | Result |
|---|---|
| Windows full suite, test-only venv with pytest 9.1.1 / platformdirs 4.13.4 | Exit 0: 524 passed, 5 skipped, 121.65 s |
| Linux full suite, test-only venv, WSL Ubuntu 26.04, Node 26.13.1 | Exit 0: 525 passed, 4 skipped, 64.02 s |
| Final smoke-only malformed-JSON hardening | All 11 smoke regression cases passed after the last edit on both OSes (Windows 0.10 s, Linux 0.18 s). Full-suite counts above precede this one additional case. |
| Final pyflakes on castlib, tests and packaging | Exit 0, no output |
| node --check castlib/ui/app.js; git diff --check | Exit 0 |
| Fresh Windows binary and final smoke script | Exit 0: 26,223,246 bytes; HEIC OK; owned Quit freed port 57916; edgechromium OK (9.8 s) |
| Fresh Linux binary and final smoke script | Exit 0: 249,746,352 bytes; HEIC OK; owned Quit freed port 53517; qtwebengine OK (6.6 s); zero Fontconfig diagnostics |
| Chrome layout at 1180 px / 420 px | Launcher static below phone panel; closed TV dropdown hidden; long errors do not increase scrollWidth; sign-in-help border remains 0 px |
| Original Linux release Fontconfig A/B | Parser identified as 2.13.1; upstream 2.18.3 rules reproduce exactly 45 diagnostics, private configuration gives zero; both runs pass qtwebengine rendering |
| Final acceptance-state.sh | Exit 0: 15 pending, 11 unverifiable across the plan; Phases 2–4 have 0/17 current, 10 pending and 7 unverifiable |

The first current-dependency Windows run had 523 passed, 5 skipped and the documented OneDrive account timeout. The baseline-dependency full run passed without modifying that excluded test. An early new fixture incorrectly assumed every source had close(); its fallback cleanup hung, the required thread dump identified shutdown before serving, and the fixture was corrected. The focused suite then passed (137 passed, 2 skipped).

The first WSL build lacked native build libraries and a Linux browser. The final local build used isolated native support libraries from the prior CI artifact and portable official Chrome for discovery; no system packages were installed. Build/test files use /var/tmp because WSL clears tmpfs /tmp between sessions. This Linux build uses Ubuntu 26.04/glibc 2.43 and Python 3.14.4 and does not replace the release workflow's Ubuntu 22.04/Python 3.12 compatibility build.

All local builds use synthetic client credentials and isolated settings/cache paths. No real sign-in, TV playback, Windows sign-out or Fedora desktop acceptance is newly certified. Private font rules retain standard installed-font discovery and an app-specific XDG cache; arbitrary host/user Fontconfig rule snippets are not imported by default. Explicit FONTCONFIG_FILE/PATH overrides remain supported.

The shared acceptance script ran successfully in Git Bash and WSL against the same checkout and reported the same stale rows. After reopening, the final WSL invocation reports no stale checked rows. change.md retains every prior acceptance revision. Rows 2.7 and 2.9 additionally declare packaging/fonts.conf as a surface. No manual confirmation was restored.

PR CI for these uncommitted fixes remains pending; earlier green PR runs validate only the original reviewed revisions. See `follow-ups/review-fixes.md` for commit, CI and real-device checks. Logs, scratch builds and screenshots are in `.git/rune/s12-fixes/`. The earlier Review Notes describe the pre-triage state.

