<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cast photos and videos from a Nextcloud server

- **Plan**: context/changes/s17-nextcloud/plan.md
- **Scope**: full
- **Session**: fresh
- **Base**: d15ca6ae424dcffa7aad0dde6eac06416803a576 (merge-base)
- **Head**: 2253d5dc570540106da9887ec554bb7f7f944d29
- **Worktree**: excluded (clean; nothing to include)
- **Checks ran at**: 2253d5dc570540106da9887ec554bb7f7f944d29 (current HEAD)
- **Manual acceptance**: 0 of 12 confirmed — pending: 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 4.2
- **Date**: 2026-11-24
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — In a folder of more than 4000 files, the listed tiles fall back to an account-wide SEARCH

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/nextcloud.py:484-485 (with :40, :446-450, :548-554, :582-593)
- **Detail**: `_snapshot` reads the whole folder in one `PROPFIND` (the plan's Page row) and then puts every media record into the 4000-entry LRU (`CACHE_ITEMS`, `:40`) in the server's order, before the list is sorted by name for display. In a folder of N > 4000 media files, the first N − 4000 records are evicted before the listing returns. When the server's order is close to name order (date-named camera files, as in an InstantUpload or OM folder), that is exactly page 1. Every tile's `thumb()` and every `resolve()` then misses the cache and calls `_search()` (`:548-554`), a `SEARCH` with depth infinity over the whole account. **Failure scenario**: a folder of 5000 `IMG_%06d.jpg` files, listed in name order, gives 200 tiles on page 1 and 200 `SEARCH` requests for their previews (a synthetic run in the review's scratch space printed `page1 tiles 200 SEARCH calls for their thumbs 200`). Each Load more page and each cast from those pages does the same. The plan meant `SEARCH` as a rare fallback for an unknown id; the Page row's own test (`test_listing_pages`, 450 media) stays under the cache size and does not reach this.
- **Fix A ⭐ Recommended**: Let `_file()` look the id up in the cached snapshots (an id → record map kept per snapshot, bounded by `SNAPSHOTS = 8`) before it calls `SEARCH`, and add a test with a 5000-entry folder asserting no `SEARCH` for page 1's previews or a cast from it.
  - Strength: Every file of a listed folder resolves without `SEARCH` for as long as its snapshot is kept, whatever the server's order or the folder's size.
  - Tradeoff: Memory per snapshot grows with the folder (already held as `Entry` objects); the lookup touches two structures.
  - Confidence: HIGH — the snapshot already holds every record the page shows.
  - Blind spot: Not measured against a real Nextcloud folder over 4000 files; the server's actual `PROPFIND` order is unverified.
- **Fix B**: Remember the records in reverse display order, so the first 4000 displayed entries are the most recent in the LRU.
  - Strength: A two-line change in `_snapshot`.
  - Tradeoff: Pages past the 4000th entry still fall back to `SEARCH`; a second big folder opened evicts the first.
  - Confidence: MED — fixes the common case only.
  - Blind spot: Casting a selection built across several big folders.
- **Decision**: FIXED (owner decision 2026-11-24: fix, Fix A) — each folder snapshot keeps an id → record map; `_file()` looks there (newest snapshot first) after the LRU and before `SEARCH`, and re-remembers what it finds. `test_big_folder_files_found_without_search` (500 files over a 50-entry LRU: every page-1 preview, a cast from page 1 and from the last page, and an older snapshot after another folder opens, all with no `SEARCH`). Deliberate break (the snapshot lookup removed) turned it red; restored, green.

### F2 — An app password granted at the moment of Cancel, a new flow or Disconnect stays live on the server

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/nextcloud.py:263-265 (test: tests/test_nextcloud.py:451-477)
- **Detail**: `loginflow.poll()` returns the app password as soon as the poll POST answers 200, without re-checking `stop` (`castlib/auth/loginflow.py:195-213`); `_finish_flow` then calls `loginflow.user()` and, under the lock, drops the answer when the flow was cancelled or replaced (`:264-265`). The dropped password is neither stored nor revoked, while the branch just above (`:259-261`) does revoke an unusable password. Login Flow v2 hands the password over once only (`research.md`, spike 1), so cast-tv can never revoke it later. **Failure scenario**: the owner grants access in the browser and, before the tab updates, presses **Cancel**, types another address and presses **Connect**, or presses **Disconnect**, while the poll answer or the `user()` call is in flight. The tab is disconnected and `nextcloud.json` is absent, but a cast-tv entry remains under the server's Settings → Security (a synthetic run with Cancel inside `poll` printed `state disconnected stored False revoked []`). `test_late_poll_answer_dropped` asserts only "not stored", after `time.sleep(0.1)` (`:466`, `:477`). On a slow runner that sleep can end before the worker thread handles the late answer, so the test passes whether or not the answer is dropped.
- **Fix**: In the dropped branch, call `self._quiet_revoke(base, login, password)` outside the lock. In `test_late_poll_answer_dropped`, wait for the `nextcloud-loginflow` thread to end instead of sleeping, then assert `fake.revoked == [password]` for both the cancel and the new-flow/Disconnect case.
- **Decision**: FIXED (owner decision 2026-11-24: fix) — a dropped late answer is revoked quietly outside the lock. `test_late_poll_answer_dropped` now waits for its own sign-in threads to end instead of sleeping and asserts the revoke after Cancel and after Disconnect; `test_new_flow_late_answer_revoked` covers a new flow. Deliberate break (the revoke removed) turned both red; restored, green.

### F3 — The README and PRD state two things the code does not do

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: README.md:211, README.md:328, context/foundation/prd.md:148; README.md:206, context/foundation/prd.md:143-144; plan.md:77
- **Detail**: (a) **The Disconnect order.** README.md:211 says "cast-tv asks the server to revoke its app password, then deletes `nextcloud.json`"; README.md:328 and FR-015 (prd.md:148) say it "first asks the server to revoke". The code forgets locally first, under the lock (`castlib/sources/nextcloud.py:375`), and revokes the captured password afterwards (`:388`). The Phase 1 review approved that order ("Disconnect ordering" note); Phase 4 then documented the old one, and the plan's Definitions row (`plan.md:77`, "revoke … then forget") was never annotated. What the owner observes is the same; the sentence is wrong. (b) **Film thumbnails.** README.md:206 says films show a placeholder "since Nextcloud makes no film thumbnails", and FR-014 says "videos with a placeholder (no film thumbnails)". The code shows a server preview for any file whose `nc:has-preview` is true (`nextcloud.py:444`, `:590`), as the plan's Phase 1 contract specifies. A server whose admin enabled video previews (the `preview_ffmpeg` provider) shows film previews. The claim holds only for the owner's server (`research.md`: 404 for films). Row 4.2 asks the owner to confirm exactly these texts, so the wording should be fixed before that reading.
- **Fix**: Reword (a) as "cast-tv forgets the app password on this computer at once, then asks the server to revoke it" in README.md:211, :328 and prd.md:148, and add a dated note on plan.md:77. Reword (b) as "films usually show a placeholder: Nextcloud makes film previews only when its admin enabled them".
- **Decision**: FIXED (owner decision 2026-11-24: fix) — README.md and FR-015 say Disconnect forgets the password on this computer at once, then asks the server to revoke it; README.md and FR-014 say films show a placeholder unless the server's admin enabled film previews; plan.md's Disconnect row carries a dated note. Row 4.2 had not been read yet, so nothing reopens.

### F4 — `same_origin` accepts a login link that a browser opens on another host

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/auth/loginflow.py:103-111 (through castlib/net.py:28-36); castlib/ui/index.html:299
- **Detail**: `same_origin` relies on `urllib.parse.urlsplit`, which reads `https://evil.test\@cloud.example.com/login` as host `cloud.example.com`: verified, `same_origin(normalise("cloud.example.com"), that URL)` is `True`. A WHATWG browser treats `\` as `/` and opens host `evil.test` (`node -e "new URL(...).host"` prints `evil.test`). **Failure scenario**: a compromised or hostile server answers `POST /index.php/login/v2` with that `login` value; the gate's link (`:href="source(tab).detail.login_url"`) and **Copy link** send the owner's browser to `evil.test`, although the plan's Same-origin row promises the login page is the typed origin. The scheme must be `https`, so it is never a `javascript:` URL. No app password goes there, since every authenticated request is rebuilt from the base. The server's operator could phish on their own host anyway, so this is defence in depth.
- **Fix**: In `same_origin`, refuse a URL whose authority (between `://` and the first `/`) contains `\` or `@`, and add `https://evil.test\@<host>/x` to `test_flow_other_origin_refused`.
- **Decision**: FIXED (owner decision 2026-11-24: fix) — `same_origin` refuses a URL whose authority holds `\`, `@`, whitespace or a control character. `test_flow_backslash_userinfo_refused` (the start answer with `evil.test\@<host>`, and four direct cases). Deliberate break (the authority check removed) turned it red; restored, green.

### F5 — `connect({server})` over a stored sign-in replaces it without revoking the old app password

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/sources/nextcloud.py:339-340, :267
- **Detail**: `connect({server})` always starts a fresh flow (the plan's Account row), and a successful one overwrites `nextcloud.json` (`:267`) without revoking the record it replaces. **Failure scenario**: with a stored sign-in, a `POST /api/sources/nextcloud/connect {"server": …}` and a granted flow leave the previous cast-tv entry live under the server's Settings → Security, with no copy left to revoke. The UI cannot send this while a credential is stored (`addressForm` is false while `detail.stored`, the Phase 3 F1 fix), and **Connect again** on an expired tab replaces a password the server already rejected. So it is reachable only through the API (from this machine or a page passing the Host/Origin check), or as a race with the gate.
- **Fix**: In `_finish_flow`, revoke the replaced record quietly when its password differs from the new one; or refuse `{server}` with a `ConfigError` while a credential is stored.
- **Decision**: FIXED (owner decision 2026-11-24: fix, the revoke variant) — a granted flow that replaces a stored sign-in revokes the replaced password quietly, after the new one is stored. `test_fresh_sign_in_revokes_the_replaced_password`. Deliberate break (that revoke removed) turned it red; restored, green.

## Review Notes

- **Bookkeeping in diff**: context/changes/s17-nextcloud/change.md, context/changes/s17-nextcloud/plan.md, context/changes/s17-nextcloud/plan-brief.md, context/changes/s17-nextcloud/frame.md, context/changes/s17-nextcloud/research.md, context/changes/s17-nextcloud/follow-ups/review-fixes.md, context/changes/s17-nextcloud/reviews/ (plan-review, phase 1-3 reports), context/foundation/roadmap.md
- **Lessons**: the ledger has 6 entries (5 KB) and was read whole. 1 of 6 names impl-review ("A ticked manual row needs a written observation"); the others ("A step for the person names exactly where to act", "A message from a user action is not owned by the status poll", "A provider secret never enters the public repository") were used as priors. No Manual row is ticked, so the first lesson has nothing to check. The address-refusal note lives in `gateNote`, which is set by the user's action; `revoke_error` comes from server state, as the poll lesson requires.
- **Plan adherence**: every planned change in Phases 1-4 is present, and every Definitions row and Phase contract test exists and asserts its degenerate case. The changes outside the plan (OneDrive, Google Photos and GoPro race fixes, `net._origin`, `tests/test_source_races.py`, `tests/test_gopro.py`, `tests/test_api.py`, `tests/ui_driver.js`, the probe debug-log markers, the `stored` / `disconnecting` UI states) come from the approved per-phase reviews, and they still hold at HEAD. The `defusedxml` line in the PRD's NFR section fits the change. A foreign DAV `href` is skipped per entry rather than refusing the whole answer; no credential follows it, so the Same-origin intent holds.
- **XML memory**: the plan accepts that 32 MiB bounds the wire answer, not the parsed tree (Performance Considerations). A synthetic 28 MB hostile answer of deeply nested elements (depth 4 000 000) parsed in about 5 s with about 1.3 GB peak RSS; a realistic 31 MiB listing (70 227 files) peaked at about 279 MB. Only a hostile server reaches this, and it is within the plan's accepted risk. A depth or element cap (iterparse) would close it if the owner wants.
- **Checked clean**: the app password goes only to the canonical origin (`NO_REDIRECT` for the source's own calls; `BEARER_SAFE` for the relay, photo fetch, thumbnail proxy and downloads). Hrefs cannot leave the files root (`..`, `%2e%2e`, `%2F..`, `%00`, a `pat`/`patrick` prefix and `//evil` are all refused). The password reaches no error, status, error ring, log or subprocess argument. No `x-html`. Every `urlopen` has a timeout and responses are closed. `SNAPSHOTS = 8` is bounded. The 0600 check sits behind `os.name == "posix"`.
- **Mutation check**: skipped. The change touches two mapped risks ("A token leaks", "The TV refuses or stalls on a source": the refusal probe), but `context/foundation/test-plan.md` §3 and `pyproject.toml` configure no mutation tool.
- **Automated checks** (repository `.venv`, at 2253d5d):
  - Row 1.1: `python -m pytest tests/test_nextcloud.py`, exit 0, 53 passed.
  - Rows 1.2, 2.2 and 3.3: `python -m pytest`, exit 0, 756 passed, 6 skipped.
  - Rows 1.3, 2.3, 3.4 and 4.1: `python -m pyflakes castlib tests`, exit 0.
  - Row 2.1: `python -m pytest tests/test_supervisor.py`, exit 0, 38 passed.
  - Row 3.1: `node --check castlib/ui/app.js`, exit 0 (node v24.19.0).
  - Row 3.2: `python -m pytest tests/test_ui.py`, exit 0, 46 passed (node on the path, so not skipped).
  - Row 1.4 (external): on PR #117 at 2253d5d, `release.yml` build passed on ubuntu-22.04 (11m39s) and windows-latest (12m4s), `release` was skipped (tag-only), and `test` passed on ubuntu-latest and windows-latest.
- **Manual rows**: 3.5-3.15 and 4.2 are pending acceptance (acceptance script exit 0, all `pending`). They need the real server, the TV, the phone, Windows and the owner's reading, and the plan leaves them open on purpose. They are not findings. F3 touches row 4.2's surface (README.md, prd.md); a fix lands before that row is run, so nothing needs reopening.
- Two delegated analysis passes (plan drift; safety, quality and patterns) were run; their findings were re-checked against the code in this session before being recorded.
