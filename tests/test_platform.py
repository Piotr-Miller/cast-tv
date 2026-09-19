import socket
import sys
import threading
import types

import pytest

from castlib import discovery, platform
from castlib.platform import ConsoleClose, ExecutionState, StayAwake, SystemdInhibit
from castlib.platform import default_backend as real_default_backend   # bound before conftest swaps it
from castlib.platform import end_on_console_close as real_end_on_console_close   # likewise


# ------------------------------------------------------------- discovery
class _FakeSocket:
    made: list = []

    def __init__(self, family, kind):
        self.opts, self.bound, self.sent, self.inbox, self.closed = {}, None, [], [], False
        self.fail_send = False
        _FakeSocket.made.append(self)

    def setsockopt(self, level, opt, value):
        self.opts[(level, opt)] = value

    def bind(self, addr):
        self.bound = addr
        if addr[0] == "10.8.0.2":
            self.fail_send = True                       # a VPN adapter with no multicast route

    def setblocking(self, flag):
        pass

    def sendto(self, data, addr):
        if self.fail_send:
            raise OSError("Network is unreachable")
        self.sent.append((data, addr))
        if self.bound and self.bound[0] == "192.168.1.5":   # only the Wi-Fi reaches the TVs
            answer = b"HTTP/1.1 200 OK\r\nLOCATION: http://%s:9197/dmr\r\n\r\n"
            self.inbox += [(answer % b"192.168.1.20", ("192.168.1.20", 1900)),
                           (answer % b"192.168.1.20", ("192.168.1.20", 1900)),   # the same TV again
                           (answer % b"192.168.1.21", ("192.168.1.21", 1900)),
                           (b"HTTP/1.1 200 OK\r\n\r\n", ("192.168.1.30", 1900))]  # no LOCATION: ignored

    def recvfrom(self, n):
        return self.inbox.pop(0)

    def close(self):
        self.closed = True


def _fake_select(rlist, wlist, xlist, timeout):
    return [s for s in rlist if s.inbox], [], []


IFACES = [("Wi-Fi", "192.168.1.5"), ("vEthernet (WSL)", "172.20.0.1"), ("VPN", "10.8.0.2")]


@pytest.mark.parametrize("plat, reuse", [("linux", True), ("win32", False)])
def test_multicast_socket_per_interface(monkeypatch, plat, reuse):
    _FakeSocket.made = []
    monkeypatch.setattr(discovery, "_new_socket", _FakeSocket)
    monkeypatch.setattr(discovery, "_select", _fake_select)
    found, report = discovery.msearch(timeout=0.05, interfaces=IFACES, platform=plat)
    assert found == {"192.168.1.20": "http://192.168.1.20:9197/dmr",
                     "192.168.1.21": "http://192.168.1.21:9197/dmr"}
    assert report == [{"name": "Wi-Fi", "ip": "192.168.1.5", "responses": 2},
                      {"name": "vEthernet (WSL)", "ip": "172.20.0.1", "responses": 0},
                      {"name": "VPN", "ip": "10.8.0.2", "responses": 0,
                       "error": "Network is unreachable"}]
    assert len(_FakeSocket.made) == 3
    for sock, (_name, ip) in zip(_FakeSocket.made, IFACES):
        assert sock.opts[(socket.IPPROTO_IP, socket.IP_MULTICAST_IF)] == socket.inet_aton(ip)
        assert sock.bound == (ip, 0)
        assert ((socket.SOL_SOCKET, socket.SO_REUSEADDR) in sock.opts) is reuse
        assert sock.closed
    assert _FakeSocket.made[0].sent == [(discovery.MSEARCH, ("239.255.255.250", 1900))]


def test_no_interface_falls_back_to_the_default_route(monkeypatch):
    _FakeSocket.made = []
    monkeypatch.setattr(discovery, "_new_socket", _FakeSocket)
    monkeypatch.setattr(discovery, "_select", _fake_select)
    monkeypatch.setattr(discovery, "lan_interfaces", lambda: [])
    found, report = discovery.msearch(timeout=0.02)
    assert found == {} and report == [{"name": "default route", "ip": None, "responses": 0}]
    sock = _FakeSocket.made[0]
    assert sock.bound is None and (socket.IPPROTO_IP, socket.IP_MULTICAST_IF) not in sock.opts


def test_lan_interfaces_skip_loopback_and_link_local(monkeypatch):
    ip = lambda a: types.SimpleNamespace(ip=a)
    adapters = [types.SimpleNamespace(nice_name="lo", name="lo", ips=[ip("127.0.0.1"), ip(("::1", 0, 0))]),
                types.SimpleNamespace(nice_name="Wi-Fi", name="{GUID}", ips=[ip("192.168.1.5"), ip("169.254.3.4")])]
    fake = types.SimpleNamespace(get_adapters=lambda: adapters)
    monkeypatch.setitem(__import__("sys").modules, "ifaddr", fake)
    assert discovery.lan_interfaces() == [("Wi-Fi", "192.168.1.5")]


