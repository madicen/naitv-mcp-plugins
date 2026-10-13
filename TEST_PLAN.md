# naitv-mcp Plugin Test Plan

**Scope:** every plugin in the 60+ plugin catalog (see PLUGIN_REFERENCE_MATRIX.md)
**Goal:** prove each plugin works as specified, and prove that the full set makes a small local model measurably better at real coding tasks.

This plan has five layers. Each layer answers a different question, and each one gates the next:

| Layer | Question it answers | Runs | Blocks |
|---|---|---|---|
| L1 Unit | Does the script's logic work? | every commit | merge |
| L2 Contract | Does it speak the JSON I/O contract naitv-mcp expects? | every commit | merge |
| L3 Golden + perf | Are outputs stable and within the performance target? | every commit (perf nightly) | merge (perf: release) |
| L4 Integration (naitv-mcp) | Does the entry route correctly through the real MCP server? | every PR | merge |
| L5 Model uplift (A/B) | Does the plugin make a local model better at real tasks? | nightly + per release | "certified" status |

L1 to L4 prove the plugin is correct. L5 proves it is useful. A plugin can pass L1 to L4 and still be useless, so L5 is the only layer that decides whether a plugin ships as "certified."

---

## 1. Repository layout

Tests live beside the plugin, and shared tooling lives in one place.

```
naitv-mcp-plugins/
├── testing/                         # shared harness (no plugin logic here)
│   ├── contract/                    # L2 runner + JSON Schema per tool
│   ├── fixtures/                    # frozen sample repos (see §3)
│   │   ├── py-small/
│   │   ├── go-small/
│   │   ├── mixed-polyglot/
│   │   ├── empty/
│   │   ├── hostile/                 # symlink loops, binary files, huge lines
│   │   └── generated-50k/           # built on demand by a script, never committed
│   ├── golden/                      # expected outputs per plugin per fixture
│   ├── eval/                        # L5 harness (see §6)
│   │   ├── tasks/                   # versioned task suites
│   │   ├── graders/
│   │   └── runs/                    # gitignored; results land here
│   └── README.md
└── plugins/
    └── structural-anchor/
        ├── plugin.json
        ├── structural-anchor.py
        ├── go-symbols/
        ├── tests/
        │   ├── test_unit.py         # L1
        │   └── test_perf.py         # L3 (marked, nightly)
        └── README.md
```

Each plugin owns its L1 tests. Shared assets (fixtures, schemas, golden files, the eval harness) belong to `testing/`. This keeps plugins self-contained while preventing five copies of the same fixture repo.

---

## 2. Layer 1: Unit tests (per plugin)

**Purpose:** verify internal logic in isolation.

**Owner:** the plugin author.

**Tooling:** pytest for Python, `go test` for Go helpers, bats for shell.

**Requirements for every plugin:**
- One test per tool minimum, plus at least one per error path.
- Tests call functions directly, not through the subprocess boundary. The subprocess boundary is L2's job.
- No network access. Tests that need the network must be marked `@pytest.mark.network` and are excluded from CI.
- Tests must not write outside a temp directory.
- Coverage floor: 80% line coverage on the plugin's own code. Generated or vendored code is excluded.

**structural-anchor examples:**
- `get_project_map` skips directories listed in `skip_dirs`.
- A `depth=1` walk does not return symbols from `pkg/a/b/c.py`.
- A Python file with a syntax error produces a `parse_error` entry and does not abort the run.
- A module-level constant that is not exported in Go does not appear in symbols.
- Complexity returns `0.0` when no functions are parsed (not `NaN`, not an exception).

---

## 3. Layer 2: Contract tests (shared harness)

**Purpose:** verify that every plugin obeys the naitv-mcp JSON I/O contract, so that a plugin written in any language is interchangeable.

**Owner:** `testing/contract/`. Written once, reused by all plugins.

**The contract under test:**

