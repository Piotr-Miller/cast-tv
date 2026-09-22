"""The hand-off engine against the fake browser: candidates, the profile, the launch, the cookie loop, close."""
import json
import os
import shutil
import stat
import threading
import time

import pytest

from castlib import config
from castlib.auth import browser, cdp
from castlib.errors import AuthError
from tests.conftest import wait_for
from tests.fakes_cdp import FakeBrowser, cookie


@pytest.fixture
def engine(monkeypatch, tmp_path):
    """Config and cache in tmp, no override, fast timings; yields a factory of fake browsers, all stopped at the end."""
    monkeypatch.setattr(config, "_CONFIG", str(tmp_path / "config"))
    monkeypatch.setattr(config, "_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("CAST_TV_BROWSER", raising=False)
    monkeypatch.setattr(browser, "POLL_INTERVAL", 0.01)
    monkeypatch.setattr(browser, "LAUNCH_TIMEOUT", 2.0)
    monkeypatch.setattr(browser, "CLOSE_GRACE", 0.2)
    fakes = []

    def make(**kw):
        f = FakeBrowser(**kw)
        fakes.append(f)
        return f
    yield make
    for f in fakes:
        f.stop()


def _use(monkeypatch, fake, path="/fake/chrome"):
    """The engine finds ``path`` alone and launches ``fake`` for it."""
    monkeypatch.setattr(browser, "candidates", lambda **kw: [path])
    monkeypatch.setattr(browser, "launch", fake.launch)


def _executable(tmp_path, name):
    p = tmp_path / name
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    return str(p)


# ------------------------------------------------------------ candidates
def test_candidates_order(tmp_path):
    exes = {name: _executable(tmp_path, name) for name in ("google-chrome", "chromium", "brave-browser")}
    exes["google-chrome-stable"] = exes["google-chrome"]           # the same binary under a second name
    asked = []

    def which(name):
        asked.append(name)
        return exes.get(name)
    assert browser.candidates(platform="linux", environ={}, which=which) == \
        [exes["google-chrome"], exes["chromium"], exes["brave-browser"]]   # order kept, duplicate dropped
    assert asked == list(browser.LINUX_NAMES)
    # Windows: per browser, the App Paths value first, then the Program Files folders; existing files only
    pf, pf86, local, reg = (tmp_path / d for d in ("pf", "pf86", "local", "reg"))
    chrome = pf / "Google" / "Chrome" / "Application" / "chrome.exe"
    edge = local / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    reg_chrome = reg / "chrome.exe"
    for p in (chrome, edge, reg_chrome):
        p.parent.mkdir(parents=True)
        p.write_bytes(b"MZ")
    env = {"PROGRAMFILES": str(pf), "PROGRAMFILES(X86)": str(pf86), "LOCALAPPDATA": str(local)}
    app_paths = lambda exe: [str(reg_chrome)] if exe == "chrome.exe" else [str(reg / "gone.exe")]   # noqa: E731
    assert browser.candidates(platform="win32", environ=env, app_paths=app_paths) == \
        [str(reg_chrome), str(chrome), str(edge)]
    assert browser.candidates(platform="win32", environ={}, app_paths=lambda exe: []) == []
    assert browser._app_paths("chrome.exe") == [] or os.name == "nt"   # no winreg off Windows: an empty list


def test_env_override_is_exclusive(tmp_path, monkeypatch):
    exe = _executable(tmp_path, "mybrowser")
    asked = []

    def which(name):
        asked.append(name)
        return str(tmp_path / "other")
    assert browser.candidates(environ={"CAST_TV_BROWSER": exe}, which=which) == [exe]
    gone = str(tmp_path / "gone")
    assert browser.candidates(environ={"CAST_TV_BROWSER": gone}, which=which) == [gone]   # used even if missing
    assert browser.candidates(environ={"CAST_TV_BROWSER": " " + exe + " "}, which=which) == [exe]
    assert asked == []                                                              # nothing else consulted
    assert browser.candidates(platform="linux", environ={"CAST_TV_BROWSER": ""}, which=lambda n: None) == []   # empty: unset
    assert browser.describe(environ={"CAST_TV_BROWSER": exe}) == "CAST_TV_BROWSER=" + exe
    assert browser.describe(environ={"CAST_TV_BROWSER": gone}) == "CAST_TV_BROWSER=%s (not found)" % gone
    monkeypatch.setattr(browser, "candidates", lambda **kw: [exe, gone])
    assert browser.describe(environ={}) == exe
    monkeypatch.setattr(browser, "candidates", lambda **kw: [])
    assert browser.describe(environ={}) == "none found"


def test_missing_override_is_browser_failed(engine, monkeypatch):
    monkeypatch.setenv("CAST_TV_BROWSER", "/nonexistent")
    asked = []
    monkeypatch.setattr(shutil, "which", lambda name: asked.append(name))

    def launch(args, **kw):
        raise FileNotFoundError(2, "No such file or directory", args[0])
    monkeypatch.setattr(browser, "launch", launch)
    h = browser.Handoff().start(lambda value: True)
    with pytest.raises(AuthError) as err:
        h.wait()
    assert err.value.code == "browser_failed" and err.value.source == "gopro"
    assert "/nonexistent" in err.value.message and "No such file" in err.value.message
    assert asked == [] and h.executable is None                    # no Chrome or Edge was tried


def test_no_candidate_is_no_browser(engine, monkeypatch):
    monkeypatch.setattr(browser, "candidates", lambda **kw: [])
    launched = []
    monkeypatch.setattr(browser, "launch", lambda *a, **kw: launched.append(a))
    h = browser.Handoff().start(lambda value: True)
    with pytest.raises(AuthError) as err:
        h.wait()
    assert err.value.code == "no_browser" and "No Chrome" in err.value.message
    assert launched == [] and not os.path.exists(browser.profile_dir())


def test_failed_launch_is_browser_failed(engine, monkeypatch):
    fake = engine(exit_at_once="Fontconfig warning: ignored\n[1:1:ERROR:main.cc] boom, no display\n")
    _use(monkeypatch, fake)
    h = browser.Handoff().start(lambda value: True)
    with pytest.raises(AuthError) as err:
        h.wait()
    assert err.value.code == "browser_failed"
    assert "/fake/chrome" in err.value.message and "boom, no display" in err.value.message
    assert "exited with code 1" in err.value.message
    assert len(fake.launches) == 1 and fake.closed == 0


def test_a_failing_candidate_is_skipped(engine, monkeypatch):
    silent = engine(silent=True)                                    # never writes the port file
    good = engine(cookies=[cookie("eyJgood")])
    fakes = {"/fake/a": silent, "/fake/b": good}
    monkeypatch.setattr(browser, "candidates", lambda **kw: ["/fake/a", "/fake/b"])
    monkeypatch.setattr(browser, "launch", lambda args, **kw: fakes[args[0]].launch(args, **kw))
    monkeypatch.setattr(browser, "LAUNCH_TIMEOUT", 0.2)
    h = browser.Handoff().start(lambda value: value == "eyJgood")
    result = h.wait()
    assert result["token"] == "eyJgood" and h.executable == "/fake/b"
    assert result["cookie"] == {"session": False, "expires": 1790000000.0}
    assert abs(result["captured_at"] - time.time()) < 5
    assert silent.terminated == 1 and silent.process.poll() == -15   # ended, not left running
    assert good.closed == 1 and good.process.poll() == 0             # closed gracefully after the capture
    assert h.wait() is result                                        # the outcome stays readable


def test_cookie_name_and_domain_filter(engine, monkeypatch):
    fake = engine(cookies=[cookie("eyJelsewhere", domain="example.com"),
                           cookie("eyJelsewhere2", domain="notgopro.com"),
                           cookie("eyJother", name="gp_other")])
    _use(monkeypatch, fake)
    seen = []

    def verify(value):
        seen.append(value)
        return True
    h = browser.Handoff().start(verify)
    wait_for(lambda: fake.polls >= 3)
    assert seen == [] and h.result is None
    fake.cookies = fake.cookies + [cookie("eyJhost", domain="gopro.com")]   # host-only on gopro.com counts
    assert h.wait()["token"] == "eyJhost" and seen == ["eyJhost"]
    fake2 = engine(cookies=[cookie("eyJsub", domain=".api.gopro.com")])    # and so does a subdomain
    _use(monkeypatch, fake2)
    assert browser.Handoff().start(verify).wait()["token"] == "eyJsub"


def test_stale_value_waits_for_a_new_one(engine, monkeypatch):
    fake = engine(cookies=[cookie("eyJold")])                        # the profile kept a dead session
    _use(monkeypatch, fake)
    seen = []

    def verify(value):
        seen.append(value)
        if value != "eyJgood":
            raise AuthError("token_rejected", "401", source="gopro")   # what the source's verify raises
        return True
    h = browser.Handoff().start(verify)
    wait_for(lambda: fake.polls >= 3)
    assert seen == ["eyJold"] and h.result is None and fake.closed == 0   # refused once; the window stays open
    fake.cookies = [cookie("eyJgood", session=True)]                 # the person signed in again
    result = h.wait()
    assert result["token"] == "eyJgood" and result["cookie"] == {"session": True, "expires": -1}
    assert seen == ["eyJold", "eyJgood"] and fake.closed == 1


def test_two_cookies_each_verified_once(engine, monkeypatch):
    fake = engine(cookies=[cookie("eyJa", domain=".gopro.com"), cookie("eyJb", domain="gopro.com")])
    _use(monkeypatch, fake)
    seen = []

    def verify(value):
        seen.append(value)
        return False
    h = browser.Handoff().start(verify)
    wait_for(lambda: fake.polls >= 4)
    assert sorted(seen) == ["eyJa", "eyJb"]                         # once each, over several polls
    h.cancel()
    with pytest.raises(AuthError) as err:
        h.wait()
    assert err.value.code == "cancelled"


def test_a_verifier_error_leaves_the_value_for_the_next_poll(engine, monkeypatch):
    fake = engine(cookies=[cookie("eyJgood")])
    _use(monkeypatch, fake)
    seen = []

    def verify(value):
        seen.append(value)
        if len(seen) == 1:
            raise OSError("network down")                           # not a refusal: tried again
        return True
    h = browser.Handoff().start(verify)
    assert h.wait()["token"] == "eyJgood" and seen == ["eyJgood", "eyJgood"]


def test_process_exit_is_browser_closed(engine, monkeypatch):
    fake = engine()
    _use(monkeypatch, fake)
    h = browser.Handoff().start(lambda value: True)
    wait_for(lambda: fake.polls >= 1)
    fake.close_window()                                             # the person closed the window
    with pytest.raises(AuthError) as err:
        h.wait()
    assert err.value.code == "browser_closed"
    assert err.value.message == "The gopro.com window was closed before a session appeared."
    assert fake.closed == 0 and fake.terminated == 0 and fake.killed == 0   # nothing to close, nothing touched


def test_timeout_closes_the_browser(engine, monkeypatch):
    fake = engine()
    _use(monkeypatch, fake)
    h = browser.Handoff().start(lambda value: True, timeout=0.15)
    with pytest.raises(AuthError) as err:
        h.wait()
    assert err.value.code == "browser_timeout" and "the window was closed" in err.value.message
    assert fake.closed == 1 and fake.process.poll() == 0             # Browser.close, and the process left
    assert fake.terminated == 0 and fake.killed == 0
    # a browser that ignores Browser.close is terminated after the grace, then killed
    stubborn = engine()
    stubborn.handlers["Browser.close"] = lambda params: {}          # answers, but the process stays
    _use(monkeypatch, stubborn)
    h = browser.Handoff().start(lambda value: True, timeout=0.15)
    with pytest.raises(AuthError):
        h.wait()
    assert stubborn.terminated == 1 and stubborn.process.poll() == -15


def test_cancel_closes_only_our_instance(engine, monkeypatch):
    ours, theirs = engine(), engine()
    theirs.serve()                                                  # the person's own browser, running
    _use(monkeypatch, ours)
    h = browser.Handoff().start(lambda value: True)
    wait_for(lambda: ours.polls >= 1)
    h.cancel()
    with pytest.raises(AuthError) as err:
        h.wait()
    assert err.value.code == "cancelled"
    assert ours.closed == 1 and ours.process.poll() == 0             # ours: Browser.close, then gone
    assert theirs.closed == 0 and theirs.process.poll() is None      # theirs: untouched, still serving
    session = cdp.connect(theirs.ws_url)
    assert session.call("Storage.getCookies") == {"cookies": []}
    session.close()
    h.cancel()                                                      # a second cancel is a no-op
    browser.Handoff().cancel()                                      # and so is one before any start
    # a cancel during the launch, before the port is written
    slow = engine(silent=True)
    _use(monkeypatch, slow)
    h = browser.Handoff().start(lambda value: True)
    wait_for(lambda: slow.launches)
    h.cancel()
    with pytest.raises(AuthError) as err:
        h.wait()
    assert err.value.code == "cancelled" and slow.process.poll() is not None


def test_profile_is_private_and_cache_is_elsewhere(engine, monkeypatch):
    fake = engine(cookies=[cookie("eyJgood")])
    _use(monkeypatch, fake)
    browser.Handoff().start(lambda value: True).wait()
    profile, cache = browser.profile_dir(), browser.cache_dir_for_profile()
    assert profile == os.path.join(config.config_dir(), "gopro-browser")
    assert cache == os.path.join(config.cache_dir(), "gopro-browser-cache")
    assert os.path.isdir(profile) and os.path.isdir(cache)
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(profile).st_mode) == 0o700
    (args, kwargs) = fake.launches[0]
    assert "--user-data-dir=" + profile in args and "--disk-cache-dir=" + cache in args
    assert kwargs["stdin"] is kwargs["stdout"] and hasattr(kwargs["stderr"], "write")   # devnull; stderr to the log
    assert os.path.exists(os.path.join(profile, browser.LAUNCH_LOG))
    browser.remove_profile()
    assert not os.path.exists(profile) and not os.path.exists(cache)
    browser.remove_profile()                                        # absent: a no-op


