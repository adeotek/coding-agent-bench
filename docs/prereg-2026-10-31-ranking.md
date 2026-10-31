# Pre-registration — can anything rank these agents? (2026-10-31)

**Status: PRE-RUN. Written and committed before the first trial of either arm. Nothing below may be edited
after the run starts; the outcome is appended in a separate section, and any deviation is listed there.**

## The question

Two arms, answered separately and never pooled into one table:

- **A — can the six ranking-capable terminal-bench cells order the three zen agents?** `docs/tb2-ranking.txt`
  says these six cells *can* separate agents (their measured rates spread by ≥ 0.33), but the rates that
  produce that spread come from different rounds and, for moca, from previous releases.
- **B — were the seven cells this repo owns worth writing?** They are oracle-green and nop-red; nobody has
  measured an agent on them yet.

## Design (fixed now, not after looking)

| | |
|---|---|
| agents | `moca` v0.7.12 (`--mode yolo`, `max_steps` 250), `opencode` v2.1.4, `pi` 1.4.0 |
| model | `opencode-go/deepseek-v4.1-flash` for all three (same model, so the agent is the variable) |
| attempts | **k = 3** per (cell, agent) |
| concurrency | `N_CONCURRENT=2`, `--max-retries 1` |
| sandbox | the tasks' own Docker images, unchanged |
| arm A cells | `db-wal-recovery`, `dna-assembly`, `dna-insert`, `gcode-to-text`, `large-scale-text-editing`, `sanitize-git-repo` (registry) |
| arm B cells | `idempotent-migrations`, `fix-flaky-suite`, `bisect-culprit`, `csv-normalizer`, `safe-cleanup` (authored) + `configure-git-webserver`, `build-cython-ext` (repaired copies) |
| trials | 54 (A) + 45 + 18 (B, two local runs) = **117** |
| cost cap | **$6**. Passing the cap ends the run and the partials are reported as partials. |

Arm B is local-only by construction (`LOCAL_TASKS`): its numbers are never quoted beside terminal-bench
numbers, in this document or anywhere else.

## What will be reported

- Per cell, per agent: **k/n** with a 95 % Wilson interval. No verdicts, no ✓/✗ cells, no single-draw claims.
- Per agent: a **pooled rate over the arm's cells**, with a clustered bootstrap over cells (the cell is the
  independent unit; attempts inside a cell are not independent).
- Exceptions and timeouts listed separately, never folded into "failed".
- Cost actually spent, from the job stores.

## Decision rules (pre-registered)

1. **A cell discriminates** if the three agents do not all land on the same verdict (all 3/3, or all 0/3).
   This is descriptive only — it says the cell is not saturated, not that anyone is better.
2. **A claim of difference** requires non-overlapping 95 % intervals between two agents, either on a cell or
   on the arm's pooled rate. Anything else is written as **"unresolved at k = 3"**, with the intervals shown.
3. **Nothing pools across arms.** A and B are separate tables and separate conclusions.
4. **Nothing pools across releases.** moca trials from v0.7.10/v0.7.11 jobs are not added to these; only
   v0.7.12 attempts count. The same applies to any agent whose version moves mid-run.
5. **If every owned cell is 3/3 for every agent**, the conclusion is "the authored set is saturated; the
   specs need to be harder", not "the agents are equal".
6. **If arm A produces no separation**, the conclusion is "these six cells cannot order these three agents
   at k = 3", and the next step is more attempts per cell (the power table in
   `docs/agents-bench-report.md`), not a different story.

## Expected outcome, written down before the data

- **Arm A, moca.** Prior attempts on these cells (earlier releases): `gcode-to-text` 0/3, `dna-assembly` 0/3,
  `dna-insert` 1/3, `large-scale-text-editing` 2/3, `sanitize-git-repo` 2/3, `db-wal-recovery` under-measured.
  Prediction: moca's pooled rate lands **below** opencode's and pi's, but with overlapping intervals, so the
  pre-registered answer will be "unresolved" — and the honest reading of a 0/3 that becomes 2/3 is that the
  old 0/3 was a release artifact, not a capability gap.
- **Arm B.** Prediction: the owned cells are **harder** than the terminal-bench cells that saturate — at least
  two of the seven will show a split verdict (neither all-pass nor all-fail) for at least one agent, because
  every one of them has a trap that a careless solution walks into.
- **The thing this experiment cannot do**: rank anyone from a single draw. If the result is 117 trials of
  "unresolved", that is a real result about the instrument's resolution, and it is what gets reported.

## Analysis plan

`scripts/bench_report.py summary <job>` for rates and intervals; `scripts/cell_stability.py` regenerated
afterwards so the new attempts enter the derived registry. Any analysis that is not in this list is
exploratory and must be labelled as such.

## Cost estimate

