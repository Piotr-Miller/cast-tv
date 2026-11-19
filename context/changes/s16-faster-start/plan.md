# A faster-starting release file (Nuitka) Implementation Plan

## Overview

This plan builds both release files with Nuitka in onefile mode, with a cached unpack folder,
instead of PyInstaller. Every start after the first then reuses the unpacked files instead of
unpacking 260 MB (Linux) or 26 MB (Windows) again.

The switch happens only if the medians measured on the owner's real machines meet the bars
agreed below. If either system misses its bar, the work stops at the decision and the owner
decides again. Behaviour accepted in S-12 must not change, including the Windows console
behaviour.

Revised on 2026-11-18 after the plan review (`reviews/plan-review.md`, RETHINK). The owner chose
the age-guarded safe delete for F2 and Codex's fixes for F1 and F3-F9.

## Current State Analysis

- **The release** is a PyInstaller onefile per system, built from `packaging/cast-tv.spec` in
  `.github/workflows/release.yml`.
  - PyInstaller documents that it unpacks to a new temporary folder on every start and deletes it
    on exit. `--runtime-tmpdir` only moves that folder (research.md, Spike, read 2026-11-18).
  - v0.5.0 sizes: Windows 26,123,741 B, Linux 260,589,552 B.
- **The spike** (research.md, 2026-11-18) used Nuitka 4.3.5 with
  `--onefile-tempdir-spec={CACHE_DIR}/…`. It keeps the unpacked files, later starts reuse them,
  and both builds passed `--window-check`.

  | | Nuitka | PyInstaller |
  | --- | --- | --- |
  | Warm `--version`, Windows | 2.4–2.7 s | 3.6 s |
  | Warm `--version`, Linux CI | 1.6 s | 4.2 s |
  | `--window-check`, Linux CI | 2.2 s | 4.8 s |
  | `--window-check`, Windows | 4.3–5.1 s | 5.9–7.2 s |
  | Linux file | 154.8 MB | 260.6 MB |
  | Build time | 16 min (Windows), 10 min (CI) | — |
- **Nuitka checks the cache on every start** (origin: vendor source,
  `nuitka/build/static_src/OnefileBootstrap.c:1295-1298` in 4.3.5). In cached mode, the outer
  bootstrap computes each unpacked file's CRC32 and rewrites any file whose checksum differs from
  the payload's. Only after that does it start the child from inside the cache
  (`:1394-1426,1472-1492`, per the review).
  - A damaged or stale cache heals itself.
  - The cost is reading the whole cache on every start: 546 MB on Linux.
  - The bootstrap runs outside the cache while it reads and writes it (review F2).
- **Nuitka exposes the started file**: `__compiled__.original_argv0`, described as "original
  argv[0] as received by the onefile binary".
  - The bootstrap keeps that value in `NUITKA_ORIGINAL_ARGV0` (`OnefileBootstrap.c:1390`), and the
    child gets `NUITKA_ONEFILE_PARENT` (`:1067,1129`).
  - The value can be a bare name when the file was started through PATH (review F7).
  - Relaunching the outer file with the onefile variables removed is supported (review, vendor
    evidence).
- **Nuitka's console mode `hide`**: "a newly spawned console will be hidden and an already
  existing console will behave like 'force'" (`--help`, 4.3.5).
  - It hides a console only when the process is that console's sole user
    (`HelpersConsole.c:201-216`).
  - Both the bootstrap and the child run it early (review, vendor evidence).
  - This is the counterpart of PyInstaller's `hide_console="hide-early"`. It does not prove that
    the Windows Terminal tab or the fallback behave the same: rows 7.1-7.3 do that.
- **Cached Windows builds run an executable child, not the DLL onefile mode**: DLL mode applies
  only to temporary specs (`Options.py:1554-1571,2545-2577`; the spike's build recorded
  `dll_mode=false`).
