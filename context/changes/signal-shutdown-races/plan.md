# Signal and shutdown races Implementation Plan

## Overview

Make cast-tv end cleanly on Ctrl+C or `kill` at any moment, and with that make the two subprocess
signal tests reliable on Ubuntu CI. `research.md` found three faults, all in the app: SIGTERM before
`run_forever()` installs its handler (A), Ctrl+C while `App.start` runs (B), and a
`KeyboardInterrupt` inside `Event.wait()` that leaves the Event's lock held, so `close()` hangs (C).
The two subprocess tests also learn to print every thread's stack when the child does not exit, so
any hang left over names where it waits.

## Current State Analysis

- **A**: `run_forever()` installs the SIGTERM handler (`castlib/app.py:260-273`, the call is at
  `:272`). `cli.ui()` calls `App.start` (`castlib/cli.py:266`) and then `run_forever()` (`:279`).
  A SIGTERM in between takes the default action. The SIGTERM test prints `ready`
  (`tests/test_gphotos.py:1245`) before `run_forever()` (`:1246`), so it hits that gap. CI run
  38617411291 failed with `-15`.
- **B**: `App.start` prints the addresses, the firewall advice, the Ctrl+C hint and the `TV:` or
  `does not expose` line (`castlib/app.py:191-209`), and only then returns. `cli.ui()` catches
  only `AlreadyRunning` and `OSError` around it (`castlib/cli.py:265-277`). A `KeyboardInterrupt` in
  `App.start` exits -2 with a traceback, and neither `interrupted()` nor `close()` runs. This was
  reproduced in 17 of 25 runs under load (`research.md`, "B"; `race-probes.md` §1).
- **C**: three main-thread loops wait with `Event.wait(t)`: `run_forever()` (`castlib/app.py:275`),
  the one-shot cast (`castlib/cli.py:163`) and the slideshow (`:237`). `Event.wait` and `Event.set`
  share the Condition lock, and Condition's `__enter__`/`_acquire_restore` are Python code where a
  `KeyboardInterrupt` can be raised with the lock taken. The mechanism was reproduced in plain Python
  (`race-probes.md` §2, 2 `LOCK-HELD` in 400). In CI run 38618655818 the child printed `Stopped.` and
  then hung, which matches `close()` blocking in `self._closed.set()` (`castlib/app.py:292`).
  Python 3.12 (CI) and 3.14.8 (local) have identical code there (`research.md`, "C").
- The deterministic tests from `81097b8` stay valid: `test_ctrl_c_while_the_handler_is_installed_still_stops`
  and `test_ctrl_c_before_run_forever_takes_over` (`tests/test_cli.py:196-224`).
  `test_cast_replaced_from_the_ui_keeps_serving` ends `run_forever()` by calling `app._closed.set()`
  from another thread (`tests/test_cli.py:134`), which the new wait must still honour.
- `App.start` is called in-process by `test_addrinuse_attaches_to_running_instance`
  (`tests/test_discovery.py:121-133`). Both of its calls fail at the bind, before anything this
  plan adds.

### Carried from predecessor

none — no Predecessor line

## Definitions

Ledger: no domain terms beyond "Ctrl+C at startup ends cast-tv like any other Ctrl+C". Its meaning
is decided. It prints `Stopped.`, sends Stop to the TV when one is selected, closes every
source and frees the port, with exit status 0. Origin: `product`, from the owner-reviewed
cloud-source-ui fix `81097b8` (`context/archive/2026-09-07-cloud-source-ui/plan.md:1468-1473`).

| Term | Decided meaning | Origin | On degenerate data | Verified by |
| ---- | --------------- | ------ | ------------------ | ----------- |
| Ctrl+C at startup | Same as Ctrl+C later: `Stopped.`, Stop to a selected TV, sources closed, port freed, exit 0 | product (`81097b8`) | Before the `App` exists (still binding), or before its HTTP loop runs (owner decision 2026-10-14, impl-review F1): nothing to stop; the port is released and the exit is quiet, status 0 | 2.1, 2.2, 2.3 |

## Desired End State

- A `kill` (SIGTERM) sent at any moment after cast-tv has printed its first line ends it like Ctrl+C:
  `Stopped.`, sources closed, exit 0. The SIGTERM test's `ready` line now comes after the
  handler is installed, and its child prints `ready` and runs `run_forever()` inside a `try`
  with `cli.ui()`'s `KeyboardInterrupt` fallback (owner decision 2026-10-14, impl-review F2).
