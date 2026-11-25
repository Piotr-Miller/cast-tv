"""Smoke-test a built cast-tv binary: the client is built in, a browser is found, HEIC decodes, the UI serves,
and the cast-tv window opens on the expected engine.

    python packaging/smoke.py dist/cast-tv-linux-x64
    python packaging/smoke.py --nuitka dist/cast-tv-linux-x64

``--version`` must end with a ``Cache:`` line: for a Nuitka file (``--nuitka``) a build folder
under the cast-tv cache whose name matches the build identity grammar, otherwise ``none``.

Exits non-zero on the first failure. Starts the binary with ``--no-browser`` on a
spare port, waits up to 60 s for ``/ui/``, reads ``/api/status`` (it must list the nextcloud source), then ends it with
``POST /api/quit`` and checks the port is free again: on Windows the onefile exe is a
bootloader and a child, and killing the process this script started ends only the bootloader.
Then ``--window-check`` shows ``/ui/`` in the window and reads it back; on Linux
the whole script runs under ``xvfb-run``.
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)                            # castlib from the checkout

from castlib import bundle                                # noqa: E402

WINDOW = "Window: edgechromium" if sys.platform == "win32" else "Window: qtwebengine"


def run(binary, *args) -> str:
    out = subprocess.run([binary, *args], capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        sys.exit("%s %s failed (%d): %s%s" % (binary, " ".join(args), out.returncode, out.stdout, out.stderr))
    if "--window-check" in args and any(label in out.stderr for label in ("Fontconfig error:", "Fontconfig warning:")):
        sys.exit("the window check reported Fontconfig diagnostics: %s" % out.stderr)
    return out.stdout


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get(port, path) -> tuple[int, bytes]:
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=5) as r:
        return r.status, r.read()


def answers(port) -> bool:
    try:
        get(port, "/api/status")
        return True
    except OSError:
        return False


def owns(proc, instance) -> bool:
    """A direct binary or its onefile child answered; an existing session never qualifies."""
    return (proc.poll() is None and isinstance(instance, dict) and bool(instance.get("id"))
            and proc.pid in (instance.get("pid"), instance.get("parent_pid")))


def kill_tree(proc) -> None:
    if proc.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        if proc.poll() is None:
            proc.kill()
    proc.wait(timeout=30)


def quit_owned(proc, port, instance) -> bool:
    """Re-check and quit over one TCP connection, which cannot switch to a replacement listener."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/api/status")
        response = connection.getresponse()
        state = json.loads(response.read())
        if not isinstance(state, dict):
            return False
        candidate = state.get("instance")
        if (response.status != 200 or not owns(proc, candidate) or candidate["id"] != instance["id"]
                or connection.sock is None):        # never reconnect to send Quit after Connection: close
            return False
        connection.request("POST", "/api/quit", body=json.dumps({"instance": instance["id"]}),
                           headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        response.read()
        return response.status == 200
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def stop(proc, port, instance=None) -> bool:
    """Quit only the verified instance; on failure kill only the process tree we launched."""
    if not owns(proc, instance) or not quit_owned(proc, port, instance):
        kill_tree(proc)
        return False
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass
    deadline = time.time() + 30
    while answers(port) and time.time() < deadline:
        time.sleep(0.5)
    if proc.poll() is None or answers(port):
        kill_tree(proc)
        return False
    return True


def cache_problem(version: str, nuitka: bool, is_build_folder=bundle.is_build_folder) -> str | None:
    """Why ``--version``'s ``Cache:`` line is wrong for this packager, or None when it is right."""
    lines = [line[len("Cache:"):].strip() for line in version.splitlines() if line.startswith("Cache:")]
    if len(lines) != 1:
        return "--version has %d Cache: lines, expected one" % len(lines)
    folder = lines[0]
    if not nuitka:
        return None if folder == "none" else "a PyInstaller file names a cache folder: %s" % folder
    if folder == "none":
        return "the Nuitka file does not know its cache folder (Cache: none)"
    if not is_build_folder(folder):
        return "the Nuitka cache folder %s is not a build folder under %s" % (folder, bundle.cache_parent())
    return None


def main(binary, nuitka=False) -> int:
    print("size: %d bytes" % os.path.getsize(binary))
    version = run(binary, "--version")
    print(version.strip())
    problem = cache_problem(version, nuitka)
    if problem:
        sys.exit(problem)
    # pywebview falls back to another engine quietly: the line names the one that would load
    if WINDOW not in version.splitlines():
        sys.exit("the cast-tv window would not use the expected engine (%s)" % WINDOW)
    if "Google Photos client: built in" not in version:
        sys.exit("the Google client is not built in")
    # both runner images carry Chrome (Windows also Edge): discovery must name one, without launching it
    if "GoPro window: " not in version or "GoPro window: none found" in version:
        sys.exit("no browser for the gopro.com window was found on this runner")
    print(run(binary, "--self-check").strip())
    port = free_port()
    proc = subprocess.Popen([binary, "--no-browser", "-p", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ended = False
    instance = None
    try:
        deadline = time.time() + 60
        while True:
            if proc.poll() is not None:
                sys.exit("the server exited early (%d)" % proc.returncode)
            try:
                status, body = get(port, "/api/status")
                state = json.loads(body)
                candidate = state.get("instance")
                if not owns(proc, candidate):
                    sys.exit("the smoke port answered from another process")
                instance = candidate
                break
            except OSError:
                if proc.poll() is not None:
                    sys.exit("the server exited early (%d)" % proc.returncode)
                if time.time() > deadline:
                    sys.exit("/ui/ never answered")
                time.sleep(1)
        status, body = get(port, "/ui/")
        if status != 200 or b"cast-tv" not in body:
            sys.exit("/ui/ answered %d" % status)
        gphotos = state["sources"]["gphotos"]["state"]
        # the Nextcloud source (and the defusedxml it imports) must have loaded in the binary
        nextcloud = (state["sources"].get("nextcloud") or {}).get("state")
        if not nextcloud or nextcloud == "error":
            sys.exit("/api/status lists no working nextcloud source")
        print("/ui/ 200, /api/status 200, gphotos %s, nextcloud %s" % (gphotos, nextcloud))
    finally:
        ended = stop(proc, port, instance)   # no HTTP Quit until ownership is established
    if not ended:
        sys.exit("the server did not end on POST /api/quit")
    print("POST /api/quit: ended, port %d free" % port)
    started = time.time()
    print("%s (%.1f s)" % (run(binary, "--window-check").strip(), time.time() - started))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    nuitka = "--nuitka" in args
    paths = [a for a in args if a != "--nuitka"]
    if len(paths) != 1:
        sys.exit("usage: python packaging/smoke.py [--nuitka] <binary>")
    sys.exit(main(os.path.abspath(paths[0]), nuitka))   # Python 3.14 on Windows will not start "dist/x.exe"
