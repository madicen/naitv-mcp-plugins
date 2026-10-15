# context-injector — Design Spec

**Date:** 2026-10-14  
**Status:** Approved first-draft (implementing)

## Tools

| Tool | Timeout | I/O |
|------|---------|-----|
| `get_code_slice` | 1s | root_path, path, start_line, end_line → code, file, hash, found |
| `find_relevant_snippets` | 1s | root_path, query, max_tokens → snippets[], total_tokens |
| `get_file_outline` | 1s | root_path, path → symbols[], line_ranges, language, found |

Missing files return `found: false` (exit 0). Path `..` rejected (exit 1).

## L5

Category `multi-file`. Gate pre-registered. No model → `pending`.
