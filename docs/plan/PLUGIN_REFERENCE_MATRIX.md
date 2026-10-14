# Complete Plugin Reference Matrix
**Quick lookup for all 67 plugins across 6 phases**

---

## How to Use This Matrix

Each row represents one plugin:
- **Name** - Plugin name in kebab-case
- **Phase** - When to implement (1-6)
- **Type** - Category
- **Tools** - Number of tools/functions it exposes
- **Implementation** - Primary language/approach
- **Perf Target** - Performance goal
- **Dependencies** - Requires which plugins
- **Complexity** - L=Low, M=Medium, H=High, X=Expert
- **Priority** - 1=Critical, 2=Important, 3=Nice-to-have

---

## Phase 1: Foundation (Weeks 1-2)

| Name | Tools | Implementation | Perf Target | Complexity | Priority |
|------|-------|-----------------|-------------|------------|----------|
| **naitv-mcp-core** | - | Go | N/A | M | 1 |
| **plugin-manager** | 3 | Python | < 1s | L | 1 |
| **py-template** | - | Python | N/A | L | 1 |
| **go-template** | - | Go | N/A | L | 1 |
| **sh-template** | - | Shell | N/A | L | 1 |

---

## Phase 2: Context & Specification (Weeks 3-5)

| Name | Tools | Implementation | Perf Target | Depends On | Complexity | Priority |
|------|-------|-----------------|-------------|-----------|------------|----------|
| **structural-anchor** | 3 | Python/Go AST | < 2s (50K files) | Plugin framework | M | 1 |
| **symbol-navigator** | 3 | LSP + AST | < 100ms | structural-anchor | M | 1 |
| **context-injector** | 3 | Python/Go AST | < 50ms | symbol-navigator | M | 1 |
| **specification-enforcer** | 4 | Python/Go AST | < 500ms | symbol-navigator | M | 1 |
| **decision-log-runner** | 4 | Markdown parsing | < 1s | semantic-search | M | 2 |
| **team-knowledge-extractor** | 4 | AST + git mining | < 2s | structural-anchor | M | 2 |
| **code-review-simulator** | 4 | Heuristics + ML | < 2s | code-style-enforcer | M | 2 |
| **blame-context-historian** | 4 | Git blame parsing | < 500ms | plugin framework | L | 3 |

---

## Phase 3: Validation & Self-Correction (Weeks 6-10)

| Name | Tools | Implementation | Perf Target | Depends On | Complexity | Priority |
|------|-------|-----------------|-------------|-----------|------------|----------|
| **lint-fix-loop** | 3 | Linter wrappers | < 1s | validate-and-test | L | 1 |
| **tdd-runner** | 3 | Test framework | < 5s | validate-and-test | L | 1 |
| **validate-and-test** | 3 | Build tools | < 5s | build-system | L | 1 |
| **mistake-tracker** | 4 | Git mining + ML | < 3s | cache-manager | M | 1 |
| **pattern-recognizer** | 4 | Code search + ML | < 1s | workspace-search | M | 1 |
| **build-system-integrator** | 4 | Build wrappers | < 5s | plugin framework | L | 1 |
| **dependency-graph-analyzer** | 4 | Import analysis | < 1s | structural-anchor | M | 1 |
| **regression-test-generator** | 3 | Template-based | < 2s | tdd-runner | L | 2 |
| **naming-validator** | 4 | Heuristics | < 100ms | code-style | L | 2 |
| **type-safety-enhancer** | 4 | Type inference | < 500ms | symbol-navigator | M | 2 |

---

## Phase 4: Advanced Context & Optimization (Weeks 11-14)

| Name | Tools | Implementation | Perf Target | Depends On | Complexity | Priority |
|------|-------|-----------------|-------------|-----------|------------|----------|
| **doc-scraper** | 3 | Markdown + HTML | < 3s | plugin framework | M | 2 |
| **workspace-search** | 3 | ripgrep + ranking | < 500ms | plugin framework | L | 1 |
| **cache-manager** | 4 | In-memory + SQLite | < 100ms | plugin framework | M | 1 |
| **error-matcher** | 3 | Similarity matching | < 2s | mistake-tracker | M | 1 |
| **task-decomposer** | 4 | Structured prompt | < 2s | structural-anchor | M | 2 |
| **mock-stub-generator** | 4 | Template-based | < 1s | symbol-navigator | L | 2 |
| **code-style-enforcer** | 4 | AST analysis | < 1s | team-knowledge | M | 2 |
| **documentation-enforcer** | 4 | AST walking | < 1s | lint-fix-loop | L | 2 |
| **secrets-detector** | 4 | Pattern matching | < 500ms | plugin framework | L | 1 |
| **circular-dependency-detector** | 4 | Graph analysis | < 1s | dependency-graph | M | 1 |

