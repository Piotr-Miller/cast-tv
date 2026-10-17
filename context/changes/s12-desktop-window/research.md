# Research: s12-desktop-window

2026-10-15. No codebase research was run for this change; the blocking question was external.
Spikes below.

## Spike: does pywebview, bundled into the PyInstaller onefile, open cast-tv's /ui/ in a native window on Linux and Windows 11 with nothing installed beyond what the OS ships? (2026-10-15, 22:40)

Ran on the owner's Fedora 44 Workstation (GNOME, Wayland, glibc 2.43, Python 3.14.8), with
pywebview 6.2.1 and PyInstaller 6.22.3. There were two builds: one native, and one in an
`ubuntu:22.04` container that mirrors `release.yml`'s Linux job. Each was run on the desktop and
in podman containers of five distributions, with the window drawn through the host's Wayland
socket. The question was agreed as "Linux and Windows 11". During the run the owner widened
Linux from "Fedora" to "the Linux family" and added macOS as a nice-to-have (no Mac is
available).

**What the previous source said.**

- `context/archive/2026-09-07-cloud-source-ui/change.md:187-188` — "It would require a desktop
  app with an embedded webview - which costs separate Linux and Windows builds and gives up
  phone access" (updated 2026-09-20).
- `context/changes/s13-gopro-auth/plan.md:131-132` — "**no embedded webview / pywebview** (a
  dependency and two platform runtimes; revisit only if S-12 makes an embedded window a product
  requirement)" (last changed 2026-10-12).

Neither claim was tested. This spike confirms "two platform runtimes", and adds that on Linux the
runtime cannot be bundled: it has to come from the host. "Separate Linux and Windows builds" is
no longer a cost of the webview, because `release.yml` already builds both. "Gives up phone
access" is a design claim, not a vendor fact, and is not settled here.

**Documentary half.**

- **Linux needs a toolkit chosen explicitly, and its system libraries** — "On Linux you have to
  explicitly choose between QT and GTK." "PyGObject is used with GTK. To install dependencies on
  Ubuntu, use `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1`"
  "Note that WebKit2 version 2.22 or greater is required."
  (https://pywebview.flowrl.com/guide/installation.html, read 2026-10-15; the page is stamped
  "Last Updated: 1/8/25")
