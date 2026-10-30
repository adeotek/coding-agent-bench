# moca vs Claude Code vs OpenCode vs Pi — Terminal-Bench 2.0 subset

Four agents, one fixed task set, one Docker sandbox, the task's own verifier. This is the
cross-agent view; the release-by-release moca history is in
[`moca-bench-report.md`](moca-bench-report.md).

> **This is a snapshot, not a live ranking.** The only four-agent sweep is the 2026-10-16 job
> (`cab-subset-20261016-004433`). Since then only moca has been re-run — five times — and it
> moved from 6/12 to 10/12 and back to 8/12 (see the moca report). The other three agents have
> not been measured since. Treat the table below as *what the field looked like at those pins*;
> the current-pin comparison is the run this report is waiting for.

## Headline — 2026-10-28, 23-cell sweep on the current pins (92 trials, 4 h 39 m, $14.84)

The first four-agent run since 2026-10-26, and the first on moca v0.7.11. Same 24-task file; the run
guard drops `build-cython-ext` as a broken task, so this is **23 cells × 4 agents × 1 attempt**.

| agent | solved | cost | $/solved | tok/solved | median agent run | exceptions |
|---|---|---|---|---|---|---|
| Claude Code 2.1.310 | **20/23** | $13.2693 | $0.6635 | 1.22 M | 227 s | 1 timeout, 1 exit 1 |
| **moca v0.7.11** | 18/23 | $0.5335 | **$0.0296** | 1.23 M | 155 s | 2 timeouts |
| OpenCode 2.1.4 | 18/23 | $0.5847 | $0.0325 | 1.45 M | 219 s | 3 × exit 1 |
| Pi 1.4.0 | 18/23 | $0.4532 | **$0.0252** | **0.83 M** | **147 s** | — |

| task | claude · moca · opencode · pi |
|---|---|
| break-filter-js-from-html | P P P P |
| circuit-fibsqrt | P P P P |
| cobol-modernization | P P P P |
| configure-git-webserver | F F P F |
| crack-7z-hash | P P P P |
| custom-memory-heap-crash | P P P P |
| db-wal-recovery | P P P P |
| dna-assembly | F F F F |
| dna-insert | P P P F |
| extract-elf | P P F P |
| filter-js-from-html | F F F F |
| fix-git | P P P P |
| gcode-to-text | P F F P |
| git-multibranch | P P P P |
| kv-store-grpc | P P P P |
| large-scale-text-editing | P P F F |
| log-summary-date-ranges | P P P P |
| mailman | P P P P |
| multi-source-data-merger | P P P P |
| nginx-request-logging | P P P P |
| overfull-hbox | P P P P |
| password-recovery | P P P P |
| sanitize-git-repo | P F P P |

**The three zen agents are one instrument, not three ranks.** Against the 2026-10-26 sweep, restricted to
the same 23 cells, the verdict flipped on **6 cells for moca, 4 for OpenCode, 5 for Pi, 2 for Claude** —
and OpenCode, Pi and Claude ran **the same binaries both times**. moca's flips cancel exactly
(18/23 → 18/23: gained `dna-insert`, `large-scale-text-editing`, `overfull-hbox`; lost `dna-assembly`,
`gcode-to-text`, `sanitize-git-repo`). A one-to-three cell gap between three agents whose own swing is
four to six cells per run is not a ranking; it is the instrument's noise floor, and at n=1 per cell this
sweep cannot lower it.

Claude is the only difference that survives — 2 cells clear of the zen three here, 4 clear on the
2026-10-26 slice — at **25× the cost per solve** ($0.6635 against $0.0296) and 1.5× the wall clock. It
buys grindy cells with money. Whether that is worth it is a budget question, not a capability one.

Two cells are shared losses and belong in the task audit, not a ranking: `filter-js-from-html` (0/4 every
run ever) and `dna-assembly` (0/4 here, after Claude passed it once). `configure-git-webserver` is the
known defective verifier — it flipped again (OpenCode up, everyone else down), which is what a verifier
that accepts a leftover artifact does.

## Protocol

