# moca vs Claude Code vs OpenCode vs Pi — Terminal-Bench 2.0 subset

Four agents, one fixed task set, one Docker sandbox, the task's own verifier. This is the
cross-agent view; the release-by-release moca history is in
[`moca-bench-report.md`](moca-bench-report.md).

> **This is a snapshot, not a live ranking.** The only four-agent sweep is the 2026-10-16 job
> (`cab-subset-20261016-004433`). Since then only moca has been re-run — five times — and it
> moved from 6/12 to 10/12 and back to 8/12 (see the moca report). The other three agents have
> not been measured since. Treat the table below as *what the field looked like at those pins*;
> the current-pin comparison is the run this report is waiting for.

## Protocol

| | |
|---|---|
| Dataset | `terminal-bench@2.0`, the fixed 12-task subset in [`docs/tb2-subset-12.txt`](tb2-subset-12.txt) |
| Models | moca / OpenCode / Pi: `opencode-go/deepseek-v4.1-flash` from 2026-10-24 (`opencode-go/glm-5.3-flash` was the default before — the rows below ran glm). Claude Code: `anthropic/claude-sonnet-5` — it cannot use a zen key, by design |
| Permissive modes | moca `--mode yolo`, OpenCode `--auto`, Claude Code `bypassPermissions` |
| Attempts | 1 per task × agent, `--max-retries 1`, `N_CONCURRENT=2` |
| Cost basis | zen spend is cash. Claude's `cost_usd` is an **API-equivalent** estimate; the run used a subscription, so its cash cost was $0 |

## Headline — 2026-10-25, four agents (run 1 of 2, 48 trials, 1 h 50 m)

Every pin moved since the 10-16 sweep and the three zen agents changed model, so this table is
a **new baseline**, not a delta on the one below it. Same 12 tasks, 1 attempt, same sandbox,
moca at 250 steps.

| agent | version | model | solved | rate (95 % CI) | cost | $/solved | tok/solved | median agent run |
|---|---|---|---|---|---|---|---|---|
| **moca** | v0.7.10 | deepseek-v4.1-flash | **11/12** | 92 % (65–99 %) | **$0.2142** | **$0.0195** | 0.77 M | **65 s** |
| **Pi** | 1.4.0 | deepseek-v4.1-flash | **11/12** | 92 % (65–99 %) | $0.2169 | $0.0197 | **0.72 M** | 68 s |
| **OpenCode** | 2.1.4 | deepseek-v4.1-flash | **11/12** | 92 % (65–99 %) | $0.3908 | $0.0355 | 1.66 M | 107 s |
| **Claude Code** | 2.1.310 | claude-sonnet-5 | 8/12 | 67 % (39–86 %) | $5.3576 equiv ($0 cash) | $0.6697 equiv | 1.50 M | 135 s |

Zen spend for the sweep: **$0.82** cash. Claude: **$5.36 API-equivalent, $0 cash**.

The three zen agents are **indistinguishable at one attempt** — 11/12 each, same single loss
— so the run was repeated; the hold study below is what this report's ranking should be read
from. What survives both runs is cost and speed: moca and Pi solve a task for ~$0.017–0.023
and ~65 s, OpenCode for ~$0.026–0.036 and ~100 s, Claude Code for 25–35× that (API-equivalent)
and twice the wall clock. Claude Code's 8/12 here is a low draw, not a level: two of its four
losses are cells it wins in run 2.

