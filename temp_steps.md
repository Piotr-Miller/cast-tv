# Next steps (2026-11-05 late, Phase 4 is on `main`; step 15a, the reopened rows, is next)

The standing note for a pause in the work (a reboot, a switch of machine): it stays in the
repository and is overwritten at the next pause.

Claude ticks each step (`- [x]`) as soon as it is done, with the date and, for a merge or a
recorded row, the PR or commit.

## Where it stands

- S-12 Phases 1 and 2 are on `main`. Phase 3 reopened 1.14, 1.16 and 2.6-2.9 (`change.md`,
  2026-10-27); with 1.8-1.13 and 1.15 they are confirmed again once, in step 15a.
- **Phase 3 is on `main`** (PR #89, rebase merge 2026-11-05, main 46d5d76). Every row 3.1-3.12 is done.
- **Phase 4 is PR #97** (branch `s12-phase4`); rows 4.1-4.10 all done (2026-11-05). Fedora found two
  bugs, both fixed on the PR (`research.md`, "Manual rows 4.6 and 4.7 on Fedora"):
  134266b, GNOME showed a new menu entry with a gear until a re-login (the hicolor theme folder's
  time is now bumped); c4a4e5a, a pipx copy started from the menu took the first `cast-tv` on PATH
  for its own launcher (Linux now uses `sys.argv[0]`). Last green runs: test 42097549541, release
  42097549651 (Windows 26123093 bytes, Linux 260586272 bytes).
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
    — 2026-11-05, commit 89735ba, **PR #97** (branch `s12-phase4`). Test run 42072787693 and
    release run 42072787694 green on both systems: Windows 26121290 bytes,
    `window-check: edgechromium OK`; Linux 260585144 bytes, `window-check: qtwebengine OK`.
    Phase 4 changed the surfaces of 3.6-3.12, so they are reopened and go into step 15a.
- [x] 13. **Windows 11:** 4.5, 4.8, 4.9 and 4.10's Windows part — accepted 2026-11-05 (8e7d001, 35ba96c,
    d27006f; `research.md`, "Manual rows 4.5, 4.8 and 4.9 on the home Windows machine").
- [x] 14. **Fedora:** 4.6, 4.7 and 4.10 — accepted 2026-11-05 at 9376efd and f971be5, on 134266b's
    binary and c4a4e5a's checkout and scratchpad pipx (`research.md`, "Manual rows 4.6 and 4.7 on
    Fedora"). In the cast-tv window the menu control sits at the top right, under the TV pill.
- [x] 15. **You:** merge PR #97 ("Rebase and merge"); then Claude rewrites the recorded SHAs from `main`.
  — 2026-11-05, main d8b7ee4; SHAs rewritten on branch `s12-phase4-shas`.

## Closing S-12

- [ ] 15a. **Windows 11 and Fedora:** confirm again the rows that Phases 2-4 reopened: 1.8-1.16,
    2.6-2.9 and 3.6-3.12, once each. **The binaries:** PR #97's release run 42097549651, built
    from fa0071f, whose code is main's c4a4e5a (the two trees differ only in
    `context/foundation/roadmap.md`); the release workflow does not run on `main`. Windows
    26123093 bytes, Linux 260586272 bytes; the artifacts expire 2027-02-03. Claude gives each
    row's exact steps in chat, drives the browser tab and the CLI where it can, and records each
    observation in `research.md` before ticking the row.
    - [ ] **Fedora** (the Linux binary in `~/Downloads/s12-15a`, the checkout, a scratchpad pipx):
      1.9 pipx with `[window]` opens a Qt window; 1.10 pipx without the extra opens a tab whose
      Quit control works; 1.11 `--no-window` opens the tab; 1.12 `CAST_TV_WINDOW_FAIL=1` opens the
      tab, Diagnostics shows `window_unavailable`; 1.13 X with a video playing stops the TV;
      1.14 Ctrl+C and `kill <pid>` stop the TV and close the window; 1.15 a second launch brings
      the window to the front; 1.16 the phone's UI has no Quit control; 2.7 the binary opens a Qt
      window with the GPU on (size, start time); 2.8 a HEIC photo shows upright on the TV;
      2.9 the Ubuntu 24.04 VM was deleted on 2026-10-27, so the row records "not run" and why,
      as its criterion allows; 3.9 the phone panel and QR codes work in the Qt window.
    - [ ] **Windows 11** (the exe in `Downloads\s12-15a`, the checkout's venv): 1.8 the venv with
      `[window]` opens a window; 1.13 X with a video playing; 1.14 Ctrl+C, and Sign out with a
      video playing; 1.15 a second launch; 2.6 the exe opens the window (size, start time);
      3.6 the QR code opens the UI on the phone; 3.7 the phone shows no panel and no Quit;
      3.8 Wi-Fi off (and Hyper-V's adapter disabled): "no network address"; 3.10 a double-click
      shows only the window; 3.11 PowerShell, Ctrl+C, no traceback; 3.12 the fallback console and
      the startup error box.
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

Write "co dalej" in the cast-tv checkout. Work from `main` (`git switch main; git pull`); until the
SHA-rewrite PR is merged, its branch is `s12-phase4-shas`.
