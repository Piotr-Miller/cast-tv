# Next steps (2026-11-18, S-16 Phase 1 done; Codex reviews it next)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **S-16, a faster-starting release file** (`context/changes/s16-faster-start/`, branch
  `s16-faster-start`, pushed; no PR yet). It switches both release files from PyInstaller to a
  Nuitka onefile that unpacks once into a cache folder.
  - **The spike** is in `research.md`. Warm starts: 1.6 s against 4.2 s on a Linux CI runner, and
    2.4-2.7 s against 3.6 s on Windows. The Linux file is 41 % smaller.
  - **The plan** has 7 phases. It was reviewed by Codex (RETHINK, F1-F9, `reviews/plan-review.md`)
    and revised; all nine findings are FIXED.
  - **The owner's bars:** the warm median of 5 runs ≤ 50 % of PyInstaller's on Linux and ≤ 75 % on
    Windows 11. The cold median must be no slower on both. If either is missed, stop and decide
    again.
  - **Old cache folders:** keep the current and the previous build. An older folder is deleted
    only after 7 days unused and with nothing running from it.
- **Phase 1 is done.** It added the Ready mark (`/api/ready`, `shown_at`), `castlib/processes.py`,
  the start of `castlib/bundle.py`, and `packaging/startup_time.py`.
  - Commits: a558115, then 5155ad8 (`--hold`). Row 1.7 was accepted at fc780be (commit 7d33c1b).
  - **Windows baseline**, PyInstaller exe of a558115, warm: median 4.24 s to a usable window.
  - Known: `--hold` also holds the unmeasured priming start. It is fixed with Phase 4, so that row
    1.7 stays current until then.
- **v0.5.0** is released (tag on bd84500), and S-12 is archived. ci-actions-node24's row 1.4 passed
  on that release; it stays unticked in its read-only archive, and this line records it.
- **CI notice:** the `ubuntu-latest` label moves to Ubuntu 26 from 2026-10-19 (the `test` and
  `release` jobs). The Linux build is pinned to `ubuntu-22.04`.
- **The TV** allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"). "No TV found" while the TV is on and
  `curl http://192.168.50.142:9197/dmr` answering 401 means that list, not cast-tv.
- **Test material:** the video is OneDrive → Dokumenty → Videos → `Przejazd - SuperCars.mp4`;
  `shelf-christmas-decoration.heic` is in OneDrive → Pictures; `Test_Pictures` is on Nextcloud.
- **Home Windows:** after a Windows sign-out, `vEthernet (Default Switch)` may get a new address.
  - Locally, `test_onedrive.py::test_token_file_mode_0600` fails intermittently: 7/10 passes on
    a558115 and 6/10 on a85f59d, measured 2026-11-18.
  - `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving` also fails intermittently.
  - CI passes both.

## Next

- [x] 1. S-16 opened, spiked, planned and plan-reviewed; Phase 1 implemented and accepted.
   — 2026-11-18, a558115, 5155ad8, 7d33c1b; pushed.
- [ ] 2. **Codex:** `$rune-impl-review s16-faster-start phase 1`. Base a85f59d; the commits above.
   The prompt with the points to check is in this session's chat.
- [ ] 3. **Claude:** triage the review findings with the owner, then
   `/rune-implement s16-faster-start phase 2`: `castlib/bundle.py` (kind, started_file, data_dir,
   relaunch_env), and the `sys.frozen` callers in `platform.py`, `shortcut.py` and `window.py`.
- [ ] 4. Phases 3-4: old-cache pruning, then Nuitka builds next to PyInstaller in CI. Phase 4 opens
   the PR.
- [ ] 5. Phase 5 on both machines: `startup_time.py` cold and warm on each PR file, then the bars
   decide.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout on the S-16 branch:
`git fetch; git switch s16-faster-start; git pull`.
