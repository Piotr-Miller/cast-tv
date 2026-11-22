# Next steps (2026-11-22, S-16: PR #111 merged; SHAs rewritten, archive and release tag next)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **S-16, a faster-starting release file** (`context/changes/s16-faster-start/`, branch
  `s16-faster-start`, **PR #111, merged 2026-11-22**). The release switches from PyInstaller to a Nuitka onefile
  that unpacks once per version into `~/.cache/cast-tv/<version>-gh<build>` (Windows:
  `%LOCALAPPDATA%\cast-tv\...`). Phases 1-6 are implemented; Phase 7 is acceptance only.
  - **The bars** (owner decisions): Nuitka's warm median ≤ 75 % of PyInstaller's on both systems
    (Linux was 50 %, lowered after 0.706 missed it), the cold median no slower.
  - **Measured:** Windows 11 (run 44630376210): warm 0.727, cold 0.988. Fedora (run 44812632302):
    warm 0.706, cold 0.633; watched run ready after 1.85 s.
  - **9b1ced7:** Linux counts our undumpable processes (systemd --user, kwin, ssh-agent) as not
    cast-tv; without it the measurement refused and pruning never ran on Fedora. It reopened
    Windows's 5.2 and 5.6.
  - **Phase 6 (93ca5b7):** `release.yml` builds, smoke-tests and publishes only Nuitka under the
    old names; `packaging/cast-tv.spec` deleted; README describes the cache (about 550 MB on Linux,
    80 MB on Windows). Release run 44821655658 green.
  - **Accepted:** 1.7, 5.1-5.6, 6.4, 7.7, 7.8. **Open:** none (2026-11-22); before that, on Windows: the
    Windows parts of 7.1-7.6 and 7.9-7.13 (their Fedora parts passed, research.md "Phase 7 on
    Fedora").
  - **Finding outside S-16:** while a video plays, the now-playing bar still shows the
    **HEIC → JPEG** badge of the photo cast before it; for a change of its own.
- **Fedora and Windows 11 are a dual boot on one laptop:** every switch is a reboot, so all
  Windows rows go into one visit (step 11).
- **v0.5.0** is released (2026-11-18), and S-12 is archived.
- **CI notice:** `ubuntu-latest` moves to Ubuntu 26 (the `test` job); the Linux build is pinned to
  `ubuntu-22.04`.
- **The TV** allows DLNA per client (Settings → General → Device Connection Manager → Device List).
  "No TV found" while `curl http://192.168.50.142:9197/dmr` answers 401 means that list.
- **Test material:** OneDrive → Dokumenty → Videos → `Przejazd - SuperCars.mp4`;
  `shelf-christmas-decoration.heic` in OneDrive → Pictures; `Test_Pictures` on Nextcloud.
- **Windows:** after a sign-out, `vEthernet (Default Switch)` may get a new address. The full
  suite passed 592/6 skipped twice on 2026-11-19.
- **Fedora's GoPro session** expired (captured 2026-09-24); not needed for S-16.

## Next

- [x] 1. S-16 opened, spiked, planned and plan-reviewed; Phase 1 implemented. — 2026-11-18.
- [x] 2. Codex's review of Phase 1; fixes; 1.7 accepted again. — 2026-11-19, a6452ce-5fa155c.
- [x] 3. `/rune-implement s16-faster-start phase 2` — 2026-11-19, dbb1b52:
   - `castlib/bundle.py`: kind, started_file, data_dir, cache_dir, relaunch_env.
   - The `sys.frozen` callers in `platform.py`, `shortcut.py` and `window.py`.
   - Row 1.7 reopened (its surface `castlib/` changed); it needs a new watched run.
- [x] 4. Phases 3-4: old-cache pruning, then Nuitka builds next to PyInstaller in CI. — 2026-11-19,
   be8eef9 (p3), 8297237 + 658da78 (p4), draft PR #111. Release run 44630376210 built and
   smoke-tested all four files green; 658da78 fixed the Windows 8.3 short cache path the first run
   (44628255344) caught.
- [x] 5a. Phase 5 on Windows 11 — 2026-11-20, 06a16b9 + 549f923: cold 4.00 vs 4.05 s (0.988),
   warm 2.87 vs 3.95 s (0.727, limit 0.75), watched run ready after 2.98 s; rows 5.2, 5.4, 5.6
   accepted at 06a16b9. research.md, "Phase 5 on Windows 11".
- [x] 5b. Phase 5 on Fedora — 2026-11-20. First 9b1ced7: Linux counts our undumpable processes
   (systemd --user, kwin, ssh-agent) as not cast-tv (owner decision); it reopened 5.2 and 5.6. On
   run 44812632302: cold 2.05 vs 3.24 s (0.633, PASS), warm 2.16 vs 3.05 s (0.706, limit 0.50,
   **FAIL**). research.md, "Phase 5 on Fedora".
- [x] 6. `/rune-impl-review s16-faster-start phase 4` (Codex) — 2026-11-20, APPROVED, no
   findings; b4c204f.
- [x] 7. The owner's decision after the miss — 2026-11-20: the Linux bar is 0.75 like Windows;
   0.706 passes it (plan.md, The bar; research.md).
- [x] 8. Fedora: the watched run, ready after 1.85 s; 5.1, 5.3 and 5.5 accepted at 3d990ec.
   — 2026-11-20.
- [x] 9. Phase 6 (93ca5b7): the release builds, smoke-tests and publishes only Nuitka under the
   old names; run 44821655658 green. Its Linux file equals the measured one apart from names; 5.1
   and 5.5 re-confirmed (6d52911). Rows' surface lines fixed, 5.1 reopened once more (2c239ca).
- [x] 10. Phase 7 on Fedora — 2026-11-20, de15238: 7.4, 7.5, 7.7-7.11 and 7.13 observed
   (research.md, "Phase 7 on Fedora"). 5.1, 7.7 and 7.8 accepted at 824a487; the "Both"
   rows wait for their Windows parts.
- [x] 11. **One Windows 11 visit (reboot into Windows; Claude drives, you watch the TV and answer
   the firewall):** rows 1.7, 5.2, 5.6, 6.4 (Windows part), 7.1-7.6 and 7.9-7.13 (Windows parts).
   In PowerShell, with every cast-tv closed:
   ```powershell
   cd C:\Source\cast-tv; git fetch; git switch s16-faster-start; git pull
   $d = "$HOME\Downloads"
   gh run download 44812632302 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64-nuitka.exe -D "$d\s16-run-44812632302\nuitka"
   gh run download 44812632302 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64.exe -D "$d\s16-run-44812632302\pyi"
   gh run download 44821655658 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64.exe -D "$d\s16-run-44821655658"
   ```
   Then start Claude in `C:\Source\cast-tv` and write "co dalej". What Claude does there:
   - 5.2/5.6: the four series on run 44812632302's pair, `--compare … --warm-ratio 0.75`; you
     leave the laptop alone for about 5 minutes.
   - 6.4: run 44821655658's exe against that Nuitka exe by build-info (as on Linux).
   - 1.7: its plan text asks for a PyInstaller exe built with the spec, which Phase 6 deleted; the
     proposal is run 44812632302's PyInstaller exe (9b1ced7, every castlib change of Phases 1-5).
     Your decision there.
   - Done 2026-11-21: 1.7, 5.2, 5.6 and 6.4 accepted at 9ad76e4 (cold 0.828, warm 0.734; a first
     attempt during Windows servicing (`TiWorker`) was discarded).
   - Done 2026-11-22: Phase 7 on Windows observed (research.md, "Phase 7 on Windows 11"); 7.4's
     sign-out not repeated (owner decision, observed in S-12). 7.1-7.6 and 7.9-7.13 accepted at
     878cc8f; every Progress row of plan.md is ticked.
   - Phase 7 on run 44821655658's exe; 7.10 uses the three Windows builds of runs 44630376210
     (already in `%USERPROFILE%\Downloads\s16-run-44630376210`), 44812632302 and 44821655658.
- [x] 12. The Phase 6 review (Codex) APPROVED, F1 fixed in 21bb5a8; 1.7 and 7.13 accepted again at
   f3fb96c; PR #111 ready, CI green, merged by the owner (rebase) — 2026-11-22, main fc89537. Its
   SHAs rewritten from main (branch `s16-after-merge`).
- [ ] 13. Merge the SHA-rewrite PR (`s16-after-merge`), then `/rune-archive s16-faster-start`.
- [ ] 14. The release tag (v0.6.0?): the owner decides the version; the tag's release run publishes
   the two Nuitka files under the old names.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout on the S-16 branch (on Windows: `C:\Source\cast-tv`):
`git fetch; git switch s16-faster-start; git pull`.