def test_discover_hands_the_report_to_the_caller(monkeypatch):
    monkeypatch.setattr(discovery, "msearch", lambda timeout: ({}, [{"name": "Wi-Fi", "ip": "192.168.1.5", "responses": 0}]))
    report = []
    assert discovery.discover(report=report) == []
    assert report == [{"name": "Wi-Fi", "ip": "192.168.1.5", "responses": 0}]


# -------------------------------------------------------------- firewall
def test_firewall_hint_text(monkeypatch):
    monkeypatch.setattr(platform, "sys", types.SimpleNamespace(platform="win32"))
    assert platform.firewall_hint(8895) == ('netsh advfirewall firewall add rule name="cast-tv" '
                                            "dir=in action=allow protocol=TCP localport=8895")
    monkeypatch.setattr(platform, "sys", types.SimpleNamespace(platform="linux"))
    assert platform.firewall_hint(8895) == "sudo firewall-cmd --add-port=8895/tcp"


# ------------------------------------------------------------ stay awake
class _Recorder:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def acquire(self):
        self.calls.append("acquire")
        if self.fail:
            raise OSError("no logind here")

    def release(self):
        self.calls.append("release")


def test_stay_awake_lifecycle():
    rec = _Recorder()
    awake = StayAwake(rec)
    awake.start()                               # a show
    awake.start()                               # its first cast
    assert rec.calls == ["acquire"] and awake.active
    awake.stop()
    assert rec.calls == ["acquire"] and awake.active
    awake.stop()
    assert rec.calls == ["acquire", "release"] and not awake.active
    awake.stop()                                # one stop too many changes nothing
    assert rec.calls == ["acquire", "release"]
    awake.start(); awake.start()
    awake.close()                               # Ctrl+C mid-show lets go at once
    assert rec.calls == ["acquire", "release", "acquire", "release"] and not awake.active
    awake.close()
    assert rec.calls[-1] == "release" and len(rec.calls) == 4
    failing = StayAwake(_Recorder(fail=True))
    failing.start()                             # a broken backend never breaks a cast
    failing.stop()


class _FakeProc:
    def __init__(self, cmd, **kw):
        self.cmd, self.kw, self.waited = cmd, kw, False
        self.stdin = types.SimpleNamespace(closed=False)
        self.stdin.close = lambda: setattr(self.stdin, "closed", True)

    def wait(self, timeout=None):
        assert self.stdin.closed                # EOF on the pipe is what ends it
        self.waited = True


def test_systemd_inhibit_holds_a_child_until_release():
    spawned = []
    backend = SystemdInhibit(which=lambda name: "/usr/bin/" + name,
                             popen=lambda cmd, **kw: spawned.append(_FakeProc(cmd, **kw)) or spawned[-1])
    backend.acquire()
    backend.acquire()                           # already held: no second child
    assert len(spawned) == 1
    proc = spawned[0]
    assert proc.cmd[:3] == ["systemd-inhibit", "--what=idle:sleep", "--who=cast-tv"]
    assert proc.cmd[-1] == "cat" and proc.kw["stdin"] is not None
    backend.release()
    assert proc.waited
    backend.release()                           # nothing held: nothing to do
    missing = SystemdInhibit(which=lambda name: None, popen=lambda *a, **k: pytest.fail("spawned"))
    missing.acquire()
    missing.release()


def test_execution_state_is_held_by_one_thread():
    calls = []
    k32 = types.SimpleNamespace(SetThreadExecutionState=lambda flags: calls.append(
        (threading.current_thread().name, flags)) or 1)
    backend = ExecutionState(kernel32=k32)
    backend.acquire()
    thread = backend._thread
    assert calls == [("stay-awake", 0x80000000 | 0x1 | 0x2)]
    backend.release()
    assert not thread.is_alive()
    assert calls[-1] == ("stay-awake", 0x80000000)   # reset on the thread that set it


def test_default_backend_per_platform(monkeypatch):
    for plat, cls in (("win32", ExecutionState), ("linux", SystemdInhibit), ("darwin", platform.NullBackend)):
        monkeypatch.setattr(platform, "sys", types.SimpleNamespace(platform=plat))
        assert type(real_default_backend()) is cls


