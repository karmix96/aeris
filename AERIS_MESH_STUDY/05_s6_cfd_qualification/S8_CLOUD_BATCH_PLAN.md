# The high-fidelity cloud batch: what is ready, what it costs, and what must be true first

Written 2026-09-18. Supersedes `reports/s8_cloud_batch.json` (2026-09-09), every figure in
which was an estimate. Every number below is measured unless it says otherwise.

The decision this batch exists to serve: **can S8 rank BWB designs by drag?** Tonight's two-grid
result says the grid error in a wing-to-wing *difference* is 0.85–4.39 counts against a
trailing-edge credit of 5.27–8.98 counts. That is the question a third and fourth level answers,
and it cannot be answered on the development host: `gci_F` needs 20.6 GiB and `gci_FF` 38.4 GiB
against 12.8 GiB available.

---

## 1. What is built and verified

All eleven meshes were built and checked here on 2026-09-18 before any machine is rented.
`reports/s8_cloud_meshes.json` carries the full record.

| level | geometries | cells | folded | wall-layer error | solve memory |
|---|---|---|---|---|---|
| `gci_F` | 12, 13, 16, 23, 29, 36, 47, 65, 81, 83 | 2,322,128 – 2,339,536 | **0 on all ten** | ≤ 3.0e-16 m | 20.5 – 20.6 GiB |
| `gci_FF` | 83 | 4,682,524 | **0** | 2.2e-16 m | 38.4 GiB |

Build cost is negligible — 25–45 s and 1.7 GiB peak per mesh — so **the cloud rebuilds them from
the same commit rather than having gigabytes shipped to it.** Building them here is a preflight,
not a delivery: the point is that a folded `gci_FF` is discovered now and not after the meter
starts.

**The CGNS writer is proven at full size.** `gci_FF` wrote in 6.1 s at 0.45 GiB peak: a 115 MB
file, 14 block-to-block connections, 7 boundary conditions, root plane at y = 4.8e-18 m. That
was an open risk and it is closed.

**The four-level family on the reference geometry is self-similar.** Interval counts in the
`o_wing` block, and the ratio at each step:

| level | o_wing intervals | cells | ratio on the previous level |
|---|---|---|---|
| `gci_C` | 92 / 64 / 48 | 603,592 | — |
| `gci_M` | 120 / 83 / 62 | 1,172,856 | 1.304 / 1.297 / 1.292 |
| `gci_F` | 156 / 108 / 81 | 2,322,128 | 1.300 / 1.301 / 1.306 |
| `gci_FF` | 204 / 141 / 105 | 4,682,524 | 1.308 / 1.306 / 1.296 |

Every step is 1.29–1.31 in every direction, which is the r ≥ 1.3 that Celik and the ASME
procedure ask for. `ds_te_frac` and `s0_frac` scale with it (0.001 → 0.000769 → 0.000592 →
0.000455 and 3.60e-6 → 2.77e-6 → 2.13e-6 → 1.64e-6). **`gci_CC` and `gci_MF` are NOT in this
family** — both are generated from `oh_L3` and carry its old trailing-edge target, `gci_CC` at
0.0052 against the 0.0013 the family wants and `gci_MF` off by exactly ×4. They must not be used
as cheap substitute levels.

---

## 2. Cost and time

### The timing model, and why it is better than the old one

52 solves on 2026-09-17 give a two-factor decomposition the old single figure did not have:

| level | cells | iterations (mean) | minutes at 6 ranks | **seconds per Mcell-iteration** |
|---|---|---|---|---|
| `gci_C` | 607,226 | 203 | 19.4 | **9.44** |
| `gci_M` | 1,176,284 | 262 | 51.2 | **9.97** |

The cost of a cell is flat across the two levels — 9.44 vs 9.97 s, a 6 % spread. **All of the
superlinearity is iteration count**, which rose ×1.29 from C to M. So the model is
`minutes = Mcells × iterations × 9.7 s / 60`, with iterations extrapolated at ×1.29 per level.

