# S8 — desktop handoff

Written 2026-09-05. Everything below is committed; nothing depends on the
laptop session that produced it.

## Where S8 stands in one paragraph

The O-H grid builds, and a four-point alpha sweep on `lhs100_seed42[83]` at
`oh_L3` produced a lift curve that agrees with AVL on the identical loft. Three
of four angles converged; one stalled in a way that is not yet explained. No
number in that sweep is grid-converged, and that is now the binding constraint.
Two defects were found and fixed on the way (the lift axis, and a spanwise
leading-edge spacing cliff), and two mistakes of the assistant's own were caught
and corrected (a moment sign error, and a convergence readback typo).

## What is settled

| | |
|---|---|
| lift curve, 4 angles | slope 0.0692 / 0.0701 / 0.0704 per deg, linear to 1.7 % |
| AVL cross-check | gap closes with incidence, 1.9 % apart at alpha 8 |
| neutral point | CFD 0.3561 m (raw integration), AVL 0.3359 m — **3.7 % of MAC apart** |
| static stability | **UNSTABLE** about x = 0.4 m, by both codes |
| cp physical bound | 3 leading-edge cells at cruise, 36 at alpha 8; worth 0.27 % of CDp |
| mesh | 567,256 cells, 0 inverted, min cell / s0 = 19.3 |

Reference contract, verified identical on all four runs: `areaRef`
0.394918242017589 m2 (half model), moment reference (0.4, 0, 0) m, `chordRef`
0.9 m. AVL matches on area (0.78984 vs the full 0.789836) and was rerun taking
moments about the same point.

## What is NOT settled, in priority order

1. **Nothing is grid-converged.** CDp moved 5.2 % and CMy 18 % from one mesh
   respacing. No drag or moment figure may be quoted, and that includes the
   neutral point, which is now a design input.
2. **The alpha 4 Newton-Krylov stall.** Residual froze at 5.2371905e-05 to eight
   significant figures, NK step length 0.00, linear residual 1.000 — the Krylov
   solve stopped reducing. Not the lift-axis defect: alpha 4 carries no
   sideslip. Undiagnosed. Candidates untested: the tip cap carries one surface
   cell at scaled Jacobian 0.049, and cell volume spans ~1e15 across the domain.
3. **Leading-edge resolution is operating-point dependent.** `target_le_turn_deg
   10` was calibrated at cruise; at alpha 8 the over-bound cell count goes 3 →
   36 and the peak excess doubles. The level definitions treat resolution as a
   property of the mesh alone, and it is not.
4. **`oh_L1`'s refinement ratio is 1.3523**, 0.0023 over the ADR-0018 ceiling of
   1.35. It needs a small reduction before it can be used in a convergence
   study.

## UPDATE 2026-09-05: the convergence family is rebuilt, and it FITS HERE

The `oh_L3 / oh_L2 / oh_L1` ladder was never a convergence family.  It refined
the three directions at 1.31 / 1.33 / 1.25 AND moved the leading-edge target
from 10 to 8 to 6 degrees and the trailing-edge fraction from 0.004 to 0.003.
With the resolution law changing between levels, a shift in CD cannot be
attributed to the grid and Richardson extrapolation over it means nothing.

`strategy_s8.refined_level` now generates the family from one ratio, holding
every law fixed.  `gci_M` IS `oh_L3` bit for bit, so the alpha sweep already run
is the medium level.

| level | cells | inverted | LE turning | memory |
|---|---|---|---|---|
| `gci_C` | 298,712 | 0 | 10.013 deg | 2.95 GiB |
| `gci_M` | 567,256 | 0 | 10.019 deg | 5.61 GiB |
| `gci_F` | 1,111,152 | 0 | 10.018 deg | **10.99 GiB** |

Effective refinement 1.2383 and 1.2512 -- consistent with each other, both in
band, against the legacy ladder's 1.2954 and 1.3523 (the second out of band).

**The fine level needs 11.0 GiB against the legacy `oh_L1`'s 24.6, so the whole
family fits on a 15.3 GiB host.**  The grid-convergence study may not need the
desktop at all.  It is tight at the fine level -- close other work first -- and
the desktop is still the safer place to run it.

Use `--level gci_C` and `--level gci_F` in the commands below; `gci_M` is
already solved.

## The job for the desktop: grid convergence on index 83

This is why it needs the desktop. Measured at 10,620 bytes/cell:

