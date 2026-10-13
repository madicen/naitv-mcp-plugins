# Thin wrappers over scripts/ — see testing/PLUGIN_HARNESS.md
.PHONY: help test test-all test-plugin test-go test-harness \
	l4 perf eval-baseline eval-treatment ablation cross-plugin

# Prefer repo venv when present (CI/local harness deps).
PYTHON ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)
PLUGIN ?=
AGENT ?= stub
SUITE ?= navigation
SEEDS ?= 3
HELD_OUT ?= 0

help: ## Show targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

test: test-all ## Alias for test-all

test-all: ## Catalog L1–L3 for every plugins/*/plugin.json
	./scripts/test_all.sh

test-plugin: ## L1–L3 for one plugin: make test-plugin PLUGIN=structural-anchor
	@test -n "$(PLUGIN)" || (echo "usage: make test-plugin PLUGIN=<name>" >&2; exit 2)
	./scripts/test.sh "$(PLUGIN)"

test-go: ## Go helper unit tests (structural-anchor + symbol-navigator)
	(cd tools/structural-anchor/go_symbols && go test ./...)
	(cd tools/symbol-navigator/go_nav && go test ./...)

test-harness: ## Shared harness unit tests + cross-plugin check
	$(PYTHON) -m pytest testing/integration/test_manifest_layout.py testing/perf/tests testing/eval/tests -q
	$(PYTHON) testing/integration/cross_plugin_check.py

cross-plugin: ## Unique tool names + exec path hygiene
	$(PYTHON) testing/integration/cross_plugin_check.py

l4: ## L4 MCP integration: make l4 PLUGIN=structural-anchor
	@test -n "$(PLUGIN)" || (echo "usage: make l4 PLUGIN=<name>" >&2; exit 2)
	./scripts/l4.sh "$(PLUGIN)"

perf: ## L3 50k perf: make perf PLUGIN=structural-anchor
	@test -n "$(PLUGIN)" || (echo "usage: make perf PLUGIN=<name>" >&2; exit 2)
	./scripts/perf.sh "$(PLUGIN)"

eval-baseline: ## L5 baseline (AGENT=stub|ollama SUITE=navigation SEEDS=3)
	HELD_OUT=$(HELD_OUT) AGENT=$(AGENT) SUITE=$(SUITE) SEEDS=$(SEEDS) ./scripts/eval.sh baseline

eval-treatment: ## L5 treatment + compare (needs baseline for navigation)
	HELD_OUT=$(HELD_OUT) AGENT=$(AGENT) SUITE=$(SUITE) SEEDS=$(SEEDS) ./scripts/eval.sh treatment

ablation: ## Leave-one-out ablation (stub; needs naitv-mcp)
	$(PYTHON) testing/eval/run_ablation.py --suite $(SUITE) --seeds $(SEEDS)