> **Weakest link, stated plainly.** That ×1.29 is one measured ratio extrapolated two levels. It
> is the dominant uncertainty in the bill, and the low/high band below brackets it at flat and at
> ×1.5 per level.

### Ranks: four, not six or twenty-four

The measured rank probe is 2121 / 1121 / 849 / 827 s at 1 / 2 / 4 / 6 ranks.

| ranks | wall time vs 6 | core-hours vs 6 |
|---|---|---|
| 2 | ×1.355 | ×0.452 |
| **4** | **×1.027** | **×0.684** |
| 6 | ×1.000 | ×1.000 |

**Four ranks is 2.7 % slower than six and costs 32 % less.** Six was right for the development
host, where finishing one case sooner mattered. The cloud runs 44 *independent* cases, so
throughput is what is being bought and per-case latency is nearly irrelevant. The old plan's
24 ranks per case is the worst of both.

The old plan also assumed 75 % parallel efficiency at 24 ranks. Measured efficiency is 42.7 % at
6. Nothing in the record supports 75 %.

### The bill

| level | cases | minutes each (4 ranks) | core-hours |
|---|---|---|---|
| `gci_F` | 40 | 131 | 349 |
| `gci_FF` | 4 | 339 | 90 |
| | **44** | | **439** |

| | core-hours |
|---|---|
| low (iterations flat) | 325 |
| **central** | **439** |
| high (iterations ×1.5/level) | 528 |
| central + 20 % retry margin | **527** |

**Core-hours is the hard number. Money is core-hours times a rate, and no rate is asserted
here — confirm it at purchase.** For orientation only, mainstream on-demand memory-optimised
instances land around \$0.10–0.15 per *physical* core-hour, spot and bare-metal providers
around \$0.02–0.05. On that spread the batch is roughly **\$10–80**, most likely \$25–60. This is
a small batch; the real financial risk is not the rate, it is paying twice because something in
§4 was not true the first time.

### Machine shape

Memory per core at 4 ranks is **5.2 GiB for `gci_F` and 9.6 GiB for `gci_FF`**. Compute-optimised
instances (4 GiB per physical core) **will not hold `gci_FF`**. Use a memory-optimised type, or
run the four FF cases at 8 ranks to halve the per-core requirement at a 30 % core-hour premium on
those four cases only.

Concurrency is `min(cores / 4, RAM / 20.6)` for F and `min(cores / 4, RAM / 38.4)` for FF:

| node | concurrent F | concurrent FF | total wall time |
|---|---|---|---|
| 16 physical cores, 128 GiB | 4 | 3 | ≈ 33 h |
| 32 physical cores, 256 GiB | 8 | 6 | ≈ 17 h |
| 64 physical cores, 512 GiB | 10 (case-bound) | 4 (case-bound) | ≈ 14 h |

Pin ranks to physical cores; do not let the scheduler put two ranks on one core's hyperthreads.

---

## 3. The pilot gate — spend 2 % first

**Run one `gci_F` case and one `gci_FF` case, end to end, and stop.** Cost: about 20 core-hours,
under 5 % of the batch. It is the only way to test the three extrapolations this plan rests on:

| what the pilot measures | what it is being checked against |
|---|---|
| peak resident memory | the ANK-only law `(2.69 + 7.23 × Mcells) × 1.05`, a **two-point fit extrapolated to 4× its largest input** |
| iterations to 1e-6 | the ×1.29-per-level growth assumption |
| seconds per Mcell-iteration | 9.7 s, measured only up to 1.17M cells |
| **does ANK-only converge at all** | see below |

> **The largest technical risk in this batch.** ANK-only is proven to 1,172,856 cells. It was
> chosen *because* Newton-Krylov froze at that size with this project's lean preconditioner —
> NKSubspaceSize 20 and NKPCILUFill 1 against ADflow's defaults of 60 and 2 — at Step 0.01 and
> linear residual 1.000. At 2.3M and 4.7M cells ANK-only is **unproven**. If it stalls at
> `gci_FF`, the fallback is restoring ADflow's NK defaults, which needs about 2 GiB more per case
> on the `1.51 + 9.46 × Mcells` law — 46.8 GiB for `gci_FF` — and is itself unproven here.
> Discover this on one case, not forty-four.

