# Research: s15-share-link-album

2026-10-15. No codebase research was run for this change; the blocking question was external.
Spikes below.

## Spike: Does an album item's page answer as a single shared item's page does? (2026-10-15, 19:48)

Run from this machine (Fedora, home network) through cast-tv's own guarded opener
(`sharelink.opener()`: https on Google hosts only, no cookies, no sign-in), against the S-09 test
album `photos.app.goo.gl/PpeVYpY5J4QkpYm99` ("OM-1 Mayrhofen", five items). "As a single item
does" means what S-09 measured and `sharelink.shared()` relies on: 200, Open Graph tags that name
the kind (`og:video*` or only `og:image`), and an `og:image` base whose `=d` / `=m37` serve the
item.

**What the previous source said.** `context/foundation/roadmap.md:198` - "**To find out:**
whether each item's page (`/share/<id>/photo/<item>?key=…`) answers as a single shared item does"
(roadmap `updated: 2026-10-14`). The measurement it rests on,
`context/archive/2026-10-13-s09-share-link-photos/research.md:98-110` (2026-10-13), counted the
item links on the album page but never fetched one: "Not measured: an album holding exactly one
item, and an album whose cover is a video." No prior claim about the item pages themselves was
found in `context/changes/`, `context/archive/` or `context/foundation/`.

**Documentary half.** Google documents what a link grants, not what its pages hold.

- **A link grants viewing to anyone holding it** - "When you share a link to your photos, anyone
  with the link can view them."
  (https://support.google.com/photos/answer/6131416?hl=en&co=GENIE.Platform%3DDesktop, read
  2026-10-15). The page does not say whether viewers must sign in, and does not describe the
  address of a photo inside a shared album or any machine-readable form of the page.
- **The API route to shared albums is gone** - shared-album functions "will return a
  `403 PERMISSION_DENIED` after March 31, 2025", and the advice is "Direct users to the Google
  Photos app to manage sharing themselves." (https://developers.google.com/photos/support/updates,
  read 2026-10-15). The page does not mention share links.
- **The legacy guide speaks of the album only** - "a shareable URL is generated that anyone can
  use to access the album" (https://developers.google.com/photos/library/legacy/guides/share-media, last
  updated 2026-09-15 UTC by its footer, read 2026-10-15). It documents no item-page address, no HTML and
  no Open Graph content.
- **The documentation does not say** what `/share/<share id>/photo/<item id>` serves. Everything
  below is measured, not documented, and may change without notice.

**Empirical half.** Three probe scripts in the session's scratchpad (not committed):
`probe_album_items.py` (each item page: status, Open Graph tags, `page_kind()`, `album_items()`,
`og_image_base()`, then `sharelink.shared()` on it), `probe_bases.py` (every media base on each
page, `=d` and `=m37` asked with `probe_media()`), `probe_sizes.py` (`=d` with
`Range: bytes=0-65535`: the `Content-Range` total and a SHA-256 of those first 64 KiB). The share
key is never printed; ids are shortened here.

```
PYTHONPATH=. python3 <scratchpad>/probe_album_items.py https://photos.app.goo.gl/PpeVYpY5J4QkpYm99
PYTHONPATH=. python3 <scratchpad>/probe_bases.py https://photos.app.goo.gl/PpeVYpY5J4QkpYm99
PYTHONPATH=. python3 <scratchpad>/probe_sizes.py https://photos.app.goo.gl/PpeVYpY5J4QkpYm99
```

- **The album page is unchanged since S-09:** 200, 1 110 291 chars, `og:description` "Shared
  album · Tap to view!", `page_kind()` `photo`, `album_items()` 5.
- **Every item page answers 200 without cookies** at
  `photos.google.com/share/<share id>/photo/<item id>?key=<the album's key>`, with no further
  redirect, about 1 066 300-1 066 800 chars, 0.53-0.78 s each.
