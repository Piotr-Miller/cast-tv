"""The menu entry: the .desktop file and the Start menu shortcut, in temporary homes."""
import json
import os
import subprocess
import sys
import types

import pytest

from castlib import shortcut
from castlib.errors import ConfigError
from castlib.shortcut import Command, MenuEntry

SPACED = "/home/a user/Apps/cast tv/cast-tv-linux-x64"


def linux(tmp_path, **kw):
    kw.setdefault("frozen", True)
    kw.setdefault("executable", SPACED)
    return MenuEntry(platform="linux", environ={}, home=str(tmp_path), **kw)


# ------------------------------------------------------------- what it starts
def test_target_per_install_kind(tmp_path):
    frozen = MenuEntry(platform="linux", frozen=True, executable="/opt/x/cast-tv", root="")
    assert frozen.target() == Command(("/opt/x/cast-tv",))
    checkout = MenuEntry(platform="linux", frozen=False, executable="/venv/bin/python", root=str(tmp_path))
    assert checkout.target() == Command(("/venv/bin/python", "-m", "castlib"), str(tmp_path))
    pipx = MenuEntry(platform="linux", frozen=False, executable="/pipx/venvs/cast-tv/bin/python", root="",
                     which=lambda name: "/home/u/.local/bin/" + name)
    assert pipx.target() == Command(("/home/u/.local/bin/cast-tv",))
    bare = MenuEntry(platform="linux", frozen=False, executable="/usr/bin/python3", root="", which=lambda n: None)
    assert bare.target() == Command(("/usr/bin/python3", "-m", "castlib"))


def test_checkout_root_comes_from_the_package_not_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = shortcut.checkout_root()
    assert root and os.path.isfile(os.path.join(root, "pyproject.toml"))
    assert os.path.isdir(os.path.join(root, "castlib"))
    site = tmp_path / "site-packages"
    (site / "castlib").mkdir(parents=True)
    assert shortcut.checkout_root(str(site / "castlib")) is None      # an installed package has no checkout


# --------------------------------------------------------------- the .desktop
def test_desktop_text_with_spaces(tmp_path):
    assert shortcut.desktop_text(Command((SPACED,))) == (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=cast-tv\n"
        "Comment=Cast local files and cloud media to a TV\n"
        'Exec="/home/a user/Apps/cast tv/cast-tv-linux-x64"\n'
        "Icon=cast-tv\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Video;Player;\n"
        "StartupWMClass=cast-tv\n")
    text = shortcut.desktop_text(Command(("/v env/bin/python", "-m", "castlib"), "/src/cast tv"))
    assert 'Exec="/v env/bin/python" -m castlib\n' in text and "Path=/src/cast tv\n" in text


@pytest.mark.parametrize("arg", ["plain", "a b", 'q"uote', "back\\slash", "dollar$x", "tick`x", "100%", "", "C:\\x y\\z"])
def test_exec_quoting_round_trips(arg):
    line = " ".join(shortcut.exec_quote(a) for a in ("/bin/prog", arg, "-m"))
    assert shortcut.parse_exec(line) == ["/bin/prog", arg, "-m"]


def test_exec_quote_follows_the_specification():
    assert shortcut.exec_quote("a b") == '"a b"'
    assert shortcut.exec_quote('x"y') == '"x\\\\"y"'      # \" at the quote level, its backslash doubled as a string
    assert shortcut.exec_quote("50%") == "50%%"


def test_install_writes_the_entry_and_the_icon(tmp_path):
    entry = linux(tmp_path)
    assert entry.state() == {"installed": False, "current": False,
                             "path": str(tmp_path / ".local" / "share" / "applications" / "cast-tv.desktop")}
    state = entry.install()
    assert state["installed"] and state["current"]
    desktop = tmp_path / ".local" / "share" / "applications" / "cast-tv.desktop"
    assert desktop.read_text(encoding="utf-8") == shortcut.desktop_text(Command((SPACED,)))
    icon = tmp_path / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "cast-tv.png"
    assert icon.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_xdg_data_home_is_respected(tmp_path):
    entry = MenuEntry(platform="linux", environ={"XDG_DATA_HOME": str(tmp_path / "data")}, home=str(tmp_path / "h"),
                      frozen=True, executable="/x")
    entry.install()
    assert (tmp_path / "data" / "applications" / "cast-tv.desktop").is_file()


