# PyInstaller spec for the standalone cast-tv: one file, a console window, the cast-tv window.
# Build from the repository root, with the window extra installed:  pyinstaller packaging/cast-tv.spec
# The console stays: Ctrl+C and closing the window stop the TV (castlib.platform).
# The window: pywebview with WebView2 on Windows, Qt WebEngine (PySide6) on Linux.
import os
import sys

from PyInstaller.utils.hooks import collect_all

heif_datas, heif_binaries, heif_hidden = collect_all("pillow_heif")

if sys.platform == "win32":
    window_hidden = ["webview.platforms.winforms"]
else:
    window_hidden = ["webview.platforms.qt", "qtpy"]

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=heif_binaries,
    datas=[("../castlib/ui", "castlib/ui")] + heif_datas,
    hiddenimports=heif_hidden + ["castlib.auth._builtin_client", "castlib.window",
                                 "castlib.window_probe"] + window_hidden,
    excludes=["tkinter", "pytest", "gi"],      # gi: a host GTK must never be collected
)
if sys.platform.startswith("linux"):
    # The bundled libgbm and libstdc++ break Qt WebEngine's GPU path on current distributions:
    # the host's GPU drivers need a newer libstdc++, and the bundled libgbm looks for drivers
    # in the wrong place. Without both it rendered everywhere tested (s12-desktop-window,
    # research.md, 2026-10-16); every distribution in scope has its own copies.
    DROP = {"libgbm.so.1", "libstdc++.so.6"}
    a.binaries = [b for b in a.binaries if os.path.basename(b[0]) not in DROP]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="cast-tv",
    console=True,
    upx=False,
)
