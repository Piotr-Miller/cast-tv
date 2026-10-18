# Next steps (2026-10-18, S-12 after Phase 1)

The standing note for a pause in the work (a reboot, a switch of machine): it stays in the
repository and is overwritten at the next pause.

Claude ticks each step (`- [x]`) as soon as it is done, with the date and, for a merge or a
recorded row, the PR or commit.

## Where it stands

- S-12 Phase 1 ("The window owns the session") is on `main` (1083431, PR #61; bookkeeping #62).
- The Phase 1 review (`reviews/impl-review-phase-1-1083431.md`) found F1-F3, fixed in PR #66
  (`main` 104dd71). The rows it reopened were confirmed again at 104dd71 (PR #67): 1.8, 1.11,
  1.13, 1.15; 1.16 stays confirmed at ffa982c. The Windows part of 1.14 (Ctrl+C, sign-out) is
  done on the fixed code.
- Left for Phase 1, all on Fedora: 1.9, 1.10, 1.12 and the `kill` part of 1.14.
- Most work stays on the Windows 11 laptop; Fedora is visited for the Linux-only manual rows,
  best once per phase.

## Now

- [x] 1. **Windows 11, a new Claude Code session:** `/rune-impl-review s12-desktop-window phase 1`. If it
   finds problems, Claude fixes them in a separate PR and you merge it. — done 2026-10-18: three
   warnings (F1 termination before the window state, F2 session-end deadline, F3 full suite),
   all fixed; PR #66.
- [x] 1a. **You:** merge PR #66 (Rebase and merge). — done 2026-10-18 (`main` 104dd71).
- [x] 1b. **Windows 11, after 1a**, in PowerShell: — done 2026-10-18 at 104dd71 (PR #67; sign-out 23:35)
   ```powershell
   cd C:\Source\cast-tv
   git switch main
   git pull
   & $env:TEMP\ctv-win\Scripts\Activate.ps1
   cast-tv
   ```
   - [x] **1.8:** a window titled cast-tv opens on the UI and PowerShell prints the addresses.
   - [x] **1.13:** start a video on the TV from the window, then close the window with X: the TV
     stops within 5 s, PowerShell prints `Stopped.` and its prompt returns.
   - [x] **1.15:** run `cast-tv` again and click the PowerShell window so it covers the cast-tv
     window. In a **second** PowerShell window run the same five lines: the cast-tv window comes
     to the front and the second PowerShell prints "Its window is in front." and returns at once.
     Close the cast-tv window with X.
   - [x] **1.11:** `cast-tv --no-window` opens a browser tab at http://127.0.0.1:8895/ui/ with
     "Quit cast-tv" in the header, not a window. Press Ctrl+C in the PowerShell window.
   - [x] **1.14 (Ctrl+C):** `cast-tv`, start a video from the window, then Ctrl+C in the
     PowerShell window: the TV stops and the window closes.
   - [x] **1.14 (sign-out), last:** `cast-tv`, start a video from the window, then Start → account
     → Sign out without closing cast-tv. After signing back in: has the TV stopped? In a new
     PowerShell window, `Get-Process cast-tv -ErrorAction SilentlyContinue` prints nothing.
     Come back with `claude --resume` in `C:\Source\cast-tv`.
- [ ] 2. **Fedora, Phase 1 manual rows.** In a terminal, in the cast-tv checkout:
   ```bash
   git switch main && git pull
   ```
   Then, in this order:
   - [ ] **1.10 (without the extra):**
     ```bash
     pipx install --force "$PWD"
     cast-tv
     ```
     Expected: a browser tab at http://127.0.0.1:8895/ui/ with a "Quit cast-tv" button at the
     right of the header. Start a video on the TV, then click "Quit cast-tv": the TV stops, the tab
     shows "cast-tv has ended; you can close this tab." and the terminal prompt returns.
   - [ ] **1.9 (with the extra):**
     ```bash
     pipx install --force "$PWD[window]"
     cast-tv
     ```
     Expected: a Qt window titled cast-tv showing the UI, not a browser tab.
   - [ ] **1.14 (kill):** in the cast-tv window, start a video on the TV. In a **second** terminal:
     ```bash
     pgrep -af cast-tv
     kill <the pid in the first column>
     ```
     Expected: the TV stops, the cast-tv window closes and the prompt returns in the first terminal.
   - [ ] **1.12 (forced fallback):**
     ```bash
     CAST_TV_WINDOW_FAIL=1 cast-tv
     ```
     Expected: a browser tab instead of a window; the terminal prints
     "No cast-tv window (unavailable: CAST_TV_WINDOW_FAIL); the UI opens in the browser…";
     **Diagnostics** (top right of the tab) shows `window_unavailable`.
   - Tell Claude (in a session on Fedora) what you saw for each row, also when it differed.
     Claude writes the observation into `research.md`, runs `--check-recordable`, ticks the row and
     opens a PR; you merge it. Do not merge anything into `main` while rows are being confirmed:
     they are recorded at the `main` SHA.
- [ ] 3. **Windows 11, 2026-10-19 before about 22:55:** S-13 rows 5.12 and 5.11 (see "S-13" below).

Steps 1 and 2 do not depend on each other; do them in either order.

## Phase 2: the release carries the window

- [ ] 4. **Windows 11:** `/rune-implement s12-desktop-window phase 2`. Claude writes the code; the PR's
   CI builds the exe and the Linux binary; Claude opens the PR.
- [ ] 5. **Windows 11, row 2.6:** the PR run's `cast-tv-windows-x64.exe`, downloaded into
   `Downloads\s12-phase2` and started from PowerShell, opens the window; `--version` shows
   `Window: edgechromium`. Record the file size and the time from Enter to a rendered UI.
- [ ] 6. **Fedora:**
   - [ ] **2.7:** the PR run's `cast-tv-linux-x64`, after `chmod +x`, opens a Qt window with the GPU
     on; `--version` shows `Window: qtwebengine`. Record the size and the start time.
   - [ ] **2.8:** a HEIC photo cast through the window shows upright on the TV.
   - [ ] **2.9:** on the Ubuntu 24.04 VM from the spike, if it still exists, the binary opens its
     window; otherwise record that it was not run, and why.
- [ ] 7. **You:** merge the Phase 2 PR.

Claude gives the exact commands for these rows when the PR's files exist.

## Phase 3: the console's information moves into the window, and the console hides

- [ ] 8. **Windows 11:** `/rune-implement s12-desktop-window phase 3`, then its PR.
- [ ] 9. **Windows 11:**
   - [ ] **3.6:** the "Open on your phone" panel lists the Wi-Fi address first; its QR code opens the
     UI on the phone.
   - [ ] **3.7:** the phone shows no phone panel and no Quit control.
   - [ ] **3.8:** with Wi-Fi off, the panel says there is no network address.
   - [ ] **3.10:** double-clicking the exe in Explorer shows only the window; closing it stops the TV.
   - [ ] **3.11:** from PowerShell the exe prints the addresses and opens the window; Ctrl+C stops the
     TV and closes the window.
   - [ ] **3.12:** a forced fallback with a hidden console shows the console again next to the tab.
- [ ] 10. **Fedora, row 3.9:** the same panel and QR codes work in the Qt window.
- [ ] 11. **You:** merge the Phase 3 PR.

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
      repeat for a pipx install and a checkout launch.
    - [ ] **4.10:** "Remove from menu" removes the entry.
- [ ] 15. **You:** merge the Phase 4 PR.

## Closing S-12

- [ ] 16. **Windows 11:** review Phases 2-4 (`/rune-impl-review`) and fix what it finds.
- [ ] 17. **You:** decide on the release tag (e.g. `v0.5.0`); the release workflow builds and publishes
    the files on GitHub Releases.
- [ ] 18. **Windows 11:** `/rune-archive s12-desktop-window`; S-12 becomes `done` in the roadmap.

## To decide, no hurry

- **Fedora:** whether to delete the VM disk in `~/.cache/cast-tv-s12-spike` (7.1 GB, VM stopped)
  and the 20 podman images `localhost/spike-*`. Not before row 2.9: it may need that VM.
- **Windows:** whether to delete `.venv-spike`, `build` and `dist` in
  `C:\Source\cast-tv\context\changes\s12-desktop-window\spike-kit` (gitignored, 1.2 GB).

## S-13: rows 5.11 and 5.12, when GoPro first rejects the session (Windows)

The session from the Edge window is from 2026-10-12 22:55; its cookie expires **2026-10-19 around
22:55**. Up to 2026-10-18 GoPro has not rejected it once (`first_401_at` empty).

1. In PowerShell:
   ```powershell
   cd $HOME\Downloads\s13-row-5.10
   $env:CAST_TV_BROWSER='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
   .\cast-tv-windows-x64.exe
   ```
2. In the cast-tv tab, click the **GoPro** tab:
   - a list means the session still works. Press Ctrl+C in the PowerShell window and try later;
   - the banner **"cast-tv couldn't access your GoPro media with this session"** means: note the
     date and time and go to step 3.
3. **Before clicking anything**, open **Diagnostics** (top right) and copy the whole text of the
   GoPro card. That is row 5.12.
4. Click **Open gopro.com again** and note whether the Edge window closed by itself or asked you to
   sign in. That is row 5.11.
5. Press Ctrl+C in the PowerShell window and give Claude the date, the Diagnostics text and the
   result of step 4.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout, on `main`.