| level | cells | memory | fits on 15.3 GiB? |
|---|---|---|---|
| `oh_L3` | 567,256 | 5.5 GiB | yes — already run |
| `oh_L2` | 1,056,480 | **11.2 GiB** | marginal |
| `oh_L1` | 2,316,902 | **24.6 GiB** | **no** |

```bash
cd <repo>
R=$(pwd)

# 1. build the two finer levels (about 30 s each; the mesher is cheap)
for L in oh_L2 oh_L1; do
  .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/build_volume.py \
    --level $L --index 83 --out $R/AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh
  /home/mike/miniconda3/envs/mach-aero/bin/python \
    AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/write_cgns.py \
    --blocks $R/AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/${L}_blocks.npz
done

# 2. solve. alpha 0 first on each level -- it is the cheapest and the one with a
#    predecessor to compare against.
for L in oh_L2 oh_L1; do
  for A in -2 0 4 8; do
    /home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
      /home/mike/miniconda3/envs/mach-aero/bin/python \
      AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py \
      --grid $R/AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/${L}_volume.cgns \
      --alpha $A --out $R/AERIS_MESH_STUDY/artifacts/s8_cfd/${L}_a${A} \
      --i-have-authorization
  done
done

# 3. gate, summarise, plot
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/convergence_gate.py \
  --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/oh_L*_a*'
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/plot_sweep.py
```

**Authorization.** `POLICY.yaml` `heavy_work.exceptions.run-s8-corrected-sweep`
covers the alpha sweep on **`oh_L3`**. Grid convergence on `oh_L2` and `oh_L1`
is outside it and needs its own entry. Do not treat the existing one as
covering it.

**Cost.** About 30 min per angle at `oh_L3` on 6 ranks. `oh_L2` is 1.9x the
cells, `oh_L1` 4.1x, and the solve does not scale linearly — budget generously.

## Read the results honestly

`solve_s8.py` verifies the freestream direction before spending the run and
refuses if it is wrong, and records what it built in `result.json`. Trust that
block; it exists because a missing `liftIndex` voided every earlier S8 result.

Convergence is judged by `convergence_gate.py`, **not** by a bare residual
number. It asks for 5 orders AND stable forces AND no divergence, and reports
`ACCEPTED_SOLVER_FROZEN` separately when a residual is frozen rather than
merely flat — because "the forces stopped moving" has two causes and only one of
them is convergence.

At `oh_L3` the alpha 0 values to compare against are:

| CL | CD | CDp | CDv | CMy |
|---|---|---|---|---|
| −0.159963 | 0.020838 | 0.011841 | 0.008996 | +0.001280 |

If CD at `oh_L2` differs from this by more than a few per cent, that is the grid
convergence signal, not an error.

## Also in flight on the laptop

A 100-design meshing robustness screen (`robustness_screen.py`), testing whether
S8 builds a valid grid across the whole development set or only on index 83.
That is the ADR-0011 section 6.1 determinism gate — the one that ended S2 — and
S8 had never been measured against it. It already found defect 18 on the first
design it touched: `build_volume.py` was calling `strategy_s6.build_locked_surface`,
which builds an entire S6 `candidate_c01` surface purely so the pyGeo loft could
be read off the end of it, and S8 was inheriting S6's span-clustering
constraints for free. On `lhs100_seed42[0]` that raised *"42 span cells capped
at 0.025 m cannot cover the 1.14972 m quarter-chord line"* and S8 never got to
build anything. Now uses `build_pygeo_case`, which is the loft alone. Index 83
rebuilds bit-identically after the change.

Results land in
`05_s6_cfd_qualification/reports/s8_robustness_screen.json`.

## Governance

- `ADR-0018` — the O-H topology decision. Stands.
- `ADR-0019` — the lift axis and the leading-edge spacing, plus two addenda:
  the sweep result, and defect 17 (the moment sign error).
- Reports: `s8_lift_index_defect_20260904`, `s8_cp_excess_diagnosis_20260904`,
  `s8_corrected_sweep_20260905`, `s8_convergence_gate_20260905`,
  `s8_robustness_screen`.
- Figure: `05_s6_cfd_qualification/viz/s8_sweep_polars_20260905.png`.
- The hold-out `round_c_lhs10_seed42` remains locked and untouched.

**`artifacts/` is globally gitignored and gets wiped.** Anything worth keeping
must be copied into `05_s6_cfd_qualification/` and, for images, force-added past
the png ignore. Two hours of results were sitting in the ignored tree before
this was noticed.