| Property | Requirement |
|---|---|
| stdin | exactly one JSON object, one line, newline-terminated |
| stdout on success | exactly one JSON object, one line, exit code 0 |
| stdout on failure | nothing, or a single JSON error object; never a partial object |
| stderr | free-form diagnostics only; never required for parsing |
| exit code | 0 success, non-zero failure |
| timeout | process killed at `timeout` seconds; the harness must report the kill as a failure |
| output size | stdout must be bounded (default 1 MB); larger output is a failure |
| determinism | same input and same repo state produce byte-identical stdout (ignoring `cached` and timing fields) |
| purity | no writes outside the plugin's cache dir (`~/.cache/naitv-mcp/<plugin>/`) |

**How the harness works:**
1. Reads each plugin's `plugin.json` and enumerates its tool entries.
2. For each entry, runs the exact `exec` string from the entry, including the `TOOL_NAME=... ` prefix, through `sh -c`, which is how naitv-mcp runs it.
3. Feeds each input from `testing/fixtures/inputs/<tool>/*.json`.
4. Validates stdout against `testing/contract/schemas/<tool>.schema.json`.
5. Runs each input twice and diffs the output to check determinism.
6. Measures wall time and compares it with the entry's `timeout`.

**Required negative cases (every tool):**
- Malformed JSON on stdin → non-zero exit, no partial stdout.
- Missing required field → non-zero exit with a descriptive stderr message.
- Unknown extra field → accepted and ignored (forward compatibility).
- `root_path` that does not exist → non-zero exit, error JSON on stderr.
- `root_path` containing `..` traversal → rejected or normalized, never escapes.
- Input larger than 1 MB → rejected with a clear error.

---

## 4. Layer 3: Golden and performance tests

### 4a. Golden output tests

**Purpose:** catch silent behavior changes.

Each plugin has golden outputs in `testing/golden/<plugin>/<tool>/<fixture>.json`. The test runs the tool on each fixture and compares against the golden file.

- Golden files are regenerated only with an explicit `--update-golden` flag, and the diff must be reviewed in the PR.
- Fields that legitimately vary (`cached`, `commit`, timing) are masked before comparison.
- Ordering must be stable. Outputs are sorted by path, then line number.

### 4b. Performance tests

**Purpose:** verify the per-plugin performance target from PLUGIN_REFERENCE_MATRIX.md.

**Setup:** a dedicated runner with fixed hardware (recorded in the results). The `generated-50k` fixture is built once per run by `testing/fixtures/generate.py --files 50000 --seed 42`.

**Measurement rules:**
- Report p50 and p95 over 10 runs, after 2 warm-up runs.
- Report cold and warm separately. Cold means the cache is empty. Warm means the cache is populated.
- A test fails if p95 exceeds the target by more than 10%.
- Targets from the matrix, for reference: structural-anchor `get_project_map` < 2s on 50K files; symbol lookup < 100ms; context slice < 50ms; linter < 1s per file; test runner < 5s.

**structural-anchor cold-start note:** the first call pays the Go helper build cost (see the Phase 2.1 design). Cold-start budget is therefore measured separately, with a looser target that is still reported.

---

## 5. Layer 4: Integration tests through naitv-mcp

**Purpose:** prove the entry works through the real server, not just through the script.

**Owner:** the naitv-mcp core team, with plugin authors adding cases.

**Test flow for each plugin entry:**
1. Start naitv-mcp with a test config that loads only the plugin under test.
2. Call `list_tools` and confirm every tool in the manifest is present, with the expected name, description, and input schema.
3. Call each tool with a valid fixture input through the MCP protocol.
4. Confirm the response is well-formed MCP output, and that the JSON payload matches the L2 schema.
5. Call each tool with an invalid input and confirm the error reaches the client as a structured error, not a crash.
6. Kill the plugin mid-run (via timeout) and confirm naitv-mcp reports a timeout and remains responsive.

**Cross-plugin checks** (run once per phase):
- No two entries claim the same tool name.
- No entry's `exec` references a path outside the plugin directory, except documented shared binaries.
- Every entry is in an approved review state before it is listed as available.

