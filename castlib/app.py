"""Everything the handler threads share: the one playback owner, the TV, the sources.

``App`` owns the registry-backed server, the selected renderer, the current
``Cast`` or ``Show``, the single-worker playback executor that orders
concurrent requests, the error ring buffer and the settings file. The CLI
uses it for a one-shot cast and for a slideshow; the UI drives it over
``/api``.
"""
from __future__ import annotations

import collections
import errno
import ipaddress
import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor

from castlib import __version__, config, dlna, photos
from castlib.discovery import control_urls, discover, local_ip, renderer_name
from castlib.dlna import AVT
from castlib.errors import CastError, ConfigError, NotMedia, TVError
from castlib.platform import StayAwake, firewall_hint
from castlib.server import Server
from castlib.sources.gopro import GoProSource
from castlib.sources.local import LocalSource
from castlib.supervisor import Cast, Show

APP_NAME = "cast-tv"
EVICT_IDLE = 60.0          # seconds a retired item goes unrequested before it is dropped
EVICT_EVERY = 10.0
TV_WATCH_EVERY = 15.0      # idle liveness check of the selected TV
INTERVAL_DEFAULT = 8
INTERVAL_MIN, INTERVAL_MAX = 2, 600


class AlreadyRunning(Exception):
    """Another cast-tv already holds the port; ``url`` is its UI."""

    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


class ErrorRing:
    """The last N errors, oldest first, each with a sequence number."""

    def __init__(self, size: int = 50):
        self._items: collections.deque = collections.deque(maxlen=size)
        self._n = 0
        self._lock = threading.Lock()

    def push(self, err: CastError) -> dict:
        with self._lock:
            self._n += 1
            entry = dict(err.as_dict(), n=self._n)
            self._items.append(entry)
            return entry

    def list(self) -> list[dict]:
        with self._lock:
            return list(self._items)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def seq(self) -> int:
        """Sequence number of the newest error; grows past the ring's size, unlike ``len``."""
        with self._lock:
            return self._n


class Settings:
    """``config_dir()/settings.json``: the slideshow interval and the chosen TV."""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.config_dir(), "settings.json")
        self.data = {"interval": INTERVAL_DEFAULT, "tv": None}
        self._lock = threading.Lock()
        try:
            with open(self.path, encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                self.data.update(stored)
        except (OSError, ValueError):
            pass
        if not valid_interval(self.data.get("interval")):
            self.data["interval"] = INTERVAL_DEFAULT

    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key, value) -> None:
        with self._lock:
            self.data[key] = value
            snapshot = dict(self.data)
        try:
            config.write_json(self.path, snapshot)
        except OSError:
            pass                                    # a read-only config dir loses nothing but memory

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self.data)


def valid_interval(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and INTERVAL_MIN <= value <= INTERVAL_MAX)


