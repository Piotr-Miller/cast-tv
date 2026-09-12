"""One supervised task per cast, and a show as a loop over casts.

The one-shot script's poll loop becomes ``Cast``: the state lives on the
object, the constraints history hardened stay (``RelTime`` arrives as
``0:00:00`` and is never compared against a literal; ``started`` latches on
PLAYING/PAUSED_PLAYBACK only; TRANSITIONING gets the longer budget), and the
"TV fetched zero bytes" diagnosis reads the item's request counter.

Ownership is the app's: every ``App.cast()`` / ``App.show()`` bumps a
generation, and a task checks it is still current *after* preparing its
material and *before* sending anything to the TV, then once more, under the
app's lock, when it takes the seat (``App._promote``): a stop or a newer owner
that landed during the SOAP round-trips wins, and the task ends cancelled
instead of undoing it. Tasks run on a single-worker executor, so two
requests accepted a second apart are ordered: the second wins, the first is
skipped (not yet sent) or replaced (already playing). A replaced item stays
registered until the registry evicts it.
"""
from __future__ import annotations

import threading
import time
import urllib.error
from xml.sax.saxutils import escape

from castlib import dlna, photos
from castlib.diagnostics import check_codecs, explain_failure
from castlib.dlna import AVT
from castlib.errors import CastError, TVError
from castlib.media import didl
from castlib.platform import firewall_hint

POLL_INTERVAL = 2.0           # seconds between GetTransportInfo calls
BUDGET_TRANSITIONING = 40.0   # TRANSITIONING is still an attempt
BUDGET_OTHER = 24.0           # STOPPED after Play for this long is a refusal
UNREACHABLE_AFTER = 3         # consecutive poll failures before the TV counts as gone
TICK = 0.25                   # reaction time of the show's wait loops, not a deadline

TERMINAL = ("stopped", "failed", "replaced", "cancelled")


def upnp_error(e) -> tuple[str, str]:
    """``(errorCode, errorDescription)`` from a SOAP fault's body; the body is read once and kept."""
    body = getattr(e, "_castlib_body", None)
    if body is None:
        try:
            body = e.read(4096).decode("utf-8", "replace") if hasattr(e, "read") else ""
        except Exception:
            body = ""
        try:
            e._castlib_body = body
        except Exception:
            pass
    return dlna.tag(body, "errorCode"), dlna.tag(body, "errorDescription")


def describe_soap_error(e) -> str:
    """``HTTP Error 500`` plus the UPnP error code and text the TV put in the body, when it did."""
    text = str(e)
    code, desc = upnp_error(e)
    if code or desc:
        text += " (UPnP %s%s)" % (code, ": " + desc if desc else "")
    return text


def item_summary(item) -> dict:
    prep = item.prepared
    return {"source": item.source, "id": item.source_id, "name": item.title,
            "kind": item.kind, "mime": item.mime,
            "converted": bool(prep is not None and prep.mime != item.mime),
            "width": item.width, "height": item.height, "size": item.size}


