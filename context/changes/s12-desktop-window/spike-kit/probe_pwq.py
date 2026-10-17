"""S-12 spike probe: cast-tv's UI files served in-process, shown in a pywebview window.
Prints one RESULT line and exits 0 only if the page rendered and its JS ran."""
import functools, http.server, os, sys, threading, time
os.environ["PYWEBVIEW_GUI"] = "qt"
import webview

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
        functools.partial(H, directory=HERE))   # /ui/... maps to HERE/ui/...
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/ui/" % srv.server_address[1]
result = {"ok": False}
t0 = time.time()

def probe(window):
    time.sleep(3)   # Alpine is deferred; give it a moment after "loaded"
    try:
        result["title"] = window.evaluate_js("document.title")
        result["alpine"] = window.evaluate_js("typeof window.Alpine")
        result["ua"] = window.evaluate_js("navigator.userAgent")
        result["ok"] = result["title"] == "cast-tv" and result["alpine"] == "object"
    except Exception as e:
        result["error"] = repr(e)
    window.destroy()

w = webview.create_window("cast-tv spike", url, width=900, height=600)
w.events.loaded += lambda: threading.Thread(target=probe, args=(w,), daemon=True).start()
threading.Timer(45, lambda: (result.setdefault("error", "timeout 45 s"), w.destroy())).start()
webview.start()
print("RESULT", result, "gui=%s" % getattr(webview, "guilib", None).__name__ if getattr(webview, "guilib", None) else "", "%.1fs" % (time.time() - t0), flush=True)
# pywebview falls back to another backend quietly when Qt fails to load (2026-10-18): a pass needs gui=qt
os._exit(0 if result["ok"] and getattr(getattr(webview, "guilib", None), "__name__", "").endswith(".qt") else 1)
