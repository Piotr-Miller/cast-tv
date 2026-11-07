# Next steps (2026-11-07, step 15a: Fedora's half is on `main`; Windows 11's rows are next)

The standing note for a pause in the work (a reboot, a switch of machine): it stays in the
repository and is overwritten at the next pause.

Claude ticks each step (`- [x]`) as soon as it is done, with the date and, for a merge or a
recorded row, the PR or commit.

## Where it stands

- **S-12 Phases 1-4 are on `main`** (Phase 3: PR #89; Phase 4: PR #97, SHAs rewritten in #99).
  Every automated row is done; Phase 4's manual rows 4.5-4.10 are accepted.
- **Step 15a** confirms once more the manual rows that Phases 2-4 reopened.
  - **Fedora's half is done** (PR #101, main 5983bf8, 2026-11-07; `research.md`, "Step 15a,
    Fedora"): 1.9-1.12, 1.16, 2.7, 2.8 and 3.9 accepted at a4694af; 2.9 recorded as not run (the
    Ubuntu VM is gone), as its criterion allows. Fedora's parts of 1.13, 1.14 and 1.15 passed;
    those rows close with Windows.
  - **Windows 11's half is next** (step 1 below).
- **The binaries** come from PR #97's release run 42097549651, built from fa0071f, whose code is
  main's c4a4e5a; `castlib/`, `packaging/` and `pyproject.toml` have not changed on `main` since.
  Windows 26123093 bytes, Linux 260586272 bytes; the artifacts expire 2027-02-03. The release
  workflow does not run on `main`.
- **Side findings for step 2** (none fails a row, `research.md`, "Step 15a, Fedora"): the console
  prints "Close the window or press Ctrl+C" on every `shown` event, not once
  (`castlib/window.py:213`); the Linux binary prints about 45 Fontconfig warnings on Fedora 45.
- **The TV** allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"). "No TV found" while the TV is on and
  `curl http://192.168.50.142:9197/dmr` answering 401 means that list, not cast-tv.
- **Test material:** the video is OneDrive → Dokumenty → Videos → `Przejazd - SuperCars.mp4`.
  `Test_Pictures` moved to Nextcloud; `shelf-christmas-decoration.heic` is also in OneDrive →
  Pictures (uploaded again on 2026-11-07; the owner keeps it there).
- Locally on the work laptop, `test_onedrive.py::test_token_file_mode_0600` always fails and
  `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving` sometimes does; CI passes both.

## Closing S-12

- [ ] 1. **Windows 11 (home machine), step 15a's Windows half.** In PowerShell:
   ```powershell
   cd C:\Source\cast-tv; git switch main; git pull
   if (-not (Test-Path .venv)) { python -m venv .venv }
   .venv\Scripts\pip install -e ".[window]"
   mkdir $HOME\Downloads\s12-15a -Force; cd $HOME\Downloads\s12-15a
   gh run download 42097549651 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64.exe
   (Get-Item .\cast-tv-windows-x64.exe).Length
   .\cast-tv-windows-x64.exe --version
   ```
   The length should be 26123093 and the last line `Window: edgechromium`. Then write "co dalej"
   to Claude in `C:\Source\cast-tv`: Claude gives each row's exact steps, drives the browser tab
   and the CLI where it can, records each observation in `research.md`, ticks the rows and opens
   the PR. The rows:
   - the checkout's venv with `[window]`: **1.8** opens a window; **1.13** X with a video playing
     stops the TV; **1.14** Ctrl+C in PowerShell, and Sign out, each with a video playing, stop
     the TV; **1.15** a second launch brings the window to the front;
   - the exe: **2.6** opens the window (size, start time); **3.6** the QR code opens the UI on
     the phone; **3.7** the phone shows no phone panel and no Quit; **3.8** with Wi-Fi off (and
     Hyper-V's adapter disabled) the panel says "This computer has no network address";
     **3.10** a double-click shows only the window and X stops the TV; **3.11** from PowerShell,
     Ctrl+C prints `Stopped.` with no traceback; **3.12** `CAST_TV_WINDOW_FAIL=1` shows the
     console again, and the startup error box.
- [ ] 2. **Either machine, after step 1's PR is merged:** `/rune-impl-review s12-desktop-window`
    for Phases 2-4, and fix what it finds (with the two side findings above). A fix that touches
    a row's surface reopens that row.
- [ ] 3. **You:** decide on the release tag (e.g. `v0.5.0`); the release workflow builds and
    publishes the files on GitHub Releases. This run also checks ci-actions-node24's row 1.4: on
    the Actions page, the tag's release run has a green `release` job, and the release's Assets
    list `cast-tv-windows-x64.exe` and `cast-tv-linux-x64` at the sizes the build printed. Tell
    Claude what you saw, and it records the observation.
- [ ] 4. **Either machine:** `/rune-archive s12-desktop-window`; S-12 becomes `done` in the roadmap.

## To decide, no hurry

- **Fedora:** whether to delete the local branch `s12-desktop-window`: its 4 commits are on `main`
  under rebased SHAs and the remote branch is gone.
- **Home Windows:** whether to delete `.venv-spike`, `build` and `dist` in
  `C:\Source\cast-tv\context\changes\s12-desktop-window\spike-kit` (gitignored, 1.2 GB).
- **Either machine:** whether a later change makes the UI say that the TV refused this computer
  (the description answering 401) instead of "No TV found"; `research.md`, row 2.8, side finding.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout. Work from `main` (`git switch main; git pull`); until
the PR carrying this note is merged, its branch is `s12-15a-windows-steps`.