| | |
|---|---|
| Dataset | `terminal-bench@2.0`. Two instruments: the fixed 12-task subset ([`docs/tb2-subset-12.txt`](tb2-subset-12.txt), all rows before 2026-10-25 17:40) and the 24-task comparison set ([`docs/tb2-subset-24.txt`](tb2-subset-24.txt) — those 12 plus 12 cells chosen from the screening sweep). The 24-task run is the current baseline |
| Models | moca / OpenCode / Pi: `opencode-go/deepseek-v4.1-flash` from 2026-10-24 (`opencode-go/glm-5.3-flash` was the default before — the rows below ran glm). Claude Code: `anthropic/claude-sonnet-5` — it cannot use a zen key, by design |
| Permissive modes | moca `--mode yolo`, OpenCode `--auto`, Claude Code `bypassPermissions` |
| Attempts | 1 per task × agent, `--max-retries 1`, `N_CONCURRENT=2` |
| Cost basis | zen spend is cash. Claude's `cost_usd` is an **API-equivalent** estimate; the run used a subscription, so its cash cost was $0 |

## Headline — 24-task set, two identical runs (192 trials) — superseded by the 2026-10-28 sweep above

Two runs of the 24-task set, same pins, same models, same 250-step budget, one attempt per cell
per run: `cab-subset-20261025-174057-3299781` (4 h 07 m) and `cab-subset-20261026-134414-1158148`
(4 h 37 m), $1.54 and $1.53 zen cash, $10.54 and $10.31 Claude API-equivalent.

| agent | run 1 | run 2 | pooled | 95 % CI (pooled) | $/solved (run 2) |
|---|---|---|---|---|---|
| **Claude Code** 2.1.310 | 21/24 | **23/24** | **44/48** | 80–97 % | $0.4483 eq |
| **Pi** 1.4.0 | 20/24 | 20/24 | 40/48 | 70–91 % | $0.0238 |
| **OpenCode** 2.1.4 | 20/24 | 19/24 | 39/48 | 68–90 % | $0.0308 |
| **moca** v0.7.10 | 18/24 | 19/24 | **37/48** | 63–87 % | $0.0249 |

**The ordering reproduced.** moca is last in both runs and Claude Code first in both, and the
pooled gaps are 7 cells to Claude and 2–3 to Pi and OpenCode. The 12-task set again saturated
inside both runs — 11/12 for all four, only `filter-js` lost — so the separation is still entirely
in the twelve added cells.

**But the instrument is noisy: 13 of 96 cells changed verdict between two identical runs (13.5 %).**
The 12-task hold study flipped 3 of 48 (6 %); the harder cells are twice as unstable.

| cell | agent | run 1 → run 2 |
|---|---|---|
| `configure-git-webserver` | Pi | ❌ → ✅ |
| `dna-assembly` | moca, Claude | ❌ → ✅ |
| `dna-assembly` | Pi | ✅ → ❌ |
| `dna-insert` | moca | ✅ → ❌ |
| `dna-insert` | Claude | ❌ → ✅ |
| `filter-js-from-html` | moca | ❌ → ⏱ (no verdict, task-side cell) |
| `gcode-to-text` | Pi | ✅ → ❌ |
| `large-scale-text-editing` | OpenCode | ✅ → ❌ |
| `large-scale-text-editing` | Pi | ❌ → ✅ |
| `overfull-hbox` | OpenCode | ❌ → ✅ |
| `sanitize-git-repo` | moca | ❌ → ✅ |
| `sanitize-git-repo` | OpenCode | ✅ → ❌ |

### What survives at cell level

**The one cell that looked structural is a broken cell, not a moca defect.** moca has never passed
`configure-git-webserver` (0/6 across the screening sweep, both runs and a 3-attempt cell run) —
and reading the task's own verifier explains why. `tests/verify.sh` clones `git@localhost`, pushes,
then curls `/hello.html`, but only the curl is asserted (`"TEST PASSED" in stdout`) and the
`expect` timeouts are ignored, so **any leftover `hello.html` in `/var/www/html` passes the cell**.
Claude Code's run-2 pass had no `sshd` installed at all — only `openssh-client` — so its clone
could not work; it passed on the file its own test left behind. Pi's run-2 pass is genuine (it
created `git` with the reference password via `chpasswd`). moca built repo + hook + nginx + sshd,
ran the pipeline end to end (403 before the push, 200 after), then restored a pristine docroot —
and got a 404 for its tidiness. The task text even says login is out of scope, while the verifier
requires exactly `git`/`password`.

