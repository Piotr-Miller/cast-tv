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
