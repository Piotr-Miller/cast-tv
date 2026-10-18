# AGENTS.md

## Hard rules

- **This repository is public.** Never commit what `ai-toolkit setup` installs (`.claude/skills/`,
  `.agents/skills/`, `.claude/prompts/`, `.claude/config-templates/`): it is course-licensed material
  and is gitignored on purpose; never `git add -f` it.
- **Secrets never enter the repository.** Provider secrets live in GitHub Actions secrets and are
  written into the release by `packaging/write_client.py`; the source tree keeps a stub. Never read
  or print a secret value or a stored token (`~/.config/cast-tv`, `%APPDATA%\cast-tv`).
- **Nothing the app needs is a file the user copies.** Credentials and settings ship with the app;
  files and environment variables may only override them. An error message never says "copy this file".
- **A manual step for the owner names the window, the control and what they should then see**
  ("in the PowerShell window running cast-tv, press Ctrl+C; it prints `Stopped.`").
- **Never merge a pull request.** The owner merges with "Rebase and merge", which gives every commit
  a new SHA: SHAs recorded in a plan are written again from `main` after the merge.

## Before starting

- Before starting, read `context/foundation/lessons.md` (rules learned from earlier mistakes), then
  `git fetch`, `git branch -r`, `gh pr list` and the `plan.md` of every folder in `context/changes/`.
  Branch new work from an up-to-date `main`, never from the branch of an open PR.

## Agent workflow

- **Single source of truth:** project instructions live in `AGENTS.md`;
  `CLAUDE.md` only imports `@AGENTS.md`. Edit this file, not the import file.
- **AI dev practices:** before changing skills, `AGENTS.md` / `CLAUDE.md`, hooks, MCP config or agent
  prompts, also read the user-level `ai-dev-practices` skill if it is installed (it may be newer than
  your training). Rules in this file take precedence over it.
- **Use the skill tree for the current agent:** `.agents/skills/` for Codex,
  `.claude/skills/` for Claude Code. Do not copy skills between these trees.

## Definition of done

- `pyflakes` and `pytest` pass locally. CI runs both on `ubuntu-latest` and `windows-latest`, so put
  OS-specific calls behind an injectable and test the logic on both
  (`context/foundation/test-plan.md`, 5.4).
- What only the real TV, a real sign-in or Windows itself can prove is a manual row in the change's
  `plan.md`. Tick it only after its observation is written in `research.md`: row, date, device,
  material and what was seen. A passing test or a commit SHA does not replace it.
- A change in `packaging/` or `.github/workflows/release.yml` also runs the release build and smoke
  test on the pull request; it must pass.

## Git and pull requests

- Commit subjects: `type(<change-id or area>): what changed`, with `feat`, `fix`, `docs`, `test` or
  `chore`, e.g. `fix(signal-shutdown-races): impl-review fixes F1-F3`.
- When work pauses (a reboot, a switch of machine), write the next steps for the owner into
  `temp_steps.md`, in English like the rest of the repository, overwriting the previous ones.

## Commands

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"   # Windows: .venv\Scripts\pip
python -m castlib                                            # run the UI
python -m pyflakes castlib tests                             # the same two checks as CI
python -m pytest
```

- The UI behaviour tests in `tests/test_ui.py` run `app.js` in `node` and are **skipped** without it.
  When you change `castlib/ui/`, make sure `node` is on the path, and run `node --check castlib/ui/app.js`.
- The desktop window needs the `window` extra (`pip install -e ".[window]"`); the test job does not install it.
- A test that hangs dumps every thread's stack after 120 s (`faulthandler_timeout`); read the dump, not the job timeout.

## Layout

- `castlib/`: the package. `cli.py` holds the three entry points (`cast-tv`, `cast-gopro`, `cast-photos`),
  `sources/` the cloud and local sources, `auth/` the sign-in flows, `ui/` the static web UI (plain
  `app.js` with Alpine; no build step).
- `cast-tv`, `cast-gopro`, `cast-photos` at the root: thin shims for the old symlink install; code goes in `castlib/`.
- `packaging/`: the PyInstaller build, the release smoke test and `write_client.py`.
- `context/foundation/`: documents that outlive a change (`prd.md`, `roadmap.md`, `tech-stack.md`,
  `test-plan.md`, `lessons.md`). `context/changes/<change-id>/`: one planned change (frame, research,
  plan, reviews). `context/archive/`: closed changes, a historical record; do not edit them.

See [`README.md`](README.md) for what the app does and how users install it.