def test_casts_and_shows_hold_it_and_close_releases(app, tmp_path):
    from tests.conftest import wait_for
    from tests.test_supervisor import _photo
    rec = _Recorder()
    app.stay_awake = StayAwake(rec)
    c = app.cast(_photo(tmp_path, "a.jpg"))
    wait_for(lambda: c.sent.is_set() and app.stay_awake.active)
    assert rec.calls == ["acquire"]
    app.stop()
    wait_for(lambda: not app.stay_awake.active)
    assert rec.calls == ["acquire", "release"]
    show = app.show([_photo(tmp_path, "b.jpg"), _photo(tmp_path, "c.jpg")], interval=2)
    wait_for(lambda: show.current is not None and show.current.sent.is_set())
    assert rec.calls[-1] == "acquire" and app.stay_awake.active
    app.close()
    assert rec.calls[-1] == "release" and not app.stay_awake.active


# ------------------------------------------------------- a closed console
def test_console_close_interrupts_main_and_waits_out_the_grace():
    calls = []
    handler = ConsoleClose(interrupt=lambda: calls.append("interrupt"),
                           sleep=lambda s: calls.append(("sleep", s)))
    for event in (2, 5, 6):                         # close, logoff, shutdown
        calls.clear()
        assert handler.handle(event) is True
        assert calls == ["interrupt", ("sleep", ConsoleClose.GRACE)]
    for event in (0, 1):                            # Ctrl+C, Ctrl+Break: Python's own handler
        calls.clear()
        assert handler.handle(event) is False
        assert calls == []


@pytest.mark.skipif(sys.platform != "win32", reason="ctypes.WINFUNCTYPE is Windows-only")
def test_console_close_registers_a_callback_that_outlives_install():
    registered = []
    k32 = types.SimpleNamespace(SetConsoleCtrlHandler=lambda cb, add: registered.append((cb, add)) or 1)
    handler = ConsoleClose(kernel32=k32, interrupt=lambda: None, sleep=lambda s: None)
    assert handler.install() is True
    (cb, add), = registered
    assert add is True and cb is handler._callback  # held, or ctypes would free it
    assert cb(2) and not cb(0)


def test_end_on_console_close_only_on_windows_and_once(monkeypatch):
    installed = []

    class Fake(ConsoleClose):
        def install(self):
            installed.append(self)
            return True

    monkeypatch.setattr(platform, "ConsoleClose", Fake)
    monkeypatch.setattr(platform, "_console_close", None)
    monkeypatch.setattr(platform, "sys", types.SimpleNamespace(platform="linux"))
    assert real_end_on_console_close() is False and installed == []   # SIGHUP covers it there
    monkeypatch.setattr(platform, "sys", types.SimpleNamespace(platform="win32"))
    assert real_end_on_console_close() is True
    assert real_end_on_console_close() is False                      # already installed
    assert len(installed) == 1


# ------------------------------------------------- a managed laptop's firewall
# the rule an employer's Intune pushed to the laptop of row 7.3's first attempt
MDM_RULE = {"name": "Block InBound connection Public Private", "profile": "Private, Public"}


def test_blocking_rule_matches_the_current_profile_only():
    assert platform.blocking_rule({"profiles": ["Private"], "rules": [MDM_RULE]}) == MDM_RULE["name"]
    assert platform.blocking_rule({"profiles": ["Public"], "rules": [MDM_RULE]}) == MDM_RULE["name"]
    assert platform.blocking_rule({"profiles": ["DomainAuthenticated"], "rules": [MDM_RULE]}) is None
    domain = {"name": "Corp", "profile": "Domain"}
    assert platform.blocking_rule({"profiles": ["DomainAuthenticated"], "rules": [domain]}) == "Corp"
    assert platform.blocking_rule({"profiles": [], "rules": [{"name": "All", "profile": "Any"}]}) == "All"
    assert platform.blocking_rule({"profiles": ["Public"], "rules": []}) is None
    assert platform.blocking_rule({}) is None


def _policy(stdout=b"", fail=None):
    asked = []

    def run(cmd, **kw):
        asked.append(cmd)
        if fail:
            raise fail
        return types.SimpleNamespace(stdout=stdout, returncode=0)

    return platform.FirewallPolicy(run=run, platform="win32"), asked


def test_firewall_policy_asks_powershell_once_and_reads_the_rule():
    policy, asked = _policy(b'{"profiles":["Private"],"rules":[{"name":"Block InBound connection '
                            b'Public Private","profile":"Private, Public"}]}\r\n')
    assert policy.blocked(wait=5) == MDM_RULE["name"]
    assert policy.blocked(wait=5) == MDM_RULE["name"]
    assert len(asked) == 1 and asked[0][0] == "powershell.exe"
    assert "-PolicyStore ActiveStore" in asked[0][-1]


