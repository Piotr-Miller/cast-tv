# Review fixes — signal-shutdown-races

## From impl-review-c52188c.md, Re-review 2, F4 (2026-10-14)

Owner decision: fix the plan now; change these code comments the next time the files change,
so that a comment-only edit does not reopen the accepted manual rows 3.6-3.8 (their surface is
`castlib/app.py`, `castlib/cli.py`). Each comment should say that before `serve()` returns, only
the socket is closed (owner decision 2026-10-14, impl-review F1/F3).

- [ ] `castlib/app.py:200-202`, `App.start` docstring: "A Ctrl+C (or SIGTERM) after the bind stops and closes the app" → once `serve()` has returned; before that only the socket is closed.
- [ ] `castlib/cli.py:139-140`, `_cast_item` `finally` comment: "free the port, whatever the exit path (… Ctrl+C …)" → whatever the exit path once `serve()` runs; an interrupt in `serve()` propagates without `close()`.
- [ ] `castlib/cli.py:278`, `cli.ui` comment: "start() already stopped and closed it" → or closed only its socket before `serve()` returned.
