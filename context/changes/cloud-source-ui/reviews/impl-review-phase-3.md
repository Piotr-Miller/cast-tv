<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cloud Source UI Implementation Plan

- **Plan**: context/changes/cloud-source-ui/plan.md
- **Scope**: Phase 3 of 7 (commit 57d012f)
- **Date**: 2026-09-10
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 9 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING (F2, F3) |
| Scope Discipline | WARNING (F4) |
| Safety & Quality | WARNING (F1, F5, F6, F7) |
| Architecture | PASS (1 observation, F10) |
| Pattern Consistency | WARNING (F8) |
| Success Criteria | WARNING (F9) |

## Success criteria

| Check | Result |
|---|---|
| 3.1 `.venv/bin/python -m pytest tests/` | PASS — 116 passed in 15.24s (Python 3.14.7) |
| `.venv/bin/python -m pyflakes castlib tests` | PASS — no output |
| 3.2 `python -m castlib ui --no-browser`, SIGINT after 12 s | PASS — printed `http://localhost:8895/ui/`, `http://192.168.50.198:8895/ui/`, the `firewall-cmd` hint, `TV: 83" OLED (192.168.50.142)`, then `Stopped.`; exit 0; port 8895 released |
| Vendored `alpine.min.js` | body after the header hashes to the stated sha256 `3ed1eed2…`; MIT notice present |
| 3.4, 3.6 manual | evidence in `research.md` (Follow-up 2026-09-10 — Phase 3: UPnP 701 and 716 observed on the Samsung) |
| 3.3, 3.5, 3.7 manual | ticked at 57d012f, no written evidence found (F9) |

All 22 named Phase 3 tests exist by exact name; `test_thumb_route_proxies_and_404s` is already present.

## Findings

### F1 — Stop during an in-flight cast is undone by the task

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/supervisor.py:112-150, castlib/app.py:388-403
- **Detail**: `Cast.run` checks `app.is_current(generation)` once (line 112), then spends up to two SOAP round-trips (the Samsung fetches a still inside `SetAVTransportURI`) before `app._promote(self)`. `App.stop()` bumps the generation and sends a raw `Stop` to the TV at once, but the task then sends `Play`, promotes itself and polls `playing`. Reproduced with `FakeTV(play_delay=0.4)`: actions `SetAVTransportURI, Stop, Play, GetPositionInfo…`, final state `playing`. The user's Stop is silently lost and the UI shows a live cast.
- **Fix**: After `Play` returns and before `_promote`, re-check `app.is_current(self.generation)`. If stale and `app.owner is None` (a stop, not a replacement), send `Stop` and `_finish("cancelled")`; if stale because a newer owner exists, `_finish("cancelled")` without `Stop`.
  - Strength: Closes the window with the generation counter the design already relies on; replacing still never sends `Stop`, so `test_replace_keeps_old_item` holds.
  - Tradeoff: One more lock read per cast; a stop that lands between the re-check and `_promote` still slips through (sub-millisecond).
  - Confidence: HIGH — the probe reproduced it against the real `App` and `FakeTV`.
  - Blind spot: A stop during `SetAVTransportURI` means the TV shows the item for a moment before the second `Stop`; acceptable.
- **Decision**: PENDING

### F2 — Prepared photo stays pinned when the task never registers it

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/supervisor.py:112-120, :256-257
- **Detail**: `_prepare` calls `photos.prepare(item)`, which pins the converted file. The stale-generation branch (`_finish("cancelled")`) and the no-TV branch (`_finish("failed", TVError("no_tv"))`) return before `_register()`. `_finish` only does `if self.item.id: registry.retire(...)`, so the registry's `on_remove → photos.release` hook never fires for an item with no id. Reproduced: `pinned=True` after the stale skip and still `True` after evicting the whole registry. Every superseded photo cast (a fast user ticking through a grid) and every cast attempted without a TV leaks retained bytes against the 256 MB budget for the life of the process. This is the ownership contract from the Phase 2 review (F2).
- **Fix**: In `_finish`, `if not self.item.id and self.item.prepared is not None: photos.release(self.item)`; add `test_supervisor.py::test_stale_task_releases_prepared_photo`.
- **Decision**: PENDING

