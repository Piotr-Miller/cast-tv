"""castlib.processes: which processes run from where, and when that cannot be known (s16-faster-start)."""
import os
import types

import pytest

from castlib import processes
from castlib.processes import Denied, Gone, IncompleteListing


class FakeWin:
    """pid -> image path, or Gone / Denied; pid -> whether its owner is us."""

    def __init__(self, images, owners):
        self.images, self._owners = images, owners

    def pids(self):
        return list(self.images)

    def owners(self):
        return self._owners

    def image(self, pid):
        value = self.images[pid]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_windows_lists_images_and_skips_what_ended():
    api = FakeWin({10: r"C:\a\cast-tv.exe", 11: Gone(), 12: r"C:\b\x.exe"}, {})
    assert processes.running_images(platform="win32", win=api) == [(10, r"C:\a\cast-tv.exe"), (12, r"C:\b\x.exe")]


def test_windows_skips_another_users_refusal():
    api = FakeWin({4: Denied(5), 10: r"C:\a\cast-tv.exe"}, {4: False})
    assert processes.running_images(platform="win32", win=api) == [(10, r"C:\a\cast-tv.exe")]


def test_windows_refusal_of_our_user_makes_the_list_incomplete():
    api = FakeWin({20: Denied(5), 10: r"C:\a\cast-tv.exe"}, {20: True})
    with pytest.raises(IncompleteListing):
        processes.running_images(platform="win32", win=api)


def test_windows_refusal_of_a_process_that_then_ended_is_skipped():
    api = FakeWin({20: [Denied(5), Gone()]}, {})           # the second image query confirms exit
    assert processes.running_images(platform="win32", win=api) == []


def test_windows_refusal_with_an_unknown_owner_is_not_ours():
    """Owner decision 2026-11-19: unelevated, protected and service processes have no owner and refuse;
    a refusal means not ours, because Windows lets a user query its own processes (measured)."""
    api = FakeWin({4: Denied(5), 20: Denied(5), 10: r"C:\a\cast-tv.exe"}, {4: None})
    assert processes.running_images(platform="win32", win=api) == [(10, r"C:\a\cast-tv.exe")]


def _native_win(*, error, handle=0):
    """Exercise the ctypes wrapper on either CI OS, without loading a Windows DLL."""
    import ctypes
    api = processes._Win32.__new__(processes._Win32)
    api.ctypes = types.SimpleNamespace(get_last_error=lambda: error, byref=ctypes.byref,
                                      create_unicode_buffer=ctypes.create_unicode_buffer)
    api.w = types.SimpleNamespace(DWORD=ctypes.c_uint32)
    closed = []
    api.k32 = types.SimpleNamespace(OpenProcess=lambda *a: handle,
                                   QueryFullProcessImageNameW=lambda *a: False,
                                   CloseHandle=closed.append)
    return api, closed


@pytest.mark.parametrize("error,expected", [(87, Gone), (5, Denied), (8, IncompleteListing)])
def test_windows_open_process_classifies_errors(error, expected):
    api, closed = _native_win(error=error)
    with pytest.raises(expected):
        api.image(20)
    assert closed == []


@pytest.mark.parametrize("error,expected", [(5, Denied), (6, IncompleteListing)])
def test_windows_image_query_classifies_errors_and_closes_handle(error, expected):
    api, closed = _native_win(error=error, handle=123)
    with pytest.raises(expected):
        api.image(20)
    assert closed == [123]


def test_windows_native_refusal_with_an_unknown_owner_is_skipped():
    api, _ = _native_win(error=5)
    api.owners = lambda: {}
    api.pids = lambda: [20]
    assert processes.running_images(platform="win32", win=api) == []


def test_windows_native_refusal_of_our_own_sid_is_incomplete():
    api, _ = _native_win(error=5)
    api.owners = lambda: {20: True}
    api.pids = lambda: [20]
    with pytest.raises(IncompleteListing, match="ours but refused"):
        processes.running_images(platform="win32", win=api)


def test_windows_other_users_api_error_is_not_an_access_refusal():
    api, _ = _native_win(error=8)
    api.owners = lambda: {20: False}
    api.pids = lambda: [20]
    with pytest.raises(IncompleteListing, match="OpenProcess failed"):
        processes.running_images(platform="win32", win=api)


def _native_owners(rows, *, succeeds=True):
    import ctypes

    class ProcessInfo(ctypes.Structure):
        _fields_ = [("SessionId", ctypes.c_uint32), ("ProcessId", ctypes.c_uint32),
                    ("pProcessName", ctypes.c_wchar_p), ("pUserSid", ctypes.c_void_p)]

    api, _ = _native_win(error=5)
    api.ctypes.POINTER = ctypes.POINTER
    api.ProcessInfo = ProcessInfo
    data = (ProcessInfo * len(rows))(*(ProcessInfo(1, pid, None, sid) for pid, sid in rows))
    freed = []

    def enumerate_owners(server, reserved, version, info, count):
        assert server is None and reserved == 0 and version == 1
        if not succeeds:
            return False
        ctypes.cast(info, ctypes.POINTER(ctypes.POINTER(ProcessInfo)))[0] = data
        count._obj.value = len(rows)
        return True

    def equal(a, b):
        assert not freed                              # SID pointers are valid only until WTSFreeMemory
        return a == b

    api.wts = types.SimpleNamespace(WTSEnumerateProcessesW=enumerate_owners, WTSFreeMemory=freed.append)
    api.security = types.SimpleNamespace(EqualSid=equal)
    return api, freed


def test_windows_owner_snapshot_compares_sids_and_frees_the_buffer():
    api, freed = _native_owners([(os.getpid(), 11), (20, 11), (21, 22), (22, None)])
    assert api.owners() == {os.getpid(): True, 20: True, 21: False, 22: None}
    assert len(freed) == 1


@pytest.mark.parametrize("rows", [[], [(os.getpid(), None)]])
def test_windows_unknown_current_owner_is_incomplete_and_frees_the_buffer(rows):
    api, freed = _native_owners(rows)
    with pytest.raises(IncompleteListing, match="owner is unknown"):
        api.owners()
    assert len(freed) == 1


def test_windows_failed_owner_enumeration_is_incomplete():
    api, freed = _native_owners([], succeeds=False)
    with pytest.raises(IncompleteListing, match="WTSEnumerateProcessesW failed"):
        api.owners()
    assert freed == []


def test_windows_owner_enumeration_failure_propagates_from_the_listing():
    api, _ = _native_owners([], succeeds=False)
    api.image = lambda pid: (_ for _ in ()).throw(Denied(5))
    api.pids = lambda: [20]
    with pytest.raises(IncompleteListing):
        processes.running_images(platform="win32", win=api)


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
