"""The stdlib WebSocket client and the DevTools session over it, against the fake endpoint."""
import json
import threading

import pytest

from castlib.auth import cdp
from tests.conftest import wait_for
from tests.fakes_cdp import FakeBrowser, cookie


@pytest.fixture
def endpoint():
    fake = FakeBrowser(cookies=[cookie("eyJone")]).serve()
    try:
        yield fake
    finally:
        fake.stop()


def test_handshake_sends_no_origin(endpoint):
    session = cdp.connect(endpoint.ws_url)
    try:
        (headers,) = endpoint.requests
        assert "origin" not in headers                             # Chrome 111+ refuses a foreign Origin; none is sent
        assert headers["upgrade"] == "websocket" and headers["sec-websocket-version"] == "13"
        assert headers["connection"] == "Upgrade" and len(headers["sec-websocket-key"]) == 24
        assert headers["host"] == "127.0.0.1:%d" % endpoint.port
        assert session.call("Storage.getCookies") == {"cookies": [cookie("eyJone")]}
    finally:
        session.close()


def test_client_frames_are_masked_and_unmasked_by_the_server(endpoint):
    endpoint.handlers["Echo.size"] = lambda params: {"size": len(params.get("blob", "")), "first": params.get("blob", "")[:3]}
    session = cdp.connect(endpoint.ws_url)
    try:
        assert session.call("Echo.size", {"blob": "abc"}) == {"size": 3, "first": "abc"}
        big = "y" * 70000                                           # a 64-bit length on the client's side
        assert session.call("Echo.size", {"blob": big}) == {"size": 70000, "first": "yyy"}
        mid = "z" * 1000                                            # and a 16-bit one
        assert session.call("Echo.size", {"blob": mid}) == {"size": 1000, "first": "zzz"}
        assert endpoint.masked == [True, True, True]
        assert [m["method"] for m in endpoint.received] == ["Echo.size"] * 3
        assert endpoint.received[1]["params"]["blob"] == big        # unmasked to the bytes that were sent
        assert [m["id"] for m in endpoint.received] == [1, 2, 3]
    finally:
        session.close()


def test_long_and_split_answers_are_joined(endpoint):
    session = cdp.connect(endpoint.ws_url)
    try:
        endpoint.pad = 70000                                        # 64-bit length from the server
        answer = session.call("Storage.getCookies")
        assert answer["padding"] == "x" * 70000 and answer["cookies"] == [cookie("eyJone")]
        endpoint.pad = 1000                                         # 16-bit length
        assert len(session.call("Storage.getCookies")["padding"]) == 1000
        endpoint.pad = 0
        endpoint.split = 3                                          # a text frame and two continuations
        assert session.call("Storage.getCookies") == {"cookies": [cookie("eyJone")]}
        assert endpoint.polls == 3
    finally:
        session.close()


def test_ping_gets_a_pong_and_events_are_discarded(endpoint):
    endpoint.ping_first = True
    session = cdp.connect(endpoint.ws_url)
    try:
        assert session.call("Storage.getCookies")["cookies"] == [cookie("eyJone")]
        wait_for(lambda: endpoint.pongs == [b"still there?"])   # read by the fake's thread a moment later
        # an event (no id) and a stray answer (another id) before the real answer are skipped
        def noisy(params):
            return {"ok": True}
        endpoint.handlers["Noisy.call"] = noisy
        real_reply = endpoint._reply

        def reply(conn, answer):
            from tests.fakes_cdp import _frame
            conn.sendall(_frame(0x1, json.dumps({"method": "Target.targetCreated", "params": {}}).encode()))
            conn.sendall(_frame(0x1, json.dumps({"id": 999, "result": {"stray": True}}).encode()))
            real_reply(conn, answer)
        endpoint._reply = reply
        assert session.call("Noisy.call") == {"ok": True}
    finally:
        session.close()


def test_protocol_error_keeps_the_session(endpoint):
    session = cdp.connect(endpoint.ws_url)
    try:
        with pytest.raises(cdp.CdpError) as err:
            session.call("No.such")
        assert err.value.code == "protocol" and "No.such" in err.value.message and "wasn't found" in err.value.message
        assert not session.closed
        assert session.call("Storage.getCookies")["cookies"] == [cookie("eyJone")]
    finally:
        session.close()


def test_server_close_raises_closed(endpoint):
    session = cdp.connect(endpoint.ws_url)
    endpoint.drop_connections()                                     # a close frame, then the socket
    with pytest.raises(cdp.CdpError) as err:
        session.call("Storage.getCookies")
    assert err.value.code == "closed" and session.closed
    with pytest.raises(cdp.CdpError) as err:
        session.call("Storage.getCookies")                          # and it stays closed
    assert err.value.code == "closed"
    session.close()                                                 # a no-op now
    # an EOF without a close frame is the same
    session = cdp.connect(endpoint.ws_url)
    endpoint.drop_connections(close_frame=False)
    with pytest.raises(cdp.CdpError) as err:
        session.call("Storage.getCookies")
    assert err.value.code == "closed"
    # the process gone: nothing listens
    endpoint.end(0)
    with pytest.raises(cdp.CdpError) as err:
        cdp.connect(endpoint.ws_url, timeout=1)
    assert err.value.code == "unreachable"


def test_call_timeout(endpoint):
    session = cdp.connect(endpoint.ws_url)
    endpoint.stall = True
    with pytest.raises(cdp.CdpError) as err:
        session.call("Storage.getCookies", timeout=0.2)
    assert err.value.code == "timeout" and "0.2" in err.value.message and session.closed
    endpoint.stall = False
    # the handshake has its own timeout
    quiet = threading.Event()
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        with pytest.raises(cdp.CdpError) as err:
            cdp.connect("ws://127.0.0.1:%d/devtools/browser/x" % srv.getsockname()[1], timeout=0.2)
        assert err.value.code == "timeout"
    finally:
        srv.close()
        quiet.set()
    with pytest.raises(cdp.CdpError) as err:
        cdp.connect("http://127.0.0.1:1/")
    assert err.value.code == "bad_url"


def test_a_plain_http_answer_is_refused(endpoint):
    """The endpoint answers 404 (a wrong path) instead of 101: refused, and the socket is not left open."""
    with pytest.raises(cdp.CdpError) as err:
        cdp.connect("ws://127.0.0.1:%d/not/the/browser" % endpoint.port)
    assert err.value.code == "refused" and "404" in err.value.message