- **An item page carries no Open Graph media tags.** The only `og:` tag on all five is
  `og:site_name` "Google Photos" - no `og:image`, no `og:video`, no `og:title`, no
  `og:description`. So `page_kind()` answers `None` and `og_image_base()` `None` on every one;
  `album_items()` answers 1 (the page links only itself).
- **`sharelink.shared()` gets them wrong.** With `page_kind()` `None` it probes the page as a
  video: items 1 and 3 came back `kind=video` (a `video-downloads.googleusercontent.com` address,
  4 MB and 3 MB), items 2, 4 and 5 raised `NotMedia no_stream`. All five are photos (`=d`
  `image/jpeg` below); items 1 and 3 are motion photos (`=m37` 206 `video/mp4`, 482 KB and
  246 KB), so the "video" was each one's embedded clip - the trap S-09 closed for single links.
- **Each item page carries the item's own base, first.** Three distinct bases per item page: the
  item's (first on the page, at char ~1 053 000), one 4 273-byte JPEG shared by all six pages
  (`…YdRLSw`, not identified), and a second address whose `=d` gives the same `Content-Range`
  total and the same first-64-KiB SHA-256 as the first:

  | Item | First base | `=d` total (B) | Second base, same total and hash | `=m37` |
  | --- | --- | --- | --- | --- |
  | 1 | `…l2AIpe` | 6 666 854 | `…HEbINA` | 206 `video/mp4` |
  | 2 | `…MmwCzl` | 3 115 330 | `…dko5ng` | no |
  | 3 | `…JQP9nz` | 5 405 094 | `…2RaJlg` | 206 `video/mp4` |
  | 4 | `…b0-L5X` | 1 975 033 | `…2n7-uA` | no |
  | 5 | `…nBOUxc` | 959 949 | `…tXr9QQ` | no |

- **The album page already carries all five item bases.** Its six bases are the five "first
  bases" above plus `…YdRLSw`; its `og:image` base is `…JQP9nz` (item 3), and the others follow in
  item-link order (1, 2, 4, 5). Fetching the item pages added no media the album page lacked,
  only the second address per item.
- **The cover's size differs from S-09's note.** S-09 recorded the cover's `=d` as 6 666 854 B
  (`s09-share-link-photos/research.md:104`); today the `og:image` base answers 5 405 094 B and
  6 666 854 B is item 1. Whether the cover changed or S-09 read a different base was not chased.