- **Freezing guidance stops at "use pyinstaller"** — "Windows / Linux Use pyinstaller." It gives
  `pyinstaller main.py --add-data index.html:. --onefile` and one Linux caveat about a missing
  `libpython3.x.so`. **The page says nothing about bundling GTK, WebKit2GTK or their typelibs.**
  (https://pywebview.flowrl.com/guide/freezing.html, read 2026-10-15)
- **No hook collects WebKit2GTK** — pywebview's own hook
  (`webview/__pyinstaller/hook-webview.py`, master, last changed 2025-10-21) collects files only
  `if is_win`, plus its `js` data. PyInstaller and pyinstaller-hooks-contrib have no
  `hook-gi.repository.WebKit2*` (full repository trees listed through the GitHub API, read
  2026-10-15). PyInstaller's gi hooks are documented for "freezing Gtk3-based applications on
  linux" and collect "themes, icons, translations"
  (https://pyinstaller.org/en/stable/hooks-config.html, read 2026-10-15).
- **The frozen app looks only inside the bundle for typelibs** — PyInstaller's runtime hook sets
  `os.environ['GI_TYPELIB_PATH'] = os.path.join(sys._MEIPASS, 'gi_typelibs')`
  (https://raw.githubusercontent.com/pyinstaller/pyinstaller/develop/PyInstaller/hooks/rthooks/pyi_rth_gi.py,
  read 2026-10-15).
- **Does the host ship WebKit2GTK 4.1 by default?**
  - **Ubuntu 24.04 Desktop: yes.** Its ISO manifest lists `gir1.2-webkit2-4.1:amd64
    2.52.6-0ubuntu0.24.04.1` and `libwebkit2gtk-4.1-0:amd64 2.52.6-0ubuntu0.24.04.1`
    (https://releases.ubuntu.com/24.04/ubuntu-24.04.5.1-desktop-amd64.manifest, read 2026-10-15).
  - **Ubuntu 22.04 Desktop: only 4.0.** Its manifest lists `gir1.2-webkit2-4.0` and
    `libwebkit2gtk-4.0-37` and no 4.1
    (https://releases.ubuntu.com/22.04/ubuntu-22.04.5-desktop-amd64.manifest, read 2026-10-15).
    pywebview falls back to 4.0 (`webview/platforms/gtk.py:50-55`, master).
  - **Fedora 44 Workstation: yes, as a dependency.** Observed locally, not documented:
    `gnome-shell` requires `libecal-2.0.so.3`, and `evolution-data-server` requires
    `libwebkit2gtk-4.1.so.0()(64bit)` (`dnf repoquery --whatrequires`, 2026-10-15).
- **Windows 11 ships WebView2** — "The Evergreen WebView2 Runtime will be included as part of
  the Windows 11 operating system."
  (https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution, page updated
  2026-10-02, read 2026-10-15). pywebview's Windows renderer `edgechromium` needs "> .NET
  Framework 4.6.2 and Edge Runtime installed"
  (https://pywebview.flowrl.com/guide/web_engine.html, read 2026-10-15). ".NET Framework 4.8 was
  originally included with Windows 11. Starting with Windows 11 22H2 (released September 2022),
  .NET Framework 4.8.1 is included."
  (https://learn.microsoft.com/en-us/dotnet/framework/install/on-windows-11, read 2026-10-15)
- **macOS uses the system WebKit and py2app** — the engine table lists macOS as
  "WebKit.WKWebView (bundled with OS)", and freezing says "macOS Use py2app."
  (web_engine.html and freezing.html above, read 2026-10-15). The pages do not say whether
  PyInstaller works on macOS.
- **Is pywebview current in 2026?**
  - Releases 6.0 (2025-08-08), 6.1 (2025-10-21), 6.2 (2026-04-13) and 6.2.1 (2026-04-15)
    (https://pypi.org/pypi/pywebview/json, read 2026-10-15).
  - Last commit 2026-10-15T12:39Z, 6117 stars (api.github.com/repos/r0x0r/pywebview, read
    2026-10-15).
  - 1,368,992 downloads in the last month (https://pypistats.org/api/packages/pywebview/recent,
    read 2026-10-15).
  - PyPI classifiers stop at Python 3.13. Yet it ran under 3.14.8 here.

**Empirical half (Linux). Windows and macOS pending: Windows needs a run on the Windows 11
laptop, macOS needs a Mac.**

The probe, `probe.py`, has the cast-tv shape: one process, a `ThreadingHTTPServer` on a thread
serving a copy of `castlib/ui/` at `/ui/`, and a pywebview window on that URL. A run passes only
if the page rendered and its JavaScript ran: `document.title == "cast-tv"` and
`typeof window.Alpine == "object"` three seconds after the window's `loaded` event.

```
python3 -m venv --system-site-packages venv-fedora      # Fedora's python3-gobject 3.56.3
venv-fedora/bin/pip install pywebview==6.2.1 pyinstaller==6.22.3
venv-fedora/bin/python probe.py
venv-fedora/bin/pyinstaller --noconfirm --onefile --add-data ui:ui --name probe-fedora probe.py
# CI-shaped build, in a container:
podman run --rm ... docker.io/library/ubuntu:22.04 bash build-ubuntu.sh
#   apt-get install python3 python3-venv python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 binutils
#   python3 -m venv --system-site-packages /v; /v/bin/pip install pywebview==6.2.1 pyinstaller==6.22.3
#   /v/bin/pyinstaller --noconfirm --onefile --add-data /work/app/ui:ui --name probe-ubuntu2204 probe.py
# each binary, per distribution, on the bare image and on the image plus WebKitGTK 4.1:
podman run --rm --security-opt label=disable -e XDG_RUNTIME_DIR=/tmp/xdg -e WAYLAND_DISPLAY=$WAYLAND_DISPLAY \
  -e GDK_BACKEND=wayland -v $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:/tmp/xdg/$WAYLAND_DISPLAY -v <binary>:/probe:ro <image> /probe
```

- **Unfrozen, on the Fedora desktop: passes.** Run in 3.9 s, backend `webview.platforms.gtk`,
  user agent `AppleWebKit/605.1.15`.
- **Native Fedora build on the Fedora desktop: passes.** The binary is 344,444,336 bytes, the
  build took 117 s, and the run took 12.2 s, most of it unpacking. 286,922 of its 295,203
  entries are `share/icons/*`, because no `hooksconfig` was set. **It contains no WebKit
  library and no `WebKit2` typelib.** WebKit2 came from the host, since the Fedora-built
  `libgirepository` also searches `/usr/lib64/girepository-1.0`.
- **CI-shaped build (`ubuntu:22.04`) on the Fedora desktop: fails.** The run ends with
  `ValueError: Namespace WebKit2 not available`, then "You must have either QT or GTK with
  Python extensions installed". It stays failed with `GI_TYPELIB_PATH=/usr/lib64/girepository-1.0`
  set, because the runtime hook overwrites that variable. The binary is 51,383,120 bytes, and
  it too contains no WebKit.
- **Matrix, 20 runs in containers.** Each cell names the build and the outcome:

  | Distribution (glibc) | Bare image | Image plus WebKitGTK 4.1 |
  | --- | --- | --- |
  | Fedora 44 (2.43) | both fail: `Namespace WebKit2 not available` | Fedora build **passes**; Ubuntu build fails: `Namespace WebKit2 not available` |
  | openSUSE Tumbleweed | both fail: `Namespace WebKit2 not available` | Fedora build **passes**; Ubuntu build fails: `Namespace WebKit2 not available` |
  | Arch | both fail: `Namespace WebKit2 not available` | Fedora build fails: `undefined symbol: webkit_get_major_version`; Ubuntu build fails: bundled `libstdc++.so.6: version 'CXXABI_1.3.15' not found (required by /usr/lib/libicui18n.so.78)` |
  | Ubuntu 24.04 (2.39) | Fedora build fails: `GLIBC_ABI_GNU2_TLS` not found; Ubuntu build fails: `Namespace WebKit2 not available` | Fedora build fails: `GLIBC_ABI_GNU2_TLS` not found; Ubuntu build fails: `undefined symbol: webkit_get_major_version` |
  | Debian 13 (2.41) | Fedora build fails: `GLIBC_2.43` not found; Ubuntu build fails: `Namespace WebKit2 not available` | Fedora build fails: `GLIBC_2.43` not found; Ubuntu build fails: bundled `libstdc++` `CXXABI_1.3.15` not found (required by `libicui18n.so.76`) |

  The CI-shaped build passed on 0 of 5 distributions, even with WebKitGTK 4.1 installed. The
  Fedora build passed only on the RPM distributions (Fedora, Tumbleweed), and only with
  WebKitGTK present. Its glibc 2.43 floor shuts out Ubuntu 24.04 and Debian 13.

**Not yet checked:**

- **Windows 11, empirically.** The documentary half says WebView2 and .NET 4.8+ ship with the
  OS. No build was run.
- **macOS, at all beyond the docs.** No Mac. Whether PyInstaller (rather than py2app) produces
  a working app is not documented.
- **Why the Arch and Ubuntu 24.04 runs hit `undefined symbol`.** gi could not load
  `libwebkit2gtk-4.1` beside the bundled libraries. This was not diagnosed.
- **Whether anything other than onefile-with-bundled-GTK works on Linux**, for example
  excluding the gi libraries from the bundle so the host's are used, or the Qt backend
  (`pywebview[qt]`, PySide6/QtWebEngine bundled). Neither was tried.
- **Real desktops other than Fedora.** The four other distributions ran as root in containers,
  without D-Bus or a session, through the Fedora compositor. A desktop install could differ.
- **Default WebKitGTK on KDE spins, Debian, Arch, openSUSE and Mint desktops.** Only Ubuntu
  (manifests) and Fedora Workstation (dependency chain) were checked.
- **The owner's added constraint**, current and widely used frameworks in 2026, and **its
  alternatives** (for example Tauri, Electron, Qt WebEngine) are a separate question. Only
  pywebview's own freshness is recorded above.
- **The real cast-tv server in-process.** The probe serves the UI files statically, with no
  `/api/*` routes, and does not handle closing the window.

**What this settles:**

- **Windows 11:** pywebview's runtime ships with the OS (documented). An empirical run is still
  pending.
- **Linux:** "bundled, nothing installed beyond what the OS ships" is refuted for the release as
  it is built today. A PyInstaller onefile does not carry WebKitGTK. The CI-shaped binary
  failed on every tested distribution. A native build works only on a distribution family close
  to the build host, with WebKitGTK present.
- **What it unblocks:** the replace-vs-wrap and toolkit choice for `/rune-frame`. Linux delivery
  is now one of the dimensions of that choice, not an assumption.

## Spike: which candidate that is current and widely used in 2026 shows cast-tv's existing /ui/ in a native window on Windows 11 and on mainstream Linux distributions, from one artifact per OS, with nothing installed? (2026-10-15, 23:09)

Same machine and container matrix as the spike above. Linux builds were made the way
`release.yml` makes them (`ubuntu:22.04`, Python 3.12.15 via uv, PyInstaller 6.22.3), then run
on the Fedora 44 desktop and in Fedora 44, Tumbleweed, Arch, Ubuntu 24.04 and Debian 13
containers through the host's Wayland socket. macOS is covered by documentation only.

**Candidates.** The owner chose them on 2026-10-15:

- PySide6 + Qt WebEngine, with **pywebview's Qt backend** as a variant;
- a Chromium-family browser in `--app` mode, with an **installed PWA** as a variant;
- Tauri 2;
- Electron;
- Flatpak with the GNOME runtime (documentation only).

**Skipped, by the owner's call, one line each:**

- **Wails** uses the same WebKitGTK on Linux as Tauri ("A Wails application is a standard Go
  application, with a webkit frontend", https://wails.io/docs/howdoesitwork; Linux "requires…
  libgtk3 and libwebkit", https://wails.io/docs/gettingstarted/installation, both read
  2026-10-15). It has 36,566 GitHub stars against Tauri's 111,929.
- **Neutralinojs** has the same Linux engine ("uses the existing web browser library in the
  operating system (e.g., gtk-webkit2 on Linux)", https://neutralino.js.org/docs/, read
  2026-10-15). It has 8,667 stars.
- **NW.js** is the Electron class ("an app runtime based on `Chromium` and `node.js`",
  https://raw.githubusercontent.com/nwjs/nw.js/master/README.md, read 2026-10-15). It has
  41,134 stars against Electron's 123,338.
- **cefpython3** is not current: its last release is 66.1, 2021-02-16, with classifiers up to
  Python 3.9 (https://pypi.org/pypi/cefpython3/json, read 2026-10-15).

Star counts come from https://api.github.com/repos/<repo>, read 2026-10-15.

**What the previous source said.**

- The spike above, `research.md:150-152`: alternatives were "a separate question", not checked.
- The owner, in session, from memory: "Firefox nie ma trybu --app (o ile pamiętam, funkcja SSB
  zniknęła w wersji 86)". This is confirmed below.
- No other prior claim about these candidates was found in `context/`.

**Documentary half.**

- **PySide6 / Qt WebEngine**
  - **Current:** 6.12.0 was uploaded 2026-10-08, with `requires_python` ">=3.10,<3.16" and a
    `manylinux_2_34` wheel (https://pypi.org/pypi/PySide6/json). Downloads were 2,819,778 in
    the last month (https://pypistats.org/api/packages/pyside6/recent). Release table: "Qt 6.12
    Qt 6.12.0 2031-09-30" (https://doc.qt.io/qt-6/qt-releases.html). All read 2026-10-15.
  - **Platforms:** "Linux binary packages are linked against glibc 2.34." Tested distributions
    include Ubuntu 22.04 and 24.04, Debian 12 and openSUSE 16.0, plus "macOS 14.4 or higher".
    Also "Qt 6.12 will be the last version to support Windows 10."
    (https://doc.qt.io/qt-6/supported-platforms.html, read 2026-10-15)
  - **What must be shipped:** "the Qt WebEngine Process executable be deployed alongside your
    application", plus `.pak` files, `icudtl.dat` and locales. On Windows, "the Visual C++
    Redistributable version 14.28 or higher is needed"
    (https://doc.qt.io/qt-6/qtwebengine-deploying.html, read 2026-10-15).
  - **Sandbox:** on Debian-derived distributions the user-namespace sandbox "is off by default",
    and "AppArmor can further restrict anonymous namespace usage"
    (https://doc.qt.io/qt-6/qtwebengine-platform-notes.html, read 2026-10-15).
  - **PyInstaller:** has `hook-PySide6.QtWebEngineCore.py` ("Include helper process executable,
    translations, and resources.", PyInstaller `develop`, read 2026-10-15).
- **pywebview's Qt backend:** `pywebview[qt]` installs **PyQt6**, not PySide6:
  `qt = ["QtPy", "PyQt6", "PyQt6-WebEngine"]`, `pyside6 = ["QtPy", "PySide6"]`
  (https://raw.githubusercontent.com/r0x0r/pywebview/master/pyproject.toml, read 2026-10-15).
  On Windows pywebview's default renderer stays WebView2 (spike above).
- **Chromium `--app`**
  - **The switch is documented in Chromium's source:** "Specifies that the associated value
    should be launched in "application" mode."
    (https://raw.githubusercontent.com/chromium/chromium/main/chrome/common/chrome_switches.h,
    read 2026-10-15)
  - **Windows 11 carries Edge,** but "the ability to uninstall … Microsoft Edge, in the EEA"
    exists
    (https://blogs.windows.com/windows-insider/2023/11/16/previewing-changes-in-windows-to-comply-with-the-digital-markets-act-in-the-european-economic-area/,
    read 2026-10-15).
  - **Linux defaults are Firefox:**
    - The Ubuntu 24.04 desktop manifest has `firefox` (snap) and no line containing "chrom"
      (https://releases.ubuntu.com/24.04/ubuntu-24.04.5.1-desktop-amd64.manifest).
    - Debian trixie `task-desktop` lists "firefox … or firefox-esr"
      (https://packages.debian.org/trixie/task-desktop, bot challenge, read with WebFetch).
    - Fedora Workstation's "firefox" group is mandatory (local `dnf` group metadata, not a web
      page).
    - All read 2026-10-15.
- **Firefox**
  - **SSB removed in Firefox 86:** Bugzilla 1682593, "Remove the SSB feature", target
    "86 Branch", resolved 2021-01-15 (https://bugzilla.mozilla.org/rest/bug/1682593).
  - **Web apps are Windows-only:** "On Windows, Firefox now supports running websites as web
    apps pinned directly to the taskbar."
    (https://www.firefox.com/en-US/firefox/143.0/releasenotes/). Release notes 144–158 mention
    no Linux or macOS support.
  - **Kiosk mode:** "--kiosk URL — Open URL full screen without user interface."
    (https://wiki.mozilla.org/Firefox/CommandLineOptions)
  - **No PWA install:** "Firefox does not support installing PWAs using a manifest file."
    (https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)
  - All read 2026-10-15.
- **Installed PWA**
  - **No service worker needed:** Chrome "removed the requirement to have a service worker that
    implements the fetch() method for installation from the menu, since version 108 on mobile
    and 112 on Desktop", though "the algorithm that displays the install prompt still requires
    the presence of a fetch() handler"
    (https://developer.chrome.com/blog/update-install-criteria).
  - **localhost counts as secure:** "localhost or 127.0.0.1 — with or without a port number"
    (MDN, above).
  - Both read 2026-10-15.
- **Tauri 2**
  - **Current:** stable v2.12.4 was published 2026-10-14 (GitHub releases API). Crates.io shows
    14,448,813 recent downloads.
  - **Webviews:** WebView2 "comes preinstalled on Windows 11"; Linux uses "webkit2gtk"
    (https://v2.tauri.app/reference/webview-versions/).
  - **AppImage:** "bundles all dependencies", and the file "grows from the 2-6 MB range to
    70+ MB". The docs warn "you must build your Tauri application using the oldest base system
    you intend to support" (https://v2.tauri.app/distribute/appimage/).
  - **Sidecar:** "Common use cases are Python CLI applications or API servers bundled using
    pyinstaller" (https://v2.tauri.app/develop/sidecar/).
  - All read 2026-10-15.
- **Electron**
  - **Current:** stable v44.7.2 was published 2026-10-14. "Electron's cadence between major
    version releases is 8 weeks long"
    (https://www.electronjs.org/docs/latest/tutorial/electron-timelines).
  - **Bundles its engine:** "By embedding Chromium and Node.js into its binary"
    (https://www.electronjs.org/docs/latest/).
  - **AppImage:** electron-builder's AppImage uses a "Static runtime (no host FUSE needed)" and
    runs "on modern distributions (Arch, Fedora, Ubuntu 24.04+) without installing FUSE"
    (https://www.electron.build/docs/appimage).
  - **Python backend:** the documentation does not say.
  - All read 2026-10-15.
- **Flatpak, GNOME runtime**
  - **WebKitGTK is in the runtime:** the GNOME 51 runtime's `elements/sdk-platform.bst` lists
    `sdk/webkit2gtk-4.1.bst` (https://gitlab.gnome.org/GNOME/gnome-build-meta, branch
    `gnome-51`). This is source, not prose.
  - **Preinstalled on Fedora, Mint and Pop!_OS:** Fedora has it "installed by default on Fedora
    Workstation"; Mint has it "built into Linux Mint 18.3 and newer"; Pop!_OS has it "built
    into Pop!_OS 20.04 and newer".
  - **Not preinstalled on Debian, Arch, openSUSE or Ubuntu:** Debian, Arch and openSUSE need an
    install command (https://flathub.org/en/setup/<distro>). Ubuntu: "will no longer be
    installed by default in the next release due in April 2023"
    (https://discourse.ubuntu.com/t/ubuntu-flavor-packaging-defaults/34061).
  - **Runtimes are not bundled:** "single-file bundles don't include dependencies"
    (https://docs.flatpak.org/en/latest/single-file-bundles.html).
  - **LAN listening and SSDP inside the sandbox:** the documentation says only "--share=network
    - Access the network".
  - All read 2026-10-15.

**Empirical half.** Run for Qt WebEngine and Chromium `--app`/PWA. Tauri and Electron are
pending: no build was made.

```
# Qt: ubuntu:22.04 + runtime libs a GitHub runner carries (libgl1 libegl1 libxkbcommon0 libnss3 libwayland-* ...)
uv venv -p 3.12 /v && uv pip install PySide6==6.12.0 "pywebview[pyside6]==6.2.1" pyinstaller==6.22.3
pyinstaller --onefile --add-data ui:ui --name probe_pwq-ubuntu2204 probe_pwq.py   # probe.py with PYWEBVIEW_GUI=qt
pyinstaller --onefile --add-data ui:ui --name probe_qt-ubuntu2204 probe_qt.py     # bare QWebEngineView
# run per distro, on a "desktop baseline" image (Mesa GL/EGL/DRI, DejaVu, xkbcommon, libwayland-*, libgbm), as the invoking user:
podman run --rm --userns=keep-id --user $(id -u):$(id -g) --device /dev/dri -e WAYLAND_DISPLAY=... \
  [-e QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu -e QT_QUICK_BACKEND=software] <image> /probe
# Chromium --app and PWA: python3 -m http.server serving ui/ (plain, and with manifest.json + 192/512 icons), then
google-chrome --user-data-dir=<tmp> --remote-debugging-port=9333 --app=http://127.0.0.1:8811/ui/
node cdp.mjs 9333   # Runtime.evaluate, Page.getAppManifest, Page.getInstallabilityErrors
firefox --profile <tmp> --no-remote --app=http://127.0.0.1:8812/ui/          # control: --new-window <url>
```

- **Qt WebEngine via pywebview, one Linux artifact (232,397,952 bytes, built in 101 s):**
  - **GPU disabled: passes on all six.** Fedora 44 desktop and the Fedora 44, Tumbleweed, Arch,
    Ubuntu 24.04 and Debian 13 containers all report `'ok': True`, the title `cast-tv`, Alpine
    an `object`, user agent `QtWebEngine/6.140.0 Chrome/140.0.0.0`, in 3.4-3.6 s.
  - **GPU on: fails on all six.** The desktop aborts with signal 6 after `eglInitialize: Failed
    to get system egl display` and `libstdc++.so.6: version 'CXXABI_1.3.15' not found (required
    by /usr/lib64/dri/iHD_drv_video.so)`. The bundled libraries include `libgbm.so.1` and
    `libstdc++.so.6` from Ubuntu 22.04. Every container fails with `QRhiGles2: Failed to create
    temporary context`.
  - **What the target must provide:** on the first pass the bare images failed with `libGL.so.1`
    missing, and the thin baselines with `libwayland-server.so.0` missing. Neither library is
    bundled, and both are present on the desktop.
- **Qt WebEngine via bare PySide6 (230,799,416 bytes):** same engine, same result. On the
  desktop with GPU disabled and on Arch, the page returned `["cast-tv","object",…]`. The probe
  then failed its own bookkeeping, `ModuleNotFoundError("No module named 'json'")`: a probe
  defect, since `json` was imported via `__import__` and not collected. With GPU on, the
  desktop aborts as above. The other containers were run on the thin baseline only
  (`libwayland-server.so.0` missing) and were not repeated.
- **Chrome 155 `--app` on the Fedora desktop: passes.**
  - Title `cast-tv`, Alpine an `object`, and `matchMedia("(display-mode: standalone)")` true,
    3.7 s after launch.
  - Without a manifest, `installabilityErrors` is `no-manifest`. **With the manifest and two
    icons, and no service worker, `installabilityErrors` is `[]`.**
- **Firefox 157.0.1 with `--app=<url>`: does not open the page.** The server received 0 requests
  in 10 s, while the process stayed alive. The control run (`--new-window <url>`) made 7
  requests: `/ui/`, `app.js`, `alpine.min.js`, `style.css`, `/api/status`, `favicon.ico`.

**Not yet checked:**

- **Windows 11, empirically, for every candidate:** Edge `--app`, pywebview/WebView2,
  PySide6, Tauri, Electron. Also whether a PyInstaller-bundled PySide6 carries the VC++ runtime
  that Qt's deploy page asks for.
- **Tauri and Electron, empirically.** In particular, whether a Tauri AppImage really carries
  WebKitGTK across the five distributions; its docs say "bundles all dependencies", but the
  spike above saw a bundled GTK fail.
- **Why the bundled Qt fails with the GPU on, and whether removing `libgbm`/`libstdc++` from
  the bundle, or a software fallback inside the app, fixes it.** Not tried. Disabling the GPU
  was set from outside, through an environment variable.
- **Qt WebEngine's sandbox under Ubuntu 24.04's AppArmor user-namespace restriction.** The
  containers ran on Fedora's kernel, so that restriction was not in force. No real Ubuntu
  desktop was tested.
- **PyQt6's licence** (`pywebview[qt]`) against cast-tv's "All rights reserved" licence. The
  build used `pywebview[pyside6]` (PySide6 is "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only"
  per PyPI). PyQt6's PyPI metadata has no licence field.
- **The macOS halves** of all candidates beyond the quotes above. No Mac.
- **Default browsers** on Arch, openSUSE and Mint, and whether a Flatpak can listen on a LAN
  port and do SSDP.
- **Edge's own PWA install criteria**, and what an installed localhost PWA shows when cast-tv is
  not running.
- **The Mozilla kiosk support page:** browser read pending,
  https://support.mozilla.org/en-US/kb/firefox-enterprise-kiosk-mode, which returns a client
  challenge.

**What this settles:**

- **Linux:** against the criterion, the only candidate that opened the UI from one CI-built
  artifact on all five distributions is **Qt WebEngine** (pywebview's Qt backend or bare
  PySide6), and only with the GPU disabled. It is current: PySide6 6.12.0 is from 2026-10-08,
  and Qt 6.12 is supported until 2031.
- **Chromium `--app` / PWA:** meets the criterion on Windows 11, through Edge, by
  documentation; outside the EEA Edge cannot be uninstalled. It does not meet it on Linux,
  whose defaults are Firefox. Firefox has no app mode on Linux, ignores `--app`, and cannot
  install a PWA.
- **Flatpak:** fails "nothing installed" on Ubuntu, Debian, Arch and openSUSE.
- **Tauri and Electron:** stay open until built.
- **What it unblocks:** `/rune-frame` now has measured inputs for the toolkit and
  Linux-delivery dimensions.

## Spike: the frame's discriminator runs, Qt bundling, Tauri/Electron AppImages, a real Ubuntu 24.04 (2026-10-16, 18:50)

These are the experiments listed in `frame.md`'s Discriminator Check. The owner chose to run
all four, with one correction for the Qt run: "najpierw wynik bazowy, potem usunięcie libgbm i
libstdc++ osobno, a na końcu obu razem" (first the baseline, then libgbm and libstdc++ removed
one at a time, and only then both together).

Builds were made in `ubuntu:22.04`, as `release.yml` does. They ran on three kinds of target:

- the Fedora 44 desktop (GNOME, Wayland, Intel iGPU, FUSE 3 only);
- the five-distribution podman matrix from the earlier spikes;
- an **Ubuntu 24.04.5 VM**: the cloud image plus `ubuntu-desktop-minimal`, kernel
  6.8.0-142, `kernel.apparmor_restrict_unprivileged_userns = 1`, no `libfuse2t64`. Runs there
  used Xvfb, with no GPU.

Windows is pending: the owner runs it on the laptop.

**What the previous source said.** `frame.md`, Discriminator Check (2026-10-16): all four rows
were open, and the Tauri/Electron row "conflates" the AppImage runtime and the bundled engine.
The documentation half of the second spike quoted electron-builder's AppImage page: a "Static
runtime (no host FUSE needed) Default in v27".

**Documentary half.** On npm, `electron-builder` dist-tags are `latest` 26.15.3 (2026-06-09)
and `next` 27.0.0-alpha.10 (2026-10-08) (https://registry.npmjs.org/electron-builder, read
2026-10-16). **The v27 static runtime the second spike quoted is not yet in a stable release.**

**Empirical half.**

```
# Qt: the pywebview + Qt probe built four times from one spec; DROP removes bundled libraries by basename
DROP=                              NAME=pwq-base      pyinstaller probe_pwq_var.spec
DROP=libgbm.so.1                   NAME=pwq-nogbm     pyinstaller probe_pwq_var.spec
DROP=libstdc++.so.6                NAME=pwq-nostdcxx  pyinstaller probe_pwq_var.spec
DROP=libgbm.so.1,libstdc++.so.6    NAME=pwq-noboth    pyinstaller probe_pwq_var.spec
# Tauri 2 (tauri.conf.json window url http://127.0.0.1:8899/ui/), Electron 44 (loadURL of the same):
npx tauri build --bundles appimage
npx electron-builder --linux AppImage        # 26.15.3, then again with 27.0.0-alpha.10
# AppImage pass criterion: a local server on 8899 sees /ui/ AND /api/status (app.js init -> refresh()),
# with no request in the 3 s before the start and none in the 3 s after the kill; app profiles wiped first
python3 -I appimage_probe.py <log> [--container NAME] <command>
```

- **Qt, the library split.** The bundles are 232,398,728 / 232,369,680 / 231,630,576 /
  231,601,928 bytes.

  | Variant | Fedora desktop, GPU on | 5 containers, GPU on | 5 containers, GPU off | Ubuntu 24.04 VM |
  | --- | --- | --- | --- | --- |
  | base | abort (134) | 0/5 | 5/5 | abort (134) |
  | no `libgbm` | abort (134) | 0/5 | 5/5 | — |
  | no `libstdc++` | **pass**, with `GBM: Failed to initialize GBM device` | 3/5 (Ubuntu 24.04 and Debian 13: `did not find extension DRI_Mesa version 1`, `failed to bind extensions`) | 5/5 | — |
  | no `libgbm`, no `libstdc++` | **pass, no GBM warnings** | **5/5** | 5/5 | **pass** |

  - **The bundled `libstdc++` is what aborts.** The abort is `CXXABI_1.3.15` required by the
    host's `iHD_drv_video.so`, against the older bundled `libstdc++`.
  - **The bundled `libgbm` breaks GBM** on the host. It searches `/usr/lib/x86_64-linux-gnu/dri`,
    then `/usr/lib/dri`, which on Fedora holds 32-bit drivers ("wrong ELF class: ELFCLASS32").
    It fails outright on Ubuntu 24.04 and Debian 13.
  - **Only removing both passes everywhere tested.**
- **Qt sandbox on Ubuntu 24.04 with the AppArmor restriction.** `pwq-noboth` passes.
  - `dmesg`: `apparmor="DENIED" operation="capable" … profile="unprivileged_userns" …
    comm="pwq-noboth" capability=21 capname="sys_admin"`.
  - The renderer (`--type=renderer`) runs in the host's user namespace (`user:[4026531837]`,
    the same as the shell) with `Seccomp: 2` and `NoNewPrivs: 1`. **The namespace layer is
    denied; the seccomp-bpf layer is active.**
- **Tauri 2.12.4 AppImage**: 81,263,096 bytes, built in 316 s.
  - **Contents:** it carries `usr/lib/libwebkit2gtk-4.1.so.0`, `libjavascriptcoregtk-4.1.so.0`,
    `libgtk-3.so.0` and `WebKitWebProcess` (170 shared objects, 254 MB extracted).
  - **Real desktops:** the Fedora desktop passes in 1.2 s, with FUSE 3 only. The Ubuntu 24.04
    VM passes in 32.8 s (software rendering under Xvfb).
  - **WebKitGTK images:** 5/5 pass, in 1.4-3.4 s.
  - **Images without WebKitGTK and GTK:** 0/15 across three widening baselines. Each stops on a
    host library the AppImage leaves out: `libfontconfig.so.1`, then `libfribidi.so.0`, then a
    different one per distribution (`libcom_err.so.2` on Tumbleweed, `libgpg-error.so.0` on
    Debian 13, `libGLESv2.so.2` on Ubuntu 24.04). `ldd` over all 170 bundled objects on Ubuntu
    24.04 found only `libfribidi.so.0` missing. The rest are `dlopen`ed at run time. Stopped
    there by time-box.
- **Electron 44.8.0, electron-builder 26.15.3 (npm `latest`)**: 125,392,228 bytes, built in 58 s.
  - **The runtime needs FUSE 2.** It fails on the Fedora desktop and on the Ubuntu 24.04 VM with
    `dlopen(): error loading libfuse.so.2` / "AppImages require FUSE to run."
  - **The engine itself works:** with `APPIMAGE_EXTRACT_AND_RUN=1` it passes on the Fedora
    desktop in 1.6 s.
  - **Containers:** 0/10. Host libraries are missing (`libnspr4.so`), and with GTK present
    "The platform failed to initialize".
- **Electron 44.8.0, electron-builder 27.0.0-alpha.10**: 117,329,369 bytes, built in 42 s.
  - **Passes on both real desktops:** Fedora in 1.4 s, the Ubuntu 24.04 VM in 1.2 s. No FUSE 2
    is needed.
  - **On Ubuntu 24.04 it runs unsandboxed.** Its AppRun runs `unshare -Ur true`, which fails
    there ("write failed /proc/self/uid_map: Operation not permitted"), so it adds
    `--no-sandbox`. The renderer has `Seccomp: 0`.
  - **Containers:** 0/10, same host-library gaps.
- **A discarded run.** The first container run of the AppImage matrix reported false PASSes:
  `/api/status` polls from instances still running, alongside "error while loading shared
  libraries". Its logs are kept as `run1-contaminated`. The probe was hardened (3 s quiet before
  and after, `/ui/` required, the container force-removed) and every AppImage result above
  comes from the rerun. On the desktop, a stale HTTP cache in the apps' profiles also hid
  `/ui/`; the profiles were wiped before each run.

**Not yet checked:**

- **Windows 11, every candidate.** A kit is ready (`run_spike.py`: Edge `--app`, pywebview
  unfrozen and onefile, pywebview + PySide6 onefile); the owner runs it.
- **Qt `noboth` on a real Ubuntu desktop with a GPU.** The VM had none.
- **Whether a Tauri or Electron AppImage runs on a desktop install other than GNOME** (KDE,
  Xfce).
- **Whether removing `libstdc++` breaks cast-tv's own bundled code** (pillow-heif); only the
  probe was built that way.
- **Electron's Python sidecar wiring.** None of the AppImages ran a cast-tv server; the UI came
  from a server outside the app.

**What this settles:**

- **Qt WebEngine's GPU failure is a bundling artifact, not a property of Qt.** A onefile without
  the bundled `libgbm` and `libstdc++` rendered with the GPU on, on the Fedora desktop and all
  five containers, and rendered on Ubuntu 24.04. There the renderer runs with seccomp but
  without the user-namespace layer.
- **Tauri's AppImage does carry WebKitGTK**, and it passed on both real desktops.
- **Electron's AppImage passes on both real desktops only with the alpha electron-builder
  27.** On Ubuntu 24.04 that build runs with `--no-sandbox`.
- **Windows remains open for all candidates.**

## Spike: the Windows 11 laptop run of `spike-kit/run_spike.py` (2026-10-18, 01:36)

The last open row of `frame.md`'s Discriminator Check. Claude ran the kit on the owner's Windows
11 laptop (Windows 11 Pro 10.0.26300, AMD64, Python 3.14.5, Edge 155, VC++ runtime 14.51
installed). Packages: pywebview 6.2.1, PySide6 6.12.0, PyInstaller 6.22.3, pythonnet 3.2.1,
QtPy 2.4.3.

**Empirical half.**

- **Edge `--app` on `/ui/`: passes.** `/api/status` came 2.3 s after launch (1.9 s on the
  rerun). The requests were `/ui/`, `alpine.min.js`, `app.js`, `style.css`, `/api/status`,
  `/favicon.ico`.
- **pywebview unfrozen (WebView2, `gui=winforms`): passes.** Title `cast-tv`, Alpine an
  `object`, user agent `Edg/155.0.0.0`; 9.8 s for the whole probe, which sleeps 3 s after load.
  pythonnet installs and loads on Python 3.14.
- **pywebview onefile (WebView2): passes.** 12,836,800 bytes, built in 34 s. 9.9 s per run.
- **pywebview + PySide6 onefile (`gui=qt`): passes.** 227,218,128 bytes, built in 229 s with
  `--clean`. User agent `QtWebEngine/6.140.0 Chrome/140.0.0.0`. 22.8 s and 22.2 s wall time for
  two runs. The WebView2 exe needs 9.7 s, so about 13 s of the difference is the onefile
  unpacking about 200 MB.
- **The bundle carries the VC++ runtime.** Its `PKG-00.toc` lists `MSVCP140.dll`,
  `MSVCP140_1.dll` and `MSVCP140_2.dll` from the PySide6 and shiboken6 wheels, and
  `VCRUNTIME140.dll` and `VCRUNTIME140_1.dll`. The laptop also has the runtime installed, so
  this run does not show the exe working without it.
- **Two kit defects, found and fixed in this run.**
  - **The first `pip install` failed with `WinError 32`**: "The process cannot access the file
    because it is being used by another process", on a file pip had just unpacked
    (`_pyinstaller_hooks_contrib/.../hook-reportlab.lib.utils.py`, then
    `PyInstaller/hooks/hook-_ctypes.py`). The second try succeeded. The likely holder is the
    virus scanner; this was not checked. `run_spike.py` now retries up to three times.
  - **The first Qt build silently tested WebView2.** The kit installed `PySide6` without
    `pywebview[pyside6]`, so `qtpy` was missing. `webview.platforms.qt` raised
    `ModuleNotFoundError: No module named 'qtpy'`, and pywebview fell back to `winforms` with
    no error exit. That exe was 12,836,273 bytes, the size of the WebView2 one. A rebuild
    without `--clean` took 3 s and reused the cached analysis without Qt. The Linux runs
    installed the extra (line 312), so their Qt results stand. `run_spike.py` now installs
    `pywebview[pyside6]` and builds with `--clean`, and `probe_pwq.py` exits 1 unless the
    backend is `webview.platforms.qt`.
- **The probes were not rerun on a machine without the VC++ runtime** or on another Windows
  account.

**What this settles:**

- **On Windows, every Python candidate meets dimension 2 from one artifact with nothing
  installed beyond the OS:** Edge `--app`, and pywebview with WebView2, unfrozen and as a 12.8
  MB onefile. WebView2 is part of Windows 11, as Edge is.
- **Qt WebEngine also works on Windows, at 227 MB** and about 13 s more start-up per launch
  from the onefile unpacking.
- **A pywebview build must fail when its chosen backend is missing.** pywebview falls back
  quietly, so a test that checks only that a window rendered can pass on the wrong engine.

**Not yet checked:**

- **The Qt exe on a Windows install without the VC++ runtime.**
- **Tauri and Electron on Windows.** The kit does not include them.
- **SmartScreen and Defender on a downloaded, unsigned 12.8 MB or 227 MB exe.** All runs were
  local builds; nothing was downloaded.
