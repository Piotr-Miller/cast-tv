# Research: s13-gopro-auth

2026-09-20. No codebase research was run for this change; the blocking question was external.
Spikes below, run from the Fedora workstation with curl and a Chrome tab that was not signed in
to gopro.com. No GoPro credential was used or recorded.

## Spike: does GoPro publish a sign-in a third-party application may use? (2026-09-20, 21:31)

Against GoPro's own pages (gopro.com, gopro.github.io) and `api.gopro.com`, without a token.

**What the previous source said.** `context/archive/2026-09-07-cloud-source-ui/research.md:259` —
"bearer token pasted from a browser; expires in hours; no public OAuth" (2026-09-08, last updated
2026-09-10). Repeated as `context/archive/2026-09-07-cloud-source-ui/change.md:179` — "**GoPro** -
no public OAuth exists." — and as `context/changes/standalone-install/research.md:42` — "GoPro has
no public sign-in for apps; the token is pasted in the UI." (2026-09-19). None of the three carries
a link or a read date.

**Documentary half.**

- **GoPro advertises a cloud API, gated by an application** — "Cloud API (BETA) / Programmatic
  access to our media cloud service. Enables upload, download and playback of media. / Request
  Access >" (https://gopro.com/en/us/info/developer-tools, which
  https://gopro.com/en/us/info/open-gopro redirects to; read 2026-09-20). The page's lead says
  "Apply to create a developer account, download our SDKs, or use our other tools that we offer
  under open source licenses." "APPLY TO ACCESS SDKS" links to
  `https://gopro.com/account?target=enterprise-application`; the Cloud API's "Request Access"
  links to `https://gopro.com/en/us/connect` — *corrected 2026-09-21*: the 2026-09-20 read
  recorded both buttons as the enterprise-application URL; the page's HTML (curl, browser UA,
  2026-09-21) puts "Request Access" under the `/connect` href in both of its copies. `/connect`,
  read by the owner in a browser on 2026-09-20, is a sales and partnership intake (tabs Bulk
  Purchasing / Business Partnerships / Reseller Opportunities / Public Relations; Company
  required) — see `frame.md`, hypothesis 2.
- **The SDK application sits behind a GoPro sign-in** — opened without a session, that URL lands on
  `https://gopro.com/login?redirect_uri=https%3A%2F%2Fgopro.com%2Faccount%3Ftarget%3Denterprise-application`,
  "Sign in to continue to GoPro." (read 2026-09-20 in Chrome). What the form asks and who is
  eligible was not read.
- **Open GoPro is camera-only** — it documents "Bluetooth Low Energy (BLE)", "WiFi" and "USB",
  and its only cloud sentence is "The GoPro cloud interface has been tailored to the needs of
  individual consumers. If you are interested in commercial usage, reach out to our business
  development team." (https://gopro.github.io/OpenGoPro/docs/, read 2026-09-20). No account
  sign-in, no OAuth, no `api.gopro.com`.
- **The Media SDK on GitHub is not the cloud API** — "With the Media SDK, you can process GoPro
  `.360` spherical video files from within your own Android Kotlin application."
  (https://github.com/gopro/media-kotlin-sdk, README; repository created 2026-06-15, last push
  2026-08-19; read 2026-09-20). Recorded so the two are not conflated.
- **The Terms of Use bear on any non-GoPro client** — under "9. General Prohibitions and
  Acceptable Use Standards", "You agree not to do any of the following: … Attempt to access or
  search the Service or Content or download Content from the Service through the use of any
  engine, software, tool, agent, device or mechanism (including spiders, robots, crawlers, data
  mining tools or the like) other than the software and/or search agents provided by GoPro or
  other generally available third party web browsers"; also "Access, tamper with, or use
  non-public areas of the Service" and "Use, display, mirror or frame the Service".
  Section 1: "You agree not to disclose your password to any third party." Section 5.1 grants
  use "solely for your personal and non-commercial purposes."
  (https://gopro.com/en/us/legal/terms, "Last Updated Date: April 11, 2024"; read 2026-09-20 in
  Chrome — the page answers 403 to curl and to non-browser fetchers.)
- **No page read today documents an OAuth client registration, scopes, or a token endpoint for
  third parties.** The documentation does not say; what exists is the gated beta above.

**Empirical half.**

```
curl -sS -X POST https://api.gopro.com/v1/oauth2/token -H "Accept: application/json" -d "grant_type=password"
curl -sS -X POST https://api.gopro.com/v1/oauth2/token -H "Accept: application/json" -d "grant_type=authorization_code"
curl -sS -X POST https://api.gopro.com/v1/oauth2/token -H "Accept: application/json" -d "grant_type=urn:ietf:params:oauth:grant-type:device_code"
curl -sS "https://api.gopro.com/v1/oauth2/authorize?response_type=code&client_id=x&redirect_uri=http://localhost/cb"
curl -sS "https://api.gopro.com/media/search?per_page=1" -H "Accept: application/json"
```

- `POST /v1/oauth2/token` answers **401**, 173 bytes, for all three grants alike:
  `{"error":"invalid_client","error_description":"Client authentication failed due to unknown
  client, no client authentication included, or unsupported authentication method."}` — the
  token endpoint is live today and refuses without a client credential; which grants it allows
  is not observable without one.
- `GET /v1/oauth2/authorize` answers **403**, `text/html`, 919 bytes, a CloudFront "Request
  blocked." page — no reachable authorization endpoint at that path.
- `GET /media/search` without a token answers **406**, 0 bytes (the app sends
  `Accept: application/vnd.gopro.jk.media+json; version=2.0.0`, `castlib/sources/gopro.py:27`;
  without a token the API does not negotiate at all).
- **The SDK application: pending a GoPro account sign-in.** The form is behind
  `gopro.com/login`; signing in is the owner's action, not the agent's. (The Cloud API's own
  route, `/connect`, is a business intake that asks for a company — corrected 2026-09-21, above.)