class App:
    def __init__(self, server: Server, debug: bool = False):
        self.server = server
        server.app = self
        self.registry = server.registry
        photos.attach(self.registry)
        self.debug = debug
        self.codec_check = True            # ffprobe local videos for DTS before casting
        self.tv: dict | None = None        # {ip, name, avt, state}
        self.tvs: list[dict] = []
        self.discovering = False
        self.lock = threading.RLock()
        self.generation = 0
        self.owner = None                  # the current Cast or Show
        self.current: Cast | None = None   # the cast most recently put on the TV
        self.errors = ErrorRing(50)
        self.settings = Settings()
        self.local = LocalSource()
        self.sources: dict = {"gopro": GoProSource()}   # name -> Source; Phases 5-6 add theirs
        self.stay_awake = StayAwake()
        self.addresses: list[str] = []
        self.started_at = time.time()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playback")
        self._closed = threading.Event()
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------ lifecycle
    @classmethod
    def start(cls, port: int, tv: str | None = None, debug: bool = False,
              browser: bool = True, out=None) -> "App":
        """Bind first, then discover in the background, print the addresses, open the browser.

        Raises ``AlreadyRunning`` when another cast-tv answers on the port, and
        ``OSError`` when the port is held by something else.
        """
        out = out or sys.stdout
        try:
            server = Server(("0.0.0.0", port))
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                url = "http://127.0.0.1:%d/ui/" % port
                if _is_cast_tv("http://127.0.0.1:%d/api/status" % port):
                    raise AlreadyRunning(url)
            raise
        app = cls(server, debug=debug)
        app.serve()
        try:
            lan = local_ip("192.0.2.1")
        except OSError:
            lan = None
        app.addresses = ["http://localhost:%d/ui/" % port]
        if lan and lan != "127.0.0.1":
            app.addresses.append("http://%s:%d/ui/" % (lan, port))
            server.set_host(lan)
        for address in app.addresses:
            print("  %s" % address, file=out, flush=True)
        print("  If the TV never fetches a byte, open the port:  %s" % firewall_hint(port),
              file=out, flush=True)
        print("  Ctrl+C ends it (playback stops on the TV too)", file=out, flush=True)
        if tv:
            try:
                app.select_tv(tv)
                print("  TV: %s (%s)" % (app.tv["name"], app.tv["ip"]), file=out, flush=True)
            except TVError as e:
                print("  %s" % e.message, file=out, flush=True)
                app.errors.push(e)
        else:
            def find():
                app.discover()
                if app.tv and app.tv.get("avt"):
                    print("  TV: %s (%s)" % (app.tv["name"], app.tv["ip"]), file=out, flush=True)
                else:
                    print("  No DLNA renderer answered. Switch the TV on and retry from the UI,\n"
                          "  or name it directly: cast-tv -t 192.168.1.50", file=out, flush=True)
            app._thread(find, "discover")
        if browser:
            try:
                webbrowser.open(app.addresses[0])
            except Exception:
                pass
        return app

    def serve(self) -> None:
        """Run the HTTP server, the eviction ticker and the TV watch in daemon threads."""
        self._thread(lambda: self.server.serve_forever(poll_interval=0.25), "http")
        self._thread(self._evict_loop, "evict")
        self._thread(self._tv_watch, "tv-watch")

    def _thread(self, target, name) -> threading.Thread:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        self._threads.append(t)
        return t

    def _evict_loop(self) -> None:
        while not self._closed.wait(EVICT_EVERY):
            try:
                self.registry.evict(EVICT_IDLE)
            except Exception:
                pass

    def _tv_watch(self) -> None:
        """While nothing plays, ask the TV for its state now and then, so the header stays honest."""
        while not self._closed.wait(TV_WATCH_EVERY):
            tv = self.tv
            if not tv or not tv.get("avt"):
                continue
            cast = self.current
            if cast is not None and not cast.terminal:
                continue                    # the cast's own poll reports on the TV
            try:
                dlna.soap(tv["avt"], AVT, "GetTransportInfo")
                self._set_tv_state("ready")
            except Exception:
                self._set_tv_state("unreachable")

    def run_forever(self) -> int:
        """Block until Ctrl+C; stops the TV and releases everything. Returns an exit code."""
        try:
            while not self._closed.wait(1.0):
                pass
        except KeyboardInterrupt:
            print()
            self.stop()
            print("   Stopped.", flush=True)
        finally:
            self.close()
        return 0

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        with self.lock:
            self.generation += 1            # any task still preparing is stale now
            owner, self.owner = self.owner, None
        if isinstance(owner, Show):
            owner.cancel()
        cast = self.current
        if cast is not None:
            cast.cancel()
        for item in self.registry.items():
            self.registry.retire(item.id)
        self._executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        config.remove_photo_tmp_dir()

    # ------------------------------------------------------------------ TV
    def discover(self) -> list[dict]:
        """Re-run SSDP; keep the preferred TV when it answers, else take the first."""
        self.discovering = True
        try:
            found = discover()
        except OSError:
            found = []
        finally:
            self.discovering = False
        tvs = [{"ip": ip, "name": name, "avt": avt} for ip, avt, name in found]
        self.tvs = tvs
        if not tvs:
            if self.tv is None or not self.tv.get("avt"):
                self.tv = {"ip": None, "name": None, "avt": None, "state": "none"}
            return self.public_tvs()
        saved = self.settings.get("tv")
        preferred = (self.tv or {}).get("ip") or saved
        pick = next((t for t in tvs if t["ip"] == preferred), tvs[0])
        # "first discovered" is a default, never a replacement for a saved choice:
        # a fallback pick while the saved TV is off leaves settings.json alone
        self._use_tv(pick["ip"], pick["name"], pick["avt"],
                     persist=(saved is None or pick["ip"] == saved))
        return self.public_tvs()

    def select_tv(self, ip: str) -> dict:
        """Resolve the control URL of ``ip``, make it the TV, remember it."""
        ip = (ip or "").strip()
        if not ip:
            raise ConfigError("bad_ip", "Give the TV's address.")
        try:                                  # validated before any request goes out:
            version = ipaddress.ip_address(ip).version   # a host or path here would be fetched and saved
        except ValueError:
            raise ConfigError("bad_ip", "Give the TV's IPv4 address, like 192.168.1.20.")
        if version != 4:
            raise ConfigError("bad_ip", "Only IPv4 addresses are supported (SSDP discovery is IPv4).")
        avt, _rc = control_urls(ip)
        if not avt:
            raise TVError("tv_no_avtransport",
                          "%s does not expose AVTransport (switched off?)." % ip)
        name = next((t["name"] for t in self.tvs if t["ip"] == ip), None)
        if name is None:
            name = renderer_name(ip) or ip
        self._use_tv(ip, name, avt)
        return self.public_tv()

    def _use_tv(self, ip, name, avt, persist: bool = True) -> None:
        self.tv = {"ip": ip, "name": name or ip, "avt": avt, "state": "ready"}
        try:
            self.server.set_host(local_ip(ip))
        except OSError:
            pass
        if persist and self.settings.get("tv") != ip:
            self.settings.set("tv", ip)

    def use_tv(self, ip: str, avt: str, name: str | None = None) -> None:
        """A TV the CLI already resolved; not remembered as the UI's choice."""
        self._use_tv(ip, name, avt, persist=False)

    def _set_tv_state(self, state: str) -> None:
        tv = self.tv
        if tv and tv.get("state") != state:
            self.tv = dict(tv, state=state)

    def tv_unreachable(self) -> None:
        self._set_tv_state("unreachable")

    def tv_control(self) -> str | None:
        tv = self.tv
        return tv.get("avt") if tv else None

    def public_tv(self) -> dict | None:
        tv = self.tv
        if not tv:
            return None
        return {"ip": tv.get("ip"), "name": tv.get("name"), "state": tv.get("state")}

    def public_tvs(self) -> list[dict]:
        return [{"ip": t["ip"], "name": t["name"]} for t in self.tvs]

    # ------------------------------------------------------------ playback
    def is_current(self, generation: int) -> bool:
        return generation == self.generation

    def _submit(self, cast: Cast) -> None:
        self._executor.submit(cast.run)

    def cast(self, item, subtitle=None) -> Cast:
        """Replace whatever plays with ``item``; cancels a running show."""
        with self.lock:
            self.generation += 1
            previous, self.owner = self.owner, None
            cast = Cast(self, item, self.generation, subtitle=subtitle)
            self.owner = cast
        if isinstance(previous, Show):
            previous.cancel()
        self._submit(cast)
        return cast

    def show(self, items, interval=None) -> Show:
        items = list(items)
        if not items:
            raise ConfigError("empty_show", "Select something first.")
        if interval is None:
            interval = self.settings.get("interval", INTERVAL_DEFAULT)
        if not valid_interval(interval):
            raise ConfigError("bad_interval", "The interval must be between %d and %d seconds."
                              % (INTERVAL_MIN, INTERVAL_MAX))
        with self.lock:
            self.generation += 1
            previous, self.owner = self.owner, None
            show = Show(self, items, interval, self.generation)
            self.owner = show
        if isinstance(previous, Show):
            previous.cancel()
        show.start()
        return show

    def _promote(self, cast: Cast) -> str:
        """Make ``cast`` the one on the TV, atomically with the generation check.

        Returns ``"promoted"``; or, when the generation moved on while the task
        was talking to the TV, ``"stopped"`` (a stop landed and nothing owns
        playback now, so the TV needs another Stop after the Play that went
        out) or ``"superseded"`` (a newer cast or show owns playback, or the app
        is closing; it will address the TV itself). The one before a promoted
        cast is replaced, its item left registered.
        """
        with self.lock:
            if not self.is_current(cast.generation):
                if self.owner is None and not self._closed.is_set():
                    return "stopped"
                return "superseded"
            previous, self.current = self.current, cast
            cast.promoted = True
        if previous is not None and previous is not cast:
            previous.replace()
        self.stay_awake.start()
        return "promoted"

    def _cast_ended(self, cast: Cast) -> None:
        if cast.promoted:
            self.stay_awake.stop()

    def stop(self) -> None:
        """Stop the show or cast and tell the TV; a task still preparing is cancelled."""
        with self.lock:
            self.generation += 1
            owner, self.owner = self.owner, None
            cast = self.current
        if isinstance(owner, Show):
            owner.stop()
        sent = cast.stop() if cast is not None and not cast.terminal else False
        if not sent:
            avt = self.tv_control()
            if avt is not None:
                try:
                    dlna.soap(avt, AVT, "Stop")
                except Exception:
                    pass

    @property
    def show_now(self) -> Show | None:
        owner = self.owner
        return owner if isinstance(owner, Show) else None

    # ------------------------------------------------------------- sources
    def source(self, name: str):
        src = self.sources.get(name)
        if src is None:
            raise NotMedia("unknown_source", "No such source: %s" % name, source=name)
        return src

    def resolve(self, source: str, source_id: str, quality: str = "auto"):
        if source == "local":
            return self.local.resolve(source_id, quality)
        return self.source(source).resolve(source_id, quality)

    def set_interval(self, value) -> None:
        if not valid_interval(value):
            raise ConfigError("bad_interval", "The interval must be between %d and %d seconds."
                              % (INTERVAL_MIN, INTERVAL_MAX))
        self.settings.set("interval", value)
        show = self.show_now
        if show is not None:
            show.interval = float(value)

    # -------------------------------------------------------------- status
    def status(self) -> dict:
        cast = self.current
        show = self.show_now
        sources = {}
        for name, src in self.sources.items():
            try:
                sources[name] = src.status()
            except CastError as e:
                sources[name] = {"state": "error", "detail": {"error": e.as_dict()}}
        return {"app": APP_NAME, "version": __version__, "tv": self.public_tv(),
                "tvs": self.public_tvs(), "discovering": self.discovering,
                "cast": cast.as_dict() if cast else None,
                "show": show.as_dict() if show else None,
                "sources": sources, "addresses": list(self.addresses),
                "session": [e.as_dict() for e in self.local.entries()],
                "errors": len(self.errors), "errors_seq": self.errors.seq,
                "settings": self.settings.as_dict(),
                "firewall_hint": firewall_hint(self.server.port),
                "uptime": round(time.time() - self.started_at)}

    def api(self, handler, path: str, query: str) -> None:
        from castlib import api
        api.dispatch(self, handler, path, query)


def _is_cast_tv(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read(4096).decode("utf-8", "replace")).get("app") == APP_NAME
    except Exception:
        return False
