# Standalone Install — Plan Brief

> Full plan: `context/changes/standalone-install/plan.md`
> Research: `context/changes/standalone-install/research.md`

## What & Why

Piotr, 2026-09-19: copying files to make the app work "is out of the question" - a new laptop or
PC must just work, for any user. Today Google Photos needs a hand-made `google-client.json`,
and installing needs Python and pipx.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Google verification | Not now; Testing mode, test users added by the owner | Verification needs an owned domain, which Piotr declined for now | Change |
| Google client | Built into the release from repository secrets; stub in the repo | Desktop secrets are public by design, but GitHub push protection and provider revocation make the repo the wrong place | Research |
| Client order | env file, config file, built-in | Overrides keep working; OneDrive's model | Plan |
| Distribution | PyInstaller onefile: Windows `.exe`, Linux binary, on GitHub Releases from a tag | The spike built a working 22 MB `.exe` in 17 s | Research |
| Standalone scope | `cast-tv` only; `cast-gopro`/`cast-photos` stay in pipx | The UI covers both sources | Plan |
| Signing | None; README explains SmartScreen | Costs money, like the domain | Plan |

## Phases

1. The built-in Google client, `--version`, the test-user line in the gate.
2. The PyInstaller spec, the release workflow with smoke tests, the README.
3. Clean Windows account, Fedora, a non-tester account, the weekly re-consent.

## Owner steps

Two repository secrets (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) and the test-user list.
