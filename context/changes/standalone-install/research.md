# Research: standalone-install

2026-09-19. Claude on the Windows laptop (Windows 11 Pro 26200, Python 3.14.5 from python.org),
the Samsung on the LAN.

## Google: what "any user" costs

- **Google Photos needs verification for general use.** The Google Photos authorization page:
  "If your application accesses the Google Photos APIs, it must pass the OAuth verification
  review." (https://developers.google.com/photos/overview/authorization)
- **What verification asks** (https://support.google.com/cloud/answer/13464321): a home page on a
  domain the developer owns and verifies in Search Console, a privacy policy on the same
  domain, a demonstration video "of your app including the OAuth grant process", a justification
  for each scope, and limited data use. A `github.io` address is GitHub's domain, not ours; the
  page does not say it qualifies. Piotr declined to buy a domain for now (`change.md`).
- **Unverified in production:** "100 new users in total, after the app presents the unverified
  app screen" (https://support.google.com/cloud/answer/7454865). Given the Photos sentence
  above, this is not a route either.
- **Testing mode**, where the `cast-tv` project is today: only the test users listed on the
  consent screen can consent (up to 100), and "A Google Cloud Platform project with an OAuth
  consent screen configured for an external user type and a publishing status of "Testing" is
  issued a refresh token expiring in 7 days" (https://developers.google.com/identity/protocols/oauth2,
  "Refresh token expiration"). The UI already handles the expiry: state `expired`, banner "The
  Google Photos consent expired ... or the test-user token ran out", Connect again
  (`castlib/ui/app.js`, `GATES.gphotos`).
- **A Desktop client's secret is not a secret.** "Installed apps are distributed to individual
  devices, and it is assumed that these apps cannot keep secrets."
  (https://developers.google.com/identity/protocols/oauth2/native-app). Shipping it inside the
  program is the documented model (rclone ships its Google Drive client the same way).
- **But not in the public repo.** GitHub push protection blocks Google OAuth client secrets by
  default ("Secrets from Figma, Google, OpenVSX, and PostHog are now push-protected by default",
  https://github.blog/changelog/2025-04-14-secret-scanning-expands-default-pattern-and-push-protection-support/),
  and a secret found in a public repo is reported to the provider. A revoked secret would break
  every copy at once. So the secret is written into the build by the release workflow from a
  repository secret; the source tree carries none. Anyone can still pull it out of the `.exe` -
  that is what "cannot keep secrets" means - but it is not published as text.

## Microsoft and GoPro

- OneDrive already ships `DEFAULT_CLIENT_ID = "652b2cf9-..."` (the owner's Entra registration)
  against the `consumers` authority; `ONEDRIVE_CLIENT_ID` overrides it. Nothing to copy today.
- GoPro has no public sign-in for apps; the token is pasted in the UI. That is a step in the UI,
  not a file, and stays.

## Spike: PyInstaller on this laptop (2026-09-19, 15:41)

Scratch venv with `pip install -e ".[test]" pyinstaller`, entry `from castlib.cli import main_tv;
main_tv()`:

```
python -m PyInstaller --noconfirm --onefile --name cast-tv --paths C:/Source/cast-tv \
    --collect-data castlib --collect-all pillow_heif entry.py
```

- Built in about 17 s: **`cast-tv.exe`, 22,532,635 bytes**, one file.
- `cast-tv.exe --help` printed the usual usage.
- `cast-tv.exe --no-browser -p 8099`, started hidden: printed its addresses and the firewall
  line, **found `83" OLED (192.168.50.142)`**; `GET /ui/` answered 200 with 30,705 bytes and
  the PR #16 markup (`addLink`); `GET /api/status` gave `gphotos: disconnected`. Stopped.
- Not yet checked in the build: a HEIC converted by `pillow_heif` (native `libheif` inside the
  bundle), a real cast from the `.exe`, Windows' first-run prompts (SmartScreen for an unsigned
  download, the firewall), a Linux build.
- `ffprobe` is optional: `castlib/diagnostics.py` returns nothing when it is missing (every call
  is under `except Exception`), so the bundle does not need it.

## Phase 3.1: Windows, clean account (2026-09-19, about 17:50)

A fresh Windows user account, `casttest`, on this laptop. What follows is the user's report, not
something Claude observed; Claude was shown three screenshots from the run (not committed, they
hold private photos).

- The user's words: "wszystko na tak, wszystko zagrało na TV, około 17:50" ("yes to everything,
  everything played on the TV, around 17:50"), answering the row's checklist item by item:
  - the account had no `%APPDATA%\cast-tv` and Python was not on PATH;
  - `cast-tv-windows-x64.exe` was downloaded from the `v0.3.0-rc1` pre-release in Edge;
    SmartScreen and the firewall prompt were met and accepted;
  - Google Photos: Connect → Google's consent (Piotr's account, a test user) → a photo and a
    video picked, both played on the Samsung;
  - OneDrive: device-code sign-in, a video played;
  - a share link: the video played;
  - closing the console window stopped the TV.
- Screenshots: Google Photos with **4 picked** (3 photos, one 2160×3840 video) while GoPro and
  OneDrive still said "not connected" - so the Google client came from the build, the account
  had no `google-client.json`; later OneDrive signed in and browsing
  `Pictures / OM Workspace / 2026_08_16` (187 items), GoPro "token stored", Google Photos
  "5 picked". The GoPro grid shows "too heavy" (100-121 Mbit/s) on every clip; that is the
  existing bitrate check on these 4K/5.3K files, not a regression, and no GoPro cast was
  claimed.
- The user signed out of `casttest` afterwards.

## Phase 3.3: a Google account that is not a test user (2026-09-19, 20:45-21:40)

What follows is the user's report plus two screenshots Claude was shown (not committed, the
first names the account).

