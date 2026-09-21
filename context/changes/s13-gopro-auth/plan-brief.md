# GoPro without a hand-pasted token (S-13) — Plan Brief

> Full plan: `context/changes/s13-gopro-auth/plan.md`
> Frame brief: `context/changes/s13-gopro-auth/frame.md`
> Research: `context/changes/s13-gopro-auth/research.md`

## What & Why

> S-13 bundles two problems - a *hand-off* problem (a session credential GoPro keeps out of page
> script has to reach cast-tv without a devtools trip) and a *standing* problem (cast-tv has no
> permitted way to call `api.gopro.com`) - and only the first is something cast-tv can change.
> (`frame.md:93-96`)

This plan solves the hand-off: the GoPro tab gets one button that opens a gopro.com window
cast-tv owns on the host, reads the session cookie from it over the Chrome DevTools Protocol
once the person has signed in, proves it against the API, and closes the window. The standing
stays what it is and is written down as a limitation, as S-11 wrote down the screen saver.

## Starting Point

The tab asks for a token copied out of the browser's devtools (`app.js:14-27`), and after a 401
asks again in a banner. The cookie is HttpOnly, so no page script can hand it over; GoPro's
"Request Access" is a business intake; every prior third-party client pastes or captures a
session (frame, hypotheses 1-2). Google Photos already runs a host-only, multi-step consent in a
thread with a `connecting` state, a note for the phone and Cancel (`gphotos.py:291-435`) - the
shape this plan copies. A local spike on 2026-09-21 proved the plumbing: Chrome 153 launched
with its own profile and a random DevTools port, a stdlib WebSocket client read an HttpOnly
cookie, `Browser.close` ended the process.

## Desired End State

Press **Open gopro.com**, sign in in the window that opens on the computer running cast-tv, and
the tab lists the library when the window closes by itself. After a refusal, the banner says
"cast-tv couldn't access your GoPro media with this session" and offers the same button. The
token field appears only when no window could be opened, with the reason. Diagnostics shows how
long the session was observed to work. The README states the standing with a date.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| -------- | ------ | ---------------- | ------ |
| Scope | The hand-off only; the standing is a documented limitation | Only the hand-off is cast-tv's to change; the owner chose it on 2026-09-21 | Frame |
| Mechanism | CDP over a Chromium-family browser already on the host, own profile, stdlib WebSocket | No new dependency or build step; a real GoPro window (social login, 2FA); Windows 11 always has Edge; proven locally | Plan |
| Success | Only after `search(tok, 1)` answers 200; cookie read by name and domain | Finding a cookie proves nothing; the API does | Plan |
| The paste | Fallback only, when the hand-off is unavailable or failed (detected by trying to launch); `--token` and `GOPRO_TOKEN` stay | The hack leaves the daily path without cutting off a Firefox-only host; a closed window or Cancel is not a failure | Plan |
| The profile | Persistent, `config_dir()/gopro-browser` (0700), password manager off, cache in `cache_dir()`, removed by `disconnect()` | GoPro's remember-me is the refresh-token equivalent OneDrive already has; no password is ever saved (ToS §1) | Plan |
| Wording | "Open gopro.com" / "Open gopro.com again"; the body names the window and the computer; never "GoPro sign-in" | The tab may look like a sign-in but must not claim it; a step names the window | Frame + Plan |
| Measurement | Passive: `captured_at`, `last_success_at`, `first_401_at`, cookie `session`/`expires`; reported as an observed period in Diagnostics | The frame forbids assuming "hours"; a 401 dates a refusal, not an expiry | Frame + Plan |
| Edge cases | Closed window = cancel; stale cookie waits for a new value; exit closes the window; no "Forget the session" control | Cancel and failure differ; the persistent profile must not loop on 401; nothing stays on screen by accident | Plan |
| CLI | UI only; `cast-gopro`'s no-token message points at the UI | One engine, one path | Plan |
| Verification | Both systems before merge; Windows on the PR's own `.exe` artifact | The PRD guardrail and the lesson that the real artefact finds what source runs miss | Plan |
| `CAST_TV_BROWSER` | An exclusive override, used even when the file is missing; a failed launch falls back | The fallback rows need a way to force a failure; `GOOGLE_CLIENT_JSON` already works this way | Review F1 |
| Metadata persistence | `gopro-session.json` next to the token (no secret), trusted only while its `token_mtime` matches | A refusal will most likely come in a later run than the capture; otherwise the measurement is lost | Review F2 |
| Diagnostics path | A `report` seam on the source; one card on the first refusal with the observed period; no panel markup change | Source-route errors never reach the ring today (`api.py:57-59`) | Review F3 |

