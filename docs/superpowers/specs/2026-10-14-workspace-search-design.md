# workspace-search — Design Spec

**Date:** 2026-10-14  
**Phase:** 4  
**Status:** Approved first-draft (implementing)

## Purpose

Local workspace search without network: regex text search, lightweight token-overlap “semantic” ranking, and candidate re-ranking.

## Tools

| Tool | Timeout | Input | Output |
|------|---------|-------|--------|
| `semantic_search` | 2s | `root_path`, `query`, optional `limit`/`depth` | `results[]` (`path`,`score`), `count`, `truncated` |
| `text_search` | 2s | `root_path`, `pattern`, optional `glob`/`depth` | `matches[]` (`path`,`line`,`text`), `count`, `truncated` |
| `rank_results` | 2s | `query`, `candidates[]` | `ranked[]` (`path`,`score`,`index`), `count` |

Stdlib only. Cap walks at 2000 files; match list at 200. No embeddings / no network.

## Performance

Matrix target `< 500ms` typical on small trees; tool timeout 2s.

## L5

Category `navigation`. Gate pre-registered. No model pinned → `pending`.

## Out of scope

True vector/embedding search, editing files, held-out suite.