def test_install_twice_is_one_entry_and_remove_twice_is_a_no_op(tmp_path):
    entry = linux(tmp_path)
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "other.desktop").write_text("[Desktop Entry]\nName=other\n")
    entry.install()
    entry.install()
    assert sorted(p.name for p in apps.iterdir()) == ["cast-tv.desktop", "other.desktop"]
    assert entry.remove() == {"installed": False, "current": False, "path": str(apps / "cast-tv.desktop")}
    assert entry.remove()["installed"] is False
    assert sorted(p.name for p in apps.iterdir()) == ["other.desktop"]          # nothing but its own
    assert not (tmp_path / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "cast-tv.png").exists()


def test_a_moved_file_or_another_copy_is_not_current(tmp_path):
    linux(tmp_path, executable="/old/place/cast-tv").install()
    state = linux(tmp_path, executable="/new/place/cast-tv").state()
    assert state["installed"] and not state["current"]
    assert linux(tmp_path, executable="/new/place/cast-tv").install()["current"]   # Update repoints it


def test_checkout_entry_needs_its_working_directory(tmp_path):
    checkout = linux(tmp_path, frozen=False, executable="/venv/bin/python", root="/src/cast tv")
    checkout.install()
    assert checkout.state()["current"]
    desktop = tmp_path / ".local" / "share" / "applications" / "cast-tv.desktop"
    old = desktop.read_text(encoding="utf-8").replace("Path=/src/cast tv\n", "")
    desktop.write_text(old, encoding="utf-8")                  # an entry written without Path
    assert not checkout.state()["current"]
    other = linux(tmp_path, frozen=False, executable="/venv/bin/python", root="/elsewhere")
    checkout.install()
    assert not other.state()["current"]


def test_checkout_command_starts_from_an_unrelated_directory(tmp_path, monkeypatch):
    """What the launcher runs: Exec in Path, started from some other directory, reaches this checkout."""
    root = shortcut.checkout_root()
    entry = linux(tmp_path / "home", frozen=False, executable=sys.executable, root=root)
    entry.install()
    fields = shortcut.desktop_fields(open(entry.path(), encoding="utf-8").read())
    argv, cwd = shortcut.parse_exec(fields["Exec"]), fields["Path"]
    assert cwd == root
    elsewhere = tmp_path / "launcher dir"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run(argv + ["--version"], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("cast-tv ")


# ---------------------------------------------------------- the Start menu
class FakePowerShell:
    """Records each PowerShell run; keeps the .lnk as the values written, and answers reads from them."""

    def __init__(self, fail=False):
        self.calls = []
        self.links = {}
        self.fail = fail

    def __call__(self, argv, capture_output, timeout, env, creationflags):
        assert argv[:4] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
        script = argv[4]
        self.calls.append((script, {k: v for k, v in env.items() if k.startswith("CAST_TV_LNK")}))
        if self.fail:
            return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"Access is denied.\r\nmore")
        path = env["CAST_TV_LNK"]
        if script is shortcut.LNK_WRITE:
            self.links[path] = {"target": env["CAST_TV_LNK_TARGET"], "args": env["CAST_TV_LNK_ARGS"],
                                "dir": env["CAST_TV_LNK_DIR"]}
            with open(path, "wb") as fh:
                fh.write(b"L\x00\x00\x00")
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        assert script is shortcut.LNK_READ
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(self.links[path]).encode(), stderr=b"")


def windows(tmp_path, ps, **kw):
    kw.setdefault("frozen", True)
    kw.setdefault("executable", str(tmp_path / "Down loads" / "cast-tv-windows-x64.exe"))
    return MenuEntry(platform="win32", environ={"APPDATA": str(tmp_path / "Roaming")}, home=str(tmp_path),
                     run=ps, config=str(tmp_path / "Roaming" / "cast-tv"), **kw)


def test_start_menu_shortcut_for_the_release(tmp_path):
    ps = FakePowerShell()
    entry = windows(tmp_path, ps)
    lnk = os.path.join(str(tmp_path / "Roaming"), "Microsoft", "Windows", "Start Menu", "Programs", "cast-tv.lnk")
    assert entry.state() == {"installed": False, "current": False, "path": lnk}
    assert entry.install() == {"installed": True, "current": True, "path": lnk}
    script, env = ps.calls[0]
    exe = str(tmp_path / "Down loads" / "cast-tv-windows-x64.exe")
    assert script is shortcut.LNK_WRITE and env == {
        "CAST_TV_LNK": lnk, "CAST_TV_LNK_TARGET": exe, "CAST_TV_LNK_ARGS": "", "CAST_TV_LNK_DIR": "",
        "CAST_TV_LNK_ICON": exe + ",0", "CAST_TV_LNK_STYLE": "1"}
    assert not os.path.exists(entry.icon_path())             # the release's own icon, no copy


