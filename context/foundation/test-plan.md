# Test Plan

> Living document; edit in place. Written 2026-09-19 from the test suite, the CI workflows and the
> manual rows of `cloud-source-ui` and `standalone-install`.

## 1. Strategy

Two layers, because CI has no TV:

- **Automated** - everything up to the wire: discovery parsing, DIDL and MIME, the relay and
  `Range`, the registry, photo conversion, each source against a scripted fake of its cloud, the
  API, the supervisor and slideshow against a fake of the TV's SOAP, the UI markup, the CLI, the
  platform hooks. Runs on every PR and every push to `main`, on Ubuntu and Windows.
- **Manual** - what only the Samsung can prove: that the TV fetches, plays, seeks and stops, that
  a sign-in completes against the real Microsoft and Google, that Windows' console, sleep and
  firewall behave. Each manual row is run by a person, observed, and written down.

## 2. Risk Map

| Risk | Where it bites | Covered by |
| --- | --- | --- |
| A web page on the LAN drives the TV | `/api`, `/ui` | `test_server.py` (Host/Origin, media token), `test_ui.py` (no external URLs) |
| The TV refuses or stalls on a source | relay, DIDL, supervisor | `test_relay.py`, `test_range.py`, `test_media.py`, `test_supervisor.py`; manual rows on the TV |
| An expiring cloud URL dies mid-film | Graph `downloadUrl`, Picker `baseUrl` | `test_relay.py` (re-resolve once), `test_gphotos.py`, `test_onedrive.py` |
| A token leaks or a secret is published | config, release | 0600 checks in `test_config.py`; `write_client.py` prints nothing; `git grep GOCSPX` |
| Windows diverges from Linux | console, sleep, firewall, paths | `test_platform.py`, the Windows CI runner, manual rows 7.x |
| A release binary misses a native library | PyInstaller bundle | `packaging/smoke.py` in the release workflow (`--self-check` decodes a HEIC) |
| A sign-in flow changes upstream | Google, Microsoft, GoPro | fakes cannot see it; manual re-check when a flow is touched |

## 3. Stack

- `pytest` and `pyflakes` (`pip install -e ".[test]"`), `pythonpath = ["."]`.
- Fakes: `tests/conftest.py::FakeTV` (the TV's SOAP and its fetches), `FakeGoPro`,
  `FakeMicrosoft`, `FakeGoogle` (HTTP servers on 127.0.0.1), a scripted `urllib` transport for
  share links (`test_gphotos.py::_Transport`).
- Fixtures: an in-process `Server` on port 0 (`server`), a full `App` with a fake TV (`app`),
  generated media in `tests/fixtures/make.py`.
- 272 tests collected in 16 files (2026-09-19; parametrised cases counted). Five are platform-bound: three need POSIX
  signals to a child and one reads Linux's `fib_trie` (skipped on Windows), one needs
  `ctypes.WINFUNCTYPE` (skipped elsewhere).

## 4. Quality Gates

| Gate | When | What must pass |
| --- | --- | --- |
| `test` workflow | every PR, every push to `main` | pyflakes on `castlib` and `tests`; pytest; on `ubuntu-latest` and `windows-latest` |
| `release` workflow | a PR touching `packaging/` or the workflow; every `v*` tag | build on `windows-latest` and `ubuntu-22.04`; `smoke.py`: client built in, `--self-check`, `/ui/` and `/api/status` answer. A tag publishes only if both builds pass |
| Manual rows | before a plan row is ticked | a written observation in the change's `research.md` (`lessons.md`, "A ticked manual row needs a written observation") |
| Merge | always | the owner merges with Rebase and merge; nothing is merged by the agent |

## 5. Cookbook Patterns

### 5.1 A new source behaviour
Extend the source's fake (`FakeGoogle`, `FakeMicrosoft`, `FakeGoPro`) with the upstream answer,
then test through the source object and once through the API (`app` fixture), as
`test_pick_and_link_over_api` does.

### 5.2 A cast or slideshow behaviour
Use the `app` fixture: `app.tv_fake` records SOAP calls and fetches; `fast_supervisor` shortens
the budgets. Assert on the TV's calls, not on timing.

### 5.3 A UI change
The UI has no JS test runner. `test_ui.py` asserts on the markup and `app.js` text (the element
exists, is in the right section, calls the right function); `node --check castlib/ui/app.js` for
syntax; the behaviour is a manual row with a screenshot.

### 5.4 A Windows-only path
Put the OS call behind an injectable (`kernel32=`, `run=`, `which=`) and test the logic with a
fake on both runners, as `test_platform.py` does; the real call is a manual row on Windows.

### 5.5 A manual row
Name exactly where the person acts (which window, which button), run it, record in `research.md`
the row, date and time, device, material and what was observed - the person's words as their
words - then tick the row with the commit.

## 6. What We Deliberately Don't Test

- A real DLNA renderer in CI (no fake renderer implementation beyond SOAP answers; decided in
  `cloud-source-ui/plan.md`, "What We're NOT Doing").
- Live Google, Microsoft or GoPro endpoints in CI.
- Browser behaviour of the UI (no Playwright): the UI is small, and its failures show on the TV.

## 7. Freshness Ledger

| Date | Change |
| --- | --- |
| 2026-09-19 | Written; covers the `release` workflow from `standalone-install` Phase 2. |
