<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Signal and shutdown races Implementation Plan

- **Plan**: context/changes/signal-shutdown-races/plan.md
- **Scope**: full
- **Session**: fresh
- **Base**: 0d55ede7d71209c1b1b1f1a775ed7eca3cf0f47d (merge-base)
- **Head**: c52188c6b32e7a5443c0c51cdf6fe7d2790f2480
- **Worktree**: excluded (clean)
- **Checks ran at**: c52188c6b32e7a5443c0c51cdf6fe7d2790f2480
- **Manual acceptance**: 3 of 3 confirmed
- **Date**: 2026-10-14
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Ctrl+C before serve() starts hangs close() in server.shutdown()

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: castlib/app.py:216-218 (window), castlib/app.py:271 → castlib/app.py:354 (hang)
- **Detail**: `App.start`'s `except KeyboardInterrupt` calls `app.close()` as soon as `app` is assigned (line 216). `close()` calls `self.server.shutdown()`, which in `socketserver` sets a flag and then waits on an Event that only `serve_forever()` sets. If the interrupt lands after `app = cls(...)` and before `serve()` has started the `http` thread (the `open_browser` line, or `serve()`'s first bytecode), nothing will ever set that Event. `close()` then blocks forever, in the main thread, inside an `Event.wait`, the very pattern Phase 1 removed. Reproduced: with `App.serve` patched to raise `KeyboardInterrupt`, `cli.ui()` printed `Stopped.` and then hung. faulthandler after 5 s: `socketserver.py:255 in shutdown` ← `app.py:354 in close` ← `app.py:271 in start` ← `cli.py:266 in ui` (probe `probe_serve.py`, session scratchpad). The window is narrow, and a second Ctrl+C gets out of it (the second interrupt reaches `cli.ui`'s `except KeyboardInterrupt: return 0`). Still, the plan promises a clean end "at any moment", and a CI child would hang. The plan's State sequencing treats "`app` exists" as "safe to close". The safe point is really "the HTTP loop is running". No test covers the gap: `test_ctrl_c_before_the_app_exists_frees_the_port` patches `__init__`, and `test_ctrl_c_during_start_stops_and_frees_the_port` patches `firewall_blocked`, which comes after `serve()`.
- **Fix A ⭐ Recommended**: In `App.start`, give the cleanup the app only after `serve()` returns (`running = app` after `app.serve()`; the except tests `running`). An interrupt before that point only closes the socket. Add a test that patches `App.serve` to raise `KeyboardInterrupt`: `cli.ui` returns 0 and the port is free.
  - Strength: Two lines, and `close()` keeps its documented precondition (socketserver: "must be called while serve_forever() is running"). It extends the Ledger's existing "before the App exists" branch, which already exits quietly with status 0.
  - Tradeoff: In that window `Stopped.` is not printed, and the App's executor and inhibitor are not closed explicitly. Nothing has been cast and no source has been opened yet, and the process exits right after.
  - Confidence: HIGH — the probe shows the exact frame; the fix avoids calling `shutdown()` without a loop.
  - Blind spot: An interrupt inside `serve()` after `http` started but before `serve()` returns also takes the socket-only path. That is harmless at exit, but it was not probed.
- **Fix B**: Make `close()` itself safe when serving never began: call `self.server.shutdown()` only when the `http` thread was started (for example, `if self._threads:`). Otherwise go straight to `server_close()`.
  - Strength: Fixes it at the source for every caller of `close()`, and `Stopped.` and the full cleanup still happen in that window.
  - Tradeoff: Touches `close()`, which every exit path uses. An interrupt between `t.start()` and `_threads.append(t)` would skip `shutdown()` while the loop runs, which is harmless only because the process is exiting.
  - Confidence: MED — `close()` is also called from the UI and the slideshow paths; those were not re-read for this.
  - Blind spot: Whether any caller relies on `close()` blocking until the HTTP loop has stopped.
- **Decision**: FIXED — Fix A (`running = app` after `serve()`, castlib/app.py:213-273; new `test_ctrl_c_before_the_http_loop_runs_does_not_hang`, which fails at HEAD's app.py after 5 s and passes with the fix); siblings: castlib/cli.py `_cast_item` tracked in F3 (FIXED), castlib/cli.py `show` tracked in F3 (FIXED), `run_forever`'s `self.close()` n/a (runs only after `serve()`), `cli.ui`'s fallback `app.close()` n/a (`App.start` had returned, so serving); reopened: 3.6, 3.7, 3.8

### F2 — The SIGTERM test child still has an uncaught window after `ready`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: tests/test_gphotos.py:1245-1246
- **Detail**: Fault A's fix moves the handler install ahead of `ready`, so the default `-15` is gone. But `_term` raises `KeyboardInterrupt`. A SIGTERM that lands after the child writes `ready` and before `run_forever()` enters its `try` (the rest of the `print`, `sys.exit`/`app.run_forever` lookups, `run_forever`'s RESUME) is raised at module level in the child. Nothing catches it, so the exit is -2 with a traceback instead of 0. This window is the old fault-A window minus the `signal.signal` call, so it is of the same order as the one CI hit in run 38617411291. Production does not have this gap: `cli.ui()` keeps the `except KeyboardInterrupt` fallback around `run_forever()` (`castlib/cli.py:282`), and the test child has no such fallback. Demonstrated by holding the window open: the same child with `time.sleep(0.5)` after `print('ready')` exited -2 with `KeyboardInterrupt` from `_term` (probe `probe_sigterm.py`, session scratchpad). The sleep shows the path, not how often it happens. 3.2 (ten runs in a row) passes, which is consistent with a rare race.
- **Fix**: Give the child the same fallback as `cli.ui()`: `try: rc = app.run_forever()` / `except KeyboardInterrupt: app.interrupted(); app.close(); rc = 0` / `sys.exit(rc)`.
- **Decision**: FIXED — Fix now, with `print('ready')` moved inside the child's `try` too (a signal landing during the `print` call is raised at its return, which was still outside the `try`); the held-open probe now ends `exit 0`, `soap Stop`, `Stopped.`; siblings: tests/test_cli.py `test_ui_prints_addresses_and_exits_cleanly_on_sigint` n/a (its child is `python -m castlib`, i.e. `cli.ui`, whose `App.start` and `run_forever` are each inside a `try` that catches `KeyboardInterrupt`), no other test runs `run_forever` in a child (grep `run_forever` in tests/); reopened: none

### F3 — cast and show close() an app whose serve() may not have started (sibling of F1)

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: castlib/cli.py:130-141 (`_cast_item`), castlib/cli.py:219-260 (`show`)
- **Detail**: Linked from F1. Both build `App(srv)` and then run `try: app.serve() … finally: app.close()`. If `serve()` raises before the `http` thread runs `serve_forever()` (a Ctrl+C at its first bytecode, or `RuntimeError: can't start new thread`), the `finally` reaches `server.shutdown()` and hangs, the same way F1 did. These paths are outside the plan, which changed only their wait loops. Before this change the same hang existed there.
- **Fix**: Move `app.serve()` above the `try` in both functions, so the `finally` owns the app only once its HTTP loop runs. An exception in `serve()` then propagates without `close()`, and the port is freed when the process exits.
- **Decision**: FIXED — Fix now (`app.serve()` above the `try` in castlib/cli.py `_cast_item` and `show`; new `test_cast_and_show_ctrl_c_before_the_http_loop_runs_do_not_hang`, which fails at HEAD's cli.py and passes with the fix); siblings: none further (grep `App(`, `.serve()` and `server.shutdown()` in castlib/: only app.py:218, fixed in F1, and these two); reopened: none (3.6 and 3.7, whose surface includes castlib/cli.py, were already reopened by F1). After all three fixes: full suite 386 passed, 1 skipped; pyflakes clean; 3.2 ten runs in a row pass; 1.2 grep clean

## Review Notes

- **Bookkeeping in diff**: context/changes/signal-shutdown-races/change.md, context/changes/signal-shutdown-races/plan-brief.md, context/changes/signal-shutdown-races/plan.md, context/changes/signal-shutdown-races/race-probes.md, context/changes/signal-shutdown-races/research.md
- Lessons: 1 of 6 entries apply to impl-review ("A ticked manual row needs a written observation"). Rows 3.6-3.8 each have a dated observation in `research.md` §"Manual checks after the fix, 2026-10-14", and all three are `current` at bed2488 per `acceptance-state.sh` (exit 0).
- Plan drift: every planned item (helper `main_wait`, three call sites, `end_on_sigterm`, the `App.start` wrap, `cli.ui` catch, `finish_or_dump`, all 10 named tests) matches the plan; no unplanned code files.
- Automated checks at c52188c, all exit 0: 1.1 (4 passed), 1.2, 2.1 (4 passed), 2.2 (11 passed), 3.1 (1 passed), 3.2 (10/10), full suite (384 passed, 1 skipped), pyflakes clean, 3.5 `gh pr checks 53`: ubuntu-latest and windows-latest pass, and the PR head is c52188c.
- Mutation check skipped: `context/foundation/test-plan.md` §2 has no risk on signal or shutdown handling, and §3 configures no mutation tool.
