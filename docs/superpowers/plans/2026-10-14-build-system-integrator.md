# build-system-integrator Implementation Plan

**Goal:** Ship four JSON I/O tools that detect a local build system, list targets, run an allowlisted target, and parse compiler-style errors.

**Spec:** `docs/superpowers/specs/2026-10-14-build-system-integrator-design.md`

## File map

| Path | Role |
|------|------|
| `tools/build-system-integrator/build_system_integrator.py` | Dispatch + logic |
| `plugins/build-system-integrator/plugin.json` | Tool entries |
| `plugins/build-system-integrator/harness.json` | L1–L5 knobs + gate |
| `testing/fixtures/build-mini/` | Makefile fixture |
| `testing/eval/tasks/fix-with-tests/` | L5 tasks |

## Tasks

- [x] Scaffold + fixture
- [x] Implement tools
- [ ] L1–L4 green
- [ ] L5 tasks + gate; `pending` if no model
- [ ] Catalog + registry + PR
