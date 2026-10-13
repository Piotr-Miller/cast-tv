---
topic: "What Google Photos share pages and their media suffixes answer, for photos and motion photos"
researcher: Claude (with Piotr)
date: 2026-10-13
change: s09-share-link-photos
---

# Research: photos through share links

Measured from this machine (Fedora, home network) on 2026-10-13, through cast-tv's own guarded
opener (`sharelink.opener()`: https on Google hosts only, no cookies, no sign-in). Probe script:
the session's scratchpad `probe_links.py` (not committed); every row below is its output.
Each media suffix was asked for `Range: bytes=0-63` and the first bytes checked.

## Material

| Link | What it is | Source |
| --- | --- | --- |
| `photos.app.goo.gl/Nj2VHaD5bqKviYhq6` | Pixel motion photo (row 6.5 `link-1`) | `context/archive/2026-09-07-cloud-source-ui/research.md:1008` |
| `photos.app.goo.gl/Vdc9XaAhsYEedMAa8` | Pixel motion photo (row 6.5 `link-2`) | same |
| `photos.app.goo.gl/KwhGzcxkNtQpudc46` | a video, known good since row 6.5 | same, `:1019` |

## Findings, 2026-10-13 22:45

### The page

All three redirect to `photos.google.com/share/<id>?key=<key>`, answer 200 without cookies, and
weigh about 1.1 MB. `sharelink.page_kind()` reads them correctly: both motion photos `photo`
(only `og:image`), the video `video` (`og:video*` tags). The two motion-photo pages are
indistinguishable from a plain photo by their tags: `og:title` "New photo · …", `og:image`
`https://lh3.googleusercontent.com/pw…=w600-h315-p-k`, `og:image:width` 600, `:height` 315.

`sharelink.candidates()` finds **two distinct bases** on each page; the `og:image` base is the
first of them (index 0). The second was not identified. The `og:image` base is therefore the one
to use, not "every base on the page".

### The suffixes on a motion photo's `og:image` base (both links answered the same)

| Suffix | Answer | Host it lands on | What it is |
| --- | --- | --- | --- |
| `=d` | 206 `image/jpeg`, 6 368 609 B | `lh3.googleusercontent.com` | the original: JPEG with MPF APP2, `hdrgm:` XMP, `GCamera:MotionPhoto`, an MP4 (`ftyp`) at byte 3 398 903 |
| `=dv` | 200 `video/mp4`, 2 969 708 B | `video-downloads.googleusercontent.com` | the embedded clip: HEVC 1440×1080 at 120 fps (row 6.5: the TV refused it) |
| `=m37` | 206 `video/mp4`, 594 293 B | `rr2---sn-….googlevideo.com` | **H.264 High 1440×1080, 30 fps, AAC LC, 1.81 s** (ffprobe of the whole file) |
| `=m22` | 206 `video/mp4`, 456 779 B | `rr3---sn-….googlevideo.com` | not inspected |
| `=m18` | 206 `video/mp4`, 170 929 B | `rr…googlevideo.com` | not inspected |
| `=w4096-h4096`, `=s0` | 206 `image/jpeg`, 3 251 139 B | `lh3.googleusercontent.com` | a re-encoded still, smaller than `=d` |

Consequences:

- **`=d` serves the full photo publicly** - no cookies, no Bearer - and honours Range. The file
  is the Pixel Ultra HDR motion photo whole, which `photos.announces_extra_images()` already
  flags and re-encodes to the primary image (the "green frame" fix,
  `context/archive/2026-09-07-cloud-source-ui/research.md:842-857`).
- **`=m37` on a motion photo is H.264** at 30 fps - the variant the Samsung plays for picked
  videos. Its 1440×1080 is the clip's own size, not 1920×1080.
- Every hop stayed inside `sharelink.allowed()` (`lh3`, `video-downloads`, `googlevideo.com`).
- The full `=d` read returned 6 368 607 bytes against a `Content-Range` total of 6 368 609 on
  the probe. The difference was not chased; it does not change the design.

### Control: the video link

Unchanged since row 6.5: `=dv` 200 `video/mp4` 3 553 208 B (the H.264 file `resolve()` picks),
`=m37`/`=m22`/`=m18` 206 `video/mp4`. Its `=d` answers 206 `image/jpeg` 408 133 B (a still
frame), so on a **video** base `=d` also answers with a photo - the page's tags, not `=d`, say
what the link is.

### A plain photo, 2026-10-13 23:01

Material: `photos.app.goo.gl/QT9rQWxXYDDfSpKD8`, a plain (not motion) photo Piotr shared for this
probe, dated Sunday, Sep 27 on the page.

The page looks exactly like a motion photo's: `page_kind()` `photo`, `og:title` "New photo · …",
the same `og:image` shape, two bases with the `og:image` base first.

| Suffix | Answer |
| --- | --- |
| `=d` | 206 `image/jpeg`, 1 387 324 B, `lh3.googleusercontent.com` |
| `=dv`, `=m37`, `=m22`, `=m18` | **404** (`image/png` error body) |
| `=w4096-h4096`, `=s0` | 206 `image/jpeg`, 1 210 241 B |

Consequence: **a motion photo is told apart from a plain one by asking for `=m37`** on the
`og:image` base. A motion photo answers 206 `video/mp4`; a plain photo answers 404, which
`probe_media()` already returns as `None` (an `HTTPError` is "not media", not a failure).

### An album, 2026-10-13 23:02

Material: `photos.app.goo.gl/PpeVYpY5J4QkpYm99`, an album ("OM-1 Mayrhofen") Piotr shared for
this probe.

**An album page passes for a single photo.** It redirects to the same
`photos.google.com/share/<id>?key=…` shape, `page_kind()` answers `photo` (no `og:video`), and its
`og:image` is the cover - whose base answers `=d` 206 `image/jpeg` (6 666 854 B, Exif) and
`=dv` 200 / `=m37` 206 `video/mp4`. Without a check, the album would be listed as one motion
photo, its cover.

Two signals told it apart, on all five pages fetched in this research (23:0x):

| Page | `og:description` | distinct `/share/<this share id>/photo/<item id>` links |
| --- | --- | --- |
| `Nj2VHaD5…` (motion photo) | `Tap to view!` | 1 |
| `Vdc9XaAh…` (motion photo) | `Tap to view!` | 1 |
| `KwhGzcxk…` (video) | `Tap to view!` | 1 |
| `QT9rQWxX…` (plain photo) | `Tap to view!` | 1 |
| `PpeVYpY5…` (album) | `Shared album · Tap to view!` | **5** |

The item-link count is structural; the description is English text (cast-tv asks with
`Accept-Language: en;q=0.9`, `castlib/net.py:78`) and may follow the page's language. Not
signals: the `<title>`, which reads "Shared album - Piotr Miller - Google Photos" on the
**plain photo** page; and the base count (2 on single items, 6 on the album) - the item links say
the same thing more directly.

Not measured: an album holding exactly one item, and an album whose cover is a video.
