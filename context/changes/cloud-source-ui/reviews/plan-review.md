<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Cloud Source UI

- **Plan**: context/changes/cloud-source-ui/plan.md
- **Mode**: Deep
- **Date**: 2026-09-09
- **Verdict**: RETHINK → SOUND after triage (all 8 findings fixed in plan, 2026-09-09)
- **Findings**: 3 critical, 5 warnings, 0 observations

Before implementation, the identity of photos picked again and the control of a show when playback is replaced have to be settled. Triage 2026-09-09: all eight findings carried into the plan (F2 and F5 in a version refined by the author). Line numbers refer to the version reviewed on 2026-09-09.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Requirement Definition | FAIL |
| End-State Alignment | FAIL |
| Lean Execution | PASS |
| Architectural Fitness | FAIL |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

## Grounding

5/5 existing paths ✓ (`cast-tv`, `cast-gopro`, `cast-photos`, `castcloud.py`, `README.md`), 5/5 symbols ✓, brief↔plan ✓. The new `castlib/` files are planned deliberately. `Progress`: the names of all 7 phases match, 38 matching criteria, no checkboxes outside the section. Definitions: 15 rows; the unresolved cases are described by F1–F2. Checked: the four scripts, the call sites of the functions being changed, and an independent review of edge cases by one subagent. No implementation tests or hardware trials were run.

## Findings

