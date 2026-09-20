# Frame Brief: Samsung screen saver during DLNA playback

> Framing step before `/10x-plan`. This document separates the observed failure
> from the initially proposed workarounds.

## Reported Observation

"Na TV pokazuje się wygaszacz w trakcie trwania slideshow, czy długiego filmu - jak to
obejść?" The owner confirmed that it occurs both during a slideshow and during a normally
playing long video, and that changing to the next slide does not reset it.

During the recorded photo incident the Samsung still reported AVTransport `PLAYING`, cast-tv
reported no error, and the media was present behind the TV's own screen saver.

## Initial Framing (preserved)

- **User's stated cause or approach:** investigate TV settings, DLNA keepalive tricks,
  Samsung's remote-control WebSocket API, or representing the slideshow as one video.
- **User's proposed direction:** decide which of those escape routes deserve serious research.
- **Pre-dispatch narrowing:** the symptom affects both moving video and slides; a fresh slide
  does not reset it.

## Dimension Map

The observation could originate at any of these dimensions:

1. **TV-side inactivity or panel-protection policy** — the TV overlays or blanks the picture
   independently of whether its DLNA renderer remains in `PLAYING`.
2. **DLNA/AVTransport activity semantics** — playback, control calls and status reads might not
   count as user activity to the Samsung.
3. **Samsung input-activity channel** — only a remote-control event may reset or cancel the
   TV-side timer; feasibility depends on an undocumented, model-specific interface.
4. **Media representation** — the TV might treat a video stream as active but a photo as idle.

## Hypothesis Investigation

| Hypothesis | Evidence | Verdict |
| --- | --- | --- |
| A TV policy owns the visible screen independently from AVTransport | The live record has the saver over a fetched photo while AVTransport stayed `PLAYING` (`standalone-install/research.md:158-169`). Samsung's S8\*F/S9\*F manual documents OLED screen protection, Auto Energy Saving, Auto Power Off and Auto Picture Off as TV-side policies. | **STRONG** |
| An ordinary TV setting may remove the cause | Auto Energy Saving and Auto Picture Off are configurable and are driven by lack of interaction, which fits both slides and moving video. The protective OLED Screen Saver itself is documented as non-disableable. The exact policy seen on this TV is not yet identified. | **PARTIAL** |
| DLNA calls or metadata can act as keepalive | Every slide already receives `SetAVTransportURI` and `Play` (`castlib/supervisor.py:120-167`, `:442-472`). The app already polls `GetPositionInfo` and `GetTransportInfo` every two seconds (`castlib/supervisor.py:45`, `:292-317`; `castlib/dlna.py:27-31`). UPnP defines those as media control/state actions, not user-presence signals. The user's observation shows that neither a fresh slide nor continuous video transfer resets the saver. | **NONE** as a serious path; one bounded `Play` A/B test could close it |
| A remote event resets the TV-side timer | Samsung documents that a remote button cancels the OLED saver. Maintained third-party integrations implement the Tizen remote channel on `wss://TV:8002/api/v2/channels/samsung.remote.control`, but Samsung does not document that external API. Exact S85F availability, token persistence, a harmless key, and prevention rather than merely dismissal remain untested. | **PARTIAL**, worthy of a hardware spike |
| Encoding the slideshow as video avoids the saver | The user sees the same symptom during a real, normally playing long video. Producing video from stills also requires encoding and conflicts with the PRD's original-byte/no-transcoding boundary (`context/foundation/prd.md:30-33`). | **NONE / contradicted** |

## Narrowing Signals

- A normally playing long video does not keep the screen active.
- Changing slides, which creates a new cast and new AVTransport commands, does not reset it.
- The TV can show the saver while continuing to report `PLAYING`; cast-tv cannot observe the
  overlay through AVTransport.
- Samsung documents remote input as a way to cancel the saver, but not DLNA activity as one.
- Samsung's model page currently lists firmware `1301.0` dated 2026-09-08; the installed
  version must be recorded before interpreting a model-specific failure as intended behavior.

The evidence is decisive enough to skip another solution-choice question: the two media-path
hypotheses are contradicted, while the TV-policy hypothesis directly predicts the observation.

## Cross-System Convention

UPnP AVTransport is a media transport control surface. `GetTransportInfo` reads transport state;
`SetAVTransportURI` binds a resource; `Play` establishes playback. The standard exposes no
screen-saver or user-presence state, so a control point cannot infer whether a TV-owned overlay
is covering valid playback.

Samsung's own convention is separate: the OLED saver and energy features are owned by the TV,
and remote input is treated as activity. This matches the observed split between a `PLAYING`
renderer and an inactive visible screen.

## Reframed Problem Statement

> **The actual problem to plan around is:** this Samsung can classify a valid DLNA session as
> inactive at the TV UI/panel-policy layer, cover the picture while AVTransport remains
> `PLAYING`, and expose neither the overlay nor a standard keep-awake control through DLNA.

The first unknown is which documented TV-side policy is firing: a configurable energy/accessibility
option or the non-disableable OLED protection. Only after that distinction is measured does it
make sense to test whether a paired Samsung remote event can safely maintain activity. Changing
the media representation or adding DLNA traffic does not address the evidenced boundary.

## Confidence

- **HIGH** for the reframe: live behavior, current code and the device documentation agree that
  the visible-screen policy is outside AVTransport.
- **MEDIUM** for the remote-channel escape hatch: the mechanism fits, but the exact TV and a
  genuinely harmless key have not been verified.

## What Changes for `/10x-plan`

Do not plan video generation or general DLNA keepalive work. First record firmware and run a
small settings matrix for Auto Energy Saving, Auto Power Off and Auto Picture Off. If the
symptom remains, perform a bounded Samsung-remote feasibility spike before planning product
integration; keep it an optional Samsung capability because the secondary persona owns an
arbitrary DLNA renderer.

## References

- Source observation: `context/changes/s11-screensaver/change.md:14-27`
- Live incident: `context/changes/standalone-install/research.md:158-169`
- Playback and polling: `castlib/supervisor.py:45`, `:120-167`, `:292-317`, `:442-472`
- AVTransport reads: `castlib/dlna.py:27-31`
- Product boundary and personas: `context/foundation/prd.md:30-48`
- Samsung model support: <https://www.samsung.com/pl/support/model/QE83S85FAEXXH/>
- Samsung OLED protection: <https://www.samsung.com/pl/support/tv-audio-video/jak-zapobiegac-wypalaniu-pikseli-na-ekranie-telewizora-oled/>
- UPnP AVTransport: <https://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf>
- Investigation tasks: `/root/tv_policy`, `/root/dlna_hypothesis`, `/root/remote_video`
