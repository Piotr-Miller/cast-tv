# Frame Brief: Cast photos and videos from a Nextcloud server

> Framing step before /rune-plan. This document captures what is *actually*
> at issue, separated from what was initially assumed.

## Reported Observation

The owner wants to cast photos and videos kept on their own Nextcloud server from cast-tv, the
same way they already do from OneDrive.

**Observed / inferred**: the wish is the owner's own statement. That photos cast from Nextcloud is
inferred: the spikes proved listing and thumbnails (JPEG, PNG, HEIC) but cast no photo. That the
owner's films play was inferred, and the third spike contradicted it (an OM camera `.MOV` refused
by every route). A verification after the frame observed the opposite: three OM MOVs, the spike's
own file included, played with picture and sound, seen by the owner (`research.md`, "Verification
after the frame").

## Initial Framing (preserved)

- **User's stated cause or approach**: Nextcloud can be reached under the house rules: sign-in with
  Login Flow v2 (nothing copied), folders browsed over WebDAV (`change.md`, Notes).
- **User's proposed direction**: a Nextcloud source that casts like OneDrive; the local-folder source
  is a separate, later change (s18). Owner decisions 2026-11-24.
- **Pre-dispatch narrowing**: none (the observation was specific).

## Dimension Map

1. **Sign-in**: Login Flow v2 gives cast-tv its own revocable app password. ← initial framing
2. **Browsing**: WebDAV lists folders and files with type, size, date, id and a preview. ← initial framing
3. **Playback route**: the TV plays a Nextcloud file through cast-tv's relay, or from a link the server gives.
4. **Playable material**: the films the owner keeps on Nextcloud play on this TV through cast-tv at all.

## Hypothesis Investigation

| Hypothesis | Falsifier (what would kill it) | Evidence | Verdict |
| --- | --- | --- | --- |
| 1. Sign-in works without copied secrets | the poll never turns 200, or the password cannot be revoked | `research.md` spike 1: 200 after 40 s with `appPassword`, `loginName`, `server`; second poll 404; `DELETE …/core/apppassword` 200, then WebDAV 401. Not found: the falsifier | STRONG (residual: SSO/2FA, an address typed without `https://`, the password's name in Settings) |
| 2. WebDAV browsing like OneDrive | no type, id or thumbnail per file | spike 2: `PROPFIND` 207 with `getcontenttype`, `getcontentlength`, `getlastmodified`, `oc:fileid`; `/core/preview` 200 for JPEG and HEIC, 404 for films; `nc:creation_time` 0 | STRONG (residual: no capture date; paging of a folder with thousands of entries) |
| 3. Playback through the relay | a relayed H.264 film does not play, or the upstream ignores Range | spike 3 route A: upstream 200 then 13 × 206, TV `PLAYING 0:00:12.487 / 0:00:14`, `Finished.`; route B (the direct HTTPS link handed to the TV): `STOPPED` for 20 s. `Upstream.headers` already travels through the relay (`castlib/items.py:19-23`, `castlib/relay.py:31-34`) | STRONG for the relay; the direct route does not play |
| 4. The owner's films play on this TV | an OM camera MOV plays through cast-tv | Against: spike 3, an OM `.MOV` (HEVC Main 10, 3840×2160, 59.94 fps, `pcm_s16le`) went `TRANSITIONING` → `STOPPED` through the relay *and* as a local file. For: `context/archive/2026-09-07-cloud-source-ui/research.md:749`, row 5.4 (2026-09-12), the Olympus `P7242629.MOV` (HEVC 3840×2160, 59.94 fps, 134 Mbit/s) reached `PLAYING` with its position advancing through the OneDrive relay. The cast core (`dlna.py`, `relay.py`, `supervisor.py`, `items.py`) has no commit after 2026-09-19. The September file's profile, bit depth and audio were not recorded, and its local mirror (`~/.onedrive-sync`) no longer exists | STRONG after verification (2026-11-24, 20:00-20:02): `P7242629.MOV`, `PB014001.MOV` and the spike's own `PA313998.MOV` (identical streams: HEVC Main 10 4K60, `pcm_s16le`, `tmcd`) played to `Finished.` as local files, with picture and sound seen by the owner. The spike's refusal is withdrawn and its cause is not established. Residual: an OM MOV through the Nextcloud relay |

## Narrowing Signals

- Asked which films the owner wants from the Nextcloud tab: **OM camera films**. So dimension 4 is
  the main value of the "videos" half of this change, not a side note.
- Asked what the owner has seen when casting an OM film since September: **not sure**. Nothing
  remembered resolved the contradiction between row 5.4 and spike 3.
- Verification (owner's choice after the first version of this brief): the three OM MOVs above
  played, seen on the TV with picture and sound. This settled dimension 4.

## Cross-System Convention

The PRD says "No transcoding; audio codecs the TV cannot decode are reported, not converted"
(`context/foundation/prd.md:174`). The existing report runs `ffprobe` on a refused video
(`castlib/supervisor.py:336-355`, `castlib/diagnostics.py:16-43`). It names bit rates above
60 Mbit/s, an odd aspect ratio, DTS/TrueHD audio and data tracks. It does not name 10-bit HEVC or
PCM audio. For a Nextcloud item it would probe `item.resolve().url` without `Upstream.headers`, so
a WebDAV address answers 401 and nothing is reported. The independent search found this gap too.
A film the TV refuses whatever its source (the OM MOV failed as a local file as well) belongs to
the casting core, not to a source. The leading hypothesis is consistent with that convention: the
source itself follows the OneDrive pattern.

## Discriminator Check

| Proposed experiment | Separates | Conflates | Cost (money / irreversible / wait) | Already answered by |
| --- | --- | --- | --- | --- |
| Find which part of an OM MOV the TV refuses (`research.md` spike 3, "Not yet checked"): cast local variants of one OM MOV with `cast-tv <file>`, each changing one thing (MOV remuxed into MP4; PCM audio replaced by AAC; both) | within dimension 4: the container, the PCM audio and the HEVC 10-bit 4K60 video as the cause of the refusal | nothing, if each variant changes one thing; a variant that changes two moves them together | 0 / none (local copies, deleted after) / minutes per variant, plus getting one OM MOV onto the laptop (from the camera card, or from Nextcloud after a sign-in the owner approves) | nothing found |
| Cast the September file `P7242629.MOV` again, now, through cast-tv | dimension 4: "this kind of film plays" (as in September) against "the TV no longer plays it" (a TV-side change since September) | where the file now lives (OneDrive or Nextcloud), if it is cast from a different source than in September: the source route and the TV's state move together, unless it is also cast as a local file | 0 / none / unknown: where the file is now is unknown | row 5.4 (2026-09-12) answered it once, before today's failure; it does not answer the current state |

## Reframed (or Confirmed) Problem Statement

> **The actual problem to plan around is**: a Nextcloud source that signs in with Login Flow v2,
> browses over WebDAV and casts through cast-tv's relay, as the owner framed it.

The initial framing was correct; proceed with the originally proposed direction. The one
contradiction found (spike 3's "camera films do not play by any route") was checked and withdrawn:
the owner's OM MOVs play on this TV. A small gap remains, but it is not a reframe. When the TV does
refuse a film, the refusal probe (`supervisor.py:341-346`) reads `item.resolve().url` without
`Upstream.headers`, so it would get a 401 for a Nextcloud item and say nothing.

## Confidence

- **HIGH**: strong evidence on all four dimensions, it matches the OneDrive pattern, and the
  verification settled the one contradiction. (The first version of this brief was MEDIUM. Its
  verification steps ran on 2026-11-24, 20:00-20:02, and are recorded in `research.md`.)

Left for the plan's manual rows, not blocking it: an OM MOV through the Nextcloud relay (Actor:
either; the TV picture needs the owner, Actor: user).

## What Changes for /rune-plan

Plan the source as proposed: Login Flow v2, WebDAV, the relay with Basic-auth headers, photo
thumbnails. Films need nothing beyond the relay. The plan should still decide how a refused
Nextcloud film is explained, since the probe loses the password (`supervisor.py:341-346`). It
should also carry a manual row for an OM MOV through the relay.

## References

- Source files: `castlib/sources/base.py:60-68`, `castlib/sources/onedrive.py:523-548`,
  `castlib/supervisor.py:336-355`, `castlib/diagnostics.py:16-43`, `castlib/items.py:19-23`,
  `castlib/relay.py:31-34`, `castlib/app.py:187-188`
- Related research: `context/changes/s17-nextcloud/research.md`;
  `context/archive/2026-09-07-cloud-source-ui/research.md:749` (row 5.4)
- Investigation: all four dimensions are narrow: research.md's spikes settle 1-3, and one section
  of research.md plus one archived row cover dimension 4. They were investigated in this session.
- Lessons: 0 of 6 ledger entries name `frame` or `all`. "Look at every branch and PR before
  building" covers every new change: run (no open PR; `s17-nextcloud` has no commits beyond `main`).
- Pressure test: prior occurrences (`grep` of `context/` for `P7242629`, `hevc`, `10-bit`, `pcm_s16`,
  `.MOV`; `git log --grep=nextcloud`: none), which found row 5.4; inverse check (no cast-core commit
  since 2026-09-19); independent search, prompt as sent:

  ```text
  Observation: the owner wants to cast photos and videos kept on their own Nextcloud server from cast-tv, the same way they already do from OneDrive.
  Surface: the repository root, /home/piotrmiller/Source/cast-tv
  What in this system or design space is most likely responsible? Look without preconception.
  Shell: do not pipe a search into head, tail or grep -v; print the command's exit status before you use its output, and capture the output to a file first when you are allowed to write files.
  ```

  It found the same source plan (the registry at `app.py:187-188`, the OneDrive pattern, the token
  store being OAuth-shaped, the sign-in UI needing a server-address step). Independently, it found
  the refusal probe at `supervisor.py:341-346` dropping `Upstream.headers` (401 on Nextcloud), and
  it named the OM MOVs as the material that would trigger it. It did not find row 5.4.
