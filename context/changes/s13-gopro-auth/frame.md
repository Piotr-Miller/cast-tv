# Frame Brief: GoPro without a hand-pasted token (S-13)

> Framing step before /10x-plan. This document captures what is *actually*
> at issue, separated from what was initially assumed. Written 2026-09-20.

## Reported Observation

The owner, 2026-09-19 (`context/foundation/roadmap.md:146`): "Rozkminka jak uprościć
dodawanie tokenu dla GoPro - ręczne wklejanie jest jakieś nieprofesjonalne" ("figure out
how to simplify adding the GoPro token - pasting it by hand looks unprofessional").

What is on screen: the GoPro tab's gate says "GoPro has no public sign-in for apps", then
lists three steps - sign in at gopro.com/media-library; F12 → Application → Cookies →
gopro.com → copy `gp_access_token` (or Network → any api.gopro.com request → the
`authorization` header after "Bearer "); paste below (`castlib/ui/app.js:14-27`,
`castlib/ui/index.html:210`). After a 401 the same paste field returns as a banner over
the list (`castlib/ui/index.html:273`). A token pasted twice is folded to one copy
(`castlib/sources/gopro.py:67-73`) because that happened in use.

## Initial Framing (preserved)

- **User's stated cause or approach**: the paste exists because GoPro offers no sign-in a
  third-party app may use; "the cloud API cast-tv calls is not public"
  (`roadmap.md:149-150`). The spike (`research.md`, 2026-09-20) confirmed the first half and
  narrowed the replacement to "reuse a real browser session (the cookie) or go through the
  gated Cloud API application; there is no third road" (`research.md:155-157`).
- **User's proposed direction**: "a GoPro sign-in inside an app-owned browser window
  (pairs with S-12) that keeps the resulting cookie; a browser extension or bookmarklet
  that hands the token to the local server" (`roadmap.md:151-153`).
- **Pre-dispatch narrowing** (owner, 2026-09-20): what is unprofessional is *the devtools
  excursion* **and** *that it is a hack at all* - not that the paste recurs. How often a
  fresh token has been pasted since 2026-09-18: not tracked. The audience is the owner,
  day to day, not release users.

## Dimension Map

1. **The browser-to-app hand-off** - the framing assumes the token lives only where
   devtools can reach it. It would break here if `gp_access_token` were readable by page
   script (not HttpOnly) or returned in a login response body.
2. **cast-tv's standing with GoPro** ← initial framing - the framing assumes no sanctioned
   sign-in exists *and*, implicitly, that a sign-in-shaped hand-off would be more
   legitimate than a paste. It would break here if GoPro published a route for an
   individual developer, or if its terms permitted personal tooling.
3. **The session's lifetime** (why the paste recurs) - ruled out as the origin by the
   owner's answer; kept on the map because it is unmeasured (`90da614`: "a hint rather
   than knowledge"; a token stored 2026-09-07 was refused on 2026-09-09, archived
   `plan.md:45`) and every browser-session road inherits it. Not investigated.

## Hypothesis Investigation

