# Frame Brief: Cast an album from a Google Photos share link (S-15)

> Framing step before /rune-plan. This document captures what is *actually*
> at issue, separated from what was initially assumed.

## Reported Observation

The owner wants "wiele zdjęć/filmów za jednym linkiem" ("many photos/videos behind one link",
2026-10-13, `context/foundation/roadmap.md:189-191`). Today a pasted album link is refused with
`album_link` (`castlib/sources/sharelink.py:196-197`, message at `:50-51`).

**Observed / inferred**: the refusal is observed: it is S-09's designed behaviour, measured on
`PpeVYpY5J4QkpYm99`. The need comes from the owner's words, not from an observed failure.
Answered 2026-10-15: the albums the owner means are **his own**, and they hold **a few to a few
dozen items**. The owner **has not tried** selecting an album's items in the Google picker. So
"a link is needed" is inferred.

## Initial Framing (preserved)

- **User's stated cause or approach**: the roadmap's ideas (`roadmap.md:201-202`): "list the
  album's items as tiles in the Google Photos tab, each resolved like a pasted single-item link;
  a slideshow of the whole album". The PRD scopes share links to "other people's libraries"
  (`context/foundation/prd.md:133-136`, FR-012).
- **User's proposed direction**: plan S-15 on the share-link path. After the spikes, the agent
  framed the open choice as "read items from the album page's data entries vs. from item pages,
  and how far to rely on undocumented keys" (session, 2026-10-15).
- **Pre-dispatch narrowing**: none; the observation was specific. The source and size of the
  albums were asked in Step 4.

## Dimension Map

The observation could originate at any of these dimensions:

1. **Item resolution through the item link** - each album item becomes a tile resolved like a
   pasted single-item link (`shared()` on `/share/<id>/photo/<item>`), and refreshed the same way
   (`castlib/sources/gphotos.py:768, 808, 832`).  ← initial framing
2. **Item list and kinds from album-page data** - one fetch of the album page yields every item's
   base and kind, via undocumented data keys.
3. **Path: the picker already covers the owner's albums** - the albums are the owner's own, and
   the Picker (multi-select, `castlib/sources/gphotos.py:1-20`, `cloud-source-ui/research.md:81`)
   may already put many of their items on the TV, so the link path would only matter for other
   people's albums.

Album size and paging is not on the map. For albums of a few dozen items (Step 4) it cannot produce
the observation; it stays an open question for the share-link path (`roadmap.md:198`).

## Hypothesis Investigation

| Hypothesis | Falsifier (what would kill it) | Evidence | Verdict |
| --- | --- | --- | --- |
| 1. Each item resolves like a single-item link | An item page without the Open Graph tags `shared()` reads - **found** | `research.md` spike 1: 5/5 item pages have only `og:site_name`; `shared()` returned motion photos as `video` and plain photos as `no_stream` | NONE |
| 2. The album page gives every item and its kind | An item missing from the entries, an entry base not serving the item, or no kind signal - **not found** on 9 entries in 2 albums | `research.md` spikes 1-2: every item base is on the album page; video key `"76647426"`, motion photo key `"146008172"`; bases pass `allowed()`. Undocumented: one video, one day of measurements | STRONG (for the link path), undocumented |
| 3. The picker already covers own albums | The picker cannot select an album's items without one-by-one picking, or its sign-in cannot be used on the host | No document in the repo says whether the picker selects a whole album (searched `context/`). Multi-select is documented in-repo (`cloud-source-ui/research.md:81`). The owner has not tried it (Step 4). S-10 names a test-user list and a 7-day refresh-token expiry (`roadmap.md:101-105`); S-08's rows passed on "a non-tester Google account" and a token that refreshed after 24 days (`roadmap.md:77-80`) | WEAK - unverified either way |

## Narrowing Signals

- The owner's albums are his own (Step 4). The PRD gives share links the job of "other people's
  libraries" (FR-012), and S-09's brief motivates links as a way around "a sign-in and the
  picker" for "a photo someone shares" (`s09-share-link-photos/plan-brief.md:8-9`). For own items,
  the system's existing route is the picker.
