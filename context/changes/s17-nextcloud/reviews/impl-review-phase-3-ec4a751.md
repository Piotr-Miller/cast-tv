<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Cast photos and videos from a Nextcloud server

- **Plan**: context/changes/s17-nextcloud/plan.md
- **Scope**: Phase 3 (phases 1–4)
- **Session**: fresh
- **Base**: 4b5e5db (4b5e5db, the previous phase's last commit: Phase 2's impl-review fix F1)
- **Head**: ec4a751 (ec4a751542949b842b9f76f8e589de8ed86280c9, current HEAD)
- **Worktree**: included(context/changes/s17-nextcloud/plan.md) — the Progress SHA write-back ` — ec4a751` on rows 3.1–3.4 only; no other local changes
- **Checks ran at**: ec4a751 (current checkout; the included change is plan bookkeeping only)
- **Manual acceptance**: 0 of 11 confirmed — pending: 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15
- **Date**: 2026-11-24
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING (1 warning, 1 observation) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — A stored Nextcloud sign-in that could not be checked offers only a new sign-in, which leaves the old app password on the server

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/ui/app.js:309 (`addressForm`), castlib/ui/app.js:331 (`canDisconnect`); castlib/ui/index.html:309, :328; with castlib/sources/nextcloud.py:324, :354, :267
- **Detail**: A stored credential that this process has not verified yet has status `disconnected` with `detail.stored = true` (`nextcloud.py:324`). Entering the tab posts `connect({})` once (`enterTab`, guarded by `_verified`). If that check fails with anything other than a 401 — cast-tv started before the Wi-Fi is up, the server briefly down — `connect` raises `UpstreamError` and the state stays `disconnected` + `stored` (only `AuthError` marks it expired, `nextcloud.py:354`). The gate then shows the address form, because `addressForm` excludes only `connecting` and `expired`; the generic **Connect** button that posts `{}` is hidden (`index.html:328`), and **Disconnect** is not offered, because `canDisconnect` is only `connected || expired`. The owner's only action is the prefilled address field + **Connect**, which posts `{server}` and always starts a fresh Login Flow (plan, Account row). On success `_finish_flow` overwrites `nextcloud.json` (`nextcloud.py:267`) without revoking the stored password, so the old app password stays listed and live under Settings → Security, and cast-tv no longer holds it to revoke later. OneDrive in the same state shows **Connect**, which posts `{}` and re-verifies the stored token (`onedrive.py:422-425`). Evidence: a node run through `tests/ui_driver.js` with status `{"state":"disconnected","detail":{"stored":true,"server":"https://cloud.example.test"}}`, `enterTab("nextcloud")` answered with an error, then `connectServer`: `addressForm` = true, `canDisconnect` = false, and the requests were `POST …/nextcloud/connect {}` and then `POST …/nextcloud/connect {"server":"https://cloud.example.test"}`.
- **Fix**: Treat a stored credential as signed in for the gate: `addressForm` is false when `detail.stored` is true, so the gate shows **Connect** (posting `{}`, which re-verifies the stored password, or starts a flow on the stored server when it has expired); `canDisconnect` also returns true when `detail.stored` is true, so the owner can drop that credential (revoking it) and type another address. Add a UI test for this state (stored, the check failed: Connect posts `{}`, Disconnect is offered, no `{server}` request).
  - Strength: Matches the plan's Account row (`connect({})` verifies a stored credential) and OneDrive's behaviour in the same state; no backend change.
  - Tradeoff: To switch to a different server while a stored credential exists, the owner first clicks Disconnect; the address field is not shown next to Connect. The same `canDisconnect` change also offers Disconnect on other sources' stored-but-unchecked gates. That is consistent (there is a file to forget), but it changes those gates as well.
  - Confidence: HIGH — the state, the hidden button and the overwrite were read in code and reproduced in the node driver.
  - Blind spot: Not checked on the real window. A backend guard (revoking the stored password when a new flow replaces it) would also close the leak, but it changes Phase 1's code and was not evaluated.
- **Decision**: FIXED (owner decision 2026-11-24: fix in the UI now) — `addressForm` is false while `detail.stored` is set, so the gate's Connect posts `{}` and checks the stored password again; `canDisconnect` is true for a stored sign-in, on every source. `test_nextcloud_unchecked_stored_sign_in_checks_again` covers it. Deliberate break (the `stored` condition dropped) turned it red; restored, green.