**Existing repo tooling:** the Go side of naitv-mcp already exposes `test`, `test_race`, `test_run`, `vet`, and `lint` tools. Core-level integration tests should use those, so plugin tests don't invent a parallel runner.

---

## 6. Layer 5: Model uplift evaluation (the one that matters)

**Purpose:** measure whether a small local model does better on real tasks with the plugins enabled than without them.

### 6a. Conditions

Every run is one of two conditions, and the only difference between them is the plugin set exposed through naitv-mcp.

| Condition | Plugins exposed | Everything else |
|---|---|---|
| **Baseline (B)** | core naitv-mcp tools only | identical |
| **Treatment (T)** | core + the plugin set under test | identical |

Hold these constant across conditions:
- Model name, quantization, context window, temperature, and seed (where the runtime supports seeding).
- System prompt and tool-usage instructions.
- Task text and the fixture repo state.
- Maximum turns and maximum tokens.
- The local runtime version (record the exact Ollama or llama.cpp version).

Randomize the order of tool definitions per run, so the model cannot learn that a position means something.

### 6b. Task suites

Tasks are versioned files in `testing/eval/tasks/<suite>/v<N>/`. Each task contains:
- A fixture repo reference and a starting commit.
- A natural-language request, written as a developer would write it.
- A machine-checkable success criterion (see §6c).
- A difficulty tag and a category tag (see table below).

| Category | Example task | Plugins expected to matter |
|---|---|---|
| Navigation | "Where is `UserService` defined and who calls it?" | symbol-navigator, structural-anchor |
| Structure | "Add a method to an existing type without breaking its interface" | specification-enforcer, structural-anchor |
| Fix-with-tests | "Make the failing test in `pkg/billing` pass" | lint-fix-loop, tdd-runner, validate-and-test |
| Refactor | "Rename a function and update all callers" | surgical-patch, symbol-navigator |
| Multi-file | "Add a new endpoint following the existing pattern" | golden-example-injector, context-injector |
| Control | "Explain what this 20-line function does" | none (should not regress) |

**Suite sizes (proposed):**
- Dev suite: 40 tasks, used while building plugins.
- Eval suite: 120 tasks, used for certification.
- Held-out suite: 40 tasks, never used during plugin development. Used once per release to detect overfitting.

Include at least 20% control tasks in every suite. Their job is to detect harm, which is the most common failure mode when tooling is added to a small model.

### 6c. Graders

Grading is deterministic. No LLM-as-judge in the certification path.

- **Behavioral graders:** run the project's test command and check pass or fail. Check that no files outside the expected set were modified.
- **Structural graders:** check that the final diff parses, applies cleanly, and touches only permitted paths.
- **Hallucination grader:** extract every symbol the model names in its final answer or diff, and check each one against the fixture's real symbol table. Report the rate of nonexistent symbols.
- **Efficiency metrics (recorded, not graded):** turns, tool calls, input and output tokens, wall time.

### 6d. Run protocol

- Each task runs **3 times per condition** (3 seeds). Total for the eval suite: 120 tasks × 3 seeds × 2 conditions = 720 runs.
- Runs are paired by task and seed, so the analysis uses paired statistics.
- Failed infrastructure runs (crash, timeout from the harness itself, not the model) are retried once and logged. They are never silently dropped.

### 6e. Metrics and pre-registered thresholds

Thresholds are written down before the run, so results can't be reinterpreted afterward.

| Metric | Gate for "helps" | Gate for "harmful" |
|---|---|---|
| Task success rate, T vs B | T higher by ≥ 10 percentage points, 95% CI excluding zero | Control-task success drops by more than 2 points |
| Nonexistent-symbol rate | T lower by ≥ 30% relative | T higher at all |
| Median tool calls to success | T lower | T higher by more than 25% |
| Tokens per successful task | Reported, no gate | Reported, no gate |

**Statistics:** paired bootstrap confidence intervals on the success-rate difference (10,000 resamples), and McNemar's test on per-task outcomes. Report effect sizes, not only p-values.

### 6f. Ablation

