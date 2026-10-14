---
date: 2026-10-14T21:38:33+02:00
researcher: Claude (Opus 5.5) with Piotr Miller
git_commit: 0d55ede7d71209c1b1b1f1a775ed7eca3cf0f47d
branch: signal-shutdown-races
repository: cast-tv
topic: "Why the SIGTERM and SIGINT subprocess tests fail intermittently on Ubuntu CI"
tags: [research, codebase, signals, ci, app, cli, threading]
status: complete
last_updated: 2026-10-14
last_updated_by: Claude (Opus 5.5)
---

# Research: Why the SIGTERM and SIGINT subprocess tests fail intermittently on Ubuntu CI

**Date**: 2026-10-14T21:38:33+02:00
**Researcher**: Claude (Opus 5.5) with Piotr Miller
**Git Commit**: 0d55ede7d71209c1b1b1f1a775ed7eca3cf0f47d
**Branch**: signal-shutdown-races
**Repository**: cast-tv

## Research Question

Two subprocess tests failed on Ubuntu CI on 2026-10-14, on commits that changed no code:

- `tests/test_gphotos.py::test_sigterm_closes_sources_like_ctrl_c` failed with `assert -15 == 0`
  (run 38617411291, `main` at `9d7afe7`, which pins ai-toolkit only).
- `tests/test_cli.py::test_ui_prints_addresses_and_exits_cleanly_on_sigint` failed with
  `subprocess.TimeoutExpired ... timed out after 15 seconds` (run 38618655818, attempt 1, PR #52,
  which changes one line of `change.md`). The rerun passed.

What makes them fail, and is the cause in the tests or in the app?

## Summary

There are three separate faults. Each one is in the app, and each one can also hit a user.

| | Where | What happens | Evidence |
| --- | --- | --- | --- |
| **A** | SIGTERM before `run_forever()` | The SIGTERM handler is installed only inside `run_forever()`. A `kill` that arrives after `App.start` but before that takes the default action, so the process dies with -15 and nothing is closed | Code reading; it matches CI's `-15` exactly |
| **B** | SIGINT during `App.start` | `KeyboardInterrupt` escapes `App.start`. `cli.ui()` catches it only around `run_forever()`, so the process exits -2 with a traceback, without `interrupted()` or `close()` | **Reproduced**: 17 of 25 runs under CPU load |
| **C** | SIGINT during `Event.wait()` in the main thread | Rarely, the `KeyboardInterrupt` leaves the `Event`'s internal lock held. `close()` then calls `self._closed.set()`, which waits on that lock forever, after "Stopped." is already printed. This is CI's hang | **Mechanism reproduced** in plain Python (2 of 400 runs); CI's output (`Stopped.` then no exit) fits only this among the paths read |

The tests are not wrong about what they expect. Each sends its signal at a moment the app does not
handle: A and B at startup, C at any moment while the main thread waits. A fix belongs in
`castlib/app.py` and `castlib/cli.py`. The tests can additionally dump thread stacks on a timeout,
so the next unknown hang shows where it waits.

## Detailed Findings

### A: SIGTERM between "ready" and `run_forever()`

- The test's child prints `ready` (`tests/test_gphotos.py:1245`) and only then calls
  `app.run_forever()` (`:1246`). The test sends SIGTERM as soon as it reads `ready`
  (`:1254`) and expects exit 0 (`:1256`).
- `run_forever()` installs the handler `_term`, which raises `KeyboardInterrupt`
  (`castlib/app.py:260-273`, the `signal.signal` call is at `:272`). Before that call, SIGTERM has
  its default disposition: the kernel ends the process, so `wait()` returns -15.
- `cli.ui()` has the same gap. `App.start` returns at `castlib/cli.py:266` and `run_forever()` runs at
  `:279`. A `kill` in between ends cast-tv without `close()`, so a Google picker session stays open
  and the TV keeps playing. That was the reason the handler was added in `4441a43`
  (`context/archive/2026-09-07-cloud-source-ui/research.md:864-866`).
- `cli.ui()`'s fallback `except KeyboardInterrupt` (`castlib/cli.py:280`) covers SIGINT in that gap,
  because SIGINT's default handler raises `KeyboardInterrupt`. It does not cover SIGTERM.

### B: SIGINT while `App.start` is still running