def test_preferences_seeded_once(engine):
    profile, _ = browser.prepare_profile()
    prefs = os.path.join(profile, "Default", "Preferences")
    with open(prefs, encoding="utf-8") as fh:
        assert json.load(fh) == {"credentials_enable_service": False, "profile": {"password_manager_enabled": False}}
    with open(prefs, "w", encoding="utf-8") as fh:
        fh.write('{"changed": "by chrome"}')                        # Chrome owns the file from now on
    assert browser.prepare_profile() == (profile, browser.cache_dir_for_profile())
    with open(prefs, encoding="utf-8") as fh:
        assert json.load(fh) == {"changed": "by chrome"}


def test_flags():
    args = browser.flags("/usr/bin/google-chrome", "/p", "/c", platform="linux")
    assert args[0] == "/usr/bin/google-chrome"
    assert "--remote-debugging-port=0" in args and "--user-data-dir=/p" in args and "--disk-cache-dir=/c" in args
    assert "--no-first-run" in args and "--no-default-browser-check" in args
    assert "--password-store=basic" in args
    assert args[-1] == "--app=https://gopro.com/media-library/"
    windows = browser.flags(r"C:\edge\msedge.exe", r"C:\p", r"C:\c", platform="win32")
    assert "--password-store=basic" not in windows and windows[-1] == "--app=https://gopro.com/media-library/"


