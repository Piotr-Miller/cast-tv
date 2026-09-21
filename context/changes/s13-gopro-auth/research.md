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
