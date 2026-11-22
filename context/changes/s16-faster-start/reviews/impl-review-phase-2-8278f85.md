<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: A faster-starting release file (Nuitka)

- **Plan**: context/changes/s16-faster-start/plan.md
- **Scope**: Phase 2 (phases 1–7)
- **Session**: fresh
- **Base**: adb54e44b5dee18a4959fe1ad5f8092fa87d3ca6 (previous phase's final accepted state, including its review fixes)
- **Head**: dbb1b529677514d0a7d76159a6d002cc66598b6b
- **Worktree**: included(context/changes/s16-faster-start/plan.md)
- **Checks ran at**: dbb1b529677514d0a7d76159a6d002cc66598b6b, before triage edits
- **Manual acceptance**: none planned for Phase 2
- **Date**: 2026-11-19
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | FAIL |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Nuitka bundled data is looked up beside the outer launcher

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: castlib/bundle.py:147
- **Detail**: The plan requires the Nuitka main module's directory. Instead, data_dir prefers __compiled__.containing_dir. Nuitka 4.3.5 defines that as the directory containing the outer onefile binary; bundled files live in the unpack directory identified by main.__file__. A realistic main with containing_dir=Downloads and __file__=cache/cast-tv/0.6.0-gh1.1/entry.py returns Downloads from both data_dir and cache_dir. Fontconfig consequently misses its bundled configuration. The test_bundle and test_platform fakes incorrectly set containing_dir to the unpack directory, hiding the error. Vendor evidence: [Nuitka 4.3.5 manual, finding files](https://github.com/Nuitka/Nuitka/blob/4.3.5/README.rst#onefile-finding-files), including the preceding python_runtime_dir versus containing_dir explanation.
- **Fix**: Derive the Nuitka data directory from main.__file__, and make the affected fakes distinguish the outer launcher directory from the unpack directory.
  - Strength: Implements the plan directly and repairs the shared data/cache facts and the Fontconfig caller together.
  - Tradeoff: Test fixtures must describe the vendor's actual two-directory layout.
  - Confidence: HIGH — the pinned vendor manual explicitly distinguishes the directories, and a local reproduction returns the wrong one.
  - Blind spot: An actual Nuitka artifact remains subject to the later build and owner acceptance phases.
- **Decision**: FIXED — recommended Fix; siblings: cache_dir fixed through the shared data_dir helper, castlib/platform.py use_bundled_font_config fixed through that helper, tests/test_platform.py Nuitka fixture fixed; reopened: none (all Manual rows were already pending).

### F2 — Startup path resolution still depends on later process state

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/bundle.py:130
- **Detail**: The plan's Critical Implementation Details require started_file to resolve once at import. The implementation captures CWD and PATH strings but repeats which/exists on each call. Real shutil.which interprets relative and empty PATH entries against the current directory, before the returned path is anchored to the startup directory. With startup CWD equal to the venv's Scripts folder and PATH='.', resolving its existing python.exe from the checkout returns None. Later PATH contents can also change which file a repeated lookup selects. The relative-PATH test replaces which with a stub, so it cannot expose this behavior.
- **Fix**: Anchor relative and empty PATH entries to the captured startup CWD before lookup, freeze the default launch-path result at import, and retain an injectable resolver for tests. Add regressions using real which after chdir and for immutable import-time resolution.
  - Strength: Preserves the actual launch identity for menu targets and detached relaunches, including relative PATH starts, while retaining test injection.
  - Tradeoff: Separates live import-time facts from explicitly injected lookups.
  - Confidence: HIGH — reproduced with a real executable and real which on this Windows host; both independent review passes confirmed it.
  - Blind spot: Real desktop launch behavior still needs the later owner acceptance rows.
- **Decision**: FIXED — recommended Fix; siblings: castlib/platform.py leave_terminal_tab and castlib/shortcut.py MenuEntry fixed through the shared started_file helper, castlib/shortcut.py _own_launcher n/a (existing checkout/pipx launcher, not a onefile release); searched all started_file/containing_dir uses in castlib, tests and packaging; reopened: none (all Manual rows were already pending).

## Review Notes

- **Bookkeeping in diff**: context/changes/s16-faster-start/change.md, context/changes/s16-faster-start/plan.md.
- Excluded local change: temp_steps.md (pre-existing handoff update). Included local plan edits only add the phase commit SHA to Automated rows 2.1–2.4.
- All six lesson entries were read. Two of six explicitly apply to implementation review or every session; the remaining surface-specific rules were checked where relevant. No secrets or stored tokens were read.
- Progress: phases 1 and 2 have suffixed Automated rows whose commits are ancestors of HEAD; phases 3–7 remain pending. No malformed n/a rows or unsuffixed completed Automated rows in the working plan. Phase 2 has no Manual rows.
- Acceptance script: Git Bash invocation exited 0; every Manual row is pending. Row 1.7 was already reopened by Phase 2; no confirmation is implied by this review.
- Gate interpreter: .venv/Scripts/python.exe (Python 3.14.5). The global python lacked pytest and pyflakes; the established project venv supplies both. No dependency or application failure was inferred from the global interpreter.
- Row 2.1: .venv/Scripts/python.exe -m pytest tests/test_bundle.py -q — exit 0; `12 passed, 1 skipped in 0.21s` (symlink creation unavailable on this account).
- Row 2.2: .venv/Scripts/python.exe -m pytest tests/test_platform.py tests/test_shortcut.py tests/test_window.py -q — exit 0; `137 passed in 12.70s`.
- Row 2.3: .venv/Scripts/python.exe -m pyflakes castlib tests packaging — exit 0; no output.
- Row 2.4: .venv/Scripts/python.exe -m pytest — exit 0; `612 passed, 7 skipped in 118.28s`.
- Mutation check skipped: the change maps to the Risk Map's Windows/Linux divergence and bundled-library behavior through Phase 2's platform/data contracts, but no mutation tool is configured in pyproject.toml or the test plan. No paid or release-build criteria apply to this phase; packaging and workflow files are unchanged.
- Plan-drift and safety/pattern passes independently reviewed the four product files and their tests; caller behavior otherwise matches the plan and existing injection/error-handling patterns.
- Owner instruction in this session: fix all findings using the recommended approach. Triage proceeds without another permission question. This skill leaves its report and fixes uncommitted.

## Triage (2026-11-19)

- Fixed F1 and F2 using the single recommended fix for each. The verdict above records the original implementation; these fixes are uncommitted working-tree changes on top of its Head.
- Files edited: castlib/bundle.py, tests/test_bundle.py, tests/test_platform.py. The existing local plan.md and temp_steps.md edits were preserved.
- Regression proof before changing production code: the strengthened bundle/platform tests exited 1 with `6 failed, 63 passed, 1 skipped in 1.50s`. Failures covered real relative PATH resolution, import-time identity, the data/cache directory and the Fontconfig caller. The import-time test also checks that an initially missing path stays unavailable after later filesystem/argv changes.
- One existing fixture used the POSIX path /usr/bin on Windows. It now uses an absolute temporary directory on the host so it continues to verify captured PATH unchanged, independently of OS path syntax.
- Focused verification: .venv/Scripts/python.exe -m pytest tests/test_bundle.py tests/test_platform.py tests/test_shortcut.py tests/test_window.py -q — exit 0; `154 passed, 1 skipped in 11.94s`.
- Lint: .venv/Scripts/python.exe -m pyflakes castlib tests packaging — exit 0; no output.
- Independent read-only verification of the fixes found no substantive new regressions; the injected resolver and PyInstaller callers retain their behavior.
- Acceptance script rerun after the fixes: exit 0, all Manual rows pending; none reopened and no confirmations written.
- Final full suite: .venv/Scripts/python.exe -m pytest — exit 0; `617 passed, 7 skipped in 122.43s`. Node was available and the UI behavior tests ran. The seven skips remain the existing platform/account-dependent cases.
- Final whitespace check: git diff --check — exit 0. F1 and F2 are both fixed; no pending triage decisions remain. The report, follow-up record, change stamp and three edited code/test files are carried for the next implementation commit.
