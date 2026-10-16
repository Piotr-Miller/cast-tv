"""S-12 spike on Windows 11 (context/changes/s12-desktop-window/frame.md, Discriminator Check).

Run from this folder:  py -3 run_spike.py
Needs internet for pip. Copies castlib/ui from this checkout, then writes results.txt next to this
file; send that file back. Each test opens a window for a few seconds and closes it by itself."""
import functools, http.server, os, platform, shutil, subprocess, sys, tempfile, threading, time, venv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results.txt")
VENV = os.path.join(HERE, ".venv-spike")
PY = os.path.join(VENV, "Scripts", "python.exe")
lines = []

# the UI under test is this checkout's own castlib/ui, copied next to the probes (ignored by git)
if not os.path.isdir(os.path.join(HERE, "ui")):
    shutil.copytree(os.path.join(HERE, "..", "..", "..", "..", "castlib", "ui"), os.path.join(HERE, "ui"))

def log(msg):
    print(msg, flush=True); lines.append(msg)
    with open(OUT, "w", encoding="utf-8") as f: f.write("\n".join(lines) + "\n")

def run(cmd, timeout=900, env=None):
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=HERE, env=env)
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode, time.time() - t0, out

log("S-12 spike, Windows: %s %s, Python %s" % (platform.platform(), platform.machine(), sys.version.split()[0]))

# 1. Edge in --app mode on /ui/: the server counts requests; /api/status means the page's JS ran (Alpine init -> refresh()).
hits = []
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *a): hits.append(self.path)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=HERE))
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/ui/" % srv.server_address[1]
edge = None
for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
    if base and os.path.exists(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")):
        edge = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"); break
if edge:
    prof = tempfile.mkdtemp(prefix="s12-edge-")
    t0 = time.time()
    p = subprocess.Popen([edge, "--app=" + url, "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check"])
    while time.time() - t0 < 20 and "/api/status" not in hits: time.sleep(0.2)
    first = time.time() - t0
    time.sleep(2); p.terminate()
    try: p.wait(10)
    except Exception: p.kill()
    log("1 edge --app: %s; /api/status %s after %.1fs; requests: %s" % (
        edge, "SEEN" if "/api/status" in hits else "NOT SEEN", first, sorted(set(hits))))
else:
    log("1 edge --app: msedge.exe not found")
srv.shutdown()

# 2. venv with pywebview (WebView2), PySide6 and PyInstaller
if not os.path.exists(PY):
    venv.create(VENV, with_pip=True)
rc, dt, out = run([PY, "-m", "pip", "install", "-q", "pywebview==6.2.1", "PySide6==6.12.0", "pyinstaller==6.22.3"])
log("2 pip install: rc %d in %.0fs %s" % (rc, dt, " | ".join(out[-3:])))

# 3. pywebview unfrozen (default Windows renderer: WebView2 / edgechromium)
rc, dt, out = run([PY, "probe.py"], timeout=120)
log("3 pywebview unfrozen: rc %d in %.1fs %s" % (rc, dt, [l for l in out if "RESULT" in l] or out[-5:]))

# 4. pywebview onefile, and 5. pywebview + Qt (PySide6) onefile
for n, script in ((4, "probe.py"), (5, "probe_pwq.py")):
    name = "s12-" + os.path.splitext(script)[0]
    rc, dt, out = run([PY, "-m", "PyInstaller", "--noconfirm", "--onefile", "--log-level", "WARN",
                       "--add-data", "ui;ui", "--name", name, script], timeout=1200)
    exe = os.path.join(HERE, "dist", name + ".exe")
    size = os.path.getsize(exe) if os.path.exists(exe) else 0
    log("%d build %s: rc %d in %.0fs, %d bytes" % (n, name, rc, dt, size))
    if size:
        rc, dt, out = run([exe], timeout=180)
        log("%d run %s: rc %d in %.1fs %s" % (n, name, rc, dt, [l for l in out if "RESULT" in l] or out[-5:]))
log("done")
