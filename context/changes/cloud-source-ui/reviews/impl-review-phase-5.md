<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cloud Source UI Implementation Plan

- **Plan**: context/changes/cloud-source-ui/plan.md
- **Scope**: Phase 5 of 7 — OneDrive tab
- **Date**: 2026-09-12
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 5 warnings, 5 observations
- **Git scope**: ed411a3..e183e9a; implementation 1bf947c, addendum and stamps e183e9a. Working tree clean at review start.
- **Progress**: Phase 5 is 5/5 (5.1 automated; 5.2–5.5 manual, each with an evidence note in research.md "Manual rows 5.2–5.5"). Current phase moves to 6.
- **Automated criteria at review**: `pytest tests/` 170 passed; pyflakes clean; `node --check castlib/ui/app.js` ok.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS — no MISSING item; two minor shape drifts (F7) |
| Scope Discipline | WARNING — one benign cross-tab change (F6) |
| Safety & Quality | WARNING — F1–F5 |
| Architecture | PASS |
| Pattern Consistency | PASS — credential scheme matches GoPro's generation rules; own urllib layer is defensible (see F1) |
| Success Criteria | WARNING — 5.4's hour-long re-resolve and 5.5's revoke were simulated, documented (F9) |

Every planned contract is implemented and the seven named tests exist and cover their stated intent; eight further tests cover the addenda. The warnings are about the token path's robustness under failure and about one unenforced invariant ("the bearer goes nowhere else"), none about the happy path that rows 5.2–5.5 exercised live.

## Findings

### F1 — `page` is a prefix check and urllib forwards the bearer across redirects

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/onedrive.py:404 (check), castlib/sources/onedrive.py:74 (`graph_get` uses the default opener)
- **Detail**: `list(page=…)` accepts any string starting with `GRAPH + "/"`, so any Graph path can be requested with the bearer, not just a `children` nextLink. `graph_get` uses `urllib.request.urlopen` with the default `HTTPRedirectHandler`, whose `redirect_request` copies every header except `content-*` onto the redirected request (verified in the 3.14 venv). `GET /me/drive/items/{id}/content` answers 302 to the pre-authenticated download host, so a caller past the Origin check can make the process send its bearer to a non-Graph host and pull up to 8 MB of media into `r.read(8 << 20)`. The target is Microsoft-owned, so this is a broken invariant, not exfiltration, but the comment on line 403 promises more than the code enforces.
- **Fix**: Build one opener for `graph_get`/`_post_form` whose redirect handler refuses (`redirect_request` returning `None` → `HTTPError`), and restrict `page` to a nextLink shape: `^GRAPH/me/drive/(root|items/<ID_RE>)/children\?` .
  - Strength: Two small changes close both halves (host pinning and path shape); a redirect from Graph is never expected on these calls, so nothing legitimate is lost.
  - Tradeoff: If Graph ever starts answering `children` with a redirect, listing breaks loudly; acceptable for a documented JSON API.
  - Confidence: HIGH — redirect header copy verified in the stdlib source; the nextLink shape is asserted verbatim in `test_list_pages_nextlink`.
  - Blind spot: The exact nextLink shape on business (SharePoint-backed) drives was not probed; only the personal drive was.
- **Decision**: FIXED — `net.NO_REDIRECT` opener (refuses every 3xx) used by `graph_get` and `_post_form`; `graph_get` treats any status ≥ 300 as an error; `page` must match `GRAPH/me/drive/(root|items/<id>)/children?`. Tests: `test_graph_redirect_is_not_followed`, same-host non-listing page added to `test_list_pages_nextlink`.

### F2 — `/api/status` can stall behind a token refresh held under the data lock

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/auth/tokens.py:119 (refresh under `_lock`), castlib/sources/onedrive.py:307 (`save()` under the source lock)
- **Detail**: `get_access_token` runs the refresher (a POST with a 30 s timeout) while holding `TokenStore._lock`, by design so two stale callers make one request. But `status()` → `exists()`/`load()` takes the same lock, so every UI poll (1.5 s cadence) blocks for the refresh's duration, and a hung token endpoint freezes the status of every tab for up to 30 s. In `_wait_for_token`, `self._store.save()` is called under the source `_lock`, so a refresh in flight also blocks the flow thread and, through it, every `status()` on the source.
- **Fix**: Keep the "one refresh at a time" guarantee with a dedicated `_refresh_lock` (or a `refreshing` flag on a Condition) and let `load()`/`exists()` read the cached `_data` under the short data lock only; move `save()` in `_wait_for_token` out of the source lock (save first, then take the lock to publish).
  - Strength: Preserves the single-refresh property and unblocks the poll; the change is local to two functions.
  - Tradeoff: Two locks with a documented order; a reader may briefly see the old token while a refresh is in flight, which is the same as today's pre-refresh state.
  - Confidence: HIGH — the lock chain is visible in the code; no test depends on the stall.
  - Blind spot: Not reproduced with a slow token endpoint; the stub answers instantly.