- A Ctrl+C during `App.start` ends cast-tv like a later Ctrl+C, with no traceback.
- No main-thread loop waits in `Event.wait`. A Ctrl+C can no longer leave an Event's lock held, so
  `close()` cannot hang on `self._closed.set()`.
- When either subprocess test's child does not exit in time, the test fails with the child's thread
  stacks in its message, not a bare `TimeoutExpired`.
- Verification: the full suite, the new deterministic tests, the race probe under load, CI on the
  PR, and two terminal checks on the Fedora PC (Phase 3).

### Key Discoveries:

- `Event.is_set()` reads `_flag` without the lock (CPython `threading.py`, `Event.is_set`). A loop
  of `time.sleep` plus `is_set()` therefore holds no lock at any moment a `KeyboardInterrupt` can
  arrive.
- Every thread cast-tv starts is a daemon (`research.md`, "C"). After `close()` nothing else keeps
  the process alive, so `close()` returning is enough for a clean exit.
- `ErrorRing` and `App.lock` are C-level `threading.Lock`/`RLock` (`castlib/app.py:60, 90, 138`),
  not Condition-based. See Open Risks: this plan relies on, but does not prove, that a plain
  `with lock:` cannot be left half-entered.
- A test can inject a `KeyboardInterrupt` without signals or subprocesses by monkeypatching a
  function the code calls. The existing `81097b8` tests already do this.

## What We're NOT Doing

- `castlib/cli.py:146` (`c.sent.wait()` outside the `KeyboardInterrupt` handler, exit 130 without
  `Stopped.`). It is a known gap from the cloud-source-ui phase-3 review and stays out unless the
  owner adds it.
- A second signal while the first is being handled (Ctrl+C pressed twice, or SIGTERM during the
  cleanup). The cleanup itself is not made re-entrant.
- Windows. Both subprocess tests stay skipped there, and console close keeps its own path
  (`castlib/platform.py` `ConsoleClose`). The new wait polls about every 50 ms, so
  `_thread.interrupt_main()` from that handler is acted on no later than today's 1 s wait does.
- Waits in daemon threads (`_evict_loop`, `_tv_watch`, the supervisor). Signals are delivered only
  to the main thread.
- Any change to what a normal Ctrl+C prints or does.

## Implementation Approach

Fix the app, not the tests. Phase 1 replaces the three main-thread `Event.wait` calls with one
helper, `main_wait`, which sleeps in short steps and checks `is_set()`. Phase 2 installs the
SIGTERM handler as soon as `App.start` has bound its port, before it prints anything. It also makes
a `KeyboardInterrupt` during the rest of `App.start` stop and close the app, then lets `cli.ui()`
return 0. Phase 3 gives both subprocess tests a timeout path that dumps the child's thread stacks,
then runs the probe and the terminal checks. Each fault gets an in-process test that injects the
`KeyboardInterrupt` deterministically, so the suite proves each fix without depending on timing.

## Critical Implementation Details

- **Timing & lifecycle**: install the SIGTERM handler *after* `Server(...)` binds. A
  failed bind (`AlreadyRunning`, `OSError`) must leave the process's signal disposition untouched,
  because `test_addrinuse_attaches_to_running_instance` runs in pytest's own process. Install it
  *before* the first `print` in `App.start`, so that any line a test or user reads means the
  handler is in place. Only the main thread may call `signal.signal`; keep the existing
  `current_thread() is main_thread()` guard and the `ValueError`/`OSError` swallow.
- **State sequencing**: when a `KeyboardInterrupt` reaches `App.start` after `app.serve()` has
  returned, run `app.interrupted()`, then `app.close()`, then re-raise. `cli.ui()` then returns 0
  without calling them again. Before that, close only the bound server socket: `close()` calls
  `server.shutdown()`, which waits for a `serve_forever` loop. `cli.cast` and `cli.show` call
  `app.serve()` before the `try` whose `finally` closes the app, for the same reason (owner
  decision 2026-10-14, impl-review F1 and F3). Tests that call
  `App.start` in-process must restore the original SIGTERM handler afterwards.

## Phase 1: The main thread waits without Event.wait

### Overview

Fault C. One helper with `Event.wait`'s contract that never takes the Event's lock, used by the
three main-thread loops.

### Changes Required:

#### 1. The helper and `run_forever`

**File**: `castlib/app.py`

