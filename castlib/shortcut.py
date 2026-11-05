"""The menu entry: a launcher cast-tv writes on request, pointing at the file that wrote it.

Linux: ``cast-tv.desktop`` under ``$XDG_DATA_HOME/applications`` (``~/.local/share``
by default) and the icon under ``icons/hicolor/256x256/apps``. Windows:
``cast-tv.lnk`` under the Start menu's Programs, written and read through
PowerShell's ``WScript.Shell``, the way the firewall question runs PowerShell.
No installer: the window's button calls ``install()`` and ``remove()``.

The entry starts what is running now (``target()``): the release file itself,
the ``cast-tv`` launcher of a pipx install, or ``python -m castlib`` in a
checkout, with the checkout as its working directory. ``state()`` says whether
an entry exists and whether it still starts this file; a moved file or another
copy makes it ``current: False``, and the window offers Update.

Reading a ``.lnk`` takes PowerShell about a second, too slow for the UI's
1.5 s poll: ``cached()`` answers from the last reading and refreshes in the
background; ``install()`` and ``remove()`` update it at once.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass

from castlib.errors import ConfigError
from castlib.server import ICON_ICO, ICON_PNG

NAME = "cast-tv"
TIMEOUT = 20      # seconds PowerShell may take to write or read the shortcut

# The values travel in environment variables, so no path is ever quoted into a script.
LNK_WRITE = r"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:CAST_TV_LNK)
$s.TargetPath = $env:CAST_TV_LNK_TARGET
$s.Arguments = $env:CAST_TV_LNK_ARGS
$s.WorkingDirectory = $env:CAST_TV_LNK_DIR
$s.IconLocation = $env:CAST_TV_LNK_ICON
$s.WindowStyle = [int]$env:CAST_TV_LNK_STYLE
$s.Description = 'Cast local files and cloud media to a TV'
$s.Save()
"""
LNK_READ = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:CAST_TV_LNK)
@{ target = [string]$s.TargetPath; args = [string]$s.Arguments; dir = [string]$s.WorkingDirectory } | ConvertTo-Json -Compress
"""
SW_SHOWNORMAL, SW_SHOWMINNOACTIVE = 1, 7


@dataclass(frozen=True)
class Command:
    """What the entry runs: the program and its arguments, and the working directory it needs (or None)."""
    argv: tuple
    cwd: str | None = None


def checkout_root(package_dir: str | None = None) -> str | None:
    """The source tree ``castlib`` was loaded from, or None for an installed package; never the current directory."""
    import castlib
    package_dir = package_dir or os.path.dirname(os.path.abspath(castlib.__file__))
    root = os.path.dirname(package_dir)
    return root if os.path.isfile(os.path.join(root, "pyproject.toml")) else None


# ------------------------------------------------------------ the .desktop file
_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')


def exec_quote(arg: str) -> str:
    """One argument of a desktop entry's ``Exec`` line, as the Desktop Entry Specification quotes it.

    An argument with a reserved character is double-quoted with ``"`, $ and \\``
    backslash-escaped. ``Exec`` is a string value, so every backslash is then
    doubled once more; ``%`` is a field code and is written ``%%``.
    """
    if arg and not (set(arg) & _RESERVED):
        quoted = arg
    else:
        quoted = '"' + "".join("\\" + c if c in '"`$\\' else c for c in arg) + '"'
    return quoted.replace("\\", "\\\\").replace("%", "%%")


def parse_exec(line: str) -> list[str]:
    """The arguments of an ``Exec`` value written by ``exec_quote`` (the inverse; field codes are not expanded)."""
    text, i = [], 0
    while i < len(line):                                  # the string level: \\ \s \n \t \r
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            text.append({"s": " ", "n": "\n", "t": "\t", "r": "\r"}.get(line[i + 1], line[i + 1]))
            i += 2
            continue
        text.append(c)
        i += 1
    s = "".join(text).replace("%%", "%")
    args, cur, quoted, any_ = [], [], False, False
    i = 0
    while i < len(s):
        c = s[i]
        if quoted:
            if c == "\\" and i + 1 < len(s):
                cur.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                quoted = False
            else:
                cur.append(c)
        elif c == '"':
            quoted, any_ = True, True
        elif c == " ":
            if cur or any_:
                args.append("".join(cur))
            cur, any_ = [], False
        else:
            cur.append(c)
        i += 1
    if cur or any_:
        args.append("".join(cur))
    return args


def desktop_text(command: Command) -> str:
    lines = ["[Desktop Entry]",
             "Type=Application",
             "Name=" + NAME,
             "Comment=Cast local files and cloud media to a TV",
             "Exec=" + " ".join(exec_quote(a) for a in command.argv)]
    if command.cwd:
        lines.append("Path=" + command.cwd.replace("\\", "\\\\"))
    lines += ["Icon=" + NAME,
              "Terminal=false",
              "Categories=AudioVideo;Video;Player;",
              "StartupWMClass=" + NAME]
    return "\n".join(lines) + "\n"


def desktop_fields(text: str) -> dict:
    """The ``[Desktop Entry]`` group's keys, values unescaped at the string level except ``Exec``."""
    fields, group = {}, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            group = line
        elif group == "[Desktop Entry]" and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            fields[key.strip()] = value if key.strip() == "Exec" else value.replace("\\\\", "\\")
    return fields


