"""The GoPro source on the ``Source`` contract, against a scripted api.gopro.com and a scripted hand-off."""
import json
import os
import re
import stat
import threading
import time
import urllib.parse

import pytest

from castlib import config, net
from castlib.auth import browser
from castlib.errors import AuthError, ConfigError, NotMedia
from castlib.sources import gopro
from castlib.sources.gopro import GoProSource
from tests.conftest import wait_for

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "gopro")


class FakeHandoff:
    """``browser.Handoff`` stand-in: the test decides what the gopro.com window yields.

    ``start(verify, timeout)`` records the verifier and returns at once, as the
    engine does; the source's thread then blocks in ``wait()``. The test drives
    the outcome from its own thread the way the engine's poll would:
    ``offer(value)`` hands a cookie value to the verifier once (an ``AuthError``
    is a refusal, remembered so the value is never offered again; a ``True``
    fills ``result`` and ends the round), ``close_window()``, ``fail()`` and
    ``time_out()`` end it with the engine's own errors. ``cancel()`` is what
    the source calls; a verification in flight still decides the round, as in
    the engine, which is how a late capture is produced.
    """

    def __init__(self):
        self.verify = None
        self.timeout = None
        self.verified = []                       # every value handed to the verifier, in order
        self.cancelled = 0
        self.result = None
        self.error = None
        self.tried = set()
        self._verifying = False
        self._done = threading.Event()

    def start(self, verify, timeout=browser.HANDOFF_TIMEOUT):
        if self.verify is not None:
            raise RuntimeError("a hand-off starts once")
        self.verify, self.timeout = verify, timeout
        return self

    def wait(self):
        self._done.wait()
        if self.error is not None:
            raise self.error
        return self.result or {}

    def cancel(self):
        self.cancelled += 1
        if self._done.is_set() or self._verifying:
            return
        self._end(AuthError("cancelled", "The gopro.com window was cancelled.", source="gopro"))

    # ------------------------------------------------------ the test's side
    def offer(self, value, session=False, expires=1790000000.0):
        """A ``gp_access_token`` value appeared in the window: verified once; ``True`` when it was adopted."""
        assert self.verify is not None, "the round has not started"
        if value in self.tried or self._done.is_set():
            return False
        self.tried.add(value)
        self.verified.append(value)
        self._verifying = True
        try:
            try:
                good = bool(self.verify(value))
            except AuthError:
                good = False
        finally:
            self._verifying = False
        if good:
            self.result = {"token": value, "captured_at": time.time(),
                           "cookie": {"session": session, "expires": -1 if session else expires}}
            self._done.set()
        return good

    def close_window(self):
        self._end(AuthError("browser_closed", "The gopro.com window was closed before a session appeared.",
                            source="gopro"))

    def fail(self, code, message):
        self._end(AuthError(code, message, source="gopro"))

    def time_out(self):
        self._end(AuthError("browser_timeout", "No gopro.com session appeared within 5 minutes; the window was closed.",
                            source="gopro"))

    def _end(self, err):
        if not self._done.is_set():
            self.error = err
            self._done.set()


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


class FakeGoPro:
    """``net.fetch`` and ``probe_media`` stand-ins: one good token, recorded fixtures, fresh signatures."""

    def __init__(self, cdn="https://cdn.test"):
        self.good = "eyJgood"
        self.cdn = cdn             # what the fixtures' https://cdn.test becomes
        self.calls = []            # every URL fetched
        self.probes = []           # every URL probed
        self.refuse = set()        # probe answers "not media" for these
        self.sig = 0
        self.before_answer = None  # callable(url, status, token): runs before an answer is returned
        self.tokens = []           # the bearer of every call, in order

    def fetch(self, url, op=None, headers=None, limit=0):
        status, body, final = self._answer(url, headers)
        if self.before_answer is not None:
            self.before_answer(url, status, (headers or {}).get("Authorization", "")[7:])
        return status, body, final

    def _answer(self, url, headers):
        self.calls.append(url)
        bearer = (headers or {}).get("Authorization", "")[7:]
        self.tokens.append(bearer)
        if bearer != self.good:
            return 401, '{"error": "unauthorized"}', url
        parsed = urllib.parse.urlparse(url)
        if parsed.path == "/media/search":
            q = urllib.parse.parse_qs(parsed.query)
            data = json.loads(_fixture("search.json"))
            per_page = int(q.get("per_page", ["100"])[0])
            page = int(q.get("page", ["1"])[0])
            media = data["_embedded"]["media"]
            data["_embedded"]["media"] = media[(page - 1) * per_page:page * per_page]
            return 200, json.dumps(data), url
        m = re.match(r"^/media/([^/]+)$", parsed.path)
        if m:                                       # GET /media/{id}: the full entry, or 404
            for x in json.loads(_fixture("search.json"))["_embedded"]["media"]:
                if x["id"] == m.group(1):
                    return 200, json.dumps(x), url
            return 404, '{"error": "not found"}', url
        m = re.match(r"^/media/([^/]+)/download$", parsed.path)
        if m:
            media_id = m.group(1)
            labels = urllib.parse.parse_qs(parsed.query).get("labels", [None])[0]
            if labels == "large":
                if media_id.startswith(("vid", "edit")):
                    body = _fixture("download_video_large.json").replace("vid-heavy", media_id)
                else:
                    body = '{"filename": "x", "_embedded": {"variations": [], "files": [], "sidecar_files": [], "sprites": []}}'
            elif media_id.startswith("vid"):
                body = _fixture("download_video.json").replace("vid-heavy", media_id)
            elif media_id.startswith("pho"):
                body = _fixture("download_photo.json")
            elif media_id.startswith("burst"):
                body = _fixture("download_burst.json")
            elif media_id.startswith("live"):
                body = _fixture("download_livephoto.json")
            elif media_id.startswith("edit"):
                body = _fixture("download_edit.json")
            else:
                return 404, '{"error": "not found"}', url
            self.sig += 1
            return 200, body.replace("sig=1", "sig=%d" % self.sig).replace("https://cdn.test", self.cdn), url
        return 404, "{}", url

    def probe(self, url, headers=None, opener=None, kinds=("video",)):
        self.probes.append(url)
        if url.split("?")[0] in self.refuse:
            return None
        path = urllib.parse.urlparse(url).path
        if path.endswith(".mp4"):
            return ("video", "binary/octet-stream", 1000) if "video" in kinds else None
        if path.endswith(".jpg"):
            # the CDN labels a source JPEG binary/octet-stream (probed 2026-09-12); the real
            # probe_media accepts that by extension, and so does this stand-in
            return ("photo", "binary/octet-stream" if "/source/" in path else "image/jpeg", 1000) \
                if "photo" in kinds else None
        return None


