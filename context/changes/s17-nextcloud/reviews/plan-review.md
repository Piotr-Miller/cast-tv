<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Cast photos and videos from a Nextcloud server

- **Plan**: `context/changes/s17-nextcloud/plan.md`
- **Brief**: `context/changes/s17-nextcloud/plan-brief.md`
- **Mode**: Deep, fresh review
- **Date**: 2026-11-24
- **Reviewed HEAD**: `d15ca6ae424dcffa7aad0dde6eac06416803a576`
- **Plan sha256**: `7e0fbb22007916372c6d900f408f76f321ff787ed8d8fe6b76d291bc69fe01fa`
- **Brief sha256**: `8b6d35f44a649f916ba9d16a7ca7a71c9ce9e9328e1a96747f2685acf12c006f`
- **Verdict**: REVISE — the source/relay architecture is sound; targeted changes are needed before implementation.
- **Findings**: 1 critical, 7 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
| --- | --- |
| Requirement Definition | WARNING |
| End-State Alignment | FAIL |
| Lean Execution | PASS |
| Architectural Fitness | WARNING |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

Read `frame.md` and `research.md` before the plan and brief. Read all 6/6 lessons; their session, credential, manual-acceptance and UI rules apply through AGENTS.md or their stated scope (none has a literal `plan-review`/`all` applicability tag). `git fetch` succeeded; remote branches were inspected; `gh pr list` returned no open PRs. This is the only active change plan. Branch: `s17-nextcloud`.

All 16 declared implementation/test/document paths have a valid location: 11 exist; 5 are intentional creates with existing parents. The explicit manual surfaces exist. Four body phases match four Progress phases; one Progress section is at the bottom; automated/manual criterion counts match (3/0, 3/0, 4/9, 1/1); no body checkboxes or malformed n/a/acceptance suffixes. The skill's acceptance-state script reports all 10 manual rows pending. No acceptance was inferred from the earlier spikes.

The code claims and line citations were checked individually below. Brief and plan agree on the main phases, but share several unsupported UI assumptions. Definitions are present, with planned test names for all 10 rows; naming a future test is not proof that its assertions cover the definition. See the definition matrix and F3–F5/F7.

One focused read-only analysis agent independently traced Phase 2 and its existing-source blast radius. The main review verified the UI and source contracts, URL/authentication boundaries, XML assumptions and test commands. No owner server, TV, credential file or stored token was accessed. External reading was limited to public Nextcloud/Python documentation. Only this report was written; the user's restriction overrides the skill's normal change.md/carry-record updates and plan triage.

## Findings

### F1 — Disconnect has an API endpoint but no UI implementation

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: `plan.md:75`, Phase 3 (`plan.md:259`), manual row 3.13 (`plan.md:310`)
- **Detail**:
  The plan promises a Disconnect action and asks the owner to press it, but Phase 3 only adds a gate/address/login step. The current UI has no disconnect method or button anywhere in `castlib/ui/app.js` or `castlib/ui/index.html`. Only the backend already supplies it (`castlib/api.py:248`). Implementing the listed UI changes and all four named UI tests could therefore leave the owner unable to disconnect from cast-tv. There is a second integration requirement: `listVisible()` keeps a loaded list visible even when disconnected (`castlib/ui/app.js:329`), whereas the planned revoke-failure note is on the gate (`plan.md:268`). Calling the endpoint alone would not reliably expose that note.
- **Fix**: Add the Nextcloud Disconnect button, POST handler and post-disconnect UI transition explicitly to Phase 3. Clear that source's list/selection and verification state, refresh status, and render `detail.revoke_error` in the resulting visible gate. Test the real UI action against successful and failed revocation, asserting endpoint, state, reachable note and no credential in the response.
  - Strength: Completes the already-decided product behavior using the existing API route.
  - Tradeoff: Adds UI state/reset work and two behavior cases to Phase 3.
  - Confidence: HIGH — the backend route exists; neither UI file contains a disconnect action.
  - Blind spot: Real removal of the server's device entry still needs row 3.13.
- **Decision**: FIXED — Disconnect on every signed-in tab (owner decision 2026-11-24), Phase 3 §2, tests and rows 3.13, 3.14.

### F2 — Redirect protection does not validate the initial credential destination

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: `plan.md:55`, `plan.md:84`, Critical Implementation Details (`plan.md:110`), Phase 1 (`plan.md:136`, `plan.md:175`)
- **Detail**:
  The promised invariant is origin-bound credentials. The concrete rule for `login` and `poll.endpoint`, however, checks scheme and host, omitting port; `https://cloud.example.com:8443` is a different origin from port 443. The poll-returned `server` is explicitly checked only for HTTP, and the href rule does not spell out authority validation before storing/using an absolute href. `NO_REDIRECT` prevents redirects, not a first request to a foreign URL (`castlib/net.py:16`); `BEARER_SAFE` strips Authorization only inside `redirect_request()` (`castlib/net.py:42`). The relay, photo loader and thumbnail proxy attach headers to the initial `up.url` (`castlib/relay.py:31`, `castlib/photos.py:226`, `castlib/api.py:293`). Thus these helpers alone do not establish the plan's guarantee. This is an incomplete security contract, not an observed leak in an implementation that does not exist yet.
- **Fix**: Specify one canonical HTTPS base and compare full `(scheme, hostname, effective port)` for all flow URLs, the poll's returned server and every absolute DAV href before using credentials. Reject URL userinfo and malformed authorities. Resolve relative DAV hrefs against that base, validate the decoded path at a segment boundary under the correct account root, then construct the outgoing URL from the trusted base and safely encoded path. Explicitly test foreign host, different port, HTTP, scheme-relative href, root-prefix confusion and encoded traversal; assert no request with credentials reaches the rejected destination. Define the media redirect policy separately: the current default follows a cross-origin/downgrade redirect after dropping Authorization; it does not refuse the redirect.
  - Strength: Makes the invariant enforceable before the first request, retaining the existing HTTP helpers.
  - Tradeoff: A server advertising a different canonical origin must be rejected with an actionable address correction.
  - Confidence: HIGH — `_origin()` already models the correct origin tuple (`castlib/net.py:28`); the current guards act only on redirects.
  - Blind spot: Canonical-address differences on other hosted/reverse-proxy installations were not exercised.
