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

## Plan-review triage: verification environment (2026-10-18)

F6 follow-up: the global, pipx and spike interpreters lacked pytest/pyflakes. Created the
gitignored repository `.venv` with `python -m venv .venv`, then installed the core and test
extra with `.\.venv\Scripts\python.exe -m pip install -e ".[test]"` (exit 0). No window extra
was installed and no application source was changed. Commands below ran sequentially from
`C:\Source\cast-tv` using `.venv\Scripts\python.exe` as `python`, with Node on PATH.

Environment: Windows laptop, Python 3.14.5 (64-bit); pytest 9.1.1, pyflakes 4.0.3,
Pillow 13.0.0, pillow-heif 1.8.1, ifaddr 0.2.0, platformdirs 4.13.4. CI remains Python 3.12
on Windows and Linux; this local baseline is not the two-OS CI or native-window acceptance.

| Command | Exit | Observed result |
| --- | --- | --- |
| `python -m pyflakes castlib tests` | 0 | No findings |
| `python -m pyflakes castlib tests packaging` | 0 | No findings |
| `python -m pytest tests/test_cli.py` | 0 | 25 passed, 2 skipped |
| `python -m pytest tests/test_api.py` | 0 | 15 passed |
| `python -m pytest tests/test_ui.py` | 0 | 11 passed |
| `python -m pytest tests/test_ui.py::test_static_exact_match_only` | 0 | 1 passed |
| `python -m pytest tests/test_platform.py` | 0 | 25 passed |
| `python -m pytest tests/test_ui.py tests/test_api.py` | 0 | 26 passed |
| `python -m pytest` | 0 | 382 passed, 5 skipped in 86.83 s |

All nine commands completed. Eight match their historical planning exit 0; the full suite
improves from the recorded exit 1 to exit 0, with no reproduction of the earlier OneDrive
failure. CLI's two skips are explicitly Windows exclusions for child signal delivery and
POSIX SIGABRT/faulthandler. Baseline tests do not prove tests/features described for later
S-12 phases; all Progress rows remain pending. Raw local logs and command results are under
`.venv/s12-review-check-1.log` through `s12-review-check-9.log` and
`.venv/s12-review-results.json`; this table is the persistent evidence if that venv is removed.

## Phase 1 gate: the flaky OneDrive test (2026-10-18)

Windows laptop, `.venv` (Python 3.14.5, no `[window]` extra), Phase 1 working tree. Rows 1.1-1.5
exit 0 (`pyflakes castlib tests`; `test_window.py` 25 passed; `test_cli.py` 29 passed, 2 skipped;
`test_api.py` 19 passed; `test_ui.py` 13 passed). The full suite exited 1 twice, each time with
only `tests/test_onedrive.py::test_token_file_mode_0600` failing (`wait_for` on the stored
`account`, 5 s), 419 passed, 5 skipped. The same test alone: 1 of 3 passed on the Phase 1 tree;
on a clean `git worktree` of `HEAD` (404d0cf, castlib imported from the worktree) 2 of 4 passed.
It fails as often without this change, and Phase 1 touches no OneDrive code. With that one test
deselected the full suite is 419 passed, 5 skipped, exit 0. Not fixed here (plan, What We're NOT
Doing); CI on the PR (row 1.7) is the two-OS gate.

## Manual row 1.8 (2026-10-18)