- **Code that assumes PyInstaller** (origin: code). Every product read of `sys.frozen`,
  `sys._MEIPASS` and `sys.executable` is in three modules (the review's caller sweep). Under Nuitka
  each would silently switch off:
  - `castlib/platform.py:508` `leave_terminal_tab`, the Windows Terminal relaunch (row 3.10): it
    sets `PYINSTALLER_RESET_ENVIRONMENT` at `:517` and restarts `sys.executable` at `:518`.
  - `castlib/platform.py:801-815` `use_bundled_font_config`, the private Fontconfig rules (F7).
  - `castlib/platform.py:827` `use_system_ca_bundle`.
  - `castlib/shortcut.py:165,185,344-347,368,383`: the menu entry's target, icon, window style
    and D-Bus environment.
  - `castlib/window.py:79` `identity`.
- **Under Nuitka's cached onefile, `sys.executable` is the unpacked copy in the cache**, not the
  file the user started.
- **The UI's first render.**
  - `castlib/ui/index.html:12` has both `x-data="castTv()"` and `x-init="init()"`, and Alpine also
    calls a component's `init` by itself, so `init()` runs twice (review F1, reproduced in Node).
  - `castlib/ui/app.js:119-139` `refresh()` swallows errors, and it awaits `/api/errors` after
    assigning the status.
  - `castlib/window.py:213` calls `on_shown` once, from pywebview's event worker.
  - `castlib/cli.py:342-343` prints the shown message.
- **`packaging/smoke.py`** recognises its own process by `instance.pid` or `instance.parent_pid`,
  and its `stop()` waits for that process to exit as well as for the port to be free.
- **The Windows firewall prompt** is per program path. Under Nuitka the listening program sits in
  the versioned cache folder, so each new version is likely to prompt again. The app's firewall
  advice is port-based (`castlib/platform.py:38`).
- **Full suite at planning:** exit 1 on 2026-11-18 (the intermittent
  `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving`, which passes alone). Re-run by the
  review the same day: exit 0, 527 passed, 5 skipped. Each phase requires exit 0. A failure is
  investigated and reproduced, never waved through.

### Carried from predecessor

none — no Predecessor line

## Definitions

| Term | Decided meaning | Origin | On degenerate data | Verified by |
| ---- | --------------- | ------ | ------------------ | ----------- |
| Ready UI | The cast-tv window is on screen (`on_shown`), and the page has rendered its first *successful* `/api/status` answer with the main controls bound and usable. TV discovery may still run. | user (2026-11-18) | A failed first status: not ready; a later success marks it. A second `init()`: marks nothing. A slow `/api/errors`: does not delay the mark. A window that never shows: no mark; the run fails after its timeout. | 1.1, 1.2, 5.3, 5.4 |
| Start time | Wall time from the script launching the file ("Enter") to Ready UI, on the same desktop for both builds. | user | A cast-tv process already running, on any port or as a bootstrap: the script refuses to measure. | 1.3, 5.1, 5.2 |
| Cold start | The first launch of a version after an update. No reboot, OS file cache not cleared, every cast-tv process closed. Nuitka: that version's cache folder is absent before each run. PyInstaller: its normal unpack. | user | A partial cache from a killed first start counts as present (Nuitka's CRC repairs it). Measured cold runs delete the validated folder first. | 1.3, 5.1, 5.2, 7.11 |
| Warm start | A launch with the version's cache present, after one unmeasured priming start. | user | — | 1.3, 5.1, 5.2 |
| Median | The median of 5 measured runs per build, mode and system. | user | A run that times out fails the measurement; there is no median of 4. | 1.3 |
| The bar | Per system. Linux: Nuitka's warm median ≤ 50 % of PyInstaller's. Windows 11: ≤ 75 %. On both, Nuitka's cold median ≤ PyInstaller's. All accepted behaviour stays correct. | user | Exactly 50 % or 75 % passes, and an equal cold median passes. Either system failing: stop and report; the decision is revisited. | 1.3, 5.5, 5.6 |
| Build identity | `<version>-<build>`. `<build>` is `gh<run id>.<run attempt>` in CI, or `local<UTC yyyymmddHHMMSS>` for a local build. The cache folder is `{CACHE_DIR}/cast-tv/<build identity>`. One grammar is shared by the builder, the pruner and the script: `^\d+\.\d+\.\d+-(gh\d+\.\d+\|local\d{14})$`. | plan (review F6) | `%LOCALAPPDATA%\cast-tv\Cache` (the GoPro browser cache), the spike's `0.5.0` and any other non-matching name are never touched. A re-run of the same commit gets a new identity. | 3.1, 4.1 |
| Current, previous | Current: the folder this process runs from. Previous: of the other matching folders, the one with the newest start marker. With no marker anywhere, the newest by modification time. A tie goes to the greater name. | user (keep current + previous); plan (marker, tie-break) | Mixed: marked folders win over unmarked ones. A single folder: nothing else exists. | 3.1 |
| Removable | A matching folder that is neither current nor previous, whose start marker (or, without one, its modification time) is at least 7 days old, and from which no running process's executable comes. | user (2026-11-18: age guard + safe delete) | The process list is incomplete (access denied for a same-user process, or an error): nothing is removed. A process that vanished during the scan is ignored. Rename fails (a locked file on Windows): the folder stays. | 3.1, 7.10 |

## Desired End State

- `cast-tv-linux-x64` and `cast-tv-windows-x64.exe` are Nuitka onefiles. The first start of a
  build unpacks into its cache folder, and later starts reuse it.
- `startup_time.py` measures Start time to the Ready mark for any build that has the mark.
  Medians for both systems and both builds are in research.md. Each system met its bar, and the
  published files are recorded as equivalent to the measured ones.
- Every behaviour accepted in S-12 holds on the published Nuitka files:
  - the window, Ctrl+C, closing, signing out and the second launch;
  - the hidden console on a double-click, the Terminal relaunch, and the console shown again on a
    fallback;
  - the menu entry: add, update and remove;
  - HEIC, HTTPS on Fedora, and the private Fontconfig rules.
- The cache keeps the current and previous build folders, plus any folder started within the last
  7 days or in use. Older ones go on the next start, and a folder in use is never deleted.
- `--version` names the cache folder. README says where the files go, how much disk they take,
  and the retention rule.

Verify: the Progress rows. The decision rows 5.5 and 5.6 gate Phases 6 and 7, and row 6.4 ties
the measurements to the published files.

### Key Discoveries:

- Nuitka's cached mode self-heals by checking the CRC of each file (`OnefileBootstrap.c:1295-1298`).
  The check runs in the outer bootstrap, outside the cache, before the child starts.
- The started file is `__compiled__.original_argv0`, which may be a bare PATH name.
  `sys.executable` is the cached copy.
