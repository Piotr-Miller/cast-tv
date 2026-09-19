---
change_id: standalone-install
title: cast-tv runs on a new PC with nothing to install or copy first
status: planned
created: 2026-09-19
updated: 2026-09-19
archived_at: null
---

## Notes

On the Windows laptop, the Google Photos tab's Connect answered "No Google OAuth client is
configured (...\google-client.json is missing)". The fix the UI offered was to create a Google
Cloud project and copy its JSON into the config directory. Piotr's answer:

"situation when we need to copy some kind of files to make app working is out of the question.
Thi sshould be standolone, new laptop, new PC app i sworjking"
(verbatim; in short: needing to copy files to make the app work is out of the question - it has
to be standalone: new laptop, new PC, the app works.)

Asked whether that is for his own PCs or for anyone: "It should be plan for any of your PCs and
any user."

So two gaps, both of which the `cloud-source-ui` plan left open on purpose:

1. **Google Photos needs a client file.** OneDrive already ships the owner's Entra client id
   (`castlib/sources/onedrive.py:39`, `DEFAULT_CLIENT_ID`); Google Photos reads
   `config_dir()/google-client.json` or `GOOGLE_CLIENT_JSON` and has no default
   (`castlib/auth/loopback.py:59`). `plan.md:140` of `cloud-source-ui` chose "No verification of
   the Google OAuth app; Testing mode with the owner as test user."
2. **Installing needs Python and pipx.** `plan.md:139` of `cloud-source-ui`: "No PyInstaller bundle
   in this change (kept as a later channel)."

## Decisions (Piotr, 2026-09-19)

Asked three questions after the research below:

1. Google verification (own domain, home page and privacy policy on it, a demo video, Google's
   review): **"for now i do not want to buy"** - no domain, no verification in this change.
2. Ship the owner's Google client now, in Testing mode (people added by hand as test users,
   consent again about weekly): **"Yes"**.
3. A new PC works without installing Python first (a Windows `.exe`, a Linux binary): **"Yes"**.

## What that means for "any user"

Until the Google app is verified, Google Photos works for the accounts the owner adds as test
users (up to 100) - anyone else sees Google's "Access blocked" page. Every other part works for
anyone: OneDrive (any personal Microsoft account, the shipped client id), GoPro (the token paste,
as today), share links (no sign-in, since PR #16), local files. Verification stays a later
change, once there is a domain.