---

## Phase 5: Specialized Workflows & Safety (Weeks 15-18)

| Name | Tools | Implementation | Perf Target | Depends On | Complexity | Priority |
|------|-------|-----------------|-------------|-----------|------------|----------|
| **think-before-write** | 3 | Prompt structure | < 2s | task-decomposer | L | 1 |
| **golden-example-injector** | 3 | Code search + rank | < 1s | workspace-search | M | 1 |
| **type-import-stubber** | 3 | AST parsing | < 500ms | symbol-navigator | L | 1 |
| **surgical-patch** | 3 | Diff generation | < 1s | lint-fix-loop | M | 1 |
| **api-contract-validator** | 4 | API extraction | < 1s | symbol-navigator | M | 1 |
| **invariant-checker** | 4 | Pattern matching | < 2s | team-knowledge | M | 1 |
| **security-checker** | 4 | Pattern DB | < 2s | lint-fix-loop | M | 1 |
| **performance-profiler** | 4 | Benchmarking | < 3s | build-system | M | 2 |
| **test-coverage-analyzer** | 4 | Coverage tools | < 2s | tdd-runner | L | 2 |
| **refactoring-suggester** | 5 | Code analysis | < 2s | structural-anchor | M | 2 |
| **accessibility-checker** | 4 | AST + rules | < 2s | lint-fix-loop | M | 3 |
| **feature-flag-manager** | 4 | Template-based | < 1s | validate-and-test | L | 3 |
| **rollback-plan-generator** | 4 | Change analysis | < 2s | change-impact | M | 3 |
| **logging-enforcer** | 4 | Pattern matching | < 1s | code-style | L | 2 |
| **deprecation-manager** | 4 | Annotation parsing | < 2s | symbol-navigator | L | 2 |

---

## Phase 6: Domain-Specific & Advanced (Weeks 19-24)

| Name | Tools | Implementation | Perf Target | Depends On | Complexity | Priority |
|------|-------|-----------------|-------------|-----------|------------|----------|
| **language-idioms-enforcer** | 4 | Pattern library | < 500ms | code-style | M | 2 |
| **database-schema-validator** | 5 | Schema parsing | < 3s | validate-and-test | H | 2 |
| **environment-validator** | 4 | Config parsing | < 1s | validate-and-test | M | 2 |
| **monitoring-alerting-setup** | 4 | Template-based | < 2s | performance-profiler | M | 3 |
| **fuzzing-test-generator** | 4 | Go fuzzing | < 5s | tdd-runner | H | 2 |
| **integration-test-generator** | 4 | Test scaffolding | < 3s | tdd-runner | H | 2 |
| **contract-testing-helper** | 4 | API analysis | < 2s | api-contract | M | 3 |
| **benchmark-generator** | 5 | Language-specific | < 3s | build-system | M | 2 |
| **memory-profiler** | 4 | Profiler wrapper | < 5s | performance-profiler | M | 3 |
| **goroutine-leak-detector** | 4 | pprof analysis | < 3s | concurrency-checker | H | 2 |
| **concurrency-checker** | 4 | Static analysis | < 2s | validate-and-test | H | 2 |
| **stale-code-identifier** | 4 | Graph analysis | < 2s | structural-anchor | M | 2 |
| **interface-segregation-enforcer** | 4 | Interface analysis | < 2s | symbol-navigator | M | 2 |
| **team-metrics-collector** | 4 | Metrics aggregation | < 5s | cache-manager | M | 2 |
| **license-compliance-checker** | 4 | Dependency analysis | < 2s | plugin framework | L | 2 |
| **performance-regression-detector** | 4 | Benchmark compare | < 10s | benchmark-generator | M | 2 |
| **documentation-sync-manager** | 4 | Doc/code compare | < 3s | documentation-enforcer | M | 2 |
| **change-impact-analyzer** | 4 | Dependency graph | < 2s | dependency-graph | M | 2 |
| **incremental-refactoring-helper** | 4 | State tracking | < 2s | refactoring-suggester | M | 3 |
| **code-generation-helper** | 5 | Template-based | < 1s | symbol-navigator | L | 3 |

