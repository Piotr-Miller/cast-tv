# Next steps (2026-11-25, S-17 Nextcloud: Fedora rows done; Windows next)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **S-17 Nextcloud** is on branch `s17-nextcloud`, draft PR #117. Phases 1-5 are implemented;
  Phase 5 (2026-11-25, `569da31`) downloads a Nextcloud film before casting, because the owner's
  OM films (HEVC 4K60, ~134 Mbit/s) stalled through the relay on the laptop's Wi-Fi and played
  smoothly from disk (`research.md`, rows 3.9 and 5.4, measurements M1-M3).
- **Accepted on Fedora (2026-11-25):** rows 3.5-3.8, 3.10-3.14 and 5.4. Row 3.9 is n/a by owner
  decision (replaced by 5.4). Full review F1-F7 fixed (`12823bd`, `907f31c`).
- **Still open:** row 3.15 (Windows) only.
- **Film thumbnails:** the owner's Storage Share has `OC\Preview\Movie` enabled but no ffmpeg,
  and konsoleH's occ list cannot set `preview_ffmpeg_path`. The owner chose a separate change:
  roadmap S-19 (proposed), cast-tv making the thumbnail itself.

## Next

- [x] 1. The owner, in Chrome: open the Nextcloud **Files** page, click **Deleted files** in the
   left navigation, select only `cast-tv-test` and/or `PB014001-h264-35M.mp4` (the M3 sample),
   and click **Delete permanently**. Only those entries disappear; leave every other deleted
   file. Tell Claude, who records it under M3 in `research.md`. — 2026-11-25, done by the owner.
- [x] 2. The owner, on GitHub, PR #117 → **Files changed**: read `README.md`'s Nextcloud section
   (the new paragraph "A film is downloaded before casting…") and FR-014 in
   `context/foundation/prd.md`, and confirm them to Claude (row 4.2). — 2026-11-25, accepted.
- [ ] 3. The owner: restart the laptop and choose **Windows 11** in the boot menu (Fedora and
   Windows are a dual boot; nothing else is left on Fedora).
- [ ] 4. The owner, in a PowerShell window, fetch the branch and install the new dependency
   (S-17 added `defusedxml`, which the Windows `.venv` does not have yet):

   ```powershell
   cd C:\Source\cast-tv
   git fetch; git switch s17-nextcloud; git pull
   .venv\Scripts\pip install -e ".[window]"
   ```

   The last line ends with `Successfully installed … defusedxml-…` (or says it is already
   satisfied).
- [ ] 5. The owner: start Claude Code in `C:\Source\cast-tv` and write "co dalej".
- [ ] 6. Row 3.15, Claude drives the window and the owner signs in: start this branch's cast-tv
   window (`.venv\Scripts\python -m castlib -d`); on the **Nextcloud** tab type the server
   address, click **Connect**, click the link (or **Copy link** and paste into Edge); the owner
   grants access; the tab lists the root folders. Close the window, start cast-tv again: the tab
   lists the folders without a new sign-in. Click **Disconnect**: the gate appears. Claude writes
   the observation into `research.md` (row, date, device, what was seen), the owner confirms,
   Claude ticks the row and pushes.
- [ ] 7. After 6: the owner merges PR #117 with **Rebase and merge**; Claude then rewrites the
   recorded SHAs from `main`, archives `s17-nextcloud` and flips roadmap S-17 to `done`.

## How to resume with Claude

On Windows: steps 3-5 above, then "co dalej". On Fedora: write "co dalej" in the cast-tv
checkout after `git fetch; git switch s17-nextcloud; git pull`.
