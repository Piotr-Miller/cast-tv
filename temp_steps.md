# Next steps (2026-11-18, v0.5.0 released; nothing is waiting)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **S-12 is done.** All 26 manual rows were current at the archive
  (`context/archive/2026-10-15-s12-desktop-window/`, archive commit cd53df0; PRs #106-#108).
- **v0.5.0 is released** (2026-11-18, tag on bd84500, release run 44371377463 green):
  https://github.com/Piotr-Miller/cast-tv/releases/tag/v0.5.0. Assets match the smoke test's sizes:
  `cast-tv-windows-x64.exe` 26,123,741 bytes (`edgechromium OK`), `cast-tv-linux-x64`
  260,589,552 bytes (`qtwebengine OK`).
- **ci-actions-node24's row 1.4** ("the next tag's release job publishes both files") was seen to
  pass on this release. The change is archived (`context/archive/2026-10-25-ci-actions-node24/`),
  which is read-only, so the row stays unticked there; this line is its record.
- **No change is open** (`context/changes/` is empty). The roadmap's open items: S-16 (start the
  release file faster, proposed; branch `roadmap-s16-nuitka` is merged as #98), S-14 (Google TV and
  Chromecast, proposed), S-10 and S-15 (parked).
- **CI notice:** GitHub says the `ubuntu-latest` label moves to Ubuntu 26 from 2026-10-19; the
  `test` and `release` jobs use it. The Linux build is pinned to `ubuntu-22.04`.
- **The TV** allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"). "No TV found" while the TV is on and
  `curl http://192.168.50.142:9197/dmr` answering 401 means that list, not cast-tv.
- **Test material:** the video is OneDrive → Dokumenty → Videos → `Przejazd - SuperCars.mp4`;
  `shelf-christmas-decoration.heic` is in OneDrive → Pictures; `Test_Pictures` is on Nextcloud.
- **Home Windows:** after a Windows sign-out, `vEthernet (Default Switch)` may get a new address.
  Locally, `test_onedrive.py::test_token_file_mode_0600` and
  `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving` fail intermittently; CI passes both.

## Next

- [x] 1. S-12's rows, archive and the v0.5.0 release. — 2026-11-18, #106-#109, tag v0.5.0.
- [ ] 2. **You:** choose the next roadmap item (S-16 is the proposed follow-up to S-12), then
   `/rune-new <change-id>`.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout on an up-to-date `main` (`git switch main; git pull`).