`large-scale-text-editing` was checked the same way and **is not** a task-side defect: its
verifier validates the allowed commands line by line, runs vim headlessly, generates
`expected.csv` *after* the run and compares SHA-256. moca's five failing scripts end in a bare
`wq` and its one pass ends in `:wq`; Claude's passes end in `:x`, OpenCode's in `:wq`. Same Ex
command, different literal — so the cell tests instruction-literal copying, which makes it a
legitimate (if pedantic) moca loss rather than a broken cell.

So the set now has **two task-side cells** (`filter-js-from-html` and `configure-git-webserver`),
and neither is an agent result. **Everything else that looked like a finding was noise:**

| cell | moca across all samples | reading |
|---|---|---|
| `configure-git-webserver` | **0/6** | **task-side defect** — the verifier accepts a leftover artifact |
| `large-scale-text-editing` | 1/6 | **real but narrow**: moca writes `wq` where the spec lists `:wq`; verifier is honest, the winners copy the colon |
| `overfull-hbox` | 3/7 | coin flip; the 3× cell run passed 3/3 |
| `sanitize-git-repo` | 3/6 | coin flip |
| `dna-assembly` | 2/6 | coin flip **for all four agents** (OpenCode 0/2, Pi 1/2, Claude 1/2) |
| `dna-insert` | 1/3 | coin flip |
| `filter-js-from-html` | never passed in any run (0/25 in the 12-task hold study) | task-side, byte-exact test |

So this report's earlier claims about `dna-assembly` being a moca capability gap, and about a
"literal-constraint defect class" made of `large-scale` + `overfull`, are both withdrawn: the
first is a hard cell for everybody, the second is built on the two least stable cells in the set.

### Per-task matrix, both runs (✅ run 1 · ❌ run 1)

| task | moca | opencode | pi | claude-code |
|---|---|---|---|---|
| break-filter-js-from-html | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| build-cython-ext | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| circuit-fibsqrt | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| cobol-modernization | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| configure-git-webserver | ❌❌ | ❌❌ | ❌✅ | ✅✅ |
| crack-7z-hash | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| custom-memory-heap-crash | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| db-wal-recovery | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| dna-assembly | ❌✅ | ❌❌ | ✅❌ | ❌✅ |
| dna-insert | ✅❌ | ✅✅ | ✅✅ | ❌✅ |
| extract-elf | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| filter-js-from-html | ❌⏱ | ❌❌ | ❌❌ | ❌❌ |
| fix-git | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| gcode-to-text | ✅✅ | ✅✅ | ✅❌ | ✅✅ |
| git-multibranch | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| kv-store-grpc | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| large-scale-text-editing | ❌❌ | ✅❌ | ❌✅ | ✅✅ |
| log-summary-date-ranges | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| mailman | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| multi-source-data-merger | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| nginx-request-logging | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| overfull-hbox | ❌❌ | ❌✅ | ✅✅ | ✅✅ |
| password-recovery | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| sanitize-git-repo | ❌✅ | ✅❌ | ❌❌ | ✅✅ |

Legend: first mark = run 1, second = run 2 · ⏱ = no verdict (task-side verifier timeout).
Per-trial seconds and turns for run 1 are in the run-1 job's `result.json`; the aggregate
efficiency table is above.

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

## Partial credit — binary scoring was hiding most of the difference

The verifier writes `ctrf.json` with every test's status, and the 24-task set runs **82 tests**
to score 24 cells. Scored that way (passed / run, `skipped` excluded), run 2 looks different:

| agent | tests | passed | credit | binary |
|---|---|---|---|---|
| claude-code | 82 | 80 | **97.6 %** | 95.8 % |
| moca | 80 | 76 | **95.0 %** | 82.6 % |
| opencode | 82 | 77 | **93.9 %** | 79.2 % |
| pi | 82 | 76 | **92.7 %** | 83.3 % |

Two things worth keeping:

1. **The four agents are 4.9 points apart on credit and 16.6 apart on binary.** Most of moca's
   and OpenCode's deficit is a *single failing test per lost cell*, not a missing capability:
   moca passes 76 of the 80 tests it runs and still scores 82.6 %.
2. **The ranking barely moves** — credit orders claude > moca > opencode > pi, binary orders
   claude > pi > opencode > moca; the middle three swap on ~1 test each. Partial credit is a
   better *resolution* instrument, not a different verdict, which is how it is reported:
   secondary, never a replacement.

