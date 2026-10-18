# Next steps (2026-10-18, S-12 Phase 1 manual rows)

The standing note for a pause in the work (a reboot, a switch of machine): it stays in the
repository and is overwritten at the next pause.

## S-12: where it stands

- Phase 1 ("The window owns the session") is on `main` (1083431, PR #61; bookkeeping PR #62).
- Manual rows confirmed on the Windows laptop at `main` ffa982c: 1.8, 1.11, 1.13, 1.15, 1.16, and
  the Windows part of 1.14 (Ctrl+C, sign-out). Observations in
  `context/changes/s12-desktop-window/research.md`.
- Left, all on Fedora: 1.9, 1.10, 1.12 and the `kill` part of 1.14.

## S-12: next steps

1. **You:** merge the pull request that records these rows (Rebase and merge).
2. **You, on the Fedora desktop**, in a terminal, in the cast-tv checkout:
   ```bash
   git switch main && git pull
   ```
   Then, in this order:
   - **1.10 (without the extra):**
     ```bash
     pipx install --force "$PWD"
     cast-tv
     ```
     Expected: a browser tab at http://127.0.0.1:8895/ui/ with a "Quit cast-tv" button at the
     right of the header. Start a video on the TV, then click "Quit cast-tv": the TV stops, the tab
     shows "cast-tv has ended; you can close this tab." and the terminal prompt returns.
   - **1.9 (with the extra):**
     ```bash
     pipx install --force "$PWD[window]"
     cast-tv
     ```
     Expected: a Qt window titled cast-tv showing the UI, not a browser tab.
   - **1.14 (kill):** in the cast-tv window, start a video on the TV. In a **second** terminal:
     ```bash
     pgrep -af cast-tv
     kill <the pid in the first column>
     ```
     Expected: the TV stops, the cast-tv window closes and the prompt returns in the first terminal.
   - **1.12 (forced fallback):**
     ```bash
     CAST_TV_WINDOW_FAIL=1 cast-tv
     ```
     Expected: a browser tab instead of a window; the terminal prints
     "No cast-tv window (unavailable: CAST_TV_WINDOW_FAIL); the UI opens in the browser…";
     **Diagnostics** (top right of the tab) shows `window_unavailable`.
3. Tell Claude what you saw for each row, also when it differed. Claude writes the observation
   into `research.md`, runs `--check-recordable` and only then ticks the row. Do not merge
   anything into `main` while the rows are being confirmed: they are recorded at the `main` SHA.
4. Then `/rune-impl-review s12-desktop-window phase 1` (a separate session), and
   `/rune-implement s12-desktop-window phase 2`.

## To decide, no hurry

- **Fedora:** whether to delete the VM disk in `~/.cache/cast-tv-s12-spike` (7.1 GB, VM stopped)
  and the 20 podman images `localhost/spike-*`.
- **Windows:** whether to delete `.venv-spike`, `build` and `dist` in
  `C:\Source\cast-tv\context\changes\s12-desktop-window\spike-kit` (gitignored, 1.2 GB).
- Whether to delete `C:\Source\cast-tv\temp_steps-2026-10-13.md` (an old untracked note).
- The local and remote branch `s12-desktop-window` still point at the merged df4900f; it is reset
  to `main` before Phase 2.

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