- **Decision**: FIXED — Definitions "Same origin" and "Server address" rows (full origin tuple, userinfo refused, URLs built from the base), Phase 1 contract and tests.

### F3 — Populating Entry.date will not put a date on a tile

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: End-State Alignment
- **Location**: Definitions (`plan.md:60`), desired tiles (`plan.md:72`), Phase 3 (`plan.md:259`), row 3.7 (`plan.md:304`)
- **Detail**:
  Both grids render metadata through `metaOf(it)` (`castlib/ui/index.html:225`, `castlib/ui/index.html:419`). That function uses dimensions, size, duration or MIME, and never reads `date` (`castlib/ui/app.js:679`). OneDrive supplies `Entry.date` (`castlib/sources/onedrive.py:190`) but its current tiles also do not display it. A source-only `test_tile_date_from_last_modified` can pass while the owner sees no date. Phase 3 does not currently include a renderer change or assertion for it.
- **Fix**: Add explicit Nextcloud date rendering to Phase 3, with a “Last modified” label/tooltip. Test both the source's UTC date extraction (including missing/invalid values and a midnight boundary) and its presence in the actual tile metadata path; no date should produce no date text.
- **Decision**: FIXED — date on Nextcloud tiles only with a "last modified" tooltip (owner decision 2026-11-24), Phase 3 §3, `test_nextcloud_tile_shows_date`.

### F4 — The shared Load more handler drops later folders

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architectural Fitness
- **Location**: Page definition (`plan.md:62`), listing (`plan.md:166`), shared UI claim (`plan.md:273`)
- **Detail**:
  The plan pages 200 entries, with folders first. The shared UI appends `items` on later pages but sets `folders` only on the first page (`castlib/ui/app.js:361`). In a folder with 201 child folders, folder 201 will be returned by the source but remain inaccessible in the UI. This was reproduced through the existing Node driver: a second page containing a new folder was requested, `next` became null, but only the first page's folder remained. The plan's 450-entry source test could pass while browsing loses data.
- **Fix**: Define paging as all child folders on the first response, with only media files consuming the 200-item offset; subsequent responses carry only the next media slice. Document this adjustment in Definitions and the brief. Test 201 folders plus 201 media files through source → API → UI, including the last folder and last file, and verify one PROPFIND snapshot is reused across its pages. A new page-less Refresh must fetch a new snapshot.
  - Strength: Fits the existing Listing fields and UI's first-page folder handling without changing every source's pagination.
  - Tradeoff: The first response can contain many folder records; the DAV response cap still applies.
  - Confidence: HIGH — the UI behavior was reproduced locally; folders and media already have separate Listing arrays (`castlib/sources/base.py:48`).
  - Blind spot: A UI with thousands of folder buttons may need later usability work, independently of correctness.
- **Decision**: FIXED — all child folders on page one, media paged from one snapshot; Load more appends folders; `test_nextcloud_load_more_keeps_folders`.

### F5 — Opening a folder after revocation destroys the promised last list

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architectural Fitness
- **Location**: Expired definition (`plan.md:64`), Phase 3 shared-list claim (`plan.md:273`), row 3.12 (`plan.md:309`)
- **Detail**:
  `openFolder()` changes the path and clears items, folders and `loaded` before the request (`castlib/ui/app.js:334`). A failed load stores an error but restores nothing (`castlib/ui/app.js:366`). `listVisible()` then returns false once the source is expired (`castlib/ui/app.js:329`), so the gate replaces the list. The precise manual scenario in row 3.12 — revoke, then open a folder — cannot preserve the last list by reusing the current UI. Reproduced with a scripted existing-source authorization error: empty arrays, `loaded=false`, and `listVisible=false`. The prior expired-list test only changes status over an already-loaded list (`tests/test_ui.py:164`), so it misses this navigation case.
- **Fix**: Stage folder navigation and replace path/items/folders/crumbs only after a successful listing, preserving the last successful snapshot on authorization failure. Define the new source's auth-error code and ensure load failures refresh source status promptly. Add a Node case that starts with a populated list, navigates into a folder that answers 401, then asserts the same old list/crumbs and the expired banner; also test Connect again and cancelled/failed reconnect.
  - Strength: Implements the decided behavior with a test of the actual triggering action.
  - Tradeoff: Shared navigation changes require regression checks for the other folder source.
  - Confidence: HIGH — both the destructive code and the resulting state were verified.
  - Blind spot: Real revocation remains a manual check; fakes prove the transition only.
- **Decision**: FIXED — `openFolder` replaces the list only after success; `nextcloud_unauthorized` refreshes status; `test_nextcloud_failed_folder_keeps_list`, row 3.12.