Windows laptop (Windows 11 Pro 10.0.26300), a venv with `pip install -e ".[window]"`, commit
a33a8a0 (PR #61; on main as 1083431). The owner ran `cast-tv` in PowerShell and confirmed the
row as written: a window titled cast-tv opened on the UI, not a browser tab, and the console
printed the addresses. Reported in the session as "1.8 potwierdzone", then with the whole PowerShell log:

- Command: `python -m venv $env:TEMP\ctv-win`, then `pip install -e ".[window]"` and
  `cast-tv.exe` from that venv. Python 3.14 (cp314 wheels). The extra resolved to
  pywebview 6.2.1, pythonnet 3.2.1, clr_loader 0.3.1, bottle 0.13.4, proxy_tools 0.1.0 and
  typing_extensions 4.16.0. No PySide6 on Windows, as intended.
- Console: three addresses (`http://localhost:8895/ui/`, the Wi-Fi LAN address and a
  192.168.16.x virtual adapter), the firewall line, the window-mode hint "Close the window
  or press Ctrl+C to end it (playback stops on the TV too)", and the TV found by discovery
  ("TV: 83" OLED").
- On closing the window the console printed `Stopped.` and the PowerShell prompt returned.
  Nothing was playing, so this does not stand in for row 1.13 (X with a video playing).

Re-confirmed at ffa982c (`main`): d2dd0ca, the revision first accepted, left the history when
PR #61 was merged by rebase (`change.md` Notes). In the same venv the owner ran `cast-tv` in
PowerShell; "okno się otworzyło, 1.8 potwierdzone" ("the window opened, 1.8 confirmed").

## Manual rows 1.16 and 1.13 (2026-10-18)

Windows laptop (Windows 11 Pro 10.0.26300), the same venv as row 1.8 (`$env:TEMP\ctv-win`,
`pip install -e ".[window]"`), the checkout on `main`; the castlib tree is the same as 1083431.
The owner reported both rows as "1.16 potwierdzone, 1.13 tez" ("1.16 confirmed, 1.13 too") and
then confirmed them as written at ffa982c (`main`; it differs from 1083431 only in `AGENTS.md`
and `CLAUDE.md`):

- 1.16: from the phone, at `http://192.168.50.213:8895/ui/` (the laptop's Wi-Fi address), the UI
  worked as before and showed no Quit cast-tv control.
- 1.13: with a video playing on the TV (83" OLED), closing the cast-tv window with X stopped the
  TV within 5 s; PowerShell printed `Stopped.` and its prompt returned.

These are the owner's reports of what they saw; the agent did not observe the TV or the phone.

## Manual row 1.15 (2026-10-18)

Windows laptop, the same venv and revision as rows 1.16 and 1.13 (ffa982c). With the cast-tv
window open behind another window, the owner ran `cast-tv` again in a second PowerShell window
(the same venv) and reported "1.15 tez" ("1.15 too"), confirming the row as written: the cast-tv
window came to the front and the second command exited at once.
This is the owner's report; the agent did not see the screen.

## Manual rows 1.11 and 1.14, Windows part (2026-10-18)

Windows laptop, the same venv and revision as rows 1.16 and 1.13 (ffa982c). The owner was given
three steps and answered "potwierdzone" ("confirmed") to all of them:

- 1.11: `cast-tv --no-window` opened a browser tab at `http://127.0.0.1:8895/ui/`, not a window,
  with the Quit cast-tv control in the header; Ctrl+C in the PowerShell window ended it.
- 1.14, Ctrl+C: with a video playing from the cast-tv window, Ctrl+C in the PowerShell window
  running cast-tv stopped the TV and closed the window.
- 1.14, sign-out: with a video playing from the cast-tv window, Start → account → Sign out without
  closing cast-tv; after signing back in the TV had stopped playing and
  `Get-Process cast-tv -ErrorAction SilentlyContinue` printed nothing. The agent's own check after
  the owner resumed the session agreed: `Get-Process cast-tv` found no process.

These are the owner's reports, apart from the last `Get-Process` check. Row 1.14 stays open: its
Fedora part (`kill <pid>` from another terminal) is still to be done.

## Manual rows 1.8, 1.11, 1.13 and 1.15 again, after the review fixes (2026-10-18)

The impl-review fixes F1-F3 (PR #66, `main` 104dd71) changed `castlib/cli.py` and
`castlib/window.py`, which reopened these rows. Windows laptop, the same venv as before
(`$env:TEMP\ctv-win`, `pip install -e ".[window]"`), the checkout at 104dd71. The owner was given
the steps for 1.8, 1.13, 1.15, 1.11 and both Windows parts of 1.14, answered "Wszystko dziala"
("everything works") at about 23:26, and then confirmed the rows at 104dd71:

- 1.8: a window titled cast-tv opened on the UI and PowerShell printed the addresses.
- 1.13: with a video playing from the window, X stopped the TV within 5 s; PowerShell printed
  `Stopped.` and its prompt returned.
- 1.15: with the window covered, `cast-tv` in a second PowerShell window brought it to the front
  and that command exited at once.
- 1.11: `cast-tv --no-window` opened the tab at `http://127.0.0.1:8895/ui/` with Quit cast-tv in
  the header; Ctrl+C ended it.
- 1.14, Ctrl+C: with a video playing from the window, Ctrl+C in PowerShell stopped the TV and
  closed the window.

These are the owner's reports; the agent did not see the TV or the screen. 1.14 stays open (its
Fedora `kill` part). The sign-out part at 104dd71 is not recorded yet: the owner said it was done
too, but `explorer.exe` on the laptop had started at 22:37:04, before the PR #66 merge at 23:21,
and a sign-out restarts it; asked the owner to clarify.

## Manual row 1.14, sign-out on the fixed code (2026-10-18)

Windows laptop, the same venv, the checkout at `main` ac3e8fc (castlib identical to 104dd71, with
the F1-F3 fixes). The owner started `cast-tv`, played a video from the window, signed out with
Start → account → Sign out without closing cast-tv, signed back in and reported "dziala"
("it works"): the TV had stopped. The agent's checks after the owner resumed the session agree
that a real sign-out ran and nothing was left: System event 7002 (user logoff) at 23:35:38,
`explorer.exe` started at 23:35:44, and `Get-Process cast-tv` found no process at 23:37:06.

With the Ctrl+C part recorded above, the Windows part of 1.14 is done on the fixed code; the row
stays open for its Fedora `kill` step.

## Manual rows 1.10, 1.9, 1.14 (kill) and 1.12, Fedora (2026-10-19)

Fedora 44 Workstation (GNOME 50.6, Wayland, kernel 7.2.11), Python 3.14.8, the checkout at `main`
f04dfcb. The agent ran the commands and drove the UI; the owner watched the TV and the screen and
confirmed each row in the session ("1 tak, 2 tak" twice: 1.10 and 1.9, then 1.14 and 1.12).

**Deviation, pipx.** Fedora has no pipx (`command -v pipx` empty, `rpm -q pipx`: not installed),
and `~/.local/bin/cast-tv` is the owner's symlink to the checkout's shim, which a real
`pipx install --force` would replace. pipx 1.18.4 ran from a venv in the session scratchpad with
`PIPX_HOME`, `PIPX_BIN_DIR` and `PIPX_MAN_DIR` there; the install is a normal pipx venv built from
the checkout, and the owner's symlink was left alone. The rows' commands ran as
`$PIPX_BIN_DIR/cast-tv` from a directory outside the checkout.

**Found: the `[window]` spec in zsh.** `pipx install --force "$PWD[window]"`, as `temp_steps.md`
wrote it, installs cast-tv **without** the extra in zsh (Fedora's and the owner's shell) and
still exits 0: zsh reads `$PWD[window]` as a subscript and expands it to an empty string
(`echo "[$PWD[window]]"` prints `[]`; bash prints the path). pipx's metadata then had no extras
and the venv had no PySide6. `"${PWD}[window]"` works: pipx logged the spec
`/home/piotrmiller/Source/cast-tv[window]` and installed PySide6 6.12.0, pywebview 6.2.1 and
QtPy 2.4.3.

- **1.10, without the extra** (21:13): the console printed the addresses, the firewall line and
  "Ctrl+C ends it (playback stops on the TV too)", and a tab opened in Chrome (the default
  browser). The agent used its own tab on the same `http://127.0.0.1:8895/ui/` (a direct
  navigation from the extension is refused with 403 `forbidden`, the cross-site check; a
  same-origin navigation from that page loads the UI). "Quit cast-tv" was at the right of the
  header. A video (OneDrive, `Dokumenty/Videos/Przejazd - SuperCars.mp4`) was started by clicking
  it at 21:17:03 and reached `PLAYING` at 21:17:16. Quit was clicked at 21:17:26: the console
  printed `Stopped.`, the process exited 0 at 21:17:26, and the tab showed "cast-tv has ended;
  you can close this tab." The owner confirmed that the TV played the video and stopped.
  Seen too: the tab's now-playing bar stayed at "Przejazd - SuperCars.mp4 playing 0:00:12" after
  the end, the last state before the server went away.
- **1.9, with the extra** (21:19): the console printed the window-mode hint "Close the window or
  press Ctrl+C to end it (playback stops on the TV too)" and three Qt warnings
  `qt.qpa.wayland.textinput: … disableSurface … Trying to disable … but 0x0 is focused`;
  `/api/status` reported `window: true`. The owner confirmed a window titled cast-tv showing the
  UI, not a browser tab.
- **1.14, kill** (21:20, the same window): the video was started through `POST /api/cast` from
  loopback (curl), the endpoint the window's page calls; the agent cannot click inside a Qt
  window on Wayland, so this replaces "start a video from the window". `PLAYING` at 21:20:24.
  `pgrep -af cast-tv` printed six lines: the Python process (220134), four `QtWebEngineProcess`
  helpers and `systemd-inhibit … --who=cast-tv`, all matching because the pipx path contains
  `cast-tv`; the first column of the first line was the main process. `kill 220134` at 21:20:40.6:
  the process was gone by 21:20:41.6, printed `Stopped.` and exited 0; no helper and no
  `systemd-inhibit` was left. The owner confirmed that the TV stopped and the window closed.
- **1.12, forced fallback** (21:20:57): `CAST_TV_WINDOW_FAIL=1` gave a Chrome tab, not a window
  (owner confirmed). The console printed the window-mode hint first and then "No cast-tv window
  (CAST_TV_WINDOW_FAIL); the UI opens in the browser. Ctrl+C ends it (playback stops on the TV
  too)"; `temp_steps.md` had expected "(unavailable: CAST_TV_WINDOW_FAIL)". `/api/status` said
  `window: false`; Diagnostics in the tab showed the card `window_unavailable`: "No cast-tv
  window: CAST_TV_WINDOW_FAIL." with the hint "The UI opened in the browser instead; Ctrl+C here
  ends cast-tv." SIGINT at 21:21:48 (the Ctrl+C the hint names): `Stopped.`, exit 0.

Two console texts for a later phase, not failures of these rows: in a fallback the console first
says "Close the window" and then that there is no window; and the Qt warnings land on the
console that Phase 3 hides.

## Phase 2: the release builds and manual row 2.6 (2026-10-26)

**The PR's release run** (PR #80, branch head c4be482, run 40386649886) was green on both
runners. Its smoke test printed:

- **Windows (`windows-latest`, Python 3.12.10):** the WebView2 runtime 155.0.4283.62 was already
  installed (the bootstrapper step did not run); `size: 26071071 bytes`, `Window: edgechromium`,
  `self-check: HEIC -> image/jpeg 16x16 OK`, `window-check: edgechromium OK (8.6 s)`.
- **Linux (`ubuntu-22.04`, under `xvfb-run -a`):** `size: 260494488 bytes`, `Window: qtwebengine`,
  `self-check: HEIC -> image/jpeg 16x16 OK` (pillow-heif without the bundled `libstdc++`, on the
  runner's own), `window-check: qtwebengine OK (5.8 s)`.
- Artifacts: `cast-tv-windows-x64.exe` id 12680597503, `cast-tv-linux-x64` id 12680887196.

A local build on the Windows laptop (Python 3.14.5, pywebview 6.2.1, pythonnet 3.2.1,
PyInstaller 6.22.3; a placeholder Google client written for the build and the stub restored
right after) was 26,167,565 bytes and passed the same smoke test with `window-check:
edgechromium OK (6.8 s)`. On Python 3.14, `subprocess` would not start the relative path
`dist/cast-tv.exe` (WinError 2), so `smoke.py` now resolves the path first.

**Row 2.6** (2026-10-26, the owner, Windows 11 laptop). The PR run's `cast-tv-windows-x64.exe`,
downloaded with `gh run download 40386649886` into `Downloads\s12-phase2`: 26,071,071 bytes,
SHA-256 `9e4dae643f11c506627c25ff0373d6a4c2bda7f55fea6fdbb22252a0fdbbbf74`. Started from
PowerShell 7.6.9; the owner pasted the console:

- `--version` printed `cast-tv 0.4.0`, `Google Photos client: built in`, `GoPro window: C:\Program
  Files\Google\Chrome\Application\chrome.exe`, `Window: edgechromium`.
- **Start 1**, `Get-Date` 21:01:01.902 just before Enter: the three addresses (localhost, the
  Wi-Fi 192.168.50.213, a 172.21.80.1 virtual adapter), the firewall line, "Close the window or
  press Ctrl+C to end it", `TV: 83" OLED (192.168.50.142)`. The cast-tv window opened on the UI
  about 2 s after Enter (owner's estimate). No SmartScreen or Defender prompt. Ended with Ctrl+C
  in the PowerShell window (owner's answer, asked twice): `Stopped.` and the prompt returned, but
  after `Stopped.` Python printed `Exception ignored in atexit callback: <function unload ...>`,
  a traceback through `pythonnet\__init__.py` line 161 (`unload`) and `clr_loader\types.py`
  line 65, ending in `KeyboardInterrupt:`. pythonnet's atexit shutdown of the .NET runtime was
  interrupted by a `KeyboardInterrupt`. Not seen before: no earlier entry here mentions it.
- **Start 2**, 21:01:25.909: the same lines; ended with the window's X (owner's answer):
  `Stopped.`, the prompt returned, no traceback.

Row 2.6's criterion (the window opens, `--version` names `edgechromium`, size and start time
recorded) is met. The Ctrl+C traceback is a separate defect on the Ctrl+C exit path (rows 1.14,
3.11), left for Phase 3, which works on that path.

**Found while trying to reproduce it** (Claude, 2026-10-26 21:10). A script that started the exe
with `Start-Process -WindowStyle Hidden` and called `CloseMainWindow()` was not a valid stand-in
for X: the onefile exe is a bootloader plus a child that owns the window, so the call reached the
bootloader, and killing it after 20 s left the child running (it was ended through
`POST /api/quit`, stderr empty). The same split explains a leftover from the local smoke run:
`dist\cast-tv.exe --no-browser -p 8099`, started at 20:13 by `smoke.py`, was still serving at
21:10. `smoke.py`'s `proc.kill()` on Windows ends only the bootloader. CI's runner is discarded
after the job, so the release gate is unaffected; a local run leaves a server on port 8099.
Left for Phase 3 with the traceback.

## Manual row 2.6 again, after the action pins moved to Node.js 24 (2026-10-26)

ci-actions-node24 (PR #82, squash 1185659) changed `.github/workflows/release.yml`, one of row
2.6's surfaces, so the acceptance at 7eb63db went stale. The exe checked here comes from PR #82's
release run 40398550351 (head 1b92d0c, whose tree is main's at 1185659; `castlib/`, `packaging/`
and the workflows are unchanged from 1185659 to 70d37b7). Its smoke test printed
`size: 26072009 bytes` and `window-check: edgechromium OK (8.0 s)`.

**Row 2.6** (2026-10-26, the owner, Windows 11 laptop). `cast-tv-windows-x64.exe` downloaded with
`gh run download 40398550351 -n cast-tv-windows-x64.exe` into `Downloads\s12-2.6-node24`:
26,072,009 bytes, SHA-256 `B227237F0E89935BD21AF499C75DD193FF7FEED31A160D1C23BE77BBD8BE549B`.
Started from PowerShell 7.6.9; the owner pasted the console:

- `--version` printed `cast-tv 0.4.0`, `Google Photos client: built in`, `GoPro window: C:\Program
  Files\Google\Chrome\Application\chrome.exe`, `Window: edgechromium`.
- Start, `Get-Date` 22:22:26.042 just before Enter: the three addresses (localhost:8895, the Wi-Fi
  192.168.50.213, the 172.21.80.1 virtual adapter), the firewall line, "Close the window or press
  Ctrl+C to end it", `TV: 83" OLED (192.168.50.142)`. The cast-tv window opened on the UI 1.5-2 s
  after Enter (owner's estimate). Ended as asked, with the window's X: `Stopped.`, the prompt
  returned, no traceback. The owner reported no SmartScreen or Defender prompt.

Row 2.6's criterion (the window opens, `--version` names `edgechromium`, size and start time
recorded) is met for the exe built by the Node.js 24 actions.

## Manual rows 2.7-2.9, Fedora (2026-10-27)

The binary is the Linux file of PR #82's release run 40398550351, the same run as row 2.6's exe.
Downloaded with `gh run download 40398550351 -R Piotr-Miller/cast-tv -n cast-tv-linux-x64` into
`~/Downloads/s12-phase2-node24`: 260,495,368 bytes, SHA-256
`aaf9b3e754c79461d0bafa5c6a0ac4a101cedd51392340cc7091f5c7dbe434fa`. `--version` printed
`cast-tv 0.4.0`, `Google Photos client: from ~/.config/cast-tv/google-client.json`,
`GoPro window: /usr/bin/google-chrome`, `Window: qtwebengine`.

**Row 2.7** (2026-10-27, the owner, Fedora 44 desktop, Wayland). Started from a terminal with
`date +%T.%3N; ./cast-tv-linux-x64`, no `QTWEBENGINE_CHROMIUM_FLAGS` set. The Qt window appeared
2.67 s after Enter and showed the rendered UI at 7.35 s. The GPU was on: the process used
`/dev/dri/renderD128`. Closed with the window's X: the window went away, the terminal printed
`Stopped.`, the process exited with code 0 and port 8895 was free again. Qt/Wayland warnings were
printed; there was no traceback.

Row 2.7's criterion (a Qt window with the GPU on; size and start time recorded) is met. The start,
7.35 s to a usable UI, is under the plan's 15 s threshold, so the Linux release stays one file.

**Row 2.8, unsuccessful attempt** (2026-10-27, Codex operating the Fedora 44 desktop;
the owner observing the 83" OLED TV at 192.168.50.142). Used the same release binary as row
2.7 and the local file `~/Downloads/Test_Pictures/shelf-christmas-decoration.heic`
(1,442,278 bytes; shelves with Christmas decorations). Google Photos was disconnected with
no picked items. The Qt UI has no local file chooser, so this attempt used the binary's CLI
with `--debug -t 192.168.50.142` and the HEIC path; it did not exercise casting through the
Qt window.

- The release converted the HEIC to `image/jpeg`, 4000x3000, 2,004,138 bytes, profile `JPEG_LRG`.
- The request log showed a TV `HEAD` request and no `GET`; transport state was `TRANSITIONING`.
  The attempt ended with `The TV stopped answering.` and
  `Check it is on and on the same network, then retry.`
- The owner confirmed that the photo was not visible on the TV ("Nie bylo widac"). Codex
  had no view of the physical TV screen and did not independently observe its picture.
- After the attempt, no cast-tv or QtWebEngine process remained and port 8895 was free.

Row 2.8 remains open: no displayed photo means orientation could not be assessed, and the
Qt-window path was not exercised. The cause of the failed display has not been established.

**Row 2.9** (2026-10-27, Claude, on the Fedora host). The Ubuntu 24.04 VM from the 2026-10-16
spike (`~/.cache/cast-tv-s12-spike`, Ubuntu 24.04.5 LTS, `ubuntu-desktop-minimal` and `xvfb`
installed) still boots. Its spike SSH key was gone, so it was booted under `qemu-kvm` with a new
cloud-init seed (`instance-id: s12-row-2-9`) carrying a fresh key; only the throwaway VM disk
changed. The same binary was copied in (same size and SHA-256 as above); in the VM `--version`
printed `cast-tv 0.4.0`, `Google Photos client: built in`, `GoPro window: none found (token paste
only)`, `Window: qtwebengine`. Started on a bare `Xvfb :99 -screen 0 1280x800x24` (no window
manager, no GPU): `/api/status` answered 3.6 s after the start, and a screenshot of the X screen
15 s later showed the cast-tv window with the full UI (header, "No TV found" panel, the GoPro,
OneDrive and Google Photos tabs, "Connect GoPro"). The console printed the addresses, "Close the
window or press Ctrl+C to end it" and one `GLX: No DRI3 Extension.` line, with no browser fallback
and no traceback. Ctrl+C (SIGINT) printed `Stopped.`, the process exited with code 0 and port
8895 was free.

Row 2.9's criterion (the Linux binary opens its window on Ubuntu 24.04, or why not) is met. The
window had no title bar because Xvfb ran without a window manager; the desktop session itself
(GNOME on Wayland) was not exercised in the VM, as the VM has no display attached.

**Row 2.8, retry from the Qt window** (2026-10-27, Codex, Fedora 44 desktop, same release
binary). Opened the release's native Qt window (`/api/status` reported `window: true`).
Using its accessible UI controls, opened OneDrive, which connected using its stored session,
then Pictures -> Test_Pictures. The grid showed `shelf-christmas-decoration.heic`
(`image/heic` in the source listing), with an upright thumbnail of the two decorated shelves.
This retry used OneDrive rather than the plan's Google Photos/local-file variants.

The window showed `No TV found`. SSDP received a response from 192.168.50.142 advertising
`http://192.168.50.142:9197/dmr`, but fetching that device description returned HTTP 401
with a UPnP fault `401 Unauthorized`, so cast-tv could not resolve AVTransport. The TV's
read-only `/api/v2/` endpoint reported `PowerState: on`, name `83&quot; OLED`, model
`QE83S85FAEXXH`. Selecting that IP in cast-tv returned `tv_no_avtransport`.

At 20:51:34 +01:00, invoked the HEIC tile's actual `Cast now` button through accessibility
in the Qt window. The app's error ring then contained `no_tv: No TV selected.` and its
status had no active cast. The photo was not sent; there is no new observation of its
orientation on the physical TV. Row 2.8 remains open. Left the Qt window open on the
prepared folder for a further retry; restored the desktop accessibility setting to its
original value (false). No app code or TV settings were changed.

**Row 2.8, further retry at 21:06 +01:00** (2026-10-27, Codex, same Fedora desktop,
release and Qt window). Pressed `Search again` in the window and waited for discovery to
finish: no TV was selected. At 21:06:30, pressed `Cast now` on the same OneDrive HEIC tile
again. The error ring gained a new `no_tv: No TV selected.` entry; status still had no
active cast. The TV reported power on, but its advertised `/dmr` endpoint still returned
HTTP 401. No photo was sent, so the TV orientation remains unverified and row 2.8 remains
open. Left the prepared window open and restored toolkit accessibility to false.

**Why the TV was not found, and row 2.8 passed** (2026-10-27, the owner at the TV, Claude on
Fedora). The 401 was the TV's own access control, not cast-tv: Samsung grants DLNA per client in
Settings → General → Device Connection Manager → Device List, and this Fedora laptop (Wi-Fi
`wlo1`, 192.168.50.198, randomised MAC `be:14:c5:89:a9:0b`) was not allowed there; the Windows
laptop was. The list shows entries only as "Device 1", "Device 3" and so on, with no name or IP;
Fedora turned out to be "Device 3". After the owner allowed it, `curl
http://192.168.50.142:9197/dmr` from Fedora returned 200 with `friendlyName` `83" OLED` and
AVTransport:1, and a discovery on the running window (`POST /api/tv/discover`, what Search again
sends) selected `83" OLED (192.168.50.142)`, state `ready`.

**Row 2.8** (2026-10-27, about 21:15 +01:00, the owner, Fedora 44 desktop, the release binary
above in its Qt window, TV QE83S85FAEXXH). `Cast now` on the OneDrive tile
`shelf-christmas-decoration.heic` (`image/heic`) in Pictures → Test_Pictures: the photo of the two
decorated shelves showed on the TV upright, as on the thumbnail. Row 2.8's criterion (a HEIC
photo cast through the window shows upright) is met; the plan's Google Photos or Local variant
was not needed, as OneDrive serves the same HEIC conversion path.

Side finding for a later change: when the TV answers the device description with 401, the UI
says "No TV found" and a cast says `no_tv`, which hides that the TV was found but refused this
computer. A message naming Device Connection Manager would have saved two retries.

Second side finding, from the same window (2026-10-27): Diagnostics also held a `tv_rejected` at
21:16:01 for the same OneDrive item: "HTTP Error 500: Internal Server Error (UPnP 701: Transition
not available); after it the TV reported TRANSITIONING" ten times. The status read just after it
showed the cast that started at 21:15:55 as `playing` (TV `PLAYING`, `error: null`, `converted:
true`, 4000x3000); `cast` in the status is the promoted cast, which a failed later one never
replaces. The likely reading, from that status and `supervisor.py` (not from the error ring,
which was gone once the window closed): a second `Cast now` 1-2 s after the first met the TV
still TRANSITIONING into the 12 MP photo; its `SetAVTransportURI` got 701, the wait of
`PLAY_701_GRACE` (4 s) saw only TRANSITIONING, and the retry got 701 again. The TV kept showing
the first, identical photo, so nothing looked wrong on the screen while Diagnostics reported a
failure. The owner confirmed pressing `Cast now` twice, so the Qt window did not double a click.
Row 2.8 rests on the cast that played, so it stands.

## Phase 3: the release builds (2026-10-27)

Implemented on Fedora (PR #89, commit 0561081). The PR's test run 40578872429 passed on
`ubuntu-latest` and `windows-latest`. Its release run 40578872547 built and smoke-tested both
files:

- **Windows (`windows-latest`):** `size: 26086550 bytes`, `Window: edgechromium`,
  `self-check: HEIC -> image/jpeg 16x16 OK`, `/ui/ 200, /api/status 200`,
  `POST /api/quit: ended, port 8099 free`, `window-check: edgechromium OK (8.1 s)`. The exe is
  the first built with `hide_console="hide-early"`; started by `smoke.py` it still served and
  answered Quit. `POST /api/quit` ending the bootloader and its child is the fix for row 2.6's
  leftover server: the smoke test now fails if anything still answers on the port.
- **Linux (`ubuntu-22.04`, under `xvfb-run`):** `size: 260510376 bytes`, `Window: qtwebengine`,
  the same self-check, `POST /api/quit: ended, port 8099 free`, `window-check: qtwebengine OK
  (5.8 s)`.

Before the PR, the new `smoke.py` ran on Fedora against the Phase 2 Linux binary (run
40398550351) with a clean `HOME`: `POST /api/quit: ended, port 8099 free`, `window-check:
qtwebengine OK (3.7 s)`. A QR code made by the page's `qrSvg()` for
`http://192.168.50.198:8895/ui/` was rendered to PNG and decoded with OpenCV's
`QRCodeDetector` back to the same address.

Not provable on Fedora, left to the manual rows: whether `GetWindowThreadProcessId` on the
console window names the onefile bootloader after a double-click (3.10, 3.12's error box), and
whether ignoring SIGINT after the window closed removes the pythonnet `atexit` traceback (3.11).

## Manual row 3.9, Fedora (2026-10-27)

**First run** (the owner, Fedora 44 desktop, Wayland). PR #89's Linux binary from release run
40578872547, downloaded into `~/Downloads/s12-phase3`: 260,510,376 bytes, SHA-256
`749dfbbb603e62f9e8c11dc49e17a679dae4ef10aeb082bd2bc3d6e4bce442fd`, `Window: qtwebengine`.
`/api/status` reported `window: true`, `host: true`, addresses `http://localhost:8895/ui/` and
`http://192.168.50.198:8895/ui/`, `firewall_blocked: null`.

- The "Open on your phone" panel listed only `http://192.168.50.198:8895/ui/`: as expected.
- **Copy** showed no "Copied.": a defect.
- **QR code** drew a tiny code in the top-left corner of the white square (owner's screenshot): a
  defect.
- Scanning that code with the phone opened the cast-tv UI on the phone, with no phone panel and
  no Quit control: as expected.

**The causes**, measured in the same window through Qt's remote debugging
(`QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:9333`, QtWebEngine 6.14, `Runtime.evaluate` with a user
gesture):

- `navigator.clipboard.writeText()` never settled (cut off after 5 s): Qt WebEngine asks for a
  clipboard permission that pywebview never answers, so neither "Copied." nor the
  `window.prompt` fallback ran. `document.execCommand('copy')` on a selected textarea returned
  true, and `wl-paste` printed the text. `copy()` now tries `execCommand` first, inside the
  click; the Diagnostics "Copy command" buttons share it.
- The HTML parser lowercased the attribute `:viewBox`, so Alpine set `viewbox`, which SVG
  ignores. Without a viewBox the path drew in pixels, one per module. The binding is now
  `:view-box.camel`. After the fix the window reported `viewBox="0 0 37 37"`, an SVG of
  180x180 px and the modules 141x141 px.

**Second run**, same window and binary, with the fixed `app.js` and `index.html` copied over the
binary's unpacked `castlib/ui` (the server reads them on every request; `cmp` showed them equal
to the checkout) and the page reloaded. The owner clicked Copy and scanned the QR code again:
"Działa". Copy pasted the address, and the code filled its square and opened the UI on the phone.

Row 3.9's criterion (the phone panel and QR codes work in the Qt window) is met with the fix.
The checks of the rebuilt binary are below.

**The rebuilt binary** (Claude, 2026-10-27). PR #89's release run 40580688484, built from 1134162:
Windows `size: 26086907 bytes`, `window-check: edgechromium OK (7.9 s)`; Linux `size: 260510504
bytes`, SHA-256 `b75a2e2d906cdfaaf4e2ef6fa674e4f4edee4799d4ecfcee65df298877dc432b`,
`window-check: qtwebengine OK (3.2 s)`; both `POST /api/quit: ended, port 8099 free`. Its Qt
window on Fedora, read through remote debugging after clicking QR code: the panel lists
`http://192.168.50.198:8895/ui/`, `viewBox="0 0 37 37"`, SVG 180x180 px, modules 141x141 px, and
`copyByCommand` is in the page. Ended with `POST /api/quit`.

## Manual rows 3.6 and 3.11 on the work laptop, without the TV and the phone (2026-10-28)

The owner, on the Intune-managed Windows 11 Enterprise laptop. Its MDM firewall rule "Block
InBound connection Public Private" is still active (checked in `ActiveStore`), so neither the TV
nor the phone can fetch from it. Only the parts that need no inbound connection are observed
here. The rows stay open until the cast and phone parts run on the other Windows machine. The exe
is PR #89's from release run 40580688484, downloaded into `Downloads\s12-phase3`: 26,086,907
bytes, SHA-256 `d85e853a384d013918bfb00b91f2347236969f0aefcd429f2dcb3c420072c1f1`, `--version`
ends `Window: edgechromium`. The laptop's IPv4 addresses: Wi-Fi 192.168.50.242 (the default
route), Hyper-V `vEthernet (Default Switch)` 172.27.112.1, `vEthernet (WSL)` 172.21.128.1 and
five 169.254.x link-local addresses.

**Started from PowerShell** (`.\cast-tv-windows-x64.exe`, row 3.11's start):

- PowerShell printed `localhost`, `192.168.50.242`, `172.27.112.1` and `172.21.128.1` (each
  `:8895/ui/`), the netsh hint, "Close the window or press Ctrl+C", `TV: 83" OLED
  (192.168.50.142)` and the firewall-policy warning naming the rule. The cast-tv window opened.
- In the window (owner's screenshots), the banner "The TV cannot fetch from this computer" showed
  the same advice. The "Open on your phone" panel listed `http://192.168.50.242:8895/ui/` first,
  then 172.27.112.1 and 172.21.128.1, each with Copy and QR code. There was no localhost and no
  169.254.x address.
- **QR code** for 192.168.50.242 drew a code filling its white square (WebView2, so the
  `:view-box.camel` fix holds there too). The phone's camera read it as
  `http://192.168.50.242:8895/ui/`. Opening it on the phone is blocked by the firewall and is left
  for the other machine.
- **Copy** showed "Copied." at the bottom of the window.
- **Ctrl+C in the PowerShell window** printed `Stopped.`, the window closed, and PowerShell came
  back with no `Exception ignored in atexit callback` traceback, which was row 2.6's finding.
  `$LASTEXITCODE` was 0.

Left for the other Windows machine: 3.6's phone opening the UI, and 3.11 with a cast running (the
TV stops on Ctrl+C).

**Double-click** (row 3.10's start), the same exe from File Explorer: at most a console flashed,
then only the cast-tv window showed, with no console window and no Windows Terminal tab (owner:
"zobaczyłem to co opisałeś"). So the console's owner is recognised as this process or the onefile
bootloader, and `hide-early` plus the owned-console check behave as intended on Windows. Closing
the window with X ended everything. Task Manager's Processes filtered on `cast-tv` showed no
results (owner's screenshot). Claude then found no `cast-tv*` process (`Get-Process`) and nothing
listening on 8895 (`Get-NetTCPConnection`).

Left for the other Windows machine: 3.10 with a cast running (the TV stops on X).

**Forced fallback with a hidden console** (row 3.12). In PowerShell:
`$env:CAST_TV_WINDOW_FAIL='1'; Start-Process .\cast-tv-windows-x64.exe`. A browser tab opened
with the UI. The console window appeared next to it, so `platform.show_console()` brought back
the hidden console. It showed the four addresses, the netsh hint, `Close the window or press
Ctrl+C to end it ...`, then `No cast-tv window (CAST_TV_WINDOW_FAIL); the UI opens in the browser.
Ctrl+C ends it (playback stops on the TV too)`, the TV and the firewall-policy warning. The owner
closed that console window with its X. The tab then showed "cast-tv is not answering. The process
may have stopped." (owner's screenshot; the tab, on localhost, also showed the firewall banner and
the phone panel). The variable was removed with `Remove-Item Env:CAST_TV_WINDOW_FAIL`.

Side finding, not a 3.12 failure: on the fallback path the console still prints `Close the window
or press Ctrl+C` (`WINDOW_ENDS`, printed before the window is tried) above the line saying there
is no window. That is harmless, but it names a window that never came.

**The error box.** In a second PowerShell window, `python -m http.server 8895 --bind 127.0.0.1`
held the port (Python 3.14.8).

- A double-click on the exe in File Explorer showed a message box titled `cast-tv` with the error
  icon, the text `Cannot bind port 8895: [WinError 10048] Only one usage of each socket address
  (protocol/network address/port) is normally permitted` and an OK button (owner's screenshot).
  It stayed until OK.
- From the first PowerShell window, `.\cast-tv-windows-x64.exe` printed the same `Cannot bind
  port 8895: [WinError 10048] ...` line and showed no box. `$LASTEXITCODE` was 1.
- The HTTP server was stopped with Ctrl+C. Claude then found no `cast-tv*` process and nothing
  listening on 8895.

Left for the other Windows machine: 3.12's cast from the tab (the TV stops when the console
closes).

**Offline** (row 3.8). Two runs: the owner turned the Wi-Fi tile off in the taskbar's network
menu, started the exe from PowerShell, then closed it with X and turned Wi-Fi back on. Both runs
gave the same result (owner's screenshots). PowerShell and the panel listed
`http://192.168.50.242:8895/ui/` first, then 172.27.112.1 and 172.21.128.1. Discovery reported
"No TV found" and "Searched on: Intel(R) Wi-Fi 6E AX211 160MHz 192.168.50.242 — 0 responses",
plus the two Hyper-V adapters, so the M-SEARCH socket bound to the Wi-Fi address without an
error. No firewall warning appeared, because there was no TV to check against. The panel never
said "This computer has no network address".

During the second run Claude logged every 3 s: `Get-NetAdapter`, `Get-NetIPAddress` and
`ifaddr.get_adapters()` (0.2.0, the library `lan_interfaces()` uses), plus `/api/status`
addresses. State changes:

```
19:20:28 wifi=Up/Connected            netip=[192.168.50.242/Preferred]  ifaddr lists 192.168.50.242
19:21:00 wifi=Disconnected/Disconnected netip=[192.168.50.242/Deprecated] ifaddr lists 192.168.50.242
19:21:21 (cast-tv started) status addresses: localhost, 192.168.50.242, 172.27.112.1, 172.21.128.1
19:22:08 (cast-tv closed)
19:22:29 wifi=Up/Connected            netip=[192.168.50.242/Preferred]
```

**Finding:** with Wi-Fi off, Windows 11 keeps the DHCP address on the disconnected adapter in
`AddressState` **Deprecated**. Here it stayed for the whole 89 s that Wi-Fi was off. `ifaddr`
does not filter it: its `IP_ADAPTER_UNICAST_ADDRESS` reads `DadState`, but the `IP` objects do
not expose it. So cast-tv offers the phone an address that nothing can reach, and the offline
message cannot show on Windows while such an address remains. On this laptop the Hyper-V
adapters (172.27.112.1, 172.21.128.1, always up) would keep the panel non-empty anyway, which the
plan accepts ("VPN or Docker addresses: listed like any other"). A Windows machine without virtual
adapters would still fail 3.8 because of the Deprecated Wi-Fi address.

**The fix** (owner's decision: on PR #89). `discovery.stale_addresses()` reads each IPv4 address's
`DadState` from `GetAdaptersAddresses` through ctypes (`_windows_dad_states`). Every address not
in `IpDadStatePreferred` (4) is stale. `lan_interfaces()` skips stale addresses, so discovery no
longer sends M-SEARCH from them, and `App.start` drops the default-route address if it is stale.
Off Windows, or if the call fails, nothing is stale and the list is as before. On this laptop with
Wi-Fi on, the call returned 192.168.50.242, 127.0.0.1 and both Hyper-V addresses as Preferred
(4), and the five 169.254.x addresses of the disconnected adapters as Tentative (1). Locally:
`pyflakes` clean. Over three full `pytest` runs, 455-456 passed and 5 were skipped. Two tests fail
on this laptop with or without the change (a full run with the change stashed: the same two
failed, 450 passed): `test_onedrive.py::test_token_file_mode_0600` always (`PermissionError` on
the token file), and `test_cli.py::test_cast_replaced_from_the_ui_keeps_serving` in some runs
(`'App' object has no attribute 'current'`, read before `__init__` finished; alone it passes).
CI decides. Row 3.8 is to be run again on the PR's new release exe.
