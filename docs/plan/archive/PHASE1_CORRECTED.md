# Phase 1: Add JSON I/O to Tool Entries (Corrected for v0.0.6)

## Reality Check

**This repo (v0.0.6):**
- Tools = JSON entries in store (internal/plugin)
- Plugins = approved kind=tool + exec store entries
- tools.Run already shells out via `sh -c` with timeout
- No Plugin interface with CallTool method
- No separate plugins/ folder for executables

**Old prompt assumed:**
- A Plugin interface with CallTool/Execution()
- plugins/ folder discovery
- New SubprocessHost

**That would duplicate existing registry + hot-reload logic.**

---

## Approach A: Extend Existing Tool Entries

**Goal:** Enable external scripts (Python, Go, Shell, Node.js) to use JSON I/O + timeout, routed through existing tools.Run machinery.

**Changes:**
1. Add optional `ioMode` field to tools.Def
2. Extend tools.Run to handle JSON I/O marshaling/unmarshaling
3. Document entry format for JSON I/O tools
4. Tests for JSON round-trip
5. Plugin templates as examples (not in-tree, just documented)

---

## Phase 1 Implementation Tasks

### Task 1.1: Extend tools.Def with JSON I/O

**File:** `internal/tools/def.go` (or tools.Def location)

Add optional fields:
```go
type Def struct {
    // existing fields...
    
    // NEW: Optional JSON I/O mode
    IOMode   string // "text" (default) | "json"
    Timeout  int    // seconds (default 30)
}
```

**Requirements:**
- `IOMode` defaults to "text" (backward compatible)
- "text" = current behavior (raw stdout)
- "json" = marshal args to JSON stdin, parse JSON stdout
- Documented in comments

### Task 1.2: Extend tools.Run for JSON I/O

**File:** `internal/tools/run.go` (or equivalent)

Update Run() to:
1. Check if entry.IOMode == "json"
2. If yes:
   - Marshal args map to JSON (one line, newline-terminated)
   - Write to subprocess stdin
   - Read JSON from stdout (one line)
   - Unmarshal to result
   - stderr = error message (free-form)
3. If no:
   - Current behavior (stdout as result)
4. Both modes: respect Timeout, enforce exit code 0

**Contract (JSON I/O mode):**
```
Stdin:  {"key":"value","key2":"value2"}\n
Stdout: {"result":"data","status":"success"}\n
Stderr: Error messages (free-form, if exit code != 0)
Exit:   0 = success, non-zero = error
```

**Requirements:**
- Backward compatible (text mode unchanged)
- Proper error handling (exit code + stderr)
- Timeout enforcement (kill subprocess if exceeds timeout)
- Test both JSON and text modes

### Task 1.3: Document Entry Format for JSON I/O Tools

**File:** `internal/plugin/README.md` (or docs)

Document how to define a JSON I/O tool entry:

```json
{
  "kind": "tool",
  "name": "structural-anchor",
  "description": "Extract project structure (packages, types, functions)",
  "exec": "python /path/to/structural-anchor.py",
  "ioMode": "json",
  "timeout": 30,
  "args": {
    "root_path": "path to analyze",
    "depth": "optional max depth"
  }
}
```

Document:
- `exec` = command to run (sh -c compatible)
- `ioMode` = "text" or "json"
- `timeout` = seconds
- `args` = input schema (for humans, not enforced)
- Return value = parsed JSON (if ioMode=json) or raw stdout

### Task 1.4: Create Plugin Template Examples

**Location:** Docs only (not in-tree)

Provide examples for implementing external JSON I/O tools:

**Python template** (structural-anchor example):
```python
#!/usr/bin/env python3
import json
import sys

try:
    # Read JSON from stdin (single line)
    input_data = json.loads(input())
    
    root_path = input_data.get("root_path")
    depth = input_data.get("depth", 3)
    
    # Do work here
    result = {
        "packages": [...],
        "languages": ["go", "python"],
        "statistics": {...}
    }
    
    # Write JSON to stdout (single line)
    print(json.dumps(result))
    sys.exit(0)
except Exception as e:
    # Error goes to stderr
    print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.exit(1)
```

**Go template:**
```go
package main

import (
    "encoding/json"
    "fmt"
    "os"
)

func main() {
    var input map[string]interface{}
    json.NewDecoder(os.Stdin).Decode(&input)
    
    // Do work
    result := map[string]interface{}{
        "data": "...",
    }
    
    json.NewEncoder(os.Stdout).Encode(result)
}
```