def use_fake_handoffs(monkeypatch, fake):
    """Every ``browser.Handoff()`` the source creates is a ``FakeHandoff``, collected in ``fake.handoffs``."""
    fake.handoffs = []

    def make():
        h = FakeHandoff()
        fake.handoffs.append(h)
        return h
    monkeypatch.setattr(browser, "Handoff", make)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = FakeGoPro()
    monkeypatch.setattr(net, "fetch", f.fetch)
    monkeypatch.setattr(gopro, "probe_media", f.probe)
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.setattr(config, "_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("GOPRO_TOKEN", raising=False)
    use_fake_handoffs(monkeypatch, f)
    return f


def _round(src, fake, params=None):
    """Start a round and return its ``FakeHandoff``."""
    d = src.connect({"fresh": True} if params is None else params)
    assert d["step"] == "browser" and d["state"] == "connecting"
    return fake.handoffs[-1]


def _sidecar():
    with open(gopro.session_file(), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- the gate
def test_status_before_and_after_connect(fake):
    src = GoProSource()
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    with pytest.raises(AuthError) as err:
        src.list()                                            # nothing stored: no call can be made
    assert err.value.code == "no_token"
    src.connect({"token": " " + fake.good + "\n"})            # pasted with whitespace
    s = src.status()
    assert s["state"] == "connected"
    assert s["detail"]["stored"] and s["detail"]["stored_at"] and s["detail"]["verified_at"]
    assert s["detail"]["age"] == "token stored just now"
    assert os.name != "posix" or oct(os.stat(gopro.token_file()).st_mode & 0o777) == "0o600"
    assert fake.calls[-1].startswith("https://api.gopro.com/media/search?") and "per_page=1&" in fake.calls[-1]
    # a stored token is not "connected" until it is verified in this process
    fresh = GoProSource()
    s = fresh.status()
    assert s["state"] == "disconnected" and s["detail"]["stored"] and s["detail"]["stored_at"]
    fresh.connect({})                                         # verify what is stored
    assert fresh.status()["state"] == "connected"
    fresh.disconnect()
    assert fresh.status() == {"state": "disconnected", "detail": {"stored": False}}
    assert not os.path.exists(gopro.token_file())


def test_env_token_is_replaced_by_a_verified_paste(fake, monkeypatch):
    """p4 review F1: the whole scenario - expired env token, paste, list/thumb/resolve on the paste, disconnect."""
    monkeypatch.setenv("GOPRO_TOKEN", "eyJexpired-env")
    src = GoProSource()
    s = src.status()
    assert s["state"] == "disconnected" and s["detail"]["stored"] and s["detail"]["age"] is None
    with pytest.raises(AuthError):
        src.connect({})                                       # verify the env token: 401
    assert src.status()["state"] == "expired"
    src.connect({"token": fake.good})                         # a paste replaces the session credential
    assert src.status()["state"] == "connected" and src.status()["detail"]["age"]
    src.list()
    src.thumb("vid-heavy")
    src.resolve("vid-light").resolve()
    assert fake.tokens[-3:] == [fake.good] * 3                # list, thumb, resolve all used the paste
    assert src.status()["state"] == "connected"
    src.disconnect()
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    assert not os.path.exists(gopro.token_file())
    with pytest.raises(AuthError) as err:
        src.list()                                            # no fallback to GOPRO_TOKEN in this process
    assert err.value.code == "no_token"
    assert fake.tokens[-1] == fake.good                       # nothing was sent with the env token
    assert gopro.token() == "eyJexpired-env"                  # the CLI / a new process still sees it
    assert GoProSource().status()["detail"]["stored"]


def test_stale_401_cannot_expire_a_fresh_connection(fake):
    """p4 review F2: an old-token 401 that lands after a reconnect is ignored."""
    src = GoProSource()
    src.connect({"token": fake.good})
    old = fake.good
    fake.good = "eyJrotated"                                   # the old token dies
    held, release = threading.Event(), threading.Event()

    def hold(url, status, bearer):
        if bearer == old and status == 401:
            held.set()
            release.wait(5)
    fake.before_answer = hold
    outcome = {}

    def stale_list():
        try:
            src.list()
        except AuthError as e:
            outcome["error"] = e.code
    t = threading.Thread(target=stale_list)
    t.start()
    assert held.wait(5)                                       # the old request has its 401, not yet delivered
    fake.before_answer = None
    src.connect({"token": fake.good})                         # a fresh paste, verified and adopted
    assert src.status()["state"] == "connected"
    release.set()
    t.join(5)
    assert outcome["error"] == "token_rejected"
    assert src.status()["state"] == "connected"               # the stale 401 changed nothing


def test_answer_after_disconnect_changes_nothing(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    held, release = threading.Event(), threading.Event()

    def hold(url, status, bearer):
        if "/media/search" in url and status == 200 and "per_page=100" in url:
            held.set()
            release.wait(5)
    fake.before_answer = hold
    t = threading.Thread(target=lambda: src.list())
    t.start()
    assert held.wait(5)
    fake.before_answer = None
    src.disconnect()
    release.set()
    t.join(5)
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}


def test_older_success_cannot_clear_a_newer_expiry(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    held, release = threading.Event(), threading.Event()

    def hold(url, status, bearer):
        if "/media/search" in url and status == 200 and "per_page=100" in url:
            held.set()
            release.wait(5)
    fake.before_answer = hold
    t = threading.Thread(target=lambda: src.list())
    t.start()
    assert held.wait(5)                                       # a success is in flight
    fake.before_answer = None
    fake.good = "eyJrotated"
    with pytest.raises(AuthError):
        src.thumb("vid-heavy")                                # a newer request: 401 → expired
    assert src.status()["state"] == "expired"
    release.set()
    t.join(5)
    assert src.status()["state"] == "expired"                 # the older success did not restore it
    fake.good = "eyJgood"
    src.connect({"token": fake.good})                         # only a verification does
    assert src.status()["state"] == "connected"


def test_401_flips_to_expired(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    fake.good = "eyJrotated"                                   # the browser session ended
    with pytest.raises(AuthError) as err:
        src.list()
    assert err.value.code == "token_rejected"
    s = src.status()
    assert s["state"] == "expired" and s["detail"]["error"]["code"] == "token_rejected"
    assert s["detail"]["stored"]                              # the old token stays until replaced
    with pytest.raises(AuthError):
        src.connect({"token": "eyJgood"})                     # the same token pasted again: still 401
    assert src.status()["state"] == "expired"
    src.connect({"token": fake.good})                         # a new paste restores it
    assert src.status()["state"] == "connected"


def test_401_over_the_api(app, fake):
    from tests.test_api import _json
    status, _, d = _json(app.base_url, "POST", "/api/sources/gopro/connect", {"token": "eyJwrong"})
    assert status == 401 and d["error"]["code"] == "token_rejected"
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["sources"]["gopro"] == {"state": "disconnected", "detail": {"stored": False}}   # nothing saved
    status, _, d = _json(app.base_url, "POST", "/api/sources/gopro/connect", {"token": fake.good})
    assert status == 200 and d["state"] == "connected" and d["detail"]["age"]
    fake.good = "eyJrotated"                                   # the stored token dies
    status, _, d = _json(app.base_url, "GET", "/api/sources/gopro/list")
    assert status == 401 and d["error"]["code"] == "token_rejected"
    _, _, s = _json(app.base_url, "GET", "/api/status")
    assert s["sources"]["gopro"]["state"] == "expired"
    status, _, d = _json(app.base_url, "POST", "/api/sources/gopro/connect", {"token": fake.good})
    assert status == 200 and d["state"] == "connected"
    status, _, d = _json(app.base_url, "GET", "/api/sources/gopro/list")
    assert status == 200
    assert [e["id"] for e in d["items"]] == ["vid-heavy", "vid-light", "pho-1", "burst-1", "live-1", "edit-1"]
    assert d["next"] is None
    status, _, d = _json(app.base_url, "POST", "/api/sources/gopro/connect", {"token": "   "})
    assert status == 400 and d["error"]["code"] == "bad_token"
    status, _, d = _json(app.base_url, "GET", "/api/sources/gopro/list?page=x")
    assert status == 400 and d["error"]["code"] == "bad_page"


def test_bad_paste_keeps_the_stored_token(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    with pytest.raises(AuthError) as err:
        src.connect({"token": "eyJgarbage"})                  # verified before it is saved
    assert err.value.code == "token_rejected"
    with open(gopro.token_file(), encoding="utf-8") as fh:
        assert fh.read() == fake.good                         # the good token is still there
    assert src.status()["state"] == "connected"               # and the source did not flip
    assert not [c for c in fake.calls if "/download" in c]


def test_double_paste_deduplicated(fake, capsys):
    tok = fake.good
    assert gopro.fold_double_paste(tok + tok) == (tok, True)
    assert gopro.fold_double_paste(tok) == (tok, False)
    assert gopro.fold_double_paste("abab") == ("ab", True)     # symmetric halves fold, as today
    src = GoProSource()
    src.connect({"token": tok + tok})
    with open(gopro.token_file(), encoding="utf-8") as fh:
        assert fh.read() == tok
    assert "pasted twice" in capsys.readouterr().out
    assert src.status()["state"] == "connected"


# ------------------------------------------------------------ the hand-off
def test_handoff_connects_after_verification(fake):
    """The round: disconnected → connecting/browser → connected, the value verified once, stored as a paste is."""
    src = GoProSource()
    h = _round(src, fake, {})                                 # nothing stored: {} starts the round
    s = src.status()
    assert s["state"] == "connecting" and s["detail"]["step"] == "browser" and s["detail"]["stored"] is False
    assert 0 < s["detail"]["expires_in"] <= 300
    assert h.timeout == 300.0 and fake.calls == []            # nothing verified before a value appears
    assert h.offer(fake.good) is True
    wait_for(lambda: src.status()["state"] == "connected")
    assert h.verified == [fake.good]
    assert [c for c in fake.calls if "per_page=1&" in c] and fake.tokens == [fake.good]   # the verifier's one call
    d = src.status()["detail"]
    assert d["stored"] and d["captured_by"] == "window" and abs(d["captured_at"] - time.time()) < 5
    assert d["cookie"] == {"session": False, "expires": 1790000000.0}
    assert d["age"] == "session captured just now" and d["verified_at"] and d["error"] is None
    assert "flow_error" not in d and "fallback" not in d
    with open(gopro.token_file(), encoding="utf-8") as fh:
        assert fh.read() == fake.good
    assert os.name != "posix" or stat.S_IMODE(os.stat(gopro.token_file()).st_mode) == 0o600
    assert src.list().items                                   # and the listing works on the captured session
    assert fake.tokens[-1] == fake.good


def test_status_carries_the_on_host_note(fake):
    src = GoProSource()
    _round(src, fake)
    d = src.status()["detail"]
    assert d["note"] == gopro.ON_HOST_NOTE
    assert "computer running cast-tv" in d["note"] and "not on the device showing this page" in d["note"]
    assert set(d) == {"stored", "step", "expires_in", "note"}   # nothing else while the window is open


def test_second_connect_joins_the_round(fake):
    src = GoProSource()
    h = _round(src, fake)
    for params in ({"fresh": True}, {}, {"fresh": True}):
        d = src.connect(params)
        assert d["step"] == "browser" and d["state"] == "connecting"
    assert len(fake.handoffs) == 1                            # one window, however many devices pressed
    h.offer(fake.good)
    wait_for(lambda: src.status()["state"] == "connected")
    assert len(fake.handoffs) == 1


def test_cancel_ends_the_round_with_no_fallback(fake):
    src = GoProSource()
    h = _round(src, fake)
    d = src.connect({"cancel": True})
    assert h.cancelled == 1
    assert d == {"state": "disconnected", "detail": {"stored": False}}   # the button again; no note, no field
    wait_for(lambda: src._flow is None)
    time.sleep(0.05)
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    assert src.connect({"cancel": True}) == {"state": "disconnected", "detail": {"stored": False}}   # nothing runs: no-op
    assert h.cancelled == 1
    # a timeout is not a fallback either: the note, and the button
    h2 = _round(src, fake)
    h2.time_out()
    wait_for(lambda: "flow_error" in src.status()["detail"])
    d = src.status()["detail"]
    assert d["flow_error"]["code"] == "browser_timeout" and "fallback" not in d
    # the next round clears the note
    _round(src, fake)
    assert "flow_error" not in src.connect({"cancel": True})["detail"]


def test_closed_window_is_not_a_fallback(fake):
    src = GoProSource()
    h = _round(src, fake)
    h.close_window()
    wait_for(lambda: src.status()["state"] == "disconnected")
    d = src.status()["detail"]
    assert d["stored"] is False and d["flow_error"]["code"] == "browser_closed"
    assert d["flow_error"]["message"] == "The gopro.com window was closed before a session appeared."
    assert "fallback" not in d


def test_no_browser_sets_the_fallback(fake):
    src = GoProSource()
    h = _round(src, fake)
    h.fail("no_browser", "No Chrome, Chromium, Edge or Brave was found on this computer.")
    wait_for(lambda: "fallback" in src.status()["detail"])
    d = src.status()["detail"]
    assert d["flow_error"]["code"] == "no_browser"
    assert d["fallback"]["reason"] == "No Chrome, Chromium, Edge or Brave was found on this computer."
    steps = d["fallback"]["steps"]
    assert steps == list(gopro.TOKEN_STEPS) and len(steps) == 3
    for n, step in enumerate(steps, 1):                       # one source of truth: the CLI prints the same lines
        assert step.split(" ")[0] in gopro.HOW_TO_GET_A_TOKEN and ("  %d. " % n) in gopro.HOW_TO_GET_A_TOKEN
    assert "F12" in steps[1] and "gp_access_token" in steps[2]
    assert "lasts a few hours" not in gopro.HOW_TO_GET_A_TOKEN
    assert gopro.HOW_TO_GET_A_TOKEN.lstrip().startswith("Run cast-tv, open the GoPro tab and press Open gopro.com.")
    assert "checked 2026-09-20" in gopro.HOW_TO_GET_A_TOKEN
    # a failed launch is the other fallback; the fallback outlives a cancelled retry
    h2 = _round(src, fake)
    assert "fallback" not in src.status()["detail"]           # the step is on screen, not the paste
    h2.fail("browser_failed", "No gopro.com window could be opened. /nonexistent: No such file or directory")
    wait_for(lambda: src.status()["detail"].get("flow_error", {}).get("code") == "browser_failed")
    assert src.status()["detail"]["fallback"]["reason"].startswith("No gopro.com window could be opened.")
    # a paste then clears it
    src.connect({"token": fake.good})
    d = src.status()["detail"]
    assert src.status()["state"] == "connected" and "fallback" not in d and "flow_error" not in d


def test_stored_token_verifies_without_a_window(fake):
    GoProSource().connect({"token": fake.good})
    src = GoProSource()                                       # a new process: stored, not yet verified
    assert src.status()["state"] == "disconnected" and src.status()["detail"]["stored"]
    d = src.connect({})
    assert d["state"] == "connected" and "step" not in d
    assert fake.handoffs == []                                # no window
    assert src.status()["detail"]["captured_by"] == "paste"  # the history is kept


def test_expired_then_fresh_starts_the_round(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    fake.good = "eyJrotated"
    with pytest.raises(AuthError):
        src.list()
    assert src.status()["state"] == "expired"
    h = _round(src, fake)                                     # {"fresh": true} after expired
    assert src.status()["detail"]["stored"] is True           # the old token is still stored meanwhile
    assert h.offer("eyJold-from-profile") is False            # the profile's stale value: refused, the window stays
    assert src._flow is not None
    assert h.offer(fake.good) is True
    wait_for(lambda: src.status()["state"] == "connected")
    d = src.status()["detail"]
    assert d["captured_by"] == "window" and d["error"] is None and d["first_401_at"] is None
    assert h.verified == ["eyJold-from-profile", fake.good]
    # {} after expired starts a round as well, as the other sources do
    fake.good = "eyJrotated2"
    with pytest.raises(AuthError):
        src.list()
    assert src.connect({})["step"] == "browser" and len(fake.handoffs) == 2


def test_disconnect_removes_the_profile(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    profile, cache = browser.prepare_profile()
    assert os.path.isdir(profile) and os.path.isdir(cache) and os.path.exists(gopro.session_file())
    src.disconnect()
    assert not os.path.exists(profile) and not os.path.exists(cache)
    assert not os.path.exists(gopro.token_file()) and not os.path.exists(gopro.session_file())
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    # and it cancels a running round, closing the window first
    h = _round(src, fake)
    browser.prepare_profile()
    src.disconnect()
    assert h.cancelled == 1 and src._flow is None and not os.path.exists(profile)
    time.sleep(0.05)
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}   # no note either


def test_close_cancels_the_round(fake):
    src = GoProSource()
    h = _round(src, fake)
    src.close()
    assert h.cancelled == 1 and src._flow is None
    src.close()                                               # final, and a second close is a no-op
    assert h.cancelled == 1
    with pytest.raises(ConfigError) as err:
        src.connect({"fresh": True})
    assert err.value.code == "source_closed"
    idle = GoProSource()
    idle.close()                                              # nothing to close


def test_a_late_capture_after_disconnect_is_dropped(fake):
    src = GoProSource()
    h = _round(src, fake)
    seen = []

    def disconnect_mid_verify(url, status, bearer):
        if "per_page=1&" in url and not seen:                 # the verifier's call is in flight
            seen.append(url)
            src.disconnect()
    fake.before_answer = disconnect_mid_verify
    assert h.offer(fake.good) is True                         # the engine's verify returned True after the cancel
    assert h.cancelled == 1 and h.result["token"] == fake.good
    time.sleep(0.1)
    assert src.status() == {"state": "disconnected", "detail": {"stored": False}}
    assert not os.path.exists(gopro.token_file()) and not os.path.exists(gopro.session_file())


def test_last_success_at_moves_on_list(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    assert src.status()["detail"]["last_success_at"] is None  # the paste's own check is not a call
    src.list()
    first = src.status()["detail"]["last_success_at"]
    assert first and abs(first - time.time()) < 5
    time.sleep(0.01)
    src.thumb("vid-heavy")
    assert src.status()["detail"]["last_success_at"] > first


def test_401_hint_carries_the_observed_period(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    src.list()
    fake.good = "eyJrotated"
    with pytest.raises(AuthError) as err:
        src.list()
    hint = err.value.hint
    assert hint.startswith("Token pasted 20") and "Worked for at least" in hint
    assert "(last successful call)" in hint and "First refusal" in hint and "after capture" in hint
    assert "Cookie" not in hint                               # a paste carries no cookie
    d = src.status()["detail"]
    assert d["error"]["hint"] == hint and d["first_401_at"] and abs(d["first_401_at"] - time.time()) < 5
    assert _sidecar()["first_401_at"] == d["first_401_at"]   # written at once
    # no success on record
    fake.good = "eyJgood"
    src2 = GoProSource()
    src2.connect({"token": fake.good})
    fake.good = "eyJrotated"
    with pytest.raises(AuthError) as err:
        src2.thumb("vid-heavy")
    assert "No successful call recorded" in err.value.hint
    # a window capture names the cookie
    fake.good = "eyJgood"
    src3 = GoProSource()
    h = _round(src3, fake)
    h.offer(fake.good, session=True)
    wait_for(lambda: src3.status()["state"] == "connected")
    fake.good = "eyJrotated"
    with pytest.raises(AuthError) as err:
        src3.list()
    assert err.value.hint.startswith("Session captured") and "Session cookie" in err.value.hint
    assert gopro.observed_period(gopro.session_meta("window", 1000.0, {"session": False, "expires": 1790000000.0}),
                                 now=1300.0).endswith("(persistent).")


def test_paste_still_works_and_is_marked_paste(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    d = src.status()["detail"]
    assert d["captured_by"] == "paste" and abs(d["captured_at"] - time.time()) < 5
    assert d["cookie"] is None and d["last_success_at"] is None and d["first_401_at"] is None
    assert d["age"] == "token stored just now"
    assert os.name != "posix" or stat.S_IMODE(os.stat(gopro.session_file()).st_mode) == 0o600
    side = _sidecar()
    assert side["captured_by"] == "paste" and side["token_mtime"] == os.path.getmtime(gopro.token_file())
    assert fake.good not in json.dumps(side) and "eyJ" not in json.dumps(side)
    # cast-gopro --token goes through the same path
    from castlib import cli
    assert cli.main_gopro(["--token", "eyJcli"]) == 0
    assert _sidecar()["captured_by"] == "paste" and "eyJcli" not in json.dumps(_sidecar())


def test_session_metadata_survives_a_restart(fake):
    src = GoProSource()
    h = _round(src, fake)
    h.offer(fake.good, session=False, expires=1790000000.0)
    wait_for(lambda: src.status()["state"] == "connected")
    before = src.status()["detail"]
    with open(gopro.session_file(), encoding="utf-8") as fh:
        text = fh.read()
    assert fake.good not in text and "eyJ" not in text and "token_mtime" in text
    again = GoProSource()                                     # a second process over the same config dir
    d = again.status()["detail"]
    assert again.status()["state"] == "disconnected" and d["stored"]
    assert d["captured_by"] == "window" and d["captured_at"] == before["captured_at"]
    assert d["cookie"] == {"session": False, "expires": 1790000000.0}
    assert d["age"] == "session captured just now"
    again.connect({})
    assert again.status()["state"] == "connected" and again.status()["detail"]["captured_by"] == "window"


def test_a_replaced_token_file_drops_the_metadata(fake):
    src = GoProSource()
    h = _round(src, fake)
    h.offer(fake.good)
    wait_for(lambda: src.status()["state"] == "connected")
    config.write_private(gopro.token_file(), fake.good)       # replaced by hand
    then = time.time() - 3 * 3600
    os.utime(gopro.token_file(), (then, then))
    d = GoProSource().status()["detail"]
    assert d["captured_by"] == "unknown" and d["captured_at"] is None and d["cookie"] is None
    assert d["age"] == "token stored 3 h ago" and d["stored_at"] == os.path.getmtime(gopro.token_file())
    assert gopro.read_session() is None                       # the sidecar belongs to another file
    # a token file from before this change: no sidecar at all
    os.unlink(gopro.session_file())
    d = GoProSource().status()["detail"]
    assert d["captured_by"] == "unknown" and d["age"] == "token stored 3 h ago"


def test_env_token_keeps_metadata_in_memory(fake, monkeypatch):
    monkeypatch.setenv("GOPRO_TOKEN", fake.good)
    src = GoProSource()
    d = src.status()["detail"]
    assert d["stored"] and d["captured_by"] == "env" and abs(d["captured_at"] - time.time()) < 5
    assert d["age"] is None and d["stored_at"] is None
    src.connect({})
    src.list()
    assert src.status()["detail"]["last_success_at"]
    fake.good = "eyJrotated"
    with pytest.raises(AuthError) as err:
        src.list()
    assert err.value.hint.startswith("Token from GOPRO_TOKEN since")
    assert not os.path.exists(gopro.session_file()) and not os.path.exists(gopro.token_file())   # nothing written


def test_last_success_write_is_throttled(fake, monkeypatch):
    writes = []
    real = gopro.write_session
    monkeypatch.setattr(gopro, "write_session", lambda meta: writes.append(dict(meta)) or real(meta))
    src = GoProSource()
    src.connect({"token": fake.good})
    assert len(writes) == 1                                   # the paste
    src.list()
    src.list()
    src.thumb("vid-heavy")
    assert len(writes) == 2                                   # the first success; the next ones within a minute do not
    assert writes[1]["last_success_at"] and _sidecar()["last_success_at"] == writes[1]["last_success_at"]
    monkeypatch.setattr(gopro, "META_WRITE_EVERY", 0.0)
    src.list()
    assert len(writes) == 3                                   # past the interval: written again
    monkeypatch.setattr(gopro, "META_WRITE_EVERY", 60.0)
    fake.good = "eyJrotated"
    with pytest.raises(AuthError):
        src.list()
    assert len(writes) == 4 and writes[-1]["first_401_at"]   # the first 401 writes at once
    with pytest.raises(AuthError):
        src.list()
    assert len(writes) == 4                                   # the second does not


def test_first_401_reports_once(fake):
    src = GoProSource()
    reported = []
    src.report = reported.append
    src.connect({"token": fake.good})
    src.list()
    fake.good = "eyJrotated"
    for call in (src.list, src.list, lambda: src.thumb("vid-heavy")):
        with pytest.raises(AuthError):
            call()
    assert len(reported) == 1
    err = reported[0]
    assert err.code == "token_rejected" and err.source == "gopro"
    assert err.hint.startswith("Token pasted") and "Worked for at least" in err.hint
    # a new session, refused again: one more card
    fake.good = "eyJgood"
    src.connect({"token": fake.good})
    fake.good = "eyJrotated"
    with pytest.raises(AuthError):
        src.connect({})                                       # the verification path reports too
    assert len(reported) == 2 and "No successful call recorded" in reported[1].hint


# ------------------------------------------------------------- the listing
def test_kind_mapping(fake, capsys, monkeypatch):
    from castlib import media
    monkeypatch.setattr(media, "_hidden_kinds_logged", set())   # "once per session": start one
    src = GoProSource()
    src.connect({"token": fake.good})
    listing = src.list()
    by_id = {e.id: e for e in listing.items}
    assert list(by_id) == ["vid-heavy", "vid-light", "pho-1", "burst-1", "live-1", "edit-1"]   # Audio is hidden
    assert "hiding an item of unknown kind 'Audio'" in capsys.readouterr().err
    assert [by_id[i].kind for i in ("vid-heavy", "vid-light", "edit-1")] == ["video"] * 3
    assert [by_id[i].kind for i in ("pho-1", "burst-1", "live-1")] == ["photo"] * 3
    v = by_id["vid-heavy"]
    assert v.name == "Ridge run" and v.date == "2026-07-27"
    assert (v.width, v.height) == (3840, 3360) and v.duration == 9.28 and v.size == 136606373   # source_duration is ms
    assert v.mime == "video/mp4" and v.thumb == "/api/sources/gopro/thumb/vid-heavy"           # a video has a still
    assert by_id["vid-light"].name == "GX010926.MP4" and by_id["vid-light"].duration == 3.63    # no title: the filename
    assert by_id["edit-1"].name == "Best of" and by_id["edit-1"].size is None and by_id["edit-1"].warn is None
    p = by_id["pho-1"]
    assert p.duration is None and p.mime == "image/jpeg" and (p.width, p.height) == (4000, 3000)
    assert p.thumb is None and by_id["burst-1"].thumb is None   # a still's only image is its multi-MB source
    assert by_id["burst-1"].duration is None                    # "0" is not a duration
    assert listing.next is None and listing.folders == [] and listing.as_dict()["crumbs"] == []
    assert ("fields=id,filename,captured_at,content_title,file_size,type,width,height,"
            "source_duration,thumbnail_available&order_by=captured_at&per_page=100&page=1") in fake.calls[-1]


def test_listing_pages(fake, monkeypatch):
    monkeypatch.setattr(gopro, "PAGE_SIZE", 2)
    src = GoProSource()
    src.connect({"token": fake.good})
    first = src.list()
    assert [e.id for e in first.items] == ["vid-heavy", "vid-light"] and first.next == "2"
    second = src.list(page="2")
    assert [e.id for e in second.items] == ["pho-1", "burst-1"] and second.next == "3"
    fourth = src.list(page="4")
    assert fourth.items == [] and fourth.next is None         # only the hidden Audio entry: a short page


def test_heavy_item_defaults_to_proxy(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    by_id = {e.id: e for e in src.list().items}
    heavy, light = by_id["vid-heavy"], by_id["vid-light"]
    assert heavy.warn == "too heavy: 118 Mbit/s"                # 136 606 373 B * 8 / 9.28 s
    assert [v["quality"] for v in heavy.variants] == ["proxy", "source"]
    assert heavy.variants[0]["default"] and not heavy.variants[1]["default"]
    assert light.warn is None and light.variants is None
    item = src.resolve("vid-heavy")                           # auto → proxy for a heavy item
    assert item.kind == "video" and item.title == "Ridge run" and item.size == 136606373
    assert item.resolve().url.startswith("https://cdn.test/u-test/vid-heavy/high_res_proxy_mp4/")
    assert src.resolve("vid-heavy", "source").resolve().url.startswith("https://cdn.test/u-test/vid-heavy/source/")
    assert src.resolve("vid-heavy", "proxy").resolve().url.startswith("https://cdn.test/u-test/vid-heavy/high_res_proxy_mp4/")
    assert src.resolve("vid-light").resolve().url.startswith("https://cdn.test/u-test/vid-light/source/")
    assert src.resolve("vid-light", "proxy").resolve().url.startswith("https://cdn.test/u-test/vid-light/high_res_proxy_mp4/")
    assert src.resolve("edit-1").resolve().url.startswith("https://cdn.test/u-test/edit-1/baked_source/")   # an edit's only mp4
    assert not any("audio_proxy" in p or ".m4a" in p for p in fake.probes)    # never a candidate


def test_resolve_reranks_each_call(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    src.list()
    item = src.resolve("vid-light")
    downloads = lambda: [c for c in fake.calls if c.endswith("/download")]   # noqa: E731
    assert downloads() == []                                  # resolve() itself touches nothing
    first = item.resolve().url
    second = item.resolve().url
    assert len(downloads()) == 2 and first != second          # a fresh signed address every time
    assert first.split("?")[0] == second.split("?")[0]
    # the source variant is refused by the CDN: the next one is taken, on every call
    fake.refuse.add("https://cdn.test/u-test/vid-light/source/default/1.mp4")
    assert item.resolve().url.startswith("https://cdn.test/u-test/vid-light/high_res_proxy_mp4/")
    assert item.resolve().url.startswith("https://cdn.test/u-test/vid-light/high_res_proxy_mp4/")


def test_resolve_photo_variant(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    src.list()
    item = src.resolve("pho-1")
    assert item.kind == "photo" and item.mime == "image/jpeg" and item.title == "Summit"
    assert item.resolve().url.startswith("https://cdn.test/u-test/pho-1/source/default/1.jpg")
    assert item.resolve().headers == {}
    assert fake.probes[-1].startswith("https://cdn.test/u-test/pho-1/source/")   # octet-stream + .jpg passed
    burst = src.resolve("burst-1")                            # a burst: the frame the library shows
    assert burst.kind == "photo"
    assert burst.resolve().url.startswith("https://cdn.test/u-test/burst-1/source/default/1.jpg")
    fake.refuse.add("https://cdn.test/u-test/burst-1/source/default/1.jpg")
    with pytest.raises(NotMedia) as err:
        burst.resolve()                                       # frames 2..n are not stand-ins
    assert err.value.code == "gopro_still_not_image"
    assert not any("/default/2.jpg" in p for p in fake.probes)
    live = src.resolve("live-1")                              # a livephoto resolves to its still
    assert live.kind == "photo"
    assert live.resolve().url.startswith("https://cdn.test/u-test/live-1/large/")
    assert src.resolve("live-1", "proxy").resolve().url.startswith("https://cdn.test/u-test/live-1/medium/")
    assert not any(".mp4" in p for p in fake.probes if "live-1" in p)
    with pytest.raises(NotMedia) as err:
        src.resolve("nope")                                   # never listed and not in the library
    assert err.value.code == "unknown_item"
    assert fake.calls[-1] == "https://api.gopro.com/media/nope"
    with pytest.raises(NotMedia):
        src.resolve("../etc")
    assert fake.calls[-1] == "https://api.gopro.com/media/nope"   # a bad id never reaches the API


def test_resolve_unlisted_id_fetches_the_item(fake):
    """``cast-gopro <media-id>`` names an item this process never listed: one ``/media/{id}`` lookup."""
    src = GoProSource()
    src.connect({"token": fake.good})
    item = src.resolve("pho-1")
    assert item.kind == "photo" and item.title == "Summit" and item.width == 4000
    assert fake.calls[-1] == "https://api.gopro.com/media/pho-1"
    assert item.resolve().url.startswith("https://cdn.test/u-test/pho-1/source/")
    src.resolve("pho-1")                                      # cached now: no second lookup
    assert fake.calls[-1] != "https://api.gopro.com/media/pho-1"
    assert src.thumb("vid-heavy") is not None                 # thumb() looks up the same way


def test_thumb_is_a_fresh_large_still_for_videos_only(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    src.list()
    first = src.thumb("vid-heavy")
    second = src.thumb("vid-heavy")
    assert first.url.startswith("https://cdn.test/u-test/vid-heavy/large/default/1.jpg")
    assert first.url != second.url and first.headers == {}   # fresh signature, no auth needed
    assert [c for c in fake.calls if "labels=large" in c][-1].startswith("https://api.gopro.com/media/vid-heavy/download?labels=large")
    assert src.thumb("edit-1") is not None
    assert src.thumb("pho-1") is None and src.thumb("burst-1") is None and src.thumb("nope") is None


def test_thumb_route_serves_the_still_through_the_sniffing_proxy(app, fake, upstream, monkeypatch):
    """The CDN says binary/octet-stream for a JPEG: the proxy types it from the bytes."""
    up = upstream(b"\xff\xd8\xff\xe0JFIF-thumb", ctype="binary/octet-stream")
    fake.cdn = up.base
    from tests.test_api import _json
    _json(app.base_url, "POST", "/api/sources/gopro/connect", {"token": fake.good})
    _, _, d = _json(app.base_url, "GET", "/api/sources/gopro/list")
    assert d["items"][0]["thumb"] == "/api/sources/gopro/thumb/vid-heavy"
    from tests.conftest import request
    status, headers, body, _ = request(app.base_url, "GET", "/api/sources/gopro/thumb/vid-heavy")
    assert status == 200 and body == b"\xff\xd8\xff\xe0JFIF-thumb"
    assert headers["Content-Type"] == "image/jpeg" and headers["X-Content-Type-Options"] == "nosniff"
    assert up.requests[-1]["path"].startswith("/u-test/vid-heavy/large/default/1.jpg")
    status, _, body, _ = request(app.base_url, "GET", "/api/sources/gopro/thumb/pho-1")
    assert status == 404


def test_resolve_after_401_flips_to_expired(fake):
    src = GoProSource()
    src.connect({"token": fake.good})
    src.list()
    item = src.resolve("vid-light")
    fake.good = "eyJrotated"
    with pytest.raises(AuthError):
        item.resolve()                                        # the relay's re-resolve lands here
    assert src.status()["state"] == "expired"


# ------------------------------------------------------------------ the CLI
def test_cli_listing_and_url_only(fake, capsys, monkeypatch):
    from castlib import cli
    gopro.save_token(fake.good)
    capsys.readouterr()
    assert cli.main_gopro([]) == 0
    out = capsys.readouterr().out
    assert "1. Ridge run" in out and "Cast one:  cast-gopro <number>" in out
    assert "3840x3360" in out                                  # the listing's resolution column
    assert cli.main_gopro(["1", "--url-only"]) == 0
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1].startswith("https://cdn.test/u-test/vid-heavy/high_res_proxy_mp4/")   # heavy: proxy by default
    assert cli.main_gopro(["1", "-q", "source", "--url-only"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("https://cdn.test/u-test/vid-heavy/source/")
    assert cli.main_gopro(["3", "--url-only"]) == 0            # a photo, by number
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("https://cdn.test/u-test/pho-1/source/")
    assert cli.main_gopro(["pho-1", "--url-only"]) == 0        # or by id
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("https://cdn.test/u-test/pho-1/source/")
    fake.good = "eyJrotated"
    assert cli.main_gopro([]) == 1
    assert "rejected the token" in capsys.readouterr().err
