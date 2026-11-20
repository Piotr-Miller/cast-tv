# Research: s16-faster-start

2026-11-18. No codebase research was run for this change; the blocking question was external.
Spikes below.

## Spike: does a Nuitka onefile of cast-tv unpack once into a fixed cache and start clearly faster than the PyInstaller onefile on later launches, with `--window-check` passing? (2026-11-18, 20:40)

Windows 11 Pro on the home laptop (`DESKTOP-35JAM1C`), Python 3.14.5, and a throwaway GitHub
Actions job on `ubuntu-22.04` with Python 3.12, the release's runner and Python. Both builds were
made from `main` at a85f59d (cast-tv 0.5.0), with the stub Google client: no secrets.

**What the previous source said.** `context/foundation/roadmap.md:222` — "the S-12 release is a
PyInstaller onefile that unpacks itself on every start: Linux 260.6 MB, Windows 26.1 MB"; and
`:226-228` — "whether its onefile can unpack once into a fixed cache directory
(`--onefile-tempdir-spec`) and reuse it on later starts" (roadmap `updated: 2026-11-18`, S-16
written 2026-11-05). The measured S-12 starts: `context/archive/2026-10-15-s12-desktop-window/research.md:861`
— "7.35 s to a usable UI, is under the plan's 15 s threshold, so the Linux release stays one
file" (Fedora 44, 2026-10-27); `:837` — "The cast-tv window opened on the UI 1.5-2 s after Enter
(owner's estimate)" (Windows, 2026-10-26). The roadmap's "unpacks itself on every start" is
confirmed below; the cache claim was an open question, now answered.

**Documentary half.**

- **PyInstaller unpacks on every start and deletes the folder** — "When started it creates a
  temporary folder in the appropriate temp-folder location for this OS." and "When the bundled
  code terminates, the bootloader deletes the temporary folder."
  (https://pyinstaller.org/en/stable/operating-mode.html, read 2026-11-18)
- **`--runtime-tmpdir` only moves that folder** — "The `_MEIxxxxxx`-folder will be created here."
  (https://pyinstaller.org/en/stable/usage.html, read 2026-11-18). The page does not describe
  reusing an earlier extraction.
- **Nuitka's cached onefile** — from `python -m nuitka --help`, Nuitka 4.3.5, the vendor's own
  text in the installed version (read 2026-11-18): `--onefile-tempdir-spec` "Defaults to
  '{TEMP}/onefile_{PID}_{TIME_US}_{RANDOM}', i.e. user temporary directory and being non-static
  it's removed. Use e.g. a string like '{CACHE_DIR}/{COMPANY}/{PRODUCT}/{VERSION}' which is a good
  static cache path, this will then not be removed." `--onefile-cache-mode`: "cached will not
  remove it and see to reuse its contents during next execution for faster startup times."
- **The web user manual is silent on the cache** — https://nuitka.net/user-documentation/user-manual.html,
  read 2026-11-18, does not mention `--onefile-tempdir-spec`, `{CACHE_DIR}` or reuse; it says "The
  startup of **Nuitka** in **Onefile** is fast, but your program might need more time." Current
  release: "The current release is Nuitka 4.3.5." (https://nuitka.net/doc/download.html, read
  2026-11-18). PySide6: "# nuitka-project: --enable-plugin=pyside6" (user manual). The manual does
  not mention QtWebEngine. Compilers: GCC, Clang or Zig on Linux; on Windows "Visual Studio 2022"
  or higher, or the MinGW64 that Nuitka downloads (user manual, "C Compiler").

**Empirical half.**

Windows (Visual Studio Build Tools 2026, `cl 14.5`; 16.3 min build):

```
python -m nuitka --onefile --assume-yes-for-downloads --msvc=latest
  --onefile-tempdir-spec="{CACHE_DIR}/cast-tv/{VERSION}" --product-name=cast-tv
  --product-version=0.5.0 --file-version=0.5.0 --windows-icon-from-ico=castlib/ui/cast-tv.ico
  --include-package=castlib --include-package-data=castlib --include-package=pillow_heif
  --include-package-data=pillow_heif --include-module=webview.platforms.winforms
  --nofollow-import-to=tkinter --nofollow-import-to=pytest
  --output-dir=<scratch>\nuitka-out --output-filename=cast-tv-nuitka.exe packaging\entry.py
pyinstaller --noconfirm packaging\cast-tv.spec        # PyInstaller 6.22.3, same venv
```

Each file run three times in a row with `--version`, then three times with `--window-check`
(wall time from `subprocess.run`, the Nuitka cache deleted before its first run):

| Windows | size | `--version` 1 / 2 / 3 | `--window-check` 1 / 2 / 3 |
| --- | --- | --- | --- |
| PyInstaller | 26,226,118 B | 4.77 / 3.60 / 3.63 s | 6.74 / 7.17 / 5.91 s |
| Nuitka, cached | 18,874,880 B | 4.86 / 2.73 / 2.38 s | 4.32 / 4.37 / 5.10 s |

- The cache stayed: `%LOCALAPPDATA%\cast-tv\0.5.0`, 56 files, 81,544,554 bytes (Nuitka's payload
  "size 81547822 to 18624112", 22.84 % compression). The existing `%LOCALAPPDATA%\cast-tv\Cache`
  (the GoPro browser cache) was left alone.
- Every run printed `Window: edgechromium` or `window-check: edgechromium OK`, rc 0. Some window
  checks of both builds also printed the GoPro 401 traceback and `ConnectionAbortedError [WinError
  10053]` (this laptop's GoPro session is expired; the page's request outlives the closing window);
  it is the same noise in both and not caused by Nuitka.

Linux, GitHub Actions run 44379679380 on `ubuntu-22.04` (branch `spike/s16-nuitka`, workflow
`.github/workflows/spike-nuitka.yml`; Nuitka 4.3.5, PyInstaller 6.22.3; 10 min Nuitka build):

```
python -m nuitka --onefile --assume-yes-for-downloads \
  --onefile-tempdir-spec='{CACHE_DIR}/cast-tv/{VERSION}' \
  --product-name=cast-tv --product-version=0.5.0 --file-version=0.5.0 \
  --enable-plugin=pyside6 \
  --include-package=castlib --include-package-data=castlib \
  --include-package=pillow_heif --include-package-data=pillow_heif \
  --include-module=webview.platforms.qt --include-module=qtpy \
  --noinclude-dlls='libgbm.so*' --noinclude-dlls='libstdc++.so*' \
  --nofollow-import-to=tkinter --nofollow-import-to=pytest --nofollow-import-to=gi \
  --output-dir=nuitka-out --output-filename=cast-tv-nuitka packaging/entry.py
```

| Linux (CI runner, xvfb) | size | `--version` 1 / 2 / 3 | `--window-check` 1 / 2 / 3 |
| --- | --- | --- | --- |
| PyInstaller | 260,587,936 B | 4.21 / 4.23 / 4.22 s | 8.35 / 4.79 / 4.81 s |
| Nuitka, cached | 154,765,528 B | 1.82 / 1.56 / 1.57 s | 2.21 / 2.18 / 2.23 s |

- The cache stayed: `~/.cache/cast-tv/0.5.0`, 545,667,616 bytes.
- Every run printed `Window: qtwebengine` or `window-check: qtwebengine OK`, rc 0; zero
  `Fontconfig error|warning` lines from the last window check of each build. The pyside6 plugin
  reported "Including QtWebEngine executable."

**Not yet checked:**

- **Start time on the real machines.** CI runner and this laptop only. Fedora, where the 260 MB
  unpack hurts most, is not timed; nor is the time to a usable UI as rows 2.6 and 2.7 measure it.
  On CI the first Nuitka start (cache just deleted) took 1.82 s, so the cold cost there is small;
  on Windows it was 4.86 s, like PyInstaller's every start.
- **A stale cache.** Whether a new release with the same `{VERSION}` (or a damaged cache folder)
  is detected; the help text does not say. Every release would need its own version in the path.
- **Where `sys.frozen` and `sys._MEIPASS` are read.** Nuitka does not set them the PyInstaller way;
  `castlib/platform.py:508` (the console detach, row 3.10), `:801`/`:806` (the private Fontconfig
  rules), `:827` (the CA bundle), `castlib/shortcut.py:165` (the menu entry's target) and
  `castlib/window.py:79` (the window icon) branch on them. Not exercised by `--version` or
  `--window-check`.
- **The menu entry's target.** In a cached onefile the running Python is the unpacked copy in the
  cache; which path a shortcut must name is untested.
- **Hiding the console on a Windows double-click** (PyInstaller's `hide_console="hide-early"`);
  Nuitka has its own console options, not tried.
- **Fontconfig on a newer distribution.** The CI runner's fonts match the old bundled parser; the
  45 diagnostics of S-12's F7 appeared only on a newer host, which this run does not have.
- **Old cache folders.** Each version leaves 81 MB (Windows) or 546 MB (Linux) in the cache, and
  nothing removes them.
- **SmartScreen and antivirus** reaction to a Nuitka exe that writes and runs DLLs from
  `%LOCALAPPDATA%`.
- **The real smoke test** (`packaging/smoke.py`: HEIC, HTTP, owned Quit) on the Nuitka files.

**What this settles:** yes. With `--onefile-tempdir-spec` a Nuitka onefile keeps its unpacked files
and later starts reuse them. Both builds pass `--window-check` on the expected engine. On the
same machines the warm starts were faster than PyInstaller's: `--version` 2.4–2.7 s against
3.6 s on Windows and 1.6 s against 4.2 s on the Linux runner; `--window-check` 2.2 s against
4.8 s on Linux. The Linux file was 41 % smaller (154.8 MB against 260.6 MB). The slice stays
open. `/rune-plan` can now weigh these numbers against the open items above.

## Row 1.7: the Ready mark on Windows 11 (2026-11-18)

The home Windows 11 laptop (`DESKTOP-35JAM1C`). A PyInstaller exe built from a558115 (Phase 1's
commit; the castlib code is unchanged at 5155ad8) with `pyinstaller --noconfirm packaging\cast-tv.spec`
in the spike's venv (PyInstaller 6.22.3, Python 3.14.5): 26,225,168 bytes, SHA-256
`AC4FC324C18FCC1AF1B310DA6E4A5B18B8DF4405A3942884288E3B90168C6AA0`. Claude ran, from the
checkout's venv at 5155ad8:

```
python packaging\startup_time.py <exe> --mode warm --runs 5 --out p1-warm.json
python packaging\startup_time.py <exe> --mode warm --runs 1 --hold 15 --out p1-watched.json
```

- 5 warm runs, one unmeasured start first: 4.32 / 4.24 / 4.64 / 3.86 / 3.41 s, median 4.24 s.
- The watched run: "ready after 3.62 s: the window stays open 15 s". The owner watched the screen
  and accepted ("akceptuję"): at the moment the time printed, the window showed the TV button and
  the GoPro / OneDrive / Google Photos tabs, and a tab click responded.
- Found: `--hold` also held the unmeasured priming start (the window stayed open after 4.17 s as
  well). It does not change any time; the priming start is never measured.

Row 1.7 is accepted at fc780beb1660330a543a6c0bf9fd41036f840f2c (the docs commit over 5155ad8; same code).

## Phase 1 implementation review and fixes (2026-11-19)

Report: `reviews/impl-review-phase-1-0707dac.md`. The owner authorized all recommended fixes;
the changes remain uncommitted as requested. This section is automated review evidence, not a
new observation accepting row 1.7.

- A held `/api/errors` reproduced Ready before the tab watcher was installed. The fixed UI
  installs its handlers first and starts initial source setup after a successful status,
  independently of errors fetching. The test driver now controls the render tick and distinct
  frames, exercises watcher callbacks, and reports started asynchronous failures.
- Deliberately replacing the Ready barrier with an immediate post, a single frame, or two frames
  without the render tick makes the new regression test fail. The initial-setup regression test
  also rejects the original committed component. These experiments used temporary source copies.
- Native Windows probes showed why desktop-session inference was unsafe: ProcessIdToSessionId
  returned access denied for image-denied processes; a WTS snapshot found protected processes
  in both session 0 and our desktop session 1. The lister now uses explicit user-SID ownership,
  and treats unknown ownership as incomplete rather than treating it as an exited process.
- **Windows limitation observed:** in this unelevated session WTS returned no owner SID for the
  inaccessible other-account processes. The fixed lister therefore raises IncompleteListing at
  PID 4. This is an intentional safe refusal, not a successful complete scan. Elevated rights may
  provide more ownership information, but that outcome has not been observed or accepted here.
  The future Phase 3 pruner must retain its no-deletion-on-IncompleteListing rule.
- Failed version probing and failed owned shutdown now reject a measurement. The known `--hold`
  behavior on priming remains deferred to Phase 4.
- The first full review run failed three existing test-synchronization hazards. The OneDrive
  failure also reproduced in a temporary checkout of base a85f59d. The tests now wait for the
  post-response Quit effect, tolerate App initialization in the CLI predicate, and wait for the
  account write through its lock before reading the fake credential file on Windows.
- Row 1.7 was reopened after the acceptance-state script reported its surface stale through
  `castlib/processes.py`, `castlib/ui/app.js` and `packaging/startup_time.py`. The original human
  observation above is preserved; only a new human observation at a committed revision can
  restore acceptance. Packaging PR build/smoke validation is also still required.

## Windows ownership without elevation (2026-11-19)

After the Phase 1 review (F7), `castlib/processes.py` decided ownership by the user SID from
`WTSEnumerateProcessesW`. On the home Windows 11 laptop, unelevated, that snapshot had no owner for
176 of 451 processes (PID 0, 4 and the protected and service processes), and those refuse
`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`. Every listing was therefore incomplete:
`startup_time.py` refused at PID 4, and Phase 3 would never prune on Windows.

Experiment (Claude, unelevated Python 3.14.5 probe; the exe is the PyInstaller build of a558115,
SHA-256 `AC4FC324…6AA0`):

- cast-tv started normally (`--no-browser -p 8897`): both processes (bootloader 32188, child 29764)
  were readable from the probe, WTS owner = our SID.
- cast-tv started with `Start-Process -Verb RunAs` (the owner approved the UAC prompt) on port
  8898: both processes (17844, 23244) were readable, WTS owner = our SID; a token check confirmed
  both elevated while the probe was not.
- In both runs, no process whose WTS owner is our SID refused the image query.

Owner decision (2026-11-19): a refusal counts as "not ours" unless WTS names our SID, which stays
incomplete. Other API errors stay incomplete. With this rule the unelevated listing returns
273 processes.

## Row 1.7 again, after the Phase 1 review fixes (2026-11-19)

Row 1.7 was reopened by the review fixes (99287e6). Same laptop. A PyInstaller exe built from
a32a0ea (the fixes, the Windows ownership rule 3e67ec8 and the unheld priming start), same venv
and command as before: 26,226,959 bytes, SHA-256
`5AD64532F501123EC122C6A670735531262C12F9D7BE01DD5143417DF2E44D26`. Claude ran from an ordinary,
unelevated PowerShell (no refusal: the ownership rule works without elevation):

```
python packaging\startup_time.py <exe> --mode warm --runs 5 --out p1b-warm.json
python packaging\startup_time.py <exe> --mode warm --runs 1 --hold 15 --out p1b-watched.json
```

- 5 warm runs: 4.28 / 4.00 / 4.08 / 4.82 / 5.10 s, median 4.28 s (2026-11-18: 4.24 s).
- The watched run: "ready after 4.17 s: the window stays open 15 s"; the priming start was no
  longer held. The owner watched and accepted ("akceptuję"): the TV button and the GoPro / OneDrive
  / Google Photos tabs were on screen when the time printed, and a tab click responded.
Row 1.7 is accepted at 185f2062837a293ab9b02b5dfbd00ed4d1cd21d6 (the docs commit over a32a0ea; same code).

## Phase 5 on Windows 11: rows 5.2, 5.4 and 5.6 (2026-11-20)

The home laptop (Windows 11, the same one as row 1.7). The files are the two Windows artifacts of
PR #111's release run 44630376210 at 7a7eb32 (Phase 4 review APPROVED), downloaded with
`gh run download 44630376210 -n <artifact> -D <dir>` into `%USERPROFILE%\Downloads\s16-run-44630376210`:

- Nuitka `cast-tv-windows-x64-nuitka.exe`: 18,300,416 B, SHA-256
  `7d044dfdffda52e52d3912c2f4f581f909ce47d0a1662366e6a20cdefaeeda99` (the review's value).
  Its build-info: identity `0.5.0-gh44630376210.1`, Nuitka 4.3.5, Python 3.12.10, pip-freeze hash
  `4e2a97f748eafcf0b5ca79f300a445f382cd6979859adf52c3ba113ebb6165a6`. Cache: `C:\Users\pmill\AppData\Local\cast-tv\0.5.0-gh44630376210.1`.
- PyInstaller `cast-tv-windows-x64.exe`: 26,143,942 B, SHA-256
  `1a622aec330dd4647dff906c6779037552669da871864877f60e985eedd9f8bf`. Cache: none.

At the owner's request, Claude ran the four series one after another from an unelevated Git Bash
in the checkout, while the owner left the laptop alone; then the comparisons:

```
.venv/Scripts/python packaging/startup_time.py <nuitka exe> --mode cold --out win-nuitka-cold.json
.venv/Scripts/python packaging/startup_time.py <nuitka exe> --mode warm --out win-nuitka-warm.json
.venv/Scripts/python packaging/startup_time.py <pyinstaller exe> --mode cold --out win-pyi-cold.json
.venv/Scripts/python packaging/startup_time.py <pyinstaller exe> --mode warm --out win-pyi-warm.json
.venv/Scripts/python packaging/startup_time.py --compare win-nuitka-cold.json win-pyi-cold.json --warm-ratio 0.75
.venv/Scripts/python packaging/startup_time.py --compare win-nuitka-warm.json win-pyi-warm.json --warm-ratio 0.75
```

| Windows 11 | runs (s) | median |
| --- | --- | --- |
| Nuitka cold | 4.41 / 4.00 / 3.90 / 3.84 / 4.02 | 4.00 s |
| Nuitka warm | 2.77 / 3.08 / 2.85 / 2.87 / 2.88 | 2.87 s |
| PyInstaller cold | 4.34 / 4.20 / 4.01 / 3.74 / 4.05 | 4.05 s |
| PyInstaller warm | 3.83 / 3.95 / 4.14 / 3.78 / 4.20 | 3.95 s |

```
cold: Nuitka median 4.00 s, PyInstaller median 4.05 s, ratio 0.988 (limit 1.00): PASS
warm: Nuitka median 2.87 s, PyInstaller median 3.95 s, ratio 0.727 (limit 0.75): PASS
```

Every run finished; all six commands exited 0. **The Windows bar is met (row 5.6)**, with a small
margin: warm 0.727 against 0.75, cold practically equal. PyInstaller's warm median was 4.28 s at
row 1.7 (2026-11-19) and 3.95 s here; a session-to-session spread of that size moves the warm
ratio by about 0.05.

The watched run (row 5.4), started by Claude at the owner's request while the owner watched:

```
.venv/Scripts/python packaging/startup_time.py <nuitka exe> --mode warm --runs 1 --hold 30 --out win-nuitka-watched.json
```

It printed "ready after 2.98 s: the window stays open 30 s". The owner confirmed ("Potwierdzam",
2026-11-20) what the row asks: the window showed the TV button and the source tabs when the time
printed, and a tab click responded. The owner also confirmed rows 5.2 and 5.6 from the results
above.

The result files, without the local `binary` path:

```
win-nuitka-cold.json:
{"size": 18300416, "sha256": "7d044dfdffda52e52d3912c2f4f581f909ce47d0a1662366e6a20cdefaeeda99", "version": ["cast-tv 0.5.0", "Google Photos client: built in", "GoPro window: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "Window: edgechromium", "Cache: C:\\Users\\pmill\\AppData\\Local\\cast-tv\\0.5.0-gh44630376210.1"], "system": "Windows 11", "mode": "cold", "runs": [4.406747102737427, 4.001554012298584, 3.8981690406799316, 3.840561866760254, 4.01525092124939], "median": 4.001554012298584}
win-nuitka-warm.json:
{"size": 18300416, "sha256": "7d044dfdffda52e52d3912c2f4f581f909ce47d0a1662366e6a20cdefaeeda99", "version": ["cast-tv 0.5.0", "Google Photos client: built in", "GoPro window: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "Window: edgechromium", "Cache: C:\\Users\\pmill\\AppData\\Local\\cast-tv\\0.5.0-gh44630376210.1"], "system": "Windows 11", "mode": "warm", "runs": [2.7672276496887207, 3.0761852264404297, 2.851867198944092, 2.871990203857422, 2.875440835952759], "median": 2.871990203857422}
win-pyi-cold.json:
{"size": 26143942, "sha256": "1a622aec330dd4647dff906c6779037552669da871864877f60e985eedd9f8bf", "version": ["cast-tv 0.5.0", "Google Photos client: built in", "GoPro window: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "Window: edgechromium", "Cache: none"], "system": "Windows 11", "mode": "cold", "runs": [4.341491222381592, 4.200770378112793, 4.007715702056885, 3.7367427349090576, 4.0519304275512695], "median": 4.0519304275512695}
win-pyi-warm.json:
{"size": 26143942, "sha256": "1a622aec330dd4647dff906c6779037552669da871864877f60e985eedd9f8bf", "version": ["cast-tv 0.5.0", "Google Photos client: built in", "GoPro window: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "Window: edgechromium", "Cache: none"], "system": "Windows 11", "mode": "warm", "runs": [3.8308188915252686, 3.9477617740631104, 4.13898491859436, 3.7803218364715576, 4.197201251983643], "median": 3.9477617740631104}
win-nuitka-watched.json:
{"size": 18300416, "sha256": "7d044dfdffda52e52d3912c2f4f581f909ce47d0a1662366e6a20cdefaeeda99", "version": ["cast-tv 0.5.0", "Google Photos client: built in", "GoPro window: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "Window: edgechromium", "Cache: C:\\Users\\pmill\\AppData\\Local\\cast-tv\\0.5.0-gh44630376210.1"], "system": "Windows 11", "mode": "warm", "runs": [2.97684907913208], "median": 2.97684907913208}
```

## Linux: our undumpable processes (2026-11-20)

The Fedora desktop (Fedora 45, KDE Plasma, systemd 262). The first Phase 5 command on the Linux
files of run 44630376210 refused before any start, and so did the other three:

```
refused: the process list is incomplete (process 3535 is ours but its executable cannot be read); close cast-tv and try again
```

Process 3535 is `systemd --user` (UID 1000, `CapEff 0000000800000000`). Linux refuses
`readlink /proc/<pid>/exe` for a process that is not dumpable, even to its owner. Seven of ours
refused: `systemd --user`, `(sd-pam)`, `kwin_wayland` (`CapEff 0000000000800000`),
`polkit-kde-authentication-agent-1`, two `ssh-agent` (capabilities zero; they make themselves
undumpable) and a zombie `zypak-sandbox` of the Bitwarden Flatpak. So every Linux listing on this
desktop was incomplete: `startup_time.py` could not measure, and Phase 3's pruning would never
have removed anything.

Claude started the Nuitka file of run 44630376210 for 8 s and listed the processes. All six of
cast-tv's processes had a readable `exe`: the onefile starter in `~/Downloads/...`, and
`cast-tv-linux-x64-nuitka.bin` and four `QtWebEngineProcess` in
`~/.cache/cast-tv/0.5.0-gh44630376210.1/`. Only the seven listed above refused.

The owner decided (2026-11-20, "tak") to use the same rule as on Windows: a refused `exe` counts as
not ours. cast-tv never makes itself undumpable. Any other read error is still incomplete. After
the change, `running_images()` on this desktop listed 120 processes.

