# Signal and shutdown races — Plan Brief

> Full plan: `context/changes/signal-shutdown-races/plan.md`
> Research: `context/changes/signal-shutdown-races/research.md` (probes: `race-probes.md`)

## What & Why

Two subprocess tests fail now and then on Ubuntu CI, on commits that change no code. The research
found the cause in the app, not the tests, and the same faults can hit a user. A `kill` or Ctrl+C
at the wrong moment ends cast-tv without stopping the TV or closing the sources, or leaves it hung
after `Stopped.`. This plan makes cast-tv end cleanly at any moment, and makes the tests report
where any remaining hang waits.

## Starting Point

- SIGTERM gets its handler only in `run_forever()`, after `App.start` has printed everything (A).
- A Ctrl+C during `App.start` escapes `cli.ui()` as a traceback (B).
- Three main-thread loops wait in `Event.wait`, where a Ctrl+C can leave the Event's lock held, so
  `close()` blocks forever in `_closed.set()` (C). Reproduced: B in 17 of 25 runs under load; C's
  mechanism in plain Python.

## Desired End State

Ctrl+C or `kill` at any point after the first printed line gives `Stopped.`, sources closed, the
port freed, and exit 0. No main-thread loop waits in `Event.wait`. If a subprocess test's child
ever hangs again, the failure shows every thread's stack.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Where to fix | In the app, not by loosening the tests | All three faults also hit users | Research |
| C: fix or only diagnose | Both: fix, and dump stacks on test timeouts | The owner wants proof if anything is left | Owner, 2026-10-14 |
| C: which waits | All three main-thread loops (`run_forever`, cast, show) | Same mechanism, same one-line fix | Owner, 2026-10-14 |
| How the main thread waits | `main_wait`: 50 ms sleeps plus `is_set()`, no Event lock | `is_set()` takes no lock, and `time.sleep` holds none | Plan |
| When SIGTERM is handled | Right after the bind in `App.start`, before the first line | A failed bind leaves pytest's handler alone; any printed line means "handler ready" | Plan |
| Ctrl+C during startup | Same as later: `Stopped.`, Stop, close, exit 0 | Decided in `81097b8` for the same window's sibling | Archive (`81097b8`) |
| Who runs the manual rows | Claude, recorded in `research.md` | Terminal-only checks, no TV involved | Plan (memory: agent drives) |

## Scope

**In scope:** the `main_wait` helper and its three call sites; the SIGTERM handler in `App.start`;
cleanup on Ctrl+C during `App.start`; a stack-dumping timeout for the two subprocess tests;
deterministic tests for each fault.

**Out of scope:** `cli.py:146` `c.sent.wait()` (known gap); a second signal during the cleanup;
Windows (tests stay skipped); waits in daemon threads.

## Architecture / Approach

The deterministic tests inject `KeyboardInterrupt` by monkeypatching, as the `81097b8` tests do, so
each fix is proven without timing luck. The subprocess tests keep what they assert. Their timeout
path sends SIGABRT to a child running with `PYTHONFAULTHANDLER=1` and fails with the dump.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Main thread waits without Event.wait | `main_wait` in `run_forever`, cast and show loops (C) | A loop that relied on `Event.wait`'s exact timing; covered by the existing suite |
| 2. Signals during startup | SIGTERM handler before the first line; Ctrl+C in `App.start` cleans up (A, B) | In-process tests that change pytest's SIGTERM handler must restore it |
| 3. Stack dump on timeout, and the checks | Helper plus its test; probe under load; two terminal checks | Only CI over time can show C is gone for good |

**Prerequisites:** branch `signal-shutdown-races` from `main` `0d55ede` (exists).
**Estimated effort:** one session, three small phases.

## Open Risks & Assumptions

- C is fixed on the mechanism, not on a reproduced hang of cast-tv itself (more than 200 local runs
  never hung). The stack dump covers this.
- Assumed, not proven: a plain C-level `Lock`/`RLock` in a `with` statement cannot be left
  half-entered by a `KeyboardInterrupt`, unlike the Python-level Condition inside an Event. If it
  can, `App.lock` has the same hazard in a smaller window.

## Success Criteria (Summary)

- The two subprocess tests pass ten times in a row locally and on the PR's CI.
- Under load, the race probe shows no -2 exits (was 17 of 25).
- Ctrl+C and `kill` in a terminal both print `Stopped.` and exit 0.
