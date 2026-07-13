# naitv-mcp-plugins

The official plugin registry for [naitv-mcp](https://github.com/madicen/naitv-mcp).

Plugins are bundles of entries (rules, workflows, tools, facts) that agents can install into naitv-mcp in one shot. This repo is the canonical home for all plugins — nothing lives in the main naitv-mcp repo.

## Installing a plugin

Use the `install_plugin` MCP tool from naitv-mcp, passing either the plugin name (resolved against this registry) or a direct path/URL to the JSON file:

```
# By name (resolves via registry.json)
install_plugin(name="loop-engineering-go")

# By URL
install_plugin(source="https://raw.githubusercontent.com/madicen/naitv-mcp-plugins/main/plugins/loop-engineering-go.json")

# By local path (useful during development)
install_plugin(source="/path/to/my-plugin.json")
```

All entries in a plugin are installed as `pending` proposals — you review and approve them in the **Review** tab of the TUI before they go live.

## Available plugins

| Plugin | Description | Version |
|--------|-------------|---------|
| [`loop-engineering-go`](plugins/loop-engineering-go.json) | Loop-engineering rules, workflows, and Go verification tools (build, vet, test, lint) for use with Continue/Cursor | 1.1.0 |
| [`lazy-dev`](plugins/lazy-dev.json) | Lazy senior dev mode (à la [ponytail](https://github.com/DietrichGebert/ponytail)) — YAGNI ladder, stdlib first, review/audit workflows. Universal [AGENTS.md adapter](adapters/lazy-dev/AGENTS.md) for non-MCP agents | 1.0.0 |

## Using a plugin without naitv-mcp (any agent)

Any MCP-capable agent gets plugins through naitv-mcp automatically. For agents without MCP, some plugins ship a universal adapter in [`adapters/`](adapters/) — a compact `AGENTS.md` you copy into your project root (or your agent's global instructions). Nearly every modern agent (Codex, Gemini CLI, OpenCode, Copilot CLI, and others) reads `AGENTS.md`; for hosts with their own convention (Cursor, Windsurf, Cline), copy the same text into their rules file.

The plugin JSON is always the source of truth; adapters are distillations kept aligned with it. See [docs/how-agent-portable-plugins-work.md](docs/how-agent-portable-plugins-work.md) for the architecture behind this pattern.

## Plugin format

A plugin is a single JSON file with the following shape:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "What this plugin does.",
  "author": "your-github-handle",
  "tags": ["tag1", "tag2"],
  "entries": [
    {
      "kind": "rule",
      "name": "my-rule",
      "delivery": "init",
      "tags": ["my-plugin"],
      "body": "The rule text the agent will see.",
      "group": "my-plugin"
    }
  ]
}
```

### Entry fields

| Field | Required | Description |
|-------|----------|-------------|
| `kind` | ✓ | Free-form label: `rule`, `workflow`, `tool`, `fact`, `note`, `project`, etc. |
| `name` | ✓ | Unique (within the plugin) human-readable identifier. |
| `body` | ✓ | The content the agent reads. Plain text or markdown. |
| `delivery` | | `init` — included in the initialization bundle every session. `on-demand` — agent fetches it explicitly. Defaults to `init`. |
| `tags` | | Array of strings for filtering and search. |
| `group` | | Display group in the TUI Entries tab. Defaults to the plugin name. |
| `fields` | | Key/value map for structured metadata (e.g. `exec`, `working_dir`, `timeout` for executable tools). |

### Executable tools

Entries with `kind: tool` and an `exec` field in `fields` are runnable directly by the agent via the `run_tool` MCP call. Supported `fields` keys:

| Field | Description |
|-------|-------------|
| `exec` | Shell command to run. Supports `{placeholder}` interpolation from call-time args. |
| `working_dir` | Directory to run in. Supports `{placeholder}` interpolation (e.g. `{project_root}`). |
| `timeout` | Hard timeout, e.g. `60s`, `2m`. |
| `disabled` | Set to `"true"` to prevent execution without deleting the entry. |
| `params` | JSON array of `{name, description, required}` objects describing accepted arguments. |

## Adding a plugin

1. Create `plugins/<your-plugin-name>.json` following the format above.
2. Add an entry to `registry.json`:

```json
{
  "name": "your-plugin-name",
  "description": "One-line description.",
  "url": "https://raw.githubusercontent.com/madicen/naitv-mcp-plugins/main/plugins/your-plugin-name.json",
  "tags": ["relevant", "tags"],
  "version": "1.0.0",
  "author": "your-github-handle"
}
```

3. Open a PR. The registry is intentionally minimal — no CI gate, no schema validator yet.

## Updating a plugin

Bump `version` in both the plugin JSON file and the corresponding entry in `registry.json`. naitv-mcp uses the version field to detect when a locally installed plugin is out of date.