- `castlib/platform.py:517` is a relaunch flag for PyInstaller only. Under Nuitka, the relaunched
  outer file must not inherit `NUITKA_ONEFILE_PARENT` or the other onefile variables.
- `index.html:12` starts `init()` a second time; Ready must not depend on `init()` returning.

## What We're NOT Doing

- No onedir archive, installer, or macOS.
- No change to Nuitka's bootstrap. A bootstrap failure, such as a full disk or an unwritable
  cache, shows Nuitka's own message. On a Windows double-click with a hidden console it may show
  nothing. This is recorded as a risk, not handled.
- No exclusion lock between a starting bootstrap and the pruner. The vendor bootstrap cannot take
  part in one. The age guard leaves one residual race: an older build unused for at least 7 days,
  started at the very moment another build prunes it. Its next start unpacks again.
- No code signing; SmartScreen behaves as today.
- No firewall rule automation for the per-build program path. The prompt is observed in row 7.12.
- No reduction of Qt WebEngine's size, and no run-time fallback to PyInstaller.

## Implementation Approach

1. Measure first, with a tool that also measures an instrumented PyInstaller build of the same
   source.
2. Make the code independent of the packager, so one source runs correctly under either.
3. Add the age-guarded pruning.
4. Build both packagers' files from the same commit in CI, and measure them on the owner's
   machines.
5. Switch only after both bars are met, and record that the published files are equivalent to the
   measured ones.
6. Re-accept the behaviour rows on the switched files. Directory-wide surfaces make any later
   change reopen them.

## Critical Implementation Details

- **The Ready mark is not tied to `init()`.** `init()` runs twice (`index.html:12` and Alpine
  itself). The mark follows the first successful status that was assigned and then rendered:
  - after Alpine's `$nextTick`, then two animation frames;
  - posted without awaiting `/api/errors`;
  - one-shot per page;
  - a failed refresh never marks.

  Removing `x-init="init()"` makes `init()` run once.
- **Measurement preconditions are process-wide.** cast-tv may run on another port (`-p`), or as a
  bootstrap only. The script refuses while any process runs that is one of these:
  - an image inside the cast-tv cache parent;
  - a file named `cast-tv*`;
  - the measured file itself.

  It reuses the process lister from Phase 1.
- **Safe delete.** Rename the folder to a sibling `<name>.removing-<pid>` first. On Windows the
  rename fails if any file inside is locked, and then the folder stays. Only the renamed copy is
  deleted recursively. A partly deleted `.removing-*` copy left by an earlier run is finished on a
  later start.
- **Ordering of the switch.** Phase 6 changes `release.yml` and removes the spec, which makes the
  rows of Phase 5 stale by surface. Row 6.4 records the equivalence and re-confirms them, or
  measures again. Phase 7 is accepted on Phase 6's PR files.
- **`started_file()` is resolved once, at import, before any change of working directory.**

## Phase 1: Measure the start

### Overview

A Ready mark in the app, a process lister, and a script that times cold and warm starts of a
release file to the mark and computes medians and the bar. Row 1.7 uses a PyInstaller build of
this phase's source. The released v0.5.0 has no mark, and the script says so.

### Changes Required:

#### 1. The Ready mark

**Files**:
- `castlib/ui/index.html`: `x-init="init()"` is removed, so Alpine's own call runs `init()` once.
- `castlib/ui/app.js`: after the first `refresh()` that assigned a status, a one-shot `_readyMarked` waits for `$nextTick` and two animation frames, then posts `/api/ready` without awaiting it. Failed refreshes skip it; a later success marks.
- `castlib/api.py`: `/api/ready` joins `HOST_ONLY` (loopback, POST). The loopback-only `instance` block gains `ui_ready_at` and `shown_at`.
- `castlib/app.py`: the app keeps the first `ui_ready_at` and `shown_at` (wall-clock seconds).
- `castlib/window.py`: `shown()` records `shown_at`.
- `castlib/cli.py`: keeps the existing shown message at `:342-343`.

**Intent**: Give the measuring script an exact moment for the owner's "Ready UI" that is
independent of the packager.

**Contract**:
- `POST /api/ready` `{}` → `200 {"ok": true}`, from loopback only. Repeated posts keep the first
  time.
- `GET /api/status` from loopback: `instance` = `{id, pid, parent_pid, ui_ready_at, shown_at}`.
  The two times are floats or `null`.
- No LAN client sees these fields.

#### 2. The process lister

**File**: `castlib/processes.py`

**Intent**: One way to see running processes' executables, shared by the script (Phase 1) and the
pruner (Phase 3).

**Contract**: `running_images() -> list[tuple[int, str]]` returns (pid, image path) for every
process the current user can see.
- Linux reads `/proc/*/exe`. Windows uses `EnumProcesses` + `QueryFullProcessImageNameW` through
  ctypes.
- A process that vanished during the scan is skipped.
- Access denied for a process of the current user, or an API error, raises `IncompleteListing`.
- (owner decision 2026-11-19) Windows: an image query refused with access denied counts as not ours unless WTS names our SID; unelevated Windows reports no owner for its protected and service processes (176 of 451), so requiring an owner would make every listing incomplete. Verified on the home laptop (research.md, "Windows ownership without elevation").
- Other users' processes that deny access are skipped.

#### 3. The measuring script

**File**: `packaging/startup_time.py`