def test_firewall_policy_unanswered_means_not_blocked():
    for policy, _ in (_policy(fail=FileNotFoundError("powershell.exe")), _policy(b"not json"),
                      _policy(b"")):
        assert policy.blocked(wait=5) is None
    linux = platform.FirewallPolicy(run=lambda *a, **k: pytest.fail("ran"), platform="linux")
    assert linux.blocked(wait=5) is None


def test_firewall_advice_names_the_rule_or_gives_the_command(monkeypatch):
    blocked, _ = _policy(b'{"profiles":["Public"],"rules":[{"name":"Block InBound connection Public Private",'
                         b'"profile":"Private, Public"}]}')
    monkeypatch.setattr(platform, "firewall_policy", blocked)
    advice = platform.firewall_advice(8895, wait=5)
    assert MDM_RULE["name"] in advice and "no allow rule can override it" in advice
    assert "TCP port 8895" in advice and "netsh" not in advice
    open_, _ = _policy(b'{"profiles":["Public"],"rules":[]}')
    monkeypatch.setattr(platform, "firewall_policy", open_)
    monkeypatch.setattr(platform, "sys", types.SimpleNamespace(platform="win32"))
    assert platform.firewall_advice(8895, wait=5) == (
        "Open the port, in PowerShell as administrator:  " + platform.firewall_hint(8895))


# ------------------------------------------------ the release binary's CA bundle
# what the bundled OpenSSL, built on Ubuntu, reports as its default paths
UBUNTU_OPENSSL = types.SimpleNamespace(openssl_cafile="/usr/lib/ssl/cert.pem",
                                       openssl_capath="/usr/lib/ssl/certs")
# Fedora 44, where this was found: no ca-bundle.crt, the bundle is a link under /etc/ssl
FEDORA_FILES = {"/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem", "/etc/pki/tls/certs"}
RHEL_FILES = {"/etc/pki/tls/certs/ca-bundle.crt", "/etc/pki/tls/certs"}
DEBIAN_FILES = {"/etc/ssl/certs/ca-certificates.crt"}


def _binary(monkeypatch, plat="linux", frozen=True):
    monkeypatch.setattr(platform, "sys", types.SimpleNamespace(platform=plat, frozen=frozen))
    monkeypatch.setattr(platform, "ssl", types.SimpleNamespace(
        get_default_verify_paths=lambda: UBUNTU_OPENSSL))


def test_ca_bundle_fedora_gets_its_own(monkeypatch):
    _binary(monkeypatch)
    env = {}
    assert platform.use_system_ca_bundle(env, FEDORA_FILES.__contains__) == \
        "/etc/ssl/certs/ca-certificates.crt"
    assert env == {"SSL_CERT_FILE": "/etc/ssl/certs/ca-certificates.crt"}


def test_ca_bundle_older_fedora_and_rhel(monkeypatch):
    _binary(monkeypatch)
    env = {}
    assert platform.use_system_ca_bundle(env, RHEL_FILES.__contains__) == \
        "/etc/pki/tls/certs/ca-bundle.crt"
    assert env == {"SSL_CERT_FILE": "/etc/pki/tls/certs/ca-bundle.crt"}


def test_ca_bundle_debian_layout_without_openssl_default(monkeypatch):
    _binary(monkeypatch)
    env = {}
    assert platform.use_system_ca_bundle(env, DEBIAN_FILES.__contains__) == \
        "/etc/ssl/certs/ca-certificates.crt"
    assert env["SSL_CERT_FILE"] == "/etc/ssl/certs/ca-certificates.crt"


def test_ca_bundle_ubuntu_keeps_openssl_default(monkeypatch):
    _binary(monkeypatch)
    env = {}
    ubuntu = DEBIAN_FILES | {"/usr/lib/ssl/certs"}
    assert platform.use_system_ca_bundle(env, ubuntu.__contains__) is None
    assert env == {}


def test_ca_bundle_user_setting_wins(monkeypatch):
    _binary(monkeypatch)
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        env = {key: "/home/me/corp-ca.pem"}
        assert platform.use_system_ca_bundle(env, FEDORA_FILES.__contains__) is None
        assert env == {key: "/home/me/corp-ca.pem"}


def test_ca_bundle_none_found_changes_nothing(monkeypatch):
    _binary(monkeypatch)
    env = {}
    assert platform.use_system_ca_bundle(env, lambda path: False) is None
    assert env == {}


def test_ca_bundle_only_in_the_frozen_linux_build(monkeypatch):
    for plat, frozen in (("linux", False), ("win32", True), ("darwin", True)):
        _binary(monkeypatch, plat, frozen)
        env = {}
        assert platform.use_system_ca_bundle(env, FEDORA_FILES.__contains__) is None
        assert env == {}