### F2 — While a slow revoke runs, the old list stays on screen with no banner, no Disconnect and no progress

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/ui/app.js:332-349 (`disconnect`), with castlib/sources/nextcloud.py:375, :388 and castlib/auth/loginflow.py:36
- **Detail**: The server detaches locally at once (`_store.clear()` at `nextcloud.py:375`) and then revokes over the network (`nextcloud.py:388`, `TIMEOUT = 30` s). The UI clears the list, the selection and `_verified` only after the POST returns (`app.js:336-338`). Scenario: the owner clicks Disconnect while the server cannot be reached and the connection attempt hangs (a home server seen from another network). For up to 30 s, every status poll already says `disconnected`, so `listVisible` stays true through `l.loaded`, the expired banner does not show (the state is not `expired`), and the header's Disconnect button disappears (`canDisconnect` is false). Nothing says a disconnect is in progress, and the list's folders and tiles still respond to clicks. It settles when the POST returns: the gate appears with the revoke note. Evidence: a node run with the disconnect POST held and the status switched to `disconnected` gave `listVisible` = true, `expired` = false, `canDisconnect` = false and the old item still listed, then `listVisible` = false after the release.
- **Fix**: In `disconnect()`, clear the list, the selection, `_verified` and the chooser before awaiting the POST (the server detaches locally whatever the revoke does), and show "Disconnecting…" on the button while `busy.connect` is set; extend `test_disconnect_shows_revoke_error` with a held POST.
- **Decision**: FIXED (owner decision 2026-11-24: fix now) — `disconnect()` clears the list, the source's tiles in the selection, `_verified` and the chooser before the POST; `disconnecting` names the source meanwhile, its gate shows **Disconnecting…**, other tabs are untouched. `test_disconnect_clears_the_list_before_the_server_answers` holds the POST. Deliberate break (clearing moved after the answer, the gate guard removed) turned it red; restored, green. Gate after both fixes: `node --check` exit 0; `tests/test_ui.py` 46 passed; full suite 756 passed, 6 skipped; pyflakes exit 0.

## Review Notes

- **Bookkeeping in diff**: context/changes/s17-nextcloud/plan.md (committed in ec4a751: rows 3.1–3.4 ticked; worktree: their ` — ec4a751` suffixes).
- **Plan drift**: `app.js` / `index.html` gate — MATCH: `SOURCES`/`GATES` entries, `serverInput` prefilled once from `detail.server` (and never over what the owner typed), `connecting()` accepts `login`, the hint line, the link with `target="_blank"`, **Copy link** copying `login_url`, **Cancel**, minutes left, the refusal in `gateNote` (lesson "A message from a user action is not owned by the status poll" respected), and the app-password note. Disconnect — MATCH: the list header and the expired gate (re-review F10), for all four sources; it clears the list, the selection tiles, `_verified` and the chooser, refreshes, and shows the gate; `revoke_error` is shown on the gate. Date, paging and failed navigation — MATCH: `metaOf` and `metaTitle` for Nextcloud only (both tile kinds bind the tooltip); Load more appends folders, once per id; `openFolder` replaces path, items, folders and crumbs only after a successful answer; `nextcloud_unauthorized` is in `AUTH_CODES`. Tests — MATCH: all 12 named tests exist. `tests/ui_driver.js` gains `bodies` and the copied text: test infrastructure for the named tests, not scope creep. No unplanned files.
- **Extra guard, beneficial**: `loadList` drops an answer whose list was deleted by a Disconnect meanwhile (`this.lists[name] !== l`), on success and on failure.
- **Race checked, not a finding**: Disconnect writes its answer into `status.sources` while a poll may be in flight. A node run with a poll held across a Google Photos Disconnect showed the stale `connected` status landing and one extra list GET, which healed on the next poll (`picks_seq` changes; the other sources answer `no_token`, which is in `AUTH_CODES`). The driver hands the same status object back on every poll, so a test must set a new `status` step before the held poll to see this.
- **`target="_blank"` in the desktop window**: the same pattern as OneDrive's link. pywebview opens external links in the system browser by default (`OPEN_EXTERNAL_LINKS_IN_BROWSER`); `window.py` does not change that setting. Row 3.5 proves it on the real window.
- **`login_url` in `href`**: the backend takes it only from a same-origin HTTPS answer (Phase 1), so a `javascript:` URL cannot reach the attribute. Every other server text goes through `x-text`.
- **Copy**: the Disconnect tooltip says "Forget this sign-in on this computer"; on Nextcloud it also revokes on the server. Owner wording, not a finding.
- **3.1**: `node --check castlib/ui/app.js` exited 0.
- **3.2**: `.venv/bin/python -m pytest tests/test_ui.py` exited 0: `44 passed in 5.23s` (32 at planning + 12 new).
- **3.3**: `.venv/bin/python -m pytest` exited 0: `754 passed, 6 skipped in 58.07s`.
- **3.4**: `.venv/bin/python -m pyflakes castlib tests` exited 0, no output.
- **Acceptance script**: `bash .claude/skills/rune-impl-review/scripts/acceptance-state.sh context/changes/s17-nextcloud/plan.md` exited 0; rows 3.5–3.15 and 4.2 are `pending`, none stale or unverifiable. Phase 3's rows 3.5–3.15 are counted in the header.
- **Lessons**: 6 of 6 entries read (the ledger is 5 KB). Applicable here: the polled-UI message rule (respected: `gateNote` for the refused address; the revoke note comes from the status, which is server state) and the manual-row observation rule (nothing ticked). The owner-step rule: rows 3.5–3.15 name the window, the control and what should be seen.
- **Mutation check**: skipped — no mutation tool is configured in `pyproject.toml` or `context/foundation/test-plan.md`.
- **Uncommitted workflow output**: this report is carried for the next implementation commit. `change.md` already reads `updated: 2026-11-24` and stays `implementing` (phase review), so it was not modified. Triage was run afterwards in the implementing session (2026-11-24): F1 and F2 FIXED.