**What this sweep cannot say.** Three variables moved for the zen agents at once (release,
model, and moca's step budget), and each agent's delta is measured against a sweep that ran a
different model. Nothing here attributes a cell to an agent's code. The per-cell picture:

| task | moca | opencode | pi | claude-code |
|---|---|---|---|---|
| build-cython-ext | ✅ (270 s) | ✅ (223 s) | ✅ (252 s) | ✅ (285 s) |
| cobol-modernization | ✅ (472 s) | ✅ (315 s) | ✅ (367 s) | ✅ (369 s) |
| custom-memory-heap-crash | ✅ (140 s) | ✅ (207 s) | ✅ (88 s) | ✅ (375 s) |
| db-wal-recovery | ✅ (24 s) | ✅ (113 s) | ✅ (16 s) | ❌ (138 s) |
| extract-elf | ✅ (70 s) | ✅ (100 s) ⚠️ | ✅ (115 s) | ❌ (131 s) |
| filter-js-from-html | ❌ (259 s) | ❌ (1800 s) ⚠️ | ❌ (517 s) | ❌ (181 s) |
| fix-git | ✅ (18 s) | ✅ (26 s) | ✅ (27 s) | ❌ (21 s) |
| kv-store-grpc | ✅ (35 s) | ✅ (31 s) | ✅ (32 s) | ✅ (33 s) |
| log-summary-date-ranges | ✅ (27 s) | ✅ (13 s) | ✅ (15 s) | ✅ (22 s) |
| mailman | ✅ (375 s) | ✅ (286 s) | ✅ (354 s) | ✅ (396 s) |
| multi-source-data-merger | ✅ (34 s) | ✅ (43 s) | ✅ (47 s) | ✅ (47 s) |
| nginx-request-logging | ✅ (60 s) | ✅ (35 s) | ✅ (23 s) | ✅ (39 s) |

⚠️ = the trial recorded an agent-phase exception. Both here are reward-1.0 trials with
`NonZeroAgentExitCodeError` alongside (OpenCode's known sporadic exit 1 after a clean final
message); `filter-js`'s 1800 s is that trial burning both the agent and verifier budgets on a
task no agent can pass.

**Task-side cell.** `filter-js-from-html` is now 0/17 across four agents, two models and three
rounds, and the failure is not a near miss: `test_clean_html_unchanged` compares output against
parser re-serialisation byte-for-byte (indentation, `\n\n` after the doctype, `&copy;` vs `©`),
so a semantically perfect filter fails. Its verifier also hangs — two of the three diagnostic
attempts produced no verdict at all. Report it as `11/11` and `11/12` beside each other.

## Hold study — 2026-10-25, run 2 (identical settings, 2 h 09 m)

Same 12 tasks, same pins, same model, 1 attempt, max-retries 1 — nothing changed between runs
except the clock. Job `cab-subset-20261025-100949-2263993`.

| agent | run 1 | run 2 | combined | cost (r1 → r2) | $/solved | median run |
|---|---|---|---|---|---|---|
| **moca** | 11/12 | **11/12** | **22/24** | $0.2142 → $0.1826 | **$0.0166–0.0195** | 65 s |
| **Pi** | 11/12 | **11/12** | **22/24** | $0.2169 → $0.2513 | $0.0197–0.0228 | 68 s |
| **OpenCode** | 11/12 | 10/12 | 21/24 | $0.3908 → $0.2599 | $0.0260–0.0355 | 107 s |
| **Claude Code** | 8/12 | 10/12 | 18/24 | $5.3576 → $5.7116 eq | $0.5712–0.6697 eq | 126–135 s |

**45 of 48 cells returned the same verdict.** All three flips were outside moca: `extract-elf`
and `fix-git` flipped **to** Claude Code, `kv-store-grpc` flipped **away from** OpenCode.
moca's column was identical across both runs (11 passes, `filter-js` lost), and so was Pi's.

What that changes:

- **The moca/Pi tie is real; the three-way tie was a single-attempt artefact.** OpenCode is half
  a cell behind over 24 trials, and it is the agent that lost a cell nobody else lost.
- **Claude Code's 18/24 is the honest number, and its spread is the widest in the study** (8–10
  per run). Two of its four run-1 losses were wins in run 2, so the earlier "it dropped from
  10/12" read was noise. Its stable losses are `db-wal-recovery` and `filter-js`, both runs.
- **`filter-js-from-html` is 0/8 here and 0/25 lifetime** across four agents, two models and
  four rounds. Nothing about the hold study touches it: it is a task-side cell.
- **Rate limiting is a live threat to concurrent zen legs.** One trial (`opencode`,
  `extract-elf`) recorded `ApiRateLimitError` — reward 1.0 anyway — and the run took 19 min
  longer than run 1. A four-agent sweep hits one endpoint with four sandboxes at once; stagger
  the legs or space them out if it starts costing cells.

**This is the first pair of runs in the repo that can measure agent variance**, because nothing
but time changed. Two runs is two samples: enough to see that moca and Pi are stable, not enough
to put a confidence interval on any agent's true rate.

### The model change was worth more than the release — measured, not assumed

The 10-25 sweep switched the three zen agents from `glm-5.3-flash` to `deepseek-v4.1-flash`
while every pin also moved, which is why its table is labelled a new baseline. A moca-only leg
isolates the model at fixed release and budget (v0.7.10, 250 steps, same 12 tasks):

| moca leg | model | steps | score |
|---|---|---|---|
| v0.7.4 | glm-5.3-flash | 100 | 8/12 |
| v0.7.4 | glm-5.3-flash | 250 | 7/12 → **10/12** when its four cells were repeated 3× |
| v0.7.10 | glm-5.3-flash | 250 | 9/12 |
| v0.7.10 | deepseek-v4.1-flash | 250 | **11/12** (twice, identical cells) |