`filter-js-from-html` is why moca shows 80 tests and not 82 — that trial produced no ctrf at all
(verifier timeout, `⏱`), and no-verdict stays excluded rather than being counted as a failure.

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

## Truncation — moca's own failure mode, fixed and re-measured (three arms, 2026-10-28 → 10-30)

The 21-cell screen found a loss mode that is neither capability nor task-side: **moca can put its whole
per-turn output budget into thinking and return nothing.** On `regex-chess` and
`adaptive-rejection-sampler` the sessions show 39 905 / 61 124 / 61 291 characters of thinking per turn
with zero text, then `response truncated (token limit reached)` and exit 1 — 43 292 output tokens, no
file. OpenCode on the same model reached 8/9 tests on one of those cells, which is what made it a
harness finding rather than a ranking fact.

v0.7.11 retries such a turn once at a reduced effort with a nudge that forbids deliberating, and ends the
run if it happens twice. Retested as a **two-arm comparison** — same 2 cells × 3 attempts, one variable
(the release), run back to back (`…-103325-2855858` on v0.7.11, `…-114403-2964679` on v0.7.10):

| cell | v0.7.11 | v0.7.10 | |
|---|---|---|---|
| `regex-chess` | **2/3** | 0/3 | two solves against none (Fisher p = 0.40 — direction, not proof) |
| `adaptive-rejection-sampler` | 0/3 | 0/3 | unchanged; a both-fail cell on this model |
| trials hitting ≥1 truncation | 6/6 | 6/6 | **same stimulus** (p = 1.00) |
| runs *ended* by a truncation | **1/6** | **6/6** | **p = 0.015** |
| cost for six trials | $0.3492 | $0.1336 | the survivor does 54 tool calls per trial against 4 |

The design is what makes it readable: **the model truncates exactly as often on both releases**, so the
agent's input is identical and only its reaction differs. At v0.7.10 a truncated turn killed the run every
time, 2–6 tool calls in; at v0.7.11 it killed one of six and the other five continued into real work. That
mechanism claim is significant at p = 0.015.

**The reward claim did not hold.** k=10 per arm, same day: **2/10 against 2/10**, p = 1.00; pooled over
every attempt on the cell, 4/13 against 2/13, p = 0.64. The k=3 "one cell moved" reading was noise, and it
is retracted in the moca report rather than deleted. What the k=10 arms exposed is that the rescue treats
the wrong half of the problem: in the v0.7.11 failures the two truncations arrive back to back, and the
truncating turn is often a **large output** — a 404-line file write, a whole module dumped to stdout — not
runaway thinking. Lowering the effort does nothing for those, and one rescue per run is too few for a task
that legitimately produces several large turns.

**v0.7.12 finished the job, and the ceiling turned out to be the constraint.** Released 2026-10-30, it
raises the per-turn ceiling on the retry (`min(model limit, context.reserveTokens) × 2^attempt`, capped at
the model's own limit — 16 384 by default against 384 000 the model can emit) and allows three rescues per
run, reset by any tool call. Retested at k=10, pre-registered, one variable (`…-122349-959024`, 3 h 01 m,
$1.0703):

| measure | v0.7.10 | v0.7.11 | v0.7.12 |
|---|---|---|---|
| `regex-chess` solves | 2/10 | 2/10 | **10/10** (p = 0.0007) |
| trials hitting ≥1 truncation | 8/10 | 9/10 | 6/10 — the stimulus still occurs |
| runs *ended* by a truncation | 8/10 | 8/10 | **0/10** (p = 0.0007) |
| rescues taken / fatal | — | 9 / 8 | **11 / 0** |
| median trial / cost per trial | 5 m / $0.035 | 7 m / $0.034 | **32 m / $0.107** |

The agent was never unable to solve this cell; it was being cut off mid-thought at a ceiling 23× below what
the model can emit. The honest half of that sentence is the second column of the last row: the solve is
bought with time and tokens — 32 minutes a trial instead of 5 — and one trial ran long enough to hit the
task's 3600 s agent cap after completing the work (the verifier scored it 1.0; exceptions and failures are
different things). The lesson generalises past moca: **before filing a cell as too hard, read the losing
agent's stop reason** — a truncated turn is a budget running out, not a decision to stop.

Neither cell is in the 12- or 24-task sets, so no number in the tables above changes; per-trial tables are
in [`moca-bench-report.md`](moca-bench-report.md).