**Intent**: Time N starts of a release file, cold or warm, to the Ready mark, and compare two
result files against the bar.

**Contract**:
- `python packaging/startup_time.py <binary> --mode cold|warm --runs 5 --out <json>`:
  - **Preflight, before every run.** It refuses (exit 2) when:
    - `running_images()` shows a cast-tv process (any image inside the cast-tv cache parent,
      named `cast-tv*`, or the measured file);
    - the listing is incomplete.
  - **Cold mode.** The folder named by `--version`'s `Cache:` line must sit under
    `<platform cache root>/cast-tv/` and match the build identity grammar, or the script refuses.
    That folder is deleted before each run. PyInstaller has no folder, so nothing is deleted.
  - **Warm mode.** One unmeasured priming run comes first.
  - **Each run.**
    - Launch with `-p <free port>`.
    - Ready = max(`ui_ready_at`, `shown_at`) − launch time.
    - End with `smoke.py`'s ownership-checked `stop()`, which waits for both the process and the
      port.
  - **A file without the fields** (`instance` lacks `ui_ready_at`) fails at once (exit 3) with "this
    build has no Ready mark (built before s16-faster-start)".
  - **No mark within 120 s** fails the measurement (exit 1).
  - **The JSON** holds the binary's path, size and SHA-256, the `--version` text, the system, the
    mode, every run's seconds and the median.
- `python packaging/startup_time.py --compare <nuitka.json> <pyinstaller.json> --warm-ratio <r>`
  prints both medians, the ratio and PASS/FAIL. Cold passes at ≤ 1.0 ×, warm at ≤ r.

### Success Criteria:

#### Automated Verification:

- Ready mark and status fields: `python -m pytest tests/test_api.py -q` — at planning: exit 0 — (new cases added in Phase 1)
- UI Ready cases: `python -m pytest tests/test_ui.py -q` — at planning: exit 0 — (new cases added in Phase 1). The cases: a single `init()` only; a duplicate `init()` marks nothing; a delayed first status; a failed first status, then a successful retry marks; a slow `/api/errors` does not delay the mark; one post per page.
- Lister and script: `python -m pytest tests/test_processes.py tests/test_startup_time.py -q` — not run: needs Phase 1 output. The cases: median; timeout; refusal on another port's instance and on a bootstrap-only process; incomplete listing; cold deletion only of a validated folder; a missing-mark binary; `--compare` at 0.5 (PASS), just above (FAIL), and an equal cold median (PASS).
- `node --check castlib/ui/app.js` — at planning: exit 0
- `python -m pyflakes castlib tests packaging` — at planning: exit 0
- Full suite: `python -m pytest` — at planning: exit 1 (2026-11-18, the intermittent); review re-run: exit 0 — must exit 0

#### Manual Verification:

- Windows: `startup_time.py` on a PyInstaller exe built from this phase's commit (`pyinstaller packaging/cast-tv.spec`, its SHA-256 recorded). 5 warm runs finish. The owner watches one run: the window shows the TV button and the source tabs, and a tab click responds at the moment the terminal prints that run's time. — surface: castlib/, packaging/startup_time.py, packaging/smoke.py, packaging/cast-tv.spec

**Implementation Note**: Manual checks are acceptance. A pending manual check is reported, not a
blocker for the next phase.

---

## Phase 2: Code that runs under either packager

### Overview

One module answers three questions: which packager built this file (if any), which file the user
started, and where the bundled data is. Every `sys.frozen`, `sys._MEIPASS` and release-only
`sys.executable` use goes through it. Under PyInstaller nothing changes.

### Changes Required:

#### 1. The bundle facts

**File**: `castlib/bundle.py`

**Intent**: The single place that knows PyInstaller from Nuitka.

**Contract**:
- `kind()` returns `"pyinstaller"`, `"nuitka"` or `None`. Nuitka is recognised by `__compiled__`
  on the main module with `onefile` set.
- `started_file() -> str | None`:
  - PyInstaller: `sys.executable`.
  - Nuitka, `original_argv0` is absolute: that path.
  - Nuitka, `original_argv0` contains a separator: joined with the working directory captured at
    import.
  - Nuitka, a bare name: `shutil.which` on the PATH captured at import.
  - Symlinks are kept, not resolved.
  - When none exists: `None`. The menu entry then answers "start cast-tv from its file once".
- `data_dir() -> str | None`: `sys._MEIPASS`, or the Nuitka main module's directory.
- `cache_dir() -> str | None`: the Nuitka build folder (the data dir), or `None`.
- `relaunch_env(environ) -> dict`: a copy for starting `started_file()` as a new instance.
  - PyInstaller: `PYINSTALLER_RESET_ENVIRONMENT=1`.
  - Nuitka: `NUITKA_ONEFILE_PARENT`, `NUITKA_ORIGINAL_ARGV0` and the other `NUITKA_*` onefile
    variables removed.
  - Both keep `CAST_TV_DETACHED` handling to the caller.
- All inputs are injectable for tests.

#### 2. The callers

**Files**:
- `castlib/platform.py`: `leave_terminal_tab` starts `bundle.started_file()` with `bundle.relaunch_env()`, keeping `CAST_TV_DETACHED`, the arguments and `CREATE_NO_WINDOW`. The Fontconfig and CA bundle helpers use `bundle.kind()` and `bundle.data_dir()`.
- `castlib/shortcut.py`: `MenuEntry` uses `bundle.kind()` and `bundle.started_file()` for its target, icon and window style. The D-Bus environment handles PyInstaller's `LD_LIBRARY_PATH_ORIG` and Nuitka's.
- `castlib/window.py`: `identity` uses `bundle.kind()`.

