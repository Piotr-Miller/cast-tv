# Next steps (2026-11-17, PR #106: Windows rows done; Fedora rows next)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **PR #106** (branch `s12-review-fixes`, fixes at cd4dc1a; CI and release run 43978457151 green).
  **Windows is done** (2026-11-17, `research.md`, "The review fixes on Windows 11"): 1.8, 2.6,
  3.6-3.8, 3.10-3.12, 4.5, 4.8 and 4.9 accepted at cd4dc1a; the Windows parts of 1.13-1.15 and
  4.10 passed. Every open row left is Fedora's.
- The owner approved fixing all eight Phases 2–4 implementation-review findings using the
  recommended approaches. All eight are applied and their saved decisions say FIXED.
- The report is `context/changes/s12-desktop-window/reviews/impl-review-phase-2-4-ee74c2c.md`.
  Its original verdict still describes the earlier reviewed HEAD; the appended Triage section
  describes the fixes and verification.
- Windows full suite: 524 passed, 5 skipped. Linux full suite: 525 passed, 4 skipped. Both used
  test-only environments with Node available. A final smoke-only guard added one case afterward;
  all 11 smoke tests and both binary smoke checks then passed. Lint and JS syntax pass.
- The current-dependency Windows run reproduced the known OneDrive account timeout; the
  full run with earlier repository dependency versions passed. The excluded test was unchanged.
- Both local builds pass HEIC, HTTP, owned Quit and expected-engine checks. Windows:
  26,223,246 bytes, edgechromium; Linux: 249,746,352 bytes, qtwebengine. Local build credentials
  are synthetic: these binaries are smoke-test material, not real sign-in acceptance artifacts.
- Fontconfig A/B: old release parser 2.13.1 plus upstream 2.18.3 rules gives exactly 45
  diagnostics; the private rules give zero and Qt rendering passes. The fix is bundled and
  automatic; explicit FONTCONFIG_FILE/PATH overrides still work. Real Fedora acceptance is open.
- Reopened: 1.9–1.12, 1.16, 2.7–2.9, 3.9, 4.5–4.10. Prior revisions and changed surfaces are in
  change.md. The 11 malformed short/combined acceptance suffixes remain unverifiable.
  Phases 2–4 currently have 10 pending and 7 unverifiable rows, 0/17 current.
- Full evidence is in research.md and follow-ups/review-fixes.md. Scratch logs, screenshots,
  test tools and local binaries are under `.git/rune/s12-fixes/` and stay out of Git.

## Reference

- **The TV** allows DLNA per client (Settings → General → Device Connection Manager → Device List,
  entries named only "Device N"). "No TV found" while the TV is on and
  `curl http://192.168.50.142:9197/dmr` answering 401 means that list, not cast-tv.
- **Test material:** the video is OneDrive → Dokumenty → Videos → `Przejazd - SuperCars.mp4`;
  `shelf-christmas-decoration.heic` is in OneDrive → Pictures; `Test_Pictures` is on Nextcloud.
- **Home Windows:** after a Windows sign-out, `vEthernet (Default Switch)` may get a new address;
  row 3.8 needs it disabled (`Disable-NetAdapter` in an administrator Terminal) and the Wi-Fi tile off.
- Locally on Windows, `test_onedrive.py::test_token_file_mode_0600` and
  `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving` fail intermittently; CI passes both.

## Next

- [x] 1. Commit the review fixes and open the PR. — 2026-11-17, cd4dc1a, PR #106.
- [x] 2. The PR's checks: test on both systems, build/smoke on both. — 2026-11-17, green; Windows
   26,124,589 bytes, `window-check: edgechromium OK`; Linux 260,588,936 bytes, `qtwebengine OK`.
- [x] 3a. **Windows**, the reopened rows on the PR's exe. — 2026-11-17, see "Where it stands".
- [ ] 3b. **Fedora**, in a terminal, on the PR's Linux binary:
   ```bash
   cd <checkout> && git fetch && git switch s12-review-fixes && git pull
   mkdir -p ~/Downloads/s12-fixes && cd ~/Downloads/s12-fixes
   gh run download 43978457151 -R Piotr-Miller/cast-tv -n cast-tv-linux-x64
   chmod +x cast-tv-linux-x64 && stat -c %s cast-tv-linux-x64 && ./cast-tv-linux-x64 --version
   ```
   The size should be 260588936. Then write "co dalej" to Claude there; Claude gives each row's
   steps. The rows: 1.9-1.12, 1.16, 2.7, 2.8 (2.9 as before: the Ubuntu VM is gone), 3.9, 4.6,
   4.7, 4.10, and the Fedora parts of 1.13, 1.14 (Ctrl+C and `kill`) and 1.15. Also check the
   fixes: no Fontconfig warnings in the terminal (F7), "Close the window or press Ctrl+C" printed
   once even after raising the window (F6), "Add to menu" below the phone panel (F3).
- [ ] 4. **You:** merge PR #106 ("Rebase and merge"); afterwards Claude rewrites the SHAs from `main`.
- [ ] 5. **You:** decide on the release tag (e.g. `v0.5.0`). This also checks ci-actions-node24's
   row 1.4 (a green `release` job; the Assets list both files at the built sizes).
- [ ] 6. `/rune-archive s12-desktop-window`; S-12 becomes `done` in the roadmap.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout. Until PR #106 is merged, work on its branch:
`git fetch; git switch s12-review-fixes; git pull`.
