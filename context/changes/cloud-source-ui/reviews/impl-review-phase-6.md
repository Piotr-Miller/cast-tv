<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cloud Source UI Implementation Plan

- **Plan**: context/changes/cloud-source-ui/plan.md
- **Scope**: Phase 6 of 7
- **Date**: 2026-09-13
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Share-link API permits blind SSRF

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/gphotos.py:627
- **Detail**: `link()` accepts any `http://` or `https://` URL and passes it to `sharelink.resolve()`, which performs a server-side GET and follows redirects. A LAN client can therefore make the cast-tv host request loopback, link-local, or private-network services. The body is not returned directly, limiting exfiltration, but service probing, state-changing GETs, and access to local-only HTTP surfaces remain possible.
- **Fix**: Require HTTPS Google Photos/share hosts at the input boundary and validate every redirect hop against an allowlist plus non-loopback/non-private address policy.
  - Strength: Removes the SSRF class while retaining the documented Google Photos share-link workflow.
  - Tradeoff: The complete set of legitimate Google redirect hosts must be established and maintained.
  - Confidence: HIGH — the endpoint is explicitly for Google Photos links, not arbitrary URL fetching.
  - Blind spot: The live redirect chain has not been catalogued across public and private Google share links.
- **Decision**: FIXED (Fix now, scope refined in triage) — `sharelink.allowed()`: https, port absent/443, no username/password (an `@` in path/query stays legal), exact hosts `photos.app.goo.gl`, `goo.gl`, `photos.google.com`, `photos.fife.usercontent.google.com`, plus subdomains of `googleusercontent.com` and `googlevideo.com` (boundary match). `_GooglePhotosOnly` checks every hop before it is sent; a hop to `accounts.google.com` raises `login_required` without fetching the page. `resolve(link, cookies_path)` builds the guarded opener itself, so the page, probes, re-resolve (`again()`) and the relay (link `Upstream.opener`) all go through it; `net.fetch` now re-raises `CastError`. Tests drive `resolve()` through a scripted urllib transport (no network) and assert refused targets are never requested. The general `cast-tv <url>` CLI relay is deliberately out of scope (local operator input).

### F2 — Bearer token survives scheme and port changes

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/net.py:31
- **Detail**: `BEARER_SAFE` strips `Authorization` only when the hostname changes. A redirect from HTTPS to HTTP on the same hostname, or to another port on that hostname, still receives the OAuth bearer. The current test covers only same-host versus different-host redirects and therefore blesses a boundary broader than the URL origin.
- **Fix**: Preserve `Authorization` only when scheme, hostname, and effective port are unchanged; always strip it on a TLS downgrade, with downgrade and cross-port tests.
- **Decision**: FIXED (Fix now) — `_DropAuthAcrossOrigins` keeps `Authorization` only for the same (scheme, host, effective port); an unreadable port counts as another origin. `test_bearer_stays_on_its_origin` covers same origin, explicit :443 + host case, TLS downgrade, other port, other host, invalid port.

### F3 — Original-video downloads can exhaust disk and survive crashes

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Safety & Quality
- **Location**: castlib/downloads.py:73
- **Detail**: The advertised 4 GiB cache bound applies only to evictable entries; an active pinned download can exceed it. A response with a missing or false `Content-Length` has no byte cap or ongoing free-space check, and even a known large length is accepted while leaving only 256 MiB. Because originals are the default and Picker supplies no size, one cast can consume nearly the filesystem. An abnormal termination can also leave `cast-tv-videos-*` directories under persistent `/var/tmp`, while README.md:58 still says cloud items are not downloaded.
- **Fix A ⭐ Recommended**: Keep Original as the default, but add a configurable hard size limit, enforce the free-space margin during transfer, translate write failures into a user-facing cast error, sweep safely identifiable stale temp directories at startup, and document disk use.
  - Strength: Preserves the explicit Phase 6 product decision while bounding resource use and cleaning abnormal-exit residue.
  - Tradeoff: Originals above the configured limit are refused even when the machine technically has enough space.
  - Confidence: HIGH — it directly closes the missing-length, lying-length, write-failure, and stale-directory cases.
  - Blind spot: The right default maximum has not been chosen from the owner's real library sizes.
- **Fix B**: Make the ranged 1080p stream the default and require an explicit Original choice, while still enforcing progressive free-space checks and stale-directory cleanup for Original.
  - Strength: Avoids multi-gigabyte writes on the common path and starts playback faster.
  - Tradeoff: Reverses the owner's recorded Phase 6 preference for Original by default and reduces default quality.
  - Confidence: MEDIUM — it reduces exposure substantially, but explicit Original casts still need the safety controls.
  - Blind spot: The 1080p variant's availability and quality have only been exercised for the sampled Google video.
- **Decision**: FIXED (Fix A, with triage refinements) — Original stays the default; no automatic downgrade. Measured on the download directory's filesystem: one file ≤ `CAST_TV_DOWNLOAD_MAX_GB` GiB (default min(16 GiB, 25 %)), all downloads together (held + cached + in flight; `_lock` keeps one in flight) ≤ 25 %, and no write that would leave free − chunk below max(1 GiB, 5 %); the env limit lifts neither budget nor reserve. All checked before every (unbuffered) write, so a missing or false `Content-Length` changes nothing; a known length is refused before a file exists; more bytes than announced → `download_long`. Short of room, unpinned cached downloads are dropped first (`_Cache.drop_unpinned`). `too_large`/`download_budget`/`no_space` carry a hint to cast the "1080p stream" variant; ENOSPC/EDQUOT on write → `no_space`, other write errors → `download_write_failed`; partial files are always removed. Video dirs are named `cast-tv-videos-<pid>-*`; `config.sweep_stale_video_dirs()` at `App` start removes only this user's dirs (not symlinks) whose pid is dead (POSIX only — Windows deferred to Phase 7; pid-less legacy dirs are kept). README documents disk use, limits and the reserve as a stop threshold. 7 new tests; 232 passed.