## Scope

**In scope:** `castlib/auth/cdp.py` and `castlib/auth/browser.py` (new); the round in
`GoProSource` with `connecting`, `close()`, timing fields, fallback signal, profile removal; the
UI gate, banner, hint and Diagnostics texts; `cast-tv --version` and the smoke test; README, PRD
FR-010 and Non-Goals, roadmap S-13, the CLI message; manual verification on Fedora and on the
Windows artifact.

**Out of scope:** a "Forget the session" UI control; bookmarklet, extension, pywebview; headless
silent retry; active probing; `cast-gopro --connect`; any change to the standing; Firefox;
Flatpak/Snap special-casing; the person's own browser profile; OneDrive and Google Photos.

## Architecture / Approach

`browser.Handoff` finds a candidate (`CAST_TV_BROWSER`, then registry / Program Files on
Windows, `PATH` names elsewhere), prepares the profile, launches `--user-data-dir --disk-cache-dir
--remote-debugging-port=0 --app=https://gopro.com/media-library/`, waits for
`DevToolsActivePort`, opens the browser-level WebSocket (no `Origin` header), and polls
`Storage.getCookies` once a second, handing each distinct `gp_access_token` value to a
`verify` callback once. `GoProSource` runs that in a daemon thread under a flow record and the
generation counter (the `gphotos` shape), adopts the verified value like a paste, and exposes
`connecting/browser`, `flow_error`, `fallback` and the timing fields in `status()`. The UI
renders the step next to the consent and device-code blocks. The launcher and the CDP session
are seams a fake browser replaces in tests.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| ----- | ---------------- | -------- |
| 1. The hand-off engine | `cdp.py`, `browser.py`, fake-browser tests, `--version` line, smoke assertion (PR builds the `.exe`) | The WebSocket subset costs more lines than estimated; Windows candidate discovery |
| 2. The source and the API | The round in `GoProSource`, fallback signal, persisted session metadata, the first-refusal Diagnostics card, `close()`, profile removal | Generation races between capture, disconnect and a second round |
| 3. The UI gate | The button, the step, the banner, the fallback block, the texts | A message owned by the poll instead of the action (`lessons.md:41-46`) |
| 4. Docs, PRD, roadmap, CLI | README with the dated standing, FR-010, S-13 row, `cast-gopro` message | Overclaiming a lifetime or the profile's benefit before it is observed |
| 5. Both systems before merge | Written observations for Fedora/Chrome and Windows/Edge on the artifact | A real gopro.com sign-in in an `--app` window of a fresh profile is not yet proven; Edge policy |

**Prerequisites:** the Fedora machine with Chrome; the Windows 11 laptop with Edge; the owner's
GoPro account for the manual rows (the agent never sees a credential); the PR branch
`s13-gopro-auth-spike` up to date with `main` (`lessons.md:13-18`).
**Estimated effort:** about 4-5 sessions across the five phases, plus the dated rows 5.11-5.12
when the first refusal happens in use.

## Open Risks & Assumptions

- A real gopro.com sign-in inside an `--app` window of a fresh profile has not been performed;
  bot-gating (`gopro.com/account` answers 403 to non-browsers) could in theory affect a
  debug-enabled Chrome. Row 5.3 is the test; the fallback is the exit.
- Whether GoPro's cookie is persistent or a session cookie is unknown; if it is a session cookie
  the profile's remember-me may carry nothing across window closes. Rows 5.3 (`cookie.session`)
  and 5.11 answer it; the plan promises nothing about it.
- The `Preferences` pre-seed for the password manager is a documented Chromium preference, not a
  supported switch; row 5.9 verifies it on Chrome and Edge.
- Edge under an enterprise policy (`RemoteDebuggingAllowed=false`) fails to yield a port; that is
  a "failed" hand-off and falls back by design, untested here (no such laptop).
- Token lifetime stays unmeasured until row 5.12; no text in the repo may assume it.

## Success Criteria (Summary)

- On both systems the GoPro tab connects through the window with no devtools step, and the token
  field is never on screen unless the window could not be opened.
- A refused session shows the decided banner and reconnects through the same button; Ctrl+C or
  Cancel never leaves a window behind.
- README, PRD and roadmap describe exactly what is built, with the standing dated; the observed
  period lands in `research.md` when it is first seen.
