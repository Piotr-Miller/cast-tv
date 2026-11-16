"""Release smoke shutdown must never terminate a session it did not start."""
import importlib.util
import json
from pathlib import Path
import types

import pytest


@pytest.fixture
def smoke():
    path = Path(__file__).resolve().parents[1] / "packaging" / "smoke.py"
    spec = importlib.util.spec_from_file_location("cast_tv_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Process:
    pid = 1234

    def __init__(self, exited=False):
        self.returncode = 0 if exited else None
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, **kwargs):
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -1


@pytest.mark.parametrize("exited,instance", [
    (True, {"id": "old", "pid": 1234}),
    (False, {"id": "other", "pid": 5678, "parent_pid": 9012}),
    (False, None),
])
def test_unowned_smoke_responder_never_receives_quit(smoke, monkeypatch, exited, instance):
    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("Quit sent without ownership"))
    killed = []
    monkeypatch.setattr(smoke, "kill_tree", lambda proc: killed.append(proc.pid))
    assert smoke.stop(Process(exited), 8099, instance) is False
    assert killed == [1234]


@pytest.mark.parametrize("child", [False, True])
def test_owned_smoke_quit_is_conditional_on_the_instance(smoke, monkeypatch, child):
    proc = Process()
    instance = {"id": "this-instance", "pid": 4321 if child else proc.pid, "parent_pid": proc.pid if child else 42}
    requests = []
    class Connection:
        sock = object()

        def request(self, method, path, **kwargs):
            requests.append((method, path, kwargs))

        def getresponse(self):
            body = json.dumps({"instance": instance}).encode() if len(requests) == 1 else b'{}'
            return types.SimpleNamespace(status=200, read=lambda: body)

        def close(self):
            pass

    monkeypatch.setattr(smoke.http.client, "HTTPConnection", lambda *a, **kw: Connection())
    monkeypatch.setattr(smoke, "answers", lambda port: False)
    assert smoke.stop(proc, 45678, instance)
    assert [r[:2] for r in requests] == [("GET", "/api/status"), ("POST", "/api/quit")]
    assert json.loads(requests[1][2]["body"]) == {"instance": "this-instance"}
    assert proc.killed is False


@pytest.mark.parametrize("payload,closed", [({"instance": {"id": "replacement", "pid": 1234}}, False),
                                           ({}, False), ([], False),
                                           ({"instance": {"id": "this", "pid": 1234}}, True)])
def test_quit_does_not_reconnect_or_touch_a_replacement(smoke, monkeypatch, payload, closed):
    calls = []

    class Connection:
        sock = None if closed else object()

        def request(self, method, path, **kwargs):
            calls.append(method)

        def getresponse(self):
            return types.SimpleNamespace(status=200, read=lambda: json.dumps(payload).encode())

        def close(self):
            pass

    monkeypatch.setattr(smoke.http.client, "HTTPConnection", lambda *a, **kw: Connection())
    assert smoke.quit_owned(Process(), 45678, {"id": "this", "pid": 1234}) is False
    assert calls == ["GET"]


def test_main_rejects_another_server_on_the_selected_port(smoke, monkeypatch):
    proc = Process()
    monkeypatch.setattr(smoke.os.path, "getsize", lambda path: 1)
    monkeypatch.setattr(smoke, "run", lambda *args: smoke.WINDOW + "\nGoogle Photos client: built in\nGoPro window: chrome")
    monkeypatch.setattr(smoke, "free_port", lambda: 45678)
    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *a, **kw: proc)
    monkeypatch.setattr(smoke, "get", lambda *args: (200, json.dumps({"instance": {"id": "other", "pid": 5678}}).encode()))
    monkeypatch.setattr(smoke, "kill_tree", lambda p: p.kill())
    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("unrelated server received Quit"))
    with pytest.raises(SystemExit, match="another process"):
        smoke.main("fixture.exe")
    assert proc.killed


def test_window_smoke_rejects_fontconfig_diagnostics(smoke, monkeypatch):
    result = types.SimpleNamespace(returncode=0, stdout="window-check: qtwebengine OK", stderr="Fontconfig warning: invalid attribute")
    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **kw: result)
    with pytest.raises(SystemExit, match="Fontconfig diagnostics"):
        smoke.run("fixture", "--window-check")