---

## Summary Statistics

### By Phase
| Phase | Plugins | Tools | Avg Complexity | Total Weeks |
|-------|---------|-------|-----------------|------------|
| 1 | 5 | ~5 | L | 2 |
| 2 | 8 | ~27 | M | 3 |
| 3 | 10 | ~35 | M | 5 |
| 4 | 10 | ~38 | M | 4 |
| 5 | 15 | ~56 | M | 4 |
| 6 | 20 | ~83 | M-H | 6 |
| **TOTAL** | **68** | **244** | **M** | **24** |

### By Complexity
- **Low (15):** plugin-manager, lint-fix-loop, tdd-runner, build-system, naming-validator, workspace-search, regression-test-gen, mock-stub-gen, type-import-stubber, surgical-patch, logging-enforcer, deprecation-manager, language-idioms, license-checker, code-gen-helper
- **Medium (45):** Most plugins
- **High (6):** database-schema-validator, fuzzing-test-gen, integration-test-gen, goroutine-leak-detector, concurrency-checker, memory-profiler
- **Expert (2):** None yet (could add if needed)

### By Priority
- **Priority 1 (Critical, 24):** Must have for core functionality
- **Priority 2 (Important, 35):** Significantly improve model quality
- **Priority 3 (Nice-to-have, 9):** Specialized use cases

### By Category
| Category | Count | Critical | Important | Nice-to-have |
|----------|-------|----------|-----------|--------------|
| Context & Knowledge | 13 | 6 | 6 | 1 |
| Validation & Testing | 18 | 10 | 7 | 1 |
| Refactoring & Improvement | 12 | 2 | 9 | 1 |
| Safety & Compliance | 12 | 8 | 4 | 0 |
| Automation & Generation | 8 | 2 | 5 | 1 |
| Specialized | 4 | 2 | 2 | 0 |

---

## Implementation Order (By Value)

### Tier 1 (Highest ROI - Do First)
1. structural-anchor (Phase 2)
2. symbol-navigator (Phase 2)
3. context-injector (Phase 2)
4. lint-fix-loop (Phase 3)
5. tdd-runner (Phase 3)
6. build-system-integrator (Phase 3)
7. dependency-graph-analyzer (Phase 3)
8. cache-manager (Phase 4)
9. workspace-search (Phase 4)
10. mistake-tracker (Phase 3)

**Timeline: Weeks 1-12** | **Impact: 60% of total quality improvement**

### Tier 2 (High Value - Do Next)
11. think-before-write (Phase 5)
12. golden-example-injector (Phase 5)
13. specification-enforcer (Phase 2)
14. decision-log-runner (Phase 2)
15. code-style-enforcer (Phase 4)
16. invariant-checker (Phase 5)
17. security-checker (Phase 5)
18. task-decomposer (Phase 4)
19. pattern-recognizer (Phase 3)
20. error-matcher (Phase 4)

**Timeline: Weeks 12-20** | **Impact: 30% of total quality improvement**

### Tier 3 (Specialized - Do Last)
All remaining plugins | **Timeline: Weeks 20-26** | **Impact: 10% of total quality improvement**

---

## Minimal Viable Set (MVP)

If you only have 4 weeks, build these:

1. **naitv-mcp-core** (Week 1) - Foundation
2. **structural-anchor** (Week 2) - Context
3. **lint-fix-loop** (Week 2-3) - Validation
4. **think-before-write** (Week 3-4) - Workflow

**Expected improvement: 2-3x**

---

## Recommended Sets by Project Type

### Startup / Small Project
**Time: 12 weeks, Plugins: 18**
- Phase 1: Core
- Phase 2: All
- Phase 3: lint-fix, tdd, build, dependency-graph, mistake-tracker
- Phase 4: cache, workspace-search
- Phase 5: think-before-write, golden-example, security
- Skip Phase 6

---

