# Research: s17-nextcloud

2026-11-24. No codebase research was run for this change; the blocking questions were external.
Spikes below. They ran against the owner's own Nextcloud server (a hosted Storage Share instance,
Nextcloud 34.0.5); its address, the account name and every credential stay out of this public
repository. Commands are given with `<server>`, `<user>` and `<token>` in their place.

## Spike: does Login Flow v2 on the owner's server give cast-tv its own app password, with nothing copied? (2026-11-24, 19:41)

From Fedora (the laptop), against the owner's server, `status.php`: `"versionstring":"34.0.5"`.

**What the previous source said.** No prior claim found: `context/` and `README.md` never mention
Nextcloud as a source. The only mention is `context/archive/2026-10-15-s12-desktop-window/research.md:1557`,
"the owner had moved `Test_Pictures` from OneDrive to Nextcloud" (a test-material note, not a claim
about the API).

**Documentary half.**

- **Start** — "To initiate a login do an anonymous POST request", `POST /index.php/login/v2`; the
  answer holds `poll` (`token`, `endpoint`) and `login`, the URL to open in a browser
  (https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html, read 2026-11-24).
- **Polling** — "This will return a 404 until authentication is done." "Once a 200 is returned it is
  another json object" with `server`, `loginName`, `appPassword`; "Note that the 200 will only be
  returned once." "The token will be valid for 20 minutes." (same URL, read 2026-11-24)
- **Revoking from the client** — `DELETE /ocs/v2.php/core/apppassword` with the app password and
  `OCS-APIREQUEST: true`; "If a non 200 status code is returned the client should still proceed with
  removing the account." (same URL, read 2026-11-24)
- **Naming** — the page does not say how a Login Flow v2 app password is named; only the older
  `getapppassword` section says "The user agent header will be used to name the app password."

**Empirical half.**

```
curl -s -X POST -A "cast-tv-spike" https://<server>/index.php/login/v2
# then POST <poll.endpoint> -d token=<token> every 2 s until 200; the owner opened `login` in Chrome
```

- The start answered HTTP 200 with the keys `poll` (`token`, `endpoint`) and `login`.
- The owner signed in and granted access; the poll turned from 404 to **200 after 40 s (20 polls)**,
  with exactly the fields `appPassword`, `loginName`, `server`; `server` was the same host; the app
  password is 72 characters (stored only in a mode-600 scratch file, deleted after the spikes).
- A second poll after the 200 answered **404**: the password is handed out once, as documented.
- An earlier start left unapproved was abandoned and a new one started: an unused flow needs no clean-up.
- Revocation at the end: `DELETE /ocs/v2.php/core/apppassword` answered **200**; the same password
  then got **401** on a WebDAV `PROPFIND`.

**Not yet checked:** the name the app password shows under Settings → Security (the `-A` value is
assumed, not seen); a server that sits behind SSO or two-factor login; what the flow does when the
owner types the server address without `https://`.

**What this settles:** sign-in can follow the house rule "nothing the user copies": the owner types
the server address, approves in the browser, and cast-tv receives and stores its own revocable app password.

## Spike: does WebDAV with that password list photos and films with type, size, date, an id and a preview? (2026-11-24, 19:44)

Same server, same app password, Basic auth.

**What the previous source said.** No prior claim found.

**Documentary half.**

