# How agent-portable plugins work

This doc explains the architecture behind agent-portable behavior packs like
[ponytail](https://github.com/DietrichGebert/ponytail), and how the same pattern
applies to naitv-mcp plugins. The `lazy-dev` plugin in this repo is a working
example.

## The core problem

Every agent host (Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Copilot, ...)
has its own mechanism for injecting behavior, and they don't agree on anything:
file locations, formats, or even the capability model. If you write your behavior
once per host, you have N copies that drift apart. The ponytail pattern solves
this with three ideas.

## Idea 1: Single source of truth

The behavior lives in exactly one canonical place. Everything else is derived
from it or kept aligned with it.

In ponytail, the canonical content is `skills/*/SKILL.md` (the full behavior) and
`AGENTS.md` (a compact distillation). A CI script (`check-rule-copies.js`) fails
the build if any host-specific copy drifts from the canonical text.

In this repo, the canonical content is the plugin JSON (`plugins/lazy-dev.json`).
The `adapters/lazy-dev/AGENTS.md` file is a distillation of its `init` rules; if
you change one, change both. (At two copies, a manual rule is fine. If adapters
multiply, write the drift-check script — but not before. YAGNI.)

## Idea 2: Thin adapters

An adapter is the smallest possible file that makes a given host load the
canonical behavior. Adapters contain no behavior of their own — they point,
wrap, or copy.

Three adapter shapes exist, matching how much the host can do:

| Shape | What it is | Example hosts |
|-------|-----------|---------------|
| **Manifest** | A small JSON/YAML file that points the host at shared `skills/`, `commands/`, `hooks/` directories | Claude Code (`.claude-plugin/plugin.json`), Codex, Gemini CLI (`gemini-extension.json`) |
| **Rule copy** | A verbatim copy of the compact ruleset in the host's expected path | Cursor (`.cursor/rules/*.mdc`), Windsurf, Cline, Copilot (`.github/copilot-instructions.md`), Kiro |
| **Code shim** | A tiny script that injects the ruleset programmatically each turn | OpenCode (`.opencode/plugins/*.mjs`) |

The discipline: when a host supports skills or hooks, point at the shared files;
never fork the content into the adapter. When a host only reads static rule
files, copy the compact text and keep it aligned.

## Idea 3: Host capability tiers

Not every host can run every feature, so the behavior degrades gracefully across
three tiers:

1. **Always-on rules** (every host) — the compact ruleset injected into every
   session. This is the floor: even a host that only reads a markdown file gets
   the core behavior.
2. **Skills / commands** (skill-capable hosts) — on-demand behaviors invoked
   explicitly (`/ponytail-review`, or naitv-mcp's on-demand entries fetched via
   `get_entry`). These would bloat the always-on context, so they load lazily.
3. **Hooks / state** (lifecycle-capable hosts) — session-start activation,
   persistent mode flags (`lite/full/ultra`), statuslines. Pure quality-of-life;
   the behavior works without them.

Design the content so tier 1 alone is useful. Tiers 2 and 3 add convenience,
never correctness.

## How naitv-mcp fits this model

naitv-mcp inverts one part of the problem nicely: instead of shipping an adapter
per host, it is *itself* the adapter. Any agent that can speak MCP gets the same
entries, regardless of host. The plugin format's `delivery` field maps directly
onto the capability tiers:

- `delivery: init` ≈ tier 1 — bundled into every session at initialize.
- `delivery: on-demand` ≈ tier 2 — the agent fetches it when needed
  (`get_entry` / `search_entries`), like invoking a skill.
- Executable `tool` entries ≈ tier 3 — host-independent "hooks" run through
  `run_tool`.

So a naitv-mcp plugin is portable to any MCP-capable agent for free. The
remaining gap is agents *without* MCP (or sessions where the server isn't
connected) — that's what the `adapters/` directory covers: a copy-in `AGENTS.md`
per plugin, the universal fallback that nearly every modern agent reads.

```
plugins/lazy-dev.json          ← source of truth (any MCP agent, via naitv-mcp)
adapters/lazy-dev/AGENTS.md    ← universal fallback (any agent that reads AGENTS.md)
```

## Anatomy of the lazy-dev plugin

The content itself follows ponytail's structure, which is worth copying for any
behavior pack:

1. **A persona + decision procedure** (`lazy-ladder`) — not vague vibes
   ("write simple code") but an ordered ladder the agent walks and stops at the
   first rung that holds. Procedures beat adjectives.
2. **Concrete prohibitions** (`minimalism-rules`) — each rule names a specific
   anti-pattern (interface with one implementation, config for a constant).
   Specific rules are checkable; "avoid over-engineering" is not.
3. **A safety floor** (`safety-floor`) — an explicit never-cut list. This is what
   separates a useful minimalism pack from a dangerous one; ponytail's benchmark
   showed a bare "write one-liners" prompt drops a safety guard, while the
   full ruleset doesn't.
4. **An output contract** (`output-style`) — minimalism applies to prose too,
   with a fixed pattern: `[code] → skipped: [X] — add when [Y]`.
5. **On-demand workflows** (`overengineering-review`, `overengineering-audit`,
   `debt-harvest`) — the tier-2 behaviors: apply the same ruleset
   retrospectively to a diff, a repo, or the trail of `lazy:` comments.

One more ponytail trick embedded in the rules: **marker comments as a debt
ledger**. Every deliberate simplification gets a `lazy:` comment naming its
ceiling and upgrade path. That makes simplicity legible as intent, and gives
the `debt-harvest` workflow something mechanical to grep for later.

## Porting checklist for a new plugin

1. Write the behavior as naitv-mcp entries. `init` rules small and always-true;
   everything situational goes `on-demand`.
2. Distill the `init` rules into `adapters/<plugin>/AGENTS.md` (target: fits in
   one screen).
3. Note in both files which one is canonical.
4. Register in `registry.json`, add to the README table.
5. Only add per-host adapter files (`.cursor/rules/`, `.claude-plugin/`, ...)
   when someone actually needs that host. Rung 1: does it need to exist?
