# Next steps (2026-10-27 late: Phase 3 in PR #89; the Windows rows 3.6-3.8 and 3.10-3.12 next)

The standing note for a pause in the work (a reboot, a switch of machine): it stays in the
repository and is overwritten at the next pause.

Claude ticks each step (`- [x]`) as soon as it is done, with the date and, for a merge or a
recorded row, the PR or commit.

## Where it stands

- S-12 Phases 1 and 2 are on `main`. All Phase 2 rows were accepted (PR #88), then reopened by
  Phase 3 with 1.14 and 1.16, because Phase 3 changes their surfaces (`change.md`, 2026-10-27).
  They are confirmed again once, in step 15a, with 1.8-1.13 and 1.15.
- **Phase 3 is PR #89** (branch `s12-phase3`, implemented on Fedora): the "Open on your phone"
  panel with Copy and a QR code per address, the firewall banner, the console hidden on
  double-click (`hide-early`), the console shown again on fallback, a message box for a startup
  failure, and the two findings of row 2.6 (Ctrl+C ignored after the window closed; `smoke.py`
  ends the server with `POST /api/quit`). Rows 3.1-3.5 are done; CI is green on both systems.
- Row 3.9 (Fedora) found Copy and the QR code broken in the Qt window; fixed in 1134162 and
  accepted at efac3c5 (`research.md`, "Manual row 3.9").
- The binaries for the Windows rows come from PR #89's release run 40580688484: Windows 26086907 bytes.
- Not provable on Fedora: whether a double-click is recognised (the console's owner is the
  onefile bootloader) and whether the pythonnet traceback after Ctrl+C is gone. Rows 3.10-3.12
  show it; if one fails, Claude fixes it on the same PR before the merge.
- The TV allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"); Fedora is "Device 3". "No TV found" while the TV is on and
  `curl http://192.168.50.142:9197/dmr` answering 401 means that list, not cast-tv.

## Now: Windows 11, Phase 3 rows

- [ ] 8. **Windows 11**, in PowerShell, in `C:\Source\cast-tv`:
   ```powershell
   git fetch; git switch s12-phase3; git pull
   mkdir $HOME\Downloads\s12-phase3 -Force; cd $HOME\Downloads\s12-phase3
   gh run download 40580688484 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64.exe
   (Get-Item .\cast-tv-windows-x64.exe).Length
   .\cast-tv-windows-x64.exe --version
   ```
   The length should be 26086907 and the last line `Window: edgechromium`. Tell Claude each row's
   result, also when it differs; Claude records it and ticks the row.
   - [ ] **3.6:** start `.\cast-tv-windows-x64.exe`. In the cast-tv window, under the header, the
     "Open on your phone" panel lists the Wi-Fi address (192.168.50.x) first. Click **QR code**
     next to it; scan the code with the phone's camera: the cast-tv UI opens on the phone. Click
     **Copy**: "Copied." shows at the bottom of the window.
   - [ ] **3.7:** on the phone, the page shows no "Open on your phone" panel and no "Quit cast-tv"
     button.
   - [ ] **3.8:** the addresses are read at start, so: close the window with X, turn Wi-Fi off
     (and unplug Ethernet), start the exe again. The panel says "This computer has no network
     address. Connect it to Wi-Fi or Ethernet." (a virtual adapter such as 172.21.80.1 may still
     be listed instead; say so). Close with X and turn Wi-Fi back on.
   - [ ] **3.11:** in the PowerShell window, start `.\cast-tv-windows-x64.exe`. The addresses
     print in PowerShell and the cast-tv window opens. Cast a photo to the TV, then press
     **Ctrl+C in the PowerShell window**: it prints `Stopped.`, the window closes, the TV stops,
     and **no** `Exception ignored in atexit callback` traceback follows (row 2.6's finding).
   - [ ] **3.10:** in File Explorer, open `Downloads\s12-phase3` and double-click
     `cast-tv-windows-x64.exe`. At most a console flashes; then only the cast-tv window shows (no
     console window, no new Windows Terminal tab). Cast a photo, then close the window with X: the
     TV stops. Check Task Manager: no `cast-tv-windows-x64.exe` left.
   - [ ] **3.12:** in PowerShell:
     ```powershell
     $env:CAST_TV_WINDOW_FAIL='1'; Start-Process .\cast-tv-windows-x64.exe
     ```
     A browser tab opens with the UI, and the console window appears next to it (it says why
     there is no window). Cast a photo from the tab, then close that console window with its X:
     the TV stops and the tab shows "cast-tv is not answering". Then
     `Remove-Item Env:CAST_TV_WINDOW_FAIL`.
     The error box: in a **second** PowerShell window run `python -m http.server 8895 --bind
     127.0.0.1`. Double-click the exe in Explorer: a "cast-tv" message box names port 8895 and
     the error, and stays until you press OK; then nothing else is left running. In the first
     PowerShell window run `.\cast-tv-windows-x64.exe`: it prints `Cannot bind port 8895: ...`,
     shows no box, and `$LASTEXITCODE` is 1. Stop the HTTP server with Ctrl+C in the second
     window.
- [ ] 9. **You:** merge PR #89 once the rows pass (or say what failed; Claude fixes it first).

## Phase 4: icon and menu entry

- [ ] 12. **Windows 11:** `/rune-implement s12-desktop-window phase 4`, then its PR.
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

- **Fedora:** whether to delete the VM disk in `~/.cache/cast-tv-s12-spike` (7.1 GB, VM stopped)
  and the 20 podman images `localhost/spike-*`. Row 2.9 is done, so nothing in S-12 needs them.
- **Fedora:** whether to delete the local branch `s12-desktop-window`: its 4 commits are on `main`
  under rebased SHAs and the remote branch is gone.
- **Windows:** whether to delete `.venv-spike`, `build` and `dist` in
  `C:\Source\cast-tv\context\changes\s12-desktop-window\spike-kit` (gitignored, 1.2 GB).

- **Either machine:** whether a later change makes the UI say that the TV refused this computer
  (the description answering 401) instead of "No TV found"; `research.md`, row 2.8, side finding.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout, on `main`.