- **Files root** — "For file operations, this usually means paths below `/remote.php/dav/files/{user}/...`"
  (https://docs.nextcloud.com/server/latest/developer_manual/client_apis/WebDAV/basic.html, read 2026-11-24).
- **Listing** — "Without `Depth: 0`, folder listings include child entries." Requestable properties
  include `d:getcontenttype`, `d:getcontentlength`, `d:getlastmodified`, `d:resourcetype`, `oc:fileid`,
  `nc:has-preview` ("Whether a preview of the file is available.") (same URL, read 2026-11-24).
- **Auth** — "All requests need to provide authentication information, either as a basic auth header";
  an app password gives "a username and password which you can use within the Basic Auth header" (same URL).
- **Previews** — neither page documents a preview endpoint; only `nc:has-preview` exists in the docs read.

**Empirical half.**

```
PROPFIND https://<server>/remote.php/dav/files/<user>/<folder>   Depth: 1
  props: getlastmodified getcontenttype getcontentlength resourcetype getetag
         oc:fileid oc:size nc:has-preview nc:creation_time nc:upload_time
SEARCH https://<server>/remote.php/dav/   basicsearch, getcontenttype LIKE video/%, depth infinity, 15 results
GET https://<server>/index.php/core/preview?fileId=<id>&x=256&y=256&a=1
```

- `PROPFIND` of the root: **HTTP 207, 3,137 B, 0.95 s** (later folders 0.14-0.15 s). Folders carry
  `resourcetype/collection`, `oc:fileid` and `oc:size` (the folder's total bytes, e.g. 38,764,484,634);
  `getcontentlength` is absent for folders.
- Files carry `getcontenttype` (`image/jpeg`, `image/png`, `image/heic`, `video/quicktime`),
  `getcontentlength`, `getlastmodified` (RFC 1123), `oc:fileid` (a number). `nc:creation_time` came
  back `0`: no capture date from this property.
- `nc:has-preview`: **true** for JPEG, PNG and HEIC; **false** for all 13 films found.
- `SEARCH` for `video/%`: **HTTP 207 in 0.24 s**, 13 results, all `video/quicktime` `.MOV` from the
  owner's OM camera (268 MB to 2.29 GB).
- Preview with Basic auth: JPEG id → **200 `image/jpeg`, 7,334 B, 0.24 s** (256×171); **HEIC → 200
  `image/jpeg`, 8,812 B, 0.53 s** (256×192, the server converts); a film → **404**. The same preview
  without auth → **401**.

**Not yet checked:** paging or limits of a `PROPFIND` on a folder with thousands of entries; photo
EXIF dates (only `getlastmodified` is a date here); whether `/core/preview` keeps working when the
server's preview settings change; video previews on a server with a video preview provider.

**What this settles:** browsing by folder works like OneDrive, with thumbnails for photos (HEIC
included) served through cast-tv with the app password; films have no server thumbnail here.

## Spike: can the TV play a Nextcloud film through cast-tv's relay, and directly from a link the server gives? (2026-11-24, 19:50)

Same server; the TV is the owner's Samsung 83" OLED (`192.168.50.142`), cast-tv from this branch's
checkout on Fedora. With the owner's permission a test folder `/cast-tv-spike/` was created with one
phone video (H.264 Constrained Baseline 1920×1080, AAC, 14 s, 27,720,677 B) and deleted afterwards,
its trash entry included.

**What the previous source said.** No prior claim about Nextcloud. On playback,
`context/foundation/prd.md:173` — "No transcoding; audio codecs the TV cannot decode are reported, not converted."

**Documentary half.**

- **Direct link** — "POST /ocs/v2.php/apps/dav/api/v1/direct" with "the `fileId` in the body"; "This
  will then return you the link to use to obtain the file."; "This link will be valid for 8 hours
  afterwards it will be removed." The page names no response field and does not mention Range
  (https://docs.nextcloud.com/server/latest/developer_manual/client_apis/OCS/ocs-api-overview.html, read 2026-11-24).
- **Download** — "A file can be downloaded by sending a `GET` request to the WebDAV url of the file";
  Range is not mentioned (WebDAV basics, URL above, read 2026-11-24).

**Empirical half.**

```
GET <webdav url of a .MOV>  Authorization: Basic …  Range: bytes=1000-1999
GET <webdav url>            (no auth)
POST /ocs/v2.php/apps/dav/api/v1/direct?format=json  fileId=<id>   (Basic, OCS-APIRequest: true)
GET <direct url>  Range: bytes=1000-1999   (no auth)
python -m castlib --no-browser -d -p 8897 --title "spike relay" "<direct url>"      # A: relay
SetAVTransportURI <direct url> + Play, sent straight to the TV (DIDL video/mp4)    # B: direct
```

- WebDAV GET with auth and Range: **206**, `Content-Range: bytes 1000-1999/268748800`, 0.49 s;
  without auth **401**. No `Accept-Ranges` header is sent, yet ranges are honoured.
- Direct link: **200**, OCS status 200, URL `https://<server>/remote.php/direct/<token>` on the same
  host; GET **without auth** with Range: **206** (0.26 s); without Range: **200**, full length.
- **A, relay, the H.264 file:** the TV sent HEAD and GET, then ranged GETs; cast-tv fetched upstream
  **200 then 13 × 206**; the TV reported `PLAYING 0:00:12.487 / 0:00:14`, then cast-tv printed
  `Finished.` The film played to the end.
- **B, direct, the same file:** SetAVTransportURI **200**, Play **200**, then the TV stayed
  `STOPPED 0:00:00 / 0:00:00` for 20 s (10 polls); no playback. The cause is not established (the
  link is HTTPS; the TV may not play HTTPS from DLNA).
- *(Withdrawn 2026-11-24, 20:02: see "Verification after the frame" below; the same file plays.)*
  **The camera's own films do not play at all**, whatever the route: an OM `.MOV` (HEVC Main 10,
  3840×2160, 59.94 fps, `pcm_s16le` 48 kHz audio, 15.5 s) went `TRANSITIONING` → `STOPPED` through
  the relay *and* from a local copy cast with `cast-tv <file>`. All 13 films found on the server are
  such MOVs.

**Not yet checked:** why B fails (HTTPS or the server's response headers) — no plain-HTTP endpoint
exists to compare; which part of the OM MOV the TV refuses (HEVC 10-bit at 4K60, PCM audio, or the
MOV container); seeking in a relayed Nextcloud film; a film several GB long through the relay.

**What this settles:** playback goes through cast-tv's relay, which streams with Range and needs the
app password or a direct link; handing the TV a Nextcloud link directly did not play. Separately,
the owner's camera MOVs are not playable on this TV by any route, so a Nextcloud tab will show films
the TV cannot play unless that is reported.

## Verification after the frame: do the owner's OM camera MOVs play on this TV? (2026-11-24, 20:00-20:02)

Asked by `frame.md` (dimension 4): row 5.4 of cloud-source-ui (2026-09-12) recorded an Olympus MOV
playing through the OneDrive relay; the third spike above recorded an OM MOV refused by every route.

**Material.** The owner's Nextcloud desktop sync folder on Fedora holds the same 13 MOVs the server
listed. `ffprobe` of three of them, including `P7242629.MOV` (the file of row 5.4) and
`PA313998.MOV` (268,748,800 B, the exact length in the spike's `Content-Range`, so the spike's
file): identical streams in all three, HEVC Main 10 `hvc1` 3840×2160 `yuv420p10le` 59.94 fps at
131-137 Mbit/s, `pcm_s16le` 48 kHz stereo (`sowt`), a `tmcd` data track, brand `qt`.

**Run.** Fedora, this branch's checkout, `cast-tv -d --no-browser -t 192.168.50.142 -p 8897 <file>`,
TV: the owner's Samsung 83" OLED. Local files, not through Nextcloud.

| File | TV state reported to cast-tv | Seen on the TV (owner) |
| --- | --- | --- |
| `2026_07_24/video/P7242629.MOV`, 16.5 s | `PLAYING` 0:00:00.319 → 0:00:14.733 / 0:00:16, `Finished.` | picture and sound to the end |
| `2026_11_01/video/PB014001.MOV`, 30.5 s | `PLAYING` 0:00:00.508 → 0:00:29.271 / 0:00:30, `Finished.` | picture and sound to the end |
| `2026_10_31/video/PA313998.MOV`, 15.5 s | `PLAYING` 0:00:00.560 → 0:00:14.847 / 0:00:15, `Finished.` | picture and sound to the end |

**What this settles:** the claim above that "the camera's own films do not play at all, whatever
the route" is **withdrawn**. The spike's own file plays as a local file, and the TV decodes HEVC
Main 10 4K60 with PCM audio in a MOV. Why that file stopped in the spike is not established (the
order of its tries and the completeness of its local copy were not recorded).

**Not yet checked:** an OM MOV through cast-tv's relay from Nextcloud (the relay was proven with an
H.264 film only; row 5.4 proved an OM MOV through the OneDrive relay).

## Manual acceptance

### Row 4.2: the owner confirms the README and PRD text (2026-11-25)

- **Device and material:** the owner, on GitHub's PR #117 page, "Files changed", at
  `907f31c8f9fbe7f2f4116bda6d8d61f1dc9911a8`: `README.md`, section *Nextcloud*, and
  `context/foundation/prd.md`, FR-014 and FR-015.
- **Seen (the owner's words, translated):** the section and both FR lines match the description:
  HTTPS only; the last-modified date, not the date the photo was taken; film previews only when
  the server's admin enabled them; Disconnect removes the password locally first, then tries to
  revoke it on the server, and a missing confirmation shows a message.

### Phase 3 rows on Fedora (2026-11-25)

Setting for every row below: Fedora (KDE Plasma, Wayland), this branch at
`c91adba`, `python -m castlib -d` started by the agent with Qt DevTools on, the cast-tv window
driven over DevTools and Chrome by the agent; the owner's hosted Nextcloud (Storage Share,
Nextcloud 34.0.5; address kept out of the repository); TV: the owner's Samsung 83" OLED
(192.168.50.142).

- **Row 3.5.** In the window's **Nextcloud** tab the address was typed with `https://` and a
  trailing `/`; **Connect** showed the gate: "Open this link on any device, sign in to Nextcloud
  and grant access:", the `…/login/v2/flow/<token>` link, "waiting for access…", "valid 20 min",
  **Copy link**, **Cancel**. Clicking the link in the window opened the server's login page in
  Chrome (the system browser; the owner saw it). The owner granted access; the owner saw the tab
  list the root folders within about 5 s. `/api/status`: `connected`, account
  `<display name> (<login>)`, `stored: true`; folders `Documents`, `Photos`, `Pictures`,
  `Templates`. `stat -c %a ~/.config/cast-tv/nextcloud.json` printed `600` (contents not read).
- **Row 3.6.** Chrome, the server's Settings → Security, "Devices & sessions": one entry named
  **cast-tv**, last activity "1 minute ago", with the "…" menu; no other cast-tv entry.
- **Row 3.7.** Window: folders `Pictures`, `OM Workspace`, `2026_11_01` clicked; the crumbs read
  `Nextcloud / Pictures / OM Workspace / 2026_11_01`. The photo tiles showed the server's preview
  (`PB014004.JPG` 4.7 MB, preview 768 px wide; the next five 768-1024 px) and the date
  `2026-11-01`, each date with the tooltip "last modified". In `video`: `PB014001.MOV` (489.1 MB)
  and `PB014042.MOV` (725.4 MB) with the film placeholder (no image) and `2026-11-01`.
- **Row 3.8.** Crumb `Pictures`, folder `Test_Pictures`, tile `shelf-christmas-decoration.heic`
  (1.4 MB, `2026-09-21`), its "Cast now" button: the debug log printed
  `[tv] HEAD /m/<token>/<id> Range=- -> 0-2004137/2004138` (the converted JPEG); the owner saw
  the photo upright on the TV. (The same folder holds an `application/octet-stream` file, hidden
  and logged once: `! nextcloud: hiding an item of unknown kind 'application/octet-stream'`.)
- **Row 3.9 (not ticked: the film stalls).** Folder `video`, tile `PB014001.MOV` (489.1 MB;
  `ffprobe` of the synced local copy: 30.53 s, 134.4 Mbit/s, the HEVC Main 10 4K60 / PCM MOV of
  the verification above), "Cast now". Debug log: `upstream: 200` for the TV's HEAD and plain GET,
  then `206` for each ranged GET (`bytes=0-`, `100656-`, `7667704-`, `73867513-`, `104835465-`,
  then the seek: `239256068-`, `441390289-`, …, `506997612-`). The owner: picture and sound; one
  press of the remote's forward/seek at about 0:15 resumed later in the film with picture and
  sound; it ran to the end; **but every few seconds the picture stopped, buffered and resumed**.
  - **Same file as a local file**, right after: `cast-tv -d --no-browser --no-window -t
    192.168.50.142 -p 8897 <synced copy>`: `PLAYING` to 0:00:29.637 / 0:00:30, `Finished.`; the
    owner: **smooth**. The TV re-opened a ranged GET about every 2 s.
  - **Measured from the laptop** through `NextcloudSource.resolve()` (the app password stayed
    in the process): two 100 MB ranges at 487 and 495 Mbit/s; seven fresh ranged requests at the
    TV's offsets: 0.15-0.26 s to the response headers, 0.10-0.12 s to the first 256 KB, and the
    first 8 MB at 187-243 Mbit/s.
  - **Link:** the laptop is on Wi-Fi only (5 GHz, signal -42 dBm, tx 780 / rx 867 Mbit/s); the
    relay carries the film twice over that radio (server → laptop → TV).
  - **Reading:** the server is fast enough in bulk, but each of the TV's frequent re-opened
    ranges costs a new HTTPS request with about 0.3 s before data and a slow-starting transfer
    only ~1.6× the film's bitrate, on a Wi-Fi link that carries the film twice. A local file has
    neither cost. Not a defect in the relay's code; a headroom limit for 134 Mbit/s films.
  - **Where it stalls (owner decision 2026-11-25: measure first).** A wired laptop is physically
    impossible, so the causes were separated with a local Range server (`rangeserve.py`,
    scratchpad, not in the repository) serving the synced copy of `PB014001.MOV` through the same
    relay, `cast-tv -d --no-browser --no-window -t 192.168.50.142 -p 8897 "http://127.0.0.1:<port>/PB014001.MOV"`;
    the TV and its connection unchanged.

    | Run | Source behind the relay | Played | Owner saw |
    | --- | --- | --- | --- |
    | M1 (row 3.9 above) | Nextcloud over the internet, laptop on Wi-Fi | to the end | stops and buffering every few seconds |
    | M2a | local server, no delay | `Finished.` | smooth |
    | M2b | local server, 0.3 s before each response's headers | `Finished.` | a stop of a fraction of a second every few seconds |
    | M2c | Nextcloud again, with temporary timing in `relay.py` (not committed) | to the end | stops every moment |

    With a local source the TV opens two ranged GETs about every 2 s and takes ~40 MB from the
    relay each time (M2a/M2b: 36-52 MB in 1.7-2.3 s). In M2c, per 31-74 MB portion: opening the
    upstream 0.14-0.17 s, **reading from Nextcloud 0.3-0.6 s, writing to the TV 1.6-3.7 s**, so
    **115-147 Mbit/s towards the TV**, against the film's 134 Mbit/s.
  - **Conclusion.** The relay's code keeps up (M2a). The limit is the laptop's Wi-Fi carrying the
    film in both directions at once: while the film arrives from the internet, what reaches the
    TV drops to about the film's own bitrate, with no headroom; each re-opened range adds
    ~0.15 s, which alone already gives short stops (M2b). Reusing upstream connections or a
    read-ahead buffer would remove only the latency, not the shared airtime; fetching the film
    before playback (as Google Photos originals are) would let the TV read it from the disk, as
    in M2a.

### M3: lighter H.264 sample through Nextcloud (2026-11-25)

- **Purpose and setting:** follow-up to row 3.9 and M1/M2 above, requested by the owner.
  Same Fedora laptop, Wi-Fi, running cast-tv instance and Samsung 83" OLED
  (`192.168.50.142`). The original `PB014001.MOV` was left intact.
- **Material:** ffmpeg converted the synced original to `PB014001-h264-35M.mp4`, H.264 High,
  3840×2160 at 60000/1001 fps, AAC LC audio; 30.530667 s, 133,854,698 bytes,
  35.074162 Mbit/s overall (`ffprobe`). Encoder: libx264, veryfast, 35M target, 40M maxrate,
  70M buffer; AAC 192k, MP4 faststart. Encoding finished before upload and playback.
- **Upload:** copied into the Nextcloud sync client's `/cast-tv-test/` folder. The running
  app's Nextcloud listing confirmed the uploaded filename, `video/mp4` and exact byte count.
  No credential file was inspected. Browser control was unavailable.
- **Observed by the agent:** cast through the running app's `/api/cast` with source `nextcloud`.
  `/api/status`, sampled every second, reported `PLAYING` at 1.253 s, then 5.299, 11.356,
  15.399, 21.460, 25.503 and 29.544 s; `STOPPED` at 36.13 s after the cast request.
  Seven media requests, no reported error. Raw status observations are in the temporary
  local file `/tmp/cast-tv-M3-status.json` (not committed).
- **Owner observation (2026-11-25):** asked whether picture and sound were smooth on the
  Samsung during M3, the owner confirmed: "Yes it was smooth".
  This supports the throughput/headroom diagnosis from M1/M2: the lighter sample plays
  smoothly through Nextcloud on the same setup. M3 changes both bitrate and
  codec/container/audio, so it does not isolate bitrate alone.
  Row 3.9 remains open: this sample does not satisfy the original OM-film criterion.
- **Cleanup:** the M3 sample, empty local sync folder and temporary encoded file were
  removed after playback. A fresh Nextcloud root listing confirmed `/cast-tv-test/` absent
  from active files. **Trash cleanup remains pending:** browser control was unavailable;
  Nextcloud's Deleted files were neither inspected nor purged. The owner must remove only
  this test folder/sample there and confirm the result.

### Row 5.4: an OM film downloaded first (2026-11-25)

- **Setting:** as the Phase 3 rows above, with this branch at `569da31` (Phase 5); the cast-tv
  window restarted so the download cache was empty.
- **Run 1 (fresh download):** window, `Pictures / OM Workspace / 2026_11_01 / video`, tile
  `PB014001.MOV` (489.1 MB), "Cast now". `/api/status` sampled every 0.5 s from the click: the
  download ran for about 7.6 s, `starting` at 7.6 s, **`playing` at 10.0 s** (position
  0:00:00.398), `playing` 0:00:29.081 at 40.4 s, `stopped` at 41.0 s. The TV's ranged GETs were
  answered from the downloaded file in `/var/tmp/cast-tv-videos-<pid>-*` (no `upstream:` line),
  in the two-requests-every-2-s pattern of a local file. The owner: **smooth, no stops or
  buffering**, picture and sound (the remote was not pressed in this run).
- **Run 2 (from the download cache), seek:** "Cast now" again; `playing` at once; the owner
  pressed the remote's forward/seek once at about 0:15: position 0:00:15.64 → 0:00:26.843 within
  one 0.5 s sample, the TV's GET `bytes=441390289-` after `bytes=231281246-`; `playing`
  0:00:28.895, then `stopped`. The owner confirmed row 5.4 (picture and sound resumed later in
  the film; ran to the end).
