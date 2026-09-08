---
change_id: cloud-source-ui
title: Pick media from GoPro, Google Photos and OneDrive in a UI, and cast it
status: new
created: 2026-09-07
updated: 2026-09-08
archived_at: null
---

## Notes

A UI for this tool: browse media from GoPro, Google Photos and OneDrive - separate
tabs are fine - and cast a selection to the Samsung TV.

Originally stated as: "UI do tej apki, ładowane pliki z GoPro, Google Photos
i OneDrive (mogą być osobne taby) i później ich castowanie na TV Samsunga."

The three sources are not alike, and that asymmetry is the whole shape of this change:

- **GoPro** is the only one that browses without ceremony. `api.gopro.com/media/search`
  returns the library, so a tab can list it. It needs a bearer token lifted from a
  logged-in browser, and that token expires after a few hours - the UI has to make
  that visible rather than failing with a bare 401.
- **Google Photos** cannot be browsed at all. The Library API has only exposed
  user-picked items since 31 March 2025, so the entry point is a link to one item.
  A tab here is a paste field plus a history of what has been pasted, not a grid.
- **OneDrive** browses over Microsoft Graph, behind a real login.

Casting itself is solved and verified against the TV; this change is only about
choosing what to cast, and about the three things that turned out to hang off that.

## Scope, as it grew

Four follow-ups after the first draft, each of which moved the design:

1. **OneDrive logs in over the network**, rather than reading the local mirror.
2. **Photos are cast as well as video** - which reaches deeper into `cast-tv` than
   any of the source work.
3. **Linux and Windows both**, not Fedora alone.
4. **Every tab gates on its own connection**: enter the tab, connect, then the list.

## Decisions

### UI and stack

A **local web UI served by the process that already runs the HTTP server**, not a
desktop app.

- The process already lives for the whole session and already holds a
  `ThreadingTCPServer` (`cast-tv:286`). The UI is more routes on it: one process,
  one port, no IPC, no second copy of the state.
- The server already binds on the LAN, because the TV must reach it. So the UI is
  reachable from a phone for free - pick the material on the couch, it plays on the
  TV. No desktop toolkit gives that.
- It is the only option that does not need a per-platform build. This was chosen
  before the cross-platform requirement arrived and survived it unchanged; GTK or
  Tauri would have made Windows a second project.

| Layer | Choice |
| --- | --- |
| Backend | `http.server`, extended with `/api/*` and `/ui/*` on the existing handler |
| Frontend | one `index.html`, ES modules, CSS - no build step |
| Reactivity | Alpine.js, ~15 KB, vendored into the repo rather than pulled from a CDN |
| Transport state | poll `GetTransportInfo` every 1-2 s |
| Structure | split into `castlib/{discovery,server,sources/{gopro,photos,onedrive}}.py` |
| Tests | `pytest` over the resolvers, DIDL, MIME and config paths |

Not FastAPI, not a frontend framework, not Node. Revisit FastAPI only if background
job queues or WebSockets turn up; OAuth alone does not justify it (below).

**Core data model: `MediaItem` carries a type** (`video` / `photo`). That type decides
`upnp:class`, MIME, DLNA flags, whether `ffprobe` runs at all, and whether the item can
join a slideshow. It is the common denominator of the three sources and the first thing
to settle in `castlib/`.

### OneDrive over Microsoft Graph

**Device code flow**, not auth code + PKCE. Entra ID only accepts `http://localhost`
redirect URIs for public clients, never an arbitrary http:// LAN address - so a login
started from the phone would break on the redirect. Device code has no redirect URI at
all, works the same from laptop and phone, and the CLI can reuse it verbatim.

- Scopes `Files.Read offline_access` (plus `User.Read` to show which account is
  connected); tenant `consumers`.
- **This does not require FastAPI.** There is no callback to serve: a POST to
  `/devicecode` and a polling loop, about 40 lines of stdlib.
