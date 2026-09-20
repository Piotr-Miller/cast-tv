---
date: 2026-09-20T13:25:07+0000
researcher: Claude (Opus 5) with Piotr Miller
git_commit: fa64a557daaac001c89e0576c771d990fbd47135
branch: s11-screensaver-research
repository: Piotr-Miller/cast-tv
topic: "The Samsung's screen saver covers a playing cast; which TV policy fires, and what can a network client do about it"
tags: [research, s11-screensaver, samsung, tizen, dlna, upnp, screensaver]
status: complete
last_updated: 2026-09-20
last_updated_by: Claude (Opus 5)
last_updated_note: "Added the measurement run of 2026-09-20 15:52-16:35 CEST"
---

# Research: the screen saver over a playing cast

**Date**: 2026-09-20 15:25 CEST
**Researcher**: Claude (Opus 5), with Piotr Miller
**Git Commit**: `fa64a557daaac001c89e0576c771d990fbd47135`
**Branch**: `s11-screensaver-research`
**Repository**: Piotr-Miller/cast-tv

## Research Question

Roadmap slice S-11: the TV shows its own screen saver during a slideshow or a long film. `frame.md`
settled that this is a TV-side policy covering a valid DLNA session, and ruled out re-encoding the
slideshow and generic DLNA keepalive. This research answers what was left open: **which** policy
fires, **how to measure** it on this TV, and whether the Samsung remote channel is a real way out.

## Summary

**The likely cause is documented, by Samsung, and it is not about stillness.** Samsung's own Smart TV
developer guide says an app must call `webapis.appcommon.setScreenSaver(SCREEN_SAVER_OFF)` when
playback starts and `SCREEN_SAVER_ON` when it stops. Suppressing the saver is therefore **opt-in per
app**, not something the TV infers from decoding media. Apps that do not call it get the saver over
live playback; that is exactly what Spotify's Tizen app and the TizenTube project are on record
fixing. Nothing in DLNA/AllShare can make that call from outside, because it is a Tizen in-app
JavaScript API, not a network-exposed one. This explains why a moving film is covered just as a still
photo is, which no "the TV sees no motion" theory can.

**The saver's own trigger is a 2-minute timer** on "the same still image **or** no input signal",
cancelled by any remote button except power. That "or no input signal" clause is the one that
plausibly catches a DLNA session the TV does not count as an app.

**Consequences for us.** UPnP has no vocabulary for a display timeout, so no amount of DLNA politeness
helps; that closes the last DLNA hypothesis with a documented reason rather than a guess. The only
external lever anyone has found is the undocumented Samsung remote WebSocket on port 8002 — and the
evidence says a key press **dismisses** the saver and restarts the 2-minute clock rather than
preventing it, so a keepalive would mean pressing a real remote key every couple of minutes, forever,
with an on-screen side effect each time. That is a workaround with a visible cost, not a fix.

**What is not yet known is specific to this TV** and needs measuring: which of several timers is
actually firing (the 2-minute saver, a ~2-hour presence-based screen-off, or a ~4-hour auto power
off), whether a settings change alone removes it, and whether a periodic key really holds it off on
this 2025 model. Section "Measurement protocol" is written to answer exactly those, in one sitting,
with timestamps rather than impressions.

**One new lead, found on the TV today:** its AVTransport exposes a Samsung extension
`X_PlayerAppHint(UpnpClass, PlayerHint)`, which asks the TV to pick a particular internal player app
for the content. If the TV's photo path and video path are different apps, and one of them calls the
suppression API, a hint is a one-line experiment with a real chance of mattering. Nobody has tested
this; it is cheap, so it belongs in the same sitting as the rest.

## Detailed Findings

### What this TV actually is (measured today, 2026-09-20)

Read from the TV at 192.168.50.142, all read-only calls:

