"""The static UI: five files, exact match, nothing else."""
from tests.conftest import request


def test_static_exact_match_only(server):
    srv, base = server
    status, headers, body, conn = request(base, "GET", "/ui/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert headers["Content-Length"] == str(len(body))
    assert b"cast-tv" in body and b"x-data" in body
    for path, ctype in (("/ui/app.js", "application/javascript"),
                        ("/ui/style.css", "text/css"),
                        ("/ui/alpine.min.js", "application/javascript"),
                        ("/ui/qrcode.js", "application/javascript")):
        status, headers, body, _ = request(base, "GET", path, conn=conn)
        assert status == 200, path
        assert headers["Content-Type"].startswith(ctype)
        assert headers["Content-Length"] == str(len(body)) and body
    for path in ("/ui/index.html", "/ui/../castlib/server.py", "/ui/app.js/", "/ui/x", "/ui/qrcode.mjs",
                 "/ui/%2e%2e/pyproject.toml", "/ui/APP.JS"):
        status, headers, body, _ = request(base, "GET", path, conn=conn)
        assert status == 404, path
        assert headers["Content-Type"].startswith("application/json")
    status, headers, _, _ = request(base, "GET", "/ui", conn=conn)
    assert status == 302 and headers["Location"] == "/ui/"
    s1, h1, b1, _ = request(base, "HEAD", "/ui/", conn=conn)
    assert s1 == 200 and b1 == b"" and h1["Content-Length"] == str(len(open_ui_bytes()))
    status, _, _, _ = request(base, "POST", "/ui/", conn=conn)
    assert status == 404


def test_root_redirects(server):
    srv, base = server
    status, headers, _, _ = request(base, "GET", "/")
    assert status == 302 and headers["Location"] == "/ui/"


def test_ui_needs_a_local_host_header(server):
    srv, base = server
    status, _, _, _ = request(base, "GET", "/ui/", {"Host": "evil.example"})
    assert status == 403


def test_ui_is_self_contained():
    """The LAN UI loads nothing from the internet: no fonts, no preconnect, no CDN."""
    from castlib.server import UI_DIR
    import os
    for name in ("index.html", "style.css", "app.js"):
        with open(os.path.join(UI_DIR, name), encoding="utf-8") as fh:
            text = fh.read()
        assert "https://" not in text and "http://" not in text, name
        assert "preconnect" not in text, name


def test_ui_has_the_gopro_gate_and_list():
    """Phase 4: the paste gate, the expired banner over the list and the variant chooser are in the markup."""
    from castlib.server import UI_DIR
    import os
    with open(os.path.join(UI_DIR, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    assert 'saveToken(tab)' in html and 'x-model="tokenInput"' in html
    assert 'class="banner warn expired"' in html and 'listVisible(tab)' in html
    assert 'class="chooser"' in html and "castNow(it, v.quality)" in html
    assert 'loadList(tab, true)' in html
    with open(os.path.join(UI_DIR, "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    assert "'/api/sources/' + name + '/list'" in js and "x-html" not in html and "innerHTML" not in js


def test_ui_offers_a_share_link_before_any_sign_in():
    """The link field sits on the Google Photos gate too; a link lists without a sign-in."""
    from castlib.server import UI_DIR
    import os
    with open(os.path.join(UI_DIR, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    gate = html[html.index('<section class="gate">'):html.index('<template x-if="listVisible(tab)">')]
    assert 'addLink()' in gate and 'x-model="linkInput"' in gate and 'linkNote' in gate
    assert '<template x-if="!connected(tab)">' in html and 'connected(tab) && !pickWaiting()' in html
    with open(os.path.join(UI_DIR, "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    assert "s.detail.picks > 0" in js and "this.linkNote = String" in js


def _ui_text(name):
    from castlib.server import UI_DIR
    import os
    with open(os.path.join(UI_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def test_gopro_gate_offers_the_window_first():
    """S-13: the GoPro gate is the window step; the paste form sits only inside a fallback block; the banner offers the window again."""
    import re
    html, js = _ui_text("index.html"), _ui_text("app.js")
    assert '<template x-if="gate(tab).window">' in html and "connectStep(tab) === 'browser'" in html
    assert 'openWindow(tab)' in html and "connect(name, { fresh: true })" in js
    forms = [m.start() for m in re.finditer(r"saveToken\(tab\)", html)]
    assert len(forms) == 2                                   # the gate's copy and the banner's copy
    for pos in forms:                                        # each under the nearest x-if, which is the fallback rule
        opener = html.rfind('<template x-if="', 0, pos)
        tag = html[opener:html.index(">", opener)]
        assert "fallback(tab)" in tag, tag
    start = html.index('class="banner warn expired"')
    banner = html[start:html.index("<h2>", start)]
    assert "gate(tab).again" in banner and "openWindow(tab)" in banner and "fallback(tab)" in banner
    assert "again: 'Open gopro.com again'" in js and "cta: 'Open gopro.com'" in js and "window: true" in js
    assert "paste: true" not in js and "steps: [" not in js and "gate(tab).paste" not in html


def test_gopro_gate_texts():
    """S-13: the decided wording; the phone line comes from the server's note; no "GoPro sign-in", no hours."""
    from castlib.sources.gopro import ON_HOST_NOTE
    html, js = _ui_text("index.html"), _ui_text("app.js")
    assert ("body: 'A gopro.com window opens on the computer running cast-tv. Sign in in that window. "
            "cast-tv then uses that browser session to access your GoPro media and closes the window.'") in js
    assert "expired: 'cast-tv couldn’t access your GoPro media with this session.'" in js
    assert "expiredBody: 'Open gopro.com again to reconnect.'" in js
    assert "A gopro.com window is open on the computer running cast-tv. Sign in in that window; this page continues by itself." in html
    block = html[html.index("connectStep(tab) === 'browser'"):html.index('<template x-if="!connecting(tab)">')]
    assert "source(tab).detail.note" in block and "cancelConnect(tab)" in block and "expires_in" in block
    assert ON_HOST_NOTE == ("The gopro.com window opens on the computer running cast-tv, not on the device "
                            "showing this page.")
    assert "'gopro.com window open…'" in js and "'reconnect needed'" in js
    for text in (js, html):
        assert "GoPro sign-in" not in text and "lasts a few hours" not in text


def test_gopro_steps_are_not_duplicated_in_the_ui():
    """S-13: the devtools steps have one source (gopro.TOKEN_STEPS); the UI lists them from detail.fallback."""
    html, js = _ui_text("index.html"), _ui_text("app.js")
    assert "F12" not in js and "F12" not in html and "gp_access_token" not in js
    assert "fallback(tab).steps" in html and "fallbackText(tab)" in html


def drive_ui(steps, scripts=()):
    """Run the page's component in node against scripted answers (tests/ui_driver.js); skipped without node.

    ``scripts`` are other files under /ui/ the page loads before app.js, such as qrcode.js."""
    import json
    import os
    import shutil
    import subprocess
    import pytest
    from castlib.server import UI_DIR
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    driver = os.path.join(os.path.dirname(__file__), "ui_driver.js")
    done = subprocess.run([node, driver, os.path.join(UI_DIR, "app.js")] + [os.path.join(UI_DIR, s) for s in scripts],
                          input=json.dumps({"steps": steps}),
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _status(gopro):
    return {"tv": None, "tvs": [], "interfaces": [], "cast": None, "show": None, "sources": {"gopro": gopro},
            "session": [], "errors": 0, "settings": {"interval": 8}}


def test_gopro_expired_list_survives_a_failed_reconnect():
    """S-13 review F1: a round from the expired banner that ends without a session keeps the last list
    under the banner; the list is fetched again only once the source is connected again."""
    connected = {"state": "connected", "detail": {"stored": True, "age": "session captured just now"}}
    expired = {"state": "expired", "detail": {"stored": True, "age": "session captured 9 h ago",
                                              "error": {"code": "token_rejected", "message": "GoPro rejected the token (401)"}}}
    connecting = {"state": "connecting", "detail": {"stored": True, "step": "browser", "expires_in": 299, "note": "n"}}
    out = drive_ui([
        {"answer": {"path": "/api/sources/gopro/list", "body": {"items": [{"source": "gopro", "id": "a", "name": "A.MP4", "kind": "video"}]}}},
        {"status": _status(connected)}, {"call": "refresh"},
        {"read": "listVisible", "args": ["gopro"]},                       # the list is on screen
        {"status": _status(expired)}, {"call": "refresh"},
        {"read": "listVisible", "args": ["gopro"]},                       # expired: the banner sits over that list
        {"answer": {"path": "/api/sources/gopro/connect", "body": dict(connecting, step="browser")}},
        {"status": _status(connecting)},
        {"call": "openWindow", "args": ["gopro"]},                        # "Open gopro.com again"
        {"read": "listVisible", "args": ["gopro"]},                       # the gate shows the waiting block
        {"status": _status(expired)}, {"call": "refresh"},                # the window was closed, cancelled or timed out
        {"read": "listVisible", "args": ["gopro"]},                       # the banner over the last list again
        {"read": "items", "args": ["gopro"]},
        {"status": _status(connected)}, {"call": "refresh"},              # a session was captured
        {"read": "listVisible", "args": ["gopro"]},
    ])
    on_screen, over_list, gate, kept, items, again = out["reads"]
    assert on_screen is True and over_list is True and gate is False
    assert kept is True, "a failed reconnect must not drop the list the banner sits over"
    assert [it["id"] for it in items] == ["a"]
    assert again is True
    assert "POST /api/sources/gopro/connect" in out["requests"]
    assert out["requests"].count("GET /api/sources/gopro/list") == 2      # once connected, once reconnected


def test_gphotos_links_stay_usable_after_the_consent_expires():
    """A share link needs no consent: with the Google consent expired, the field is still offered (on
    the gate and under the list) and the pasted links still list, under the expired banner."""
    html = _ui_text("index.html")
    forms = [line for line in html.splitlines() if 'class="paste linkpaste"' in line]
    assert len(forms) == 2
    for form in forms:
        assert "expired" not in form, form
    expired = {"state": "expired", "detail": {"stored": True, "picks": 1, "picks_seq": 1,
                                              "error": {"code": "refresh_rejected", "message": "Connect again."}}}
    status = dict(_status({"state": "disconnected", "detail": {"stored": False}}))
    status["sources"] = {"gphotos": expired}
    out = drive_ui([
        {"answer": {"path": "/api/sources/gphotos/list", "body": {"items": [
            {"source": "gphotos", "id": "link-1", "name": "QT9rQWxXYDDfSpKD8", "kind": "photo"}]}}},
        {"status": status},
        {"call": "refresh"}, {"call": "ensureList", "args": ["gphotos"]},   # what opening the tab runs
        {"read": "listVisible", "args": ["gphotos"]},
        {"read": "items", "args": ["gphotos"]},
    ])
    visible, items = out["reads"]
    assert "GET /api/sources/gphotos/list" in out["requests"]
    assert visible is True and [it["id"] for it in items] == ["link-1"]


def _host_status(host, window):
    return dict(_status({"state": "disconnected", "detail": {"stored": False}}), host=host, window=window)


def test_quit_control_only_in_a_host_tab():
    """Quit shows in a browser tab on the computer running cast-tv; not in the window, not on the phone."""
    html = _ui_text("index.html")
    assert 'x-show="canQuit()"' in html and 'quitApp()' in html and 'x-text="quitNote"' in html
    assert 'x-show="offline && !ended"' in html
    out = drive_ui([
        {"status": _host_status(True, False)}, {"call": "refresh"}, {"read": "canQuit"},
        {"status": _host_status(True, True)}, {"call": "refresh"}, {"read": "canQuit"},
        {"status": _host_status(False, False)}, {"call": "refresh"}, {"read": "canQuit"},
    ])
    assert out["reads"] == [True, False, False]


def test_quit_keeps_its_message_across_polls():
    """Quit's answer is its own state (lessons.md): no poll overwrites it, and none is sent once it ended."""
    out = drive_ui([
        {"status": _host_status(True, False)}, {"call": "refresh"},
        {"answer": {"path": "/api/quit", "body": {"error": {"code": "internal", "message": "cast-tv hit an internal error: x"}}}},
        {"call": "quitApp"}, {"call": "refresh"},
        {"read": "quitNote"}, {"read": "ended"}, {"read": "canQuit"},
        {"answer": {"path": "/api/quit", "body": {"ok": True}}},
        {"call": "quitApp"},
        {"read": "quitNote"}, {"read": "ended"}, {"read": "canQuit"},
        {"call": "refresh"}, {"call": "refresh"},
        {"read": "quitNote"}, {"read": "offline"},
    ])
    failed, failed_ended, still_offered, note, ended, offered, kept, offline = out["reads"]
    assert failed == "cast-tv hit an internal error: x" and failed_ended is False and still_offered is True
    assert note == "cast-tv has ended; you can close this tab." and ended is True and offered is False
    assert kept == note and offline is False
    assert out["requests"].count("POST /api/quit") == 2
    assert out["requests"][-1] == "POST /api/quit"         # nothing polled after it ended


def open_ui_bytes():
    from castlib.server import UI_DIR
    import os
    with open(os.path.join(UI_DIR, "index.html"), "rb") as fh:
        return fh.read()


ADDRESSES = ["http://localhost:8895/ui/", "http://192.168.50.198:8895/ui/", "http://172.21.80.1:8895/ui/"]


def _phone_status(host=True, addresses=ADDRESSES, blocked=None, advice=""):
    return dict(_host_status(host, True), addresses=list(addresses), firewall_blocked=blocked,
                firewall_advice=advice)


def test_phone_panel_lists_lan_addresses():
    """S-12 Phase 3: every LAN address in the server's order, the default route first; localhost dropped."""
    html = _ui_text("index.html")
    assert html.index('src="/ui/qrcode.js"') < html.index('src="/ui/app.js"')
    panel = html[html.index('<section class="phone"'):html.index("</section>", html.index('<section class="phone"'))]
    assert "Open on your phone" in panel and 'x-for="a in phoneAddresses()"' in panel
    assert "copy(a, 'address')" in panel and "toggleQr(a)" in panel and "qrSvg(a).d" in panel
    out = drive_ui([
        {"status": _phone_status(addresses=ADDRESSES + ["http://127.0.0.1:8895/ui/"])}, {"call": "refresh"},
        {"read": "phoneAddresses"},
    ])
    assert out["reads"] == [ADDRESSES[1:]]


def test_phone_panel_qr_codes():
    """Each address gets its own QR code, from the vendored qrcode.js, toggled one at a time."""
    out = drive_ui([
        {"status": _phone_status()}, {"call": "refresh"},
        {"call": "toggleQr", "args": [ADDRESSES[1]]}, {"read": "qrOpen"},
        {"read": "qrSvg", "args": [ADDRESSES[1]]}, {"read": "qrSvg", "args": [ADDRESSES[2]]},
        {"call": "toggleQr", "args": [ADDRESSES[2]]}, {"read": "qrOpen"},
        {"call": "toggleQr", "args": [ADDRESSES[2]]}, {"read": "qrOpen"},
    ], scripts=["qrcode.js"])
    open1, wifi, other, open2, closed = out["reads"]
    assert (open1, open2, closed) == (ADDRESSES[1], ADDRESSES[2], "")
    for qr in (wifi, other):
        modules = qr["size"] - 8                          # a 4-cell quiet zone on each side
        assert modules >= 21 and (modules - 17) % 4 == 0   # a QR version's side: 17 + 4 * version
        assert qr["d"].startswith("M4 4h1v1h-1z")           # the top-left finder pattern starts at the quiet zone
    assert wifi["d"] != other["d"]
    plain = drive_ui([{"status": _phone_status()}, {"call": "refresh"}, {"read": "qrSvg", "args": [ADDRESSES[1]]}])
    assert plain["reads"] == [None]                       # no qrcode.js: no code, no error


def test_phone_panel_only_on_localhost():
    """The phone's page (not on this machine's loopback) shows no phone panel."""
    out = drive_ui([
        {"status": _phone_status(host=True)}, {"call": "refresh"}, {"read": "phoneVisible"},
        {"status": _phone_status(host=False)}, {"call": "refresh"}, {"read": "phoneVisible"},
    ])
    assert out["reads"] == [True, False]


def test_phone_panel_offline():
    """With no LAN address the panel says so, instead of an empty list."""
    html = _ui_text("index.html")
    assert "This computer has no network address. Connect it to Wi-Fi or Ethernet." in html
    assert '<template x-if="!phoneAddresses().length">' in html
    out = drive_ui([{"status": _phone_status(addresses=ADDRESSES[:1])}, {"call": "refresh"},
                    {"read": "phoneAddresses"}, {"read": "phoneVisible"}])
    assert out["reads"] == [[], True]


def test_firewall_banner_follows_status():
    """The block-all policy banner shows the server's advice while firewall_blocked is set, and goes with it."""
    html = _ui_text("index.html")
    assert 'x-show="firewallBlocked()"' in html and 'x-text="status.firewall_advice"' in html
    advice = "This computer's firewall policy blocks every incoming connection"
    out = drive_ui([
        {"status": _phone_status(blocked=None)}, {"call": "refresh"}, {"read": "firewallBlocked"},
        {"status": _phone_status(blocked="Block all", advice=advice)}, {"call": "refresh"},
        {"read": "firewallBlocked"},
        {"status": _phone_status(blocked=None)}, {"call": "refresh"}, {"read": "firewallBlocked"},
    ])
    assert out["reads"] == [False, True, False]
