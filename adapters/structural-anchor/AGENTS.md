# Structural Anchor — codebase map before thrashing

<!-- Universal adapter for the structural-anchor plugin. Copy this file into any project
     root (or your agent's global instructions) for agents that read AGENTS.md.
     Keep this text aligned with plugins/structural-anchor.json — the plugin JSON is
     the source of truth. -->

Before broad greps or opening many files to learn a repo, build a structural map first.

1. Call **get_project_map** with `root_path` set to the project root (absolute path).
2. Read the returned packages and symbols to orient — Python and Go are supported.
3. Only then open specific files you actually need.

Alternatives when you need less detail:

- **list_languages** — file and line counts per language, plus a primary-language hint.
- **get_codebase_statistics** — total files, lines, complexity, package count.

All three tools share a cache keyed by git commit fingerprint under `~/.cache/naitv-mcp/structural-anchor/`. Install the tool bundle before first use (see `tools/structural-anchor/README.md` in the plugin repo).