For any plugin set that passes the gate, run ablations to find which plugins carry the gain:
- Leave-one-out: T minus one plugin, for each plugin in the set.
- Report any plugin whose removal changes success by less than 2 points as a candidate for removal. A plugin that adds tokens without adding success is a cost, not a feature.

### 6g. Context budget

Local models have a fixed context window, so the plugins compete for it. Track the total tokens that plugin outputs inject per task. Run one additional condition at a reduced context window (for example, 50% of the normal size) to confirm the plugins degrade gracefully rather than crowding out the task.

---

## 7. Certification levels

A plugin's status is determined by the highest layer it has passed.

| Level | Requirement | Meaning |
|---|---|---|
| **Draft** | L1 and L2 pass | Works in isolation. Not offered to users. |
| **Verified** | L1 through L4 pass, perf within target | Correct and integrates with naitv-mcp. Offered with a warning. |
| **Certified** | L5 passes the "helps" gate on the eval suite, does not trip the "harmful" gate, and holds on the held-out suite | Measured to improve a small local model. Offered by default. |

Certification is per plugin **and** per plugin set. A plugin can be Verified but not Certified if its measured effect is within noise.

---

## 8. Cadence and CI

| Trigger | Runs |
|---|---|
| Every commit to a plugin | L1, L2 for that plugin |
| Every PR | L1, L2, L3 golden, L4 for changed plugins |
| Nightly | L3 perf on the fixed runner; L5 dev suite on the changed plugin set |
| Release candidate | L5 eval suite and held-out suite; ablation; full L4 across all plugins |
| Phase exit | Full L1 to L5 on everything built in that phase |

Results from each run are stored with the naitv-mcp version, plugin versions, model identifier and quantization, and hardware. A result that cannot be reproduced from those fields is not admissible for certification.

---

## 9. Mapping to the implementation phases

| Phase | Test deliverables |
|---|---|
| 1 (naitv-mcp core, JSON I/O) | L2 harness; L4 integration harness; `plugin-manager` `test_plugin` tool wired to L2 |
| 2 (context tools) | Fixtures (`py-small`, `go-small`, `mixed-polyglot`, `hostile`, `empty`); 50K generator; golden files; L3 perf runner; first L5 dev suite (navigation and structure tasks only) |
| 3 (validation) | Fix-with-tests task category; hallucination grader |
| 4 (optimization) | Cache-correctness tests (stale results after file change must never be returned); cold vs warm perf reporting |
| 5 (workflows) | Multi-file and refactor categories; full L5 eval suite and held-out suite |
| 6 (domain) | Per-domain task suites; leave-one-out ablation across the full set |

**Phase 2 must not start with the L5 harness.** Build L1 to L4 first, so the first plugin's uplift measurement is trustworthy.

---

## 10. Open decisions

These need an answer before the harness is built. Each is listed with my recommendation.

1. **Local model under test.** Recommend one fixed model and quantization as the reference (for example, a 7B to 8B coder model at Q4), plus a second model later to check that results generalize. Model choice changes the numbers, so it has to be fixed before baselines are recorded.
2. **Eval task source.** Recommend writing tasks against the fixture repos first, then adding tasks from real naitv-mcp issues once the harness is stable.
3. **Who maintains the held-out suite.** Recommend the person who does not write plugins, so the held-out suite stays independent of plugin development.
4. **Perf runner hardware.** Recommend one dedicated machine, recorded in every result, rather than the developer laptops.

---

## 11. Immediate next steps

1. Build the L2 contract harness and its schemas for the three structural-anchor tools.
2. Build the `generated-50k` fixture generator and the `py-small` and `go-small` fixtures.
3. Write the L1 tests for structural-anchor alongside its implementation, not after it.
4. Wire L4 for structural-anchor through the real naitv-mcp server.
5. Build the L5 harness skeleton with the navigation category only, and record a baseline before any plugin is enabled in treatment.

Step 5 matters most. A baseline recorded before any plugin is turned on is the only way to tell later whether a plugin helped.