- **Decision**: FIXED (differently, per the user) — `TokenStore` runs the refresh under a dedicated `_refresh_lock` with no data lock held around the network call; callers queued behind a refresh re-check and take its result; a credential `_version` (bumped by save/clear/refresh) makes a late answer after `disconnect()` or a new sign-in be dropped instead of restoring/overwriting. `save()` in `_wait_for_token` stays under the source lock with the generation check. Tests: `test_status_answers_while_a_refresh_hangs`, `test_concurrent_callers_share_one_refresh`, `test_late_refresh_does_not_restore_a_disconnected_sign_in`, `test_late_refresh_does_not_overwrite_a_new_sign_in` (three fail on the old store).

### F3 — An unexpected exception in the poll thread leaves the gate on a dead code

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/onedrive.py:297
- **Detail**: `_wait_for_token` catches only `AuthError` and `UpstreamError`. `self._store.save()` (line 307) can raise `OSError` (read-only or missing config dir, disk full), and anything else unexpected escapes too. The thread then dies via the default excepthook with `self._flow` still set: `status()` reports `connecting` with the old code forever, `connect({})` repeats that code, and only `cancel`/`disconnect` clears it.
- **Fix**: Add `except Exception as e:` around the body that, generation-checked, clears `_flow`/`_flow_stop` and records `_flow_error = {"code": "flow_failed", "message": str(e)}`; one test with a `save` that raises.
- **Decision**: FIXED — `_wait_for_token` now wraps the body (`_finish_flow`) in a catch-all that, generation-checked, clears the flow and records `flow_error = flow_failed` with the exception text. Test: `test_flow_thread_failure_clears_the_code` (a raising `save`; the next connect starts a new flow).

### F4 — The token file is written in place, not atomically

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/config.py:81 (`write_private`), used from castlib/auth/tokens.py:77, :88, :127
- **Detail**: `write_private` opens with `O_WRONLY|O_CREAT|O_TRUNC` and writes into the live file. A crash or disk-full mid-write leaves an empty or partial `onedrive.json`; `_read()` maps that to "nothing stored", so the refresh token is silently lost and the user is signed out. `config.write_json` already uses mkstemp + `os.replace`; the token store is the only JSON file that does not.
- **Fix**: Make `write_private` write to `mkstemp(dir=…)`, `os.fchmod(fd, 0o600)`, write, `os.replace` — mirroring `write_json`; the existing `test_token_file_mode_0600` keeps guarding the mode.
- **Decision**: FIXED — `config.write_private` now writes a 0600 `mkstemp` file beside the target and `os.replace`s it, mirroring `write_json`; `test_write_private_mode` extended (old content and no temp file survive a failed write).

### F5 — The `slow_down` assertion cannot reliably fail

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: tests/test_onedrive.py:258-266
- **Detail**: With `interval=0.01` and `SLOW_DOWN_STEP=0.05`, the assertion `stamps[0] - t0 >= 0.05` also passes without the step whenever four 10 ms waits plus four stub round trips exceed 50 ms, which is routine on a loaded machine. It is a lower bound, so a regression that drops the +5 s step would not be caught.
- **Fix**: Unit-test `devicecode.poll` with a fake `stop` event that records each `wait(interval)` argument and assert the sequence `[0.01, 0.01, 0.06, 0.06]`.
- **Decision**: FIXED — `test_devicecode_polling_errors` passes a `threading.Event` subclass that records each `wait(interval)` and asserts `[0.01, 0.01, 0.06, 0.06]`; the wall-clock lower bound is gone. Verified: dropping the step makes the test fail.

