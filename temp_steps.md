# Next steps (2026-11-22, S-16 merged and archived; the release next)

The standing pause note; overwrite it at the next handoff. Claude ticks each step (`- [x]`) as
soon as it is done, with the date and, for a merge or a recorded row, the PR or commit.

## Where it stands

- **S-16, a faster-starting release file:** merged as PR #111 (rebase, main fc89537) on
  2026-11-22 and archived → `context/archive/2026-11-18-s16-faster-start/` (9ae180b). The
  release is a Nuitka onefile that unpacks once per build into `~/.cache/cast-tv/<version>-gh<run>.<attempt>`
  (Windows: `%LOCALAPPDATA%\cast-tv\...`). Warm start against PyInstaller: 0.706 on Fedora,
  0.734 on Windows 11 (bar 0.75); cold 0.633 and 0.828 (bar 1.00). All 21 manual rows accepted.
- **Not yet released:** `main` still says `0.5.0` (`castlib/__init__.py`); v0.5.0 (2026-11-18)
  is the last PyInstaller release. The next tag publishes the two Nuitka files under the old
  names.
- **Users will notice:** a new version's first start unpacks (about 550 MB on Linux, 80 MB on
  Windows), and Windows' firewall asks once per new build (its rule names the unpacked exe).
- **Finding outside S-16:** while a video plays, the now-playing bar still shows the
  **HEIC → JPEG** badge of the photo cast before it; for a change of its own.
- **Fedora and Windows 11 are a dual boot on one laptop:** every switch is a reboot.
- **CI notice:** `ubuntu-latest` moves to Ubuntu 26 (the `test` job); the Linux build is pinned to
  `ubuntu-22.04`.
- **The TV** allows DLNA per client (Settings → General → Device Connection Manager → Device List).
  "No TV found" while `curl http://192.168.50.142:9197/dmr` answers 401 means that list.
- **Measuring on Windows:** check first that `TiWorker` (Windows servicing) is idle; on
  2026-11-21 it spoiled a whole series.

## Next

- [x] 1. Merge the PR of branch `s16-after-merge` (S-16's SHAs rewritten from main, the archive,
   roadmap S-16 → done, this file). — 2026-11-22, PR #112.
- [ ] 2. The release: the owner picked 0.6.0 (2026-11-22). Claude opens a
   PR `chore(release): cast-tv <version>` that sets `castlib/__init__.py`; the owner merges it;
   then the tag `v<version>` on main, whose release run publishes the files.
- [ ] 3. After the release: download both files from the GitHub release and start each once on
   its system (the first start of the published build).
- [ ] 4. The owner picks the next roadmap item (S-14 Google TV / Chromecast is proposed), or the
   HEIC-badge finding.

## How to resume with Claude

Write "co dalej" in the cast-tv checkout (on Windows: `C:\Source\cast-tv`) after
`git fetch; git switch main; git pull`.