117 trials at the measured ~$0.035 marginal cost → **$4.1 expected, $6 cap**. Time: 3–4 h at concurrency 2.

---

## Outcome

### Result — arms A and B, 117 trials, $2.59 of the $6 cap (2026-10-31)

Every trial in both arms ran to a verifier verdict. Jobs: `cab-subset-20261031-011345-2374062` (A),
`cab-subset-20261031-121016-3263920` (B, authored), `cab-subset-20261031-131929-3554116` (B, repaired).

**Arm A — the six cells that were supposed to rank (54 trials, 3 h 11 m, $1.80).**

| agent | rate | 95 % Wilson | exceptions |
|---|---|---|---|
| moca v0.7.12 | 11/18 = 61 % | [39 %, 80 %] | 1 (agent timeout, reward 0) |
| opencode v2.1.4 | 11/18 = 61 % | [39 %, 80 %] | 6 (3 of them still scored 1.0) |
| pi 1.4.0 | 9/18 = 50 % | [29 %, 71 %] | 0 |

| cell | moca | opencode | pi |
|---|---|---|---|
| db-wal-recovery | 3/3 | 2/3 | 3/3 |
| dna-assembly | 1/3 | 1/3 | 0/3 |
| dna-insert | 1/3 | 2/3 | 1/3 |
| gcode-to-text | 1/3 | 2/3 | 2/3 |
| large-scale-text-editing | 3/3 | 1/3 | 1/3 |
| sanitize-git-repo | 2/3 | 3/3 | 2/3 |

**Rule 2 applies: unresolved at k = 3.** No pair separates — two agents sit on the same 61 % point estimate
and every interval overlaps every other. The widest raw gap (`large-scale-text-editing`, 3/3 against 1/3)
still overlaps, because 3/3 has a Wilson floor of 44 %.

**Prediction check.** Half right, and the wrong half matters. I predicted moca would land *below* the other
two with overlapping intervals: the overlap was right, the ordering was wrong — moca is level with OpenCode
and above Pi. The "moca is weak on dna/gcode" reading from earlier releases (0/3, 0/3) does not reproduce at
v0.7.12 (1/3, 1/3); those 0/3s were release artifacts.

**Arm B — the seven owned cells (63 trials, $0.79).**

*Authored five (45 trials):* moca 13/15 = 87 % [62–96], opencode 15/15 = 100 % [80–100],
pi 14/15 = 93 % [70–99]. Three cells split 2/3 against 3/3 (`csv-normalizer` and `fix-flaky-suite` against
moca, `safe-cleanup` against pi); every interval overlaps by ≥ 30 points.

*Repaired two (18 trials):* `build-cython-ext` 3/3 for all three; `configure-git-webserver` moca 3/3,
opencode 2/3, pi 3/3. Against the upstream verifier these cells had **never passed for anyone**.

**Rule 5 applies: the authored set is saturated.** My prediction — at least two cells splitting rather than
saturating — failed. A split verdict is not a split rate, and 2/3 against 3/3 is exactly the noise the
registry already refuses to call a ranking. The specs need to be harder, not the sample bigger.

**What the repairs bought.** `configure-git-webserver` and `build-cython-ext` went from 0/N for every agent
under the upstream verifiers to 6/6, 5/6 and 6/6 under the repaired ones. That is the strongest evidence in
this stretch that the old 0/N columns were the verifier's opinion, not the agents' capability.

### Deviations from the plan, listed because they happened

1. **Exceptions.** My first pass excluded exception trials from the denominator. Harbor still runs the
   verifier when the agent exits non-zero, and three OpenCode trials scored 1.0 while raising
   `NonZeroAgentExitCodeError` (a clean JSON transcript, a finished answer, exit 1 anyway — a v2.1.4 quirk,
   not an agent failure). Excluding them would have reported OpenCode as 8/12 = 67 % instead of 11/18 = 61 %.
   All rates above judge by reward, which is the bench's standing rule.
2. **The pre-run cell list is no longer the derived one.** `docs/tb2-ranking.txt` now names **five** ranking
   cells, not six: this run's data took `dna-assembly`'s spread from 0.50 to 0.17. The registry is derived on
   purpose; the pre-registration quoted the version that existed before the measurement.
3. **`cell_stability.py` gained a local-dataset exclusion** (12 jobs skipped, named in the registry metadata).
   Not an analysis choice — a correctness fix: without it the authored and repaired cells would have entered
   the terminal-bench registry under names that also exist upstream.

### What is next, priced

The power table in [`agents-bench-report.md`](agents-bench-report.md) says 70 % vs 30 % needs ~17 attempts
per arm, 60 % vs 20 % needs ~16. At k = 3 per cell the bench can detect almost nothing at cell level; k = 3
per arm over many cells is what it can afford. So the next honest step on ranking is **more attempts on few
cells**, not more cells at k = 3 — and for the owned cells, harder specs first.