class MenuEntry:
    """The menu entry of this machine and this running file; every outside dependency can be injected."""

    def __init__(self, platform=None, environ=None, home=None, run=subprocess.run, frozen=None,
                 executable=None, which=shutil.which, root=None, config=None, argv0=None):
        self.platform = platform or sys.platform
        self.environ = os.environ if environ is None else environ
        self.home = home or os.path.expanduser("~")
        self._run = run
        self.frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self.executable = executable or sys.executable
        self.which = which
        self.argv0 = argv0
        self.root = root
        self._config = config
        self._lock = threading.Lock()
        self._cached: dict | None = None
        self._refreshing = False

    @property
    def supported(self) -> bool:
        return self.platform == "win32" or self.platform.startswith("linux")

    # -------------------------------------------------------- what it starts
    def target(self) -> Command:
        """The command line of this file: the release, a checkout, or the pipx launcher."""
        if self.frozen:
            return Command((self.executable,))
        root = self.root if self.root is not None else checkout_root()
        if root:
            return Command((self.executable, "-m", "castlib"), root)        # checkout_root() is absolute
        launcher = self._own_launcher() or self.which(NAME)
        if launcher:
            return Command((launcher,))
        return Command((self.executable, "-m", "castlib"))

    def _own_launcher(self) -> str | None:
        """The ``cast-tv`` script that started this process, on Linux. PATH may name another one, or none:
        the old symlink install next to pipx, or a desktop session's PATH without the launcher's folder
        (row 4.7, 2026-11-05). Windows keeps ``which``: its launcher is an .exe, accepted in row 4.8."""
        if self.platform == "win32":
            return None
        arg = self.argv0 if self.argv0 is not None else (sys.argv[0] if sys.argv else "")
        if os.path.basename(arg) != NAME:
            return None
        path = os.path.abspath(arg)                    # not realpath: pipx's bin/ symlink outlives a reinstall
        return path if os.path.isfile(path) else None

    # ---------------------------------------------------------------- where
    def _data_home(self) -> str:
        return self.environ.get("XDG_DATA_HOME") or os.path.join(self.home, ".local", "share")

    def path(self) -> str:
        """Where the entry lives (whether or not it exists)."""
        if self.platform == "win32":
            appdata = self.environ.get("APPDATA") or os.path.join(self.home, "AppData", "Roaming")
            return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", NAME + ".lnk")
        return os.path.join(self._data_home(), "applications", NAME + ".desktop")

    def icon_path(self) -> str:
        """The icon file ``install()`` writes; on Windows only outside the release, which uses its own."""
        if self.platform == "win32":
            config = self._config or _config_dir()
            return os.path.join(config, NAME + ".ico")
        return os.path.join(self._data_home(), "icons", "hicolor", "256x256", "apps", NAME + ".png")

    # ---------------------------------------------------------------- state
    def state(self) -> dict:
        """``{"installed", "current", "path"}``: an entry exists, and it starts this file the way ``target()`` would."""
        path = self.path()
        if not os.path.isfile(path):
            return {"installed": False, "current": False, "path": path}
        try:
            current = self._points_here(path)
        except Exception:
            current = False
        return {"installed": True, "current": current, "path": path}

    def _points_here(self, path: str) -> bool:
        want = self.target()
        if self.platform == "win32":
            got = self._read_lnk(path)
            return (_same_path(got.get("target", ""), want.argv[0])
                    and got.get("args", "") == subprocess.list2cmdline(list(want.argv[1:]))
                    and _same_path(got.get("dir", ""), want.cwd or ""))
        with open(path, encoding="utf-8") as fh:
            fields = desktop_fields(fh.read())
        return (parse_exec(fields.get("Exec", "")) == list(want.argv)
                and (fields.get("Path") or None) == want.cwd)

    def cached(self) -> dict | None:
        """The last ``state()`` for the UI's poll; None until it is known, or where there is no menu."""
        if not self.supported:
            return None
        if self.platform != "win32":
            return self.state()                   # a small file: read it every time
        with self._lock:
            known, start = self._cached, not self._refreshing and self._cached is None
            if start:
                self._refreshing = True
        if start:
            threading.Thread(target=self._refresh, name="menu-entry", daemon=True).start()
        return known

    def _refresh(self) -> None:
        try:
            value = self.state()
        finally:
            with self._lock:
                self._refreshing = False
        with self._lock:
            self._cached = value

    def _remember(self, value: dict) -> dict:
        with self._lock:
            self._cached = value
        return value

    # ---------------------------------------------------------------- write
    def install(self) -> dict:
        """Write (or rewrite) the entry for this file; installing twice leaves one entry."""
        if not self.supported:
            raise ConfigError("menu_unsupported", "cast-tv cannot add a menu entry on this system.")
        command = self.target()
        try:
            if self.platform == "win32":
                self._write_lnk(command)
            else:
                self._write_desktop(command)
        except ConfigError:
            raise
        except Exception as e:
            raise ConfigError("menu_failed", "The menu entry could not be written: %s" % e)
        return self._remember(self.state())

    def remove(self) -> dict:
        """Delete what ``install()`` wrote and nothing else; removing twice is a no-op."""
        for path in (self.path(), self.icon_path()):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError as e:
                raise ConfigError("menu_failed", "The menu entry could not be removed: %s" % e)
        if self.platform != "win32":
            self._touch_icon_theme()
        return self._remember(self.state())

    def _write_desktop(self, command: Command) -> None:
        icon = self.icon_path()
        os.makedirs(os.path.dirname(icon), exist_ok=True)
        shutil.copyfile(ICON_PNG, icon)
        self._touch_icon_theme()
        path = self.path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(desktop_text(command))
        os.replace(tmp, path)

    def _touch_icon_theme(self) -> None:
        """Bump the theme folder's time, as ``xdg-icon-resource`` does: GNOME Shell rescans an icon theme
        only when that folder changes, not when a file lands in ``256x256/apps`` (row 4.7, 2026-11-05)."""
        try:
            os.utime(os.path.join(self._data_home(), "icons", "hicolor"))
        except OSError:
            pass                                       # the entry still works; the icon shows after a re-login

    def _powershell(self, script: str, env: dict):
        full = dict(self.environ)
        full.update(env)
        proc = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, timeout=TIMEOUT, env=full,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip() if proc.stderr else ""
            raise ConfigError("menu_failed", "PowerShell could not handle the shortcut: %s"
                              % (err.splitlines()[0] if err else "exit %s" % proc.returncode))
        return proc

    def _write_lnk(self, command: Command) -> None:
        if self.frozen:
            icon = command.argv[0]                         # the release carries the icon itself
        else:
            icon = self.icon_path()                        # neither the checkout nor pipx has a stable .ico of its own
            os.makedirs(os.path.dirname(icon), exist_ok=True)
            shutil.copyfile(ICON_ICO, icon)
        path = self.path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._powershell(LNK_WRITE, {
            "CAST_TV_LNK": path,
            "CAST_TV_LNK_TARGET": command.argv[0],
            "CAST_TV_LNK_ARGS": subprocess.list2cmdline(list(command.argv[1:])),
            "CAST_TV_LNK_DIR": command.cwd or "",
            "CAST_TV_LNK_ICON": icon + ",0",
            # the release hides its console itself; python and the pipx launcher cannot, so theirs starts minimised
            "CAST_TV_LNK_STYLE": str(SW_SHOWNORMAL if self.frozen else SW_SHOWMINNOACTIVE),
        })

    def _read_lnk(self, path: str) -> dict:
        proc = self._powershell(LNK_READ, {"CAST_TV_LNK": path})
        text = proc.stdout.decode("utf-8", "replace").strip() if proc.stdout else ""
        return json.loads(text) if text else {}


def _same_path(a: str, b: str) -> bool:
    if not a or not b:
        return a == b
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def _config_dir() -> str:
    from castlib import config
    return config.config_dir()


menu_entry = MenuEntry()


def cached() -> dict | None:
    """``menu_entry.cached()``, looked up at call time so the test suite can swap the entry."""
    return menu_entry.cached()


def install() -> dict:
    return menu_entry.install()


def remove() -> dict:
    return menu_entry.remove()