**Intent**: Under Nuitka, behave exactly as the PyInstaller release does today. Under PyInstaller
and outside a release, behave exactly as now.

**Contract**: Existing parameters such as `frozen=` and `executable=` keep working for tests.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/test_bundle.py -q` — not run: needs Phase 2 output. The cases: the three kinds; `started_file` absolute, relative from another working directory, a bare name on PATH, a path with spaces, a symlink kept, and missing; `relaunch_env` per kind.
- Callers under all three kinds: `python -m pytest tests/test_platform.py tests/test_shortcut.py tests/test_window.py -q` — at planning: exit 0 — (Nuitka cases added in Phase 2)
- `python -m pyflakes castlib tests packaging` — at planning: exit 0
- Full suite: `python -m pytest` — at planning: see Phase 1 — must exit 0

---

## Phase 3: Old cache folders

### Overview

At start, a Nuitka release removes its own old build folders, by the owner's rule with the age
guard and the safe delete.

### Changes Required:

#### 1. Pruning

**Files**:
- `castlib/bundle.py`: `prune_caches()`, plus the start marker.
- `castlib/cli.py`: calls it once at start, in a background thread, after the window shows, and only for a Nuitka release.

**Intent**: Bound the disk use while never deleting a folder that is in use or was used recently.

**Contract**: `prune_caches(cache_dir, processes=running_images, now=time.time, rename=os.rename,
remove=shutil.rmtree, min_age_days=7) -> list[str]` returns the folders removed.
1. Touch `<cache_dir>/.cast-tv-started`.
2. Candidates are the siblings that match the build identity grammar.
3. Keep the current folder, and the previous one per Definitions (marker, mtime fallback,
   tie-break).
4. Every other candidate is removable only when its marker (or mtime) is ≥ 7 days old and no
   listed image lies inside it.
5. `IncompleteListing` means nothing is removed.
6. A removable folder is renamed to `<name>.removing-<pid>`. If the rename fails, it stays. The
   renamed copy is removed recursively, and errors are ignored.
7. Leftover `*.removing-*` siblings are removed.

### Success Criteria:

#### Automated Verification:

- Pruning cases: `python -m pytest tests/test_bundle.py -q` — not run: needs Phase 2 output. The cases:
  - three builds, the oldest 8 days old, is removed;
  - an old folder 6 days old is kept;
  - an old folder in use is kept;
  - an incomplete listing removes nothing;
  - no markers: the mtime fallback applies;
  - mixed marked and unmarked folders;
  - a tie in the marker time, and a tie in mtime;
  - a single build;
  - `Cache`, `0.5.0` and other foreign names are untouched;
  - a rename failure keeps the folder;
  - a removal error;
  - a leftover `.removing-*` is finished.
- `python -m pyflakes castlib tests packaging` — at planning: exit 0
- Full suite: `python -m pytest` — must exit 0

---

## Phase 4: Nuitka builds next to PyInstaller

### Overview

The release workflow builds both packagers' files from the same commit on both systems, and
smoke-tests all four. A tag still publishes the PyInstaller files until Phase 6.

### Changes Required:

#### 1. The Nuitka build

**File**: `packaging/build_nuitka.py`

**Intent**: One command that builds the Nuitka onefile for the running system, with the same
contents and behaviour as `packaging/cast-tv.spec`.

**Contract**: `python packaging/build_nuitka.py --out <path> [--build-id <id>]` builds from
`packaging/entry.py`:
- **Cache spec:** `--onefile` with `--onefile-tempdir-spec={CACHE_DIR}/cast-tv/<build identity>`.
  `<build>` comes from `--build-id`, else from `GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT`, else
  `local<UTC timestamp>`. The identity is validated against the shared grammar.
- **Contents:** product and file version from `castlib.__version__`; `castlib`, `pillow_heif` and
  their data; `tkinter`, `pytest` and `gi` not followed.
- **Windows:** WinForms backend, `--windows-console-mode=hide`, the `.ico`.
- **Linux:** `pyside6` plugin, Qt backend, `qtpy`; `libgbm.so*` and `libstdc++.so*` excluded;
  `packaging/fonts.conf` at `fontconfig/fonts.conf` in the data dir.
- **Nuitka version:** pinned. The script fails unless `nuitka.Version` is 4.3.5.
- **Provenance:** `<out>.build-info.json` holds the identity, the Nuitka, Python and pip-freeze
  hash, the commit, and the exact option list.

#### 2. `--version` names the cache

**File**: `castlib/cli.py`

**Intent**: The script, and a curious user, can see where the files go.

**Contract**: The output gains a `Cache: <folder>` line under Nuitka, and `Cache: none` otherwise.

#### 3. The workflow

**File**: `.github/workflows/release.yml`

**Intent**: Build, smoke-test and upload both packagers' files on both systems.

**Contract**:
- Installs `nuitka==4.3.5 zstandard ordered-set`, and `patchelf` on Linux.
- The Nuitka files are uploaded as `cast-tv-linux-x64-nuitka` and `cast-tv-windows-x64-nuitka.exe`,
  each with its `build-info.json`. The PyInstaller files keep their names.
- `smoke.py` runs on all four files.
- The `release` job still publishes only the PyInstaller files.

#### 4. The smoke test

**File**: `packaging/smoke.py`

**Intent**: Prove a Nuitka file is as complete as the PyInstaller one.

**Contract**: For a Nuitka file, it also requires a `Cache:` line naming a folder that matches the
grammar.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/test_smoke.py tests/test_build_nuitka.py tests/test_cli.py -q` — not run: needs Phase 4 output. `test_build_nuitka` covers: the options per system; the identity from `--build-id`, from the CI variables and as local; a grammar rejection; the version pin; the provenance file.
- `python -m pyflakes castlib tests packaging` — at planning: exit 0
- (paid) The PR's release workflow builds and smoke-tests four files green: `gh run watch <run> --exit-status` — artifact: the PR run's four artifacts and their build-info — not run: external

