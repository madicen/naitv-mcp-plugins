# naitv-plugins

Plugin registry for [naitv-mcp](https://github.com/madicen/naitv-mcp) — the local MCP server + TUI for managing AI agent context.

Plugins are JSON manifests that bundle entry definitions (rules, workflows, executable tools) and are installed through the MCP protocol:

```
install_plugin(source="loop-engineering-go")
```

naitv-mcp fetches `registry.json` from this repo to resolve plugin names to URLs.

---

## Available plugins

| Plugin | Description |
|--------|-------------|
| [loop-engineering-go](plugins/loop-engineering-go.json) | Loop Engineering for Go — rules, workflows, and verification tools (build, vet, test, lint) |

---

## Plugin format

Each plugin is a JSON file in `plugins/` with this shape:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "What this plugin does",
  "author": "your-username",
  "tags": ["optional", "tags"],
  "entries": [
    {
      "kind": "rule",
      "name": "my-rule",
      "delivery": "init",
      "body": "Rule text shown to the agent at session start.",
      "tags": ["my-tag"]
    },
    {
      "kind": "tool",
      "name": "my-tool",
      "delivery": "on-demand",
      "body": "Description shown to the agent.",
      "fields": {
        "exec": "some-command --flag {param}",
        "timeout": "60s",
        "params": "[{\"name\":\"param\",\"description\":\"...\",\"required\":true}]"
      }
    }
  ]
}
```

**Field reference:**

| Field | Values | Notes |
|-------|--------|-------|
| `kind` | `rule`, `workflow`, `fact`, `note`, `tool` | Entry type |
| `delivery` | `init`, `on-demand` | `init` = included in initialize bundle; default if omitted |
| `fields.exec` | shell command string | Makes a `tool` entry executable |
| `fields.timeout` | e.g. `"60s"` | Execution timeout |
| `fields.params` | JSON string (array of `{name, description, required}`) | Interpolated as `{name}` in exec |
| `fields.disabled` | `"true"` / `"false"` | Disables the tool without removing it |
| `fields.working_dir` | absolute path | Set via `set_project` after install |

---

## Adding a plugin to the registry

1. Add your plugin JSON to `plugins/your-plugin-name.json`
2. Add an entry to `registry.json` pointing at the raw GitHub URL
3. Open a PR

---

## Installing plugins

With [naitv-mcp](https://github.com/madicen/naitv-mcp) running, ask your agent:

```
# By name (looks up registry.json automatically)
install_plugin(source="loop-engineering-go")

# By direct URL
install_plugin(source="https://raw.githubusercontent.com/madicen/naitv-plugins/main/plugins/loop-engineering-go.json")

# From a local file (useful during development)
install_plugin(source="./path/to/my-plugin.json")
```

All entries are proposed as **pending** — review and approve them in the naitv-mcp TUI before they go live.