- The test reads lines until one contains `does not expose AVTransport` or `TV:`
  (`tests/test_cli.py:180`), then sends SIGINT (`:182`). Both lines are printed **inside**
  `App.start`: `castlib/app.py:206` and `:208`. After the second one, `App.start` still runs
  `app.errors.push(e)` (`:209`), the browser step, and `return app`.
- `cli.ui()` calls `App.start` in a `try` that catches only `AlreadyRunning` and `OSError`
  (`castlib/cli.py:265-277`). A `KeyboardInterrupt` raised inside `App.start` therefore leaves
  `main` as an uncaught exception. Python prints a traceback and exits -2. `interrupted()` and
  `close()` never run, so `app` is not even bound.
- **Reproduced 2026-10-14** with the probe in [race-probes.md](race-probes.md) (§1), using the
  project's venv (Python 3.14.8) and `2 x nproc` busy loops for load. The probe sent SIGINT 0 s
  after the `does not expose` line: 17 of 25 runs exited `-2` with `KeyboardInterrupt`, and in 16
  of them the traceback ended at `castlib/app.py:62` in `ErrorLog.push`, called from
  `app.py:209`. With 0.2 ms or more of delay, and on an idle machine, all runs exited 0 with
  "Stopped.". So only a slow machine hits it, as CI's runners are.
- This is the failure `81097b8` (2026-09-14) set out to fix, for the moment inside
  `signal.signal`. That fix covered `run_forever()` and the gap after `App.start`, but not
  `App.start` itself.

### C: the hang after "Stopped."

- In run 38618655818, the `TimeoutExpired` carried the child's remaining output:
  `stdout_seq = [b'\n   Stopped.\n']`. `interrupted()` had therefore completed
  (`castlib/app.py:283-287`). The process then failed to exit within 15 s.