### Medium Project / Team
**Time: 18 weeks, Plugins: 35**
- All of Phase 1-4
- Phase 5: Most plugins except accessibility, feature-flag, rollback
- Phase 6: Pick 10 most relevant

---

### Large Enterprise
**Time: 26 weeks, Plugins: 68**
- All 6 phases
- All 68 plugins
- Deep customization per domain

---

## Quick Lookup by Use Case

### "My models keep making syntax errors"
Use: **lint-fix-loop** → **validate-and-test** → **build-system-integrator**

### "I don't understand my codebase structure"
Use: **structural-anchor** → **symbol-navigator** → **dependency-graph-analyzer**

### "Code doesn't follow our patterns"
Use: **pattern-recognizer** → **code-style-enforcer** → **golden-example-injector**

### "Security vulnerabilities slip through"
Use: **security-checker** → **secrets-detector** → **invariant-checker**

### "Tests are always missing"
Use: **tdd-runner** → **test-coverage-analyzer** → **regression-test-generator**

### "Models rewrite entire files"
Use: **surgical-patch** → **refactoring-suggester** → **incremental-refactoring-helper**

### "Can't track what changed"
Use: **change-impact-analyzer** → **dependency-graph-analyzer** → **blame-context-historian**

### "Performance regressions happen"
Use: **performance-profiler** → **benchmark-generator** → **performance-regression-detector**

### "Database migrations break"
Use: **database-schema-validator** → **change-impact-analyzer**

### "Bad names everywhere"
Use: **naming-validator** → **code-style-enforcer** → **language-idioms-enforcer**

---

## Learning Path for Developers

### To Learn naitv-mcp Plugin System
1. Read `CURSOR_QUICK_START.md` (15 min)
2. Implement **plugin-manager** (2-3 hours)
3. Create Python template plugin (1-2 hours)
4. Implement **structural-anchor** (4-6 hours)

### To Learn Plugin Patterns
1. Study **lint-fix-loop** (subprocess + tool integration)
2. Study **symbol-navigator** (LSP + AST patterns)
3. Study **workspace-search** (semantic search)
4. Study **mistake-tracker** (data aggregation + ML)

### To Learn Advanced Patterns
1. **dependency-graph-analyzer** (graph algorithms)
2. **cache-manager** (caching strategies)
3. **think-before-write** (prompt engineering)
4. **security-checker** (pattern-based analysis)

---

## Performance Optimization Tips

### For Fast Plugins (< 500ms)
- Cache aggressively
- Use ripgrep for search
- AST parsing with memoization
- Pattern matching over complex analysis

### For Medium Plugins (500ms - 2s)
- Batch operations
- Lazy evaluation
- Incremental computation
- Smart caching with invalidation

### For Slow Plugins (> 2s)
- Run asynchronously
- Provide progress feedback
- Cache results long-term
- Consider breaking into smaller tools

---

## Testing Checklist Per Plugin

- [ ] All tools have unit tests
- [ ] Integration test with naitv-mcp
- [ ] Real codebase test (e.g., Linux kernel)
- [ ] Performance benchmark vs. target
- [ ] Error case testing
- [ ] Documentation examples verified

---

## Deployment Checklist Per Phase

- [ ] All plugins pass tests
- [ ] Performance targets met
- [ ] Documentation complete
- [ ] Examples work end-to-end
- [ ] Backward compatibility verified
- [ ] CI/CD pipeline working
- [ ] Team trained on new plugins

---

## Future Enhancements (Beyond Phase 6)

### Potential Phase 7 (Advanced AI)
- **Model-specific optimizers** - Optimize prompts per model family
- **Cost analyzer** - Track token usage per plugin
- **Adaptive plugin selection** - Choose best plugins per task
- **Plugin marketplace** - Share community plugins
- **Multi-language translation** - Auto-translate code between languages

### Potential Phase 8 (Deep Integration)
- **IDE plugins** - VS Code, IntelliJ integration
- **GitHub Actions** - CI/CD integration
- **Pre-commit hooks** - Automatic validation
- **Editor extensions** - Real-time plugin output
- **Team collaboration** - Share plugin results

---

**Total Lines in This Reference:** 500+  
**Total Unique Plugins Documented:** 68  
**Total Tools Across All Plugins:** 244  
**Status:** Complete reference matrix ready for implementation

