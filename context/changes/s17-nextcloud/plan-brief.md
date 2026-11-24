# Cast photos and videos from a Nextcloud server — Plan Brief

> Full plan: `context/changes/s17-nextcloud/plan.md`
> Frame brief: `context/changes/s17-nextcloud/frame.md`
> Research: `context/changes/s17-nextcloud/research.md`
> Review: `context/changes/s17-nextcloud/reviews/plan-review.md` (REVISE, F1-F9; this revision answers it)

## What & Why

> **The actual problem to plan around is**: a Nextcloud source that signs in with Login Flow v2,
> browses over WebDAV and casts through cast-tv's relay, as the owner framed it.

The owner keeps photos and the OM camera films on their own Nextcloud and wants to cast them the
way OneDrive works today, without copying any secret.

## Starting Point

Three spikes on the owner's server (Nextcloud 34.0.5) proved the sign-in, the listing with previews
and an H.264 film through the relay. A check after the frame showed the OM MOVs play on the Samsung
as local files; through the Nextcloud relay they are still to be seen (row 3.9). The UI has no
Disconnect control, shows no tile dates, drops folders on Load more and loses the list on a failed
folder open; this plan fixes what the new tab needs.

## Desired End State

A Nextcloud tab: type the server address, approve in a browser on any device, browse folders with
previews and dates, cast photos (HEIC converted) and films (relayed with Range), run slideshows.
Every signed-in tab can be disconnected; on Nextcloud that revokes cast-tv's app password when the
server answers. A refused remote film's diagnosis reads the film through cast-tv's own address.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Sign-in | Login Flow v2; cast-tv's own revocable app password | nothing copied; proven on the owner's server | Frame / Research |
| Playback | through the relay with Basic auth; never a direct link to the TV | route B did not play | Research |
| Server address | HTTPS only; bare host gets `https://`; subfolder kept; `http://` and userinfo refused | the password never crosses a network unencrypted | Plan (owner) |
| Credential origin | every URL that carries or receives the password must match the base's scheme, host and port; outgoing URLs are built by cast-tv | the redirect guard alone does not check the first request | Review F2 |
| XML | `defusedxml` with `forbid_dtd`, `forbid_entities`, `forbid_external` all set; refuse answers over 32 MiB before parsing | a parser policy that does not depend on one machine's Expat | Plan (owner), review F6 |
| Release check | `defusedxml` in `pyproject.toml`; the smoke test asserts the `nextcloud` source; `pyproject.toml` triggers the release build on PRs | prove the Nuitka file carries the new dependency | Plan (owner) |
| Tile date | last-modified date, on Nextcloud tiles only, tooltip "last modified" | free from the listing; other sources keep their tiles | Plan (owner), review F3 |
| Disconnect | a control on every signed-in tab; Nextcloud revokes on the server, then forgets locally even if that fails, and says so | the API route existed with no UI | Plan (owner), review F1 |
| Paging | all child folders on page one; media 200 per page from one snapshot | the shared Load more keeps only page one's folders | Review F4 |
| Failed folder open | the old list stays until a new one arrives | the expired banner must sit over the last list | Review F5 |
| Refused-film probe | ffprobe reads cast-tv's media URL for every remote film; a diagnosis stays best effort | one fix for all sources; no provider credential on a command line | Plan (owner), review F7, F9 |
| Credential file | a new app-password store, `nextcloud.json`, 0600 on POSIX | `TokenStore` drops files without a refresh token | Plan |
| WebDAV user | read from `/ocs/v2.php/cloud/user`, not the login name | a login by email would break the path | Plan |

## Scope

**In scope:**
- Login Flow v2 sign-in from the window or the phone; verify, cancel, expired, best-effort revoke
- WebDAV folders, crumbs, paging, previews, film placeholders, Nextcloud dates
- Casting photos, films and slideshows; the refusal probe for remote films
- Disconnect on all four tabs; the shared list fixes
- `defusedxml`, the smoke assertion, the release trigger; README, PRD and roadmap lines

**Out of scope:**
- Plain HTTP, several servers or accounts; EXIF dates; video thumbnails; a bitrate warning
- Dates on other sources' tiles; direct links to the TV; SSO beyond the browser login; s18

## Architecture / Approach

`castlib/auth/loginflow.py` (network calls, the address and origin rules) and
`castlib/auth/apppassword.py` (the credential file) feed `castlib/sources/nextcloud.py`, a `Source`
registered in `app.py` that parses WebDAV with `defusedxml`. Media, photos and previews reuse
`Upstream.headers` through `BEARER_SAFE`; the source's own calls use `NO_REDIRECT`; all start from
URLs built on the canonical base. The supervisor probes refused remote films at
`server.media_url(item)`. The UI adds the address field and `login` step, Disconnect for all tabs, and
the date, paging and navigation fixes.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. The Nextcloud engine | flow, credential file, WebDAV source, `defusedxml`, release check, scripted-server tests | WebDAV shapes on other servers; the release build on the PR |
| 2. Refusal probe | ffprobe reads the relay for remote films | changes the probe path for OneDrive, GoPro, Google Photos too |
| 3. The tab and shared UI fixes | gate, login step, Disconnect everywhere, date, paging, navigation; 10 Fedora rows, 1 Windows row | how each desktop window opens the login link |
| 4. Documents | PRD FR line, roadmap S-17, README | — |

**Prerequisites:** the owner's server reachable; the Samsung on; Chrome signed in to Nextcloud; a Windows visit for row 3.15.
**Estimated effort:** ~4 sessions: Phase 1 is the bulk; Phase 3 adds a sitting of manual rows; Windows waits for a visit.

## Open Risks & Assumptions

- The cast-tv window may not open `target="_blank"` links in the system browser; **Copy link** is the fallback (rows 3.5, 3.15).
- What the app password is called under Settings → Security is unknown until row 3.6.
- A folder with thousands of entries is one large `PROPFIND`; 32 MiB bounds the wire, not the parsed tree.
- Order inside a folder (folders, then names) and one account at a time are plan assumptions the owner can overturn.

## Success Criteria (Summary)

- The owner connects their server from the window and the phone (and on Windows) without copying anything.
- An OM film and a HEIC photo from Nextcloud play on the Samsung; a slideshow runs to its end; the remote seeks.
- Disconnect removes cast-tv from the server's Settings → Security, or says it could not.
