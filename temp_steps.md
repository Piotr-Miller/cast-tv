# Next steps (2026-10-27, main 1239dcb: Phase 2 rows done; merge the rows PR, then Phase 3 on Windows)

The standing note for a pause in the work (a reboot, a switch of machine): it stays in the
repository and is overwritten at the next pause.

Claude ticks each step (`- [x]`) as soon as it is done, with the date and, for a merge or a
recorded row, the PR or commit.

## Where it stands

- S-12 Phase 1 is done; S-13 is archived (PR #78).
- S-12 Phase 2 ("The release carries the window") is on `main` as 7eb63db (PR #80, squash-merged).
  All its manual rows are now accepted: 2.6 at 70d37b7 (PR #86) and 2.7-2.9 at 1239dcb, on the
  binaries of PR #82's release run 40398550351 (Windows 26072009 bytes, Linux 260495368 bytes).
- Phase 2 reopened Phase 1 rows 1.8-1.13 and 1.15 (`castlib/cli.py` changed); they are confirmed
  again once, near the end (step 15a). 1.14 and 1.16 stay current.
- ci-actions-node24 (PRs #82-#85) is archived; its row 1.4 (the `release` job publishes both files)
  waits for the next `v*` tag (step 17).
- The TV allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"); Fedora is "Device 3" and is allowed since 2026-10-27. If a
  machine gets "No TV found" while the TV is on, `curl http://192.168.50.142:9197/dmr` answering
  401 means that list, not cast-tv.
- Merge method: PRs #78-#87 went in as squash merges. Squash or rebase both work; after a merge
  Claude rewrites the branch SHAs in the plan to the `main` SHA.

## Now: Phase 2 rows 2.7-2.9

- [x] 1. **Windows 11, row 2.6:** re-confirmed 2026-10-26 on run 40398550351's exe, accepted at
   70d37b7 (PR #86).
- [x] 2. **Fedora, rows 2.7-2.9:** done 2026-10-27 (`research.md`, "Manual rows 2.7-2.9, Fedora"):
   2.7 the Qt window in 2.67 s, the UI at 7.35 s, GPU on, so the Linux release stays one file;
   2.8 a OneDrive HEIC upright on the TV, after allowing Fedora in the TV's Device Connection
   Manager; 2.9 the window opens in the Ubuntu 24.04.5 VM under Xvfb.
- [ ] 3. **You:** merge the PR `s12-rows-2.7-2.9`. The rows name `main`'s 1239dcb, so the merge
   needs no SHA rewrite.

## Phase 3: the console's information moves into the window, and the console hides

- [ ] 8. **Windows 11:** `/rune-implement s12-desktop-window phase 3`, then its PR. It also fixes
   the two findings of row 2.6 (`research.md`, "Phase 2"): the pythonnet `atexit` traceback after
   Ctrl+C, and `packaging/smoke.py` leaving the onefile child running on Windows.
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
      repeat for a pipx install and a checkout launch. Fedora has no pipx (2026-10-19): install it
      first (`sudo dnf install pipx`), or ask Claude for a scratchpad pipx as in Phase 1, which
      leaves the `~/.local/bin/cast-tv` symlink alone.
    - [ ] **4.10:** "Remove from menu" removes the entry.
- [ ] 15. **You:** merge the Phase 4 PR.

## Closing S-12

- [ ] 15a. **Windows 11 and Fedora:** confirm again the Phase 1 rows that Phase 2 reopened
    (`castlib/cli.py` changed): 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.15. Once, at the `main` SHA after
    the Phase 4 merge, since Phases 3 and 4 change `cli.py` again. Claude gives the steps.
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