### F1 — Picking a photo again has no merge rule

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — a significant decision; needs thought
- **Dimension**: Requirement Definition
- **Location**: Definitions (`plan.md:74`, `:82`), MediaItem (`:263`), Phase 6 (`:852–863`)
- **Detail**: The plan declares `(source, source_id)` unique, but successive Picker sessions append entries. Google keeps the ID of the same item across sessions. After a photo is picked in S1 and in S2 and S1 then expires, the plan does not say whether the photo stays available through S2 or gets a "re-pick". ID stability is confirmed by the [PickedMediaItem documentation](https://developers.google.com/photos/picker/reference/rest/v1/mediaItems).
- **Fix**: Settle on one entry per ID, keeping the selection order, refreshed through the current valid session.
  - Strength: Removes duplicates and needless re-picking of photos.
  - Tradeoff: Requires explicit management of the links to sessions.
  - Confidence: HIGH — the documentation confirms ID stability.
  - Blind spot: The user's preference about repeats in the queue.
- **Decision**: FIXED — one entry per ID, refreshed through a valid session, re-pick when none is valid (Definitions `pick`, Phase 6 §2, `test_repick_merges_by_media_id`)

### F2 — An old show can hang or take over new playback

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — an architectural decision; needs careful consideration
- **Dimension**: Architectural Fitness
- **Location**: Phase 3 — Cast and Show (`plan.md:530–541`, `:558`), Definitions (`:75`, `:85`)
- **Detail**: A replaced `Cast` gets `replaced`, but the show waits only for `stopped` or `failed`. During a video it can therefore wait forever. During a photo the old show can wake up after the interval and replace material started by hand. There is also no rule for stopping the previous `Show`. "Last SOAP wins" describes the outcome of a race, not an unambiguous order of commands. In addition, according to Definitions a single photo lasts until Stop, while the loop description ends it after the interval. The current code has one synchronous owner of playback (`cast-tv:473–510`); it offers no pattern that settles these cases. The finding also covers the missing decisions under Requirement Definition.
- **Fix**: Define one owner of playback; a manual cast and a new show cancel the previous show. Serialise `SetURI + Play`, also end the wait on cancellation, and describe the single photo separately.
  - Strength: Unambiguous TV and UI state under concurrent control.
  - Tradeoff: Concurrency and cancellation tests are needed.
  - Confidence: HIGH — the contradiction follows directly from the state contract.
  - Blind spot: When the interval countdown starts during a slow conversion.
- **Decision**: FIXED — differently from the proposal: one owner plus a `generation` checked after the material is prepared and before commands, a single-threaded executor ordering requests (instead of a lock alone), an interruptible wait of the Show on `replaced`/`cancelled` (250 ms is the loop's reaction time; the network has its own timeouts), the interval counted from a successful `Play`; a single photo in a show holds until Stop (Critical Implementation Details, Phase 3 §2 and §6, Definitions `slideshow` and `cast (while playing)`)

### F3 — Eviction can remove the material being played

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — a significant decision; needs thought
- **Dimension**: Blind Spots
- **Location**: Phase 1 — Registry (`plan.md:268–275`), Phase 5 manual verification (`:804–806`)
- **Detail**: `evict(idle_seconds)` goes by the time of the last request. There is no protection for the current cast, transfers in progress, or subtitles. After 60 seconds of pause an entry can disappear, so the resume after an hour required in Phase 5 ends in a local 404 before the resolver refreshes the URL. The decision in Definitions concerns the previous cast, but the Registry contract describes general removal after inactivity. The current code keeps file routes for the life of the process (`cast-tv:108–112`, `:451–460`).
- **Fix**: Protect the active cast, its subtitles and open transfers; after a period of inactivity remove only entries retired from playback.
  - Strength: Keeps resume and late subtitle fetches possible.
  - Tradeoff: The Registry needs to know about owners and active requests.
  - Confidence: HIGH — the current contract does not tell active entries from retired ones.
  - Blind spot: The behaviour of Samsung's buffer needs a hardware test.
- **Decision**: FIXED — `retire(id)` from the supervisor, `evict()` only for retired entries with no transfers in progress, subtitles share the video's fate (Phase 1 §3 and §10, Definitions `cast (while playing)`)

### F4 — The listing gives no thumbnail address

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — a significant decision; needs thought
- **Dimension**: Plan Completeness
- **Location**: Routing (`plan.md:299–301`), API (`:557`), Source (`:650–661`)
- **Detail**: The only thumbnail route needs an ID from the Registry: `/m/<token>/<id>/thumb`. `Entry` returns the source ID and `thumb: bool`, and registration happens only when casting. So the grid gets no addressable thumbnail before the material is started.
- **Fix**: Add a protected thumbnail route by `(source, source_id)` and return its URL in `Entry`.
  - Strength: Uses the existing `Source.thumb()` without registering the whole library.
  - Tradeoff: The route's response and error contract has to be written.
  - Confidence: HIGH — a gap between listing and routing.
  - Blind spot: Refreshing expired thumbnail URLs.
- **Decision**: FIXED — route `GET /api/sources/<name>/thumb/<source_id>` behind Origin/Host, `Entry.thumb: str | None`, `/m/.../thumb` removed (Phase 1 §5, Phase 3 §3 and §6, Phase 4 §1)

### F5 — Photo conversion happens too late for DIDL

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — a significant decision; needs thought
- **Dimension**: End-State Alignment
- **Location**: Phase 2 — Serving photos (`plan.md:449–455`), profiles and conversion (`:423–447`)
- **Detail**: The plan calls `prepare()` on the TV's HTTP request. But DIDL reaches the TV earlier, in `SetAVTransportURI` — that is how the current code works (`cast-tv:473–475`). A HEIC can be announced as HEIC and delivered as JPEG. A PNG kept as is also gets the common `JPEG_LRG` profile. Preparing and publishing the resulting MIME, size and dimensions before SOAP is missing.
- **Fix**: Prepare the photo before SOAP and build both the DIDL and the HTTP response from the same `Prepared` data; choose the profile from the resulting MIME.
  - Strength: Consistent MIME, size and dimensions along the whole path.
  - Tradeoff: Starting a photo waits for the conversion.
  - Confidence: HIGH — the order of operations is visible in the code.
  - Blind spot: The accepted image profiles still need the Samsung.
- **Decision**: FIXED — differently from the proposal: `Prepared` as a separate object (the source fields of `MediaItem` stay), the profile from the resulting MIME and dimensions (`photo_profile`), the route published only after a successful preparation and generation check, HTTP does not convert, a conversion error ends the task before SOAP (Phase 1 §3, Phase 2 §2–§4 and §6, Definitions `kind → wire`)

### F6 — The source mapping does not carry out the rules for photos

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — a significant decision; needs thought
- **Dimension**: End-State Alignment
- **Location**: Phase 4 (`plan.md:674–681`), Phase 5 (`:770–772`)
- **Detail**: GoPro is to handle photos through the existing `library_url()`, which rejects image variants (`cast-gopro:119–122`) and checks them with `is_video()` (`:137`; `castcloud.py:75–80`). A photo download path based on a verified API response is missing; the `files` fallback does not guarantee handling of an image-only variant. OneDrive, on the other hand, accepts any `image/*`, so it lets `image/gif` through as well, despite GIFs being explicitly excluded.
- **Fix**: Add GoPro photo resolution based on real fixtures, and a common filter of allowed formats before an `Entry` is created.
  - Strength: The listing matches the declared scope of supported media.
  - Tradeoff: A probe of a GoPro photo is needed, not only of its thumbnail.
  - Confidence: HIGH — both problems follow from specific conditions.
  - Blind spot: The actual download format of burst/livephoto remains unverified.
- **Decision**: FIXED — a second GoPro probe (download of a photo/burst/livephoto) and `photo_url()` with a ranking of image variants; a common `is_allowed_photo()` in `media.py` used by GoPro, OneDrive and the Picker; an `image/gif` case in `test_kind_from_facets` (Phase 2 §2 and §6, Phase 4 §2 and §5, Phase 5 §2, Phase 6 §2, Definitions `media`)

### F7 — The photo cache contradicts the promise of temporary storage

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — a quick decision; the fix is obvious and local
- **Dimension**: Blind Spots
- **Location**: Phase 2 — Photo pipeline (`plan.md:440–443`), scope (`:132–133`), Phase 7 paths (`:934–936`)
- **Detail**: The plan promises a cache in a temporary directory but points to `cache_dir()/photos`. `cache_dir()` currently means `~/.cache/cast-tv` (`castcloud.py:18`), and in Phase 7 `user_cache_dir()`. Removing the photos when the process ends is not described.
- **Fix**: Use a separate per-process temporary directory with cleanup; keep the persistent metadata cache apart.
- **Decision**: FIXED — `tempfile.mkdtemp` per process, removed in `atexit` and on Ctrl+C, `cache_dir()` for metadata only, `photo_tmp_dir()` in `config.py`, `test_tmp_dir_removed_at_exit` (Phase 1 §8, Phase 2 §3 and §6)

### F8 — The manual replacement test comes before the functionality it needs

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — a quick decision; the fix is obvious and local
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — Manual Verification (`plan.md:389–390`)
- **Detail**: Phase 1 requires starting a second cast while the first is running. A second CLI call on the same port currently ends in a bind error (`cast-tv:462–466`). A Registry inside the process does not change that, and controlling several casts arrives only in Phase 3.
- **Fix**: In Phase 1, check two entries in one server with an integration test; leave manual replacement of playback to Phase 3.
- **Decision**: FIXED — item 1.5 replaced by automated 1.4 (`test_second_item_does_not_replace_first` on two entries in one server); manual replacement stays in 3.5 (Phase 1 Success Criteria, Progress)
