# Next steps (2026-11-18, S-12 archived; the owner merges the 0.5.0 PR and tags v0.5.0)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **PR #106** (branch `s12-review-fixes`): Codex's impl-review fixes F1-F8 at 0f3ef79, then the
  manual rows on both machines.
  - **Windows 11** (2026-11-17, `research.md`, "The review fixes on Windows 11"): 1.8, 2.6,
    3.6-3.8, 3.10-3.12 and 4.5 accepted at 0f3ef79; the Windows parts of 1.13-1.15 and 4.10 passed.
  - **Fedora, now KDE Plasma 6.8.3** (2026-11-17, `research.md`, "The review fixes on Fedora, KDE
    Plasma"; the owner decided Fedora's rows are accepted on Plasma): 1.9-1.16, 2.7, 2.8, 2.9 (not
    run: no Ubuntu desktop) and 3.9 accepted at 21722ca (commit 68c5a07). F3, F6 and F7 seen on
    screen: "Add to menu" below the phone panel, the "Close the window" line once, no Fontconfig
    warnings. 4.6 and 4.7 accepted at 408dc79 (commit 849e904); 4.10's Fedora part passed.
    **Fedora is done.**
- **The launcher-icon finding:** after **Add to menu**, Plasma's Application Dashboard (Meta key)
  once listed cast-tv with a blank document icon while KRunner, the panel and Alt+Tab showed the
  TV; it was not reproduced afterwards. The owner approved a hardening: the menu entry also sends
  KIconLoader's `iconChanged` D-Bus signal (`castlib/shortcut.py`, `_announce_icon_change`). It
  changes `shortcut.py`, so the menu rows are confirmed again on 408dc79's release run 44178871505:
  Fedora's are done, and Windows's 4.8, 4.9 and 4.10 were accepted at 408dc79 on 2026-11-18
  (`research.md`, "The menu rows on Windows 11 again"). **All 26 manual rows of S-12 are current;
  none is open.**
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

- [x] 1. The review fixes, PR #106, CI green. — 2026-11-17, 0f3ef79.
- [x] 2. Windows rows on the PR's exe. — 2026-11-17.
- [x] 3. Fedora rows on the PR's Linux binary and pipx. — 2026-11-17, 68c5a07.
- [x] 4. **Claude:** the hardening commit pushed to #106; wait for its release run to be green.
   — 2026-11-17, 408dc79; release run 44178871505 green (Windows 26,124,328 bytes, `edgechromium
   OK`; Linux 260,590,064 bytes, `qtwebengine OK`).
- [x] 5. **Fedora (Claude drives; the owner looks once):** — 2026-11-17, 4.6 and 4.7 accepted at
   408dc79; 4.10's Fedora part passed (`research.md`, "The menu rows on Fedora again").
- [x] 6. Windows 11, 4.8, 4.9 and 4.10's Windows part on 408dc79's exe. — 2026-11-18, accepted
   at 408dc79; the acceptance script reports 26 current rows.
- [x] 7. PR #106 merged by rebase (main 8d99b49); SHAs rewritten from `main`. — 2026-11-18,
   PR "s12-shas-from-main" (the owner merges it).
- [x] 8. The owner chose `v0.5.0`, archive first, then the release. — 2026-11-18.
- [x] 9. `/rune-archive s12-desktop-window`: outcome completed, 26 of 26 manual rows current;
   S-12 `done` in the roadmap. — 2026-11-18, e3326d1 and a11a2fb on `archive-s12-desktop-window`.
- [x] 10. **You:** merge the archive PR ("Rebase and merge"); afterwards Claude writes the new
   `archive_commit` from `main` (as for signal-shutdown-races). — 2026-11-18, #108; cd53df0.
- [x] 11. **Claude:** a PR setting `castlib/__init__.py` to `0.5.0` (`chore(release): cast-tv 0.5.0`).
   — 2026-11-18, branch `release-0.5.0`, with the archive_commit fix.
- [ ] 12. **You:** merge it, then tag `v0.5.0` on `main` and push the tag:
   `git switch main; git pull; git tag v0.5.0; git push origin v0.5.0`. The `release` job
   publishes the GitHub Release; check its Assets list both files at the built sizes. This also
   checks ci-actions-node24's row 1.4.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout on an up-to-date `main` (`git switch main; git pull`).