| Hypothesis | Evidence | Verdict |
| --- | --- | --- |
| 1. The token is reachable outside devtools (page script, a bookmarklet) | Owner, 2026-09-20, signed-in gopro.com/media-library tab, console: `document.cookie.includes('gp_access_token=')` → **false**. The cookie is invisible to page script there (HttpOnly, on the evidence). The sub-agent's contrary inference - the login app reads it via `document.cookie` in its DEV branch, `/logout` clears it without HttpOnly (both read 2026-09-20) - described a non-production path and a clearing header that need not repeat the original flags. Side findings: no `refresh_token` or renewal call in any login bundle; `/login/api/code` is 2FA delivery; the login response body carries no token as far as the page uses it. | NONE - framing holds; a bookmarklet is ruled out |
| 2. A GoPro-sanctioned road exists for an individual, or the terms permit personal tooling | Developer-tools page (read 2026-09-20): "Cloud API (BETA) … Request Access" links to `gopro.com/en/us/connect`, **not** to the enterprise-application URL `research.md:20-26` recorded (only the SDK buttons go there). `/connect`, read by the owner 2026-09-20 in a browser: a sales/partnership intake ("Please add your details to one of the below tabs and someone will reach out to you soon") with tabs Bulk Purchasing / Business Partnerships / Reseller Opportunities / Public Relations; on the tab shown, "Who are you purchasing for? School / Government Agency / Company / Broadcasting / Other" and Company/Organization required (the Business Partnerships tab's fields were not read). Terms of Use (2024-04-11; read 2026-09-20) §9: no access "through the use of any engine, software, tool, agent, device or mechanism … other than the software and/or search agents provided by GoPro or other generally available third party web browsers"; §5.1 personal and non-commercial use only. No developer or API terms exist; the only developer licence GoPro publishes is the camera-SDK documentation licence (github.com/gopro/camera-kotlin-sdk, LICENSE). The 2016 Developer Program was company-only and discontinued by 2018 (HN 16189633); Open GoPro (2021) is camera-only. OpenGoPro issue #404 (2023): an individual's "Partnership → Software" contact went a month without an answer. | NONE - framing holds; a paste, an extension and an app-owned browser stand on the same footing |
| 3. The paste is unprofessional because it recurs | Owner did not select it. Lifetime unmeasured here; third-party clients disagree: "TTL of a few hours" (aricha/GoProcure), "expires after a few days" (Crafoord/gopro-cloud-export). | NONE as origin; OPEN as a measurement for the plan |

## Narrowing Signals

- Owner: the unprofessional parts are the devtools trip **and** the hack itself, for the
  owner's own daily use. These pull apart: a smoother hand-off removes the first and
  leaves the second untouched.
- `document.cookie` on the signed-in tab does not contain `gp_access_token`: page script
  cannot read it; only devtools, a browser extension with the cookies permission, or a
  browser the app owns can. Of the roadmap's three ideas the bookmarklet is out. How the
  media-library page builds its own `Authorization: Bearer` header when page script cannot
  read the cookie was not established; nothing observed points at an endpoint that returns
  the token, and the plan should not assume one.
- `/connect` is a business intake form. The Cloud API beta is not a road an individual
  non-commercial tool can take on today's evidence.
- Prior art (sub-agent, 2026-09-20, GitHub API over twelve repositories): every
  third-party client of `api.gopro.com` is either a devtools paste (gpdwn, gpcd,
  gopro-plus, GoProcure, gopro-api …) or a captured session - Electron intercepting the
  post-login redirect (Woyken), a whole Cookie header pasted (Crafoord), a bundled Chromium
  that "takes the session token" (JeroenMinnaert/gopro-media-downloader, 2026-08-31: the
  roadmap's app-owned-browser idea, already built by someone else). None records contact,
  block or endorsement from GoPro; absence of enforcement is not permission.

## Cross-System Convention

In cast-tv every other source carries a vendor-issued client identity and a documented
grant with refresh: OneDrive ships the owner's Entra registration
(`castlib/sources/onedrive.py:39`; device code, ~90 days), Google Photos ships a built-in
client (`castlib/auth/_builtin_client.py`; loopback + PKCE, refresh token). GoPro is the one
source with no client identity at all; its "connection" is a borrowed browser session. The
archived change already rejected an embedded webview for this - "revisit only if pasting a
token proves genuinely painful in use" (`context/archive/2026-09-07-cloud-source-ui/change.md:186-189`)
- and `context/foundation/lessons.md:27-32` counts a pasted token as an acceptable in-UI
step. S-11 set the precedent for closing a slice as documented rather than built when the
other side leaves no lever (`context/archive/2026-09-20-s11-screensaver/`).

## Reframed Problem Statement

> **The actual problem to plan around is**: S-13 bundles two problems - a *hand-off*
> problem (a session credential GoPro keeps out of page script has to reach cast-tv
> without a devtools trip) and a *standing* problem (cast-tv has no permitted way to call
> `api.gopro.com`) - and only the first is something cast-tv can change.

The hand-off problem is real and its mechanism space is now narrowed by evidence: page
script cannot read the cookie, so what remains is a browser the app owns or an extension
that can, and either is the same borrowed session as the paste. The standing problem has
no code-side fix: the only "Request Access" is a B2B intake, no terms permit third-party
tools, and every prior client lives in the same grey zone. Half of the initial framing held
("no sign-in exists"); its implicit half - that a sign-in-shaped hand-off would be less of
a hack - does not. Addressing the hand-off makes the tab *look* like a sign-in; it does not
make it one, and whatever is planned has to say so rather than promise it.

## Confidence

**HIGH** - both dimensions were closed by the owner's own observations (the console check,
the `/connect` page) on top of documentary evidence read today; the external prior art
converges on the same two roads; the repo's own earlier decision points the same way. One
measurement stays open for the plan, not the frame: how long a token actually lives.

## What Changes for /10x-plan

The plan, if there is one, is about the hand-off only, under a stated premise that
cast-tv's standing with GoPro is unchanged and is recorded as a limitation (as S-11
recorded the screen saver). The bookmarklet idea is dropped. "GoPro sign-in" is not a
phrase the plan may use for a captured session. Whether the hand-off is worth building at
all - against the archived "revisit only if pasting a token proves genuinely painful in
use" and a still-untracked paste frequency - is the owner's decision before planning, not
the plan's. The plan must not assume a token lasts hours until someone measures it.

## References

- Source files: `castlib/sources/gopro.py:37-46,67-73`, `castlib/ui/app.js:14-27`,
  `castlib/ui/index.html:210,273`, `castlib/sources/onedrive.py:39`,
  `castlib/auth/loopback.py:14-19`
- Related research: `context/changes/s13-gopro-auth/research.md` (two spikes, 2026-09-20);
  a correction is owed to its lines 20-26 (Request Access → `/connect`, not the
  enterprise-application form)
- Prior decisions: `context/archive/2026-09-07-cloud-source-ui/change.md:179-189`,
  `context/foundation/lessons.md:27-32`, commit `90da614`
- External (all read 2026-09-20): https://gopro.com/en/us/info/developer-tools;
  https://gopro.com/en/us/connect (owner, in a browser; 403 to every fetcher);
  https://gopro.com/en/us/legal/terms; https://gopro.github.io/OpenGoPro/docs/;
  https://github.com/gopro/OpenGoPro/issues/404; https://news.ycombinator.com/item?id=16189633;
  https://github.com/JeroenMinnaert/gopro-media-downloader
- Investigation tasks: no task-list tool in this session; two read-only sub-agents
  (hand-off; standing with GoPro), 2026-09-20, no GoPro credential used or seen