- **No SDK.** The docs demonstrate `azure-identity` + `msgraph`; that dependency tree
  costs more than the raw flow.
- Refresh token is good for ~90 days rolling - refresh silently on 401, store under
  `castcloud.CONFIG` with mode 0600. Strictly better than GoPro's few-hour token.
- `@microsoft.graph.downloadUrl` is pre-authenticated and honours `Range`, so it feeds
  the existing relay directly. **It expires after ~1 h: resolve on demand, never cache**,
  or a seek an hour into a film hits a dead URL.
- `$expand=thumbnails` for the grid; the `video` facet carries bitrate and dimensions and
  the `photo` facet capture data - so the "the TV will refuse this" check runs without
  `ffprobe` and without fetching a byte.

The local mirror at `~/.onedrive-sync` is **dropped as a source**. On Windows the sync
root is `%USERPROFILE%\OneDrive` and Files On-Demand leaves 0-byte placeholders that look
like files. Serving from disk when a file happens to be local stays available as a later
optimisation, not as the design.

### Photos, not just video

Casting a photo does not work today. Four places:

| Where | Today | Needed |
| --- | --- | --- |
| `cast-tv:19` `MIME` | no image types at all | `.jpg/.png/.heic/.webp` |
| `cast-tv:302` | unknown extension falls back to `video/mpeg` | type from the real extension |
| `cast-tv:311` | `upnp:class` hardcoded `object.item.videoItem` | `object.item.imageItem.photo` |
| `cast-tv:24` `DLNA_FEATURES` | `OP=01` and video streaming flags | image flags / `JPEG_LRG` - verify against the TV |
| `castcloud.py:54` `is_video()` | rejects everything but video | `is_media()`, returning a type rather than a bool |

Two of these are features rather than repairs:

- **Slideshow.** A photo has no duration; the TV holds it until told otherwise, and DLNA
  offers no playlist here. The laptop drives the show: a queue plus `SetAVTransportURI`
  every N seconds. This changes the UI model from "pick one file" to "pick a set", and it
  is what makes photos worth putting on an 83" screen at all.
- **HEIC.** Phone photos in OneDrive and Google Photos will be HEIC and the TV will not
  decode it. Convert in the relay (Pillow + `pillow-heif`), not by shelling out -
  `heif-convert` barely exists on Windows. This is the photo analogue of the DTS warning,
  except it is fixable rather than merely reportable.

**To verify:** `cast-photos` ranks video variants (`=dv`, `=m37`, …, `cast-photos:20`).
Google serves photos under different suffixes (`=d` for the original, `=w…-h…` for
scaled). Confirm against a live link the way `=dv` was confirmed.

### A connection gate on every tab

Entering a tab shows its connection state first, and the list second. The shape is the
same in all three; what sits inside the gate is not:

- **OneDrive** - a real login. Device code, then the list.
- **GoPro** - no public OAuth exists. The gate holds the token paste with instructions
  and an expiry countdown. It looks like a login step; it is not one.
- **Google Photos** - a login would buy nothing, because the library cannot be listed
  even when authenticated. The gate is the paste field.

**A literal "web wrapper" for GoPro is not possible in a browser.** Embedding GoPro's
login page in an iframe is blocked by `X-Frame-Options`, and same-origin policy would
prevent reading the session even if it were not. It would require a desktop app with an
embedded webview - which costs separate Linux and Windows builds and gives up phone
access. Rejected; revisit only if pasting a token proves genuinely painful in use.

### Linux and Windows

`pipx install` replaces the symlink. `pyproject.toml` with `[project.scripts]` mapping
`cast-tv` / `cast-gopro` / `cast-photos` into `castlib`; on Windows pipx generates
`cast-tv.exe`, so extensionless files with a shebang stop being a problem. This retires
`castcloud.cast_tv_path()` (`castcloud.py:94`) and the `subprocess.call` hop between
commands (`castcloud.py:113`) - it becomes a function call. PyInstaller stays available
as a second channel for people without Python, not as the primary one.

