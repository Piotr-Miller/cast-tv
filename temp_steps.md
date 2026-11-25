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
- **Still open:** row 3.15 (Windows), row 4.2 (README and PRD text changed by Phase 5, so it was
  reopened), and the M3 test sample in the Nextcloud trash.
- **Film thumbnails:** the owner's Storage Share has `OC\Preview\Movie` enabled but no ffmpeg,
  and konsoleH's occ list cannot set `preview_ffmpeg_path`. The owner chose a separate change:
  roadmap S-19 (proposed), cast-tv making the thumbnail itself.

## Next

- [ ] 1. The owner, in Chrome: open the Nextcloud **Files** page, click **Deleted files** in the
   left navigation, select only `cast-tv-test` and/or `PB014001-h264-35M.mp4` (the M3 sample),
   and click **Delete permanently**. Only those entries disappear; leave every other deleted
   file. Tell Claude, who records it under M3 in `research.md`.
- [ ] 2. The owner, on GitHub, PR #117 → **Files changed**: read `README.md`'s Nextcloud section
   (the new paragraph "A film is downloaded before casting…") and FR-014 in
   `context/foundation/prd.md`, and confirm them to Claude (row 4.2).
- [ ] 3. Row 3.15 at the next Windows visit (`C:\Source\cast-tv`, after `git fetch;
   git switch s17-nextcloud; git pull`): start this branch's cast-tv window; on the
   **Nextcloud** tab type the server address, click **Connect**, click the link (or **Copy
   link** and paste into Edge); grant access; the tab lists the root folders. Close the window,
   start cast-tv again: the tab lists the folders without a new sign-in. Click **Disconnect**:
   the gate appears.
- [ ] 4. After 1-3: the owner merges PR #117 with **Rebase and merge**; Claude then rewrites the
   recorded SHAs from `main`, archives `s17-nextcloud` and flips roadmap S-17 to `done`.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout after `git fetch; git switch s17-nextcloud; git pull`.
