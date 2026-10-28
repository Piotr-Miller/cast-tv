# Next steps (2026-10-28, PR #89: the row 3.8 fix is in; the TV and phone parts need the home Windows machine)

The standing note for a pause in the work (a reboot, a switch of machine): it stays in the
repository and is overwritten at the next pause.

Claude ticks each step (`- [x]`) as soon as it is done, with the date and, for a merge or a
recorded row, the PR or commit.

## Where it stands

- S-12 Phases 1 and 2 are on `main`. Phase 3 reopened 1.14, 1.16 and 2.6-2.9 (`change.md`,
  2026-10-27); with 1.8-1.13 and 1.15 they are confirmed again once, in step 15a.
- **Phase 3 is PR #89** (branch `s12-phase3`). Rows 3.1-3.5 are done, 3.9 (Fedora) is accepted.
- **2026-10-28, on the Intune work laptop** (`C:\Source\Trainings\AI\cast-tv`; its MDM rule
  "Block InBound connection Public Private" blocks every inbound connection, so neither the TV nor
  the phone can reach it). Every part that needs no inbound connection passed, on run
  40580688484's exe (`research.md`, "Manual rows 3.6 and 3.11 on the work laptop"):
  - 3.6: Wi-Fi first, the QR code fills its square and the phone read the right URL, Copy works;
  - 3.10: a double-click shows only the window, X ends everything;
  - 3.11: `Stopped.`, the window closes, **no** `atexit` traceback (row 2.6's finding is fixed);
  - 3.12: the console comes back on the fallback; the error box and the text-only terminal error.
- **Row 3.8 failed and is fixed** in 6878387. With Wi-Fi off, Windows keeps the Wi-Fi address as
  `Deprecated` and the panel listed it. Addresses that are not `Preferred` are now skipped. On
  run 40750049252's exe, with Wi-Fi off, the work laptop listed only its two Hyper-V addresses
  (2026-10-28); the "no network address" message itself needs a machine without them. A side
  finding, not fixed: on the fallback the console still prints "Close the window or press Ctrl+C"
  above "No cast-tv window".
- **The exe for the remaining rows** comes from PR #89's release run 40750049252 (built from
  731ccab): Windows 26089838 bytes, `window-check: edgechromium OK`; Linux 260518120 bytes. Test
  run 40750043256 is green on both systems.
- Locally on the work laptop, `test_onedrive.py::test_token_file_mode_0600` always fails and
  `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving` sometimes does, with or without
  the change; CI passes both.
- The TV allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"). "No TV found" while the TV is on and
  `curl http://192.168.50.142:9197/dmr` answering 401 means that list, not cast-tv.

## Now: the home Windows machine, PR #89's remaining rows

- [ ] 8. **Home Windows 11**, in PowerShell, in `C:\Source\cast-tv`:
   ```powershell
   git fetch; git switch s12-phase3; git pull
   mkdir $HOME\Downloads\s12-phase3b -Force; cd $HOME\Downloads\s12-phase3b
   gh run download 40750049252 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64.exe
   (Get-Item .\cast-tv-windows-x64.exe).Length
   .\cast-tv-windows-x64.exe --version
   ```
   The length should be 26089838 and the last line `Window: edgechromium`. Tell Claude each
   row's result; Claude records it and ticks the row.
   - [ ] **3.6:** start `.\cast-tv-windows-x64.exe`. In the cast-tv window, click **QR code** next
     to the first (192.168.50.x) address in "Open on your phone" and scan it with the phone's
     camera: the cast-tv UI opens on the phone.
   - [ ] **3.7:** on the phone, the page shows no "Open on your phone" panel and no "Quit cast-tv"
     button. Close the cast-tv window with X.
   - [ ] **3.8:** turn the Wi-Fi tile off in the taskbar's network menu (and unplug Ethernet),
     wait 10 s, start the exe again. The panel says "This computer has no network address.
     Connect it to Wi-Fi or Ethernet." If a virtual adapter (Hyper-V, WSL, VPN) is still listed
     instead, say which; the Wi-Fi address must **not** be listed. Close with X, turn Wi-Fi back on.
   - [ ] **3.11:** in PowerShell, start the exe, cast a photo to the TV, then press **Ctrl+C in
     the PowerShell window**: `Stopped.`, the window closes, the TV stops, no traceback.
   - [ ] **3.10:** in File Explorer, double-click the exe, cast a photo, close the window with X:
     the TV stops, and Task Manager shows no `cast-tv-windows-x64.exe`.
   - [ ] **3.12:** in PowerShell, `$env:CAST_TV_WINDOW_FAIL='1'; Start-Process .\cast-tv-windows-x64.exe`.
     Cast a photo from the browser tab, then close the console window that appeared with its X:
     the TV stops and the tab shows "cast-tv is not answering". Then
     `Remove-Item Env:CAST_TV_WINDOW_FAIL`.
- [ ] 9. **You:** merge PR #89 once the rows pass (or say what failed; Claude fixes it first).

## Phase 4: icon and menu entry

- [ ] 12. **Either machine:** `/rune-implement s12-desktop-window phase 4`, then its PR. The icon is
    decided (owner, 2026-10-27): the draft in `context/changes/s12-desktop-window/icon/make_icon.py`.
    On Fedora the Alt+Tab gear goes away only with this phase: the window's `app_id` `cast-tv`
    and the `.desktop` entry it adds.
- [ ] 13. **Windows 11:**
    - [ ] **4.5:** the icon on the exe, the window and the taskbar button.
    - [ ] **4.8:** "Add to Start menu" puts a shortcut in Start that starts with no console; pinning to
      the taskbar works.
    - [ ] **4.9:** after moving the exe to another folder, "Update menu entry" repoints the shortcut.
    - [ ] **4.10:** "Remove from menu" removes the entry.
- [ ] 14. **Fedora:**
    - [ ] **4.6:** the window's dash and taskbar entry show the cast-tv icon.
    - [ ] **4.7:** "Add to menu" puts an entry in the GNOME overview that starts with no terminal;
      repeat for a pipx install and a checkout launch. Fedora has no pipx (2026-10-19): install it
      first (`sudo dnf install pipx`), or ask Claude for a scratchpad pipx as in Phase 1, which
      leaves the `~/.local/bin/cast-tv` symlink alone.
    - [ ] **4.10:** "Remove from menu" removes the entry.
- [ ] 15. **You:** merge the Phase 4 PR.

## Closing S-12

- [ ] 15a. **Windows 11 and Fedora:** confirm again the rows that Phases 2 and 3 reopened: 1.8-1.16
    and 2.6-2.9 (`cli.py`, `platform.py`, the UI and the spec changed). Once, on the release binaries
    built after the Phase 4 merge, since Phase 4 changes `cli.py` again. Claude gives the steps.
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
- **Either machine:** whether to drop "Close the window or press Ctrl+C" from the console when the
  window falls back (`castlib/cli.py`, `WINDOW_ENDS`); `research.md`, row 3.12, side finding.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout. Until PR #89 is merged, work on its branch:
`git fetch; git switch s12-phase3; git pull`. After the merge: `git switch main; git pull`.