### F6 — Broken thumbnails now collapse on every tab, not only OneDrive

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: castlib/ui/index.html:169, castlib/ui/index.html:282
- **Detail**: `@error="$el.hidden = true"` was added to the thumbnail `<img>` in both the local and the source grids, so a failed thumbnail shows the placeholder for GoPro and local files too. Benign and arguably right, but not in the plan or the addenda. Two smaller cross-tab text changes ride along: GoPro's "checking the token…" became "checking…" (app.js:193) and gate error notes now append `e.hint` for every source (app.js:242).
- **Fix**: One line in the Phase 5 addendum naming the three cross-tab UI changes.
- **Decision**: FIXED — Phase 5 addendum in plan.md names the three cross-tab UI changes. (The addendum's `page` bullet was also updated to the F1 rule.)

### F7 — `connect()` payload and the "show files" step differ from the written contract

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: castlib/sources/onedrive.py:292; castlib/ui/app.js:196
- **Detail**: The plan says `connect()` returns `{step: "code", user_code, verification_uri, expires_in}`; the code returns `dict(status(), step="code")` with those fields nested under `detail`. The UI reads `detail.*`, so it is self-consistent, and the addendum describes the three connect shapes but not the nesting. The plan's "signed in as … — show files" intermediate step is collapsed: the gate switches straight to the list once `connected`, with "signed in as …" in the list header.
- **Fix**: Amend the addendum: the code fields ride on `detail` (the same object `status()` shows while pending), and the gate hands over to the list without an intermediate step.
- **Decision**: FIXED — Phase 5 addendum now states the `detail` nesting of the code fields and that the gate hands over to the list with no intermediate step.

### F8 — Per-process listing caches grow without bound

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/onedrive.py:221-223 (`_raw`, `_thumbs`, `_parents`)
- **Detail**: The three maps only shrink on `disconnect()` or a new sign-in; `THUMB_FRESH` governs staleness, not eviction. A long session browsing a large drive keeps every driveItem ever listed (about 1–2 KB each with thumbnail sets). GoPro has the same `_raw` on a single feed; OneDrive's folder tree makes it larger, though still tens of MB for tens of thousands of items.
- **Fix**: Cap `_raw`/`_thumbs` with a small LRU (a few thousand ids), or keep only the last N listings; `_parents` can stay (ids and names only).
- **Decision**: FIXED — `_raw` is an `OrderedDict` capped at `CACHE_ITEMS = 4000` (LRU: hits move to the end, `_thumbs` evicted in lockstep) via `_remember()`; `_parents` unchanged. Test: `test_listing_cache_is_bounded`.

### F9 — Rows 5.4 and 5.5 were closed with documented substitutions

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/cloud-source-ui/plan.md:1213-1214; research.md rows 5.4, 5.5
- **Detail**: Row 5.4's "seek an hour into a film after leaving it paused for over an hour" was not exercised live; the note points at `test_relay.py::test_reresolve_once` and `test_download_url_resolved_on_open`. Row 5.5 replaced the account-side revoke with garbage tokens on disk, which produces the same `invalid_grant` on refresh. Both notes say so in bold, which satisfies the lessons.md rule, but the ticks stand on tests and a simulation rather than the criterion as written. The HEIC half of 5.4 was done three times over (landscape, a mis-built portrait fixture, a corrected phone-style portrait) and the 4K half once.
- **Fix**: Leave the ticks with their notes; optionally list "pause an hour, then seek" as a follow-up to try during Phase 7's soak.
- **Decision**: FIXED (differently, per the user) — 5.4 marked partially verified in the Phase 5 block and research.md (tests are auxiliary evidence); the hour-pause seek is a new Phase 7 criterion and Progress row 7.5. 5.5 unticked and left open: garbage tokens exercise `invalid_grant` handling, not the account-side revoke; it closes on a real revoke or an explicit criterion change (the user's call, not made here).

### F10 — Three error paths untested; two cheap hardenings

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/onedrive.py:255-261 (`graph_unauthorized`), castlib/auth/devicecode.py:265 (`refresh_failed`), castlib/sources/onedrive.py:93 (`graph_not_json`); castlib/sources/onedrive.py:46 (`ID_RE`); castlib/auth/devicecode.py:207 (`verification_uri`)
- **Detail**: A second 401 after a successful refresh, a 5xx from the refresh, and a non-JSON Graph body have no test. `ID_RE` admits `.` and `..`, yielding `/me/drive/items/..` (same host, own bearer, no escape). `verification_uri` from the token endpoint is rendered as an `href` without an `https://` check; the trust boundary is login.microsoftonline.com, so this is one line of belt and braces.
- **Fix**: Three short tests against the stub; require an alphanumeric in `ID_RE`; `startswith("https://")` on `verification_uri`.
- **Decision**: FIXED (differently, per the user) — ids go through `good_id()`: `ID_RE.fullmatch` plus an explicit refusal of `.` and `..` (no alphanumeric requirement); `devicecode.start` parses `verification_uri` and refuses anything but `https` with a non-empty host (`devicecode_refused`). Tests: `test_second_401_after_a_refresh_is_graph_unauthorized` (one refresh, then `graph_unauthorized`), `test_refresh_5xx_keeps_the_credential` (`refresh_failed`, state stays `connected`, tokens intact), `test_graph_200_with_a_non_json_body` (`graph_not_json` on a 200), `test_item_ids_are_one_clean_segment`, `test_verification_uri_must_be_https_with_a_host`.

## Triage (2026-09-13)

- Fixed as proposed: F1, F3, F4, F5, F6, F7, F8
- Fixed differently (the user's design): F2 (refresh lock + credential version, `save()` kept under the source lock), F9 (5.4 partial, hour-pause seek → row 7.5; 5.5 unticked and open), F10 (`fullmatch` + `.`/`..`, parsed https-with-host check)
- Skipped / accepted / dismissed: none
- Suite after triage: `pytest tests/` 182 passed (170 before); pyflakes clean; `node --check castlib/ui/app.js` ok
- Not committed by the review; the diff touches `castlib/{net,config}.py`, `castlib/auth/{tokens,devicecode}.py`, `castlib/sources/onedrive.py`, `tests/{test_onedrive,test_config}.py`, `plan.md`, `research.md`