Proceed to the other 42 only when all four rows above are confirmed.

---

## 4. The checklist — everything that must be true before money is spent

### A. The measuring instruments (no CFD; this is the review's G0)

The 2026-09-16 external review demonstrated, with synthetic counterexamples fed to the real
functions, that several checkers accept what they should reject. Two of its predictions were
confirmed live in data generated on 2026-09-17 and are already fixed. Paying for 44 runs whose
provenance or verdicts cannot be trusted is the single most expensive mistake available here.

| # | item | state |
|---|---|---|
| A1 | Per-run record directories carry the geometry (defect 25) | **done**, 16 Sept |
| A2 | Surface-field archives carry the geometry, hash read back from the stored bytes (defect 26) | **done** 18 Sept — had been 44 of 52 rows pointing at another wing's flow |
| A3 | y+ statistics masked to wall zones (defect 27) | **done** 18 Sept — 82.2 % of the sample had been far field |
| A4 | `gci.py` refuses a family whose successive differences grow under refinement (defect 28) | **done** 18 Sept — it had returned p = +2, "ok", GCI 37 % on f(h) = 1 + h⁻² |
| A5 | `audit_runs.checks` fails closed on missing or NaN fields (defect 29) | **done** 18 Sept. A `REQUIRED` schema runs before every physical check; "I cannot check this" is now a finding. Deleting or NaN-ing any of sixteen fields had produced no finding at all |
| A6 | A force still travelling cannot be accepted on the residual route (defect 30) | **done** 18 Sept. A history at residual 1e-8 with CL running −0.1 → 2.0 was ACCEPTED "via residual target"; it is now REJECTED |
| A7 | Moment reference compared on all three components | **done** 18 Sept. `[0.4, 3, 4]` — a moment about a point 3 m out on a 1.25 m half-span — had passed, because only x was read |
| A8 | Every counterexample committed as a regression test | **done** 18 Sept — `test_checkers_reject.py`, 25 assertions, all passing |
| A9 | `hex_volumes` checks the local Jacobian, not just summed signed volume | OPEN, not blocking. A cell with a −1.4 corner Jacobian passes the present test. All eleven meshes cleared the weaker check; this strengthens it |
| A10 | Cap-perimeter gap check compares whole vectors, not per-axis sorted coordinates | OPEN, low |

**A5–A8 are closed.** Two things are worth recording about how.

The runaway guard in A6 had to be written twice. The first version was purely relative, and it
rejected two real runs — `g36/gci_C_a0` and `g65/gci_C_a0` — whose CL sits at −0.032 and −0.0087
at zero incidence, so an absolute tail movement of 1.8e-4 reads as 2.07 %. That is the near-zero
percentage trap the review names, met in the act of fixing something else. The guard now requires
a movement to be *both* relatively large and absolutely material, and the two tests are an order
of magnitude clear of each other at both ends: the real runs move 1.8e-4 in CL, the counterexample
moves 0.35.

Writing it also surfaced a latent bug of the project's own. Inside `gate`, the name `tail` is the
force history that the `spread` and `rel` closures read — and the linear-residual block rebinds
it to a 1-D slice. Any check added after that point breaks. Nothing had been added after that
point until now, which is the only reason it had never fired. The linear-residual slice has its
own name now.

**All 52 runs from 2026-09-17 were re-gated under the new rules and all 52 remain ACCEPTED.**

### B. Identity of every paid run — **implemented in `cloud_identity.py`**

