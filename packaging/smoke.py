"""Smoke-test a built cast-tv binary: the client is built in, a browser is found, HEIC decodes, the UI serves,
and the cast-tv window opens on the expected engine.

    python packaging/smoke.py dist/cast-tv-linux-x64

Exits non-zero on the first failure. Starts the binary with ``--no-browser`` on a
spare port, waits up to 60 s for ``/ui/``, reads ``/api/status``, then stops it.
Then ``--window-check`` shows ``/ui/`` in the window and reads it back; on Linux
the whole script runs under ``xvfb-run``.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

PORT = 8099
WINDOW = "Window: edgechromium" if sys.platform == "win32" else "Window: qtwebengine"


def run(binary, *args) -> str:
    out = subprocess.run([binary, *args], capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        sys.exit("%s %s failed (%d): %s%s" % (binary, " ".join(args), out.returncode, out.stdout, out.stderr))
    return out.stdout


def get(path) -> tuple[int, bytes]:
    with urllib.request.urlopen("http://localhost:%d%s" % (PORT, path), timeout=5) as r:
        return r.status, r.read()


def main(binary) -> int:
    print("size: %d bytes" % os.path.getsize(binary))
    version = run(binary, "--version")
    print(version.strip())
    # pywebview falls back to another engine quietly: the line names the one that would load
    if WINDOW not in version.splitlines():
        sys.exit("the cast-tv window would not use the expected engine (%s)" % WINDOW)
    if "Google Photos client: built in" not in version:
        sys.exit("the Google client is not built in")
    # both runner images carry Chrome (Windows also Edge): discovery must name one, without launching it
    if "GoPro window: " not in version or "GoPro window: none found" in version:
        sys.exit("no browser for the gopro.com window was found on this runner")
    print(run(binary, "--self-check").strip())
    proc = subprocess.Popen([binary, "--no-browser", "-p", str(PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 60
        while True:
            try:
                status, body = get("/ui/")
                break
            except OSError:
                if proc.poll() is not None:
                    sys.exit("the server exited early (%d)" % proc.returncode)
                if time.time() > deadline:
                    sys.exit("/ui/ never answered")
                time.sleep(1)
        if status != 200 or b"cast-tv" not in body:
            sys.exit("/ui/ answered %d" % status)
        status, body = get("/api/status")
        gphotos = json.loads(body)["sources"]["gphotos"]["state"]
        print("/ui/ 200, /api/status 200, gphotos %s" % gphotos)
    finally:
        proc.kill()
        proc.wait(timeout=30)
    started = time.time()
    print("%s (%.1f s)" % (run(binary, "--window-check").strip(), time.time() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main(os.path.abspath(sys.argv[1])))   # Python 3.14 on Windows will not start "dist/x.exe"