- On `casttest`, `google.json` under `%APPDATA%\cast-tv` renamed to `.bak` so the Google Photos
  tab showed Connect; consent opened with a second Google account that is not on the app's
  test-user list.
- 20:45, Google's page (in Polish): "Dostęp zablokowany: aplikacja cast-tv nie przeszła
  weryfikacji przez Google" ("Access blocked: cast-tv has not completed the Google verification
  process"), "Błąd 403: access_denied".
- 20:46, the cast-tv gate: "waiting for consent… valid 2 min", Copy link and Cancel, and the
  line "cast-tv's Google app is in testing: if Google says "Access blocked", the cast-tv author
  has to add your Google account as a test user first." - the gate's line explains the block.
- The user then closed the console window before pressing Cancel; the UI stopped answering, as
  it should (#11: closing the window ends cast-tv). `google.json` was restored on `casttest`.
- Cancel, ~21:40, rechecked on the `pmill` account (Google Photos never connected there, so the
  gate showed Connect without renaming anything) with `cast-tv-windows-x64.exe` from
  `v0.3.0-rc1`: Connect → Google's tab closed without signing in → Cancel in the UI. The user's
  word: "Wraca" ("it goes back") - the gate showed "Connect Google Photos" with Connect again.

## Phase 3.2: Linux, `v0.3.0-rc1` on Fedora 44 (2026-09-19, from 22:39) - failed

Claude ran steps 1-2 on the laptop (Fedora release 44): `~/.config/cast-tv` moved to
`cast-tv.bak`, `cast-tv-linux-x64` fetched with curl (35 578 344 bytes, sha256
`7488d0478fbf082f7d89173e115e6f0df9925526e2c01ddfab91a8cd98fb5671`).

- Without `chmod +x`: "Permission denied", as the plan expects; after it the binary starts and
  reports version `0.3.0`. No port command was needed: the FedoraWorkstation zone already allows
  1025-65535/tcp.
- **The first TV search missed.** At 22:39 the startup M-SEARCH got 0 answers on `wlo1` although
  the Samsung was on (ping answered, `:9197/dmr` gave 200); a `POST /api/tv/discover`, what the
  UI's retry does, found `83" OLED` at once. The next start, 22:44, found it on the first try. A
  lost datagram, most likely; with the old config the remembered TV (`settings.tv`) would have
  hidden it. Not acted on.
- **Every HTTPS request failed.** Connect on the Google Photos tab: "Could not reach Google's
  sign-in service: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
  unable to get local issuer certificate (_ssl.c:1010)>". The binary is built on
  `ubuntu-latest` and PyInstaller bundles that runner's `libcrypto.so.3`; `strings` on the copy
  unpacked in `/tmp/_MEI…` shows `OPENSSLDIR: "/usr/lib/ssl"`. Fedora has no `/usr/lib/ssl`
  (its bundle is `/etc/pki/tls/certs/ca-bundle.crt`, its own Python reports
  `openssl_cafile='/etc/pki/tls/cert.pem'`), and the build carries no `certifi`. OneDrive and
  GoPro go through the same `urllib`, so they would fail alike. Windows is unaffected (Python
  loads the system store there; row 3.1 passed), and so is the pipx install on Fedora (the
  system's OpenSSL).
- Fix, chosen by the user over bundling `certifi` ("Zachowuje systemowy trust store, wspiera
  firmowe CA i nie zamraża certyfikatów w binarce" - "It keeps the system trust store, supports
  company CAs and does not freeze certificates into the binary"):
  `platform.use_system_ca_bundle()`, called first thing in `packaging/entry.py`. Only in the
  frozen Linux build, only when neither `SSL_CERT_FILE` nor `SSL_CERT_DIR` is set and OpenSSL's
  default file and directory are both missing, it sets `SSL_CERT_FILE` to the first existing
  file of `CA_BUNDLES`. Tests cover the user's own setting, Fedora, a Debian layout, Ubuntu
  (default present, nothing changes), no bundle found, and every build other than frozen Linux.
- **Fedora 44 has no `/etc/pki/tls/certs/ca-bundle.crt`.** The first workaround (rc1 restarted
  at 22:44 with `SSL_CERT_FILE` at that path) failed exactly as before, at 22:54:39; the path is
  Fedora 42's and RHEL's. On 44 the bundle is `/etc/ssl/certs/ca-certificates.crt`, a link to
  `/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem`; `/etc/pki/tls/cert.pem`, which Fedora's own
  Python reports as its `openssl_cafile`, does not exist either, only the `capath`
  `/etc/pki/tls/certs`. `CA_BUNDLES` therefore starts with the `/etc/ssl` file and keeps
  `ca-bundle.crt` and the `/etc/pki/ca-trust` file behind it. rc1 was restarted at 22:56 with
  `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`.
- **With the right bundle the flow works.** rc1 with
  `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`: consent went through (`verified_at`
  22:58:45), the picker session finished with 2 picks at 22:58:50, and at 22:59:57 a photo
  (`PXL_20260916_161438453.MP.jpg`, `image/jpeg`) was `playing` on the Samsung with `tv_state`
  PLAYING and 0 errors. The user: "Video and photo woorking". This is the diagnostic run, so it
  proves the fix's mechanism, not the row.
- **HEIC, 23:05-23:06.** Three OneDrive HEIC files cast; the prepared JPEGs in
  `/tmp/cast-tv-photos-…` are 4 360 546, 4 360 402 and 4 360 212 bytes, all 4096x3072 - byte for
  byte the three files of cloud-source-ui row 5.4 (`IMG_HEIC_landscape`,
  `IMG_HEIC_portrait_orient6`, `IMG_HEIC_portrait_irot`). The URL the TV held was fetched from
  this laptop and answered 200, `image/jpeg`, `DLNA.ORG_PN=JPEG_LRG`. At first the user saw
  nothing: **the TV's own screensaver had come on over the still photo and did not come back**,
  while AVTransport still reported PLAYING and 0 errors. Once it woke, the photos were there,
  "jeden plik jest odwrocyny" ("one file is upside down") - the `orient6` fixture, whose pixels
  were rotated the wrong way when it was made (cloud-source-ui row 5.4 settles this: `irot` and
  EXIF agree, so every HEIF-spec viewer shows the same, and `IMG_HEIC_portrait_irot` is the
  corrected one; the user confirmed it was that file). Not an app fault. The screensaver is worth remembering: a still photo can look
  like a dead cast.
- Row 3.2 counts only on `v0.3.0-rc2`, run as is.
- **Connect opened no browser tab** (the user's word, 22:5x): the consent had to be reached
  through Copy link. The binary runs with `LD_LIBRARY_PATH` set to its own `/tmp/_MEI…`
  directory, which leaks into anything it spawns - `xdg-open` and `gio open` run that way both
  print "MESA-LOADER: failed to open dri: /tmp/_MEI…/libstdc++.so.6: version `GLIBCXX_3.4.32`
  not found" - though in a shell test both still reached the browser. Not explained yet; the
  server was also started detached by Claude, not from the user's own terminal.

## Phase 3.4: weekly consent (pending)

- The user, 2026-09-19: "ustawiłem teraz nowy consent 21:46 19/09" ("I've just given a new
  consent, 21:46 19/09"), on this laptop right after the Cancel check of row 3.3. While the app
  is in Testing, Google's refresh token lasts 7 days, so the tab should say "The Google Photos
  consent expired" from about 2026-09-26 21:46; no Connect before then, or the week restarts.
