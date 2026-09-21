# The high-fidelity cloud batch: what is ready, what it costs, and what must be true first

Written 2026-09-18. Supersedes `reports/s8_cloud_batch.json` (2026-09-09), every figure in
which was an estimate. Every number below is measured unless it says otherwise.

The decision this batch exists to serve: **can S8 rank BWB designs by drag?** Tonight's two-grid
result says the grid error in a wing-to-wing *difference* is 0.85–4.39 counts against a
trailing-edge credit of 5.27–8.98 counts. That is the question a third and fourth level answers,
and it cannot be answered on the development host: `gci_F` needs 20.6 GiB and `gci_FF` 38.4 GiB
against 12.8 GiB available.

> **This batch is superseded. Revised 21 September, after 16 desktop solves.**
> `docs/AUDIT_2026-09-20_reliability.md` §6 and the 21 Sept 00:40 addendum in `S8_REPORT`.
>
> **The premise in the paragraph above is wrong.** "Grid error in a difference is 0.85–4.39 counts
> against a credit of 5.27–8.98" was an estimate. Measured on three wings, the credit is
> −7.21/−8.78/−8.54 counts at `gci_C` and **−2.47/−3.07/−2.61 at `gci_M`** — it loses **65–69 %** on
> the refinement already owned, so its own grid sensitivity is 5.5–6.2 counts, larger than the
> wing-to-wing spread it was being used to resolve.
>
> **The good news, and the reason to still buy compute:** vis4 halved and doubled moves absolute drag
> by 57 counts and the credit by at most **0.63** (`reports/s8_vis4_credit.json`). The error is
> genuine discretisation, not a free parameter of the scheme, so **a third grid level can measure it.**
>
> **But this batch cannot.** The eleven meshes in §1 are the **treatment configuration only**. The
> credit needs both legs on the same grid, and the χ-3 baseline does not exist at `gci_F` or `gci_FF`.
> As written the batch would refine absolute drag on ten wings — a quantity that is
> dissipation-dominated and not the claim — and still not say where the credit settles.
>
> **Re-scope:**
>
> | | as written | re-scoped |
> |---|---|---|
> | `gci_F` treatment | 10 wings × 4α = 40 | 3 wings × 4α = **12** |
> | `gci_F` baseline | **0 — not built** | 3 wings × 4α = **12 (new meshes needed)** |
> | `gci_FF` | 1 wing × 4α = 4 | 1 wing × 2α = **2** |
> | core-hours | **439** | **~255** |
>
> Cheaper and answerable. Build cost for the baseline meshes is 25–45 s each.
>
> **One gate remains before the meter starts:** the wall-normal direction diverges (C_D 208.24 →
> 209.13 → 213.33, step growing 4.7×; `gci.py` returns p = −5.97 and refuses a GCI). A global
> refinement refines that direction too, so `gci_F` bought now is a third point on a family with no
> demonstrated limit. Two or three solves localise it — CDp rising while CDv falls at fixed s0 points
> at the `o_wing`/`o_out` interface, not at the boundary layer.
>
> Also note for §2 below: **r ≥ 1.3 is not met.** The global cell-derived ratio is 1.2479 and the
> 1.300 in the level table is the near-wall spacing ratio, which is not what ASME V&V 20 defines r on.

