# Next steps (2026-11-17, review fixes ready for commit and PR checks)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- Branch: `s12-review-fixes`, created from up-to-date main `ee74c2c`.
- The owner approved fixing all eight Phases 2–4 implementation-review findings using the
  recommended approaches. All eight are applied and their saved decisions say FIXED.
- The report is `context/changes/s12-desktop-window/reviews/impl-review-phase-2-4-ee74c2c.md`.
  Its original verdict still describes the earlier reviewed HEAD; the appended Triage section
  describes the fixes and verification.
- Changes remain **uncommitted**. The review skill does not commit. Source, tests, packaging
  and workflow records belong together; ownership hashes are in
  `.git/rune/s12-desktop-window.carry`.
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

- [x] 1. **In the PowerShell window for C:\Source\cast-tv**, run `git branch --show-current`,
   `git status --short` and `git diff --stat`. Expect branch `s12-review-fixes` and the approved
   source/test/packaging changes plus S-12 records and this note. Have the approved fix set
   committed together with the reopened plan rows and change notes, then open a PR. Never add
   ignored toolkit material or scratch builds, and never merge the PR through an agent.
   — 2026-11-17, Claude committed the fix set and opened the PR (see the PR list).
- [ ] 2. **On the PR's GitHub Checks page**, verify both test jobs and both release build/smoke jobs
   turn green for the new commit. The local Linux build uses Ubuntu 26.04 / glibc 2.43 and does
   not replace the workflow's Ubuntu 22.04 / Python 3.12 compatibility check.
- [ ] 3. **On Windows and Fedora, using the new PR artifacts**, run the reopened acceptance rows and
   focused checks from `follow-ups/review-fixes.md`. In the cast-tv window, the launcher should
   sit below the phone panel and long errors should wrap. In Fedora's Terminal, expect no
   Fontconfig warnings and no repeated startup line when raising the window. Write each real
   observation before re-confirming through `$rune-implement s12-desktop-window`.
   Do not use the old PR #97 artifact or the local synthetic-client builds for these confirmations.
- [ ] 4. After the owner merges, rewrite commit references from main as required, then perform a fresh
   review of the fix revision. The owner decides the release tag. Archive only after the intended
   implementation/review work is settled, recording any remaining manual acceptance honestly.

To resume: tell the next session to commit the approved review fixes and open a PR, without
merging it. The carry record protects later hand edits; check its hashes before adopting files.
