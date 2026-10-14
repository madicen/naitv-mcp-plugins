# Plugin Template: JSON I/O Tool (Corrected for v0.0.6)

## Context

You are implementing a single plugin for the naitv-mcp enhancement ecosystem. This plugin runs as an external script (Python, Go, Shell, or Node.js) with JSON I/O, routed through the existing tool entry mechanism.

**After Phase 1 (JSON I/O support):**
- You define the plugin as a JSON I/O tool entry
- You implement the script in your chosen language
- The entry specifies the exec path, args schema, timeout
- The script reads JSON from stdin, writes JSON to stdout

**Reference:**
- PHASE1_CORRECTED.md — How JSON I/O routing works
- COMPREHENSIVE_NAITV_MCP_PLAN_EXTENDED.md — Plugin specs
- PLUGIN_REFERENCE_MATRIX.md — Plugin details (name, tools, perf target, dependencies)
- internal/plugin/README.md — Entry format (after Phase 1)

---

## Plugin Specification

Get details from PLUGIN_REFERENCE_MATRIX.md:

```
Plugin Name:     [FROM MATRIX]
Phase:           [FROM MATRIX]
Category:        [FROM MATRIX]
Tools:           [FROM MATRIX - exact list]
Implementation:  [Python/Go/Shell/Node.js]
Perf Target:     [FROM MATRIX]
Dependencies:    [FROM MATRIX]
```

---

## What You're Building

A plugin consists of:

1. **Implementation script** (tool.py, tool.go, tool.sh, etc.)
   - Reads JSON from stdin (one line: `{"key":"value",...}`)
   - Performs work
   - Writes JSON to stdout (one line: `{"result":"..."}`)
   - Returns non-zero exit code on error

2. **Entry definition** (JSON snippet for admin/code-review)
   - `name`, `description`, `exec`, `ioMode: "json"`, `timeout`, `args`
   - Added to tool store by human reviewer

3. **Tests** (unit + integration)
   - Test each tool individually
   - Test JSON I/O contract
   - Test error handling

4. **Documentation**
   - README with tool descriptions
   - Examples of input/output
   - Performance notes

---

## File Structure

```
implementation/
├── PLUGIN_NAME.py              # Or .go, .sh, etc
├── tests/
│   └── test_PLUGIN_NAME.py     # Unit tests
├── examples/
│   └── sample_input.json       # Example input
└── README.md                   # Documentation
```

(No in-tree registration; entry goes through Review gate)

---

## Implementation Checklist

### Script
- [ ] Reads JSON from stdin (sys.stdin / stdin / etc)
- [ ] Parses as JSON object
- [ ] Implements all tools from PLUGIN_REFERENCE_MATRIX.md
- [ ] Writes JSON to stdout (single line, newline-terminated)
- [ ] Returns exit code 0 on success, non-zero on error
- [ ] Error messages on stderr (free-form text)
- [ ] Handles edge cases gracefully
- [ ] Respects timeout (don't run forever)
- [ ] No external dependencies except in requirements.txt / go.mod

### Tests
- [ ] Unit test for each tool
- [ ] JSON I/O round-trip test
- [ ] Error handling test (bad input, missing args)
- [ ] Performance test vs. target
- [ ] All tests passing locally

### Documentation
- [ ] README with overview
- [ ] Tool descriptions
- [ ] Examples of input/output
- [ ] Performance characteristics
- [ ] Troubleshooting (common errors)

### Entry Definition
```json
{
  "kind": "tool",
  "name": "PLUGIN_NAME",
  "description": "...",
  "exec": "python /path/to/PLUGIN_NAME.py",
  "ioMode": "json",
  "timeout": 30,
  "args": {
    "tool1_arg1": "type/description",
    "tool1_arg2": "type/description"
  }
}
```

---

## Implementation Pattern

### Python Template

```python
#!/usr/bin/env python3
import json
import sys

def handle_tool1(args):
    """Implement tool1."""
    result = {"status": "success", "data": "..."}
    return result

def handle_tool2(args):
    """Implement tool2."""
    result = {"status": "success", "data": "..."}
    return result

def main():
    try:
        # Read input from stdin
        input_data = json.loads(input())
        tool_name = input_data.get("tool")
        
        if tool_name == "tool1":
            result = handle_tool1(input_data)
        elif tool_name == "tool2":
            result = handle_tool2(input_data)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
            print(json.dumps(result), file=sys.stderr)
            sys.exit(1)
        
        # Write result to stdout
        print(json.dumps(result))
        sys.exit(0)
    
    except Exception as e:
        error = {"error": str(e)}
        print(json.dumps(error), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Go Template

```go
package main

import (
    "encoding/json"
    "fmt"
    "io"
    "os"
)

func handleTool1(args map[string]interface{}) map[string]interface{} {
    return map[string]interface{}{
        "status": "success",
        "data":   "...",
    }
}

func main() {
    var input map[string]interface{}
    
    if err := json.NewDecoder(os.Stdin).Decode(&input); err != nil {
        fmt.Fprintf(os.Stderr, "{\"error\": \"%v\"}", err)
        os.Exit(1)
    }
    
    tool := input["tool"].(string)
    var result map[string]interface{}
    
    switch tool {
    case "tool1":
        result = handleTool1(input)
    default:
        result = map[string]interface{}{"error": "Unknown tool"}
        fmt.Fprintf(os.Stderr, "%s", toJSON(result))
        os.Exit(1)
    }
    
    json.NewEncoder(os.Stdout).Encode(result)
}

func toJSON(v interface{}) string {
    b, _ := json.Marshal(v)
    return string(b)
}
```

### Shell Template

```bash
#!/bin/bash
set -e

# Read JSON from stdin
read -r input_json

# Extract tool name (using jq)
tool_name=$(echo "$input_json" | jq -r '.tool')

case "$tool_name" in
    tool1)
        # Extract args
        arg1=$(echo "$input_json" | jq -r '.arg1')
        
        # Do work
        result=$(jq -n \
          --arg result "..." \
          '{status: "success", data: $result}')
        
        echo "$result"
        ;;
    *)
        echo '{"error":"Unknown tool"}' >&2
        exit 1
        ;;
