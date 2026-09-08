#!/usr/bin/env python3
"""Spike: which OAuth flow can carry the Google Photos Picker scope?

The question this answers (see research.md, Open Questions #1): does Google's
limited-input-device ("device code") flow accept
`photospicker.mediaitems.readonly`, and does the resulting token actually open a
Picker session? If not, the desktop loopback flow is the fallback - so both are
here, and both end in the same proof: `POST /v1/sessions` succeeding.

    export GOOGLE_CLIENT_ID=...apps.googleusercontent.com
    export GOOGLE_CLIENT_SECRET=...        # Google requires it even for installed apps
    ./spike-picker-oauth.py device         # try the device flow
    ./spike-picker-oauth.py loopback       # try the desktop loopback flow
    ./spike-picker-oauth.py device --pick  # ...and wait for a pick, then probe baseUrl

Standard library only. Nothing is stored; tokens live for the run and are printed
only as their last four characters.

Which client type to create in Google Cloud Console -> APIs & Services -> Credentials:
  device   : "TVs and Limited Input devices"
  loopback : "Desktop app"
Enable "Google Photos Picker API" in the API library first, and add yourself as a
test user on the consent screen (testing mode is enough; no verification needed).
"""
import http.server, json, os, secrets, sys, time, urllib.parse, urllib.request, webbrowser
import base64, hashlib, threading

SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
DEVICE_CODE = "https://oauth2.googleapis.com/device/code"
TOKEN = "https://oauth2.googleapis.com/token"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
PICKER = "https://photospicker.googleapis.com/v1"


def post(url, data, headers=None):
    body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
    req = urllib.request.Request(url, body, headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw}


def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}"), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw), dict(e.headers)
        except ValueError:
            return e.code, {"raw": raw}, dict(e.headers)


def say(label, status, body):
    print("  %-28s HTTP %s  %s" % (label, status, json.dumps(body)[:300]))


def creds():
    cid, sec = os.environ.get("GOOGLE_CLIENT_ID"), os.environ.get("GOOGLE_CLIENT_SECRET")
    if not cid:
        sys.exit("Set GOOGLE_CLIENT_ID (and GOOGLE_CLIENT_SECRET) - see the docstring.")
    return cid, sec


# ------------------------------------------------------------ device code flow
def device_flow():
    cid, sec = creds()
    print("\n[1] device/code with the Picker scope - THIS is the question")
    status, body = post(DEVICE_CODE, {"client_id": cid, "scope": SCOPE})
    say("device/code", status, body)
    if status != 200:
        err = body.get("error")
        if err == "invalid_scope":
            print("\n  => CONFIRMED: the device flow refuses the Picker scope."
                  "\n     Fallback: `%s loopback`." % sys.argv[0])
        elif err == "invalid_client":
            print("\n  => Inconclusive: Google rejected the client before looking at the scope."
                  "\n     GOOGLE_CLIENT_ID must be a 'TVs and Limited Input devices' client.")
        else:
            print("\n  => device/code failed with %s - read the body above." % err)
        return None
    print("\n  => Scope ACCEPTED at device/code. Now prove the token works:")
    print("     open %s  and enter  %s" % (body["verification_url"], body["user_code"]))
    interval, deadline = int(body.get("interval", 5)), time.time() + int(body.get("expires_in", 1800))
    while time.time() < deadline:
        time.sleep(interval)
        status, tok = post(TOKEN, {
            "client_id": cid, "client_secret": sec or "", "device_code": body["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5; continue
        say("token", status, {k: (v[-4:] if k.endswith("token") else v) for k, v in tok.items()})
        if status == 200:
            return tok
        return None
    print("  timed out waiting for the code to be entered")
    return None


# ------------------------------------------------------ desktop loopback flow
def loopback_flow():
    cid, sec = creds()
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            msg = b"Done - back to the terminal." if "code" in got else b"No code in redirect."
            self.send_response(200); self.send_header("Content-Length", str(len(msg)))
            self.end_headers(); self.wfile.write(msg)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = "http://127.0.0.1:%d" % srv.server_address[1]
    threading.Thread(target=srv.handle_request, daemon=True).start()
    url = AUTH + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "code_challenge": challenge, "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(16)})
    print("\n[1] loopback: opening the consent page (redirect -> %s)" % redirect)
    print("    %s" % url)
    webbrowser.open(url)
    for _ in range(600):
        if got: break
        time.sleep(0.5)
    if "code" not in got:
        print("  no code received: %s" % got); return None
    status, tok = post(TOKEN, {
        "code": got["code"], "client_id": cid, "client_secret": sec or "",
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
    say("token", status, {k: (v[-4:] if k.endswith("token") else v) for k, v in tok.items()})
    return tok if status == 200 else None


# ------------------------------------------------------------------- picker
def prove_with_picker(tok, pick=False):
    hdr = {"Authorization": "Bearer " + tok["access_token"], "Content-Type": "application/json"}
    print("\n[2] sessions.create - the real proof that the token carries the scope")
    status, sess = post(PICKER + "/sessions", b"{}", hdr)
    say("sessions.create", status, sess)
    if status != 200:
        print("  => token was minted but the Picker API refuses it."); return
    print("  => SESSION OPENED. pickerUri:\n     %s" % sess["pickerUri"])
    print("     (open it on the phone too - that is the device-independence claim)")
    if not pick:
        post_del = urllib.request.Request(PICKER + "/sessions/" + sess["id"], method="DELETE",
                                          headers=hdr)
        try:
            urllib.request.urlopen(post_del, timeout=15); print("  session deleted")
        except Exception as e:
            print("  delete failed: %s" % e)
        return

    print("\n[3] waiting for you to pick something...")
    interval = float(sess.get("pollingConfig", {}).get("pollInterval", "5s").rstrip("s") or 5)
    while True:
        time.sleep(interval)
        status, s2, _ = get(PICKER + "/sessions/" + sess["id"], hdr)
        if s2.get("mediaItemsSet"):
            break
    status, items, _ = get(PICKER + "/mediaItems?" + urllib.parse.urlencode(
        {"sessionId": sess["id"], "pageSize": 5}), hdr)
    say("mediaItems.list", status, {"count": len(items.get("mediaItems", []))})
    for it in items.get("mediaItems", [])[:5]:
        mf = it.get("mediaFile", {})
        print("   - %-6s %s  %s" % (it.get("type"), it.get("filename") or it.get("id"),
                                   mf.get("mimeType")))
    first = (items.get("mediaItems") or [{}])[0].get("mediaFile", {}).get("baseUrl")
    if first:
        print("\n[4] baseUrl: does the fetch need the Bearer header?")
        suffix = "=dv" if items["mediaItems"][0].get("type") == "VIDEO" else "=d"
        for label, h in (("with Bearer", {"Authorization": hdr["Authorization"], "Range": "bytes=0-1"}),
                         ("without", {"Range": "bytes=0-1"})):
            st, _, rh = get(first + suffix, h)
            print("  %-14s HTTP %s  Content-Type=%s" % (label, st, rh.get("Content-Type")))
    urllib.request.urlopen(urllib.request.Request(
        PICKER + "/sessions/" + sess["id"], method="DELETE", headers=hdr), timeout=15)
    print("  session deleted")


if __name__ == "__main__":
    mode = (sys.argv[1:2] or ["device"])[0]
    pick = "--pick" in sys.argv
    tok = device_flow() if mode == "device" else loopback_flow()
    if tok:
        prove_with_picker(tok, pick)