**Not yet checked:** what the enterprise-application form asks and whether an individual
developer is eligible; whether the Cloud API beta issues an OAuth client or another kind of
credential, on what terms and at what price (no public documentation found; whatever exists is
behind the application); whether "business development" answers an individual; the 2021
announcement page (https://gopro.com/en/us/news/open-gopro-announce, 403 to non-browsers).

**What this settles:** the prior sentence stands in its narrow reading and falls in its broad
one — there is still no self-serve, documented sign-in for third-party applications, but GoPro
now advertises a gated "Cloud API (BETA)" for exactly the upload/download/playback the app
needs, behind a business intake form (`/connect`, corrected 2026-09-21; the 2026-09-20 text
said "an application form the owner can open"); and the Terms of Use, read today, permit
access only through GoPro's own software or a general web browser. That is the fact set a frame
has to weigh before anything is planned.

## Spike: which sign-in does GoPro's own web app use, and does it take a client a third party could register? (2026-09-20, 21:31)

Against `https://gopro.com/login` as served today, its script bundles, and the one third-party
client with public source; the form was never submitted.

**What the previous source said.** `castlib/sources/gopro.py:39-47` (`HOW_TO_GET_A_TOKEN`) —
"open https://gopro.com/media-library/ and sign in … copy the value of gp_access_token (it starts
with eyJ)"; `context/archive/2026-09-07-cloud-source-ui/plan.md:45` — "The stored GoPro token is a
five-segment JWE; its expiry is not readable client-side." No prior claim about the sign-in
endpoint itself.

**Documentary half.**

- **GoPro's pages do not document the account sign-in at all** — neither the developer-tools
  page nor Open GoPro (URLs and read dates above) names a login endpoint, a grant, a client id or
  a scope. The documentation does not say.
- **A third-party client with public source uses the password grant with GoPro's own web client
  credentials** — `authURL = "https://api.gopro.com/v1/oauth2/token"`, form fields `grant_type`
  = `password`, `client_id` = `apiClientID`, `client_secret` = `apiClientSecret`, `scope` =
  `"root root:channels public me upload media_library_beta live"`, `username`, `password`; a
  second call refreshes with `grant_type` = `refresh_token`
  (https://hackage.haskell.org/package/gopro-plus-0.6.6.7/docs/src/GoPro.Plus.Auth.html,
  package uploaded 2025-03-09, source copyright 2020; read 2026-09-20). The two credential
  constants are GoPro's, embedded in that source; their values are deliberately not recorded
  here. Nothing on GoPro's pages grants a third party their use.

**Empirical half.**

```
curl -sS -L https://gopro.com/login                                  # 200, 7035 bytes, 12 <script> tags
curl -sS -L https://static.gopro.com/web-apps/assets/login/9516cf96b65f299a1b0ba77a658cb6aa4c463e8b/_next/static/chunks/{pages/_app-12ee074cbedc86b5,952-25d420ee0857c0e6,pages/index-eea1e47943dbca79}.js
grep -o 'url:"[^"]*"' …index….js ; grep -o 'production:{apiBase:[^}]*' …_app….js
```

- **The login page is GoPro's own Next.js app**, build `9516cf96b65f299a1b0ba77a658cb6aa4c463e8b`,
  served from `static.gopro.com`; a fresh Chrome load made 3 requests to gopro hosts (`HEAD
  /login` 200, one CSS 200, one analytics beacon 503) and none to `api.gopro.com`.
- **Its production config**: `apiBase:"https://api.gopro.com"`, `auth:"https://gopro.com/login/auth"`,
  `login:"https://gopro.com/login"`, `externalProviders:"https://gopro.com/login/external-providers"`,
  `mediaLibrary:"https://gopro.com/media-library"`, `logout:"https://gopro.com/logout"`.
- **The password form talks to a same-origin backend, not to `/v1/oauth2/token`**: an axios
  instance with `baseURL:"/login/api"` and three calls — `url:"/login"` (POST), `url:"/code"`
  (GET), `url:"/social-login?provider="` (GET) with providers `google_oauth2`, `apple_oauth2`,
  `facebook`. A second instance uses `baseURL: apiBase, withCredentials: true`, and only in the
  DEV environment sets `Authorization: "Bearer " + cookie("gp_access_token")` — the cookie name
  the app's paste instructions already point at (`castlib/sources/gopro.py:42`).
- **The page reads an authorization-code-shaped set of query parameters**: `origin`,
  `redirect_uri`, `code_challenge`, `client_id`, `redirect`, `provider`, `brand`, with brands
  `plus`, `ecomm`, `awards`, `quik`, `asus`, `asus-storycube` — a hand-off for GoPro's own
  properties. The bundles contain no `code_verifier`, `response_type` or
  `code_challenge_method` string, so the exchange completes elsewhere (the `/code` call is the
  only candidate seen).
- **The endpoint the third-party client uses is alive**: the `401 invalid_client` in the first
  spike is the same `/v1/oauth2/token`.

**Not yet checked:** whether `POST /login/api/login` returns the token in its body or only as
the `gp_access_token` cookie (needs a real sign-in, not performed); whether the `code_challenge`
hand-off completes with a `code` for any client id other than GoPro's (needs one of theirs);
what the Quik mobile app sends (not observed); whether `/login/api` is rate-limited or bot-gated
the way `gopro.com/account` is (403 to curl).

**What this settles:** the official web sign-in is a same-origin backend (`gopro.com/login/api/login`)
that ends in the `gp_access_token` cookie, plus an authorization-code-with-PKCE-shaped hand-off
that takes a `client_id` — but the only client ids in evidence are GoPro's own, and the only
third-party route with public source borrows GoPro's embedded web credentials for a password
grant, which no GoPro page permits. Whatever replaces the paste either reuses a real browser
session (the cookie) or goes through the gated Cloud API application; there is no third road on
today's evidence.

## Spike: an app-owned Chrome window, read over CDP from the standard library (2026-09-21, 20:03)

Against the Chrome installed on the Fedora workstation, headless, with a throwaway profile in the
session scratchpad. No GoPro page was opened and no credential was used: the cookie read here was
one the spike set itself. Run for `/10x-plan` to prove the plumbing of the mechanism before
recommending it; the real gopro.com sign-in in such a window is Phase 5 of the plan.

**What the previous source said.** `frame.md:62-65` - only devtools, an extension with the cookies
permission, or a browser the app owns can read the HttpOnly cookie. Nothing in the folder said how
an app-owned browser would hand the cookie over.

**Documentary half** (all read 2026-09-21).

- **The DevTools port file** - once the port is bound Chrome writes `"<port>\n/devtools/browser/<uuid>"`
  to `DevToolsActivePort` in the user data dir "so Telemetry, ChromeDriver, etc. can pick it up"
  (https://chromium.googlesource.com/chromium/src/+/main/content/browser/devtools/devtools_http_handler.cc;
  the reader side in `chrome/browser/devtools/remote_debugging_server.cc`). Puppeteer defaults to
  `--remote-debugging-port=0` (commit `26145e9`).