**Intent**: add a module-level `main_wait(event, timeout, sleep=time.sleep)` that returns as soon as
`event.is_set()`, or `False` after `timeout`. It sleeps in steps of at most 0.05 s and never calls
`event.wait`. `run_forever()` loops on `main_wait(self._closed, 1.0)` instead of
`self._closed.wait(1.0)`. Its docstring says why: a `KeyboardInterrupt` inside `Event.wait` can
leave the Event's lock held.

**Contract**: `main_wait(event: threading.Event, timeout: float, sleep=time.sleep) -> bool`, which
returns the same values as `Event.wait(timeout)`. `run_forever()`'s behaviour and return value are
unchanged. Setting `_closed` from another thread still ends it, within about 50 ms.

#### 2. The CLI loops

**File**: `castlib/cli.py`

**Intent**: the one-shot cast loop (`_follow`, `:163`) and the slideshow loop (`show`, `:237`) wait
with `main_wait(c.done, 0.5)` and `main_wait(sh.done, 0.5)`. Their `except KeyboardInterrupt`
paths stay as they are.

**Contract**: `from castlib.app import AlreadyRunning, App, main_wait`. Output and exit codes are unchanged.

#### 3. Tests

**File**: `tests/test_cli.py`

**Intent**: deterministic tests for the helper and the three call sites.

**Contract**: the new tests are:
- `test_main_wait_behaves_like_event_wait`: `True` at once when set, `False` after the timeout,
  `True` soon after another thread sets it;
- `test_ctrl_c_inside_main_wait_leaves_the_event_usable`: the injected `sleep` raises
  `KeyboardInterrupt`; afterwards `event.set()` returns and `event._cond._lock.acquire(timeout=1)`
  succeeds;
- `test_run_forever_ctrl_c_in_its_wait_stops_and_closes`: `castlib.app.main_wait` is patched to
  raise `KeyboardInterrupt`; `run_forever()` returns 0, prints `Stopped.`, sends Stop, and
  `_closed` is set;
- `test_run_forever_does_not_wait_on_the_event_in_the_main_thread`: `app._closed.wait` replaced by
  a function that fails the test; `run_forever()` ended by `_closed.set()` from another thread;
- `test_cast_and_show_ctrl_c_in_their_wait_print_stopped`: through `cli_env`, with
  `castlib.cli.main_wait` patched to raise `KeyboardInterrupt`, `cli.cast` and `cli.show` both
  return 0 and print `Stopped.`.

### Success Criteria:

#### Automated Verification:

- The new Phase 1 tests pass: `.venv/bin/python -m pytest -q tests/test_cli.py -k "main_wait or in_its_wait or does_not_wait_on_the_event"` — not run: needs Phase 1 output
- No main-thread Event wait is left in the loops: `test -z "$(grep -nE '(_closed|c\.done|sh\.done)\.wait\(' castlib/app.py castlib/cli.py | grep -vE '_evict_loop|_tv_watch|EVICT_EVERY|TV_WATCH_EVERY')"` — at planning: exit 1 — expected until Phase 1 (finds `app.py:275`, `cli.py:163`, `cli.py:237`)
- The whole suite passes: `.venv/bin/python -m pytest -q` — at planning: exit 0
- Pyflakes is clean: `.venv/bin/python -m pyflakes castlib tests` — at planning: exit 0

---

## Phase 2: Signals during startup

### Overview

Faults A and B. The SIGTERM handler is in place before `App.start` prints anything. A
`KeyboardInterrupt` during the rest of `App.start` ends cast-tv like any other Ctrl+C.

### Changes Required:

#### 1. `App.start` and the handler

**File**: `castlib/app.py`

**Intent**: move the SIGTERM installation out of `run_forever()` into a module helper,
`end_on_sigterm()`. That covers the main-thread guard, `_term` raising `KeyboardInterrupt`, and the
swallowed `ValueError`/`OSError`. `App.start` calls it right after the bind succeeds, before the
first `print`. `run_forever()` keeps calling it inside its `try`, as `81097b8` requires, because
`cli._taken_over` reaches `run_forever()` without `App.start`. The body of `App.start` after the
bind is wrapped. On `KeyboardInterrupt` it calls `app.interrupted()` and `app.close()` when `app`
exists, otherwise `server.server_close()`, and then re-raises.

**Contract**: `end_on_sigterm() -> None` is idempotent and does nothing off the main thread.
`App.start`'s signature, return value and the exceptions it raises before the bind are unchanged.
After the bind, a `KeyboardInterrupt` leaves it with the app already stopped and closed.

