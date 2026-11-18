# A faster-starting release file (Nuitka) — Plan Brief

> Full plan: `context/changes/s16-faster-start/plan.md`
> Research: `context/changes/s16-faster-start/research.md`

## What & Why

The release files are PyInstaller onefiles, which unpack themselves on every start: 260 MB on
Linux, 26 MB on Windows. Nuitka's onefile can unpack once into a cache folder and reuse it. The
spike measured warm starts of 1.6 s against 4.2 s on a Linux CI runner and 2.4–2.7 s against
3.6 s on Windows, and a 41 % smaller Linux file. This change switches both releases to Nuitka,
but only if the owner's own machines show a clear gain.

## Starting Point

v0.5.0 is built by `packaging/cast-tv.spec` in `release.yml`. Five places in `castlib` recognise
the release through PyInstaller's `sys.frozen` and `sys._MEIPASS`, and under Nuitka they would
silently switch off:
- the Windows Terminal relaunch,
- the private Fontconfig rules,
- Fedora's CA bundle,
- the menu entry's target and icon,
- the window icon.

## Desired End State

Both release files are Nuitka onefiles under the same asset names. The second and later starts
skip the unpacking. The cache keeps the current and previous builds, plus any started in the last
7 days or still running. Every behaviour accepted
in S-12 holds, the Windows console included. Medians from the owner's Fedora desktop and Windows
laptop show each system met its bar.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Packager | Nuitka, onefile, cached unpack folder | It reuses its unpack and passed the window check on both systems. | Research |
| Scope | Linux and Windows 11 | The owner wants one decision for both, each with its own bar. | Plan (owner) |
| Bar, Linux | Warm median ≤ 50 % of PyInstaller's; cold median ≤ PyInstaller's | A felt gain without a slower first start after an update. | Plan (owner) |
| Bar, Windows | Warm median ≤ 75 %; cold ≤ PyInstaller's | Windows has less to unpack, so less to win. | Plan (owner) |
| A miss | Stop, report, the owner decides again | No automatic drop or switch of either system. | Plan (owner) |
| Start time | Launch to Ready UI: the window shown and the first *successful* status rendered with usable controls; `init()` runs once | What a person feels; TV discovery may continue; review F1 found the double `init()` | Plan (owner; review F1) |
| Cold start | First launch of a new version, no reboot, all cast-tv closed, Nuitka's version folder absent | The real "after an update" case. | Plan (owner) |
| Runs | Median of 5 per build, mode and system | Smooths noise near the bar. | Plan (owner) |
| Old caches | Keep current + previous; delete an older folder only if its last start was ≥ 7 days ago and no running process comes from it; rename first (Windows: fails if locked), then delete; incomplete process list → delete nothing | Bounded disk use; the vendor bootstrap cannot take part in a lock, so an age guard covers the start-up race | Plan (owner, after review F2) |
| Cache path | `{CACHE_DIR}/cast-tv/<version>-gh<run>.<attempt>` (or `-local<timestamp>`), one grammar for builder, pruner and script; Nuitka pinned at 4.3.5 | Each build payload gets its own folder; the commit alone did not distinguish re-runs | Plan (review F6) |
| Windows console | Nuitka `--windows-console-mode=hide`, with the Terminal relaunch kept | The counterpart of `hide-early`; S-12's accepted behaviour stays. | Plan |
| Order | Measure, then switch (with a recorded equivalence of published vs measured files), then re-accept behaviour with directory-wide surfaces | Rows accepted before the switch would go stale; review F4 | Plan (review F4) |

## Scope

**In scope:**
- A Ready mark in the app and a measuring script.
- One packager-neutral module in place of `sys.frozen`.
- Old-cache pruning.
- A Nuitka build in CI next to PyInstaller, then the switch.
- README.
- Re-running S-12's behaviour rows on the new files.

**Out of scope:**
- Onedir, installers, macOS and signing.
- Firewall-rule automation.
- Shrinking Qt WebEngine.
- A run-time fallback to PyInstaller.
- Handling a failing Nuitka bootstrap (full disk); recorded as a risk.

## Architecture / Approach

`castlib/bundle.py` answers which packager built the file, which file the user started
(`__compiled__.original_argv0` under Nuitka), where the data is, and how to relaunch. Every caller
uses it. `packaging/build_nuitka.py` mirrors the spec's contents. `release.yml` builds both
packagers until the decision. `packaging/startup_time.py` times launches to the Ready mark
(`/api/ready` from the page plus `on_shown`) and compares medians against the bar.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Measure the start | Ready mark, process lister, `startup_time.py` | The mark fires before the controls are usable (F1 cases) |
| 2. Either packager | `castlib/bundle.py`, callers ported | A missed `sys.frozen` path that only shows on a real machine |
| 3. Old caches | Age-guarded, rename-first pruning | The residual start-up race |
| 4. Builds side by side | Four smoke-tested files per PR | Nuitka build time, Qt plugin gaps |
| 5. Measure and decide | Medians on Fedora and Windows; the bar | A slow disk makes the warm CRC pass miss the bar |
| 6. Switch | Nuitka files under the release names; README; equivalence to the measured files | A build difference forcing a re-measure |
| 7. Behaviour again | S-12's rows on the Nuitka files | The Windows console relaunch under Nuitka |

**Prerequisites:**
- The owner's Fedora desktop and Windows 11 laptop for Phases 5 and 7.
- Visual Studio Build Tools for local Windows builds (present).

**Estimated effort:** ~4–6 sessions. Phases 1–4 are code and CI; Phases 5 and 7 are on the
machines.

## Open Risks & Assumptions

- Windows may miss its 75 % bar: the spike's `--window-check` ratio was about 70–75 %.
- The cache folder per version likely makes Windows ask about the firewall again after each
  update (recorded in row 7.12).
- Disk use: up to about 1.1 GB on Linux (two versions).
- A Nuitka bootstrap error (full disk) may be invisible on a Windows double-click.
- Residual race (accepted): an older build unused for ≥ 7 days, started at the very moment another build prunes it; its next start unpacks again.
- The plan was reviewed (RETHINK, 2026-11-18) and revised: F1-F9 fixed (`reviews/plan-review.md`).

## Success Criteria (Summary)

- On the owner's machines, later starts reach a usable window in at most half (Linux) or three
  quarters (Windows) of today's time, and the first start after an update is no slower.
- Everything that worked in v0.5.0 still works, the console behaviour on Windows included.
- The cache keeps two builds, plus any started in the last 7 days or still running.