def test_stale_port_file_is_removed_before_launch(engine, monkeypatch):
    fake = engine(cookies=[cookie("eyJgood")])
    _use(monkeypatch, fake)
    profile, _ = browser.prepare_profile()
    with open(os.path.join(profile, "DevToolsActivePort"), "w", encoding="utf-8") as fh:
        fh.write("1\n/devtools/browser/stale\n")                    # last run's port
    assert browser.Handoff().start(lambda value: True).wait()["token"] == "eyJgood"
    assert fake.port_file_existed is False                          # gone before the browser started


def test_nothing_logs_the_value(engine, monkeypatch, capfd):
    fake = engine(cookies=[cookie("eyJsecret-value")])
    _use(monkeypatch, fake)
    seen = []
    result = browser.Handoff().start(lambda value: seen.append(value) or True).wait()
    assert result["token"] == "eyJsecret-value"
    closed = engine(cookies=[cookie("eyJsecret-value")])
    _use(monkeypatch, closed)
    h = browser.Handoff().start(lambda value: False)
    wait_for(lambda: closed.polls >= 1)
    closed.close_window()
    with pytest.raises(AuthError) as err:
        h.wait()
    out, errtext = capfd.readouterr()
    assert "eyJsecret-value" not in out + errtext + err.value.message
    log = os.path.join(browser.profile_dir(), browser.LAUNCH_LOG)
    with open(log, encoding="utf-8") as fh:
        assert "eyJsecret-value" not in fh.read()


def test_handoff_runs_on_its_own_thread(engine, monkeypatch):
    """``start()`` returns before the launch; ``wait()`` may be called from another thread later."""
    fake = engine(cookies=[cookie("eyJgood")])
    _use(monkeypatch, fake)
    h = browser.Handoff()
    started = time.monotonic()
    assert h.start(lambda value: True) is h and time.monotonic() - started < 0.5
    out = []
    t = threading.Thread(target=lambda: out.append(h.wait()))
    t.start()
    t.join(5)
    assert out[0]["token"] == "eyJgood"
    with pytest.raises(RuntimeError):
        h.start(lambda value: True)                                 # a round starts once