esac
```

---

## Entry Example

For `structural-anchor` plugin:

```json
{
  "kind": "tool",
  "name": "structural-anchor",
  "description": "Extract project structure (packages, types, functions)",
  "exec": "python /home/user/.config/naitv-mcp/tools/structural-anchor.py",
  "ioMode": "json",
  "timeout": 30,
  "args": {
    "root_path": "Path to analyze",
    "depth": "Max depth (optional, default 3)"
  }
}
```

---

## Testing Checklist

- [ ] Unit test for each tool
- [ ] JSON I/O contract test
  ```python
  input_data = {"tool": "tool1", "arg": "value"}
  result = subprocess.run(
      ["python", "tool.py"],
      input=json.dumps(input_data) + "\n",
      capture_output=True,
      text=True
  )
  assert result.returncode == 0
  output = json.loads(result.stdout)
  assert "status" in output or "error" not in output
  ```
- [ ] Error handling test (bad JSON, missing tool)
- [ ] Performance vs. target
  ```bash
  time python tool.py < sample_input.json  # Should be < target
  ```
- [ ] All tests passing

---

## Performance Verification

Before marking done:

1. Test with realistic input (see examples/)
2. Measure execution time
3. Compare to target (e.g., < 2s for structural-anchor)
4. If slower:
   - Profile (python -m cProfile, go prof)
   - Identify bottleneck
   - Optimize or document

---

## Git Workflow

```bash
# Create implementation (done in code)

# Test locally
python tool.py < examples/sample_input.json | jq

# Commit
git commit -m "feat(PLUGIN_NAME): implement PLUGIN_NAME plugin

Tools:
- tool1: [description]
- tool2: [description]

Performance: < 2s on typical input
Tests: 8 unit tests, 2 integration tests
Entry: [paste JSON entry snippet]"
```

---

## Success Criteria

Plugin is done when:
- [ ] All tools implemented
- [ ] JSON I/O contract works
- [ ] Tests passing (unit + integration)
- [ ] Performance target met
- [ ] Documentation complete
- [ ] Entry definition written (ready for Review)

---

## Next Steps (After Implementation)

1. Document entry in JSON format
2. Submit to maintainer for Review
3. Once approved, entry added to tool store
4. Tool available in naitv-mcp

---

## Common Pitfalls

1. **Don't output anything except JSON to stdout**
   - Use stderr for diagnostics
   - Only JSON on stdout (one line)

2. **Don't ignore errors**
   - Exit code != 0
   - stderr message
   - Return gracefully

3. **Don't hardcode paths**
   - Use relative paths or accept via args

4. **Don't trust input**
   - Validate args
   - Handle missing fields
   - Descriptive errors

5. **Don't forget tests**
   - Unit test each tool
   - Integration test JSON I/O
   - Error cases

