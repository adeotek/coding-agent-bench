# Pre-registration — v0.7.12 truncation retest (2026-10-30)

Written **before** the run, committed with the pin. Its purpose is to stop the next paragraph
("4/10, meaning…") from being written after the fact, which is how the v0.7.11 reward claim survived a
day longer than it should have.

- **Cell:** `regex-chess` — the cell that motivated the truncated-turn work and the one both earlier
  arms measured at k=10.
- **Arms:** v0.7.12 at `N_ATTEMPTS=10`, moca only. Baselines already in the job store, no re-spend:
  v0.7.11 `cab-subset-20261028-135325-3120017` (2/10, 8/10 ended on a truncation) and v0.7.10
  `cab-subset-20261028-145731-3210350` (2/10, 8/10).
- **Command:** `AGENTS=moca N_ATTEMPTS=10 TASK_NAMES=regex-chess ./scripts/bench.sh run subset -y --max-retries 1`

## Hypothesis

v0.7.12 raises the per-turn output ceiling on the retry (`min(model limit, context.reserveTokens) ×
2^attempt`, capped at the model's own limit) and allows three rescues per run, reset by any tool call. If
the v0.7.11 failures were the 16 384-token ceiling cutting a thought short — as the k=10 sessions suggest
(truncating turns are thinking-only, the retry truncating again 0–4 tool calls later) — then a v0.7.12
trial should no longer **end** on a truncation. Whether the cell is solvable is a separate question.

## Metrics, fixed now

**Primary — survival** (share of trials whose run ends on a truncation, i.e. `response truncated` and
exit 1 with the bound warning):

| outcome | Fisher, two-sided vs 8/10 | reading |
|---|---|---|
| ≤ 2/10 | p = 0.023 | mechanism supported |
| 3/10 | p = 0.07 | suggestive, not confirmed |
| ≥ 4/10 | p ≥ 0.21 | not supported |

**Secondary — reward** (solved trials), baseline 2/10 on both arms: only **≥ 8/10** reaches p = 0.023
(5/10 is p = 0.35). **The reward metric cannot decide this cell at n=10**, and no reward difference below
8/10 will be written up as an improvement — it will be reported as a number and called noise.

**Descriptive, no decision attached:** tool calls per trial, the ceiling actually used (the session logs
`retry N of 3 at M output tokens`), cost, and how each run ended (step budget vs truncation bound vs
verifier).

## What would count as a defect in v0.7.12

- Every attempt carries the same `max_tokens` — the escalation never happens (implementation bug).
- Bound hits stay above 4/10 **with** `retry 3 of 3` in the logs — the ceiling is not the binding
  constraint, and the next lever is not another ceiling bump.
- A run truncating at the top of the escalation (131 072 output tokens) — that is runaway output, not a
  short ceiling, and the answer is the output-splitting guidance rather than more room.

## Reporting

Numbers come from `scripts/bench_report.py` over `results/jobs/`, never from a run log by hand. Both
reports (`docs/moca-bench-report.md`, `docs/agents-bench-report.md`) get the result in the same commit as
the job that produced it, including a negative one.
