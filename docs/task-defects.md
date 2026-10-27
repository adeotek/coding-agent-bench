# Task audit — is every cell a task?

`make audit` runs Harbor's own `oracle` (executes the reference solution — must **pass**) and
`nop` (does nothing — must **fail**) over `docs/tb2-all.txt`. Zero model tokens; verifier wall
clock only.

Round: **2026-10-26/27**, 89 cells, 15 jobs (`results/audit/jobs/batch-*.job` are the pointers).

| verdict | cells | meaning |
|---|---|---|
| **healthy** | **78** | oracle passes, nop fails — a real task |
| **task-side defect** | **8** | the task or its reference solution is broken |
| **host-limited** | **3** | unpassable *on this host* for environmental reasons, not task reasons |
| vacuous / both-broken / no-verdict | 0 | — |

Healthy includes the 12 cells that both agents and the audit agree on; the audit says nothing
about *discrimination*, only about solvability.

## Task-side defects (8)

Re-verified at 2 attempts each in `cab-audit-20261027-014246-145939` before being called defects.

| cell | evidence | cause |
|---|---|---|
| `build-cython-ext` | oracle 0/3 (audit + dedicated recheck `cab-audit-20261026-233417-3014135`) | verifier **clones pyknotid 0.5.3 from GitHub at verification time** and asserts the upstream project's own suite passes; one upstream test (`…reconstructed_space_curve`) now fails. Non-hermetic by construction: the verdict tracks GitHub's content, not the agent's work. All four agents passed this cell 8/8 on 2026-10-25/26 — it rotted in a day. |
| `build-pmars` | oracle 0/2 | `solution/solve.sh` installs `dpkg-dev=1.22.21`; that version is no longer in the image's repositories (`E: Version '1.22.21' for 'dpkg-dev' was not found`). |
| `make-doom-for-mips` | oracle 0/3 | solution runs `make` which calls `clang`; `clang` is not installed in the image (`make: clang: No such file or directory`). |
| `mcmc-sampling-stan` | oracle 0/2 | verifier: `RStan package is not properly installed … there is no package called 'rstan'` — the reference solution never gets `rstan` installed. |
| `protein-assembly` | oracle 0/2 | verifier: `File /app/gblock.txt does not exist` — the reference solution produces no output. |
| `rstan-to-pystan` | oracle 0/2 | verifier: `Required output file not found: /app/alpha_est.csv` — reference solution produces no output (same R-stan family as above). |
| `tune-mjcf` | oracle 0/2 | no artifacts produced by the reference solution. |
| `train-fasttext` | oracle 0/1 then **1.0, 1.0** | the verifier asserts `accuracy > 0.62` and the reference solution measures **0.619725** — a knife-edge threshold. The cell passes or fails on training noise, so a loss here is not an agent capability signal. |

Family pattern worth noting: **three of the eight are R/Stan cells** whose reference solutions
install R packages at solve time, and **two more are build cells that assume a tool the image
does not ship**. Bit-rot in the reference solution, not in the tasks' prose.

## Host-limited (3) — not task defects

This host is a **QEMU guest with a generic vCPU (`QEMU Virtual CPU version 2.5+`) and no
`/dev/kvm`**, which makes these cells unpassable here for reasons that have nothing to do with
the task or with an agent:

| cell | evidence | limitation |
|---|---|---|
| `mteb-leaderboard` | oracle solution dies with `Illegal instruction (core dumped)` running `python leaderboard.py` | the image's wheels use CPU instructions this vCPU does not expose (no AVX/AVX-512 advertised) |
| `qemu-startup` | oracle fails | no `/dev/kvm` — no hardware virtualization in the guest |
| `qemu-alpine-ssh` | oracle fails | same |

They must be reported as **not measurable on this host**, never as broken tasks, and any
"full 89" claim made from this machine has to carry that caveat. (`mteb-retrieve`, the twin of
`mteb-leaderboard` at the same size, *is* healthy here — so the failure is per-image, not
per-family.)

## What this changes

1. **The ceiling of a "full 89" run measured here is 86 cells** (89 − 3 host-limited), and 8 of
   those are cells where a failure says nothing about the agent. The effective comparison set is
   **78 cells**, before accounting for saturation.
2. **Re-audit before every round.** `build-cython-ext` proves a cell can flip from "all agents
   pass" to "oracle fails" inside a day. An audit is a cheap gate (zero tokens, ~1 h with cached
   images) and the only defence against publishing a rot-driven "regression".
3. **The registry stays small and evidence-backed.** `docs/task-side.json` carries only cells
   with a verifier-level defect that mis-scores agents (`configure-git-webserver`,
   `filter-js-from-html`, `build-cython-ext`). Broken *tasks* are recorded here instead: they need
   a repair, not an exclusion, because excluding them from a set only hides the rot.

## Reproduce

```bash
make audit                                    # 89 cells, batched, images pruned per batch
python3 scripts/bench_report.py audit $(cat results/audit/jobs/*.job | sort -u)
```

The audit is resumable: batch markers under `results/audit/jobs/` record what already ran, and a
re-run derives its batches from whatever is still pending.
