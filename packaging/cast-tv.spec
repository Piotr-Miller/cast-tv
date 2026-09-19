# PyInstaller spec for the standalone cast-tv: one file, a console window.
# Build from the repository root:  pyinstaller packaging/cast-tv.spec
# The console stays: Ctrl+C and closing the window stop the TV (castlib.platform).
from PyInstaller.utils.hooks import collect_all

heif_datas, heif_binaries, heif_hidden = collect_all("pillow_heif")

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=heif_binaries,
    datas=[("../castlib/ui", "castlib/ui")] + heif_datas,
    hiddenimports=heif_hidden + ["castlib.auth._builtin_client"],
    excludes=["tkinter", "pytest"],
)
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
