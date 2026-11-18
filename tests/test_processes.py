"""castlib.processes: which processes run from where, and when that cannot be known (s16-faster-start)."""
import os
import types

import pytest

from castlib import processes
from castlib.processes import Denied, Gone, IncompleteListing


class FakeWin:
    """pid -> image path, or Gone / Denied; pid -> session."""

    def __init__(self, images, sessions, mine=1):
        self.images, self.sessions, self.mine = images, sessions, mine

    def pids(self):
        return list(self.images)

    def session(self, pid):
        if pid == os.getpid():
            return self.mine
        return self.sessions.get(pid)

    def image(self, pid):
        value = self.images[pid]
        if isinstance(value, Exception):
            raise value
        return value


def test_windows_lists_images_and_skips_what_ended():
    api = FakeWin({10: r"C:\a\cast-tv.exe", 11: Gone(), 12: r"C:\b\x.exe"}, {})
    assert processes.running_images(platform="win32", win=api) == [(10, r"C:\a\cast-tv.exe"), (12, r"C:\b\x.exe")]


def test_windows_skips_another_sessions_refusal():
    api = FakeWin({4: Denied(5), 10: r"C:\a\cast-tv.exe"}, {4: 0})
    assert processes.running_images(platform="win32", win=api) == [(10, r"C:\a\cast-tv.exe")]


def test_windows_refusal_in_this_session_makes_the_list_incomplete():
    api = FakeWin({20: Denied(5), 10: r"C:\a\cast-tv.exe"}, {20: 1})
    with pytest.raises(IncompleteListing):
        processes.running_images(platform="win32", win=api)


def test_windows_refusal_of_a_process_that_then_ended_is_skipped():
    api = FakeWin({20: Denied(5)}, {})                     # no session any more: it is gone
    assert processes.running_images(platform="win32", win=api) == []


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="Linux owners")
def test_linux_reads_exe_links_and_judges_refusals_by_owner(tmp_path, monkeypatch):
    for pid in ("10", "11", "12", "self"):
        (tmp_path / pid).mkdir()
    links = {str(tmp_path / "10" / "exe"): "/opt/cast-tv-linux-x64"}
    refused = {str(tmp_path / "12" / "exe")}

    def readlink(path):
        if path in links:
            return links[path]
        if path in refused:
            raise PermissionError(path)
        raise FileNotFoundError(path)                     # 11: a kernel thread

    owners = {str(tmp_path / "12"): os.getuid() + 1}
    real_stat = os.stat
    monkeypatch.setattr(processes.os, "readlink", readlink)
    monkeypatch.setattr(processes.os, "stat",
                        lambda p: types.SimpleNamespace(st_uid=owners[p]) if p in owners else real_stat(p))
    assert processes.running_images(platform="linux", proc_root=str(tmp_path)) == [(10, "/opt/cast-tv-linux-x64")]
    owners[str(tmp_path / "12")] = os.getuid()               # ours, yet unreadable
    with pytest.raises(IncompleteListing):
        processes.running_images(platform="linux", proc_root=str(tmp_path))


def test_linux_without_proc_is_incomplete(tmp_path):
    with pytest.raises(IncompleteListing):
        processes.running_images(platform="linux", proc_root=str(tmp_path / "missing"))


def test_unknown_platform_is_incomplete():
    with pytest.raises(IncompleteListing):
        processes.running_images(platform="darwin")