The single-attempt legs **cannot** split the +3: the 250-step glm leg lost two cells that repeated
3/3 and 3/3 at its own settings, i.e. a leg moves ±2–3 cells on a twelve-cell set. What survives
is the endpoint (8/12 → 11/12), the model's steadiness (two identical runs) and its economics
(one-fifth the cost per solved task), and the budget's tail-cost effect (one 246-turn, $0.43
attempt). Read the cross-agent table with that in mind: the jump from the 10-16 rows is mostly a
**model** change, not an agent change — which is also the fairest reading of OpenCode's and Pi's
gains. Full detail, including the retraction, in
[`docs/moca-bench-report.md`](moca-bench-report.md#attribution--what-the-legs-support-and-what-they-do-not).

## Headline — 2026-10-16, four agents (superseded: glm at 100 steps)

| agent | version | model | solved | rate (95 % CI) | cost | $/solved | tok/solved | median agent run |
|---|---|---|---|---|---|---|---|---|
| **Pi** | 1.3.0 | glm-5.3-flash | **11/12** | 92 % (65–99 %) | $0.5204 | $0.0473 | 1.02 M | 97 s |
| **OpenCode** | 2.0.30 | glm-5.3-flash | **10/12** | 83 % (55–95 %) | **$0.2965** | **$0.0296** | **0.59 M** | 156 s |
| **Claude Code** | 2.1.301 | claude-sonnet-5 | **10/12** | 83 % (55–95 %) | $5.6804 equiv ($0 cash) | $0.5680 equiv | 1.26 M | 108 s |
| **moca** | v0.5.1-beta | glm-5.3-flash | 6/12 | 50 % (25–75 %) | $0.3082 | $0.0514 | 1.27 M | **46 s** |

Zen spend for the whole sweep: **$1.13** cash. Claude: **$5.68 API-equivalent, $0 cash**.

The 2026-10-11 three-agent run on the same tasks, for the record:

| agent | version | solved | cost | $/solved |
|---|---|---|---|---|
| Claude Code | 2.1.296 | 11/12 | $4.6538 equiv | $0.4231 |
| moca | v0.3.0-beta | 10/12 | $0.1886 | $0.0189 |
| Pi | 1.1.0 | 9/12 | $0.4295 | $0.0477 |

## Per-task matrix — 2026-10-16 (historical)

| task | moca | opencode | pi | claude-code |
|---|---|---|---|---|
| build-cython-ext | ✅ (294 s) | ✅ (289 s) | ✅ (255 s) | ✅ (296 s) |
| cobol-modernization | ❌ (198 s) | ✅ (468 s) | ✅ (900 s) ⚠️ | ✅ (302 s) |
| custom-memory-heap-crash | ❌ (337 s) | ✅ (361 s) | ✅ (474 s) | ✅ (502 s) |
| db-wal-recovery | ❌ (35 s) | ✅ (137 s) | ✅ (107 s) | ✅ (53 s) |
| extract-elf | ✅ (150 s) | ✅ (175 s) ⚠️ | ✅ (88 s) | ✅ (159 s) |
| filter-js-from-html | ❌ (53 s) | ❌ (570 s) | ❌ (1205 s) | ❌ (241 s) |
| fix-git | ✅ (22 s) | ✅ (28 s) | ✅ (29 s) | ❌ (18 s) |
| kv-store-grpc | ✅ (20 s) | ❌ (67 s) | ✅ (26 s) | ✅ (42 s) |
| log-summary-date-ranges | ❌ (39 s) | ✅ (19 s) | ✅ (17 s) | ✅ (24 s) |
| mailman | ❌ (289 s) ⚠️ | ✅ (362 s) | ✅ (891 s) | ✅ (400 s) |
| multi-source-data-merger | ✅ (29 s) | ✅ (48 s) | ✅ (43 s) | ✅ (57 s) |
| nginx-request-logging | ✅ (26 s) | ✅ (32 s) | ✅ (31 s) | ✅ (40 s) |

⚠️ = the trial recorded an agent-phase exception. `pi`/`cobol` and `opencode`/`extract-elf` are
reward-1.0 trials with an exception alongside; `moca`/`mailman` is a genuine exit-3 wrap-up.

**One cell nobody passes:** `filter-js-from-html` (0/4). Across all runs to date it is 0 in
14+ attempts over four agents and two models — a task-side contradiction, not an agent
signal (see the moca report for the test-source audit).

**One cell separates the field:** `kv-store-grpc` — only OpenCode misses it, and it does so
for a specific reason (below).

## Efficiency

| agent | input tokens (incl. cache) | output tokens | $/solved | tok/solved | median agent run | median trial (incl. install) |
|---|---|---|---|---|---|---|
| moca | 7.63 M | 61.0 K | $0.0514 | 1.27 M | **46 s** | 118 s |
| opencode | 5.90 M | 47.7 K | **$0.0296** | **0.59 M** | 156 s | 222 s |
| pi | 11.17 M | **238.6 K** | $0.0473 | 1.02 M | 97 s | 144 s |
| claude-code | 12.61 M | 171.6 K | $0.5680 equiv | 1.26 M | 108 s | 173 s |

- **OpenCode is the cost/efficiency leader** on this subset — fewest tokens per solved task
  and the lowest $/solved, with the slowest median run (it iterates long on its two losses).
- **moca is the fastest per run** — it fails fast and succeeds fast — and was the most
  expensive zen agent per solved task *at this pin*, because it failed twice as often at a
  similar token volume.
- **Pi buys accuracy with output tokens**: 238 K output, 5× OpenCode's, and 11.2 M input.
  It still lands at $0.047/solved because output is cheap on this model.
- **Claude Code is 19× OpenCode's $/solved** on API-equivalent pricing. On a subscription the
  cash is $0, which is the only reason that ratio is acceptable; the token profile (~97 %
  cache reads) is the harness's, not the model's.

## Failure taxonomy

**moca (6/12) — behaviour, not capability, and mostly since fixed.** The v0.5.1 round was the
bottom of its regression: cobol and db-wal were *false success claims* (asserted recovery that
the verifier disproved), log-summary "fixed" working scaffolding (scope creep), custom-memory
fixed the debug build but never ran the release path, and mailman spent all 100 steps on
reconnaissance and wrapped up with a setup plan. The fixes that followed are documented in the
moca report: the effort-map/endpoint fix, the working-style rules, the stateful-file guard and
the delivery rule moved it 6 → 7 → 10 → 8 (v0.7.4) across the next five rounds.

**opencode (10/12) — one missing server, one shared task.** `kv-store-grpc` produced the
proto, generated code and a server file (5/7 verifier tests) but left **no listening gRPC
server** — connection refused on `127.0.0.1:5328`. `extract-elf` passed (reward 1.0) while
`opencode run` exited 1 after a clean event stream — a v2 headless-exit quirk, retried once,
work intact.

**pi (11/12) — the best result, and its one timeout was on a passing task.**
`cobol-modernization` hit the 900 s agent cap mid-way through its own 30+-case differential
sweep against real GnuCOBOL; the deliverable was already complete and the verifier scored 1.0.
`filter-js` is its only real loss (1205 s of iteration, still byte-preserving).

**claude-code (10/12) — a headless-mode behaviour loss.** On `fix-git` it recovered the
dangling reflog commit, hit the genuine content conflict, then **asked the user which side to
keep and ended the turn**. Headless has no user, so the merge stayed unresolved. It solved the
same task in 45 s the week before. `filter-js` is the other loss.

**Cross-agent lessons**

1. **A question is a lost cell in headless mode.** Claude's fix-git loss is the cleanest
   example; any agent that can block on an approval or a clarification must be driven in a
   permissive, non-interactive mode (all four are, by protocol) *and* must not ask anyway.
2. **A timeout is not always a failure.** pi's cobol timeout scored 1.0; moca's 900 s kills
   mid-work. Read `verifier_result.rewards.reward` before reading `exception_info`.
3. **Exit codes are not verdicts.** moca exits 3 at its step budget, OpenCode can exit 1 after
   a clean stream, and both can still score 1.0. The verifier decides.
4. **Cache reads dominate every token profile** (~93–95 % of prompt tokens for the zen
   agents, ~97 % for Claude). Compare $/solved and tok/solved, not raw input.
5. **Task-side cells are shared losses.** filter-js (0/4) and nginx's whitespace/placement
   assertions cost every agent the same points; they belong in the task audit, not in a
   ranking.

## What would make this report current

1. **Done — the 2026-10-25 sweep replaced the 10-16 snapshot.** The next thing worth running is
   an attribution leg, not another sweep: one agent at a time, one knob moved (v0.7.10 at
   `glm-5.3-flash`, or v0.7.4 at deepseek), on the same 12 tasks. Nothing in the current table
   says which of pin/model/budget produced the +3 cells.
2. **Keep the moca-only rounds out of this table.** They are a release history, not a
   comparison; mixing them would silently compare different dates.
3. **If a cell decides the ranking, cell-run it** (`N_ATTEMPTS=3`) before writing it into the
   verdict — at n=12 a single flip is inside the noise band.

## Update procedure

After a sweep, in the same commit:

```bash
python3 scripts/bench_report.py summary <job>          # per-agent cost/token/speed
python3 scripts/bench_report.py matrix <job>           # task × agent, with rewards
```

Replace the headline table and matrix with the new sweep (keeping the previous one in a
"history" table), update **Efficiency**, write the per-agent failure paragraphs from the
verifier output, then re-check the **Cross-agent lessons** — a lesson that stops being true
gets corrected, not deleted.
