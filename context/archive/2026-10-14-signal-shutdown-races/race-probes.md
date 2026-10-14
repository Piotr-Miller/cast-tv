# Race probes for signal-shutdown-races

Two throwaway scripts used on 2026-10-14 to reproduce faults B and C (see
[research.md](research.md)). Use them to show the faults before the fix and their absence after it.
They are not tests: they need minutes, CPU load and luck. Run each from outside the repository,
with the project's interpreter and `-I`, passing the repository path as an argument.

Load, when asked for: `for i in $(seq $((2 * $(nproc)))); do timeout 300 sh -c 'while :; do :; done' & done`.
Stop it with `kill` on those PIDs. Do not use `pkill -f` on the loop text, because it also matches
the shell that launched it.

## 1. SIGINT after the line the CLI test waits for (fault B)

```python
"""Send SIGINT to `python -m castlib -t 127.0.0.1` at a delay after the 'does not expose' line."""
import os, signal, socket, subprocess, sys, tempfile, time
REPO = sys.argv[1]; delays = [float(x) for x in sys.argv[2].split(",")]; runs = int(sys.argv[3])
def free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
for d in delays:
    res = {}
    for _ in range(runs):
        env = dict(os.environ, HOME=tempfile.mkdtemp(), PYTHONUNBUFFERED="1", PYTHONFAULTHANDLER="1")
        p = subprocess.Popen([sys.executable, "-m", "castlib", "-p", str(free()), "--no-browser", "-t", "127.0.0.1"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, cwd=REPO)
        while True:
            l = p.stdout.readline()
            if not l or "does not expose" in l or "TV:" in l: break
        time.sleep(d)
        p.send_signal(signal.SIGINT)
        try:
            out, _ = p.communicate(timeout=8)
            k = "exit %s%s" % (p.returncode, " Stopped" if "Stopped." in out else "")
            if "Traceback" in out:
                k += " TB:" + out.strip().splitlines()[-1][:60]
        except subprocess.TimeoutExpired:
            p.send_signal(signal.SIGABRT); out, _ = p.communicate(); k = "HANG"   # faulthandler prints every thread
        res[k] = res.get(k, 0) + 1
    print(d, res, flush=True)
```

Run: `<repo>/.venv/bin/python -I sigint_probe.py <repo> 0,0.0002,0.002 25`, under load.
2026-10-14 results, 3.14.8, under load, delay 0: `{'exit 0 Stopped': 8, 'exit -2 TB:KeyboardInterrupt': 17}`.
After a fix for B, every run should be `exit 0 Stopped`.

## 2. KeyboardInterrupt inside `Event.wait` (fault C's mechanism)

```python
"""Does a KeyboardInterrupt delivered during Event.wait() ever leave the Event's lock held?"""
import random, signal, subprocess, sys, time
CHILD = r'''
import sys, threading
ev = threading.Event()
try:
    while not ev.wait(float(sys.argv[1])):
        pass
except KeyboardInterrupt:
    pass
print("ok" if ev._cond._lock.acquire(timeout=2) else "LOCK-HELD", flush=True)
'''
runs, wait = int(sys.argv[1]), sys.argv[2]
res = {}
for _ in range(runs):
    p = subprocess.Popen([sys.executable, "-c", CHILD, wait], stdout=subprocess.PIPE, text=True)
    time.sleep(0.05 + random.random() * 0.02)
    p.send_signal(signal.SIGINT)
    out, _ = p.communicate(timeout=10)
    k = out.strip() or "rc=%s" % p.returncode
    res[k] = res.get(k, 0) + 1
print(sys.version.split()[0], "wait", wait, res)
```

Run: `python3 -I event_probe.py 400 0.00001`. Results on 2026-10-14 with 3.14.8:
`{'ok': 394, 'rc=-2': 1, 'rc=1': 3, 'LOCK-HELD': 2}`. Of the `rc` results, one is the
`RuntimeError: release unlocked lock` case and three are interrupts during import. With
`wait = 1.0`, 200 runs were all ok. A fix that keeps the main thread out of `Event.wait` makes
this probe irrelevant to cast-tv: the probe tests Python, not the app.