#### 2. `cli.ui()`

**File**: `castlib/cli.py`

**Intent**: catch `KeyboardInterrupt` from `App.start` and return 0. `App.start` has already
printed `Stopped.` and cleaned up. The existing fallback after `App.start`
(`except KeyboardInterrupt` around `run_forever()`) stays.

**Contract**: `ui()` returns 0 for a Ctrl+C at any point after the bind.

#### 3. Tests

**File**: `tests/test_cli.py`

**Intent**: deterministic tests for A and B, with in-process `App.start` sandboxed the way the `app`
fixture is (tmp config and cache, `discover` returning nothing, browser off, a free port). The
original SIGTERM handler is restored after each test.

**Contract**: the new tests are:
- `test_start_installs_the_sigterm_handler_before_its_first_line`: `App.start(..., out=recorder)`,
  where the recorder notes `signal.getsignal(SIGTERM)` at its first write. That handler raises
  `KeyboardInterrupt`;
- `test_ctrl_c_during_start_stops_and_frees_the_port`: a function `App.start` calls after the
  addresses (for example `castlib.app.firewall_blocked`) raises `KeyboardInterrupt`; `cli.ui(...)`
  returns 0, the output has `Stopped.`, and the port can be bound again;
- `test_ctrl_c_before_the_app_exists_frees_the_port`: `App.__init__` raises `KeyboardInterrupt`;
  `cli.ui(...)` returns 0 and the port can be bound again;
- `test_failed_bind_leaves_sigterm_alone`: after the `AlreadyRunning` and `OSError` paths,
  `signal.getsignal(SIGTERM)` is what it was before.

### Success Criteria:

#### Automated Verification:

- The new Phase 2 tests pass: `.venv/bin/python -m pytest -q tests/test_cli.py -k "first_line or during_start or before_the_app_exists or failed_bind"` — not run: needs Phase 2 output
- The existing signal tests pass: `.venv/bin/python -m pytest -q tests/test_cli.py tests/test_gphotos.py -k "sigint or sigterm or ctrl_c"` — at planning: exit 0
- The whole suite passes: `.venv/bin/python -m pytest -q` — at planning: exit 0
- Pyflakes is clean: `.venv/bin/python -m pyflakes castlib tests` — at planning: exit 0

---

## Phase 3: Subprocess tests report where a hang waits, and the checks

### Overview

The owner's decision: even with C fixed, a subprocess test that times out must say where the
child waited. Then the race probe and two terminal checks confirm the fixes on a real process.

### Changes Required:

#### 1. A timeout that dumps stacks

**Files**:
- `tests/conftest.py`: add a helper, `finish_or_dump(proc, timeout)`. It returns the child's
  remaining output once the child exits. On `TimeoutExpired` it sends `SIGABRT`, reads what
  faulthandler printed, and calls `pytest.fail` with that output.
- `tests/test_cli.py`, `tests/test_gphotos.py`: both subprocess tests set `PYTHONFAULTHANDLER=1`
  in the child's environment and end through the helper, instead of `communicate(timeout=15)` and
  `wait(timeout=10)`.

**Intent**: a future hang fails with every thread's stack in the message.

**Contract**: `finish_or_dump(proc: subprocess.Popen, timeout: float) -> str`, POSIX only, like the
tests that use it. `test_finish_or_dump_names_the_waiting_frame` runs a child that blocks forever
in `threading.Event().wait()`, with a 1 s timeout, and checks that the failure text contains
`Current thread` or `Thread 0x` and `wait`.

### Success Criteria:

#### Automated Verification:

- The helper's test passes: `.venv/bin/python -m pytest -q tests/test_cli.py -k finish_or_dump` — not run: needs Phase 3 output
- The two subprocess tests pass ten times in a row: `for i in $(seq 10); do .venv/bin/python -m pytest -q tests/test_cli.py tests/test_gphotos.py -k "exits_cleanly_on_sigint or sigterm_closes" || exit 1; done` — at planning: exit 0
- The whole suite passes: `.venv/bin/python -m pytest -q` — at planning: exit 0
- Pyflakes is clean: `.venv/bin/python -m pyflakes castlib tests` — at planning: exit 0
- CI passes on the PR, Ubuntu and Windows: `gh pr checks <PR>` — not run: external

#### Manual Verification:

