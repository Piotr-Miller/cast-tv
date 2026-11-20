# Next steps (2026-11-20, S-16 Phase 5: the Linux bar is missed; the owner decides, draft PR #111)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **S-16, a faster-starting release file** (`context/changes/s16-faster-start/`, branch
  `s16-faster-start`, pushed; no PR yet). It switches both release files from PyInstaller to a
  Nuitka onefile that unpacks once into a cache folder.
  - **The owner's bars:** the warm median of 5 runs ≤ 50 % of PyInstaller's on Linux and ≤ 75 % on
    Windows 11. The cold median must be no slower. If either is missed, stop and decide again.
  - **Old cache folders:** keep the current and previous build. An older one is deleted after
    7 days unused and with nothing running from it.
- **Phase 1 is done and reviewed.**
  - a558115 and 5155ad8 are the implementation.
  - Codex's review is `reviews/impl-review-phase-1-0707dac.md`: REJECTED, then F1-F7 fixed in
    99287e6, then APPROVED.
  - 3e67ec8: Windows counts an access-denied process as not ours unless WTS names our SID (owner
    decision, verified with a normal and an elevated cast-tv). Without it the measurement refused
    and pruning would never run. Phase 3 keeps "nothing removed on an incomplete listing".
  - a32a0ea: the priming start is never held.
  - **Row 1.7 is accepted at 185f206** (5982c46). PyInstaller warm median 4.28 s on this laptop.
  - Linux owner coverage (`tests/test_processes.py`) and the release build/smoke still need CI;
    no PR run exists yet.
- **v0.5.0** is released, and S-12 is archived. ci-actions-node24's row 1.4 passed on that release;
  it stays unticked in its read-only archive.
- **CI notice:** `ubuntu-latest` moves to Ubuntu 26 (the `test` and `release` jobs); the Linux build
  is pinned to `ubuntu-22.04`.
- **The TV** allows DLNA per client (Settings → General → Device Connection Manager → Device List).
  "No TV found" while `curl http://192.168.50.142:9197/dmr` answers 401 means that list.
- **Test material:** OneDrive → Dokumenty → Videos → `Przejazd - SuperCars.mp4`;
  `shelf-christmas-decoration.heic` in OneDrive → Pictures; `Test_Pictures` on Nextcloud.
- **Home Windows:** after a sign-out, `vEthernet (Default Switch)` may get a new address. The full
  suite passed 592/6 skipped twice on 2026-11-19 after Codex's test-synchronization fixes (F6).

## Next

- [x] 1. S-16 opened, spiked, planned and plan-reviewed; Phase 1 implemented. — 2026-11-18.
- [x] 2. Codex's review of Phase 1; fixes; 1.7 accepted again. — 2026-11-19, 99287e6-5982c46.
- [x] 3. `/rune-implement s16-faster-start phase 2` — 2026-11-19, 8278f85:
   - `castlib/bundle.py`: kind, started_file, data_dir, cache_dir, relaunch_env.
   - The `sys.frozen` callers in `platform.py`, `shortcut.py` and `window.py`.
   - Row 1.7 reopened (its surface `castlib/` changed); it needs a new watched run.
- [x] 4. Phases 3-4: old-cache pruning, then Nuitka builds next to PyInstaller in CI. — 2026-11-19,
   ed90da9 (p3), 9dfd306 + 7a7eb32 (p4), draft PR #111. Release run 44630376210 built and
   smoke-tested all four files green; 7a7eb32 fixed the Windows 8.3 short cache path the first run
   (44628255344) caught.
- [x] 5a. Phase 5 on Windows 11 — 2026-11-20, 67084d1 + 9217ad9: cold 4.00 vs 4.05 s (0.988),
   warm 2.87 vs 3.95 s (0.727, limit 0.75), watched run ready after 2.98 s; rows 5.2, 5.4, 5.6
   accepted at 67084d1. research.md, "Phase 5 on Windows 11".
- [x] 5b. Phase 5 on Fedora — 2026-11-20. First eed2a5b: Linux counts our undumpable processes
   (systemd --user, kwin, ssh-agent) as not cast-tv (owner decision); it reopened 5.2 and 5.6. On
   run 44812632302: cold 2.05 vs 3.24 s (0.633, PASS), warm 2.16 vs 3.05 s (0.706, limit 0.50,
   **FAIL**). research.md, "Phase 5 on Fedora".
- [x] 6. `/rune-impl-review s16-faster-start phase 4` (Codex) — 2026-11-20, APPROVED, no
   findings; b3bd7f4.
- [ ] 7. **You:** decide after the Linux miss: keep PyInstaller (close S-16 as measured, not
   switched), switch anyway with a recorded decision, or lower the Linux bar. Phases 6-7 wait for it.
- [ ] 8. Then, if switching: the watched run on Fedora (5.3), Windows 5.2 and 5.6 again on run
   44812632302, Phase 6. Row 1.7 still needs a new watched run.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout on the S-16 branch:
`git fetch; git switch s16-faster-start; git pull`.
