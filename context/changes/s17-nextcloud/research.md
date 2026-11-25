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