**Shell template:**
```bash
#!/bin/bash
set -e

# Read JSON from stdin
read -r input_json

# Parse JSON (using jq or similar)
root_path=$(echo "$input_json" | jq -r '.root_path')

# Do work
result=$(jq -n \
  --arg root "$root_path" \
  '{root: $root, result: "..."}')

# Write JSON to stdout
echo "$result"
```

Document:
- Stdin/stdout contract
- Error handling (stderr + exit code)
- Timeout expectations
- Testing approach

### Task 1.5: Write Tests

**Files:** `internal/tools/run_test.go` (or tools tests)

Tests needed:
- [ ] JSON I/O round-trip (marshal args, parse result)
- [ ] Text mode still works (unchanged behavior)
- [ ] Error handling (exit code != 0)
- [ ] Timeout enforcement
- [ ] Subprocess cleanup on timeout
- [ ] Malformed JSON handling

Example test:
```go
func TestRunJSONIO(t *testing.T) {
    entry := &Def{
        Name: "test-tool",
        Exec: `python -c 'import json, sys; data=json.load(sys.stdin); print(json.dumps({"result": data["input"].upper()}))'`,
        IOMode: "json",
        Timeout: 5,
    }
    
    args := map[string]interface{}{"input": "hello"}
    result, err := Run(context.Background(), entry, args)
    
    // Parse result as JSON
    var output map[string]interface{}
    json.Unmarshal([]byte(result.(string)), &output)
    
    assert.Equal(t, "HELLO", output["result"])
}
```

### Task 1.6: Update Documentation

**Files:**
- `internal/tools/README.md` or `docs/TOOLS.md`
- `internal/plugin/README.md`

Document:
- Tool entry format (existing + new IOMode field)
- JSON I/O contract (stdin/stdout/stderr/exit)
- When to use json vs text mode
- Examples for each language (Python, Go, Shell)
- Performance expectations
- Testing guidance

### Task 1.7: Integration with Review

**Existing:** Human-in-the-loop via Review gate before tool activation

**No change needed.** JSON I/O mode is just an option on existing Def entries. Review gate still applies.

---

## Acceptance Criteria

- [ ] tools.Def has optional IOMode field
- [ ] tools.Run handles JSON I/O marshaling/unmarshaling
- [ ] Backward compatible (text mode unchanged)
- [ ] Error handling with exit code + stderr
- [ ] Timeout enforcement on JSON I/O
- [ ] Tests pass (JSON + text modes, errors, timeout)
- [ ] Documentation complete with examples
- [ ] Examples show Python, Go, Shell usage
- [ ] Entry format documented

---

## Git Workflow

Create a worktree:
```bash
git worktree add ../naitv-mcp-phase1 HEAD
cd ../naitv-mcp-phase1
git checkout -b feat/phase1-json-tool-io
```

Commit:
```bash
git commit -m "feat(phase1): add JSON I/O mode to tool entries

- Add IOMode field to tools.Def (text|json)
- Extend tools.Run for JSON stdin/stdout marshaling
- Maintain backward compatibility with text mode
- Add timeout enforcement for external scripts
- Document entry format and examples
- Add tests for JSON I/O round-trip

This enables external scripts (Python, Go, Shell) to be used as MCP tools
via the existing entry mechanism, without creating a parallel plugin system."
```

---

## Why This Approach

✅ **Extends existing system** — tools.Def, tools.Run, Review gate
✅ **Non-breaking** — text mode unchanged, JSON is optional
✅ **Lazy-ladder** — reuses timeout + sh -c from tools.Run
✅ **Keeps naitv-mcp generic** — entry = transport layer
✅ **Humans in the loop** — Review still gates activation
✅ **Minimal surface** — 1 field + 1 method enhancement
✅ **No duplication** — doesn't rebuild registry/hot-reload

---

## After Phase 1

Once JSON I/O works:
- Phase 2-6: Create tools as JSON I/O entries
- Each plugin = standalone script (Python/Go/Shell) + entry definition
- Entries define args, timeout, exec path
- Scripts read JSON from stdin, write JSON to stdout
- Same plugin specs as before, just routed through tools.Def

Later (Phase 4+, if needed):
- Optional: folder-based discovery (~/.config/naitv-mcp/tools/)
- Scan folder, auto-register .json entries as tools
- But only if entry-based proves insufficient

