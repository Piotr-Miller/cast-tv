"""Time how long a release file takes to reach a usable window, cold and warm, and compare two builds.

    python packaging/startup_time.py <binary> --mode cold|warm [--runs 5] --out result.json
    python packaging/startup_time.py --compare nuitka.json pyinstaller.json --warm-ratio 0.5

Each run launches the file with ``-p <free port>``, as a person would start it, and waits for
the Ready mark (s16-faster-start): the cast-tv window is on screen (``shown_at``) and the page
has rendered its first status (``ui_ready_at``). The time is the later of the two minus the
launch. Then the run ends that instance the way ``smoke.py`` does, by an ownership-checked
Quit that waits for the process and the port.

Before every run no cast-tv may be running: not on another port, not as a bootstrap still
unpacking, not the measured file. Any process whose executable is named ``cast-tv*``, lies in
the cast-tv cache folder or is the measured file counts, and so does anything answering on
127.0.0.1:8895. When the process list cannot be read completely, the script refuses rather
than guesses.

Cold: before each run the build's cache folder (the ``Cache:`` line of ``--version``; none for
PyInstaller) is deleted, after checking it is a build folder under the cast-tv cache. Warm: one
unmeasured start first, then the measured ones.

Exit codes: 0 done; 1 a run failed or never got ready; 2 refused (cast-tv running, an unreadable
process list, an unexpected cache path); 3 the file has no Ready mark (built before
s16-faster-start).
"""
import argparse
import hashlib
import json
import os
import platform as _platform
import shutil
import subprocess
import sys
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (_HERE, os.path.dirname(_HERE)):          # smoke.py next to it; castlib from the checkout
    if _path not in sys.path:
        sys.path.insert(0, _path)

import smoke                                              # noqa: E402
from castlib import bundle                                # noqa: E402
from castlib.processes import IncompleteListing, running_images   # noqa: E402

READY_TIMEOUT = 120.0
CLEAR_TIMEOUT = 30.0
DEFAULT_PORT = 8895


class Refused(Exception):
    """Measuring now would give a wrong number or delete the wrong thing (exit 2)."""


class NoReadyMark(Exception):
    """The file's status has no Ready fields: it was built before s16-faster-start (exit 3)."""


class RunFailed(Exception):
    """A run ended early or did not get ready in time (exit 1)."""


