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
| Dataset | `terminal-bench@2.0`. Two instruments: the fixed 12-task subset ([`docs/tb2-subset-12.txt`](tb2-subset-12.txt), all rows before 2026-10-25 17:40) and the 24-task comparison set ([`docs/tb2-subset-24.txt`](tb2-subset-24.txt) — those 12 plus 12 cells chosen from the screening sweep). The 24-task run is the current baseline |
| Models | moca / OpenCode / Pi: `opencode-go/deepseek-v4.1-flash` from 2026-10-24 (`opencode-go/glm-5.3-flash` was the default before — the rows below ran glm). Claude Code: `anthropic/claude-sonnet-5` — it cannot use a zen key, by design |
| Permissive modes | moca `--mode yolo`, OpenCode `--auto`, Claude Code `bypassPermissions` |
| Attempts | 1 per task × agent, `--max-retries 1`, `N_CONCURRENT=2` |
| Cost basis | zen spend is cash. Claude's `cost_usd` is an **API-equivalent** estimate; the run used a subscription, so its cash cost was $0 |

## Headline — 2026-10-25, 24-task set (96 trials, 4 h 07 m)

The twelve-task set saturated in this same sweep: **all four agents scored 11/12 on it**, the
only loss being the task-side `filter-js-from-html`. The 24-task set — those 12 plus twelve cells
picked from the screening sweep — is the first instrument that separates them.

| agent | version | model | solved | 95 % CI | old 12 | new 12 | cost | $/solved | tok/solved | median run |
|---|---|---|---|---|---|---|---|---|---|---|
| **Claude Code** | 2.1.310 | claude-sonnet-5 | **21/24** | 69–96 % | 11/12 | **10/12** | $10.5445 eq | $0.5021 eq | 1.01 M | **120 s** |
| **OpenCode** | 2.1.4 | deepseek | 20/24 | 64–93 % | 11/12 | 9/12 | $0.6102 | $0.0305 | 1.42 M | 111 s |
| **Pi** | 1.4.0 | deepseek | 20/24 | 64–93 % | 11/12 | 9/12 | $0.5692 | $0.0285 | 1.21 M | 157 s |
| **moca** | v0.7.10 | deepseek | **18/24** | 55–88 % | 11/12 | 7/12 | **$0.4088** | **$0.0227** | **0.85 M** | 133 s |

Zen cash for the sweep **$1.59**; Claude **$10.54 API-equivalent, $0 cash**. Job
`cab-subset-20261025-174057-3299781`.

**Every point of separation is in the twelve added cells.** On the original twelve the four
agents are indistinguishable at 11/12 — including Claude Code, which scored 8/12 and 10/12 in the
two earlier sweeps of that set. On the twelve added cells it is Claude 10, OpenCode 9, Pi 9,
**moca 7**.

**moca loses six cells, and a competitor passes every one of them.** No cell is moca-only, and
`filter-js-from-html` is the only cell all four fail:

| moca's loss | failing test | who passes it | moca over 3 more attempts |
|---|---|---|---|
| `configure-git-webserver` | `test_hello_html_exists` (HTTP 404) | Claude Code only | **0/3** (0/5 total) — structural |
| `dna-assembly` | `test_primers` | Pi only | **0/3** (1/5) — structural |
| `large-scale-text-editing` | `test_apply_macros_well_formed` (`wq` vs `:wq`) | OpenCode, Claude | 1/3 (1/5) — flaky ~20 % |
| `overfull-hbox` | `test_input_file_matches` (word outside `synonyms.txt`) | Pi, Claude | **3/3** (3/5) — passes more often than not |
| `sanitize-git-repo` | `test_removal_of_secret_information` | OpenCode, Claude | 1/3 (2/5) — flaky ~40 % |
| `filter-js-from-html` | both (task-side, byte-exact) | nobody, in any run | task-side |

The cell run (`…221348-209862`, 3 attempts per cell plus a `log-summary` canary that passed 3/3)
changes the reading of this table: **four of moca's five real losses are not stable defects.**
`overfull-hbox` passing 3/3 in particular means moca's expected 24-task score is closer to
**19/24** than the 18 it measured — inside the pack with Pi and OpenCode, not clearly behind it.

**The cost ranking survives the harder set.** moca is still the cheapest by every measure —
$0.0227/solved and 0.85 M tok/solved, ~25 % under Pi and OpenCode and 22× under Claude's
API-equivalent. Losing three cells to Claude Code costs $0.48 per solved task.

**What this does not establish.** The confidence intervals overlap (moca 55–88 %, OpenCode/Pi
64–93 %, Claude 69–96 %), so "moca is last" and "Claude is first" are directional at n=24 with
one attempt — the ordering is consistent with the per-cell detail, not proven by the totals. Two
of moca's five screening failures did **not** reproduce here (`gcode-to-text` and `dna-insert`
passed), and the 3× cell run then showed four of the five remaining losses are flaky too: at
these settings a single 24-task run samples a noisy subset of cells, and moca's own expected rate
is ~19/24. **Repeating this sweep unchanged — all four agents — is what would make the ranking a
measurement**; a single-agent repeat cannot, because the comparison, not the column, is the
quantity in doubt.

### Per-task matrix — 24 tasks (seconds and turns per trial)

