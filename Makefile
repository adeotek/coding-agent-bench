SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help setup doctor test probe dry-run smoke subset full render report view net-view prune

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s %s\n", $$1, $$2}'

setup: ## install Harbor (pinned) + check docker
	./scripts/bench.sh setup

doctor: ## check docker/harbor/adapter/credentials (ARGS=--probe for live probes)
	./scripts/bench.sh doctor $(ARGS)

test: ## harness unit test: the moca run line + session mirror (no spend, needs the harbor tool env)
	PYTHONPATH="$(CURDIR)" "$$(uv tool dir)/harbor/bin/python" test/moca_run_command_test.py

probe: ## live credential probes (one tiny request per agent)
	./scripts/bench.sh probe

dry-run: ## validate the rendered job config (ARGS=smoke|subset|full, default subset)
	./scripts/bench.sh dry-run $(or $(ARGS),subset)

smoke: ## run the hello-world task across all agents (pipeline + auth check)
	./scripts/bench.sh run smoke

subset: ## run the Terminal-Bench 2.0 subset (N_TASKS=20 default)
	./scripts/bench.sh run subset

full: ## run full Terminal-Bench 2.0 (expensive: time, tokens, disk)
	./scripts/bench.sh run full

render: ## render the effective config to results/ and print its path
	./scripts/bench.sh render $(or $(ARGS),subset)

report: ## re-derive report tables from results/jobs (ARGS="runs" | "summary <job>" | "matrix <job>…")
	python3 scripts/bench_report.py $(or $(ARGS),runs)

view: ## browse job results in the web viewer (bound to 127.0.0.1)
	./scripts/bench.sh view

net-view: ## browse job results bound to 0.0.0.0 (LAN access; the viewer has no auth)
	./scripts/bench.sh view --host 0.0.0.0

prune: ## reclaim docker disk (image + system prune)
	./scripts/bench.sh prune
