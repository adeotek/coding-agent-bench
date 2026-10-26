SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help setup doctor test probe dry-run smoke subset full screen render report view net-view prune

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s %s\n", $$1, $$2}'

setup: ## install Harbor (pinned) + check docker
	./scripts/bench.sh setup

doctor: ## check docker/harbor/adapter/credentials (ARGS=--probe for live probes)
	./scripts/bench.sh doctor $(ARGS)

test: ## harness unit tests: moca run line + session mirror, report parsers, harbor pin guard (no spend)
	PYTHONPATH="$(CURDIR)" "$$(uv tool dir)/harbor/bin/python" test/moca_run_command_test.py
	python3 test/bench_report_steps_test.py
	python3 test/bench_report_compare_test.py
	python3 test/bench_report_report_test.py
	python3 test/bench_pin_guard_test.py

probe: ## live credential probes (one tiny request per agent)
	./scripts/bench.sh probe

dry-run: ## validate the rendered job config (ARGS=smoke|subset|full, default subset)
	./scripts/bench.sh dry-run $(or $(ARGS),subset)

smoke: ## run the hello-world task across all agents (pipeline + auth check)
	./scripts/bench.sh run smoke

subset: ## run the Terminal-Bench 2.0 subset (N_TASKS=20 default)
	./scripts/bench.sh run subset

screen: ## moca-only screen of one 10-task batch (BATCH=N) from docs/tb2-screen.txt
	@BATCH=$(or $(BATCH),1); \
	FIRST=$$(( (BATCH-1)*10 + 1 )); LAST=$$(( BATCH*10 )); \
	TASKS=$$(grep -v '^#' docs/tb2-screen.txt | grep -v '^$$' | sed -n "$${FIRST},$${LAST}p" | paste -sd,); \
	echo "screen batch $$BATCH: $$TASKS"; \
	AGENTS=moca N_ATTEMPTS=$${N_ATTEMPTS:-1} TASK_NAMES="$$TASKS" \
		./scripts/bench.sh run subset -y --max-retries 1

full: ## run full Terminal-Bench 2.0 (expensive: time, tokens, disk)
	./scripts/bench.sh run full

render: ## render the effective config to results/ and print its path
	./scripts/bench.sh render $(or $(ARGS),subset)

report: ## tables from results/jobs: ARGS="runs|summary <job>|matrix <job>…|compare <job>…"; JOBS="<job>…" regenerates docs/bench-latest.md
	@if [ -n "$(JOBS)" ]; then \
	  python3 scripts/bench_report.py export $(JOBS) && \
	  python3 scripts/bench_report.py report $(JOBS) --out=docs/bench-latest.md && \
	  echo "report: docs/bench-latest.md"; \
	else python3 scripts/bench_report.py $(or $(ARGS),runs); fi

view: ## browse job results in the web viewer (bound to 127.0.0.1)
	./scripts/bench.sh view

net-view: ## browse job results bound to 0.0.0.0 (LAN access; the viewer has no auth)
	./scripts/bench.sh view --host 0.0.0.0

prune: ## reclaim docker disk (image + system prune)
	./scripts/bench.sh prune