### F3 — `prev` re-casts a retired item that can be evicted while on screen

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/supervisor.py:178-185, castlib/items.py:68-79, :96-121
- **Detail**: `Show.run` reuses the same `MediaItem` object for `prev`. Its previous `Cast` was `replace()`d, so `registry.retire` set `retired_at`, and nothing clears it: `_register` skips `add` when the item is still registered, and `Registry.add` does not reset `retired_at` if it was evicted meanwhile. `evict` removes anything with `retired_at` set, `in_flight == 0` and 60 s idle, so a photo held past 60 s after `prev` (the interval allows 600 s) or a paused video is evicted while on the TV, and `photos.release` unpins its file. Reproduced: after `next`, `prev`, `registry.evict(0.0)` returned the item in state `playing`. The Definitions table says the item being played is never evicted.
- **Fix**: Clear `retired_at` (and children's) whenever an item re-enters playback: `Registry.add` resets it, and `_register` calls a new `registry.revive(item.id)` when the item is already registered; test `test_registry.py::test_readd_clears_retired` and `test_supervisor.py::test_prev_item_is_not_evictable`.
- **Decision**: PENDING

### F4 — CLI files are listed and castable from the API as `session`

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Scope Discipline
- **Location**: castlib/app.py:446, castlib/sources/local.py:60-79, castlib/ui/index.html:163-190
- **Detail**: The plan says "A `local` source exists for CLI-registered items only; it is not listable from the API." `LocalSource.list` does raise, but `GET /api/status` carries `session: [...]` with every file given on the command line, with the absolute filesystem path as the item id, and `POST /api/cast {source: "local", id: <path>}` casts it (restricted to remembered paths). The UI renders a "From the command line" section. This is not folder browsing, so no "What We're NOT Doing" rule is broken, and it is what made manual row 3.5 (cast from the UI while a CLI cast plays) possible before any source exists. It is still a new UI surface and an API exposure the plan decided the opposite of, and it shows host paths to any LAN device that passes the Host check.
- **Fix A ⭐ Recommended**: Keep it and document it as a plan addendum; change the `session` ids to opaque tokens (the registry already mints them) so no filesystem path leaves the process.
  - Strength: Preserves the only way to drive a cast from the UI before Phase 4 and keeps row 3.5 reproducible; the id change is small and matches the `media URL` definition's "paths are exact-match lookups on opaque ids".
  - Tradeoff: The plan's "not listable" sentence becomes "listable, not browsable"; Phase 4's `Entry` shape inherits a `local` source.
  - Confidence: HIGH — `LocalSource.remember` already owns the path→entry map, so an opaque key is a local change.
  - Blind spot: Whether the user wants CLI files visible on the phone at all.
- **Fix B**: Remove `session` from `/api/status` and the UI section; keep `LocalSource` for `resolve` of CLI casts only.
  - Strength: Matches the plan text literally; nothing about the host leaves the process.
  - Tradeoff: Until Phase 4 there is nothing to cast from the UI, so row 3.5 can only be re-verified after GoPro lands.
  - Confidence: MEDIUM — `index.html` and `app.js` reference `session`; removal is mechanical but touches three files.
  - Blind spot: Not checked whether any test asserts on `session`.
- **Decision**: PENDING

### F5 — Thumb proxy replays the upstream Content-Type on a same-origin URL

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/api.py:241-258
- **Detail**: `ctype = resp.headers.get("Content-Type") …; send_header("Content-Type", ctype)`. A source, captive portal or stale URL answering 200 `text/html` makes `/api/sources/<n>/thumb/<id>` a same-origin HTML document; opened as a navigation it runs in the UI's origin and passes the Origin/Host check for every mutation. No source is wired yet, so nothing is exploitable in this commit, but Phases 4–6 route arbitrary cloud responses through exactly this path.
- **Fix**: Accept only `image/*` (else 502 `thumb_not_image`) and add `X-Content-Type-Options: nosniff` to the response; extend `test_thumb_route_proxies_and_404s` with an HTML upstream.
- **Decision**: PENDING

### F6 — Re-discovery overwrites the saved TV choice

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/app.py:283-285, :300-306
- **Detail**: `pick = next((t for t in tvs if t["ip"] == preferred), tvs[0]); self._use_tv(...)` persists by default. If the saved TV is off and the user presses "Search again", the first other renderer becomes selected and `settings["tv"]` is rewritten to it; the explicit choice is gone after restart. The plan makes "first discovered" the default, not a replacement for a saved selection.
- **Fix**: `_use_tv(..., persist=(pick["ip"] == preferred or self.settings.get("tv") is None))`; test `test_discovery.py::test_rediscovery_keeps_saved_tv`.
- **Decision**: PENDING

### F7 — API input hardening: TV address, show size, connect kwargs, double unquote

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/app.py:288-301, castlib/api.py:125-132, :196, :210
- **Detail**: Four small boundary gaps, all behind the Origin/Host check so none is remotely exploitable: (a) `select_tv` only strips the string; `{"ip": "example.com/x?"}` makes the server GET `http://example.com/x?:9197/dmr` on four ports and, on a matching XML answer, writes that host to `settings.json`; (b) `/api/show` resolves an unbounded list synchronously on the handler thread — ~30 k entries fit in the 1 MiB body, and from Phase 4 each `resolve` is an upstream call; (c) `src.connect(**body)` with a body key `"self"` raises `TypeError` → 500 with a traceback; (d) `_thumb(handler, src, unquote(rest))` decodes a path the dispatcher already unquoted, mangling ids containing `%25`.
- **Fix**: `ipaddress.ip_address(ip)` (or a strict hostname regex) in `select_tv` → `ConfigError("bad_ip")`; `MAX_SHOW_ITEMS = 500` check in `/api/show`; pass the body as one dict to `connect(params)`; drop the second `unquote`.
- **Decision**: PENDING

### F8 — Settings persistence bypasses the config helpers

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: castlib/app.py:93-104
- **Detail**: `Settings.set` reimplements temp-file-then-`os.replace` inline and swallows `OSError` without unlinking the temp file, so a failed `json.dump` or `replace` leaves `~/.config/cast-tv/settings.XXXXXX` files behind. `config.cache_write` (the sibling) unlinks on failure and is where the plan says config writes live ("Config writes go through castlib/config.py helpers").
- **Fix**: Add `config.config_write(name, data)` next to `cache_write` (same temp-then-rename with cleanup, utf-8) and call it from `Settings.set`.
- **Decision**: PENDING

### F9 — Manual rows 3.3, 3.5 and 3.7 are ticked without written evidence

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/cloud-source-ui/plan.md:1181-1185, research.md (Follow-up 2026-09-10 — Phase 3)
- **Detail**: The research note records rows 3.4 and 3.6 (the 701 and 716 faults were "seen during manual rows 3.4 and 3.6"). Nothing records the phone opening the UI (3.3), stop/replace from the UI with no 404 in `--debug` (3.5), or the unplugged TV showing unreachable and retry recovering (3.7). The Phase 1 review (F7) raised the same gap and it was fixed by a verification note; this is the second occurrence, which makes it a candidate for `lessons.md`.
- **Fix**: Append a short table to the Phase 3 follow-up in `research.md` (row, material, observed) for 3.3, 3.5 and 3.7, or untick the rows that were not actually exercised.
- **Decision**: PENDING

### F10 — UI: Google Fonts fetched at runtime, poll loop without overlap guard, error badge stuck at 50

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: castlib/ui/index.html:8-9, castlib/ui/app.js:75-89
- **Detail**: (a) The LAN UI preconnects to and loads Archivo and IBM Plex Mono from `fonts.googleapis.com` on every page open, the only external runtime dependency in an otherwise self-contained design (Alpine is vendored). (b) `setInterval(refresh, 1500)` has no in-flight guard, so a slow `/api/status` lets an older answer overwrite a newer one, and it keeps polling at full rate while `offline`. (c) Errors are reloaded only when `s.errors !== this.errors.length`; `ErrorRing.__len__` caps at 50, so once the ring is full new errors no longer refresh the closed-panel badge and list.
- **Fix**: Vendor the two faces (or use a system stack); add an `_inflight` flag and a slower interval while offline; have `/api/status` report a monotonically increasing error sequence number instead of the count.
- **Decision**: PENDING

## Noted, not raised

- `cli.py:313-314` special-cases the literal argument `ui` (`python -m castlib ui`) unless a file named `ui` exists in the cwd; a `--ui` flag would be less magical. Works, untested.
- `cli.py:135-137` `c.sent.wait()` sits outside the `KeyboardInterrupt` handler, so Ctrl+C during conversion or `SetAVTransportURI` exits 130 without `Stopped.`; same shape as the pre-Phase-3 script, not a regression.
- `tests/test_discovery.py` imports `_json` from `tests/test_api.py`; the helper belongs in `conftest.py`.
- `ThreadPoolExecutor` workers are joined by an atexit hook, so a Ctrl+C while the worker is inside a 60 s photo fetch delays exit; not verified at runtime.
- Pulled forward from later phases, justified and minimal: `platform.py` (firewall hint, no-op stay-awake), `sources/base.py` (the `Source` protocol the delegated routes need), `diagnostics.py` (lifted from `cli.py` so the supervisor gets values, not prints), `pyproject.toml` package data for `ui/*`.

## Verified clean

Every `/api` and `/ui` answer carries an exact `Content-Length` and nothing new calls `send_error`; `/ui` is an exact-match map on the unquoted path (traversal, `%2e%2e`, case and trailing slash all 404); bodies are bounded at 1 MiB; every SOAP, upstream and subprocess call has a timeout; `App.lock` is held only for field swaps and no network call runs under it; there are no joins, so `close()` from a handler thread cannot deadlock; previous casts are replaced and never removed from the registry; the CLI keeps `cast-tv film.mkv`, `--stop`, `--list`, `-s`, `--debug`, `-c` behaviour including retire-in-finally and the restored keep-alive timeout from the Phase 1 review; `RelTime` passes through unparsed; the UI uses `x-text` everywhere (no `x-html`/`innerHTML`) and POSTs every mutation with a JSON body.