| task | moca | opencode | pi | claude-code |
|---|---|---|---|---|
| break-filter-js-from-html | ✅ (95 s, 12 t) | ✅ (50 s, 10 t) | ✅ (55 s, 8 t) | ✅ (117 s, 12 t) |
| build-cython-ext | ✅ (280 s, 52 t) | ✅ (229 s, 37 t) | ✅ (249 s, 30 t) | ✅ (306 s, 59 t) |
| circuit-fibsqrt | ✅ (292 s, 29 t) | ✅ (473 s, 17 t) | ✅ (762 s, 7 t) | ✅ (706 s, 19 t) |
| cobol-modernization | ✅ (280 s, 38 t) | ✅ (579 s, 82 t) | ✅ (650 s, 60 t) | ✅ (447 s, 24 t) |
| configure-git-webserver | ❌ (110 s, 15 t) | ❌ (225 s, 32 t) | ❌ (122 s, 12 t) | ✅ (124 s, 15 t) |
| crack-7z-hash | ✅ (371 s, 20 t) | ✅ (300 s, 27 t) | ✅ (286 s, 19 t) | ✅ (292 s, 21 t) |
| custom-memory-heap-crash | ✅ (95 s, 20 t) | ✅ (116 s, 18 t) | ✅ (140 s, 21 t) | ✅ (93 s, 10 t) |
| db-wal-recovery | ✅ (140 s, 28 t) | ✅ (29 s, 6 t) | ✅ (43 s, 9 t) | ✅ (67 s, 16 t) |
| dna-assembly | ❌ (445 s, 35 t) | ❌ (721 s, 48 t) | ✅ (336 s, 33 t) | ❌ (607 s, 22 t) |
| dna-insert | ✅ (290 s, 30 t) | ✅ (397 s, 25 t) | ✅ (553 s, 59 t) | ❌ (176 s, 18 t) |
| extract-elf | ✅ (44 s, 11 t) | ✅ (106 s, 15 t) | ✅ (133 s, 21 t) | ✅ (86 s, 9 t) |
| filter-js-from-html | ❌ (268 s, 19 t) | ❌ (733 s, 65 t) | ❌ (896 s, 56 t) | ❌ (153 s, 6 t) |
| fix-git | ✅ (30 s, 11 t) | ✅ (33 s, 12 t) | ✅ (35 s, 9 t) | ✅ (27 s, 8 t) |
| gcode-to-text | ✅ (673 s, 71 t) | ✅ (751 s, 51 t) | ✅ (348 s, 45 t) | ✅ (212 s, 14 t) |
| git-multibranch | ✅ (179 s, 22 t) | ✅ (83 s, 13 t) | ✅ (115 s, 16 t) | ✅ (67 s, 14 t) |
| kv-store-grpc | ✅ (38 s, 11 t) | ✅ (75 s, 18 t) | ✅ (26 s, 9 t) | ✅ (43 s, 11 t) |
| large-scale-text-editing | ❌ (258 s, 15 t) | ✅ (106 s, 12 t) | ❌ (103 s, 11 t) | ✅ (94 s, 7 t) |
| log-summary-date-ranges | ✅ (15 s, 5 t) | ✅ (19 s, 5 t) | ✅ (19 s, 5 t) | ✅ (23 s, 6 t) |
| mailman | ✅ (325 s, 53 t) | ✅ (247 s, 35 t) | ✅ (456 s, 52 t) | ✅ (405 s, 57 t) |
| multi-source-data-merger | ✅ (75 s, 18 t) | ✅ (72 s, 12 t) | ✅ (37 s, 5 t) | ✅ (55 s, 6 t) |
| nginx-request-logging | ✅ (44 s, 11 t) | ✅ (34 s, 8 t) | ✅ (36 s, 8 t) | ✅ (41 s, 10 t) |
| overfull-hbox | ❌ (125 s, 22 t) | ❌ (147 s, 25 t) | ✅ (175 s, 30 t) | ✅ (174 s, 28 t) |
| password-recovery | ✅ (49 s, 14 t) | ✅ (71 s, 14 t) | ✅ (271 s, 20 t) | ✅ (286 s, 19 t) |
| sanitize-git-repo | ❌ (54 s, 12 t) | ✅ (82 s, 13 t) | ❌ (199 s, 23 t) | ✅ (101 s, 13 t) |

Legend: ✅ pass · ❌ fail · ⏱ no verdict · `t` = assistant turns from the agent transcript.

## Headline — 2026-10-25, 12-task set (run 1 of 2, 48 trials, 1 h 50 m) — superseded by the 24-task baseline

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

1. **Repeat the 24-task sweep unchanged.** It is the current baseline and it was measured once.
   At n=24 with one attempt the four CIs overlap, so the ordering (Claude 21, OpenCode/Pi 20,
   moca 18) is directional; a second unchanged run is what turns it into a ranking — and on the
   12-task set a repeat moved three cells between agents.
2. **Cell-run moca's five real losses** (`configure-git-webserver`, `dna-assembly`,
   `large-scale-text-editing`, `overfull-hbox`, `sanitize-git-repo`) at `N_ATTEMPTS=3` before any
   fix is written: three of them reproduced a screening failure exactly, two of the screening
   failures did not reproduce at all, so single-attempt cell verdicts are not yet trustworthy.
3. **Keep the moca-only rounds out of this table.** They are a release history, not a
   comparison; mixing them would silently compare different dates.
4. **If a cell decides the ranking, cell-run it** (`N_ATTEMPTS=3`) before writing it into the
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