class Cast:
    """One attempt to put one item on the TV, and the watch over it."""

    def __init__(self, app, item, generation, subtitle=None):
        self.app = app
        self.item = item
        self.subtitle = subtitle
        self.generation = generation
        self.state = "preparing"
        self.tv_state = ""          # CurrentTransportState as the TV reports it
        self.started = False
        self.position = ""          # RelTime as reported: "0:00:00", not zero-padded
        self.duration = ""
        self.reason: CastError | None = None
        self.media_line: str | None = None   # ffprobe's one-line description, after a refusal
        self.reasons: list[str] = []         # ffprobe's reasons, for the CLI to print
        self.promoted = False                # this cast reached the TV
        self.created = time.time()
        self.play_at: float | None = None
        self.sent = threading.Event()   # Play returned, or the cast failed before that
        self.done = threading.Event()   # a terminal state was reached
        self.watchers: list[threading.Event] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._stopping = False
        self.thread: threading.Thread | None = None

    # ------------------------------------------------------------ the task
    def run(self) -> None:
        """The executor task: prepare, check the generation, register, SetAVTransportURI + Play."""
        app = self.app
        try:
            self._prepare()
        except CastError as e:
            self._finish("failed", e)
            return
        except Exception as e:
            self._finish("failed", CastError(
                "prepare_failed", "Could not prepare %s: %s" % (self.item.title, e),
                source=self.item.source, item=self.item.source_id))
            return
        if not app.is_current(self.generation):
            self._finish("cancelled")           # a newer cast or show took over meanwhile
            return
        avt = app.tv_control()
        if avt is None:
            self._finish("failed", TVError(
                "no_tv", "No TV selected.",
                hint="Switch the TV on and search again, or enter its address."))
            return
        self._register()
        url = app.server.media_url(self.item)
        try:
            dlna.soap(avt, AVT, "SetAVTransportURI",
                      "<CurrentURI>%s</CurrentURI><CurrentURIMetaData>%s</CurrentURIMetaData>"
                      % (escape(url), didl(self.item, url)))
            try:
                dlna.soap(avt, AVT, "Play", "<Speed>1</Speed>")
            except urllib.error.HTTPError as e:
                # The Samsung fetches a still during SetAVTransportURI and is already
                # PLAYING when Play arrives, which it refuses as "701: Transition not
                # available". The transport state, not the fault, says whether it plays.
                if upnp_error(e)[0] != "701" or not self._already_playing(avt):
                    raise
        except Exception as e:
            if (isinstance(e, urllib.error.HTTPError) and upnp_error(e)[0] == "716"
                    and self.item.requests == 0):
                # The Samsung probes the address inside SetAVTransportURI; when the
                # port is closed it answers "716: Resource not found" at once, so this
                # is the firewall case, not a bad file.
                self._finish("failed", self._fetched_nothing())
                return
            self._finish("failed", TVError(
                "tv_rejected", "The TV rejected the request: %s" % describe_soap_error(e),
                source=self.item.source, item=self.item.source_id))
            return
        with self._lock:
            self.play_at = time.time()
            self.state = "starting"
        verdict = app._promote(self)
        if verdict != "promoted":
            if verdict == "stopped":
                # The stop's own Stop went out before our Play; send another
                # so the TV does not keep playing what the user just stopped.
                try:
                    dlna.soap(avt, AVT, "Stop")
                except Exception:
                    pass
            self._finish("cancelled")
            return
        self.sent.set()
        self.thread = threading.Thread(target=self._poll, name="cast-poll", daemon=True)
        self.thread.start()

    def _already_playing(self, avt) -> bool:
        try:
            state = dlna.tag(dlna.soap(avt, AVT, "GetTransportInfo"), "CurrentTransportState")
        except Exception:
            return False
        return state in ("PLAYING", "TRANSITIONING", "PAUSED_PLAYBACK")

    def _prepare(self) -> None:
        item = self.item
        if self.app.debug:
            item.debug = True
        if item.kind == "photo":
            photos.prepare(item)
        elif item.kind == "video" and item.path and self.app.codec_check:
            bad, cmd = check_codecs(item.path)
            if bad:
                self.app.errors.push(CastError(
                    "dts_audio", "%s audio - Samsung cannot decode it, playback will be silent."
                    % "/".join(bad), hint=cmd, source=item.source, item=item.source_id))

    def _register(self) -> None:
        reg = self.app.registry
        srv = self.app.server
        sub = self.subtitle
        if sub is not None and not sub.id:
            reg.add(sub)                     # the subtitle first, so the video never references a missing route
            self.item.caption = (sub.path, srv.media_url(sub))
        if not self.item.id or reg.get(self.item.id) is not self.item:
            reg.add(self.item)
        else:
            reg.revive(self.item.id)         # a show's prev: retired when replaced, playing again now
        if sub is not None:
            sub.parent = self.item.id

    # ------------------------------------------------------------ the watch
    def _poll(self) -> None:
        avt = self.app.tv_control()
        failures = 0
        while not self._stop.is_set():
            if self._stop.wait(POLL_INTERVAL):
                break
            try:
                state, rel, dur = dlna.transport_state(avt)
            except Exception:
                failures += 1
                if failures >= UNREACHABLE_AFTER:
                    self.app.tv_unreachable()
                    self._finish("failed", TVError(
                        "tv_unreachable", "The TV stopped answering.",
                        hint="Check it is on and on the same network, then retry.",
                        source=self.item.source, item=self.item.source_id))
                    return
                continue
            failures = 0
            with self._lock:
                self.tv_state, self.position, self.duration = state, rel, dur
                if state in ("PLAYING", "PAUSED_PLAYBACK"):
                    self.started = True
                    self.state = "playing" if state == "PLAYING" else "paused"
            if state in ("PLAYING", "PAUSED_PLAYBACK"):
                continue
            if not self.started:
                # TRANSITIONING is still an attempt; STOPPED after it is a refusal
                budget = BUDGET_TRANSITIONING if state == "TRANSITIONING" else BUDGET_OTHER
                if time.time() - self.play_at >= budget:
                    self._finish("failed", self._never_started())
                    return
            elif state == "STOPPED":
                self._finish("stopped")
                return

    def _fetched_nothing(self) -> TVError:
        return TVError(
            "tv_fetched_nothing",
            "The TV never started playing and never asked for the file.",
            hint="That is almost always the firewall. Open the port:  "
                 + firewall_hint(self.app.server.port),
            source=self.item.source, item=self.item.source_id)

    def _never_started(self) -> TVError:
        item = self.item
        if item.requests == 0:
            return self._fetched_nothing()
        reasons: list[str] = []
        if item.kind == "video":
            target = item.path
            if target is None and item.resolve is not None:
                try:
                    target = item.resolve().url     # ffprobe reads over HTTP(S), as the CLI always did
                except Exception:
                    target = None
            if target:
                self.media_line, reasons = explain_failure(target)
        self.reasons = reasons
        hint = None
        if reasons:
            hint = "; ".join(reasons) + ". Try a lighter variant:  cast-gopro <n> -q proxy"
        return TVError("tv_never_started", "The TV never started playing.", hint=hint,
                       source=item.source, item=item.source_id)

    # ------------------------------------------------------------- endings
    def _finish(self, state: str, reason: CastError | None = None) -> None:
        with self._lock:
            if self.state in TERMINAL:
                return
            self.state = state
            self.reason = reason
        self._stop.set()
        if reason is not None:
            self.app.errors.push(reason)
        if self.item.id:
            self.app.registry.retire(self.item.id)   # served until idle, never yanked
        else:
            photos.release(self.item)        # never registered: no eviction will unpin it
        self.sent.set()
        self.done.set()
        for ev in self.watchers:
            ev.set()
        self.app._cast_ended(self)

    def stop(self) -> bool:
        """Tell the TV to stop and end the watch; safe to call twice. True when Stop was sent."""
        with self._lock:
            if self.state in TERMINAL or self._stopping:
                return False
            self._stopping = True
        sent = False
        avt = self.app.tv_control()
        if avt is not None and self.promoted:
            try:
                dlna.soap(avt, AVT, "Stop")
                sent = True
            except Exception:
                pass
        self._finish("stopped")
        return sent

    def replace(self) -> None:
        """A newer cast is on the TV; this one ends without touching playback."""
        self._finish("replaced")

    def cancel(self) -> None:
        self._finish("cancelled")

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL

    def as_dict(self) -> dict:
        with self._lock:
            d = {"id": self.item.id or None, "state": self.state, "tv_state": self.tv_state,
                 "started": self.started, "position": self.position,
                 "duration": self.duration, "requests": self.item.requests,
                 "since": self.play_at, "generation": self.generation,
                 "error": self.reason.as_dict() if self.reason else None}
        d.update(item_summary(self.item))
        return d