---

## Phase 5: Measure on the owner's machines and decide

### Overview

The owner runs `startup_time.py` on the Fedora desktop and the Windows 11 laptop, against both
files of one Phase 4 PR run. Results go to research.md, and the bars decide.

### Changes Required:

#### 1. Results

**File**: `context/changes/s16-faster-start/research.md`

**Intent**: Record, per system, both builds' cold and warm runs, the medians, the ratios and
PASS/FAIL, with the run ID, the SHA-256 of the files and their build-info.

**Contract**: One section per system, with the commands verbatim.

### Success Criteria:

#### Manual Verification:

- Fedora, in a terminal in the checkout:
  1. Download the PR run's two Linux files.
  2. Run `startup_time.py` cold then warm on each.
  3. Run `--compare … --warm-ratio 0.5`.

  The terminal prints PASS/FAIL per mode; the results and both JSON files go to research.md.
  — surface: castlib/, packaging/, pyproject.toml, .github/workflows/release.yml
- Windows 11, in PowerShell in the checkout: the same with the Windows files and `--warm-ratio 0.75`. — surface: castlib/, packaging/, pyproject.toml, .github/workflows/release.yml
- Fedora: the owner watches one Nuitka warm run. The window shows the TV button and the source tabs, and a tab click responds when the run's time prints. — surface: castlib/ui/, castlib/window.py, castlib/api.py, castlib/app.py
- Windows 11: the same watched run. — surface: castlib/ui/, castlib/window.py, castlib/api.py, castlib/app.py
- Linux bar met, or the owner's decision after a miss recorded — surface: castlib/, packaging/, pyproject.toml, .github/workflows/release.yml
- Windows bar met, or the owner's decision after a miss recorded — surface: castlib/, packaging/, pyproject.toml, .github/workflows/release.yml

**Implementation Note**: If either bar is missed, stop after this phase and report to the owner.
Phases 6 and 7 do not start without the owner's decision.

---

## Phase 6: Switch the release to Nuitka

### Overview

The release publishes the Nuitka files under the existing asset names. PyInstaller leaves the
build. README describes the cache. The published files are shown to be equivalent to the measured
ones.

### Changes Required:

#### 1. Release

**Files**:
- `.github/workflows/release.yml`: only the Nuitka build, its files under the release names `cast-tv-linux-x64` and `cast-tv-windows-x64.exe`, smoke-tested and published.
- `packaging/cast-tv.spec`: deleted.
- `packaging/startup_time.py`: it no longer refers to the spec.

**Intent**: One packager, and the asset names users already know.

**Contract**: The asset names are unchanged. `smoke.py` runs on both published files.

#### 2. README

**File**: `README.md`

**Intent**: Users know these things:
- the first start of a new version unpacks;
- where the files go and how much disk they take;
- that cast-tv keeps the current and previous versions, plus any used in the last 7 days or still
  running;
- that Windows may ask about the firewall again after an update.

**Contract**: The install section and Limitations.

### Success Criteria:

#### Automated Verification:

- `python -m pytest tests/test_smoke.py tests/test_build_nuitka.py -q` — not run: needs Phase 4 output
- Full suite: `python -m pytest` — must exit 0
- (paid) The PR's release workflow is green with the two Nuitka files under the release names: `gh run watch <run> --exit-status` — artifact: the PR run's two artifacts and their build-info — not run: external

#### Manual Verification:

- Equivalence. Compare the published files' `build-info.json` with the measured files' from Phase 5: the Nuitka version, the option list, the Python version, the pip-freeze hash, and the `castlib/` and `packaging/build_nuitka.py` contents at both commits (`git diff --stat <measured>..<published> -- castlib packaging/build_nuitka.py packaging/entry.py packaging/fonts.conf`).
  - Equal apart from names: record it in research.md and re-confirm rows 5.1-5.6 at this revision.
  - Otherwise: measure Phase 5 again on the published files.
  - surface: castlib/, packaging/, pyproject.toml, .github/workflows/release.yml

---

## Phase 7: The accepted behaviour on the Nuitka files

### Overview

S-12's behaviour rows run again on Phase 6's PR files, plus the rows the cache adds. Every row's
surface covers `castlib/`, `packaging/` and the workflow, so any change in this phase reopens it.

### Success Criteria:

#### Manual Verification:

