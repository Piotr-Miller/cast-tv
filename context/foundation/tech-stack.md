---
project_name: cast-tv
language: python
python: ">=3.10 (CI 3.12; the Windows laptop runs 3.14)"
package_manager: pip / pipx
hints:
  language_family: python
  team_size: solo
  deployment_target: user-machine (Fedora, Windows 11)
  distribution: GitHub Releases (PyInstaller onefile) + pipx from source
  ci_provider: github-actions
  has_auth: true           # third-party OAuth only: Microsoft device code, Google loopback
  has_payments: false
  has_realtime: false      # the UI polls /api/status every 1.5 s
  has_ai: false
  has_background_jobs: false
---

## The stack

| Layer | Choice |
| --- | --- |
| Server | `http.server` handlers on a `socketserver.ThreadingTCPServer`, one process and one port (8895) for the TV, the UI and the API |
| TV control | UPnP/DLNA over SOAP (`AVTransport:1`), SSDP discovery on every interface (`ifaddr`) |
| UI | one `index.html`, `app.js`, `style.css`; Alpine.js vendored; no build step, nothing from a CDN |
| Photos | Pillow + pillow-heif: EXIF transpose, HEIC/WebP to JPEG, 4096 px cap |
| Config paths | `platformdirs` (`~/.config/cast-tv`, `%APPDATA%\cast-tv`) |
| OneDrive | Microsoft Graph over device code, no SDK; the owner's Entra client id ships in the code |
| Google Photos | Picker API over the desktop loopback flow with PKCE; the client ships in release builds only |
| GoPro | `api.gopro.com` with a token pasted from a logged-in browser |
| Windows specifics | `SetThreadExecutionState` against sleep, a console-close handler, firewall policy detection |
| Tests | pytest + pyflakes, fakes for the TV's SOAP and for Google/Graph/GoPro |
| Release | PyInstaller onefile, built and smoke-tested by `.github/workflows/release.yml` on a `v*` tag |

## Why this stack

The process that serves bytes to the TV already lives for the whole session and already listens
on the LAN, because the TV has to reach it. Putting the UI on the same server gives one process,
one port, no IPC and a UI the phone can open for free - no desktop toolkit gives that, and it
needs no per-platform build (`cloud-source-ui/change.md`, "UI and stack").

Standard library first: FastAPI, a frontend framework and Node were each rejected; OAuth alone
did not justify a framework, since OneDrive's device code is a POST and a polling loop and
Google's loopback is a one-shot local listener. Revisit only if WebSockets or job queues turn up.

Video is never transcoded: the TV pulls the original through a `Range`-aware relay, so a film
seeks from the remote and the laptop stays idle. Photos are the exception - they are small, and
the TV cannot show HEIC or a rotated JPEG as-is.

The release is a PyInstaller onefile because a new PC must work without Python
(`standalone-install/change.md`); the spike built a 22.5 MB `.exe` in 17 s. The console window
stays, because Ctrl+C and closing it are how the user stops the TV.
