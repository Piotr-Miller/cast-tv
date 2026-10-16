# Frame Brief: a desktop window for cast-tv on Windows and Linux (S-12)

> Framing step before /rune-plan. This document captures what is *actually*
> at issue, separated from what was initially assumed. Written 2026-10-16.

## Reported Observation

The owner's words (`context/foundation/roadmap.md:142`, recorded 2026-09-19 in commit
`9858973`): "Desktop UI (Win/Linux) zamiast WebUI" ("a desktop UI (Win/Linux) instead of the web
UI").

Narrowed on 2026-10-16. On the computer, all three of these bother him:

1. **Two things to keep track of.** A console window must stay open, and the UI is one browser
   tab among many, which can be lost or closed while the TV keeps playing.
2. **It looks like a web page:** address bar, tabs.
3. **Starting and coming back.** There is no icon in the menu or taskbar; cast-tv is started
   from a terminal or a file, and getting back to the UI goes through the browser.

**Observed / inferred**: all three complaints are observed; the owner lives with them on
Fedora and the Windows 11 laptop. "A desktop UI" as the answer to them is inferred: nobody
has tried an app-style window yet.

## Initial Framing (preserved)

- **Stated approach** — the roadmap's "Ideas", written by the assistant on 2026-09-19 as
  "starting points, not findings" (`roadmap.md:144-147`):
  - the existing UI in a native window (e.g. pywebview), with the server in the same process;
  - closing the window stops the TV, as the console window does now (#11);
  - a tray icon.
- **Constraints the owner added on 2026-10-15** (`research.md`, both spikes):
  - the whole Linux family, not only Fedora;
  - frameworks current and widely used in 2026;
  - macOS as a nice-to-have;
  - agreed spike criterion: "one artifact per OS, with nothing installed".
- **Proposed direction**: build that desktop window for Windows and Linux.
- **Pre-dispatch narrowing (2026-10-16)**:
  - all three complaints apply (the observation above);
  - "Telefon zostaje na WebUI" (the phone keeps the web UI);
  - the window is "Głównie dla mnie, ale w sumie każda osoba może ściągnąć sobie z releasu"
    (mainly for me, but anyone can download it from the release).

## Dimension Map

The observation could originate at any of these dimensions:

1. **Process lifetime.** The TV session lives as long as the console process, not the UI;
   nothing ties the UI to the session. This produces complaint 1. ← initial framing (partly:
   "closing the window stops the TV")
2. **Window chrome.** The UI is drawn in the user's own browser, in an ordinary tab. This
   produces complaint 2. ← initial framing (the native window)
3. **OS integration.** The release is a bare file, with no icon, launcher entry or tray. This
   produces complaint 3. ← initial framing (partly: the tray icon)
4. **Delivery constraint.** The PRD promises "one download, nothing installed" and limits
   dependencies. This decides which answer to dimension 2 is even deliverable on Linux.

## Hypothesis Investigation

The four dimensions:

| Hypothesis | Falsifier (what would kill it) | Evidence | Verdict |
| --- | --- | --- | --- |
| **1. Lifetime is bound to the console, not the UI** | Closing the tab already stops the TV; a build without a console exists; a UI control quits the app. **None found.** | **Console by design:** `packaging/cast-tv.spec:1-3,24`. **Stop paths:** `castlib/platform.py:293-354` (console close, #11) and `castlib/cli.py:321`. **The only end is Ctrl+C or a signal:** `castlib/app.py:311-312`. **Closing the tab stops nothing:** no beforeunload or heartbeat (`castlib/ui/app.js:106-111`), and `/api/status` records nothing (`castlib/api.py:104-108`). **UI "Stop" stops playback only:** `api.py:157-162`. | STRONG |
| **2. "Looks like a page" is the browser's chrome** | The UI already opens app-style; or there is no code to launch an app window. **Neither found.** | **Opened as a plain tab:** `webbrowser.open` (`app.py:262-264`); a second launch opens another tab (`cli.py:268-275`). **No app identity:** no manifest, and `/favicon.ico` answers 204 (`castlib/server.py:195-198`). **App-window code exists, GoPro-specific:** `castlib/auth/browser.py` already launches Chromium-family browsers with `--app=` (`:153`), with the URL hard-coded (`:41`). **Spike result:** in both spikes (`research.md`), every candidate that removes the chrome also changes delivery (dimension 4). | STRONG |
| **3. No OS presence** | An icon, `.desktop` entry, shortcut or installer exists or is planned. **Not found**; only the roadmap's tray-icon idea. | **No integration:** no icon files in the repository; `release.yml:37-48` uploads a bare binary; the spec has no `icon=`. **Ruled out by policy:** PRD Non-Goal "No code signing, installers, auto-update or macOS for now" (`prd.md:175`); "desktop shortcuts" out of scope (`context/archive/2026-09-19-standalone-install/plan.md:49`). | STRONG |
| **4. The delivery constraint decides dimension 2 on Linux** | Every candidate meets "one artifact, nothing installed" on Linux, or the PRD does not ask for it. **Not found.** | **The PRD asks for it:** `prd.md:59-60` ("nothing else installed") and `prd.md:156` (dependencies limited to the standard library plus four packages). **Platforms:** `prd.md:154` names "Fedora … and Windows 11", while the owner's 2026-10-15 scope is the Linux family plus macOS, a PRD Non-Goal. **Spike outcomes (`research.md`):** pywebview/GTK passed 0/5 distributions; Qt WebEngine passed 5/5 only with the GPU off, at 232 MB; Chromium `--app` fails where Firefox is the default. | STRONG |

All four were investigated. Dimensions 1 and 3 went to one delegate, dimension 2 to another,
and dimension 4 came from the existing spikes.

## Narrowing Signals

- **Step 1.5:** the owner confirmed all three complaints, so all three dimensions are in play
  and none is ruled out. "Telefon zostaje na WebUI" rules out replacing the UI: the window
  wraps the existing `/ui/`.
- **Step 4:** exit (a). Step 3 found strong evidence for all four dimensions and a falsifier
  for none, and the pre-dispatch answers had already located the observation. No further
  question was asked.
- **The inverse check found that the console is not only a stop switch.** It is the only place
  that shows:
  - the LAN addresses for the phone (`app.py:234-235`; US-03 says "the printed LAN address");
  - the firewall advice (`app.py:236,242`);
  - the TV that was found (`app.py:249`).

  The UI shows none of these (`castlib/ui/index.html`).

## Cross-System Convention

This project decided twice against embedded webviews:
`context/archive/2026-09-07-cloud-source-ui/change.md:187-189` and
`context/changes/s13-gopro-auth/plan.md:131-132`, the latter "revisit only if S-12 makes an
embedded window a product requirement". It decided once for an app-owned Chromium window
(S-13, `castlib/auth/browser.py`). `tech-stack.md:36-40` keeps one process, one port and a UI
the phone opens for free.

The leading hypothesis fits these decisions: the window wraps `/ui/` and the phone path stays.
It departs from them in one place: it names the console and the missing OS presence as
separate problems, which the initial framing folded into "a window".

## Discriminator Check

The proposed experiments come from `research.md`'s "Not yet checked" lists:

| Proposed experiment | Separates | Conflates | Cost (money / irreversible / wait) | Already answered by |
| --- | --- | --- | --- | --- |
| **Windows 11 laptop run:** Edge `--app` on `/ui/`, pywebview/WebView2, the PySide6 onefile | Whether each candidate meets dimension 2 under the dimension 4 criterion on Windows | Nothing, if each candidate is run on its own | 0 / no / the owner's time at the laptop: unknown | **Still open**; the kit is ready. **Partly answered:** an Edge `--app` window from `castlib/auth/browser.py` ran on that laptop for GoPro (`context/changes/s13-gopro-auth/research.md:688-699`, cost 0). It did not show `/ui/`, so it does not dominate. |
| **Tauri 2 and Electron AppImages** in the five-distribution matrix | Whether an AppImage with its own engine meets dimension 4 on Linux | The **AppImage runtime** (FUSE, user namespaces) and **the bundled engine** | 0 / no / unknown (two toolchains to install, two builds) | **Run 2026-10-16** (`research.md:392`). Tauri 2.12.4 AppImage carries WebKitGTK 4.1; it passed on the Fedora desktop (FUSE 3 only) and on an Ubuntu 24.04 VM. Electron with electron-builder 26.15.3 needs `libfuse.so.2` and failed on both; with 27.0.0-alpha.10 it passed on both, and runs `--no-sandbox` on Ubuntu 24.04. |
| **Qt onefile without the bundled `libgbm` and `libstdc++`, GPU on** | Whether the GPU failure is a bundling artifact or inherent to the bundle | **`libgbm`** and **`libstdc++`**, removed together | 0 / no / about 10 min (101 s build plus matrix, measured 2026-10-15) | **Run 2026-10-16, one library at a time as the owner asked** (`research.md:392`). The bundled `libstdc++` causes the abort, and the bundled `libgbm` breaks GBM. Without both, the bundle passed with the GPU on: Fedora desktop and 5/5 containers. |
| **Qt onefile on a real Ubuntu 24.04 desktop** | Whether Ubuntu 24.04's user-namespace restriction (AppArmor) breaks Qt WebEngine's sandbox, against the container result | Nothing | 0 / no / unknown (needs a machine or VM) | **Run 2026-10-16 on an Ubuntu 24.04 VM**, AppArmor restriction on, no GPU (`research.md:392`). The Qt bundle without both libraries passed. The user-namespace layer was denied; the renderer runs with `Seccomp: 2`. |

## Reframed (or Confirmed) Problem Statement

> **The actual problem to plan around is**: on the host, cast-tv should be one thing you
> start, see, return to and close. Today that is split across a console that owns the TV
> session and the screen's information, a plain browser tab, and a file with no OS presence.
> Each of the three parts has its own cause, and only one of them is about how the UI is
> drawn.

The initial framing, "put the UI in a native window", addresses dimension 2 and part of
dimension 1. Closing the window can stop the TV, but complaint 1 also needs the console gone,
and the console currently carries the phone's LAN address and the firewall advice. Complaint
3 needs an icon and a launcher entry, which the PRD's "no installers" non-goal excludes today.

The direction holds: wrap `/ui/`, keep the phone on the web UI. But a window alone would leave
two of the three complaints standing. The toolkit choice is one decision among four, not the
whole slice.

## Confidence

**HIGH.** All four dimensions have strong evidence in this repository. The owner confirmed
all three complaints. The independent search, given only the observation, landed on the same
three causes and the same PRD constraints.

The plan still needs decisions only the owner can make. These are inputs, not verification
steps:

- Whether the PRD's "no installers / desktop shortcuts" non-goal (`prd.md:175`) is relaxed for
  an icon and a launcher entry. — Actor: user
- Whether "nothing installed" on Linux (`prd.md:59`) and the dependency list (`prd.md:156`)
  hold for the window, given the spike outcomes. — Actor: user
- Which platforms the PRD names: Fedora and Windows 11 (`prd.md:154`), or the Linux family; and
  macOS stays a Non-Goal (`prd.md:175`) or becomes a nice-to-have. — Actor: user

## What Changes for /rune-plan

The plan covers three host-side problems, each with its own decision:

- **Lifetime:** the window owns the session, and the console's information (LAN address,
  firewall advice, TV found) gets a home in the UI.
- **Presentation:** which window, chosen against the spike data and the PRD constraints.
- **OS presence:** an icon or launcher entry, or explicitly none.

The phone path stays untouched. The PRD lines above are settled before the plan picks a
toolkit.

## References

- **Source files:** `packaging/cast-tv.spec:1-3,24`; `castlib/app.py:234-249,262-264,311-312`;
  `castlib/cli.py:268-275,321`; `castlib/platform.py:293-354`; `castlib/api.py:104-108,157-162`;
  `castlib/ui/app.js:106-111`; `castlib/server.py:195-198`; `castlib/auth/browser.py:41,153`;
  `.github/workflows/release.yml:37-48`; `context/foundation/prd.md:59-60,70,154-156,175`;
  `context/foundation/roadmap.md:139-147`.
- **Related research:** `context/changes/s12-desktop-window/research.md` (two spikes,
  2026-10-15).
- **Investigation:** dimensions 1 and 3 delegated to one search agent, dimension 2 to another;
  dimension 4 from the spikes.
- **Pressure test:**
  - Independent search ran, carrying the observation only. It found the same three causes.
  - Prior occurrences checked: the cloud-source-ui and S-13 decisions.
  - Inverse checked: what else the console carries.
  - Lessons: 1 of 6 entries applied to this stage ("Look at every branch and PR before
    building"; checked: no open PRs or unmerged branches).