- Windows, Explorer:
  1. Double-click the PR exe in its download folder. A console flashes at most briefly; then only the cast-tv window shows, with no Windows Terminal tab left.
  2. Cast `Przejazd - SuperCars.mp4` and close the window with X. The TV stops, and no cast-tv process is left in Task Manager.

  — surface: castlib/, packaging/, .github/workflows/release.yml
- Windows, PowerShell: `& .\cast-tv-windows-x64.exe`. The addresses print there and the window opens. Press Ctrl+C in that PowerShell window: `Stopped.` prints, the window closes, and the prompt returns. — surface: castlib/, packaging/, .github/workflows/release.yml
- Windows, PowerShell: `$env:CAST_TV_WINDOW_FAIL='1'; Start-Process .\cast-tv-windows-x64.exe`. The new process's console window reappears next to a browser tab with the UI. Closing that console window stops the TV. Then `Remove-Item Env:CAST_TV_WINDOW_FAIL`. — surface: castlib/, packaging/, .github/workflows/release.yml
- Both, with the video playing:
  - X stops the TV and ends the process.
  - Windows: Start → account → Sign out, then sign in again: the TV has stopped.
  - Fedora: `kill <pid>` of the started file stops the TV and closes the window.

  — surface: castlib/, packaging/, .github/workflows/release.yml