- `GET http://192.168.50.142:8001/api/v2/` → `modelName: QE83S85FAEXXH` (the 2025 S85F QD-OLED, 83"),
  internal model `25_PTM_QD`, `OS: Tizen`, `Language: pl_PL`, `countryCode: PL`,
  `PowerState: on`, **`TokenAuthSupport: true`**, `remote_available: true`,
  `resolution: 3840x2160`, `name: 83" OLED`. `firmwareVersion` comes back as the literal string
  `Unknown`, so **the firmware version cannot be read over the network** and must be read off the TV's
  own menu.
- Ports open: **8001, 8002, 8080, 9197**. 8002 being open matches the modern (TLS) remote channel.
- UPnP services on 9197: `AVTransport:1`, `RenderingControl:1`, `ConnectionManager:1`. Device
  description at `/dmr`, `modelNumber: AllShare1.0`.
- **AVTransport actions**, beyond the standard set: `X_PrefetchURI`, `X_GetStoppedReason`,
  **`X_PlayerAppHint`**, `X_DLNA_GetBytePositionInfo`.
  `X_PlayerAppHint` takes `(InstanceID, UpnpClass, PlayerHint)`.
- **RenderingControl actions**, beyond `GetMute/SetMute/GetVolume/SetVolume`: `X_GetTVSlideShow`,
  `X_SetTVSlideShow` (with a boolean show state and a theme id), `X_SetZoom`, `X_GetAspectRatio`,
  `X_Move360View` and friends.
- **But the TV disowns most of them.** `X_GetServiceCapabilities` on RenderingControl answers
  `GetMute,SetMute` — the SCPD is a generic Samsung template, and only mute is claimed. Consistent
  with that, `X_GetTVSlideShow` answers `CurrentShowState 0, CurrentThemeId 0, TotalThemeNumber 0`.
  Treat the vendor slideshow extension as advertised-but-empty unless a test proves otherwise.
- `GetCurrentTransportActions` answers an empty `<Actions>` list with nothing casting, and
  `X_GetStoppedReason` answers empty fields. `GetVolume` reads `0` and `GetMute` reads `0` on this
  set, which matters for key choice later: a volume key here would be visible and would move a
  volume that currently sits at zero.

This is the first time the project has touched RenderingControl or ports 8001/8002 at all; the archive
has no record of either (see "Historical context").

### Which TV-side policy fires

Ranked by fit with the observation. The evidence is external; the verdict for this unit is what the
measurement has to settle.

**1. The OLED protective Screen Saver — prime suspect.**
Samsung (official, PL and EN):
[jak-zapobiegac-wypalaniu-pikseli…](https://www.samsung.com/pl/support/tv-audio-video/jak-zapobiegac-wypalaniu-pikseli-na-ekranie-telewizora-oled/),
[how-samsung-oled-tv-displays-are-protected…](https://www.samsung.com/levant/support/tv-audio-video/how-samsung-oled-tv-displays-are-protected-with-logo-detection-and-screen-saver/).
It activates **after 2 minutes** when the TV "displays the same still image **or does not have an input
signal** from an external device", dims by up to 95%, is **on by default and cannot be disabled**, and
"upon pressing any button except for power button… Screen Saver mode is canceled". The second half of
the trigger — no input signal — is what can catch a DLNA session, and it does not care whether the
picture moves.

**2. Auto Power Saving — presence-based screen-off, fits a longer session.**
Settings → General & Privacy → Power and Energy Saving → Auto Power Saving
([Samsung, 2025 models](https://www.samsung.com/levant/support/tv-audio-video/how-to-use-power-and-energy-saving-functions-on-your-2025-samsung-smart-tv/)).
It watches Wi-Fi signals and remote usage and **turns the screen off** when it concludes nobody is
there; Samsung Poland's newsroom describes reducing brightness after **more than two hours** without
detected viewer activity
([news.samsung.com/pl](https://news.samsung.com/pl/jak-telewizor-samsung-moze-oszczedzac-energie-i-zadbac-o-twoje-rachunki-za-prad)).
Nobody is pressing a remote during a two-hour film, so this fits the "long film" half of the complaint
even if the 2-minute saver were somehow suppressed. **Configurable**, unlike the protective saver.

**3. Auto Power Off — hours, and it powers the set down.**
Same menu; Samsung's 2025 page says it triggers when "the TV buttons and remote control are not used
for a set period of time". The duration is not on the 2025 page; regional support and independent
write-ups put it at about **4 hours** with a 300-second on-screen countdown first. If the TV had gone
off rather than dark, this would be the candidate — worth checking the setting while in the menu, not
worth a dedicated test.

**4. Ruled out as the cause, listed so nobody re-checks them.** *Pixel Shift* and *Auto Logo
Brightness* (Panel Care) move or dim parts of the image, they do not blank it. *Auto Picture Off*
(Accessibility) is **user-invoked** — a deliberate "screen off, keep the sound" mode, not a timer.
*Ambient Mode* has to be entered; community reports of it "taking over" most likely misname the Auto
Power Saving screen-off.

**5. No signal power off** is about a physical input with no signal, which is not our case.

### Why no DLNA politeness can fix it, and what does suppress the saver

**The suppression API is Samsung's, and it is in-app.** Samsung's developer guide
([setting-screensaver](https://developer.samsung.com/smarttv/develop/guides/fundamentals/setting-screensaver.html))
documents `webapis.appcommon.setScreenSaver(SCREEN_SAVER_ON | SCREEN_SAVER_OFF)` and tells app authors
to turn it **off when playback starts or resumes** and **on when it pauses or stops**. It even notes
that if "Auto Protection Time" is switched off in the TV settings, the API has no effect. Two things
follow:

1. **Suppression is opt-in per app.** The TV does not infer "media is playing" from decoding. An app
   that never calls it gets the saver over live playback. This is the documented mechanism behind the
   symptom, and it explains the moving-film case that every media-shape theory failed to explain.
2. **A network client cannot call it.** It is a Tizen web-app JavaScript API inside the app's own
   sandbox, not an RPC. cast-tv talks to the TV's bundled DLNA renderer from outside; whether that
   renderer calls `setScreenSaver` is Samsung's choice, not ours, and no public source documents what
   the stock AllShare renderer does.

**Corroboration that this is a live, current failure mode, not a theory:**

- TizenTube issue [#630](https://github.com/reisxd/TizenTube/issues/630) — "Screensaver activates
  during active playback", diagnosed in that project as missing `setScreenSaver(SCREEN_SAVER_OFF)`
  calls (maintained open-source project).
- Spotify's Tizen app leaves the screen sleeping after ~2 minutes for the same reason, while apps that
  do call the API do not
  ([community thread](https://community.spotify.com/t5/Other-Podcasts-Partners-etc/Samsung-app-not-keeping-the-TV-awake-while-playing/td-p/6360915), forum).
- Owners of the **2025** S90F QD-OLED report the screen saver covering an active Google Cast session,
  worse after a firmware update, cleared only by pressing the remote again and again
  ([us.community.samsung.com](https://us.community.samsung.com/t5/LED-and-OLED-TVs/S90F-going-to-screensaver-while-casting/td-p/3460861), forum;
  the page refuses automated fetches, so this rests on search excerpts — lower confidence, but it is
  the closest model and year to ours).

**The standard has nothing to offer.** UPnP AVTransport and RenderingControl cover transport state and
presentation values such as volume and brightness; neither defines a display timeout, screen-saver or
standby-inhibit variable
([UPnP AVTransport v3 spec](https://upnp.org/specs/av/UPnP-av-AVTransport-v3-Service-20101231.pdf)).
So a fully compliant renderer still has no way to be told "do not cover me". This is what turns
`frame.md`'s **NONE** verdict on DLNA keepalive from an observation into a rule.

**HDMI-CEC does not apply**: Anynet+ signals travel the physical HDMI link, and a DLNA cast has no
HDMI connection at all — the TV decodes internally. There is no link to send "device active" over.

### The remote channel: what it costs and what it buys

**Endpoint and pairing.** `wss://<ip>:8002/api/v2/channels/samsung.remote.control?name=<base64>`, the
TV presenting a self-signed certificate; the reference Python library disables verification outright
(`ssl.CERT_NONE`). On first connect the TV shows an "allow this device" prompt; accepting returns a
`token` in the `ms.channel.connect` payload, which the client stores and replays as `token=` to skip
the prompt ([xchwarze/samsung-tv-ws-api](https://github.com/xchwarze/samsung-tv-ws-api), maintained).

**The prompt may come back every time, and that is a TV setting we cannot read.** The library's own
troubleshooting says newer sets default to asking **on every connection**, fixed only in the TV menu:
Settings → General → **Device Connection Manager → Access Notification Settings → "First Time Only"**.
A real-world fix in another project
([Apps2Samsung PR #645](https://github.com/Apps2Samsung/Apps2Samsung/pull/645)) found three distinct
causes of re-prompting: keying the stored token by the TV's **IP address** (a DHCP change looks like a
new device), writing the settings file before assigning the new token, and that menu setting — for
which **there is no API to read or change it remotely**. Token lifetime is undocumented; it appears to
die only when that menu setting is "Always", when the device is removed from the TV's Device List, or
on a Smart Hub reset.

**There is no harmless key.** The protocol as reverse-engineered exposes only real IR-equivalent key
codes; no project sends a no-op or a "stay awake" frame
([COMMANDS.md](https://github.com/xchwarze/samsung-tv-ws-api/blob/master/COMMANDS.md)). Judging each
candidate by what it does: `KEY_MUTE` **toggles** — repeated sends alternate mute; `KEY_VOLUP`/
`KEY_VOLDOWN` change volume and raise the on-screen volume bar (and this TV reads volume `0` today);
`KEY_HOME` opens Smart Hub and would stop or background the very playback we are protecting;
arrow keys usually surface the seek overlay; `KEY_ENTER` often toggles play/pause. The least-bad
construction anyone can offer is `KEY_VOLDOWN` immediately followed by `KEY_VOLUP` — net-zero volume,
a brief on-screen flash — and that is a deduction from key semantics, not a recipe any source endorses.

**Dismiss, not prevent.** Samsung's wording is cancellation ("upon pressing any button… Screen Saver
mode is canceled"), the S90F owners describe pressing the remote repeatedly through a cast, and no
source describes any key pre-empting the timer. The only documented prevention is the in-app API. So a
keepalive would work only by re-arming a dismissal faster than the ~2-minute countdown — every two
minutes, for the length of a film, each time with a visible flash. **That is the honest shape of this
option**, and it is why the spike must measure prevention on this set before anyone plans it.

**The stdlib cost, concretely.** Every reference implementation (samsungtvws, Home Assistant's
`samsungtv`, the Node projects) depends on a third-party WebSocket package — Home Assistant breaks when
`websockets` is missing or mismatched. Writing it by hand against `socket` + `ssl` is nevertheless a
bounded job: an HTTP/1.1 Upgrade handshake, validating `Sec-WebSocket-Accept =
base64(sha1(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))`, then RFC 6455 framing where
**client frames must be masked** with a 4-byte XOR key, over an `ssl` context with verification off
for the self-signed certificate. Perhaps 150 lines with no reconnect logic; more once a TV reboot,
a changed IP or a revoked token must be survived.

### Alternatives named, not pursued

- **SmartThings** is the official route to this TV
  ([developer.smartthings.com](https://developer.smartthings.com/docs/api/public/)), but its public API
  is **cloud** (OAuth, internet round-trip, 30-day personal tokens), and its capability reference has
  `switch`, `mediaPlayback`, `audioVolume`, `audioMute`, `tvChannel`, `mediaInputSource` — **nothing
  for a screen saver or a display timeout**. A local path exists only as unofficial reverse-engineered
  CoAP-DTLS. Trading a LAN-only app for a cloud dependency to press a button is the wrong shape for
  this project.
- **Tizen settings over the network**: the port 8001 REST endpoint is read-only device info; no project
  or Samsung document exposes Panel Care or Power and Energy Saving as remotely settable.

### Where this would hook into cast-tv, if anything is built

Established by reading the code; these are facts about today's tree, not a design.

- **There is no shared ticker to extend.** Each promoted cast starts its own poll thread
  (`castlib/supervisor.py:198-199`), `POLL_INTERVAL = 2.0` (`castlib/supervisor.py:45`), and a `Show`
  adds a second independent wait loop at `TICK = 0.25` (`castlib/supervisor.py:484-507`).
- **`StayAwake` is the precedent to copy** (`castlib/platform.py:246-291`): a **counted** hold, taken on
  the 0→1 edge and released on 1→0, failures swallowed, bracketed in exactly two places —
  `App._promote` / `App._cast_ended` (`castlib/app.py:456`, `:459-461`) for a lone cast, and
  `Show.run`'s try/finally (`castlib/supervisor.py:444`, `:473-474`) for a show. Anything held "for the
  duration of playback" must be bracketed in both places or it will miss one path.
- **Its Linux backend is the shape for a supervised side channel** (`castlib/platform.py:144-179`):
  `systemd-inhibit … cat` blocking on a **pipe**, so the child dies with cast-tv even on SIGKILL, and
  `release()` closes stdin, waits 2 s, then kills. A held socket wants the same discipline.
- **Shutdown has a rule**: `App.close()` (`castlib/app.py:286-315`) force-releases and deliberately
  **never `join()`s** a thread, so that `close()` called from a request-handling thread cannot
  deadlock. A new background holder must release by closing its socket or setting an event.
- **A toggle is cheap and well-trodden**: `index.html:111-113` → `app.js:458-466` →
  `POST /api/settings` (`castlib/api.py:169-179`) → `App.set_interval` (`castlib/app.py:497-504`) →
  `Settings.set` → atomic `config.write_json` (`castlib/config.py:70-89`), read back through
  `App.status()` (`castlib/app.py:524`). A new boolean follows the same path; note `Settings.__init__`
  validates only `interval` on load (`castlib/app.py:98-99`).
- **There is no WebSocket code anywhere** in `castlib/` or `tests/` — zero hits for `ws://`, `wss://`,
  `websocket`. This would be a new protocol surface for a stdlib-only app.
- **The app knows almost nothing about the TV**: discovery parses only `friendlyName` and the
  AVTransport `controlURL` (`castlib/discovery.py:126-155`), `control_urls` resolves RenderingControl
  but **nothing ever calls it**, and `App.tv` is just `{ip, name, avt, state}` (`castlib/app.py:134`).
  Model, ports and capabilities have nowhere to live yet.
- **Test seams exist and must be respected**: `discovery._new_socket` / `discovery._select` are seams
  precisely because patching module-level `socket`/`select` broke threaded tests; DLNA tests replace
  `dlna.soap` wholesale with `FakeTV` (`tests/conftest.py:124-207`), whose `hooks[action]` lands a race
  inside a specific SOAP round-trip; `_no_stay_awake` (`tests/conftest.py:210-216`) is autouse so no
  test ever touches a real backend. A TV-facing keepalive needs the same autouse neutering.

## Code References

- `castlib/supervisor.py:45` — `POLL_INTERVAL = 2.0`, the existing TV poll cadence.
- `castlib/supervisor.py:198-199` — each promoted cast starts its own `cast-poll` thread.
- `castlib/supervisor.py:444`, `:473-474` — `Show.run` brackets `stay_awake` around a whole show.
- `castlib/platform.py:246-291` — `StayAwake`: counted start/stop, `close()` for shutdown.
- `castlib/platform.py:144-179` — `SystemdInhibit`: child blocked on a pipe, bounded release.
- `castlib/app.py:456`, `:459-461` — the per-cast stay-awake bracket.
- `castlib/app.py:286-315` — `close()` ordering, and the no-`join()` rule.
- `castlib/app.py:497-504`, `castlib/api.py:169-179`, `castlib/ui/app.js:458-466` — the settings path
  a new toggle would follow.
- `castlib/discovery.py:126-170` — all the app learns about a TV today.
- `tests/conftest.py:124-207`, `:210-216` — `FakeTV` with per-action hooks; the autouse stay-awake
  neutering.

## Architecture Insights

- **The saver is above the transport, and the transport cannot see it.** AVTransport reports PLAYING
  while the panel is covered, so cast-tv's health model is blind here by construction. Any "is the
  picture actually visible" check would need a different channel; whether one exists at all is the
  first thing the measurement looks for.
- **Opt-in suppression makes this a class of bug, not an incident.** Because Samsung requires apps to
  declare playback, every non-app source — DLNA, Cast, anything external — is exposed to the same
  2-minute timer. That is why this reproduces on a film and why no media-side change can fix it.
- **Any fix is a workaround with a visible cost**, so the plan should treat "change a TV setting and
  document it in the README" as a first-class outcome, not a failure to build something.

## Historical Context (from prior changes)

- **The screen saver appears nowhere in the project before 2026-09-19.** The single recorded
  observation is `context/changes/standalone-install/research.md` (row 3.2, 23:05): the saver came on
  over a still HEIC photo and stayed, AVTransport still answering PLAYING, zero errors.
- **The two 30-minute slideshows never looked at the TV.** Row 7.4 on Fedora and row 7.3 on Windows
  (`context/archive/2026-09-07-cloud-source-ui/research.md`) recorded GNOME idle seconds, the journal,
  the Windows execution-state bits and AVTransport — and nothing about what was on the screen. Likewise
  row 7.5 held a film in `PAUSED_PLAYBACK` for 65 minutes, sampling DLNA state every 5 minutes, with no
  note about the panel. **So the repo neither confirms nor contradicts a saver during an advancing
  slideshow**; the owner's report that it happens there too is the only evidence, and the measurement
  should capture it properly.
- Useful TV facts already established there: a still is reported as `PLAYING 0:00:00 / 0:00:00`, so the
  slideshow interval must come from our clock, not the TV's position; the TV re-fetches a photo whole
  (HEAD + GET, sometimes twice, no ranges), so a prepared file must stay served while it is on screen;
  `RelTime` is `0:00:00`, never zero-padded; a `Play` right after the TV already started a still draws
  UPnP 701, handled by `_settles_playing`.
- The project has **never** called RenderingControl on this TV, never read its device description
  beyond `friendlyName`, and never touched ports 8001/8002 — today is the first time.

## Related Research

- `context/changes/s11-screensaver/frame.md` — the framing step this builds on: the TV-policy
  hypothesis is STRONG, the media-representation hypotheses are contradicted, DLNA keepalive is NONE.
- `context/changes/standalone-install/research.md` — the live incident, in the rc1 run of row 3.2.
- `context/archive/2026-09-07-cloud-source-ui/research.md` — DLNA profiles, photo serving, the 701
  race, the long-run rows that did not watch the screen.

## Measurement protocol

One sitting, about 40 minutes, at the TV with the laptop. It answers: which timer fires, whether a
setting alone removes it, whether we can see it over the network, and whether the two cheap experiments
are worth anything. Record times to the second; `watch-tv.py` in this folder logs the network side once
a second so nothing rests on memory.

**Before anything, write down the starting state** (menus are in Polish on this set; English names in
brackets):

1. Settings → Support → About this TV [Pomoc → Informacje] — **the firmware version**. It cannot be read
   over the network, and the 2025 reports say behaviour changed between firmwares.
2. Settings → General & Privacy → Power and Energy Saving [Ogólne i prywatność → Zasilanie i
   oszczędzanie energii] — the current value of **Auto Power Saving**, **Auto Power Off**, and the
   energy-saving/brightness options.
3. Settings → General & Privacy → Panel Care [Pielęgnacja panelu] — **Pixel Shift** and **Auto Logo
   Brightness**, for the record.
4. Settings → General → Device Connection Manager → Access Notification Settings [Menedżer połączeń
   urządzeń → Ustawienia powiadomień o dostępie] — is it **"First Time Only"** or **"Always"**? This
   decides whether a paired client is prompted once or on every connect, and it cannot be read
   remotely.

**Run A — a single still photo, nothing else.** In one terminal:
`python3 context/changes/s11-screensaver/watch-tv.py 192.168.50.142 > run-a.tsv`. Cast one photo from
the UI, then leave the remote alone and do not touch the TV. Watch the screen. **Note the wall-clock
second the picture goes dark.** Expected, if the protective saver is the one: about 2 minutes. Keep
watching for 10 minutes: does it come back on its own, stay dark, or cycle? Then press one remote
button and note whether the picture returns and how long it stays before going dark again — that is the
dismiss-versus-prevent question, answered on our own TV.

**Run B — an advancing slideshow.** Same logging, a show with the interval at its default 8 s, and
again nobody touching the remote. This is the run the repo has never done with eyes on the screen. If
the picture survives past 2 minutes here but not in run A, the trigger is stillness and slide changes
count as content change; if it goes dark on the same schedule as run A, the trigger is "no input
signal" and the media does not matter. **Either answer is a result**; the second one matches the
owner's report and would make the still-image half of Samsung's wording irrelevant to us.

**Run C — a film, 10 minutes, untouched.** The moving-picture control. If this goes dark too, the
"still image" clause is definitively not what is firing on this set.

**In every run, afterwards, read the log.** The question is whether **anything** in it moved when the
screen went dark: transport state, position, `PowerState` from port 8001, mute, volume, or any field of
the device dictionary (the script prints a note when one changes). If nothing moves, then cast-tv
cannot detect the saver at all, and the plan must accept that the UI can never show "your TV is
covering this" — worth knowing before someone promises it.

**Experiment 1 — the cheap DLNA close-out** (this is the one bounded test `frame.md` allowed). While a
photo is on screen and dark, re-send `Play` from the laptop and see whether the picture returns; then,
in a fresh run, send `Play` every 60 s from the start and see whether the screen ever goes dark. If
neither helps, the DLNA path is closed with our own evidence and nobody needs to wonder again.

**Experiment 2 — the player hint, new today.** Before casting a photo, call the Samsung extension
`X_PlayerAppHint(InstanceID=0, UpnpClass=object.item.imageItem.photo, PlayerHint=…)` and see whether the
TV routes the content to a different internal player. The point is not the hint itself: if the TV's
video path is an app that suppresses the saver and the photo path is not, this is the only lever we
have that is inside DLNA. Try the obvious hint values, record the faults; a `600`/`401` fault is a
perfectly good answer and closes the lead in five minutes.

**If a setting alone fixes it**, that is the whole change: document it in the README with the exact
Polish and English menu path, and close S-11 without code. Measure that first, because it is free.

## Open Questions

1. **Which timer is it?** The 2-minute protective saver fits the recorded incident; nothing yet
   distinguishes it from Auto Power Saving on a longer run. Runs A to C settle it.
2. **Does an advancing slideshow behave differently from a single still?** The repo's two 30-minute
   slideshows never watched the screen; the owner reports it happens there too. Run B is the first
   clean look.
3. **Can cast-tv observe the saver at all over the network?** If no field moves, the answer is no, and
   the UI must never claim otherwise.
4. **Does the stock AllShare renderer call `setScreenSaver`?** Not documented publicly for any model.
   Only the runs can show it indirectly.
5. **On this firmware, does a periodic key prevent the saver or only dismiss it?** Everything found says
   dismiss. If it only dismisses, a keepalive means a visible flash every two minutes for the length of
   a film — a cost the owner should weigh before any spike is planned.
6. **Is Access Notification set to "First Time Only"?** If it is "Always", a paired client is prompted
   on every connect and the whole remote-channel option is unusable in practice.
7. **What does `X_PlayerAppHint` accept, and does the TV honour it?** Unknown to every source; cheap to
   try.
8. **Token durability** — undocumented; only a paired token left dormant for days would show it.

## Follow-up: the measurement, 2026-09-20 15:52-16:35 CEST

Run by Piotr at the TV with Claude driving the laptop; every cast came from a **local file**
through the CLI, so no cloud source and no Google consent was touched (row 3.4 of
`standalone-install` is unaffected). `watch-tv.py` logged the network side once a second
throughout. Times below are wall clock on the laptop; where a number depends on Piotr noticing
something, that is said.

### The TV's settings, read off the screen (photographs, not committed)

- **Firmware `T-PTMFDEUC-0090-1301.0`** (`E2592200, BT - S`), model `QE83S85FAEXXH`, name `83" OLED`.
  This is the current firmware for the model.
- **Power and Energy Saving** ("Oszczędzanie energii"): Energy Saving Solution **off**, Brightness
  Optimisation **off**, Minimum brightness 20, Dynamic brightness **off**, **Auto Power Saving off**,
  Auto Power Off **4 h**, no-signal Auto power off **disabled**.

**So every configurable energy feature is already off.** That removes the second candidate from the
research above - the presence-based screen-off cannot be what fires - and it kills the cheapest
possible outcome: **there is no setting left to change**. What remains is the OLED protective Screen
Saver, which Samsung documents as non-disableable.

### What the network sees: nothing

While the screen was covered **during an active cast**, every field stayed exactly as it was with the
picture visible: `CurrentTransportState PLAYING`, `RelTime 0:00:00`, `PowerState on`, mute `0`,
volume `0`, and no field of the port-8001 device dictionary changed. The same held with nothing
casting at 15:52. **cast-tv cannot detect the screen saver over the network**, so the UI must never
claim to know whether the picture is visible. Open question 3 of this document is answered: no.

### Run A - one still photo

- 16:00:08 cast started, 16:00:35 `PLAYING`. First blackout reported 16:03:50, but Piotr had been in
  the TV's menus just before, so that interval is not clean.
- **Clean measurement: a remote key at 16:04:27, dark again 124 s later.** Allowing for the seconds
  it takes to type, that is Samsung's documented **2 minutes**, counted from the key press.
- The key press **dismissed** the saver and **re-armed** it, exactly as the external sources said.
- **The cast survived intact**: Piotr's words, "wróciło zdjęcie" - the photo came back by itself, no
  re-cast needed. The saver covers the picture; it does not end the DLNA session.

### Run B - a slideshow, 20 photos at 8 s

First attempt did not run at all (`python -m castlib` from another directory: "No module named
castlib"); what was on screen then was still run A's photo, held by the TV after its server had gone.
The corrected run cast 100 slides.

- Key press 16:21:38. At 16:24:17, **159 s later and 18 slide changes later, the screen was dark**.
- Each slide is a fresh `SetAVTransportURI` + `Play`; the log shows the `TRANSITIONING` → `PLAYING`
  pair every 8 s throughout.

**This is the periodic-`Play` experiment, run at an 8-second interval, and it failed.** No DLNA
keepalive can work if a new URI and a new `Play` every 8 s do not hold the screen. The **NONE** verdict
in `frame.md` now rests on our own evidence, not only on the standard's silence.

### Run C - a moving film, 13 minutes

- Key press 16:28:23 with the film already playing.
- **16:31:02, 159 s later: the picture was there** ("Film"). **16:34:10, 347 s later - nearly six
  minutes - still there**, position advancing 9:11 / 12:57.

**A moving picture defeats the timer; a still one does not.** This overturns the reading this document
started from. The clause that fires on this set is Samsung's **"the same still image"**, not "no input
signal", and a slideshow counts as a succession of still images - eight seconds of a motionless frame
is evidently as still as eight minutes of one.

### The vendor extension, closed

`X_PlayerAppHint` was called with four combinations of `UpnpClass` and `PlayerHint`
(`object.item.imageItem.photo` / `object.item.videoItem` × `video` / `1` / `VideoPlayer`): **every one
answered `402 Invalid Args`**. Consistent with `X_GetServiceCapabilities` on RenderingControl naming
only `GetMute,SetMute`. The Samsung extensions are advertised in the SCPD and not usable. Lead closed.

### What this means for the change

1. **The problem is photos, not playback in general.** A film is safe; a slideshow is not; and a
   **paused** film is a still image, which explains the one long-playback row the archive has
   (row 7.5 held `PAUSED_PLAYBACK` for 65 minutes). That narrows any feature to "while a photo is on
   screen, or while a cast is paused".
2. **No setting, no DLNA path.** Both cheap outcomes are gone, on our own evidence.
3. **The only lever left is the remote channel**, and the measurement sets its terms: a key press
   buys **2 minutes**, so a keepalive means a real key every ~100 s for as long as photos are on
   screen, each with whatever the TV shows for that key. That is the honest cost; whether it is worth
   paying is Piotr's call, and the alternative is a README line saying a slideshow needs a nudge of
   the remote every two minutes.
4. **The film half of the report stays unconfirmed.** Asked whether that film had been paused, Piotr
   answered "Nie pamiętam" - he does not remember, and nothing is gained by inventing a reason. So the
   scope rests on what was measured today, **photos and paused casts**, and the film report is carried
   as unreproduced: a playing film survived six minutes here. No session should be spent chasing it;
   if the saver ever appears over a normally playing film, that observation gets written here and the
   scope is revisited.

### Corrections made during the run

Two claims of Claude's were wrong and were withdrawn on the spot: that the slideshow had been running
behind the saver from 16:07 (it had never started), and that the timer counts only remote input
regardless of content (run C shows video holds the screen). Both are recorded here so the numbers above
are read with the right history.

## Follow-up: the model's own manual settles it, 2026-09-20 evening

Piotr asked the obvious question - can the saver simply be switched off for photos? Claude
suggested the "Auto Protection Time" setting might be hiding in Panel Care. **That suggestion was
unfounded**, and the Polish manual for this model settles the matter without another trip to the TV.

- **Page 174**, under Energy Saving → Screen Saver, gives the general rule and then the exception
  for this series verbatim: "Jeśli telewizor wyświetla nieruchomy obraz przez dwie godziny lub
  dłużej, może zostać uaktywniony wygaszacz ekranu. … Jeśli telewizor wyświetla ten sam obraz przez
  2 minuty, Wygaszacz ekranu jest aktywowany automatycznie. **Wygaszacz ekranu nie można wyłączyć,
  aby zapewnić ochronę pikseli. (S8\*F/S9\*F)**" - if the TV shows a still image for two hours or
  more the saver may start; on S8\*F/S9\*F it starts after **2 minutes** and **cannot be disabled,
  to protect the pixels**.
- So this series has a threshold sixty times shorter than other models, and is the one that cannot
  turn it off. Our measurement - 124 s from a remote key - is that documented behaviour, not a fault.
- **Page 164**, Panel Care, lists exactly three items: Pixel Shift, Auto Logo Brightness, Pixel
  Refresh. **There is no screen-saver switch there.**
- "Auto Protection Time", which Samsung documents as switchable, belongs to other sets - The Frame
  among them - not to this series. Nothing needed photographing; the manual answers it.

This confirms the README sentence written before the check, which is now backed by the manual
rather than by inference from support pages.

### The one avenue this leaves, for the record

Samsung's `setScreenSaver(SCREEN_SAVER_OFF)` is offered to **apps running on the TV**, and Samsung
recommends it for photo slideshows specifically. A Tizen app of our own could call it. That is a
different project from cast-tv - a TV application, published or side-loaded, rather than a laptop
serving DLNA - and it would have to be verified on an S85F, since the manual's "cannot be disabled"
may or may not bind an app using that API. Recorded because it is the only path that addresses the
cause rather than dismissing the symptom; not proposed.