**Not yet checked:** an album item that is a video (all five here are photos) - what its item
page and its base answer; whether the album page lists every item's base on a large album
(roadmap's paging question, its own spike); a one-item album and a video-cover album; whether an
item page answers without `?key=`; whether the item-link order and base order hold on other
albums; whether the two addresses per item are the same file end to end (only the total size and
the first 64 KiB were compared); the `…YdRLSw` 4 KB image; a page served in another language;
the S-09 cover-size discrepancy above.

**What this settles:** no - an album item's page does not answer as a single shared item's page
does: it is reachable (200, no cookies) but has no Open Graph media tags, so `shared()` misreads
it (motion photos as videos, plain photos as `no_stream`); each item's media is still reachable
through the base that page - and the album page itself - carries, which unblocks deciding how
S-15 reads an album's items.

## Spike: Can a video item in an album be told apart from a motion photo, from what cast-tv fetches without cookies? (2026-10-15, 20:35)

Run as the spike above (`sharelink.opener()`, no cookies), against a test album made for this
spike: `photos.app.goo.gl/aMWZSeAZQKdE8cdZ6` ("cast-tv S-15 probe: video cover", four items -
one motion photo, two plain photos, and the video of `photos.app.goo.gl/KwhGzcxkNtQpudc46`, which
was the control). The album was created in Chrome on the Google account Stefan Bocian, at the owner's choice,
from items that were already shared publicly; no new item was exposed.

**What the previous source said.** `context/changes/s15-share-link-album/research.md:89` -
"**Not yet checked:** an album item that is a video (all five here are photos)" (2026-10-15, the
spike above). `context/archive/2026-10-13-s09-share-link-photos/research.md:63-65` - on a video
base `=d` "also answers with a photo - the page's tags, not `=d`, say what the link is"
(2026-10-13). The spike above found that an item page has no such tags.

**Documentary half.** No new read: the spike above read Google's pages today (2026-10-15).
They do not describe share pages, item pages or their data, so everything below is measured, not
documented.

**Empirical half.** Four scratchpad scripts (not committed): `probe_video_item.py` (album page,
each item page and the single video link: Open Graph tags, every media base and
`video-downloads` address, `=d`/`=dv`/`=m37`/`=m22`/`=m18` asked with `Range: bytes=0-1`),
`probe_isvideo.py` (`data-isvideo` and each item's data entry on four pages),
`probe_entries.py` and `probe_entry_bases.py` (each album-page entry `["<item id>",["<base>",w,h,…]…]`,
its keys, and what its base answers). Share keys are never printed.

```
PYTHONPATH=. python3 <scratchpad>/probe_video_item.py https://photos.app.goo.gl/aMWZSeAZQKdE8cdZ6 https://photos.app.goo.gl/KwhGzcxkNtQpudc46
PYTHONPATH=. python3 <scratchpad>/probe_entry_bases.py https://photos.app.goo.gl/aMWZSeAZQKdE8cdZ6
PYTHONPATH=. python3 <scratchpad>/probe_entry_bases.py https://photos.app.goo.gl/PpeVYpY5J4QkpYm99
```

- **The suffixes do not tell them apart.** A video's base and a motion photo's base answer the
  same kinds: `=d` 206 `image/jpeg`, `=dv` 200 `video/mp4`, `=m37`/`=m22`/`=m18` 206
  `video/mp4`. Only the sizes differ: on this album the video gave `=dv` 3 553 208 B and `=m37`
  3 482 294 B, the motion photo 3 802 686 B and 493 681 B.
- **The album page's data marks a video.** Each item has a data entry on the album page,
  `["<item id>",["<base>",<width>,<height>,…]…,{…}]`. Only the video's entry has the key
  `"76647426"`: `[8335,null,1080,1920,null,4,134,…]` (the tile shows 0:08). The single video
  link's entry for the same video has it too: `[8264,null,1080,1920,…]`. In both albums (nine
  entries), every motion photo's entry, and only those, has `"146008172":[null,2415]` (the same
  2415 on all three). Plain photos have neither key. `"76647426"` occurs once in the video-cover
  album's page and never in the OM-1 album's (no video there).
- **The item page marks it too.** On the video's item page, the element that carries its base
  has `data-isvideo="true"` and `data-width="1080" data-height="1920"`. The other three item pages
  have no `data-isvideo`. Neither album page has a `data-isvideo` attribute, so it is an
  item-page signal only.
- **The video's base serves the same file as the single link.** `=dv` gives 3 553 208 B and
  `=d` 408 133 B both from the album entry's base and from the single link's `og:image` base,
  the same totals S-09 recorded for this video
  (`s09-share-link-photos/research.md:62-63`). `=m37` differs: 3 482 294 B from the album
  base, 3 538 143 B from the single link's base, both `video/mp4` (codec not inspected).
- **The entry's base is an allowed address.** All nine entry bases are on
  `lh3.googleusercontent.com`, pass `sharelink.allowed()` and match the base pattern of
  `candidates()`.
- **The video's item page has a ready address.** It has one `video-downloads.googleusercontent.com`
  address, answering 200 `video/mpeg` (not `video/mp4`) and 3 553 208 B. The motion photo's
  item page has two: one 200 `video/mp4` 3 802 686 B (its clip), one 500.

**Not yet checked:** what `"76647426"` and `"146008172"` mean beyond this co-occurrence. That
8335 is a duration in ms is a guess from the 0:08 tile, and so is everything else about them.
Also not checked: a second video item, a video longer than a few seconds, or one recorded on
another device; whether the keys are stable across days or page languages; the codec of the
album base's `=m37`; why the same video's `=m37` totals differ between the two bases; a large
album.