What actually breaks, in order of how much it will hurt:

1. **SSDP discovery across interfaces** (`cast-tv:31-37`). The socket is not pinned to an
   interface. A typical Windows box has several - Wi-Fi, Ethernet, Hyper-V, WSL, VPN - so
   M-SEARCH leaves through the wrong one and discovery silently finds nothing. Enumerate
   interfaces and send from each (`IP_MULTICAST_IF`). Also set `SO_REUSEADDR`
   conditionally: its UDP semantics differ from Linux's.
2. **The firewall.** The TV connects *inbound* to 8895. Windows Firewall prompts on first
   bind, or blocks silently when the network is classed Public; firewalld does the same on
   Fedora. Document `netsh advfirewall` / `firewall-cmd`, and extend `explain_failure()`
   (`cast-tv:319`) with the "the TV fetched zero bytes" case - the function exists exactly
   so this is not guesswork.
3. Config paths: `%APPDATA%` rather than `~/.config` (`castcloud.py:18-19`).
4. Explicit `encoding="utf-8"` on every `open()` (`cast-gopro:39,52`,
   `castcloud.py:120,126`) - Polish filenames on a legacy console otherwise.
5. Staying awake becomes two shims: `systemd-inhibit` and `SetThreadExecutionState`
   via `ctypes`. Not cosmetic during a slideshow.

`local_ip()` (`cast-tv:291`) is fine as it stands - the UDP-connect trick picks the
address on the right route on both systems.

CI: GitHub Actions matrix over `ubuntu-latest` and `windows-latest`. No TV in CI, so test
the pure parts - resolvers, DIDL, MIME, config paths - which is where this class of bug
lives anyway.

### Launching it

```
cast-tv                   # no arguments -> the UI (argparse only errors here today)
cast-tv film.mkv          # CLI unchanged
python -m castlib ui      # from a checkout, during development
```

Starting the UI brings up 8895 (media, `/ui` and `/api` on one port), calls
`webbrowser.open()`, and prints both addresses - `localhost` and the LAN one for the
phone, plus the discovered TV. Three things to handle at startup: a port already in use
should attach to the running instance rather than dying on `EADDRINUSE`; the firewall hint
belongs here rather than after the TV goes quiet; and the process staying in the
foreground is a consequence of streaming rather than copying, so say so. Running it as a
background service (`systemd --user`, Task Scheduler) is deliberately deferred - a
permanently held port and constant SSDP churn buy nothing until the thing is used daily.

## Dependency bill

The "single file, standard library only" promise does not survive this change. Honestly:

- `pillow` + `pillow-heif` - HEIC conversion. Not optional; without it the OneDrive tab
  shows black frames.
- `ifaddr` - multi-interface discovery.
- `platformdirs` - config paths. The one that could be hand-rolled in ten lines.

Still no Node, no frontend framework, no FastAPI. `ffprobe` / `ffmpeg` stay optional and
degrade gracefully - a manual download on Windows, and Graph facets cover the OneDrive
pre-check without them.

## Design

Mockups, clickable: https://claude.ai/code/artifact/0673495b-4537-4e06-9f72-5ae5511d14fa

Five artboards - the app (gate -> list, grid, cast bar), the slideshow, the phone view,
the three gates side by side, and the diagnostic states. Dark, media-first; Archivo and
IBM Plex Mono. Two decisions embedded there worth flagging: photo selection **persists
across tabs**, so a slideshow queue can mix GoPro and OneDrive, and `GX010042.MP4` is
labelled `3840 x 3360`, the frame the README actually recorded at 119 Mbit/s.

## Open

- DLNA image flags and profile against this particular Samsung - untested.
- Google Photos suffixes for stills.
- Whether the LAN-exposed UI needs a token in the URL. It is a home network, but the tab
  does list a cloud library to anyone who can reach port 8895.