def median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _same(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def is_cast_tv(image: str, binary: str, parent: str) -> bool:
    """A cast-tv release, bootstrap or cached child, or the measured file itself."""
    if os.path.basename(image).lower().startswith("cast-tv"):
        return True
    if _same(image, binary):
        return True
    inside = os.path.normcase(os.path.abspath(image))
    return inside.startswith(os.path.normcase(os.path.abspath(parent)) + os.sep)


def cast_tv_processes(binary: str, images=running_images, parent=None) -> list[tuple[int, str]]:
    parent = parent or bundle.cache_parent()
    try:
        listed = images()
    except IncompleteListing as e:
        raise Refused("the process list is incomplete (%s); close cast-tv and try again" % e)
    return [(pid, img) for pid, img in listed if is_cast_tv(img, binary, parent) and pid != os.getpid()]


def default_port_answers(port=DEFAULT_PORT) -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/status" % port, timeout=2):
            return True
    except Exception:
        return False


def preflight(binary: str, images=running_images, answers=default_port_answers, parent=None,
              wait: float = 0.0, clock=time.monotonic, sleep=time.sleep) -> None:
    """Refuse while any cast-tv runs; ``wait`` seconds of grace for the previous run's processes to go."""
    deadline = clock() + wait
    while True:
        running = cast_tv_processes(binary, images, parent)
        busy = answers()
        if not running and not busy:
            return
        if clock() >= deadline:
            what = ", ".join("%d %s" % p for p in running) or "something on 127.0.0.1:%d" % DEFAULT_PORT
            raise Refused("cast-tv is running (%s); close it first" % what)
        sleep(0.5)


def cache_from_version(text: str) -> str | None:
    """The folder named on ``--version``'s ``Cache:`` line; None for ``Cache: none`` or no such line."""
    for line in text.splitlines():
        if line.startswith("Cache:"):
            value = line[len("Cache:"):].strip()
            return None if value in ("", "none") else value
    return None


def clear_cache(folder: str | None, valid=bundle.is_build_folder, remove=shutil.rmtree) -> None:
    """Cold mode: delete the build's unpacked files, but only a real build folder under the cast-tv cache."""
    if folder is None:
        return
    if not valid(folder):
        raise Refused("--version names %r, which is not a build folder under %s" % (folder, bundle.cache_parent()))
    if os.path.isdir(folder):
        remove(folder)


def ready_seconds(instance: dict, launched: float) -> float | None:
    if "ui_ready_at" not in instance or "shown_at" not in instance:
        raise NoReadyMark("this build has no Ready mark (built before s16-faster-start)")
    ready, shown = instance.get("ui_ready_at"), instance.get("shown_at")
    if ready is None or shown is None:
        return None
    return max(ready, shown) - launched


def fetch_status(port: int) -> dict:
    with urllib.request.urlopen("http://127.0.0.1:%d/api/status" % port, timeout=2) as r:
        return json.loads(r.read())


def measure_once(binary: str, *, port=None, popen=subprocess.Popen, status=fetch_status, stop=smoke.stop,
                 owns=smoke.owns, clock=time.time, sleep=time.sleep, timeout=READY_TIMEOUT,
                 hold: float = 0.0, out=print) -> float:
    """One timed start. ``hold`` > 0 (a watched run): print the time the moment it is ready and keep
    the window open that many seconds, so a person can check it was really usable then."""
    port = port or smoke.free_port()
    launched = clock()
    proc = popen([binary, "-p", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    instance = None
    try:
        while True:
            if proc.poll() is not None:
                raise RunFailed("cast-tv exited early (%s)" % proc.returncode)
            try:
                candidate = status(port).get("instance")
            except (OSError, ValueError):
                candidate = None                       # not listening yet
            if candidate is not None:
                if not owns(proc, candidate):
                    raise Refused("port %d answered from another process" % port)
                instance = candidate
                seconds = ready_seconds(candidate, launched)
                if seconds is not None:
                    if hold > 0:
                        out("ready after %.2f s: the window stays open %.0f s" % (seconds, hold))
                        sleep(hold)
                    return seconds
            if clock() - launched > timeout:
                raise RunFailed("no Ready mark within %.0f s" % timeout)
            sleep(0.05)
    finally:
        stop(proc, port, instance)


def run_series(binary: str, mode: str, runs: int, *, version_text: str, measure=measure_once,
               check=preflight, clear=clear_cache, out=print) -> list[float]:
    folder = cache_from_version(version_text)
    if mode == "warm":
        check(binary, wait=CLEAR_TIMEOUT)
        measure(binary)                                # the priming start: unpacks, not measured
    times = []
    for i in range(runs):
        check(binary, wait=CLEAR_TIMEOUT)
        if mode == "cold":
            clear(folder)
        seconds = measure(binary)
        times.append(seconds)
        out("%s run %d: %.2f s" % (mode, i + 1, seconds))
    return times


def compare(nuitka: dict, pyinstaller: dict, warm_ratio: float) -> tuple[list[str], bool]:
    if nuitka["mode"] != pyinstaller["mode"]:
        raise ValueError("the two results are of different modes: %s and %s" % (nuitka["mode"], pyinstaller["mode"]))
    if nuitka["system"] != pyinstaller["system"]:
        raise ValueError("the two results come from different systems")
    limit = 1.0 if nuitka["mode"] == "cold" else warm_ratio
    ratio = nuitka["median"] / pyinstaller["median"]
    ok = ratio <= limit + 1e-9
    lines = ["%s: Nuitka median %.2f s, PyInstaller median %.2f s, ratio %.3f (limit %.2f): %s"
             % (nuitka["mode"], nuitka["median"], pyinstaller["median"], ratio, limit, "PASS" if ok else "FAIL")]
    return lines, ok


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("binary", nargs="?")
    ap.add_argument("--mode", choices=("cold", "warm"))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2, metavar=("NUITKA_JSON", "PYINSTALLER_JSON"))
    ap.add_argument("--warm-ratio", type=float, default=0.5)
    ap.add_argument("--hold", type=float, default=0.0,
                    help="a watched run: keep the window open this many seconds after the Ready mark")
    args = ap.parse_args(argv)
    if args.compare:
        with open(args.compare[0], encoding="utf-8") as a, open(args.compare[1], encoding="utf-8") as b:
            lines, ok = compare(json.load(a), json.load(b), args.warm_ratio)
        print("\n".join(lines))
        return 0 if ok else 1
    if not args.binary or not args.mode or not args.out:
        ap.error("give a binary, --mode and --out (or --compare)")
    binary = os.path.abspath(args.binary)
    try:
        preflight(binary)
        version = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=180).stdout
        measure = (lambda b: measure_once(b, hold=args.hold)) if args.hold > 0 else measure_once
        times = run_series(binary, args.mode, args.runs, version_text=version, measure=measure)
    except Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    except NoReadyMark as e:
        print(str(e), file=sys.stderr)
        return 3
    except RunFailed as e:
        print("failed: %s" % e, file=sys.stderr)
        return 1
    result = {"binary": binary, "size": os.path.getsize(binary), "sha256": _sha256(binary),
              "version": version.strip().splitlines(), "system": "%s %s" % (_platform.system(), _platform.release()),
              "mode": args.mode, "runs": times, "median": median(times)}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print("%s median: %.2f s (%d runs) -> %s" % (args.mode, result["median"], len(times), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