**What this settles:** yes - a video item can be told apart, but only through undocumented page
data. On the album page its entry carries `"76647426"` and a motion photo's carries
`"146008172"`; on its item page, `data-isvideo="true"`. Its base serves the same `=dv` file as a
single video link. The suffixes alone cannot tell a video from a motion photo. This unblocks the
frame's choice of where S-15 reads an album's items and their kinds.

## Spike: Does a one-item album pass as a single item? (2026-10-15, 20:38)

Run as above, against `photos.app.goo.gl/3Vf4CXxQfyeQ4Jgb7` ("cast-tv S-15 probe: one item",
one plain photo from the OM-1 album, made for this spike as above). The control was the S-09
single photo link `photos.app.goo.gl/QT9rQWxXYDDfSpKD8`.

**What the previous source said.** `context/foundation/roadmap.md:98-99` - "a one-item album is
handled as its item" (roadmap `updated: 2026-10-14`). That was S-09's design (`album_items() > 1`
refuses), but no one-item album had been fetched: "Not measured: an album holding exactly one
item" (`s09-share-link-photos/research.md:112`).

**Documentary half.** As above: not documented.

**Empirical half.** Inline script: Open Graph tags, `<title>`, `page_kind()`, `album_items()`,
then `sharelink.shared()` on both links.

- **The two pages differ only in their text.** One-item album: 200, 1 100 413 chars, `og:title`
  "cast-tv S-15 probe: one item · Friday, Feb 6 📸", `og:description` "Shared album · Tap to
  view!". Single photo: 200, 1 097 136 chars, `og:title` "New photo · Sunday, Sep 27 📸",
  `og:description` "Tap to view!". Both answer `page_kind()` `photo` and `album_items()` 1.
- **`shared()` handles the one-item album as its photo:** `kind=photo`, `=d` `image/jpeg`
  "2 MB" (the OM-1 photo gives 1 975 033 B), `clip=False`. The control gives `kind=photo`, `=d`
  "1 MB".

**Not yet checked:** a one-item album whose item is a video or a motion photo; a page in another
language (the `og:description` is the only signal and it is English text).

**What this settles:** confirmed - a one-item album passes as its item through today's
`shared()`, as the roadmap says, and only `og:description` ("Shared album") tells it apart.

## Spike: Does a video cover put `og:video` on the album page? (2026-10-15, 20:35)

Measured in the same run as the video-item spike, on the same album. The video was the album's
cover in Google Photos' own editor ("Okładka albumu" showed the video's frame, 20:2x).

**What the previous source said.** `context/archive/2026-10-13-s09-share-link-photos/plan.md:173`
- tests were "refused on a photo-cover and on a video-cover page" (2026-10-13). There, a
video-cover page was a synthetic page with `og:video` tags. The S-09 research had not measured
one: "Not measured: … an album whose cover is a video" (`s09-share-link-photos/research.md:112`).

**Documentary half.** As above: not documented.

**Empirical half.** From `probe_video_item.py` above.

- **No `og:video`, and `og:image` is not the cover.** The album page has `og:title`
  "cast-tv S-15 probe: video cover · Feb 6 – Sep 4 📸", `og:description` "Shared album · Tap to
  view!", no `og:video*` tag, and `page_kind()` `photo`. Its `og:image` base answers `=d`
  5 007 083 B, `=m37` 493 681 B - the motion photo, the album's first item, not the video set as
  cover. In the OM-1 album, `og:image` is the third item in link order (spike above), so which
  item becomes `og:image` is not "the first" either.

**Not yet checked:** what picks the `og:image` item; whether an album whose only or first item is a
video gets `og:video`.

**What this settles:** refuted for this album - the cover chosen in Google Photos does not reach
the album page's Open Graph tags, so `og:image` says nothing about the cover or about the
album's kinds. S-09's `album_link` refusal holds either way, because it counts item links.