### F4 — Resource creation races disconnect and shutdown cleanup

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Architecture
- **Location**: castlib/sources/gphotos.py:278
- **Detail**: `_start_flow()` opens the loopback listener before publishing the flow and capturing its generation, so a concurrent disconnect can finish first and the older connect can then publish a live flow. `pick()` detects a generation change after creating a remote Picker session but raises without deleting that untracked session. Conversely, disconnect increments the generation only after sequential remote DELETE calls; offline cleanup may block for up to 30 seconds per session and leaves a broad race window. The happy-path cleanup tests do not exercise these interleavings.
- **Fix**: Advance lifecycle generation and detach resources atomically before external cleanup; create flows/sessions under an explicit reservation, cancel or delete anything that becomes stale, and execute cleanup outside locks with a bounded shutdown budget.
  - Strength: Gives connect, pick, disconnect, and close one consistent ownership model and prevents both resurrected local flows and leaked Picker quota.
  - Tradeoff: Requires a careful state-machine edit plus deterministic barrier-based concurrency tests.
  - Confidence: HIGH — the current ordering exposes concrete interleavings visible directly in the code.
  - Blind spot: Google has not been tested under a prolonged DELETE outage, so the real shutdown delay distribution is unknown.
- **Decision**: FIXED (Fix now, full scope (a)+(b)+(c), with triage refinements) — `disconnect()`/`close()` take everything out under `_lock` first (generation bump, flow, waiting pick's poller, the whole session dict; `disconnect` snapshots the credential, then clears the store); `close()` also sets a permanent `_closed` flag under the same lock, and `connect`/`pick`/flow publication/session registration check it (`source_closed`). Flow cancel and remote DELETEs run outside the lock against one monotonic `CLEANUP_BUDGET` (5 s) deadline on a daemon thread (inline fallback if the interpreter refuses threads), so a hanging DELETE neither blocks the caller nor keeps the process alive; a failed DELETE never undoes local state. `_start_flow` captures the generation before `loopback.start` and cancels a listener that went stale instead of publishing it; `pick()` deletes a session that went stale while opening (bounded, with the bearer that opened it) and still raises `cancelled`. `connect()`'s verify path no longer marks connected across a concurrent disconnect. Tests: barrier-based flow and pick interleavings, bounded + final `close()` with a silent Google, and a subprocess proving a hanging cleanup worker does not keep the process alive. The CLI test now takes a fresh source for its second `pick_photos` run (a closed source stays closed).

### F5 — Time-expired sessions remain in the internal registry

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/sources/gphotos.py:563
- **Detail**: Phase 6 says a session whose `expireTime` has passed is dropped. `_live_sessions()` excludes it from public state and correctly gives orphaned items a `re-pick` warning, but leaves the session and its item-id set in `_sessions` until disconnect or exit. A long-running process can therefore accumulate stale records.
- **Fix**: Prune expired records from `_sessions` and their ids from picks, and extend `test_session_expired_marks_items` to assert the internal record is removed.
- **Decision**: FIXED (Fix now, with triage refinements) — `_prune_expired()` (under `_lock`, called from `status()`, `list()`, `resolve()`, `_refresh_base()`) removes sessions past `expireTime` from `_sessions` and their id from every `picks[…]["sessions"]`, keeping the media entry ("re-pick") and links to live sessions; no DELETE because an expired session is of no further use. `test_session_expired_marks_items` asserts the record and links are gone; `test_repick_merges_by_media_id` asserts a medium in both an expired and a live session keeps only the live link.

## Verification

- `python -m pytest tests/` could not start with the shell's system Python because pytest is not installed there.
- `.venv/bin/python -m pytest tests/` passed: **212 passed in 24.30s**. The initial sandboxed run was invalid because loopback socket creation was denied; the permitted rerun passed.
- `.venv/bin/python -m pyflakes castlib tests` passed.
- `node --check castlib/ui/app.js` passed.
- All eleven Phase 6 test names required by the plan exist in `tests/test_gphotos.py`.
- Manual rows 6.2–6.5 have dated device, material, and observed-result evidence in `context/changes/cloud-source-ui/research.md`.
- Mutation testing was skipped because `context/foundation/test-plan.md` does not exist, so no §4 risk-critical module applies.
- After triage fixes (2026-09-13): `.venv/bin/python -m pytest tests/` → **236 passed**; `.venv/bin/python -m pyflakes castlib tests` clean.

## Triage summary

- Fixed: F1, F2, F3 (Fix A), F4, F5 (5)
- Skipped / accepted / dismissed: none
- Deferred by design: the stale video-directory sweep is POSIX-only (Windows in Phase 7); the general `cast-tv <url>` CLI relay stays unguarded (local operator input, not a LAN client).
- Pending manual re-check: rows 6.5 (share link still plays) and 6.3 (a picked video, Original, downloads and plays), since the share-link allowlist and the download limits touch both paths.
