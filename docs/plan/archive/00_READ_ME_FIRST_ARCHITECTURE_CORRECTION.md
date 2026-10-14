# ⚠️ ARCHITECTURE CORRECTION: Phase 1 Rewritten for v0.0.6

## What Changed

The original Phase 1 prompt was based on assumptions about naitv-mcp's structure that don't match v0.0.6 reality.

**Original (incorrect):**
- Assumed Plugin interface with CallTool/Execution() methods
- Proposed new SubprocessHost + plugins/ folder discovery
- Would create a second, parallel plugin system

**Corrected (v0.0.6 compatible):**
- Extends existing tools.Def + tools.Run
- Adds optional `ioMode: "json"` field to tool entries
- Reuses existing registry, Review gate, hot-reload
- No new infrastructure, no duplication

---

## Files to Use (Corrected)

### Phase 1 Implementation
**Read: `PHASE1_CORRECTED.md`**
- Extends tools.Def with IOMode field
- Updates tools.Run for JSON stdin/stdout marshaling
- Documents entry format + examples
- Maintains backward compatibility

### Plugin Implementation Template
**Read: `PLUGIN_TEMPLATE_CORRECTED.md`**
- Shows how to write a JSON I/O script (Python/Go/Shell)
- Entry definition format
- Testing approach
- Success criteria

### All Other Documents
- COMPREHENSIVE_NAITV_MCP_PLAN_EXTENDED.md — Plugin specs unchanged
- PLUGIN_REFERENCE_MATRIX.md — Plugin details unchanged
- CURSOR_QUICK_START.md — Guidance unchanged
- MASTER_INDEX.md — Navigation unchanged

---

## Quick Summary: What Phase 1 Does

**Goal:** Enable external scripts (Python, Go, Shell) to be MCP tools with JSON I/O.

**How:**
1. Add `ioMode` field to tools.Def
2. Extend tools.Run to handle JSON marshaling
3. Document entry format
4. Write tests

**Entry example:**
```json
{
  "kind": "tool",
  "name": "structural-anchor",
  "exec": "python /path/to/structural-anchor.py",
  "ioMode": "json",
  "timeout": 30,
  "args": {"root_path": "..."}
}
```

**Script contract:**
```
Stdin:  {"root_path": "/repo", ...}\n
Stdout: {"packages": [...], "stats": {...}}\n
Stderr: (error messages if exit != 0)
Exit:   0 on success
```

---

## Implementation Workflow

### Step 1: Create Worktree
```bash
git worktree add ../naitv-mcp-phase1 HEAD
cd ../naitv-mcp-phase1
git checkout -b feat/phase1-json-tool-io
```

### Step 2: Read Phase 1 Spec
Open and read `PHASE1_CORRECTED.md` completely. It covers:
- Exact file changes (tools.Def, tools.Run)
- Entry format documentation
- Template examples
- Tests needed

### Step 3: Implement (in Cursor auto mode)
Paste this prompt into Cursor:

[See CURSOR_PROMPTS_FOR_IMPLEMENTATION_CORRECTED.md — coming next]

### Step 4: After Phase 1 Complete
- Verify tests pass
- Commit to feat/phase1-json-tool-io
- Begin Phase 2+ plugins using PLUGIN_TEMPLATE_CORRECTED.md

---

## Why This Approach

✅ **Extends existing code** — tools.Def, tools.Run, Review gate
✅ **Non-breaking** — text mode unchanged, JSON is opt-in
✅ **Minimal** — 1 field + 1 method enhancement
✅ **Reuses machinery** — timeout, sh -c, registry all exist
✅ **Keeps naitv-mcp generic** — just transport layer
✅ **Humans in loop** — Review gate still gates activation

---

## What Stays the Same

- Plugin specs (COMPREHENSIVE_NAITV_MCP_PLAN_EXTENDED.md)
- Plugin list (PLUGIN_REFERENCE_MATRIX.md)
- Performance targets
- 67 total plugins
- 26-week timeline (5 phases: 1 core + 4 plugin phases)

**What changed:** How Phase 1 is implemented to match actual codebase.

---

## Files to Read Next

1. **PHASE1_CORRECTED.md** (7 tasks, ~30 min read)
2. **PLUGIN_TEMPLATE_CORRECTED.md** (template for all 67 plugins)
3. **CURSOR_PROMPTS_FOR_IMPLEMENTATION_CORRECTED.md** (ready-to-paste prompts)

---

## Questions?

The correction ensures:
- ✅ Phase 1 can actually be implemented (files exist, structure matches)
- ✅ Phase 2-6 plugins use the right mechanism (entry-based JSON I/O)
- ✅ No wasted effort building a second plugin system
- ✅ Lean approach (extend what exists)

If anything is unclear, re-read PHASE1_CORRECTED.md sections 1.1-1.2.

---

**Status:** Ready to begin. Create worktree, read PHASE1_CORRECTED.md, paste prompt into Cursor.