## Spike: Does the Google Photos Picker let a user select all items of an album in one action? (2026-10-15, 20:47)

Asked by the frame (`frame.md`, dimension 3): the owner's albums are his own, and the Picker is
the system's route for his own items. Documentary half read today; empirical half run with the
owner on the host, against his album "OM-1 Mayrhofen" (five photos, one date).

**What the previous source said.** `context/archive/2026-09-07-cloud-source-ui/research.md:81-82`
- "a documented **Picker API**: the user picks - multi-select - in Google's own UI (phone
included), and the app lists exactly those items with `baseUrl`s." (2026-09-08). It says nothing
about albums. `frame.md` (2026-10-15): "No document in the repo says whether the picker selects a
whole album". No prior claim about album selection was found.

**Documentary half.**

- **Albums are not browsable in the picker** - "Albums, favorites, and other common photos
  categories are not show directly." (sic)
  (https://developers.google.com/photos/picker/guides/picking-experience, last updated
  2025-10-06 UTC by its footer, read 2026-10-15)
- **An album is reached by search** - "Users can search for photos using various criteria, such
  as keywords, dates, locations, and album titles." The page advises apps that "utilize albums" to
  prompt users "to search once they enter the Google Photos app." (same page, read 2026-10-15)
- **Selection is per item** - "After searching, the user can select one or more items from the
  results." (same page). The page does not say whether a select-all, a whole-album or a whole-day
  selection exists. **The documentation does not say.**
- **What comes back is media items, not albums** - the getting-started guide says the list method
  is used "to get details about the selected media items"; it does not mention albums
  (https://developers.google.com/photos/picker/guides/get-started-picker, last updated
  2025-10-06 UTC, read 2026-10-15).
- **The pick is capped at 2000 items** - `pickingConfig.maxItemCount` "Defaults to 2000 if not
  specified", and "Values above 2000 will be coerced to 2000." The session resource has no
  album field (https://developers.google.com/photos/picker/reference/rest/v1/sessions, last
  updated 2025-10-06 UTC, read 2026-10-15).

**Empirical half** (2026-10-15, 20:48-20:54). cast-tv 0.4.0 from this branch, run on the host
with `.venv/bin/python ./cast-tv --no-browser`. The stored Google token was refused, so the tab
asked for consent; the owner gave it on the host as Piotr Miller, and the tab answered
`connected`. The owner then clicked Pick in the UI on the PC, searched "OM-1 Mayrhofen" in the
picker, and selected with **the checkbox next to the date**, a single click. He confirmed Done.

```
curl -s http://192.168.50.198:8895/api/status            # sources.gphotos.detail
curl -s http://192.168.50.198:8895/api/sources/gphotos/list
```

- **One click on the date checkbox selected the group.** The owner reported "Checkbox przy dacie,
  pc". There was no album control; the date group's checkbox did the job.
- **The pick returned exactly the album's count.** `/api/status`: `picks` 5, `pick.state`
  `done`, `pick.count` 5, `sessions` 1. The list has five `photo` items, all dated 2026-02-06 by
  name (`PXL_20260206_1748…`/`…1749…`), three 4000×3000 and two 3000×3284. That matches the
  OM-1 album's five items (spike 1: three 4000×3000 entries, two 3000×3284).
- **All five list as `photo`.** Four carry `.MP.jpg` names, though only two of the album's items
  answered `=m37` in spike 1; that mismatch was not chased.

**Not yet checked:** whether the search returned only the album's items or more (the owner
reported the control, not the result count; only the pick's count, 5, is measured); an album
spanning several dates (one date checkbox per date, presumably - not tried); an album holding a
video; the picker on a phone; how long the new consent lasts (S-10's 7-day expiry, Testing mode).

**What this settles:** for the owner's own album, yes in effect, with no album control. The docs
say albums are not shown and are found by title search. On the PC, one date checkbox selected
the five-item, single-date album, and the pick returned all five items. The frame's dimension 3
holds for this case; whether S-15 is still needed for the owner is his decision.