> ## The wall-normal direction diverges on the production meshes — and it does not block this batch
>
> **Measured 2026-09-21 on three gate-ACCEPTED runs per family.** This was the one gate standing
> between the audit and a recommendation to buy. It did not clear.
>
> | | `gci_C` | +normal | ++normal | steps on C_D | verdict |
> |---|---|---|---|---|---|
> | **Family A** (cap 10.2 × s0) | 208.237 | 209.134 | 213.330 | **+0.897, +4.196** | DIVERGENT, p = 5.80 |
> | **Family B** (cap 2.04 × s0, production) | 201.737 | 202.307 | 206.499 | **+0.570, +4.192** | DIVERGENT, p = 7.52 |
>
> CDp: family A +3.930 then +6.308; family B +4.054 then +6.636. CDv converges in both (p ≈ 1.44).
>
> **The tip-cap rebuild changed nothing.** The hypothesis that the divergence was an artifact of the
> defective cap — it fixed the outboard extrusion in exactly the region the signature points at — is
> **refuted**: the second step is +4.192 counts on family B against +4.196 on family A. Identical.
>
> **And then it was diagnosed, and it does NOT block the batch.** Written after localising it, which
> reverses the "do not rent" this box said an hour earlier. The chain of measurements:
>
> 1. **Where.** All of the C_D growth is in ONE spanwise band, 0.17–0.33 of the semi-span: +11.17
>    counts out of a +10.69 total, with every other band flat or slightly falling. Within that band it
>    concentrates on the leading edge and the first half-chord (ring segments i 23–69 carry +9.65).
>    Not the tip, not the trailing-edge base (+0.75), not uniform.
> 2. **What is held.** That family refines the wall-normal direction and **holds the chordwise count
>    at 93** at every level. The directional decomposition puts **chord at 88 %** of the coarse→fine
>    CDp error and **normal at −15 %** (`s8_directional_refinement.json`). So it refines the direction
>    carrying about a tenth of the error while freezing the one carrying nearly all of it.
> 3. **The confound, measured.** The leading-edge cell aspect ratio — chordwise spacing over first-cell
>    height, at the station where the change lives:
>
> | family | nose aspect ratio | growth |
> |---|---|---|
> | wall-normal only, chord held | 25.1 → 32.1 → **41.1** | **1.63×** |
> | **global, all directions at r = 1.3** | 25.1 → 23.5 → 28.3 → 26.3 | **1.20×** |
>
> The directional family's aspect ratio grows 64 % in exactly the region where the CDp change appears.
> The global family holds it. **So the divergence is what happens when the non-limiting direction is
> refined alone — not a demonstrated property of the grid family**, and it does not transfer to a
> global refinement, whose two measured points move the OTHER way (CDp 110.794 → 89.288).
>
> **Consequence: this does not justify refusing the batch.** What it does justify is one cheap test
> first — **wall-normal refinement on top of a chord-refined mesh, ~1.5 h on this host.** If the
> divergence survives that, it is real and the batch waits. If it vanishes, the directional families
> are diagnostics only and must never again be read as convergence studies.
>
> Recorded plainly because this box has now said both things: the divergence is a measurement, the
> inference from it to the global family was wrong, and the correction came from asking *where* rather
> than *how much*.
>
> ## A second thing, found the same night and NOT a reason to stop
>
> **The worst cells in this family get worse as it refines, and the preflight cannot see it.**
> `reports/s8_mesh_quality_ladder.json`, geometry 83, family B:
>
> | | `gci_C` | `gci_M` | `gci_F` | `gci_FF` |
> |---|---|---|---|---|
> | scaled Jacobian **min** | 0.0090 | 0.0063 | **0.0043** | **0.0025** |
> | scaled Jacobian p001 | 0.0142 | 0.0109 | 0.0084 | 0.0056 |
> | min cell volume (m³) | 4.4e-15 | 2.0e-15 | 9.3e-16 | 4.2e-16 |
> | *median* scaled Jacobian | 0.944 | 0.950 | 0.954 | **0.957** |
> | *neighbour volume ratio p99* | 1.331 | 1.248 | 1.208 | **1.207** |
> | folded cells | 0 | 0 | 0 | **0** |
>
> Every metric §1 records — folds, wall-layer error — and every bulk metric **improves** all the way
> up the ladder. The worst-cell conditioning degrades by about 1.4× per level, and at `gci_F` roughly
> 1,400 cells sit below a scaled Jacobian of 0.0084. Neither `s8_cloud_meshes.json` nor
> `s8_robustness_screen_gciF.json` records a scaled Jacobian at all, so "0 folded, clean: True" and
> "61/61 built cleanly" are true and do not speak to this. **That is PLAN §0.1 again, inverted: the
> metrics measure the bulk and nothing measures the worst cell, which is what a linear solver feels.**
>
> **RETRACTED, same night.** This box first said a mesh of this family "failed to converge" and that
> the batch should not be bought. **That was my misreading, not a finding.** I read column 9 of the
> ADflow iteration table as the total residual; the header says it is `Res rhou`. Its mild upward drift
> over the tail became "the residual rose monotonically, the solver walked away from a solution", and
> on that basis I stopped the run at iteration 224 — where the comparable family-A run had needed 266.
>
> What `convergence_gate.py` says about that same run, which I should have run first:
>
> | | |
> |---|---|
> | verdict | REJECTED |
> | `not_diverging` | **pass** |
> | `no_growing_oscillation` | **pass** |
> | `solver_frozen` / `linear_solve_dead` | **False / False** |
> | relative residual | **4.46e-6** against a 1e-6 target |
> | CL / CD settled over the tail | **0.0008 % / 0.0010 %** |
> | equations short of limit | `rhoE` only — 5.39 orders against 6.0 |
>
> So it was not diverging and not frozen. It was a run four and a half times from its stopping rule
> with settled forces, rejected on the energy equation's order and the residual target. Energy dropping
> 5.39 orders is genuinely below this campaign's measured range of 6.12–7.48 over 77 runs, so it is
> worth noting — but it is not a stall and it says nothing about whether `gci_F` converges. Re-running.
>
> **The conditioning trend below is real and stands. The stall it was attached to does not.**
>
> `gci_F` (0.0043) and `gci_FF` (0.0025) are worse conditioned than that mesh, which looked like a
> second reason to stop. **That inference fails too, and for an independent reason:**
>
> | mesh | worst cell is at | cells below 0.01 | converges? |
> |---|---|---|---|
> | `gci_C` | `o_wing` **outermost** normal layer (j 63/64), ring i 23–24, mid-span | 6 | **yes** |
> | `gci_C_normal_s0_b` | `o_wing` **outermost** normal layer (j 82/83), ring i 23–24, mid-span | 18 | no |
>
> Same block, same ring index, same span station, same **outermost** layer — the O-block's far-field
> edge, a low-gradient region. `o_out` (0.52) and `cap_out` (0.049) are healthy in both. So the
> poorly-conditioned cells are a small, localised, **pre-existing** feature at every level, including
> levels that converge perfectly well. Eighteen cells at the far-field boundary are unlikely to stall a
> solver that tolerates six of them in the same place.
>
> **So: the scaled Jacobian degrading up the ladder is real, it is invisible to this plan's preflight,
> and it should be recorded — but it is not evidence that `gci_F` will fail to converge.** The stall's
> cause is not established. The other differences in that mesh are a 5× finer first spanwise cell at
> the tip (cap 2.04 vs 10.2 × s0) and a 4× finer trailing edge, either of which is a better suspect
> than 18 far-field cells.
>
> **What this does and does not change.** It does not block the batch on conditioning grounds. It does
> leave this plan's own largest stated risk — "ANK-only is proven to 1,172,856 cells" — now
> demonstrated to bite on an 788k-cell mesh of this family, which is a stronger warning than a cell
> count. `gci_C_normal_s0_b` fits this host and is the free probe: if a solver setting converges it,
> the batch needs a setting; if nothing does, find the cause before buying a level that cannot be
> restarted cheaply.

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