- Both: start the file a second time while the window is open. The existing window comes to the front, and the second process exits. — surface: castlib/, packaging/, .github/workflows/release.yml
- Windows:
  1. In the window click **Add to Start menu**: "Added: find cast-tv in Start.".
  2. Windows key, `cast-tv`: Best match "cast-tv, App" with the TV icon. Enter opens the window with no console.
  3. Right-click the taskbar button → Pin to taskbar; close the window; the pin opens it again.
  4. Move the file to `moved\` and start it there: **Update menu entry (points to another file)**; clicking it turns the button into **Remove from menu**.
  5. **Remove from menu**: "Removed from the Start menu.". Unpin.

  — surface: castlib/, packaging/, .github/workflows/release.yml
- Fedora:
  1. **Add to menu**: "Added: find cast-tv in the applications menu.".
  2. Meta key, `cast`: the cast-tv tile with the TV icon starts the window with no terminal.
  3. Move the file and start it: **Update menu entry**.
  4. **Remove from menu**: "Removed from the menu.".

  — surface: castlib/, packaging/, .github/workflows/release.yml
- Fedora:
  1. Cast `shelf-christmas-decoration.heic` from OneDrive → Pictures: it shows upright on the TV.
  2. The OneDrive and Google Photos lists load (HTTPS through Fedora's CA bundle).
  3. The terminal that started the file shows no `Fontconfig error` or `Fontconfig warning` line.

  — surface: castlib/, packaging/, .github/workflows/release.yml
- Both: in the window's **Open on your phone** panel, scan the QR code with the phone. The UI opens on the phone, with no phone panel and no Quit control. — surface: castlib/, packaging/, .github/workflows/release.yml
- Both, retention:
  1. Download the Nuitka file from three runs or run attempts of the Phase 6 PR. Each has a distinct identity; `gh run rerun <id>` makes a new attempt.
  2. Start each once, so three folders exist under the cache.
  3. Set the oldest folder's marker back 8 days: `touch -d '8 days ago' <dir>/.cast-tv-started` on Fedora, or `(Get-Item <dir>\.cast-tv-started).LastWriteTime = (Get-Date).AddDays(-8)` on Windows.
  4. Start the newest. Within a minute the oldest folder is gone and the other two remain.
  5. Repeat with the oldest build running: its folder stays.

  — surface: castlib/, packaging/, .github/workflows/release.yml
- Both, an interrupted first start:
  1. Delete this build's cache folder (the path from `--version`).
  2. Start the file, and after 1 s end the process you started: `kill -9 <pid>` on Fedora, or `Stop-Process -Id <pid> -Force` on Windows.
  3. Start it again: the window opens normally.

  — surface: castlib/, packaging/, .github/workflows/release.yml
- Windows: start a new identity's file for the first time. Whether the firewall prompt appears is recorded in research.md. The owner answers it. — surface: castlib/, packaging/, .github/workflows/release.yml
- Both: the cache folder's size per build is recorded and matches README. — surface: README.md, castlib/, packaging/

---

## Testing Strategy

### Unit Tests:

- **`tests/test_processes.py`:** a vanished process; access denied for a same-user process
  (incomplete); another user's process (skipped).
- **`tests/test_bundle.py`:**
  - kinds, `started_file` resolution cases, `data_dir`, `cache_dir`, `relaunch_env`;
  - every pruning case in Phase 3.
- **`tests/test_platform.py`, `tests/test_shortcut.py`, `tests/test_window.py`:** the Nuitka case
  of each caller.
  - The relaunch uses the started file and drops the onefile variables.
  - Fontconfig and CA find their files under Nuitka's data dir.
  - The menu target is the started file.
- **`tests/test_api.py`:** `/api/ready` from loopback only, the first time kept, and `instance` only
  for loopback.
- **`tests/test_ui.py`:** the Ready cases in Phase 1.
- **`tests/test_startup_time.py`:** against a fake binary script, the cases in Phase 1.
- **`tests/test_build_nuitka.py`:** the cases in Phase 4.
- **`tests/test_smoke.py`:** the `Cache:` line check.

### Integration Tests:

- The PR's release workflow builds and smoke-tests four files (Phase 4), then two (Phase 6).

### Manual Testing Steps:

The rows above name the window, the control, the expected result and the evidence that goes to
research.md. Real sign-in and TV checks stay pending until a person sees them.

## Performance Considerations

- A warm start reads the whole cache for the CRC check. On a slow disk this is the risk to the
  bar, which is why the owner's machines decide.
- `prune_caches` runs in the background after the window shows. It never delays Ready.
- CI build time grows by about 10–16 minutes per system while both packagers build (Phases 4–5).

## Migration Notes

- Every build gets its own cache folder. Folders beyond the current and previous ones go once they
  have not been started for 7 days and nothing runs from them.
- `%LOCALAPPDATA%\cast-tv\Cache` (the GoPro browser cache) and the spike's `0.5.0` folder are never
  touched. The spike's folder can be deleted by hand.

## References

- Spike: `context/changes/s16-faster-start/research.md`
- Plan review: `context/changes/s16-faster-start/reviews/plan-review.md`
- S-12 rows re-run in Phase 7: `context/archive/2026-10-15-s12-desktop-window/plan.md` (rows 1.13-1.15, 2.8, 3.6-3.12, 4.6-4.10; the fallback procedure at `:560`)
- Roadmap: `context/foundation/roadmap.md` S-16

## Progress

> Convention: `- [ ]` pending, `- [x]` done, `- [-]` not applicable (` — n/a: <reason>` required). Append ` — <commit sha>` when a step lands. A Manual row takes ` — accepted at <full sha>` when a human confirms it. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Measure the start

#### Automated

- [x] 1.1 Ready mark and status fields (test_api) — a558115
- [x] 1.2 UI Ready cases (test_ui) — a558115
- [x] 1.3 Lister and script (test_processes, test_startup_time) — a558115
- [x] 1.4 node --check castlib/ui/app.js — a558115
- [x] 1.5 pyflakes — a558115
- [x] 1.6 Full suite — a558115

#### Manual

- [ ] 1.7 Windows: startup_time.py on a PyInstaller exe of this phase's commit, 5 warm runs, one watched

### Phase 2: Code that runs under either packager

#### Automated

- [x] 2.1 test_bundle — 8278f85
- [x] 2.2 Callers under all three kinds (test_platform, test_shortcut, test_window) — 8278f85
- [x] 2.3 pyflakes — 8278f85
- [x] 2.4 Full suite — 8278f85

### Phase 3: Old cache folders

#### Automated

- [x] 3.1 Pruning cases (test_bundle) — ed90da9
- [x] 3.2 pyflakes — ed90da9
- [x] 3.3 Full suite — ed90da9

### Phase 4: Nuitka builds next to PyInstaller

#### Automated

- [x] 4.1 test_smoke, test_build_nuitka, test_cli — 7a7eb32
- [x] 4.2 pyflakes — 7a7eb32
- [x] 4.3 The PR's release workflow builds and smoke-tests four files — 7a7eb32

### Phase 5: Measure on the owner's machines and decide

#### Manual

- [ ] 5.1 Fedora: 5 cold + 5 warm runs of each file, medians recorded
- [x] 5.2 Windows 11: 5 cold + 5 warm runs of each file, medians recorded — accepted at 67084d10952c3d4e7f3902d6ececac8e367d1488
- [ ] 5.3 Fedora: one run watched, the window visibly ready at the mark
- [x] 5.4 Windows 11: one run watched, the window visibly ready at the mark — accepted at 67084d10952c3d4e7f3902d6ececac8e367d1488
- [ ] 5.5 Linux bar met, or the owner's decision after a miss recorded
- [x] 5.6 Windows bar met, or the owner's decision after a miss recorded — accepted at 67084d10952c3d4e7f3902d6ececac8e367d1488

### Phase 6: Switch the release to Nuitka

#### Automated

- [ ] 6.1 test_smoke, test_build_nuitka
- [ ] 6.2 Full suite
- [ ] 6.3 The PR's release workflow green with the two Nuitka files under the release names

#### Manual

- [ ] 6.4 The published files recorded as equivalent to the measured ones, rows 5.1-5.6 re-confirmed, or measured again

### Phase 7: The accepted behaviour on the Nuitka files

#### Manual

- [ ] 7.1 Windows double-click: only the window, closing it stops the TV
- [ ] 7.2 Windows from PowerShell: output there, window opens, Ctrl+C stops both
- [ ] 7.3 Windows: a forced fallback shows the console again
- [ ] 7.4 Both: X, Windows sign-out and Linux kill stop the TV and end the process
- [ ] 7.5 Both: a second launch brings the window to the front
- [ ] 7.6 Windows: Start menu entry, pinning, Update after a move, Remove
- [ ] 7.7 Fedora: menu entry, Update after a move, Remove
- [ ] 7.8 Fedora: HEIC upright, HTTPS lists load, no Fontconfig diagnostics
- [ ] 7.9 Both: the phone panel's QR opens the UI on the phone
- [ ] 7.10 Both: only the current and previous cache folders remain past the age guard; a running build's folder is kept
- [ ] 7.11 Both: a cold start killed during unpacking, then started again, opens normally
- [ ] 7.12 Windows: the firewall prompt for a new build recorded
- [ ] 7.13 Both: the cache size per build recorded and matching README