- **The port needs a non-default profile** - since Chrome 136 `--remote-debugging-port` and
  `--remote-debugging-pipe` are ignored on the default data directory and "must now be accompanied
  by the `--user-data-dir` switch to point to a non-standard directory"
  (https://developer.chrome.com/blog/remote-debugging-port, 2025-03-17). The same post names cookie
  extraction over remote debugging as the abuse the change targets - which is what this design does
  with the person's own consent, in a profile the app owns.
- **The `Origin` check** - the WebSocket endpoint answers 403 only when the request *carries* an
  `Origin` header outside `--remote-allow-origins` (`devtools_http_handler.cc`, `OnWebSocketRequest`);
  a client with no `Origin` connects (Selenium issue #11750, 2023-03-08, Chrome 111).
- **What a cookie looks like** - `Network.Cookie` has `name`, `value`, `domain`, `path`, `expires`
  ("seconds since the UNIX epoch … -1 if the expiry date is not set"), `size`, `httpOnly`, `secure`,
  `session`, `sameSite`, … ; `Storage.getCookies` "Returns all browser cookies" at the browser
  endpoint (https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json).
- **One process per data directory** - `ProcessSingleton` "is named according to the user data
  directory", so a fresh directory always starts a new browser even while the person's own Chrome
  runs (https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/process_singleton.h;
  https://chromium.googlesource.com/chromium/src/+/main/docs/user_data_dir.md).
- **Edge** takes the same switches and "matches the APIs of the Chrome DevTools Protocol"
  (https://learn.microsoft.com/en-us/microsoft-edge/devtools-protocol-chromium, updated 2025-11-26);
  the enterprise policy `RemoteDebuggingAllowed` can block it
  (https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/remotedebuggingallowed).
  `--app=<url>` is Chromium's application-mode switch (https://peter.sh/experiments/chromium-command-line-switches/).
- **Firefox** disabled CDP by default in 129 (2024-05-28 announcement) and removed it in 141
  (2025-07-22; https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/141,
  https://fxdx.dev/cdp-retirement-in-firefox/). Firefox is not a candidate.
- **Where Windows keeps them** - Chrome's installer registers
  `Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe` (https://www.chromium.org/developers/installer/);
  Playwright probes `%LOCALAPPDATA%`, `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%` +
  `Google\Chrome\Application\chrome.exe` / `Microsoft\Edge\Application\msedge.exe` without the registry
  (https://github.com/microsoft/playwright/blob/main/packages/playwright-core/src/server/registry/index.ts).
  No Microsoft document states Edge's install path or an `App Paths\msedge.exe` key; the plan probes
  both and treats either as a hint, not a guarantee.

**Empirical half.**

```
google-chrome --version                       # Google Chrome 153.0.8010.47
google-chrome --headless=new --user-data-dir=<scratch>/cdp-profile --remote-debugging-port=0 \
              --no-first-run --no-default-browser-check about:blank
cat <scratch>/cdp-profile/DevToolsActivePort  # 44041 / /devtools/browser/d6257305-…
curl -s http://127.0.0.1:44041/json/version   # {"Browser":"Chrome/153.0.8010.47", …, "webSocketDebuggerUrl":"ws://127.0.0.1:44041/devtools/browser/…"}
python3 cdp_spike.py                          # a socket-only WebSocket client; the script is in the session scratchpad, not in the repository
```

- The port file appeared **0.3 s** after launch on the second run (first run: within the 10 s wait).
- The handshake without an `Origin` header answered 101; `Target.getTargets` listed `page`,
  `browser_ui`, `browser_ui`, `background_page`.
- `Storage.setCookies` planted two cookies for `gopro.com`, one with `httpOnly: true` and an expiry
  an hour ahead, one plain; `Storage.getCookies` returned both, the first as
  `{'name': 'gp_access_token', 'httpOnly': True, 'secure': True, 'expires': 1790017486.3, 'session': False}`,
  the second with `'expires': -1, 'session': True`.
- `Browser.close` ended the process; `wait()` returned **0**.
- The browsers on this machine: `google-chrome`, `google-chrome-stable` and `firefox` on `PATH`; no
  Chromium, Brave, Edge or Flatpak browser.

**Not yet checked:** a real gopro.com sign-in inside an `--app` window of a fresh profile (bot
gating, social-login popups, 2FA); whether `gp_access_token` as GoPro sets it is a session cookie or
persistent (the `session` / `expires` fields will say, Phase 5); whether the `Preferences` pre-seed
switches the password manager off in Chrome and in Edge; Edge on the Windows laptop; a keyring
prompt on Linux without `--password-store=basic`.

**What this settles:** the hand-off can be built on the standard library alone against a
Chromium-family browser the host already has - the port file, the WebSocket without `Origin`, the
HttpOnly read and the graceful close all behave as documented on today's Chrome - and Firefox is
out. What it does not settle is GoPro's side of the window; that stays a manual row.

## Phase observations

One entry per ticked manual row (`lessons.md:5-10`): the row, the date, the machine, what was seen.

### Phase 1

- **Row 1.5** (2026-09-22, the Fedora workstation, from the checkout). `--version` printed three
  lines; the third read `GoPro window: /usr/bin/google-chrome` (Google Chrome 153.0.8010.47 at that
  path). The owner confirmed the three lines. The venv carries no `cast-tv` script (the package is
  not installed in it), so the module form `.venv/bin/python -m castlib --version` is the same
  command; the agent's own run of it printed `cast-tv 0.3.0`, `Google Photos client: from
  ~/.config/cast-tv/google-client.json`, `GoPro window: /usr/bin/google-chrome`. With
  `CAST_TV_BROWSER=/nonexistent` the third line read
  `GoPro window: CAST_TV_BROWSER=/nonexistent (not found)`. Nothing was launched.
- **Rows 1.1, 1.3, 1.4** (2026-09-22, commit `bec95a4`, PR #40). The test workflow (run 35772205093)
  passed on `ubuntu-latest` and `windows-latest`. The release build (run 35772205088) was green on
  `ubuntu-22.04` and `windows-latest`; its smoke step printed `GoPro window: /usr/bin/google-chrome`
  on Ubuntu and `GoPro window: C:\Program Files\Google\Chrome\Application\chrome.exe` on Windows
  (discovery only; nothing launched). Artifacts: `cast-tv-windows-x64.exe` (22 584 564 bytes) and
  `cast-tv-linux-x64` (35 341 932 bytes); the `.exe` was downloaded from the run to check the row.

### Phase 2

- **Rows 2.1 (local half), 2.2, 2.3** (2026-09-22, the Fedora workstation, from the checkout).
  `.venv/bin/python -m pytest tests/test_gopro.py tests/test_api.py`: 53 passed (20 new tests of
  the round, the sidecar and the report seam in `test_gopro.py`, 2 in `test_api.py`), stable over
  three consecutive runs. `.venv/bin/python -m pytest`: 328 passed, 1 skipped, 29.7 s.
  `.venv/bin/python -m pyflakes castlib tests`: no output. No browser process was started by the
  suite (`pgrep -af gopro-browser` empty afterwards). Row 2.1's CI half is checked on the phase
  commit's workflow run. Noted while running the old suite against the new source: the first run
  of `test_status_before_and_after_connect` (its `connect({})` with nothing stored now starts a
  round) launched a real Chrome from a pytest tmp profile before the fake `Handoff` was wired in;
  the profile and the process were removed by hand, and `tests/conftest.py` now refuses
  `browser.launch` for the whole suite so that cannot recur.
- **Row 2.4** (2026-09-23, the Fedora workstation, `.venv/bin/python -m castlib --no-browser` from the
  checkout, the old UI in place; the browser the engine picked is the first candidate of row 1.5,
  `/usr/bin/google-chrome`, Google Chrome 153.0.8010.47 as read on 2026-09-22). The owner ran
  `curl -s -H 'Host: localhost:8895' -X POST http://localhost:8895/api/sources/gopro/connect -d '{"fresh": true}'`;
  the answer was `{"state": "connecting", "detail": {"stored": true, "step": "browser", "expires_in": 299,
  "note": "The gopro.com window opens on the computer running cast-tv, not on the device showing this
  page."}, "step": "browser"}` and a gopro.com window opened on this machine. No sign-in was performed;
  the owner closed the window with its own close control. `curl -s http://localhost:8895/api/sources/gopro`
  then answered `state: disconnected`, `detail.stored: true`, `captured_by: "unknown"` (the token file
  is the one pasted 9 days earlier, before this change, so it has no sidecar), `age: "token stored 9
  days ago"`, `captured_at`/`cookie`/`last_success_at`/`first_401_at` null, and `flow_error` `{"code":
  "browser_closed", "message": "The gopro.com window was closed before a session appeared."}`; no
  `fallback` key. Two things learned on the way: the first attempt hit a cast-tv started 26 hours
  earlier (`.venv/bin/cast-tv`, pid 697736, holding port 8895), which answered the old 401 text with
  "lasts a few hours" because a running process keeps the code it started with; it was idle (cast
  `stopped`, no show) and was ended with SIGTERM before the row was rerun. And the migration case of
  the plan ("a token file from before this change keeps working ... `captured_by` reads `unknown`") was
  observed for real, not only in `test_a_replaced_token_file_drops_the_metadata`.
- **Row 2.1, the CI half** (2026-09-23, commit `ed8f964`, PR #40). The test workflow (run 35906449051)
  passed on `ubuntu-latest` and `windows-latest` (the whole suite, `test_gopro.py` and `test_api.py`
  included). The release build (run 35906449032) was green on `ubuntu-22.04` and `windows-latest`; its
  smoke step printed `GoPro window: /usr/bin/google-chrome` and `GoPro window: C:\Program
  Files\Google\Chrome\Application\chrome.exe`, so the `.exe` of this commit exists for Phase 5.

### Phase 3

- **Rows 3.1, 3.2 (local half), 3.3** (2026-09-23, the Fedora workstation, from the checkout).
  `.venv/bin/python -m pytest tests/test_ui.py`: 9 passed (3 new: the window block first with the
  paste form only inside a fallback block, the decided texts with no "GoPro sign-in" and no "lasts a
  few hours", the devtools steps absent from `app.js`). `.venv/bin/python -m pytest`: 336 passed,
  1 skipped, 28.5 s. `.venv/bin/python -m pyflakes castlib tests`: no output. `node --check
  castlib/ui/app.js`: no output. Row 3.2's CI half is checked on the phase commit's workflow run.
- **A rendering pre-check before the manual rows** (2026-09-23, the agent, same machine; not a
  substitute for rows 3.4 and 3.5, which the owner runs against the real gopro.com window). A
  throwaway cast-tv (`XDG_CONFIG_HOME` and `XDG_CACHE_HOME` in the session scratchpad, so the
  owner's token and profile were untouched; `CAST_TV_BROWSER=/nonexistent`; `--no-browser -p 8896`)
  was driven in the owner's Chrome through the extension. The idle gate showed the heading, the
  decided body, one button "Open gopro.com", the note and no token field. Pressing the button
  showed, within a second, the fallback block: "cast-tv could not open a gopro.com window here: No
  gopro.com window could be opened. /nonexistent: [Errno 2] No such file or directory:
  '/nonexistent'. A token pasted from a signed-in browser works instead:", the three numbered steps
  from `TOKEN_STEPS`, the field and "Save token"; no separate `flowError` line (the fallback carries
  the reason). A paste of `eyJnot-a-real-token` showed "GoPro rejected the token (401) - expired or
  incomplete." under the note (`gateNote`); the block stayed. No JavaScript console error; the
  Diagnostics count stayed 0 (a failed launch is status-only, as designed). Two things learned: the
  extension's own navigation carries `Sec-Fetch-Site: cross-site`, which `server.py`'s
  `_check_origin` refuses by design (curl without that header got 200), so the page was reached with
  a same-origin `location.href = '/ui/'` from the refused page; and the `browser_failed` reason
  repeats the fallback line's idea ("could not open ... : No gopro.com window could be opened. ..."),
  which is truthful but reads twice - left as is, a wording trim is a Phase 4 question.
- **Row 3.4** (2026-09-23, the Fedora workstation, `.venv/bin/python -m castlib` from the checkout,
  the cast-tv tab in Chrome; the window's browser is the first candidate of row 1.5,
  `/usr/bin/google-chrome`, Google Chrome 153.0.8010.47 as read on 2026-09-22). The token pasted 9
  days earlier was first forgotten with `curl -s -H 'Host: localhost:8895' -X POST
  http://localhost:8895/api/sources/gopro/disconnect` (which also removed the sidecar and the
  `gopro-browser` profile of row 2.4), so the tab showed the plain gate: "Connect GoPro", the body,
  one button "Open gopro.com", the note, no token field and no numbered steps. Pressing the button:
  "Opening…" for a moment, then the waiting block ("A gopro.com window is open on the computer
  running cast-tv. Sign in in that window; this page continues by itself.", "waiting for the
  sign-in… valid 5 min", the on-host note, "Cancel"), the tab hint "gopro.com window open…", and a
  gopro.com window opened on this machine; no sign-in was performed. "Cancel" on the page closed
  the window; the gate returned to the button alone, no note, no field. The owner confirmed every
  screen as described ("3.4 i 3.5 wszystko jak w opisie").
- **Row 3.5** (2026-09-23, same machine, `CAST_TV_BROWSER=/nonexistent .venv/bin/python -m castlib`
  after Ctrl+C on the previous run, which printed `Stopped.`). Pressing "Open gopro.com" showed
  within a second, under the button, the fallback block: "cast-tv could not open a gopro.com window
  here: No gopro.com window could be opened. /nonexistent: [Errno 2] No such file or directory:
  '/nonexistent'. A token pasted from a signed-in browser works instead:", the three numbered
  steps, the token field and "Save token". A junk value (`eyJtest`) and "Save token" put "GoPro
  rejected the token (401) - expired or incomplete." under the note; the block stayed. Confirmed by
  the owner as above. The paste of a real token is row 5.6, not run here.
- **Row 3.2, the CI half** (2026-09-23, commit `2ab06e3`, PR #40). The test workflow (run 35916371410)
  passed on `ubuntu-latest` and `windows-latest` (the whole suite, `test_ui.py` included). The release
  build (run 35916371620) was green on `ubuntu-22.04` and `windows-latest`; its smoke step printed
  `GoPro window: /usr/bin/google-chrome` and `GoPro window: C:\Program
  Files\Google\Chrome\Application\chrome.exe`; artifacts `cast-tv-windows-x64.exe` (22 569 701 bytes)
  and `cast-tv-linux-x64` (35 352 062 bytes).

### Phase 4

- **Rows 4.1, 4.2, 4.3** (2026-09-24, the Fedora workstation, from the checkout).
  `.venv/bin/python -m pytest tests/test_cli.py`: 15 passed (1 new,
  `test_gopro_without_a_token_points_at_the_ui`: `cast-gopro` with an empty config dir and no
  `GOPRO_TOKEN` prints "No GoPro token stored." then a line starting "Run cast-tv, open the GoPro
  tab and press Open gopro.com." before the F12 step and the dated standing note; `--help` for
  `--token` reads "the UI's Open gopro.com is the usual route"). The two greps of the plan -
  "lasts a few hours" / "last hours" over `README.md`, `castlib/ui/app.js`, `castlib/sources/gopro.py`,
  and "GoPro sign-in" over `README.md`, the UI files, `gopro.py`, `prd.md` - found nothing (both
  exited 1); the same "GoPro sign-in" grep over `roadmap.md` also found nothing after the S-13
  section was rewritten (its old "Ideas" line carried the phrase). `.venv/bin/python -m pyflakes
  castlib tests`: no output. `.venv/bin/python -m pytest`: 338 passed, 1 skipped, 28.5 s; no
  `gopro-browser` process afterwards. Nothing was launched by this phase.
- **A read-through before row 4.4** (2026-09-24, the agent; the owner's own read is the row).
  Every claim in the README's GoPro section and the new Limitations paragraph was traced: the
  standing sentence and the three sources with their read date 2026-09-20 to this file's first
  spike (lines 20-58; see the 4.4 outcome below for what the sentence may say); the Terms' "Last Updated Date: April 11,
  2024" and the §9 wording to lines 46-56; Firefox 141 (2025-07-22) to lines 207-209; the
  browser list and Chrome-first order to `castlib/auth/browser.py:48-51,81`; the profile mode,
  the seeded password-manager preference, the cache location and the `--app=` media-library
  window to `browser.py:41,54,120-154`; the five-minute deadline to `browser.py:44`; the on-host
  note to `castlib/sources/gopro.py:54`; "session captured" in the header to `gopro.py:793-796`;
  `gopro-session.json` and its fields to `gopro.py:50-52`; the first-refusal card to the source's
  `report` seam (Phase 2); `CAST_TV_BROWSER` as the only candidate to `browser.py:90-95` and
  `--version` to `castlib/cli.py:286-299`; `GOPRO_TOKEN` to `gopro.py:84-88`; the fallback rule
  to `castlib/ui/index.html:224-229,304-309`; the disconnect route removing token, sidecar and
  profile to `gopro.py:873-876`; the Windows paths to `castlib/config.py:7-8`. Two sentences are
  inferences, not sourced facts, and are worded as such: that GoPro "can end that on its side
  at any time", and that the observed lifetime "once one is observed, is recorded with its
  date" (a commitment about this file's Measurements table, below). Not claimed anywhere: that
  the password-manager preference takes effect in Chrome or Edge (row 5.9 measures it), or any
  session lifetime.
- **Row 4.4, first read: not confirmed** (2026-09-24, the owner). The sentence "GoPro offers no
  sign-in that another application may use" (README Limitations) and its GoPro-section form
  "GoPro publishes no sign-in for other applications" overreach the sources: this file's line 84
  records only that no documented, self-serve sign-in was found, and the closed beta's terms
  remain unknown. The owner's wording, adopted verbatim: "No publicly documented, self-serve
  sign-in for third-party applications was found (checked 2026-09-20)." Applied the same day
  to both README places and, for one claim with one wording, to the three other copies:
  `STANDING_NOTE` in `castlib/sources/gopro.py:54` (printed by `cast-gopro`; the plan's Phase 2
  contract at `plan.md:411-412` prescribed the older sentence, so this is a deliberate deviation
  from the plan's text on the owner's finding), the S-13 "Found" bullet in
  `context/foundation/roadmap.md`, and the PRD Non-Goal, whose "none is offered to individuals"
  was replaced for the same reason (whether an individual is eligible for the beta is "Not yet
  checked", line 84-85). The row stays open until the owner reads the two README passages again.
- **The fallback line, trimmed** (2026-09-24, the owner's call on the Phase 3 review note):
  `fallbackText` in `castlib/ui/app.js` no longer prefixes "cast-tv could not open a gopro.com
  window here: "; it shows the server's own sentence (`fallback.reason`, e.g. "No Chrome,
  Chromium, Edge or Brave was found on this computer." or "No gopro.com window could be opened.
  /nonexistent: ...") followed by "A token pasted from a signed-in browser works instead:". The
  Phase 3 observations above quote the older, doubled line as it was seen then.
- **Rows 4.1-4.3 re-run after the two changes** (2026-09-24, same machine): `tests/test_ui.py`,
  `tests/test_gopro.py`, `tests/test_cli.py`: 68 passed; the full suite 338 passed, 1 skipped,
  30.3 s; `node --check castlib/ui/app.js` and pyflakes clean; the two greps of the plan and a
  third one for the old sentence ("publishes no sign-in", "offers no sign-in", "none is offered
  to individuals") over README, `castlib/` and `context/foundation/` all found nothing.
- **Row 4.4, second read: confirmed** (2026-09-24, the owner, README from the checkout against
  this file). One more correction before the confirmation: in the Limitations paragraph "what
  that beta offers, to whom and on what terms is not published" overstated what is unknown -
  the developer page does advertise upload, download and playback (lines 20-22); what is not
  established is the access the beta grants, to whom, and on what terms. The owner's wording,
  adopted verbatim: "what access the beta grants, to whom and on what terms is not published."
  The owner also kept the corrected standing sentence in `STANDING_NOTE`, the roadmap and the
  PRD as within the intended scope ("usuwają to samo zbyt kategoryczne twierdzenie"). With that
  change the owner confirmed the row: every claim in the GoPro section and the Limitations
  paragraph carries its date or traces to this file.
- **The Phase 4 commit, the CI half** (2026-09-24, commit `d669315`, PR #40). The test workflow
  (run 36046967872) passed on `ubuntu-latest` (338 passed, 1 skipped, 30.9 s) and `windows-latest`
  (335 passed, 4 skipped, 87.7 s). The release build (run 36046967835) was green on `ubuntu-22.04`
  and `windows-latest`; its smoke step printed `GoPro window: /usr/bin/google-chrome` and
  `GoPro window: C:\Program Files\Google\Chrome\Application\chrome.exe`; artifacts
  `cast-tv-windows-x64.exe` (22 595 547 bytes) and `cast-tv-linux-x64` (35 351 998 bytes), so the
  `.exe` of this commit exists for Phase 5 if no review fix lands after it.

### Phase 5

- **Rows 5.1, 5.2** (2026-09-24, commit `d14deaa`, PR #40). The commit under test is the branch
  head after the Phase 4 close-out; it touches `context/` only, so its binary is built from the
  code of `d669315` and nothing later (the Phase 5 commit itself is context-only too, so this
  run stays the one that counts). The test workflow (run 36049997692) passed on `ubuntu-latest`
  (338 passed, 1 skipped, 31.3 s) and `windows-latest` (335 passed, 4 skipped, 83.8 s). The
  release build (run 36049997670) was green on `ubuntu-22.04` and `windows-latest`; its
  `release` job was skipped as designed (no tag); its smoke step printed `GoPro window:
  /usr/bin/google-chrome` and `GoPro window: C:\Program Files\Google\Chrome\Application\chrome.exe`.
  The run's artifacts: `cast-tv-windows-x64.exe` (artifact id 10830037066, 22 572 716 bytes as
  GitHub lists it, i.e. zipped; expires 2026-12-23) and `cast-tv-linux-x64` (id 10830006951,
  35 352 149 bytes). The Windows artifact was downloaded on the Fedora workstation with `gh run
  download 36049997670 -n cast-tv-windows-x64.exe`: the unpacked `cast-tv-windows-x64.exe` is
  22 840 651 bytes, SHA-256
  `0d22f1d7caff48e8413817098bfbf6d0ce21a72046100c651240aaef27809317`. Row 5.10's copy on the
  laptop is checked against that hash (`Get-FileHash .\cast-tv-windows-x64.exe` in PowerShell)
  so "the artifact of the commit under test" is a comparison, not a belief. Rows 5.1 and 5.2 are
  ticked on this.
- **Pre-checks before the manual rows** (2026-09-24, the agent, the Fedora workstation; nothing
  launched, nothing signed in). `ss -ltnp 'sport = :8895'` listed nothing, so no older cast-tv
  holds the port (row 2.4's first attempt hit one); `pgrep -af gopro-browser` found no browser
  process. `google-chrome --version`: Google Chrome 153.0.8010.47, unchanged since row 1.5;
  `.venv/bin/python -m castlib --version` printed the three lines with `GoPro window:
  /usr/bin/google-chrome`. `~/.config/cast-tv/` holds no `gopro-token` and no
  `gopro-session.json` (row 3.5's junk paste was refused and never saved), so the GoPro tab
  shows the gate on start. It does hold the `gopro-browser` profile that row 3.4's window
  created on 2026-09-23; no sign-in was performed in it, so GoPro asks to sign in either way,
  and the disconnect route before row 5.3 removes it and gives the Definitions' "empty on first
  use" case. The LAN address for row 5.8 is `http://192.168.50.198:8895/ui/` (`hostname -I`;
  cast-tv prints it at start).
- **Found on the way: a directory `remove_profile()` does not remove** (2026-09-24, the agent).
  Next to the expected `~/.cache/cast-tv/gopro-browser-cache/` (the `--disk-cache-dir`) there is
  `~/.cache/cast-tv/gopro-browser/Default/`, empty, dated 2026-09-23 20:57. It is Chrome's own
  doing: on Linux, when the user data dir sits under `$XDG_CONFIG_HOME`, Chrome keeps its cache
  in the same subpath under `$XDG_CACHE_HOME` ("this maps ~/.config/google-chrome to
  ~/.cache/google-chrome", `GetUserCacheDirectory` in
  https://chromium.googlesource.com/chromium/src/+/main/chrome/common/chrome_paths_linux.cc,
  read 2026-09-24), and `--disk-cache-dir` moves only the HTTP cache out of it.
  `castlib/auth/browser.py:141-144` removes the profile and `gopro-browser-cache` only, so this
  directory survives `disconnect()`. Harmless (an empty tree), Linux-only, and not a row of this
  phase, so no code change here; recorded for the owner's call (a third `rmtree` in
  `remove_profile()` and a README "Where files live" mention would close it).
- **How the Fedora rows were run** (2026-09-24, the agent, on the owner's request "zrob to za
  mnie"; the sign-in itself stayed the owner's). cast-tv from the checkout at `d14deaa`,
  `.venv/bin/python -m castlib --no-browser`, started under `setsid` so it owns its process
  group and a terminal's Ctrl+C can be reproduced as SIGINT to that group (`--no-browser` only
  skips opening the UI tab; the hand-off window is unaffected, README "GoPro"). The UI was
  driven in the owner's Chrome through the extension, in a tab of its own reached with the
  same-origin `location.href = '/ui/'` step of the Phase 3 pre-check. That tab was occluded the
  whole time (`document.visibilityState === 'hidden'`), and the UI pauses its poll in a hidden
  tab by design (`castlib/ui/app.js:107`, resumed by the `visibilitychange` handler), so after
  each server-side transition the view was refreshed with the same `refresh()` that handler
  calls; the transitions that follow a user action (the button, Cancel) arrived through the
  action's own response, as in any tab. The app window is Google Chrome 153.0.8010.47
  (`/usr/bin/google-chrome`, `/opt/google/chrome/chrome` in `ps`) on the app's own profile; the
  owner's Chrome profile was never touched. Every reading below is from `GET
  /api/sources/gopro`, `GET /api/errors`, `pgrep`, `ls` and the page text; no token value was
  read or printed.
- **Row 5.4** (2026-09-24 22:09 local, the Fedora workstation). Start state: no token, no
  sidecar; the row-3.4 profile removed first with `POST /api/sources/gopro/disconnect` (answer
  `{"state": "disconnected", "detail": {"stored": false}}`; `gopro-browser` and
  `gopro-browser-cache` gone). The gate: "Connect GoPro", the body, one button "Open
  gopro.com", the note, no field; Diagnostics 0. The button: the tab hint "gopro.com window
  open…", the waiting block ("A gopro.com window is open on the computer running cast-tv. Sign
  in in that window; this page continues by itself.", "waiting for the sign-in… valid 5 min",
  the on-host note, "Cancel"); a process `/opt/google/chrome/chrome
  --user-data-dir=…/gopro-browser --disk-cache-dir=…/gopro-browser-cache
  --remote-debugging-port=0 --no-first-run --no-default-browser-check --password-store=basic …`
  and `DevToolsActivePort` in the profile; the API `connecting`, `step: browser`, `expires_in:
  294`. "Cancel" on the page: the Chrome process gone, the API `{"state": "disconnected",
  "detail": {"stored": false}}` (no `flow_error`, no `fallback`), the gate back to the button
  alone, no note, no field; Diagnostics still 0.
- **Row 5.5** (2026-09-24 22:16 local, same machine; run twice, the second time with the view
  read). The window opened on
  `https://gopro.com/login?redirect_uri=https%3A%2F%2Fgopro.com%2Fmedia-library…` (GoPro sends
  the `--app=` media-library URL to its own login page; no bot wall). No sign-in performed. The
  window was closed *not with its X* (a Wayland session with no xdotool) but by closing its only
  page target over CDP from a second client on the browser endpoint (`Target.closeTarget`;
  `close_window.py` in the session scratchpad, on `castlib.auth.cdp`): the last window closing
  is what the X does, and Chrome then exits on its own - the process was gone within 1 s. The
  API: `disconnected`, `flow_error: {"code": "browser_closed", "message": "The gopro.com window
  was closed before a session appeared."}`, no `fallback`; Diagnostics 0. The view after
  `refresh()`: the button, under it the warn-coloured line "The gopro.com window was closed
  before a session appeared.", the note; no field. The X button itself is pressed by the owner
  on Windows (row 5.10).
- **Row 5.7** (2026-09-24 22:17 local, same machine). With a round running - the Chrome main
  process sits in cast-tv's own process group (`pgid` equal to cast-tv's pid), so a terminal's
  Ctrl+C reaches both, as it would at a real terminal - SIGINT was sent to that group (`kill
  -INT -- -<pgid>`). cast-tv exited within 1 s, its output ending with `Stopped.`; the Chrome
  process was gone in the same second; `pgrep -f gopro-browser`, run from a script file so no
  shell command line carried the pattern, printed no browser process (its one hit was the
  agent's own `bash -c`, whose command line contained the pattern; at a terminal, where the
  command line is `pgrep -f gopro-browser` alone, it prints nothing). Also the Definitions'
  SIGTERM case, in a separate round at 22:18: `kill -TERM <cast-tv pid>` to cast-tv alone,
  Chrome not signalled - `Stopped.`, and the window was gone in the same second, so `close()`
  closes it by itself (`castlib/sources/gopro.py:878-887`).
- **Row 5.3, the measured half** (2026-09-24, same machine; cast-tv restarted at 22:18 after the
  SIGTERM round; the profile present from the rounds above, with no session in it). The button
  pressed at 20:18:38 UTC (22:18:38 local): `connecting/browser`, `expires_in: 299`. The owner
  signed in in the window (method, 2FA and the moment of the last click: the owner's report,
  which this row waits for). A once-per-second recorder of `GET /api/sources/gopro` saw
  `connecting` until 20:20:54 and `connected` at 20:20:55 UTC: `captured_by: "window"`,
  `captured_at: 1790281254.958` = 2026-09-24T20:20:54.957Z; `stored_at` and `verified_at`
  20:20:55.072Z (verified against `api.gopro.com` and written 115 ms after the cookie was
  seen); `cookie: {"session": false, "expires": 1790886054.401}` = 2026-10-01T20:20:54.401Z,
  exactly 7.0 days (604 799 s) after capture - **the `gp_access_token` cookie GoPro sets is
  persistent with a seven-day expiry, not a session cookie** (what the token itself is good for
  is the observed period, rows 5.11-5.12). The window closed by itself (no Chrome process with
  the profile afterwards). The tab after `refresh()`: the header "session captured just now"
  (the tab hint the same), the library listed (100 items on the first page, "Load more"),
  Diagnostics 0 (`errors_seq: 0`, `/api/errors` empty). Files at 22:20: `gopro-token` (0600,
  1 273 bytes) and `gopro-session.json` (0600, 213 bytes); the sidecar reads `captured_at
  1790281254.958`, `captured_by "window"`, `cookie {session: false, expires: 1790886054.401}`,
  `last_success_at 1790281256.513` (the first list, 1.6 s after capture), `first_401_at null`,
  `token_mtime 1790281255.073` = the token file's mtime; no part of the token in it. From the
  button to the list: 2 min 17 s, of which the sign-in is the owner's part.
- **Row 5.3, the owner's half, and row 5.9 for Chrome** (2026-09-24, the owner, at the window
  on the Fedora workstation): signed in with the password (not Google or Apple), no 2FA was
  asked, and no "Save password?" bubble appeared in the window after the sign-in ("haslo, nie
  bylo 2fa, nie widzialem dymku"). The seconds from the last sign-in click to the list were not
  timed; the button-to-list span above (2 min 17 s) includes the typing. Row 5.3 is ticked on
  the two halves together; row 5.9 stays open for its Edge half (row 5.10).
- **Row 5.6, the fallback half** (2026-09-24 22:24 local, the agent, same machine). A deviation
  from the row's literal command, on purpose: the fallback instance ran as a *second* cast-tv,
  `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` in the session scratchpad,
  `CAST_TV_BROWSER=/nonexistent .venv/bin/python -m castlib --no-browser -p 8896`, so the first
  window capture of row 5.3 stayed live on port 8895 for the observed-period rows (5.11-5.12)
  instead of being removed by the `disconnect` the row needs first; the fallback path does not
  read the config dir, and the disconnect-then-recapture case in the real config dir is row
  5.8. Its `--version` third line: `GoPro window: CAST_TV_BROWSER=/nonexistent (not found)`.
  In its tab, "Open gopro.com" at 20:24:34.183 UTC: the API had `flow_error.code:
  "browser_failed"` and `fallback` at 20:24:34.186 (3 ms; nothing launched, no Chrome process
  with a `--user-data-dir`), and the page showed under the button, in one block: "No gopro.com
  window could be opened. /nonexistent: [Errno 2] No such file or directory: '/nonexistent'. A
  token pasted from a signed-in browser works instead:", the three numbered steps of
  `TOKEN_STEPS` (media-library and sign in; F12 -> Application -> Storage -> Cookies; copy
  `gp_access_token`, or the Network tab's "authorization" header), the field with the `eyJ…`
  placeholder and "Save token"; the note below; Diagnostics 0. The paste half is the owner's.
- **Row 5.6, the paste half** (2026-09-24 22:33 local, the owner pasted a token from the
  devtools of their own signed-in Chrome into that field and pressed "Save token"; the agent
  read the result). The API on port 8896: `connected`, `stored: true`, `age: "token stored just
  now"`, `captured_by: "paste"`, `captured_at: 1790281991.434` (20:33:11 UTC), `cookie: null`,
  `first_401_at: null`, and neither `fallback` nor `flow_error` any more (a paste clears the
  fallback, as `test_no_browser_sets_the_fallback` has it); the list answered 100 items with a
  next page; Diagnostics 0. The page: the header and the tab hint "token stored just now", the
  library listed, `gateNote` empty. In the throwaway config dir: `gopro-token` (0600, 1 273
  bytes), `gopro-session.json` (0600, 170 bytes: `captured_by "paste"`, `cookie null`,
  `token_mtime` = the file's mtime, no part of the token), and an empty `gopro-browser`
  directory that `prepare_profile()` had created before the failed launch (expected: the
  profile is prepared, then the candidates are tried). Also seen: the sidecar's
  `last_success_at` (20:33:11.567, the verifying `search`) lagged the API's (20:33:18.849, the
  list) by design - the disk write is throttled to once a minute (`META_WRITE_EVERY`). The 8896
  instance was then stopped and its tab closed; the scratchpad dirs are the session's.
- **Seen before row 5.8: an open tab keeps its list after an API disconnect** (2026-09-24 22:34,
  the agent). `POST /api/sources/gopro/disconnect` on the live instance answered
  `disconnected`, removed `gopro-token`, `gopro-session.json`, the profile and its cache. The
  tab that had been listing (the owner had meanwhile switched it to Photos and loaded 200
  items) showed, after `refresh()`, the hint "not connected" over the same list, not the gate:
  the gate renders only while `!listVisible(tab)` (`castlib/ui/index.html:196`), and the list is
  dropped only on a transition *to* `connected` (the Phase 3 review F1 rule, `d820006`). A
  reload showed the gate with the button and no field. Not a row of this phase (the UI has no
  disconnect control; the route is curl-only, "What We're NOT Doing") and the phone loads the
  page fresh; recorded because a future "Forget the session" control would have to clear the
  list as well as the credential.
- **Row 5.8, the measured half** (2026-09-24 22:39-22:40 local; the owner on the phone and at
  the Fedora window, the agent at the API). After the disconnect above (no token, no profile),
  the owner opened `http://192.168.50.198:8895/ui/` on the phone and pressed "Open gopro.com"
  there. The recorder on `GET /api/sources/gopro` (once a second, the agent's hidden tab's poll
  paused, so the phone was the only UI client) saw `disconnected` until 20:39:40,
  `connecting/browser` at 20:39:41 UTC (the window opened on the Fedora workstation), and
  `connected` at 20:40:42 UTC, 61 s later: `captured_by: "window"`, `captured_at:
  1790282441.284` = 2026-09-24T20:40:41.283Z, `stored_at`/`verified_at` 20:40:41.398Z, `cookie:
  {"session": false, "expires": 1790887240.448}` = 2026-10-01T20:40:40.447Z, again 7.0 days
  (604 799 s) after capture; `last_success_at: 1790282442.004` = 0.7 s after capture, the
  phone's own list request, so the phone's tab listed by itself (the owner's report says what
  the phone showed); Diagnostics 0; no Chrome process with the profile afterwards (the window
  closed by itself). Files at 22:40: `gopro-token` (0600, 1 273 bytes), `gopro-session.json`
  (0600, 215 bytes, `captured_by "window"`, `token_mtime` = the file's mtime, no part of the
  token), the profile `gopro-browser` (0700). This capture is the one now live on the Fedora
  workstation, and the one rows 5.11-5.12 measure; the sign-in in the window was in a profile
  the disconnect had emptied, so it was a full sign-in (the owner's report confirms which).
  cast-tv does not log requests, so the phone's address is not in its output. Ticked with the
  owner's report on the phone's screens.
- **Row 5.8, the owner's half, and row 5.9 for Chrome again** (2026-09-24, the owner): the
  phone showed the on-host note ("notka była"), the phone's tab went to the list by itself
  without a refresh ("lista sama"), the window on the Fedora workstation asked for a sign-in
  ("prosiło o logowanie": the disconnect had emptied the profile, so no remembered session
  carried over - the profile question of row 5.11 is a different case, a profile that *has*
  seen a sign-in), and no "Save password?" bubble appeared ("bez dymku"), the second Chrome
  observation for row 5.9. Row 5.8 is ticked on the two halves; row 5.9 still waits for Edge.

## Measurements

To be filled by the owner from Phase 5 of the plan; values only, never a token.

| Field | Observation | Date |
| --- | --- | --- |
| `captured_at` / `captured_by` of the first window capture (Fedora, Chrome) | 2026-09-24T20:20:54.957Z (22:20:54 local) / `window`; cast-tv from the checkout at `d14deaa`, Google Chrome 153.0.8010.47 | 2026-09-24 |
| `cookie.session` / `cookie.expires` at capture | `false` / 1790886054.401 = 2026-10-01T20:20:54Z, 7.0 days after capture: a persistent cookie | 2026-09-24 |
| Sign-in method and seconds to the list (Fedora, Chrome) | password, no 2FA, no "Save password?" bubble; 2 min 17 s from the button to the list including the typing (the last click was not timed) | 2026-09-24 |
| Sign-in method and seconds to the list (Windows, Edge, the artifact) | | |
| Worked for at least (last successful call after capture) | | |
| First refusal (first 401 after capture) | | |
| "Open gopro.com again" after the refusal: closed without typing, or asked to sign in | | |
