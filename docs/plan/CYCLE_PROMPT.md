# Cursor build cycle: naitv-mcp plugins

Paste everything under the line into Cursor (auto mode), with the naitv-mcp-plugins repo open at its root. To build one plugin, add `PLUGIN=<name>` on the first line. Without it, the cycle works through the catalog in order.

---

You are building naitv-mcp plugins one at a time in the naitv-mcp-plugins repo. Follow these steps in order. Do not skip steps.

## 0. Read first, in this order

1. `docs/plan/README.md`
2. `docs/plan/VCS.md`. You use **jj**, not git. Never run git write commands.
3. `docs/plan/ARCHITECTURE.md`
4. `docs/plan/TESTING.md`
5. `testing/PLUGIN_HARNESS.md`
6. `docs/plan/plugins.json`

## 1. Preflight. Stop and report if any check fails

- `jj --version` succeeds.
- `jj status` succeeds in the repo root, and `jj log -r 'trunk()' -n 3` resolves.
- `gh auth status` succeeds.
- `python3 scripts/catalog_check.py` exits 0.
- `jj diff --summary` is empty, or lists only files you expect. If it lists unrelated files, stop. Do not fold them into a plugin change.
- Read `l5.model` from `testing/PLUGIN_HARNESS.md`'s harness config. If no model is pinned, L5 will be `pending` for every plugin in this run. That is allowed. Do not substitute the stub agent for evidence.

## 2. Pick the plugin

- If `PLUGIN` is set: `planned` builds (steps 3 to 11); `needs-spec` runs spec mode (2b); anything else stops the cycle.
- Otherwise, take the first entry in `docs/plan/plugins.json` by `order` where `status` is `planned` and every name in `depends_on` has `status` `exists`.
- If there is no buildable `planned` entry, run spec mode (2b) on the first `needs-spec` entry, in `order`, whose `depends_on` are all `exists` or `planned`. Skip entries whose `spec_status` is already `draft` (their spec PR is waiting for a person). The spec step is for entries with no `spec_status` yet, so a run never reopens a draft.
- Never invent tool names. The matrix gives tool counts only.

## 2b. Spec mode (for `needs-spec` entries)

Turning an entry into a buildable plugin is a design decision, so spec mode writes or completes the spec and stops for review. It does not implement anything.

1. `jj new trunk()`.
2. If the entry has no `spec_status` yet, write one at `spec_path` from the same template, using `draft_tools` as the starting tool list. The spec names exactly `tool_count` tools, or explains why the count changes. For each tool it gives the input JSON, the output JSON, and the timeout. It also says which fixture tests apply.
3. Do not set `tools` yourself. A person approves the draft. Approval is done by setting `spec_status` to `approved`, `tools` to the approved list, and `status` to `planned`. Only a human makes that change. If the entry is still `draft`, stop here.
4. `python3 scripts/catalog_check.py`.
5. `jj describe -m "docs(<name>): spec" -m "<draft tools and open questions>"`, then bookmark, push, and open a PR titled `spec(<name>): <summary>`, following the PR format in step 10.
6. Stop after one spec PR per run. A person reviews and approves the spec before the plugin is built.

## 3. Start an isolated change

```
jj new trunk()
```

Every edit for this plugin goes in this change. Do not touch other plugins. Shared harness changes must be additive and listed in the PR body.

## 4. Spec and plan

Use today's date from `date +%F`.

- `docs/superpowers/specs/<date>-<name>-design.md`: purpose, each tool's input and output JSON, performance target, failure modes, out of scope.
- `docs/superpowers/plans/<date>-<name>.md`: ordered tasks with file paths.

Use `docs/superpowers/specs/2026-09-12-structural-anchor-design.md` as the format reference.

## 5. Scaffold

If `plugins/<name>/` does not exist:

```
./scripts/scaffold_plugin.sh <name> <profile>
```

Use the `profile` from the catalog entry.

## 6. Implement

- Tools go under `tools/<name>/`. Each tool entry in `plugins/<name>/plugin.json` has `exec` in the form `TOOL_NAME=<tool> python3 ~/.config/naitv-mcp/tools/<name>/<file>`, `io_mode: "json"`, a `timeout`, and `params`.
- Follow the rules in `ARCHITECTURE.md` section 3: stdlib first, one JSON line out, diagnostics to stderr, deterministic, bounded, cache only under `~/.cache/naitv-mcp/<name>/`, no network.

## 7. Tests

Create every item in `TESTING.md` section 2 that applies to this profile. Then run:

```
make test-plugin PLUGIN=<name>
make l4 PLUGIN=<name>
```

Fix until green. You get three fix attempts per failing layer. If a layer still fails after that, set the entry's `status` to `blocked`, write the failing output into `notes`, run `python3 scripts/catalog_check.py`, go to step 10, and stop the cycle. Do not continue to the next plugin with a blocked dependency.

## 8. L5 proof

Follow `TESTING.md` section 3.

- Write at least 10 dev tasks with `plugins_expected: ["<name>"]` under `testing/eval/tasks/<category>/`, plus at least 2 control tasks. Use the `eval_category` from the catalog. If it is `null`, set `l5` to `not-applicable` and skip this step.
- Do not create, read, or run held-out tasks. Never set `HELD_OUT=1`.
- Write the gate into `harness.json` → `l5.gate` **before** the first eval run, using the values in `TESTING.md` section 3.3.
- Run baseline and treatment with the pinned model:

  ```
  make eval-baseline AGENT=ollama SUITE=<category> SEEDS=3
  make eval-treatment AGENT=ollama SUITE=<category> SEEDS=3
  ```

- Commit the summary to `testing/eval/baselines/<name>-<category>-v1.json`.
- Do not edit the gate after you see results. Record a failed gate as it is.
- If no model is available, set `l5` to `pending` and say so in the report.

## 9. Update the catalog

Set the entry's `status` to `exists` once L1 to L4 pass. Set `l5` to the outcome from `TESTING.md` section 3.4. Run `python3 scripts/catalog_check.py`.

## 10. Describe, bookmark, push, open a PR

```
jj diff --summary
```

Confirm no caches, `__pycache__`, `.venv`, `testing/eval/runs/`, or generated fixtures are included. Then:

```
jj describe -m "feat(<name>): <summary>" -m "<what it does, perf, test counts, L5 result>" -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_012NGuAhdyW7FCdG1ahcWwqd"
jj bookmark set plugin/<name> -r @
jj git push --bookmark plugin/<name>
```

Add `--allow-new` to the push only if jj says the bookmark is new. Do not force-push.

```
gh pr create --head plugin/<name> --base main --title "feat(<name>): <summary>" --body "<summary, test results, L5 arms, model, seeds, task count, gate result>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Record the PR URL.

## 11. Next plugin

Unless `PLUGIN` was set, return to step 2. Stop the cycle after any plugin that ends `blocked`.

## Hard rules

- VCS writes go through jj only.
- Never rewrite a pushed change. No `jj abandon` or `jj squash` on pushed work.
- Never change an eval gate after seeing results.
- Never report a plugin as helpful without a gated `measured-helpful` result.
- Never treat stub-agent output as evidence.
- Never invent tool names for `needs-spec` entries.

## Final report

Plain text, under 300 words. One line per plugin attempted: name, final status, L1 to L4 pass or fail, L5 outcome, bookmark, PR URL. Then list the `needs-spec` entries skipped, and any `blocked` entries with the reason.