- Under CPU load, the race probe sends SIGINT 0 s after the `does not expose` line in 25 runs, and every run is `exit 0 Stopped` (before the fix: 17 of 25 exited -2). Run by Claude with `race-probes.md` §1; the result is recorded in `research.md` — surface: castlib/app.py, castlib/cli.py
- In a terminal on the Fedora PC, `.venv/bin/cast-tv --no-browser` is started. Pressing Ctrl+C in that terminal as soon as the `http://localhost:8895/ui/` line appears prints `Stopped.`, and the prompt returns within 2 s. Run by Claude; recorded in `research.md` — surface: castlib/app.py, castlib/cli.py
- A second run of `.venv/bin/cast-tv --no-browser` is started. Then `kill <its pid>` from another terminal makes the first terminal print `Stopped.`, and it exits with status 0 (`echo $?`). Run by Claude; recorded in `research.md` — surface: castlib/app.py

**Implementation Note**: Manual checks are acceptance. Each needs a written observation in
`research.md` before its row is ticked (lessons: "A ticked manual row needs a written observation").

---

## Testing Strategy

### Unit Tests:

- `main_wait` semantics, and the Event staying usable after a `KeyboardInterrupt` inside it (Phase 1).
- Each main-thread loop takes its Ctrl+C path when its wait raises (Phase 1).
- The SIGTERM handler is installed before `App.start`'s first line, and is left alone when the bind fails (Phase 2).
- A Ctrl+C during `App.start`, with and without an `App`, ends with exit 0 and a free port (Phase 2).
- The timeout helper reports the child's stacks (Phase 3).

### Integration Tests:

- The two subprocess tests, unchanged in what they assert, run ten times in a row (Phase 3).

### Manual Testing Steps:

1. Under CPU load, run `race-probes.md` §1 with delay 0, 25 runs: all `exit 0 Stopped`.
2. In a terminal, start `.venv/bin/cast-tv --no-browser`, then press Ctrl+C at the first address line: it prints `Stopped.` and the prompt returns.
3. Start it again, then `kill <pid>` from a second terminal: `Stopped.`, and `echo $?` prints 0.

## Performance Considerations

`main_wait` wakes every 50 ms in the main thread while cast-tv waits. That is a few dozen
wake-ups per second at no measurable CPU cost, and it is how promptly `_closed.set()` and Windows
console close are noticed.

## References

- Research: `context/changes/signal-shutdown-races/research.md`, probes in `race-probes.md`
- Prior fix: `81097b8` and `context/archive/2026-09-07-cloud-source-ui/plan.md:1468-1473`
- Deterministic-test pattern: `tests/test_cli.py:196-224`

## Progress

> Convention: `- [ ]` pending, `- [x]` done, `- [-]` not applicable (` — n/a: <reason>` required). Append ` — <commit sha>` when a step lands. A Manual row takes ` — accepted at <full sha>` when a human confirms it. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: The main thread waits without Event.wait

#### Automated

- [x] 1.1 The new Phase 1 tests pass — e39716a
- [x] 1.2 No main-thread Event wait is left in the loops — e39716a
- [x] 1.3 The whole suite passes — e39716a
- [x] 1.4 Pyflakes is clean — e39716a

### Phase 2: Signals during startup

#### Automated

- [x] 2.1 The new Phase 2 tests pass — 4cdcfbd
- [x] 2.2 The existing signal tests pass — 4cdcfbd
- [x] 2.3 The whole suite passes — 4cdcfbd
- [x] 2.4 Pyflakes is clean — 4cdcfbd

### Phase 3: Subprocess tests report where a hang waits, and the checks

#### Automated

- [x] 3.1 The helper's test passes — 0e33b39
- [x] 3.2 The two subprocess tests pass ten times in a row — 0e33b39
- [x] 3.3 The whole suite passes — 0e33b39
- [x] 3.4 Pyflakes is clean — 0e33b39
- [x] 3.5 CI passes on the PR, Ubuntu and Windows — 0e33b39

#### Manual

- [x] 3.6 Race probe under load: every run exit 0 Stopped — accepted at 89a10050affd2102ca7692994dd64d7d5834b0e2
- [x] 3.7 Ctrl+C at the first address line prints Stopped and returns — accepted at 89a10050affd2102ca7692994dd64d7d5834b0e2
- [x] 3.8 kill ends cast-tv with Stopped and status 0 — accepted at 89a10050affd2102ca7692994dd64d7d5834b0e2