- Albums hold a few to a few dozen items (Step 4). That is far below the show's 500-item cap
  (`castlib/api.py:22`), and paging is unlikely to bite at that size.
- The owner has not tried the picker on an album (Step 4). That leaves dimension 3 open: a
  verification question, not a memory question.

## Cross-System Convention

In this codebase, each kind of access has its own route: the picker for the owner's library (a
documented API), share links for other people's items (scraped, measured, undocumented). The
initial framing puts the owner's own albums on the scraped route. That is outside the convention,
and nothing yet shows the documented route fails for them. An independent search, given only
the observation, reached the same alternative ("the test album appears to be the owner's own …
its items might already be pickable in bulk") and the same open points: picker album
selection, paging, refresh through the album page, stability of undocumented data.

## Discriminator Check

| Proposed experiment | Separates | Conflates | Cost (money / irreversible / wait) | Already answered by |
| --- | --- | --- | --- | --- |
| Large-album paging spike (`roadmap.md:198`, `research.md` "Not yet checked") | completeness of dimension 2 on large albums | nothing | 0 / creating a large public album (unpublishable later; exposure while public: unknown) / minutes | nothing found |
| Picker album selection: Google's Picker docs read today, then a pick on the host | dimension 3 holds vs. fails, which decides whether dimensions 1-2 serve the owner's need | the doc reading and the live pick can disagree; they are two halves of one spike | 0 / none (a picker session) / minutes, plus a Google consent round if the host's consent has lapsed (state unknown) | nothing found (repo documents multi-select only) |

## Reframed (or Confirmed) Problem Statement

> **The actual problem to plan around is**: getting many items of the owner's **own** album onto
> the TV in one go. Whether that needs the share-link scraper at all depends on whether Google's
> picker can already select an album's items - unverified.

The initial framing assumed the share-link path and planned how items resolve on it. The spikes
killed its first half (item links do not resolve as single links). The owner's answers then
moved the need onto the route the system already has for his own library. If the picker selects
a whole album, S-15 may shrink to little or nothing for the owner, and the scraper (dimension 2,
undocumented keys) stays for other people's albums, which nobody has asked for yet. If it cannot,
the share-link path is the road, and dimension 2 is its source.

## Confidence

**MEDIUM.** Dimension 1 is dead on strong evidence, and the reframe survived an independent search.
But the pivot (dimension 3) rests on an unverified vendor capability. Verify before planning:

- Read Google's Picker API documentation today for album or select-all support in the picking
  UI, with quotes, URLs and read-dates (`/rune-spike s15-share-link-album`) — Actor: agent
- Start cast-tv on the host and complete the Google consent for the Google Photos tab if it has
  lapsed — Actor: user
- Open a picker session and try to select all items of one of the owner's albums. Record
  whether it can be done and how many clicks it takes — Actor: either
- Decide whether S-15 still serves the owner if the picker covers it, or should be re-scoped
  to other people's albums or parked — Actor: user

## What Changes for /rune-plan

If the picker selects albums, the plan is about the picker route: perhaps a show over a picked
set, perhaps nothing. If it does not, the plan builds the album path on the album page's data
entries, not on item links, and carries the undocumented-data risk explicitly.

## References

- Source files: `castlib/sources/sharelink.py:45-51, 186-198, 280-304`;
  `castlib/sources/gphotos.py:754-842`; `castlib/api.py:22, 128-141`;
  `castlib/supervisor.py:417-419`
- Related research: `context/changes/s15-share-link-album/research.md` (spikes 1-4, 2026-10-15)
- Prior decisions: `context/foundation/prd.md:133-136`;
  `context/archive/2026-10-13-s09-share-link-photos/plan-brief.md:8-9, 34-38`;
  `context/archive/2026-09-07-cloud-source-ui/research.md:81`
- Investigation: dimensions 1-3 checked in this session, not delegated (evidence came from the
  spikes and a direct read of the code)
- Pressure test: independent search (Explore agent given only the observation and the repo
  root), which landed on the same alternative; prior occurrences searched in `context/`. Lessons:
  0 of 6 ledger entries name `frame`/`all`; "Look at every branch and PR before building" (every
  new change) was applied - `git fetch`, no other remote branch, no open PR