class Show:
    """Plays a queue in selection order: photos hold for the interval, videos play to the end."""

    def __init__(self, app, items, interval, generation):
        self.app = app
        self.items = list(items)
        self.interval = float(interval)
        self.generation = generation
        self.index = -1
        self.current: Cast | None = None
        self.skipped = 0
        self._state = "playing"
        self._paused = False
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self._cmd: str | None = None
        self._wake = threading.Event()
        self._lock = threading.RLock()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run, name="show", daemon=True)

    def start(self) -> None:
        self.thread.start()

    # --------------------------------------------------------------- loop
    def run(self) -> None:
        app = self.app
        app.stay_awake.start()
        try:
            i, n = 0, len(self.items)
            while 0 <= i < n:
                if not app.is_current(self.generation):
                    self._end("cancelled")
                    return
                self.index = i
                self._prefetch(i + 1)
                with self._lock:
                    self._paused, self._paused_at, self._paused_total = False, None, 0.0
                cast = Cast(app, self.items[i], self.generation)
                cast.watchers.append(self._wake)
                self.current = cast
                app._submit(cast)
                outcome = self._wait(cast, single=(n == 1))
                if outcome == "cancelled":
                    self._end("cancelled")
                    return
                if outcome == "stop":
                    self._end("stopped")
                    return
                if outcome == "failed":
                    self.skipped += 1
                if outcome == "prev":
                    i = max(0, i - 1)
                    continue
                i += 1
            self._end("finished")
        finally:
            app.stay_awake.stop()

    def _prefetch(self, start: int) -> None:
        ahead = [it for it in self.items[start:start + 2] if it.kind == "photo"]
        if ahead:
            try:
                photos.prefetch(ahead)
            except Exception:
                pass

    def _wait(self, cast: Cast, single: bool) -> str:
        """Block until this item's turn is over; returns why."""
        while True:
            self._wake.wait(TICK)
            self._wake.clear()
            with self._lock:
                cmd, self._cmd = self._cmd, None
            if cmd == "stop":
                return "stop"
            if cmd in ("next", "prev"):
                return cmd
            if not self.app.is_current(self.generation):
                return "cancelled"
            state = cast.state
            if state in ("replaced", "cancelled"):
                return "cancelled"              # a manual cast took over
            if state == "failed":
                return "failed"
            if state == "stopped":
                return "advanced"               # a video played to its end
            if cast.item.kind == "photo" and not single:
                remaining = self.remaining(cast)
                if remaining is not None and remaining <= 0:
                    return "advanced"

    def remaining(self, cast: Cast | None = None) -> float | None:
        """Seconds until the next item; counted from a successful ``Play``, frozen while paused."""
        cast = cast or self.current
        if cast is None or cast.play_at is None or cast.item.kind != "photo":
            return None
        if len(self.items) == 1:
            return None                         # a queue of one holds until stop
        with self._lock:
            paused = self._paused_total
            if self._paused and self._paused_at is not None:
                paused += time.time() - self._paused_at
        return self.interval - (time.time() - cast.play_at - paused)

    def _end(self, state: str) -> None:
        with self._lock:
            if self._state in ("finished", "stopped", "cancelled"):
                return
            self._state = state
        cast = self.current
        if cast is not None and state in ("finished", "stopped"):
            cast.stop()                         # a held photo ends here; a finished video is a no-op
        self.done.set()

    # ------------------------------------------------------------ controls
    def _signal(self, cmd: str) -> None:
        with self._lock:
            self._cmd = cmd
        self._wake.set()

    def pause(self) -> None:
        with self._lock:
            if self._paused or self._state != "playing":
                return
            self._paused, self._paused_at = True, time.time()
        cast = self.current
        if cast is not None and cast.item.kind == "video" and cast.sent.is_set():
            self._soap("Pause")
        self._wake.set()

    def resume(self) -> None:
        with self._lock:
            if not self._paused:
                return
            self._paused = False
            if self._paused_at is not None:
                self._paused_total += time.time() - self._paused_at
            self._paused_at = None
        cast = self.current
        if cast is not None and cast.item.kind == "video" and cast.sent.is_set():
            self._soap("Play", "<Speed>1</Speed>")
        self._wake.set()

    def next(self) -> None:
        self._signal("next")

    def prev(self) -> None:
        self._signal("prev")

    def stop(self) -> None:
        self._signal("stop")

    def cancel(self) -> None:
        """A newer owner exists; end without touching the TV."""
        self._end("cancelled")
        self._wake.set()

    def _soap(self, action: str, body: str = "") -> None:
        avt = self.app.tv_control()
        if avt is None:
            return
        try:
            dlna.soap(avt, AVT, action, body)
        except Exception:
            pass

    @property
    def state(self) -> str:
        with self._lock:
            if self._state != "playing":
                return self._state
            return "paused" if self._paused else "playing"

    @property
    def terminal(self) -> bool:
        return self.state in ("finished", "stopped", "cancelled")

    def as_dict(self) -> dict:
        idx = self.index
        cur = self.items[idx] if 0 <= idx < len(self.items) else None
        nxt = self.items[idx + 1] if 0 <= idx + 1 < len(self.items) else None
        remaining = self.remaining()
        return {"id": self.generation, "index": idx, "total": len(self.items),
                "interval": self.interval, "state": self.state, "skipped": self.skipped,
                "current": item_summary(cur) if cur else None,
                "next": item_summary(nxt) if nxt else None,
                "remaining": None if remaining is None else max(0.0, round(remaining, 1)),
                "items": [item_summary(it) for it in self.items]}
