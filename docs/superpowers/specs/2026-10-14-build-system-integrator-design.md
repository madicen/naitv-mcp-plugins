# build-system-integrator — Design Spec

**Date:** 2026-10-14  
**Phase:** 3  
**Status:** Approved first-draft (catalog `planned` → implementing)

## Purpose

Help agents detect the local build system, list targets, run one allowlisted target with a short timeout, and parse `file:line: message` errors from logs.

## Tools

| Tool | Timeout | Input | Output |
|------|---------|-------|--------|
| `detect_build_tool` | 5s | `root_path` | `tool`, `config_files[]` |
| `list_build_targets` | 5s | `root_path` | `tool`, `targets[]` |
| `run_build_target` | 10s | `root_path`, `target` | `exit_code`, `output_tail`, `tool`, `target` |
| `parse_build_errors` | 5s | `output` | `errors[]` (`file`,`line`,`message`), `count` |

Supported tools: `make`, `go`, `npm`, `cargo`, `python`, or `unknown`.

`run_build_target` only runs allowlisted commands (e.g. `make <target>`, `go build ./...`). No arbitrary shell. Output tail capped at 8 KiB.

## Performance

Matrix target `< 5s` for detect/list/parse; run uses up to ~4s subprocess timeout inside a 10s tool timeout.

## Failure modes

- Bad `root_path` / missing required fields → stderr + exit 1
- No build tool / unsupported target → exit 0 JSON with `exit_code` 2
- Subprocess timeout → `exit_code` 124

## Fixtures

- New: `build-mini` (Makefile) — justified: shared fixtures are source trees without build files for make
- Reuse: `go-small`, `empty`

## L5

Category `fix-with-tests`. Gate pre-registered in harness. No model pinned → result `pending` until ollama run.

## Out of scope

Network installs, editing files, non-allowlisted commands, held-out suite.
