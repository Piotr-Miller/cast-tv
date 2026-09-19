# Foundation Docs

Cross-change living documents that span multiple changes. This project keeps:

| Doc | What it holds |
| --- | --- |
| `prd.md` | What cast-tv is for, who uses it, and what "working" means |
| `roadmap.md` | Every slice of work, its change folder and its status |
| `tech-stack.md` | The stack and why it is this one |
| `test-plan.md` | How cast-tv is tested, what CI covers and what only the TV can prove |
| `lessons.md` | Append-only rules learned from reviews and from mistakes in the sessions |

The first four were written on 2026-09-19, after the fact: reconstructed from
`context/changes/cloud-source-ui/`, `context/changes/standalone-install/`, the README and the git
history, not from a planning session held before the work.

## Update convention

**Edit-in-place.** Foundation docs evolve over the lifetime of the project. When something
changes incrementally (a new dependency, a refined goal, a finished slice), edit the existing
file. Don't create dated copies.

## Archive convention

When a foundation doc is fully superseded - replaced by a new approach rather than refined -
move it to `foundation/archive/YYYY-MM-DD-<doc>.md` and write the replacement at the original
path. The archive folder is a historical record; nothing reads from it routinely.

## Anti-pattern

Do **not** put change-scoped docs here. Anything tied to a single change (its plan, its
research, its review) belongs under `context/changes/<change-id>/`. Foundation is for what
outlives any one change.