- After `interrupted()` both paths call `close()`: `run_forever()`'s `finally`
  (`castlib/app.py:277-280`) and `cli.ui()`'s fallback (`castlib/cli.py:280-283`). The first thing
  `close()` does that can block is `self._closed.set()` (`castlib/app.py:292`). Every thread cast-tv
  starts is a daemon (`app.py:201, 233`, `platform.py:91, 225`, `supervisor.py:198, 436`, each
  source's threads), and the source `close()` methods do nothing without a stored credential or
  open flow. So no other wait on these paths explains a hang longer than 15 s.
- `run_forever()` waits with `while not self._closed.wait(1.0)` (`castlib/app.py:275`) in the
  main thread, and that is where the `KeyboardInterrupt` is raised.
  `Event.wait` is `with self._cond: ... self._cond.wait(timeout)`, and `Condition.wait`
  re-acquires the lock in a `finally` (`_acquire_restore`). A `KeyboardInterrupt` raised while the
  lock is being taken or released can leave it held, or try to release it twice. The `Event`'s
  `set()` takes the same lock (`with self._cond`), so it then waits forever.
- **Mechanism reproduced 2026-10-14** in plain Python 3.14.8, with the probe in
  [race-probes.md](race-probes.md) (§2): a main thread looping `ev.wait(t)`, one SIGINT at a random
  moment, then a 2 s attempt to take `ev._cond._lock`.
  - With `t = 0.00001`, 400 runs: 2 `LOCK-HELD`, 1 `RuntimeError: release unlocked lock` (the
    traceback shows the `KeyboardInterrupt` landed inside `_acquire_restore`, `threading.py:378`),
    394 ok. The other 3 runs were interrupted while still importing.
  - With `t = 1.0`, as in `run_forever()`, 200 runs: all ok. The window is tiny when most of the time
    is spent blocked in the C-level acquire, which is why CI hits it only rarely.
- CI runs Python 3.12 (`.github/workflows/test.yml:19`). The bodies of `Condition.wait`,
  `Condition.__enter__/__exit__/_acquire_restore` and `Event.wait/set` are identical in CPython's
  `3.12` branch and in the local 3.14.8. Checked 2026-10-14 by AST-diffing
  `raw.githubusercontent.com/python/cpython/3.12/Lib/threading.py` against
  `/usr/lib64/python3.14/threading.py`.
- The CLI has the same pattern in two more places: `cast` waits `c.done.wait(0.5)`
  (`castlib/cli.py:163`) and a show waits `sh.done.wait(0.5)` (`:237`). Both catch
  `KeyboardInterrupt`, then call `app.stop()`, and later `close()` in their `finally` (`:141`, `:260`), which can
  set those Events. Neither has failed in CI, because no test signals them.

### How often (all 146 CI runs since 2026-09-14)

- SIGTERM test: failed once, 2026-10-14 (A).
- SIGINT test: failed twice. On 2026-09-14 (run 34866064345) it was B's sibling inside
  `signal.signal`, fixed by `81097b8`. On 2026-10-14 (run 38618655818, attempt 1) it was C.
- Every other CI failure was a real bug, fixed on the next commit. No other test is flaky.

## Code References

- `castlib/app.py:158-230`: `App.start`. The `TV:` and `does not expose` lines are printed at `:206` and `:208`, and `app.errors.push(e)` is at `:209`.
- `castlib/app.py:238-239, 246-247`: `_evict_loop`, `_tv_watch`. These wait on `self._closed` in daemon threads, where no signal is delivered.
- `castlib/app.py:260-281`: `run_forever`. The SIGTERM handler is installed at `:272` and the main-thread wait is at `:275`.
- `castlib/app.py:283-287`: `interrupted` prints "Stopped.".
- `castlib/app.py:289-318`: `close`. `self._closed.set()` is at `:292`.
- `castlib/cli.py:263-284`: `ui`. `App.start` is called at `:266`, outside the `KeyboardInterrupt` handler, and the fallback is at `:280`.
- `castlib/cli.py:162-174, 235-251`: the `cast` and show loops wait on an Event in the main thread.
- `tests/test_gphotos.py:1230-1257`: the SIGTERM test. It prints `ready` before `run_forever()`.
- `tests/test_cli.py:164-193`: the SIGINT test. Its trigger lines are printed inside `App.start`.

## Architecture Insights

- cast-tv handles a signal by turning it into `KeyboardInterrupt` in the main thread. Python raises
  that exception at any bytecode boundary, including inside `threading` internals and inside
  `App.start`. Every `try/except KeyboardInterrupt` therefore protects only the code inside it, and
  the lock inside an `Event` is not safe against it.
- The safe shapes are: the main thread sleeps in something that holds no lock (for example
  `time.sleep` with an `is_set()` check, or `signal.sigwait`/`signal.pause` on POSIX); or the
  handler only records the signal and the main loop acts on it. This is a design note for
  `/rune-plan`, not a decision.

## Historical Context (from prior changes)

- `4441a43` (2026-09-13, cloud-source-ui p6): "SIGTERM runs the Ctrl+C path", found live at rows 6.3-6.5, because a plain `kill` left a Google picker session (`context/archive/2026-09-07-cloud-source-ui/plan.md:1400`, `research.md:864-866`).
- `81097b8` (2026-09-14, p7): "Ctrl+C at startup stops the TV like any other, found by CI". It moved the handler install inside the `try` and added `cli.ui()`'s fallback, because run 34866064345 caught a SIGINT inside `signal.signal` (`context/archive/2026-09-07-cloud-source-ui/plan.md:1468-1473`, `research.md:1073`). Its subprocess test "passed 20 of 20 runs locally", which an idle machine cannot disprove (see B).
- `7a7c885` (2026-09-14): both subprocess tests are skipped on Windows (`plan.md:1454-1458`).
- `context/archive/2026-09-07-cloud-source-ui/reviews/impl-review-phase-3.md:152`: `cli.py:146` `c.sent.wait()` sits outside the `KeyboardInterrupt` handler, so a Ctrl+C there exits 130 without "Stopped.". It is a known, separate gap.

## Related Research

- [race-probes.md](race-probes.md): the two probe scripts and how to run them. Use them to show A, B and C before the fix and their absence after it.
- `context/archive/2026-09-07-cloud-source-ui/research.md`: the original SIGTERM and Ctrl+C findings.

## Open Questions

- C is shown by the mechanism and by CI's output, not by a hang of cast-tv itself on this machine:
  more than 200 runs of the real app did not hang. Settle this in the plan: either accept the
  mechanism, or make the SIGINT test dump thread stacks on a timeout (`PYTHONFAULTHANDLER=1`, then
  SIGABRT), so a recurrence in CI names the frame it waits in.
- Are the two other main-thread waits (`castlib/cli.py:163, 237`) in scope? They share C's
  mechanism but no test or user report has shown it. This is the owner's call when planning.
- `castlib/cli.py:146` (`c.sent.wait()` without a handler) is a known gap from the phase-3 review.
  It is out of this change unless the owner adds it.