def test_start_menu_shortcut_for_a_checkout(tmp_path):
    ps = FakePowerShell()
    root = str(tmp_path / "Source" / "cast tv")
    entry = windows(tmp_path, ps, frozen=False, executable=str(tmp_path / "venv" / "python.exe"), root=root)
    assert entry.install()["current"]
    _, env = ps.calls[0]
    assert env["CAST_TV_LNK_TARGET"] == str(tmp_path / "venv" / "python.exe")
    assert env["CAST_TV_LNK_ARGS"] == "-m castlib" and env["CAST_TV_LNK_DIR"] == root
    assert env["CAST_TV_LNK_STYLE"] == "7"                    # python's console starts minimised
    ico = str(tmp_path / "Roaming" / "cast-tv" / "cast-tv.ico")
    assert env["CAST_TV_LNK_ICON"] == ico + ",0"
    with open(ico, "rb") as fh:
        assert fh.read(4) == b"\x00\x00\x01\x00"              # the packaged ICO, copied where it stays
    ps.links[entry.path()]["dir"] = ""                        # an old shortcut without the working directory
    assert not entry.state()["current"]
    assert entry.remove()["installed"] is False
    assert not os.path.exists(ico) and entry.remove()["installed"] is False


def test_start_menu_shortcut_for_pipx_and_a_moved_exe(tmp_path):
    ps = FakePowerShell()
    launcher = str(tmp_path / "pipx bin" / "cast-tv.exe")
    pipx = windows(tmp_path, ps, frozen=False, executable="python.exe", root="", which=lambda n: launcher)
    pipx.install()
    assert ps.calls[0][1]["CAST_TV_LNK_TARGET"] == launcher and ps.calls[0][1]["CAST_TV_LNK_ARGS"] == ""
    moved = windows(tmp_path, ps, executable=str(tmp_path / "Elsewhere" / "cast-tv-windows-x64.exe"))
    assert moved.state() == {"installed": True, "current": False, "path": moved.path()}


def test_powershell_failure_is_a_readable_error(tmp_path):
    entry = windows(tmp_path, FakePowerShell(fail=True))
    with pytest.raises(ConfigError) as e:
        entry.install()
    assert e.value.code == "menu_failed" and "Access is denied." in e.value.message
    assert "more" not in e.value.message


def test_cached_reads_the_shortcut_in_the_background(tmp_path):
    ps = FakePowerShell()
    entry = windows(tmp_path, ps)
    assert entry.cached() is None                             # not known yet: the UI shows no button
    for _ in range(200):
        if entry.cached() is not None:
            break
        import time
        time.sleep(0.01)
    assert entry.cached() == {"installed": False, "current": False, "path": entry.path()}
    entry.install()
    assert entry.cached()["installed"] is True                 # install() updates it at once
    assert MenuEntry(platform="darwin").cached() is None      # no menu here: no button


# ------------------------------------------------------- the packaged icons
def test_packaged_icons_without_the_repository():
    from castlib.server import ICON_ICO, ICON_PNG, UI_FILES
    with open(ICON_PNG, "rb") as fh:
        assert fh.read(8) == b"\x89PNG\r\n\x1a\n"
    with open(ICON_ICO, "rb") as fh:
        assert fh.read(4) == b"\x00\x00\x01\x00"
    assert os.path.dirname(ICON_ICO).endswith(os.path.join("castlib", "ui"))   # not under packaging/
    assert "/ui/icon.png" in UI_FILES and not any(name.endswith(".ico") for name, _ in UI_FILES.values())


def test_wheel_package_data_carries_both_icons():
    import fnmatch
    try:
        import tomllib
    except ImportError:                                       # Python 3.10
        pytest.skip("tomllib needs Python 3.11")
    root = shortcut.checkout_root()
    with open(os.path.join(root, "pyproject.toml"), "rb") as fh:
        patterns = tomllib.load(fh)["tool"]["setuptools"]["package-data"]["castlib"]
    for name in ("ui/icon.png", "ui/cast-tv.ico"):
        assert any(fnmatch.fnmatch(name, p) for p in patterns), name