**Run one `gci_F` case and one `gci_FF` case, end to end, and stop.** Cost: **31.4 core-hours**
(8.8 + 22.6), about **7 %** of the batch. An earlier draft of this section said 20 core-hours and
under 5 %; that was wrong, and the runbook's figure is the correct one. It is the only way to test the three extrapolations this plan rests on:

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
| B5 | The 17 Sept `gci_C`/`gci_M` results carried in at the same settings and commit | **done** — `gci_four_level.py`; the compatibility check passes on the real pair and the four-level path is verified against a constructed answer |

### C. Operational — **implemented in `cloud_batch_run.py`**

| # | item | state |
|---|---|---|
| C1 | Monotonic timing, with the wall-clock gap reported as the suspend signal | **done** — `Stopwatch` |
| C2 | Termination by process group (`start_new_session`), never `pkill -f` | **done** |
| C3 | `/proc/PID/cwd` does not identify an ADflow run | known; runs are identified by manifest |
| C4 | Disk floor checked **before** each case | **done** — 25 GiB, tested |
| C5 | Spend cap in core-hours, and a `STOP` file that works without this process | **done** — both tested |
| C6 | `--watch-memory` on every case | **done** — passed to every solve |

**B5, the last item, is now closed.** `gci_four_level.py` combines the levels and computes the
study the batch exists to produce. Two things it will not do:

- **It refuses to combine runs that are not the same case.** Geometry, incidence, Mach, Reynolds,
  turbulence model and variant, reference area and moment reference must all agree before any
  level joins the family. Tested by changing one level's turbulence model to SST: it stops and
  names the field. Picking the three meshes with the most cells is not a grid-convergence study.
- **It refuses to quote a number it is not entitled to.** With two levels it reports
  `TREND_ONLY` and no band. With three or more it reports the *observed* order, and
  `certified_uncertainty_percent` stays empty for any quantity whose family fails a condition —
  including the divergence test that once let `f(h) = 1 + h⁻²` through as p = +2, "ok", GCI 37 %.

Verified against a constructed family, `CD = 0.0150 + 0.00080 h²` at r = 1.300 across four levels:
both triplets return **p = 2.0000** and an extrapolate of **0.0150000**, the exact constructed
answer, and agree with each other to a spread of 0.000. On the real `gci_C`/`gci_M` pair the
compatibility check **passes** — the two are genuinely the same case — and the analysis correctly
reports `TREND_ONLY`, because two levels cannot give an observed order.

> **What the unit test could not catch, 20 September.** All of the above is true and the tool does
> refuse what it should. But it was passing the **near-wall spacing ratio 1.300** into the band while
> recording the global cell-derived 1.2479 in the same file — and a unit test built at r = 1.300
> cannot detect a wrong choice of r, because the constructed family and the assumed ratio agree by
> construction. The α-0 C_D band was reported as 54.8 % where the correct ratio gives 67.9 %: the one
> substitution that shrinks the reported uncertainty. Fixed; `asme_r_requirement` now reports
> `met: false` explicitly. The lesson is narrow and worth keeping: **a verification case that
> supplies its own r verifies the formula, not the input.** Defect 29.

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