**Cross-agent lesson, added:** an empty reply at the output limit is not a model decision to stop — it
is a budget being exhausted mid-thought. Before filing such a cell as "too hard" or as a capability
gap, read the losing agent's session for the stop reason.

## The instrument's floor, measured — 8 flapping cells at k=3 (2026-10-30)

Every sweep in this report has been read against a shrug: three of four agents ran byte-identical binaries
in the 2026-10-26 and 2026-10-28 sweeps and still flipped 4, 5 and 2 of 23 cells, so a 1–3 cell gap could not
be called a ranking. This run measures why. The **eight cells whose verdicts moved for any zen agent**
(`docs/tb2-noisebar.txt`, derived from the two sweeps' job stores rather than curated), three zen agents,
**3 attempts each**, `cab-subset-20261030-180311-1319333`, 72 trials, 4 h 49 m, **$1.9574**.

| cell | moca | opencode | pi |
|---|---|---|---|
| `configure-git-webserver` | 0/3 | 0/3 | 0/3 |
| `dna-assembly` | 0/3 | **1/3** | **2/3** |
| `dna-insert` | **1/3** | 3/3 | **2/3** |
| `extract-elf` | 3/3 | 3/3 | 3/3 |
| `gcode-to-text` | 0/3 | **1/3** | **1/3** |
| `large-scale-text-editing` | **2/3** | **2/3** | 0/3 |
| `overfull-hbox` | 3/3 | 3/3 | 3/3 |
| `sanitize-git-repo` | **2/3** | 3/3 | **2/3** |
| **tally** | **11/24** | **16/24** | **13/24** |

**Ten of the 24 (cell, agent) pairs are split at three attempts** — not "near-certain", split: `dna-assembly`
for OpenCode at 1/3, `dna-insert` for moca 1/3 and Pi 2/3, `gcode-to-text` 1/3 for two agents,
`large-scale-text-editing` 2/3 for two, `sanitize-git-repo` 2/3 for two. Half of the cells this bench argues
about are coin flips for at least one agent, while `overfull-hbox` and `extract-elf` are unanimous passes for
all three and `configure-git-webserver` a unanimous fail.

**The flips are mostly arithmetic.** From each pair's measured rate `p`, two independent one-attempt runs
disagree with probability `2p(1−p)`; summed over these eight cells that predicts **1.3 flips for moca, 1.3 for
OpenCode, 1.8 for Pi**. The two sweeps saw 6, 4 and 5 across 23 cells — the same order of magnitude, produced
by cells whose rates sit near one-half. Nothing mysterious is happening: a one-attempt verdict on a middling
cell flips half the time by construction.

**But "flip" is not one phenomenon, and the difference matters.** Of the 15 zen flips between the two sweeps,
**7** land on a pair that is split at k=3 — sampling noise, exactly as modelled — and **8** land on a pair
where three attempts were unanimous: 5 unanimous fails and 3 unanimous passes. Those are not explained by the
rate alone. They are drift (a verifier's own behaviour, a cell that rots between rounds, the agent's leftover
artifacts) or a rate low enough that three draws cannot see it — 0/3 bounds a rate only at **≤63 %**, so
"unanimous" at k=3 is not "never passes". `configure-git-webserver` is the clean example of the first kind: it
passed for OpenCode in one sweep and for Pi in the other, and now fails 3/3 for all three agents. It is the
cell whose verifier accepts a leftover artifact, so its verdict tracks litter, not capability.

**What this buys the next sweep.** A one-attempt cell verdict is quotable for a pair that is unanimous at k=3
and worth nothing for the ten split ones; the aggregate carries ±2–3 cells per agent, which is the swing
actually observed. One-attempt sweeps therefore remain useful for "did anything break" and cannot, at any k
that fits this budget, resolve a 1–3 cell ordering. Ranking needs the paired multi-attempt design — and note
its price: eight cells at three attempts cost **$1.96 and 4 h 49 m**, more wall clock than a 23-cell one-attempt
sweep for a third of the cells.

Exceptions, counted separately from failures as always: moca 2 × `AgentTimeoutError`; OpenCode 7 ×
`NonZeroAgentExitCodeError`, of which **5 scored 1.0** — the known "exits 1 after clean work" quirk, and the
reason this report never equates an exception with a loss. moca's column runs v0.7.12 rather than the v0.7.11
the flips were recorded on (its only change is the truncated-turn path), so OpenCode and Pi carry the
like-for-like comparison.

## Task audit — the cells themselves (2026-10-26/27, zero tokens)

Every cell in `docs/tb2-all.txt` was audited with Harbor's own agents before planning anything at
scale: `oracle` runs the reference solution (must pass), `nop` does nothing (must fail).

| verdict | cells | what it means for a scoreboard |
|---|---|---|
| healthy | **78** | a pass means work was done |
| task-side defect | **8** | a failure here is the task's fault, not the agent's |
| host-limited | **3** | not measurable on this machine |
| vacuous / both-broken / no verdict | 0 | no verifier here is satisfiable by inaction |

The 8 defects (each re-verified at two attempts) are **bit-rot in reference solutions**, not bad
prose: `build-cython-ext` (verifier clones upstream and asserts *its* suite — non-hermetic, and it
rotted from 8/8 agent passes to oracle 0/3 within a day), `build-pmars` (pinned `dpkg-dev` gone),
`make-doom-for-mips` (missing `clang`), `mcmc-sampling-stan` + `rstan-to-pystan` (R packages never
install), `protein-assembly` + `tune-mjcf` (no output), `train-fasttext` (knife-edge
`accuracy > 0.62` against a 0.619725 reference — it passes or fails on training noise).

The 3 host-limited cells are environmental, not task-side: this box is a QEMU guest with a generic
vCPU and no `/dev/kvm`, so `mteb-leaderboard` dies on `Illegal instruction` and the two `qemu-*`
cells cannot start a VM. `mteb-retrieve`, the same size and family, is healthy — so it is the
image, not the family.

Two consequences for every table in this report: a "full" run measured here tops out at **86
cells**, and **8 of them cannot produce an agent signal at all** — the honest denominator is
**78**. Nothing above changes: none of the four agents' measured cells is among the 8 or the 3.
Evidence: `docs/task-defects.md`; reproduce with `make audit`.

One more measured fact about this dataset, from the 2026-10-27 two-agent screen of the 21
audited-but-never-run cells (`cab-subset-20261027-105352-727505`, 42 trials): **17 of 21 were passed
by both agents**, 2 discriminated (`make-mips-interpreter` cleanly; `regex-chess` only because moca
burned its output budget on thinking and never wrote the file), and 2 failed for both by timeout or
truncation. The public set is saturated for this class of agent — which is why this report ranks
agents on cost, turns and dollars-per-solve as well as on passes: on cells nobody fails, the only
signal left is what the pass costs.

## What would make this report current

1. **Stop repeating the sweep at n=1 — done, and the answer is measured.** Three repeats moved 4–6 cells
   per agent on unchanged binaries, so the eight cells that flipped were run at k=3 (`…180311-1319333`,
   $1.96): **10 of 24 (cell, agent) pairs are split at three attempts**, and the sweep-level movement is
   what those rates must produce. A one-attempt verdict is quotable only for a pair that is unanimous at
   k=3; the aggregate carries ±2–3 cells per agent. Ranking three agents needs the paired multi-attempt
   design, and its price is visible: eight cells at k=3 cost more wall clock than a 23-cell n=1 sweep.
2. **Read the task's verifier before believing a cell.** `configure-git-webserver` looked like
   moca's only structural defect until `tests/verify.sh` was read: it asserts a leftover artifact,
   not the behaviour, and Claude passed it once with no `sshd` installed. The remaining candidate
   (`large-scale-text-editing`, 1/6) is cheap to check the same way — `~/.cache/harbor/tasks/*/`
   holds every task's `tests/` — and a cell run at `N_ATTEMPTS=3` is the measurement, not a fix.
3. **Keep the moca-only rounds out of this table.** They are a release history, not a
   comparison; mixing them would silently compare different dates.
4. **If a cell decides the ranking, cell-run it** (`N_ATTEMPTS=3`) before writing it into the
   verdict — at n=12 a single flip is inside the noise band.
5. **The truncation cell needs a different fix, not more attempts.** The mechanism of moca v0.7.11 is
   established (p = 0.015) and its reward effect on `regex-chess` is nil at k=10 (2/10 vs 2/10). The
   evidence points at large single outputs and a one-rescue-per-run bound, which is a moca change, not a
   bench measurement — measure it here at k=10 on that cell once it ships.

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
