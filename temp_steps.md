# Next steps (2026-11-17, PR #106: Fedora done; Windows's menu rows are next)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **PR #106** (branch `s12-review-fixes`): Codex's impl-review fixes F1-F8 at cd4dc1a, then the
  manual rows on both machines.
  - **Windows 11** (2026-11-17, `research.md`, "The review fixes on Windows 11"): 1.8, 2.6,
    3.6-3.8, 3.10-3.12 and 4.5 accepted at cd4dc1a; the Windows parts of 1.13-1.15 and 4.10 passed.
  - **Fedora, now KDE Plasma 6.8.3** (2026-11-17, `research.md`, "The review fixes on Fedora, KDE
    Plasma"; the owner decided Fedora's rows are accepted on Plasma): 1.9-1.16, 2.7, 2.8, 2.9 (not
    run: no Ubuntu desktop) and 3.9 accepted at 03b1b77 (commit 727351c). F3, F6 and F7 seen on
    screen: "Add to menu" below the phone panel, the "Close the window" line once, no Fontconfig
    warnings.
- **The launcher-icon finding:** after **Add to menu**, Plasma's Application Dashboard (Meta key)
  once listed cast-tv with a blank document icon while KRunner, the panel and Alt+Tab showed the
  TV; it was not reproduced afterwards. The owner approved a hardening: the menu entry also sends
  KIconLoader's `iconChanged` D-Bus signal (`castlib/shortcut.py`, `_announce_icon_change`). It
  changes `shortcut.py`, so **4.6, 4.7 and 4.10 (Fedora) and 4.8, 4.9 and 4.10's Windows part are
  confirmed again on the binaries of the PR's next release run.** The Windows code path is
  unchanged (the signal is Linux-only), but the rule reopens every row whose surface it touches.
- **The TV** allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"). "No TV found" while the TV is on and
  `curl http://192.168.50.142:9197/dmr` answering 401 means that list, not cast-tv.
- **Test material:** the video is OneDrive → Dokumenty → Videos → `Przejazd - SuperCars.mp4`;
  `shelf-christmas-decoration.heic` is in OneDrive → Pictures; `Test_Pictures` is on Nextcloud.
- **Fedora's GoPro session** expired (captured 2026-09-24); not needed for S-12. S-13's rows
  5.11-5.12 were recorded on 2026-10-26; nothing is overdue there.
- **Home Windows:** after a Windows sign-out, `vEthernet (Default Switch)` may get a new address.
  Locally, `test_onedrive.py::test_token_file_mode_0600` and
  `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving` fail intermittently; CI passes both.

## Next

- [x] 1. The review fixes, PR #106, CI green. — 2026-11-17, cd4dc1a.
- [x] 2. Windows rows on the PR's exe. — 2026-11-17.
- [x] 3. Fedora rows on the PR's Linux binary and pipx. — 2026-11-17, 727351c.
- [x] 4. **Claude:** the hardening commit pushed to #106; wait for its release run to be green.
   — 2026-11-17, ac7aa2d; release run 44178871505 green (Windows 26,124,328 bytes, `edgechromium
   OK`; Linux 260,590,064 bytes, `qtwebengine OK`).
- [x] 5. **Fedora (Claude drives; the owner looks once):** — 2026-11-17, 4.6 and 4.7 accepted at
   ac7aa2d; 4.10's Fedora part passed (`research.md`, "The menu rows on Fedora again"). on the new Linux binary, 4.6 (the
   panel's icon), 4.7 (**Add to menu**, then Meta + `cast` in the Dashboard: the TV icon; started
   from the launcher with no terminal) and 4.10 (**Remove from menu**; Meta + `cast` finds no app).
- [ ] 6. **Windows 11 (Claude drives, as on 2026-11-17; the owner answers the firewall prompt):**
   on the new exe, 4.8 (Add to Start menu, Start finds it, no console, pinning), 4.9 (moved file,
   Update menu entry) and 4.10's Windows part. The exe should be 26124328 bytes. In PowerShell:
   ```powershell
   cd C:\Source\cast-tv; git fetch; git switch s12-review-fixes; git pull
   mkdir $HOME\Downloads\s12-fixes2 -Force; cd $HOME\Downloads\s12-fixes2
   gh run download 44178871505 -R Piotr-Miller/cast-tv -n cast-tv-windows-x64.exe
   ```
   Then write "co dalej" to Claude in `C:\Source\cast-tv`.
- [ ] 7. **You:** merge PR #106 ("Rebase and merge"); afterwards Claude rewrites the SHAs from `main`.
- [ ] 8. **You:** decide on the release tag (e.g. `v0.5.0`). This also checks ci-actions-node24's
   row 1.4 (a green `release` job; the Assets list both files at the built sizes).
- [ ] 9. `/rune-archive s12-desktop-window`; S-12 becomes `done` in the roadmap.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout. Until PR #106 is merged, work on its branch:
`git fetch; git switch s12-review-fixes; git pull`.