### F6 — A 32 MB response limit and the local Expat version are not a portable XML safety policy

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: XML details (`plan.md:114`), Phase 1 tests (`plan.md:185`)
- **Detail**:
  The plan relies on ElementTree/Expat 2.4.1+ and the review machine's Expat 2.9.0, but the package supports Python >=3.10 without an Expat constraint (`pyproject.toml:11`). Python may use a system Expat; bundling “its Python's own” does not establish a safe minimum for releases or source installs. Current [Python XML security documentation](https://docs.python.org/3/library/xml.html#xml-security) identifies additional risks below 2.7.2, including large-token behavior addressed after 2.4.1. A wire-size cap also does not cap expanded text or tree memory. A bounded local example on Expat 2.9.0 expanded a 13,348-byte internal-entity document into 4,194,304 text bytes. This demonstrates that entity expansion is still allowed below protection thresholds; it is not a claim that a full billion-laughs attack succeeded. No planned test covers the input cap, DTD/entity policy or malformed XML.
- **Fix**: Specify a hardened parser that rejects DTDs/entities (for example `defusedxml` with DTD prohibition), keep the wire cap, and detect oversize by reading cap+1 and refusing rather than parsing a truncated prefix. Add dependency/files to Phase 1 if needed. Test DTD/internal/external entities, malformed/oversized XML and namespace/propstat handling using bounded fixtures, and record the supported runtime policy rather than the development venv's version.
  - Strength: Removes the implicit dependence on one machine's parser build and makes rejection observable.
  - Tradeoff: Adds a small dependency or an explicitly maintained parser policy.
  - Confidence: HIGH — runtime constraints, documentation and the bounded expansion example agree.
  - Blind spot: Final decoded tree memory remains larger than wire bytes even without entities; do not describe 32 MB as a total-memory bound.
- **Decision**: FIXED — defusedxml with forbid_dtd/forbid_entities/forbid_external, cap+1 refusal, hostile-XML tests, dependency in pyproject, smoke assertion and release trigger (owner decision 2026-11-24).

### F7 — Phase 2's target-only test would not prove the authenticated probe works

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 tests (`plan.md:231`), integration strategy (`plan.md:364`)
- **Detail**:
  The proposed test asserts which URL `explain_failure()` receives. The existing test stubs that function to return a diagnosis without opening anything (`tests/test_supervisor.py:54`) and explicitly expects the old signed upstream address (`tests/test_supervisor.py:64`). Repeating that pattern with a local URL would pass if the probe cannot actually fetch authenticated bytes. Phase 1's separate relay test does not exercise the registration/lifetime/probe sequence. The source compatibility analysis itself found no blocker; the verification needs to prove the composition.
- **Fix**: Name the existing opposite assertion as an update. In the new probe test, have the diagnostic test double actually GET/Range-read its supplied local URL from an upstream that refuses missing Basic auth, then return its diagnostic result. Assert received bytes, required header, hint and item lifetime. Add regression cases for a custom opener/refresh and an already-downloaded item retaining its local path.
- **Decision**: FIXED — Phase 2 tests read the media URL for real against an upstream needing Basic; `tests/test_supervisor.py:64` update named.

### F8 — Manual acceptance has unreachable steps and omits the Windows webview

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Out of scope (`plan.md:97`), manual instructions (`plan.md:298`), criteria (`plan.md:302`), surfaces for Phase 3
- **Detail**:
  Several rows do not name a reachable control/window; see the row-by-row audit below. In particular, row 3.9 asks for the UI's seek control, but none exists: the UI has show previous/pause/next controls (`castlib/ui/index.html:134`), and the API exposes only pause/resume/next/prev/stop (`castlib/api.py:29`). The product expects seeking with the TV remote (`context/foundation/prd.md:82`). Row 3.11 repeats the address/Connect flow after the earlier rows leave the source connected, when that gate is hidden. Most importantly, excluding Windows because no new OS call is added misses the real browser surface: Windows uses WebView2 while Fedora uses Qt WebEngine (`castlib/window.py:42`), and the plan itself records uncertain link/clipboard behavior (`plan-brief.md:76`). CI installs only the test extra (`.github/workflows/test.yml:20`), so it cannot prove this native-window sign-in behavior. `test_write_private_mode` also deliberately makes its 0600 assertion POSIX-only (`tests/test_config.py:76`).
  The acceptance-state script exposes another gap: every Phase 3 manual row currently falls back to only `app.js`, `index.html`, and `test_ui.py`. A later change to `nextcloud.py`, Login Flow, photos or relay would not invalidate the accepted sign-in/casting rows.
- **Fix**: Rewrite each row with its window/page, visible control, initial state and observation; use the TV remote for the seeking row, and disconnect/reset before the phone sign-in row. Add a pending Windows native-window row covering new sign-in, opening/copying the link, return to the connected tab, restart/reuse and Disconnect; it may wait for the next Windows visit but must stay in the plan. Add explicit per-row surfaces that include the engine/auth/media code each observation actually proves, then run the acceptance-state parser again.
  - Strength: Meets the repository's existing acceptance rules and checks the surface fakes cannot prove.
  - Tradeoff: Adds a real Windows session; it need not block automated implementation.
  - Confidence: HIGH — different renderers and absent controls are established by code.
  - Blind spot: The actual Windows browser/link behavior is intentionally untested in this review.
- **Decision**: FIXED — every manual row rewritten with window, control and observation; seek via the Samsung remote; Disconnect before the phone row; Windows row 3.15 added (owner decision 2026-11-24); explicit surfaces per row.

### F9 — A few guarantees and origin labels overstate the evidence

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Requirement Definition
- **Location**: `plan.md:58`, `plan.md:77`, `plan.md:224`; `plan-brief.md:35`, `plan-brief.md:40`, `plan-brief.md:84`
- **Detail**:
  “Any” refused remote film having an ffprobe reason is stronger than existing diagnostics: optional/missing/failed ffprobe returns no diagnosis (`castlib/diagnostics.py:16`), no TV requests bypass the probe (`castlib/supervisor.py:338`), and only selected heuristics produce reasons (`castlib/diagnostics.py:34`). “No secret on a command line” should say no provider credential/app password: the local media URL still carries the process media capability token (`castlib/server.py:3`, `castlib/server.py:385`). The brief's “nothing stays behind” on Disconnect contradicts the accepted failed-revoke behavior (`plan.md:63`). The ordering claim “matches OneDrive” is not established by the cited code: OneDrive sets a page size of 200 (`castlib/sources/onedrive.py:41`) but retains the API's item order (`castlib/sources/onedrive.py:437`), with no client name sort. Finally, the Photo row's exact allowlist comes from code (`castlib/media.py:32`), not a Nextcloud product guarantee; the PRD independently excludes GIF/raw (`context/foundation/prd.md:175`) but does not establish that exact MIME allowlist.
- **Fix**: Say best-effort diagnostic information when available; distinguish media capability from provider credential; qualify removal as best effort with a persistent failure note. Label the exact photo allowlist as an inherited cast-tv compatibility choice, and sorting/page size/account scope as explicit plan assumptions (not inferred user decisions or guarantees supplied by OneDrive). Keep the decided UTC last-modified semantics; add the missing renderer/tests from F3 rather than claiming existing tiles already show dates.
- **Decision**: FIXED — best-effort diagnosis and revoke wording; media token vs provider credential; order and page size as plan assumptions; photo list origin `code`.

## What is sound

- The actual casting goal has a backing source design. Login Flow v2 avoids copying a credential; WebDAV lists account files; a separate app-password store fits a credential that has no OAuth refresh token. `Source.resolve(source_id, quality="auto")` should retain the optional quality parameter even if Nextcloud ignores it (`castlib/sources/base.py:67`). No Source/API schema redesign is needed.
- Registration in `app.py` is sufficient for the generic source API. Folder paths can be Folder/crumb IDs; numeric file IDs can be source IDs. `MediaItem.resolve` supplies an Upstream; the HTTP server remains responsible for registration and media delivery. HEIC conversion already receives upstream headers. Reusing the raster thumbnail proxy is correct and preserves its content-sniffing protection (`castlib/api.py:306`).
- The evidence supports choosing the relay. The spike proved an H.264 film through it; the later local tests withdrew the OM-playback refusal. Those tests do **not** establish an OM film through Nextcloud. Rows 3.8–3.10 appropriately leave actual Nextcloud photo/OM playback, sound, seeking and mixed-show acceptance pending.
- No transcode, direct-TV HTTPS link, EXIF request per item, video preview or bitrate heuristic is needed to meet the stated owner's use case. In particular the owner server reported no film previews, and heavy OM films were observed to play. Excluding extra SSO integration is reasonable as long as ordinary browser-based 2FA is not rejected; Login Flow v2 delegates authentication to that browser. See [Nextcloud Login Flow](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html#login-flow-v2).
- No packaging change is intrinsically required for the proposed Python modules: the package already lists `castlib.auth` and `castlib.sources` (`pyproject.toml:27`). There is no new built-in provider secret/client registration to ship. If F6 adds a dependency, list it and validate installation normally.

## Phase 2 compatibility and blast radius

| Case | Code evidence | Result |
| --- | --- | --- |
| Registration/lifetime | `castlib/supervisor.py:141`, `castlib/supervisor.py:277`, `castlib/supervisor.py:322`, `castlib/supervisor.py:367` | Registered before the TV URL; `_never_started()` evaluates before `_finish()` retires the item. |
| HTTP recursion/threading | `castlib/server.py:187`, `castlib/server.py:348`, `castlib/server.py:385` | `/m/` accepts the media token before Host/Origin checks; independent request threads can serve the probe. |
| GoPro | `castlib/sources/gopro.py:925`, `castlib/relay.py:30` | Fresh signed address per open; relay route preserves behavior. |
| OneDrive | `castlib/sources/onedrive.py:537`, `castlib/relay.py:30` | Fresh preauthenticated Graph download address; relay route is valid. |
| Google Photos bearer streams | `castlib/sources/gphotos.py:884`, `castlib/relay.py:33` | Relay adds the bearer; cross-origin redirect dropping still applies. |
| Share links | `castlib/sources/gphotos.py:803`, `castlib/sources/gphotos.py:827`, `castlib/relay.py:38` | Resolver custom opener and refresh hook are retained; the probe uses the same serving path as playback. |
| `download=True` | `castlib/sources/gphotos.py:892`, `castlib/supervisor.py:265`, `castlib/downloads.py:234` | Preparation sets `item.path` before registration; the path-first rule continues to probe the downloaded local file. |
| Existing local file | `castlib/supervisor.py:342` | Remains a local path. |
| No registered ID | `plan.md:227` | Skipping is a sensible defensive rule; production cast registration normally supplies the ID. |

No current remote source requires a different probe route. The production call to `explain_failure()` is confined to `_never_started()` (`castlib/supervisor.py:349`); the other `media_url()` uses publish cast/subtitle URLs. Update the existing contrary test at `tests/test_supervisor.py:64`; add compositional coverage per F7. The correct promise is improved access to diagnostic bytes, not a guaranteed root-cause explanation for every refusal.

## Current State Analysis and Key Discoveries: citation audit

Every explicit code file:line reference in those sections was checked, including references that repeat earlier ones. Unranged OneDrive/config claims were traced to their implementations rather than accepted as narrative.

| Plan reference/claim | Evidence checked | Assessment |
| --- | --- | --- |
| `plan.md:26`, Source at `base.py:60-68` | `castlib/sources/base.py:60` | Correct; preserve `quality="auto"` in resolve. |
| `plan.md:28`, source registry `app.py:187-188` | `castlib/app.py:187` | Exact and correct. |
| `plan.md:28`, generic routes `api.py:229-275` | `castlib/api.py:228`, `castlib/api.py:243`, `castlib/api.py:254` | Correct; source lookup is at 228, thumbnail entry at 229, source routes through 271. Lines 274–275 begin raster detection. Minor range imprecision, no contract issue. |
| `plan.md:29`, OneDrive generation/thread/status | `castlib/sources/onedrive.py:219`, `castlib/sources/onedrive.py:286`, `castlib/sources/onedrive.py:303`, `castlib/sources/onedrive.py:350` | Confirmed, including cancellation and late-result generation checks. |
| `plan.md:31`, LRU/crumbs/thumb Upstream | `castlib/sources/onedrive.py:463`, `castlib/sources/onedrive.py:496`, `castlib/sources/onedrive.py:550` | Confirmed; LRU cap 4000 at 46/501. |
| `plan.md:33` and `plan.md:82`, refresh token required at `tokens.py:44` | `castlib/auth/tokens.py:43` | Correct; predicate at 43, return at 44. |
| `plan.md:34`, private config writes | `castlib/config.py:54`, `castlib/config.py:107` | Correct on POSIX; Windows uses per-user profile location, not a proven POSIX 0600 permission equivalent. |
| `plan.md:35`, `items.py:19-23` | `castlib/items.py:19` | Correct Upstream fields: URL, headers, optional opener. |
| `plan.md:36` and `plan.md:84`, `relay.py:31-34` | `castlib/relay.py:31`, `castlib/relay.py:38` | Correct header forwarding; actual default/custom opener choice is at 38. |
| `plan.md:36`, `photos.py:226-231` | `castlib/photos.py:226` | Correct header forwarding and default/custom opener choice. |
| `plan.md:37`, `api.py:293-294` | `castlib/api.py:293`, `castlib/api.py:297` | Correct; header loop extends to 295; opener choice at 297. |
| `plan.md:38` and `plan.md:84`, `net.py:40-47` | `castlib/net.py:28`, `castlib/net.py:42` | Authorization drops on a redirect across scheme/host/port. This is conditional protection, not a proof about the initial URL or all possible headers (F2). |
| `plan.md:38`, secret-carrying calls use NO_REDIRECT | `castlib/net.py:16`, `castlib/sources/onedrive.py:83` | Valid pattern for source/auth calls; media uses BEARER_SAFE or the supplied opener. |
| `plan.md:39`, probe `supervisor.py:336-355` | `castlib/supervisor.py:341` | Correct: resolves URL without forwarding headers to ffprobe. A protected DAV GET would not gain Basic auth from this code. |
| `plan.md:41`, gate steps `app.js:253-258`, `index.html:233-318` | `castlib/ui/app.js:255`, `castlib/ui/index.html:243`, `castlib/ui/index.html:282`, `castlib/ui/index.html:296` | Correct three steps and absence of a server-address form. |
| `plan.md:43`, PHOTO_MIMES `media.py:32` | `castlib/media.py:32` | Exact allowlist correct; code origin, not a Nextcloud-defined product rule (F9). |
| `plan.md:44`, unknown source `media.py:93` | `castlib/media.py:93`, `castlib/media.py:124` | Correct function reference; final unknown-source `None` is specifically at 124. |
| `plan.md:45`, baseline numbers | Re-executed below | Matches in `.venv`; literal system-python commands fail because their modules are not installed. |
| `plan.md:85`, `server.py:3-5`, `:187-191` | `castlib/server.py:3`, `castlib/server.py:187` | Correct dispatch and media capability model; explains why same-machine probe works. |
| `plan.md:87`, link/Copy pattern `index.html:298` | `castlib/ui/index.html:298`, `castlib/ui/index.html:303` | Link and target exist. Current adjacent Copy copies the code, not the link; Phase 3 must explicitly wire Copy link to `login_url`. |

Additional consequential code assumptions outside those sections: dates are not rendered (F3), folders are not appended by Load more (F4), navigation does not preserve the last list on 401 (F5), and neither a Disconnect UI nor a seek UI exists (F1/F8). These were checked in code and locally exercised where applicable.

## Definitions and discriminating assertions

All named Nextcloud tests are future work; `tests/test_nextcloud.py` does not exist yet, as expected before Phase 1. This table evaluates the specified verification contract, not the quality of unwritten assertions. A test must fail for the wrong result in the final column; successful metadata parsing alone is insufficient for UI guarantees.

| Row (`plan.md`) | Origin assessed | Planned test(s) | Required negative/discriminating assertion |
| --- | --- | --- | --- |
| Address (55) | Recorded user decision in the plan; HTTPS advice also matches this conversation | `test_address_normalised`, `test_http_address_refused`, `test_poll_server_http_refused` | Bare host/subfolder preserved, blank/HTTP rejected before any authenticated request. Add full-origin and malformed-authority cases from F2. |
| Account (56) | One active credential and replacement are plan assumptions; “a server” alone does not decide all replacement semantics | `test_connect_verifies_stored` | Assert stored Connect verifies without starting a poll; fresh starts one, repeated Connect returns the same active flow, cancellation/late completion cannot overwrite a replacement. Clarify precedence of `{server}` versus stored/fresh: line 163 says it starts a flow, whereas line 56 permits a fresh one only with `fresh`. |
| Folder root (57) | Protocol constraint, independently supported by [Nextcloud's login-name warning](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html#obtaining-the-login-credentials) | `test_login_name_differs_from_user_id` | Email login must not appear as the DAV user segment; returned user ID must be safely encoded in every root/path/SEARCH scope. |
| Photo (58) | Inherited code allowlist plus product's GIF/raw exclusion, not an API guarantee | `test_hidden_kinds` | JPEG/PNG/HEIC/HEIF/WebP admitted; GIF/raw/PDF/missing MIME absent; unsupported kind logged once without dumping credential-bearing objects. |
| Video (59) | Explicit plan assumption; Graph's video facet is a different mechanism | `test_hidden_kinds` | `video/quicktime` admitted; octet-stream `.mp4` hidden. Use both positive and negative assertions, not only the hidden-file count. |
| Date (60) | Recorded user choice of mtime; UTC date is explicitly decided by the plan | `test_tile_date_from_last_modified` | Exact UTC day, absent/invalid date omitted; test actual tile rendering too (F3). |
| Order (61) | Explicit plan assumption | `test_listing_order` | Folder/media split, case-insensitive ordering and stable ties; do not assert one arbitrary server tie order as a universal guarantee. |
| Page (62) | Explicit plan assumption, informed only in page size by OneDrive | `test_listing_pages`, `test_empty_folder` | Empty, 200 and 201/450 media items, terminal next token, folder visibility across the boundary and actual UI consumption (F4). Decide/refuse malformed or negative offsets. |
| Disconnect (63) | Recorded user choice, with best-effort remote cleanup | `test_disconnect_revokes_then_forgets`, `test_disconnect_unreachable_still_forgets` | Assert DELETE precedes local clear, successful revoke removes only the current token, every HTTP/network failure still clears locally, and warning survives status polls until Connect. UI action/note tests needed (F1). |
| Expired (64) | Protocol 401 plus decided UI behavior | `test_revoked_password_expires` | Source enters expired; the actual failed navigation preserves old items/crumbs; `{}` reconnect starts a new login on the remembered server (F5). Clarify that the source can observe list/OCS 401s; relay/thumbnail HTTPErrors do not automatically mark the Source expired. |

There are 10 rows: the Photo and Video entries share a planned test name. A named test for each row is present, but Account's complete branch matrix and the UI portions of date/page/expired/disconnect are not secured by the currently specified test contracts. The Phase 1 testing strategy's general “every row on degenerate data” should be made concrete as above.

For the secrecy invariant (`plan.md:117`, `plan.md:192`, `plan.md:359`), `test_password_never_in_status` should inspect serialized API responses, error ring, captured stdout/stderr and mocked subprocess arguments, not only `status()`. Inject a synthetic password into an upstream error body too. `CastError.as_dict()` exposes message/hint (`castlib/errors.py:25`); generic API failures print tracebacks and expose exception text (`castlib/api.py:64`), relay failures print exception strings (`castlib/relay.py:62`), and photo/thumbnail errors interpolate exceptions (`castlib/photos.py:240`, `castlib/api.py:304`). Specify that new auth/DAV errors do not include raw credential-bearing responses/records/headers. These are existing output sinks to test, not evidence of a current Nextcloud password leak.

## Independent degenerate walkthrough

Dataset independently constructed for this review: account UID `pat`, email login `pat@example.test`; a Depth-1 response containing the requested collection itself, 201 child folders, `A.JPG` and `a.jpg` with equal mtime, one response repeated with the same file ID, a `Clip.MOV` at a UTC midnight boundary, a missing-MIME file, and an invalid-date file. Also consider an empty folder, a singleton and 200/201/450 admitted media files.

1. Resolve the root using UID, not login: decided; base contract permits a root crumb with null ID (`castlib/sources/base.py:48`). OCS lookup test can prove this without a real login.
2. Ignore the current collection's self response; do not expose it as its own child. Respect successful DAV `propstat` groups and resource type. These are essential parser details absent from the concrete Phase 1 contract; add fixtures/assertions. The [WebDAV documentation](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/WebDAV/basic.html#requesting-properties) explains per-property missing responses; a flat property search is insufficient.
3. Filter unsupported/missing MIME; preserve the invalid-date media tile without a date: decided in Definitions. Current generic filtering needs the new nextcloud branch (`castlib/media.py:93`).
4. Equal names under case folding retain server order, as the plan says stable ties. Do not promise a fixed cross-refresh order unless a secondary key is deliberately added. For a repeated file identity, deduplicate before paging/rendering or reject an inconsistent response: the current tile loop uses `source:id` as its key (`castlib/ui/index.html:406`). The plan should state this parser behavior; no user preference is needed for duplicate wire records.
5. Page 201 folders plus media: current UI loses later folders (F4). The proposed fix keeps folders outside the media page offset. Empty/singleton/exact-boundary pages are otherwise decided.
6. Render the midnight date: source can produce the decided UTC date, but the current metadata renderer omits it (F3).
7. Navigate after revocation: source can raise AuthError; current UI drops the last list before that error (F5).

The material outcomes are covered by F3–F5. The self-response/propstat/duplicate checks are protocol-normalization assertions to add to the Phase 1 fixture contract, not new product features.

## Manual row audit

The shared paragraph at `plan.md:298` identifies Fedora, Chrome and Samsung, but does not supply missing controls or make a hidden gate reachable. Every row remains pending.

| Progress row | Present criterion | Needed correction |
| --- | --- | --- |
| 3.5 | Names cast-tv window, Nextcloud, address, Connect, link, browser Grant access, root-list observation | Mostly concrete. Name the Fedora terminal for `stat`, and spell out the Copy-link fallback: press Copy link, paste into the browser address bar, open, then Grant access. Never display the JSON contents. |
| 3.6 | Chrome Settings → Security, device list, observed token name | Adequate inspection row. Name the Devices & sessions/list section as actually shown when recording the observation; no secret/token value is needed. |
| 3.7 | Folder chain and expected crumbs/thumbnails/date | Say “in the cast-tv window's Nextcloud tab, click folder buttons …”. Choose a concrete HEIC/JPEG test file. The real collection layout is unverified here; check whether MOVs are in the `video` child noted in research before prescribing the exact folder. |
| 3.8 | Cast one HEIC; upright picture on Samsung | Name the window, chosen tile and its Cast now play button (`index.html:413`), with material identifier recorded. |
| 3.9 | Cast OM film, debug 200/206, picture/sound, UI seek | Use the tile's Cast now; name the terminal running cast-tv with debug enabled (current launch instructions omit debug). Use the Samsung remote playback seek control, not a nonexistent cast-tv seek UI, and specify expected position/resumed picture and sound. |
| 3.10 | Three photos and one film complete | Name the tile selection/tick controls, order, Start show button (`index.html:471`), Samsung observations and Show finished in cast-tv. |
| 3.11 | Phone UI, address, Connect, grant, root listing | Specify disconnect/reset first; otherwise the connected tab has no address gate. Name the cast-tv window's Open on your phone panel and chosen LAN address/QR control (`index.html:80`). |
| 3.12 | Chrome revoke, Nextcloud folder open, expired banner, Connect again | Name the specific cast-tv device entry and revoke control in server Security; verify the old list and crumbs survive the failed folder navigation. Fresh login must re-use the remembered address. |
| 3.13 | Nextcloud Disconnect, server entry absent, local file absent | Add the actual UI control and reset path (F1). Name Chrome Security for the device-list observation and the Fedora terminal for the metadata-only file-existence check. |
| 4.2 | Owner reads README/PRD and confirms accuracy | Name the editor/viewer tabs for `README.md` and `context/foundation/prd.md`; expected descriptions include HTTPS, mtime and best-effort revoke behavior. Existing explicit surfaces are appropriate. |

Add the Windows native-window row described in F8 and explicit engine/media surfaces. This review did not perform or claim any of these checks. The existing real-TV/real-login coverage is appropriately broad once the instructions are made executable; no extra TV transcode investigation is required by the goal.

## Automated statuses re-executed

The plan records 11 automated rows, comprising five unique existing commands and one future command. Repeated whole-suite/lint rows were verified once each; rerunning them per phase adds no evidence before implementation.

| Command as recorded | Literal current shell result | With repository `.venv/bin/python` | Assessment |
| --- | --- | --- | --- |
| `python -m pytest` | exit 1: system `/usr/bin/python` has no pytest | exit 0; **675 passed, 6 skipped**, 681 collected | Recorded baseline is true in the project environment. |
| `python -m pyflakes castlib tests` | exit 1: system interpreter has no pyflakes | exit 0, no output | Same interpreter qualification. |
| `python -m pytest tests/test_supervisor.py` | exit 1: no pytest | exit 0; **33 passed** | Existing baseline true; new tests do not exist yet. |
| `python -m pytest tests/test_ui.py` | exit 1: no pytest | exit 0; **32 passed** | Node is present; behavior tests ran rather than being skipped. |
| `node --check castlib/ui/app.js` | exit 0 | n/a | Matches recorded status. |
| `python -m pytest tests/test_nextcloud.py` | Not run | Not run | Correctly marked as requiring Phase 1 output; absent file is expected. |

Tests were run with pytest's cache provider disabled; no expected result, test or product file was changed. This is an environment qualification, not a product test failure or evidence that the recorded 675/6 count was fabricated. Make the plan's setup explicit: activate `.venv` or use its interpreter. The local interpreter reports Python 3.15.2/Expat 2.9.0; the configured CI interpreter is Python 3.12. No new CI or release-build result is claimed.

Additional read-only checks: Node driver reproductions for folder pagination, missing date metadata and revoked-folder navigation; a bounded ElementTree expansion example; declaration/path/Progress comparison; the skill's manual-acceptance parser. No live endpoint or real device was used.

## Review scope and disposition

The next step is to revise the plan and brief for F1–F8, then correct F9's claims. No plan changes or decisions were applied by this review. Definitions, protocol-negative cases and manual acceptance should be updated together so the implementer cannot satisfy the gates while omitting the owner-visible behavior. The owner merges any eventual PR; nothing was committed, pushed or merged here.

## Re-review 2 (2026-11-24)

- **Mode**: Deep
- **Scope**: Whole plan — its hash differs from round 1, which has no `Plan sha256 after triage` or formal `edited:` entries. Re-checked every FIXED decision F1–F9, the revised brief and the changes those fixes introduce.
- **Reviewed HEAD**: `d15ca6ae424dcffa7aad0dde6eac06416803a576`
- **Plan sha256**: `992b8693c2aefb76fc4ef2e03e222f8c6930e5e11cdceaeab5449104f95cdd26`
- **Verdict**: REVISE — seven earlier findings close; F1 and F8 retain narrow gaps, recorded as F10 and F11 below.
- **Findings**: 0 critical, 1 warning, 1 observation
- **Closes**: F2, F3, F4, F5, F6, F7, F9

### Verdicts

| Dimension | Verdict |
| --- | --- |
| Requirement Definition | PASS |
| End-State Alignment | FAIL — Disconnect is still unreachable in one promised state (F10) |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | PASS |
| Plan Completeness | WARNING — the Windows acceptance surface omits its native-window implementation (F11) |

### Grounding

Grounding: 19/19 declared implementation/test/document locations valid (14 existing, 5 intentional creates with existing parents); referenced code symbols traced; brief↔plan consistent; 5/5 unique runnable planning commands match their recorded exit status. All 12 Definitions rows were reviewed, including their origin labels, protocol-normalization rules and degenerate cases. The inherited photo allowlist remains explicitly code-derived; it is not evidence of a Nextcloud guarantee or a new owner decision. Account scope, video filtering and sorting remain stated plan assumptions. No new material requirement ambiguity was found.

Read all 6/6 lesson entries; their session, manual-acceptance, credential and UI rules apply through AGENTS.md or their stated scope (none has a literal `plan-review`/`all` tag). `git fetch` succeeded, remote branches were inspected, and `gh pr list` returned no open PRs. This is the only active change plan; the current branch is `s17-nextcloud`. All four body phases match Progress; automated/manual criterion counts are 4/0, 3/0, 4/11 and 1/1. Progress is at the bottom, with no checked rows or malformed n/a/acceptance suffixes. The skill's acceptance-state script exits 0 and reports all 12 manual rows pending. Every declared manual surface exists or is a planned create; that path check does not prove the declarations are complete (F11).

One focused read-only analysis agent checked the revised shared UI behavior, callers, manual controls and a degenerate listing. The main review verified its findings against the code, and checked origin/authentication rules, XML policy, release integration, probe composition and statuses. No owner server, real TV, credential file or stored token was accessed. No implementation, plan or manual-acceptance mark was changed. The report was appended, change.md was stamped `plan_reviewed`, and those written files were recorded in the skill's Git carry record. Nothing was committed, pushed or merged.

### F10 — Disconnect is still hidden on an expired tab without a list

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: End-State Alignment
- **Location**: Phase 3 §2 (`plan.md:317–325`), Desired End State (`plan.md:91`); residual of F1
- **Detail**:
  The revision adds the actual POST action, state clearing and revoke-error note, but locates Disconnect only in the list header. That header belongs to the `listVisible(tab)` template (`castlib/ui/index.html:329`). `listVisible()` returns false for an expired source without a loaded list (`castlib/ui/app.js:329–332`), a normal state after verifying a revoked credential at startup or opening a fresh browser page. A read-only run through the existing Node driver reproduced `listVisible=false` with no list. Thus implementing the specified header leaves that owner unable to disconnect, contrary to the explicit promise that every connected or expired tab has the control. The current proposed tests do not explicitly require this state.
- **Fix**: Put Disconnect outside the list-only conditional, or add it to the expired gate as well. Extend `test_disconnect_every_source` to cover connected, expired-with-list and expired-without-list states for all four sources, asserting that the rendered control is reachable and invokes the same handler.
- **Decision**: FIXED — Disconnect also on the expired gate (Phase 3 §2); `test_disconnect_every_source` covers connected, expired with a list and expired without a list for all four sources.

### F11 — The Windows acceptance surface omits the native window code

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 manual row 3.15 (`plan.md:379`); residual of F8
- **Detail**:
  The new Windows row correctly requires real native-window sign-in, link/copy behavior, restart/reuse and Disconnect. Its explicit `— surface:` list includes auth, source and UI files, but omits `castlib/window.py`. That module selects WebView2 versus Qt (`window.py:42–47`) and creates/starts the native window (`window.py:241–253`). Explicit mode replaces fallback surfaces, so a later change to this central part of what the owner inspected would not invalidate the row's recorded acceptance. The row remains pending today; this is an acceptance-bookkeeping gap, not evidence that Windows sign-in fails.
- **Fix**: Add `castlib/window.py` to row 3.15's explicit surface declaration (and row 3.5, which also checks native-window link behavior), then rerun the acceptance-state script. Leave all manual rows pending until observations are recorded.
- **Decision**: FIXED — `castlib/window.py` added to the explicit surfaces of rows 3.5 and 3.15.

### Resolution of earlier findings

| Earlier finding | Result | Revised-plan evidence and remaining work |
| --- | --- | --- |
| F1 — Disconnect UI | Partially resolved → F10 | Phase 3 §2 supplies the button/POST, list/selection/verification reset, status refresh and reachable revoke note after clearing the list (`plan.md:315–325`); tests and manual rows now cover it across all four tabs. The expired-without-list gate still needs the control. |
| F2 — Initial credential destination | Closed | Definitions now compare scheme, hostname and effective port for flow URLs, returned server and absolute DAV hrefs, refuse userinfo/malformed addresses and foreign/scheme-relative URLs, and require outgoing URLs to be constructed from the canonical base (`plan.md:67–68`, `:128–130`, `:158–165`, `:188–194`). The decoded root rule applies at a segment boundary; incoming paths forbid dot segments and controls. Redirect stripping is accurately described separately from first-request validation. Negative-origin tests are named; implementation must exercise those rules before sending credentials, rather than treating the existing redirect opener as the validator. |
| F3 — Date rendering | Closed | Tile date defines UTC and missing/invalid omission; Phase 3 explicitly changes `metaOf` and requires the last-modified tooltip and actual UI date assertion (`plan.md:73`, `:331`, `:348`). The HTML file is already in Phase 3's changes; the tooltip needs a binding there because today's metadata spans use only `x-text` (`index.html:225`, `:419`). |
| F4 — Folders lost in pagination | Closed | All child folders arrive on page one; only media use 200-item offsets; later pages reuse a snapshot and a page-less request renews it (`plan.md:76`). The shared handler appends folders as well as items and has a regression test (`:331–332`, `:349`). This covers the 201-folder boundary without requiring later folder pages. |
| F5 — Failed navigation destroys last list | Closed | Navigation commits path/items/folders/crumbs only on success; the new auth code triggers immediate status refresh; the specified regression starts with a populated list and checks preservation plus expired banner (`plan.md:139–140`, `:333–350`). Existing `watchSources` preserves the loaded list on failed/cancelled reconnect (`app.js:212–220`), and `tests/test_ui.py:164–193` already covers that behavior. The plan also names the OneDrive regression. |
| F6 — XML policy | Closed | The parser explicitly forbids DTDs, entities and external references; reads cap+1 and rejects oversize before parsing; handles parse failures generically; names hostile/malformed/oversize/namespace tests (`plan.md:131–136`, `:223–234`). The dependency, module-level import, binary status assertion and release PR trigger are explicit (`:180`, `:203–213`, `:243`). The plan acknowledges that tree memory exceeds wire size and that defusedxml does not replace Expat maintenance. |
| F7 — Probe composition test | Closed | Phase 2 updates the old opposite assertion and requires the diagnostic double to GET/Range-read the relay URL against a Basic-auth-required upstream, checking bytes, header, hint and registration lifetime (`plan.md:260–278`). Custom opener/refresh, downloaded-item and local-path regressions are named. The existing relay forwards the headers and opener (`relay.py:30–38`); `_never_started()` runs before retirement (`supervisor.py:322`, `:367`). |
| F8 — Manual controls, Windows and surfaces | Partially resolved → F11 | Manual rows name actual windows, controls, setup and observations; seeking uses the Samsung remote, phone sign-in begins with Disconnect, and Windows acceptance remains pending (`plan.md:363–379`). Explicit engine/media surfaces replace the old UI-only fallback. Native-window code is still missing from the window rows' surfaces. |
| F9 — Overstated evidence/origins | Closed | The plan distinguishes local OM evidence from the pending Nextcloud relay observation (`plan.md:22`), qualifies diagnosis (`:95–96`, `:264–266`) and revoke (`:77`, `:91–92`) as best effort, distinguishes the media capability from provider credentials (`:137–138`), and labels the inherited allowlist, account scope and order appropriately (`:69`, `:71–74`). The brief makes the same qualifications. |

### Independent walkthrough and blast radius

An independently constructed response has `x.MOV` and `X.mov` in that server order, a repeated file ID, unsupported/missing MIME, a missing-date file, a UTC-midnight date, 201 child folders and 201 admitted media files. Also consider an empty collection and exactly 200 media. The plan decides all outcomes: ignore the collection's self record and unsuccessful propstats, keep the first duplicate ID, hide unsupported kinds, preserve server order for case-insensitive ties, omit missing/invalid dates, and take the UTC day at midnight. Page one contains all 201 folders and the first 200 media; page two contains the last medium, no folders and no next token. Empty/exactly-200 collections have no next token. Current filtering needs the named Nextcloud branch (`media.py:93–124`); current rendering/pagination need the already-planned fixes (`app.js:361–364`, `:679–686`). The additional expired-without-list walkthrough exposes F10; it does not require a new product decision.

Shared callers were traced: folder and crumb buttons use `openFolder` (`index.html:391`, `:398`); initial loading, Refresh and Load more use `loadList` (`app.js:349`, `index.html:359`, `:438`); metadata appears in the current show item and both grids (`index.html:122`, `:225`, `:419`). Disconnect reaches the existing generic API route (`api.py:248–252`) and each source already implements local cleanup. `explain_failure` has one production caller (`supervisor.py:349`); the changed probe target retains relay headers, custom opener/refresh behavior and path-first downloads. No additional unplanned caller or competing pattern was found.

### Commands and external grounding

Commands were rerun in the repository environment, once per unique command. Pytest used `-p no:cacheprovider` to avoid cache writes; no check, test or expected result was skipped or changed.

| Planning command | Re-review result |
| --- | --- |
| `python -m pytest` | `.venv/bin/python`: exit 0, 675 passed, 6 skipped |
| `python -m pyflakes castlib tests` | `.venv/bin/python`: exit 0, no output |
| `python -m pytest tests/test_supervisor.py` | `.venv/bin/python`: exit 0, 33 passed |
| `python -m pytest tests/test_ui.py` | `.venv/bin/python`: exit 0, 32 passed; Node is on PATH |
| `node --check castlib/ui/app.js` | exit 0 |
| Future Nextcloud tests | Not run as recorded: requires Phase 1 output |
| PR release build/smoke | Not run as recorded: external; no PR exists yet |

Public documentation was rechecked only for protocol/parser claims: [Nextcloud Login Flow](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html) supports the separate browser flow, account-id distinction and best-effort client removal; [Nextcloud WebDAV](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/WebDAV/basic.html) supports the authenticated files root and per-property multistatus handling. [defusedxml's maintained documentation](https://github.com/tiran/defusedxml#defusedxml) confirms the three parser flags, including `forbid_dtd=False` by default; [Python XML security](https://docs.python.org/3/library/xml.html#xml-security) still requires attention to the actual Expat runtime, independently of the new parser policy. These checks validate plan feasibility, not the owner's unperformed login/TV/Windows rows.

This requested re-review is saved without plan triage. F10 and F11 remain PENDING; earlier-round text and decisions are preserved.
