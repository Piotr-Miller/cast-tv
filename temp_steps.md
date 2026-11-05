# Next steps (2026-11-05, Phase 4 is PR #97; its manual rows 4.5-4.10)

The standing note for a pause in the work (a reboot, a switch of machine): it stays in the
repository and is overwritten at the next pause.

Claude ticks each step (`- [x]`) as soon as it is done, with the date and, for a merge or a
recorded row, the PR or commit.

## Where it stands

- S-12 Phases 1 and 2 are on `main`. Phase 3 reopened 1.14, 1.16 and 2.6-2.9 (`change.md`,
  2026-10-27); with 1.8-1.13 and 1.15 they are confirmed again once, in step 15a.
- **Phase 3 is on `main`** (PR #89, rebase merge 2026-11-05, main 46d5d76). Every row 3.1-3.12 is done.
- **2026-10-28, on the Intune work laptop** (`C:\Source\Trainings\AI\cast-tv`; its MDM rule
  "Block InBound connection Public Private" blocks every inbound connection, so neither the TV nor
  the phone can reach it). Every part that needs no inbound connection passed, on run
  40580688484's exe (`research.md`, "Manual rows 3.6 and 3.11 on the work laptop"):
  - 3.6: Wi-Fi first, the QR code fills its square and the phone read the right URL, Copy works;
  - 3.10: a double-click shows only the window, X ends everything;
  - 3.11: `Stopped.`, the window closes, **no** `atexit` traceback (row 2.6's finding is fixed);
  - 3.12: the console comes back on the fallback; the error box and the text-only terminal error.
- **Row 3.8 failed and is fixed** in 3dd7f1b. With Wi-Fi off, Windows keeps the Wi-Fi address as
  `Deprecated` and the panel listed it. Addresses that are not `Preferred` are now skipped. On
  run 40750049252's exe, with Wi-Fi off, the work laptop listed only its two Hyper-V addresses
  (2026-10-28); the "no network address" message itself needs a machine without them.
- **Row 3.12's side finding is fixed** in 7861809: "Close the window or press Ctrl+C" is printed
  only once the window shows, so a fallback prints only "No cast-tv window ...; Ctrl+C ends it".
  Checked on the work laptop on run 40760424209's exe (2026-10-28).
- **The exe for the remaining rows** comes from PR #89's release run 40760424209 (built from
  7861809): Windows 26088117 bytes, `window-check: edgechromium OK`; Linux 260517152 bytes. Test
  run 40760424122 is green on both systems.
- Locally on the work laptop, `test_onedrive.py::test_token_file_mode_0600` always fails and
  `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving` sometimes does, with or without
  the change; CI passes both.
- The TV allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"). "No TV found" while the TV is on and
  `curl http://192.168.50.142:9197/dmr` answering 401 means that list, not cast-tv.

## Done: the home Windows machine, PR #89's remaining rows

**2026-11-04, the home machine** (`research.md`, "Manual rows 3.6-3.12 on the home Windows
machine"): 3.6 and 3.7 accepted at 55a1e9b. 3.10 failed on Windows Terminal (this machine's
default terminal) and is fixed in 6fc8930, 16b7a1d and d607d09: a double-click starts a copy
without a console, and the Terminal window shows for about 2-4 s. 3.10-3.12 are accepted at
d607d09 on release run 41921369531's exe (in `Downloads\s12-phase3c`). 3.8: with Wi-Fi off the
panel listed only Hyper-V's 172.18.48.1; with that adapter disabled too, it said "This computer
has no network address" (accepted at d607d09).


- [x] 8. **Home Windows 11**, in PowerShell, in `C:\Source\cast-tv`:
   ```powershell
   git fetch; git switch s12-phase3; git pull
   mkdir $HOME\Downloads\s12-phase3c -Force; cd $HOME\Downloads\s12-phase3c
   gh run download 40760424209 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64.exe
   (Get-Item .\cast-tv-windows-x64.exe).Length
   .\cast-tv-windows-x64.exe --version
   ```
   The length should be 26088117 and the last line `Window: edgechromium`. Tell Claude each
   row's result; Claude records it and ticks the row.
   - [x] **3.6:** start `.\cast-tv-windows-x64.exe`. In the cast-tv window, click **QR code** next
     to the first (192.168.50.x) address in "Open on your phone" and scan it with the phone's
     camera: the cast-tv UI opens on the phone.
   - [x] **3.7:** on the phone, the page shows no "Open on your phone" panel and no "Quit cast-tv"
     button. Close the cast-tv window with X.
   - [x] **3.8:** turn the Wi-Fi tile off in the taskbar's network menu (and unplug Ethernet),
     wait 10 s, start the exe again. The panel says "This computer has no network address.
     Connect it to Wi-Fi or Ethernet." If a virtual adapter (Hyper-V, WSL, VPN) is still listed
     instead, say which; the Wi-Fi address must **not** be listed. Close with X, turn Wi-Fi back on.
   - [x] **3.11:** in PowerShell, start the exe, cast a photo to the TV, then press **Ctrl+C in
     the PowerShell window**: `Stopped.`, the window closes, the TV stops, no traceback.
   - [x] **3.10:** in File Explorer, double-click the exe, cast a photo, close the window with X:
     the TV stops, and Task Manager shows no `cast-tv-windows-x64.exe`.
   - [x] **3.12:** in PowerShell, `$env:CAST_TV_WINDOW_FAIL='1'; Start-Process .\cast-tv-windows-x64.exe`.
     Cast a photo from the browser tab, then close the console window that appeared with its X:
     the TV stops and the tab shows "cast-tv is not answering". Then
     `Remove-Item Env:CAST_TV_WINDOW_FAIL`.
- [x] 9. **You:** merge PR #89 once the rows pass (or say what failed; Claude fixes it first).
  — 2026-11-05, rebase merge, main 46d5d76; SHAs rewritten from main.

## Phase 4: icon and menu entry

- [x] 12. **Either machine:** `/rune-implement s12-desktop-window phase 4`, then its PR.
    — 2026-11-05, commit c4ce4e1, **PR #97** (branch `s12-phase4`). Test run 42072787693 and
    release run 42072787694 green on both systems: Windows 26121290 bytes,
    `window-check: edgechromium OK`; Linux 260585144 bytes, `window-check: qtwebengine OK`.
    Phase 4 changed the surfaces of 3.6-3.12, so they are reopened and go into step 15a.
- [ ] 13. **Windows 11**, in PowerShell, in `C:\Source\cast-tv`:
   ```powershell
   git fetch; git switch s12-phase4; git pull
   mkdir $HOME\Downloads\s12-phase4\moved -Force; cd $HOME\Downloads\s12-phase4
   gh run download 42072787694 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64.exe
   (Get-Item .\cast-tv-windows-x64.exe).Length
   ```
   The length should be 26121290. Tell Claude each row's result; Claude records it and ticks the row.
   - [ ] **4.5:** in File Explorer, open `Downloads\s12-phase4`: `cast-tv-windows-x64.exe` shows the
     amber TV icon (press F5 if Explorer still shows a generic one). Double-click it: the cast-tv
     window's title bar and its taskbar button show the same icon.
   - [ ] **4.8:** in that window, under "Open on your phone", click **Add to Start menu**: next to
     it "Added: find cast-tv in Start." appears and the button turns into **Remove from menu**.
     Close the window with X. Press the Windows key, type `cast-tv`: the entry shows the icon;
     press Enter: the window opens and no console window appears. Right-click its taskbar button →
     **Pin to taskbar**, close the window with X, click the pinned icon: the window opens again.
     Close it with X.
   - [ ] **4.9:** in PowerShell, `Move-Item .\cast-tv-windows-x64.exe .\moved\; .\moved\cast-tv-windows-x64.exe`.
     The button in the window reads **Update menu entry (points to another file)**; click it: it
     turns into **Remove from menu**. Close with X, start cast-tv from Start: the window opens
     (Task Manager → Details → right-click `cast-tv-windows-x64.exe` → Open file location opens
     `moved`). Close it with X.
   - [ ] **4.8, pipx and checkout:** in `C:\Source\cast-tv`:
     `.\.venv\Scripts\pip install -e ".[window]"; Set-Location $HOME; C:\Source\cast-tv\.venv\Scripts\python -m castlib`.
     The window shows **Update menu entry (points to another file)**; click it, close with X, start
     cast-tv from Start: the window opens, with a console minimised on the taskbar, and the entry
     and window show the icon. With pipx, if installed:
     `pipx install --force "cast-tv[window] @ git+https://github.com/Piotr-Miller/cast-tv@s12-phase4"`,
     then `cast-tv`, **Update menu entry**, X, start from Start: the window opens with the icon.
   - [ ] **4.10:** start cast-tv from Start, click **Remove from menu**: "Removed from the Start
     menu." and the button turns into **Add to Start menu**. Close with X; typing `cast-tv` after
     the Windows key finds no app. Unpin the taskbar icon by hand (right-click → Unpin).
- [ ] 14. **Fedora**, in a terminal:
   ```bash
   mkdir -p ~/Downloads/s12-phase4 && cd ~/Downloads/s12-phase4
   gh run download 42072787694 -R Piotr-Miller/cast-tv -n cast-tv-linux-x64
   chmod +x cast-tv-linux-x64 && stat -c %s cast-tv-linux-x64 && ./cast-tv-linux-x64
   ```
   The size should be 260585144.
   - [ ] **4.6:** with the window open, press Super: in the overview and the dash, and in Alt+Tab,
     the cast-tv window shows its icon, not a gear. If it is still a gear before step 4.7, say so,
     and look again after 4.7 (GNOME may take the icon only from the menu entry).
   - [ ] **4.7:** in the window, click **Add to menu**: "Added: find cast-tv in the applications
     menu." Close the window with X, then press Ctrl+C in the terminal if it still runs. Press
     Super, type `cast-tv`: the entry shows the icon; Enter opens the window and no terminal.
     Then the checkout: `cd <checkout> && git switch s12-phase4 && git pull && .venv/bin/pip install -e '.[window]' && cd ~ && <checkout>/.venv/bin/python -m castlib`,
     **Update menu entry**, X, start from the overview: the window opens. With pipx
     (`sudo dnf install pipx`):
     `pipx install --force "cast-tv[window] @ git+https://github.com/Piotr-Miller/cast-tv@s12-phase4"`,
     `~/.local/bin/cast-tv`, **Update menu entry**, X, start from the overview: the window opens.
     Phase 1's `~/.local/bin/cast-tv` symlink is replaced by pipx's launcher; say if you want it kept.
   - [ ] **4.10:** start cast-tv from the overview, click **Remove from menu**: "Removed from the
     menu."; close with X; Super + `cast-tv` finds no app.
- [ ] 15. **You:** merge PR #97.

## Closing S-12

- [ ] 15a. **Windows 11 and Fedora:** confirm again the rows that Phases 2-4 reopened: 1.8-1.16,
    2.6-2.9 and 3.6-3.12 (`cli.py`, `platform.py`, `window.py`, the UI and the spec changed). Once,
    on the release binaries built after the Phase 4 merge. Claude gives the steps.
- [ ] 16. **Windows 11:** review Phases 2-4 (`/rune-impl-review`) and fix what it finds.
- [ ] 17. **You:** decide on the release tag (e.g. `v0.5.0`); the release workflow builds and publishes
    the files on GitHub Releases. This run also checks ci-actions-node24's row 1.4: on the Actions
    page, the tag's release run has a green `release` job, and the release's Assets list
    `cast-tv-windows-x64.exe` and `cast-tv-linux-x64` at the sizes the build printed. Tell Claude
    what you saw, and it records the observation.
- [ ] 18. **Windows 11:** `/rune-archive s12-desktop-window`; S-12 becomes `done` in the roadmap.

## To decide, no hurry

- **Fedora:** whether to delete the local branch `s12-desktop-window`: its 4 commits are on `main`
  under rebased SHAs and the remote branch is gone.
- **Home Windows:** whether to delete `.venv-spike`, `build` and `dist` in
  `C:\Source\cast-tv\context\changes\s12-desktop-window\spike-kit` (gitignored, 1.2 GB).
- **Either machine:** whether a later change makes the UI say that the TV refused this computer
  (the description answering 401) instead of "No TV found"; `research.md`, row 2.8, side finding.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout. Until PR #97 is merged, work on its branch:
`git fetch; git switch s12-phase4; git pull`. After the merge: `git switch main; git pull`.