| # | item | state |
|---|---|---|
| B1 | Geometry, mesh **bytes**, mesher and solver commit, fully resolved options, physical inputs, force references | **done** — `run_manifest()` |
| B2 | `g83/F/α0` is a label, never an identity — deterministic `case_id` from the inputs, separate `execution_id` per attempt | **done** — verified that a changed mesh, geometry or setting changes the id |
| B3 | Archive copies to a `.part`, hashes the **stored** bytes, and only then renames into place | **done** — a killed job leaves a `.part`, never a plausible wrong answer |
| B4 | Reference area is each geometry's own (defect 23) | **done** — the batch refuses to start if any geometry's area is missing |
| B5 | The 17 Sept `gci_C`/`gci_M` results carried in at the same settings and commit | open — needs the analysis step, not the runner |

### C. Operational — **implemented in `cloud_batch_run.py`**

| # | item | state |
|---|---|---|
| C1 | Monotonic timing, with the wall-clock gap reported as the suspend signal | **done** — `Stopwatch` |
| C2 | Termination by process group (`start_new_session`), never `pkill -f` | **done** |
| C3 | `/proc/PID/cwd` does not identify an ADflow run | known; runs are identified by manifest |
| C4 | Disk floor checked **before** each case | **done** — 25 GiB, tested |
| C5 | Spend cap in core-hours, and a `STOP` file that works without this process | **done** — both tested |
| C6 | `--watch-memory` on every case | **done** — passed to every solve |

**And one rule that is neither B nor C:** a verdict comes from the **artefacts**, never the exit
code. ADflow exits 0 on SIGTERM, which this project has known since PLAN 0.3. On 18 September SU2
exited **1** having written its restart, surface and forces files, after 24 successful writes of
that same restart during the run — the outputs were complete and only the final write failed. A
non-zero exit disproves nothing either. `verdict_from_artefacts()` records the exit code and does
not use it.

---

## 5. What the batch must deliver, stated before it runs

So that the result cannot be graded after the fact:

1. **Observed order `p` per quantity** — CL, CD, CDp, CDv, CMy — on g83 across four levels, with
   fit residual and monotonicity reported alongside, and the certified-uncertainty field left
   **empty** for any quantity whose family fails a condition.
2. **Triplet consistency:** C/M/F against M/F/FF. If those two disagree on `p`, the solutions are
   not in the asymptotic range and the extrapolated drag is not quotable, whatever the formula
   returns.
3. **The fine-level offset across ten wings.** Tonight the C→M correction was common-mode to
   within 0.85–4.39 counts. Does that survive at F? This is the number that decides whether the
   ten-wing dataset can be corrected at all.
4. **The trailing-edge credit re-measured at F.** It was −5.27 to −8.98 counts across the fleet
   at C, and wing 83 reproduced its own prediction to 0.12 counts. Grid-converged or not?
5. **y+ at F and FF.** `s0_frac` falls 3.60e-6 → 2.13e-6 → 1.64e-6, so the tip-cap exceedance
   should resolve. Confirm on wall-masked statistics: at `gci_C` the true wall p99 is 0.671–1.156
   with 18 of 52 runs above 1.0.
6. **Iterative uncertainty**, measured, not assumed. Continuing below 1e-6 moves forces 0.073 %
   and two paths to the same target differ 0.32 % in CDp — 0.15 to 0.6 counts. The GCI anchor
   cases should be run to a tighter L2 so that the iterative part is small against the spatial
   part being measured.

---

## 6. What this batch does *not* settle

- **Validation.** Four levels give numerical uncertainty, not physical accuracy. There is still
  no low-speed 3D wing experiment in the record for a BWB.
- **Transition.** ADflow has none. The Eppler 387 runs that would judge SU2's Langtry-Menter
  models stopped unconverged and disagree with each other by 37 counts. Fully turbulent is not a
  safe upper bound: of 88 NeuralFoil sections, the turbulent/free-transition drag ratio runs
  0.46–1.97, and values below 1 mean laminar bubbles can reverse the sign.
- **Whether same-α is the right comparison.** A wing that must carry a given weight should be
  compared at the same lift and in trim, not the same incidence. That decision needs the mission
  mass and speed, and it changes which angles the *next* campaign runs — not this one.
