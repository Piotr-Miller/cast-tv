import re
import sys

import pytest

from castlib.discovery import interface_addresses, local_addresses


def _fib_trie_local_addresses():
    """IPv4 addresses the kernel lists as LOCAL: an independent source of truth on Linux."""
    try:
        with open("/proc/net/fib_trie", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    found = set()
    for prev, line in zip(lines, lines[1:]):
        if "/32 host LOCAL" in line:
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", prev)
            if m:
                found.add(m.group(1))
    return found


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="fib_trie is Linux-only")
def test_allowed_hosts_cover_every_interface_address():
    kernel = _fib_trie_local_addresses()
    if not kernel:
        pytest.skip("no readable fib_trie")
    assert kernel <= interface_addresses()
    assert kernel <= local_addresses()


def test_local_addresses_always_include_loopback_names():
    assert {"localhost", "127.0.0.1", "::1"} <= local_addresses()


def test_select_and_persist(app, monkeypatch, tmp_path):
    import json
    import os
    from castlib import app as app_module
    from castlib.app import Settings
    from tests.test_api import _json
    monkeypatch.setattr(app_module, "control_urls",
                        lambda ip: ("http://%s:9197/avt" % ip, "") if ip != "192.0.2.1" else (None, None))
    monkeypatch.setattr(app_module, "local_ip", lambda ip: "127.0.0.1")
    monkeypatch.setattr(app_module, "renderer_name", lambda ip: "Described")
    app.tvs = [{"ip": "192.0.2.9", "name": "Bedroom", "avt": "http://192.0.2.9:9197/avt"}]
    status, _, d = _json(app.base_url, "POST", "/api/tv/select", {"ip": "192.0.2.9"})
    assert status == 200
    assert d["tv"] == {"ip": "192.0.2.9", "name": "Bedroom", "state": "ready"}
    assert app.tv_control() == "http://192.0.2.9:9197/avt"
    settings = os.path.join(str(tmp_path / "config"), "settings.json")
    with open(settings, encoding="utf-8") as fh:
        assert json.load(fh)["tv"] == "192.0.2.9"
    assert Settings(settings).get("tv") == "192.0.2.9"        # a restart reads it back
    status, _, d = _json(app.base_url, "POST", "/api/tv/select", {"ip": "192.0.2.1"})
    assert status == 503 and d["error"]["code"] == "tv_no_avtransport"
    assert app.tv["ip"] == "192.0.2.9"                        # a failed select changes nothing
    status, _, d = _json(app.base_url, "POST", "/api/tv/select", {"ip": ""})
    assert status == 400
    # an address discovery never listed gets its name from the device description
    app.tvs = []
    status, _, d = _json(app.base_url, "POST", "/api/tv/select", {"ip": "192.0.2.7"})
    assert status == 200 and d["tv"]["name"] == "Described"


def test_select_rejects_anything_but_ipv4_before_any_request(app, monkeypatch):
    from castlib import app as app_module
    from tests.test_api import _json
    asked = []
    monkeypatch.setattr(app_module, "control_urls", lambda ip: asked.append(ip) or (None, None))
    monkeypatch.setattr(app_module, "renderer_name", lambda ip: asked.append(ip) or None)
    before = app.tv
    for bad in ("example.com/x?", "192.0.2.9:9197", "http://192.0.2.9", "::1", "fe80::1", "192.0.2"):
        status, _, d = _json(app.base_url, "POST", "/api/tv/select", {"ip": bad})
        assert status == 400 and d["error"]["code"] == "bad_ip", bad
    assert asked == []                                        # nothing was fetched
    assert app.tv == before and app.settings.get("tv") is None   # nothing was saved


def test_rediscovery_keeps_saved_tv(app, monkeypatch):
    from castlib import app as app_module
    from tests.test_api import _json
    monkeypatch.setattr(app_module, "local_ip", lambda ip: "127.0.0.1")
    app.settings.set("tv", "192.0.2.9")                       # an explicit choice, now switched off
    app.tv = None
    monkeypatch.setattr(app_module, "discover", lambda: [("192.0.2.5", "http://192.0.2.5/avt", "Kitchen")])
    status, _, d = _json(app.base_url, "POST", "/api/tv/discover")
    assert status == 200 and d["tv"]["ip"] == "192.0.2.5"     # usable now
    assert app.settings.get("tv") == "192.0.2.9"              # but the saved choice survives
    app.tv = None
    monkeypatch.setattr(app_module, "discover", lambda: [("192.0.2.5", "http://192.0.2.5/avt", "Kitchen"),
                                                          ("192.0.2.9", "http://192.0.2.9/avt", "Bedroom")])
    status, _, d = _json(app.base_url, "POST", "/api/tv/discover")
    assert d["tv"]["ip"] == "192.0.2.9"                       # back on: preferred again
    assert app.settings.get("tv") == "192.0.2.9"
    # with nothing saved yet, the first discovered TV is remembered as before
    app.settings.set("tv", None)
    app.tv = None
    status, _, d = _json(app.base_url, "POST", "/api/tv/discover")
    assert d["tv"]["ip"] == "192.0.2.5" and app.settings.get("tv") == "192.0.2.5"


def test_discover_keeps_the_preferred_tv(app, monkeypatch):
    from castlib import app as app_module
    from tests.test_api import _json
    found = [("192.0.2.5", "http://192.0.2.5/avt", "Kitchen"), ("127.0.0.1", "http://127.0.0.1:1/avt", "Fake TV")]
    monkeypatch.setattr(app_module, "discover", lambda: found)
    monkeypatch.setattr(app_module, "local_ip", lambda ip: "127.0.0.1")
    status, _, d = _json(app.base_url, "POST", "/api/tv/discover")
    assert status == 200
    assert [t["ip"] for t in d["tvs"]] == ["192.0.2.5", "127.0.0.1"]
    assert d["tv"]["ip"] == "127.0.0.1"                        # the one already selected stays
    monkeypatch.setattr(app_module, "discover", lambda: [])
    app.tv = None
    status, _, d = _json(app.base_url, "POST", "/api/tv/discover")
    assert d["tvs"] == [] and d["tv"]["state"] == "none"


def test_addrinuse_attaches_to_running_instance(app, monkeypatch, upstream):
    from castlib.app import AlreadyRunning, App
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    with pytest.raises(AlreadyRunning) as info:
        App.start(app.server.port, browser=True)
    assert info.value.url == "http://127.0.0.1:%d/ui/" % app.server.port
    # a port held by something that is not cast-tv is a plain bind failure
    other = upstream(b"<html>", ctype="text/html")
    with pytest.raises(OSError) as err:
        App.start(other.server_address[1], browser=False)
    assert not isinstance(err.value, AlreadyRunning)
