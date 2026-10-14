# Version control: jj only

Status: required for every agent working in this repo.

## 1. Rule

Use **jj** (Jujutsu) for every write: describe, new, bookmark, push, abandon, restore. Do not run git write commands. The repo is colocated (`.jj` and `.git` both present), so `.git` exists for tools that need it, but jj is the authority.

Forbidden git writes: `add`, `commit`, `checkout`, `switch`, `branch`, `merge`, `rebase`, `push`, `pull`, `stash`, `reset`, `restore`, `worktree`, `cherry-pick`, `tag`.

Allowed git reads: `log`, `show`, `diff`, `status`, `blame`, `rev-parse`.

## 2. Commands

| Task | Command |
|---|---|
| Check state | `jj status` |
| See the change | `jj diff --summary` |
| Start an isolated change on trunk | `jj new trunk()` |
| Name the change | `jj describe -m "<subject>" -m "<body>" -m "<trailers>"` |
| Create or move a bookmark to the change | `jj bookmark set plugin/<name> -r @` |
| Push a bookmark | `jj git push --bookmark plugin/<name>` (add `--allow-new` only on the first push, when jj says the bookmark is new) |
| Undo a file's changes | `jj restore <path>` |
| Start a follow-up change | `jj new` |

If the trunk revset does not resolve, check `jj bookmark list` and use `main@origin` instead.

## 3. Shape of work

- One change per plugin: `feat(<name>): <summary>`. Sub-steps may be separate changes if that keeps each reviewable.
- Each plugin gets its own bookmark: `plugin/<name>`.
- Do not squash, abandon, or rewrite changes that have been pushed. Fix forward with `jj new`.
- Do not sweep unrelated working-copy changes into a plugin change. Run `jj diff --summary` first. If it shows files outside the plugin, stop and report.

## 4. Never commit generated output

Before describing a change, confirm `jj diff --summary` contains none of:

- `__pycache__/`, `.pytest_cache/`, `.venv/`
- `testing/eval/runs/`
- generated fixtures (for example `generated-50k/`)
- cache files under `~/.cache` (these are outside the repo anyway)

## 5. Commit message

```
feat(<name>): <one-line summary>

<what it does, perf numbers, test counts, L5 result>

Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NGuAhdyW7FCdG1ahcWwqd
```

Each `-m` becomes a paragraph in jj.

## 6. Pull requests

Open one PR per plugin bookmark, with `gh` (not git):

```
gh pr create --head plugin/<name> --base main --title "feat(<name>): <summary>" --body "<summary, test results, L5 result>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

The PR body lists the arms, model, seeds, task count, and gate result for L5, or says `pending` when no model was run.

## 7. Stop conditions

Stop and report rather than work around these:

- `jj` is not installed, or the repo is not jj-managed.
- `gh auth status` fails.
- `jj diff --summary` shows changes outside the plugin you are working on.
- A push is rejected. Do not force-push.
