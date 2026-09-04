# S8 O-H CFD — runbook

**State on 2026-09-04.** One alpha 0 point has run and is partly withdrawn; both
alpha 8 attempts are void. See
[`ADR-0019`](../../00_governance/decisions/ADR-0019-s8-lift-axis-and-le-spacing.md).

| | |
|---|---|
| alpha 0, `artifacts/s8_cfd/oh_L3_a0` | converged; cp verdict, CD, CDp, CDv, CMy and y+ **stand**; **CL withdrawn** |
| alpha 8, `..._a8_nCycles4000_unconverged` | **void** — solved sideslip |
| alpha 8, `..._a8` | **void** — solved sideslip, and stalled |

Both alpha 8 runs applied angle of attack in the x–y plane, which is spanwise on
this mesh, against a root symmetry plane that forbids spanwise crossflow. That
is defect 14. It is fixed in `solve_s8.py` and the fix is now checked at runtime
rather than assumed.

## 0. Authorization — read before anything else

`05_s6_cfd_qualification/POLICY.yaml` blocks heavy work. The
`run-s8-first-point` exception was written for **one alpha 0 point** and has been
consumed. The corrected sweep is new heavy work.

`policies/s8_oh_corrected_sweep_v1.yaml` is written and deliberately **unsigned**
(`authorized_by: null`, `status: PENDING`). Nothing in this repository may treat
it as an authorization. To authorize, a human adds to `POLICY.yaml` under
`heavy_work.exceptions`:

```yaml
    run-s8-corrected-sweep:
      policy: policies/s8_oh_corrected_sweep_v1.yaml
      decision: AERIS_MESH_STUDY/00_governance/decisions/ADR-0019-s8-lift-axis-and-le-spacing.md
      authorized_by: principal_investigator
      authorized_on: <date>
      scope: >-
        The corrected alpha sweep on the rebuilt S8 oh_L3 grid, on
        lhs100_seed42[83] at the nominal mission operating point. Authorizes
        lift-curve measurement and a repeat of the surface-pressure bound check.
        Does NOT authorize tip-cap viscous quantities, grid convergence, a
        family freeze, a hold-out unlock, or any paper claim.
      minimum_mpi_processes: 6
```

and fills the same two fields in the policy file.

## 1. Free checks — run these first, they cost seconds

**The lift axis, measured against the solver itself.** No solve; `nCycles 0`.

```bash
cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
/home/mike/miniconda3/envs/mach-aero/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/verify_lift_index.py \
  --grid AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/oh_probe_volume.cgns
```

Expect `liftIndex 3` to give `(0.990268, 0.000000, 0.139173)` at alpha 8 and
`liftIndex 2` to give `(0.990268, 0.139173, 0.000000)`. The second is the
corrupted run reproduced on demand.

**Mesh acceptance on the rebuilt grid.**

```bash
/home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 4 \
  /home/mike/miniconda3/envs/mach-aero/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/preflight_adflow.py \
  --grid AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/oh_L3_volume.cgns
```

## 2. Rebuild the mesh, if it is not already the 2026-09-04 one

The tracked `oh_L3` has been rebuilt with `smooth_le_spacing`. Its summary must
report `le_spacing_smoothing.worst_step_after` at 1.15 and
`stations_clamped` at 11. If it does not, rebuild:

```bash
cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
L=oh_L3   # or oh_probe, oh_L2, oh_L1

.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/build_volume.py --level $L
/home/mike/miniconda3/envs/mach-aero/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/write_cgns.py \
  --blocks AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/${L}_blocks.npz
```

## 3. The corrected sweep, once authorized

Four points, about 30 minutes each on 6 ranks — roughly **2 hours** for the set,
from the measured 1808 s of the alpha 0 run at the same cell count.

```bash
cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
for A in -2 0 4 8; do
  /home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
    /home/mike/miniconda3/envs/mach-aero/bin/python \
    AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py \
    --grid AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/oh_L3_volume.cgns \
    --alpha $A \
    --out AERIS_MESH_STUDY/artifacts/s8_cfd/oh_L3_fixed_a${A} \
    --i-have-authorization
done
```

`solve_s8.py` now verifies the freestream direction after `setAeroProblem` and
before the solve, and refuses to run if it is wrong. A bad setup costs seconds,
not hours. The realised directions are written into each `result.json`.

**Run alpha 0 first and check it before starting the others.** It is the only
point with a predecessor to compare against, and three numbers must reproduce
essentially unchanged, because the flow field at alpha 0 does not depend on the
lift axis:

| | previous | expected |
|---|---|---|
| CD | 0.021416 | same to ~4 decimals |
| CDp | 0.012494 | same |
| CMy | 0.001085 | same |
| **CL** | 0.032301 | **about −0.161**, not 0.032 |

If CD moves materially, something other than the lift axis changed and the
sweep should stop. The leading-edge respacing does perturb the field slightly,
so exact agreement is not expected — a shift in the fourth decimal of CD is
the respacing; a shift in the second is a problem.

## 4. Read the results

```bash
# where cp exceeds its physical bound, and what it costs in drag
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/locate_cp_excess.py \
  --surface AERIS_MESH_STUDY/artifacts/s8_cfd/oh_L3_fixed_a0/s8_a0_000_surf.cgns \
  --le-index 44
```

Baseline to beat, from the pre-fix alpha 0 run:

| | cells over bound | peak excess | share of CDp |
|---|---|---|---|
| leading edge | 11 | 0.1706 | 9.8 % |
| trailing-edge corners | 19 | 0.1011 | 0.01 % |

The trailing-edge corner cells are **expected to remain**. They sit at a C0 kink
that absorbs 86–106 degrees of turning in one cell, refinement cannot reduce
that, and they carry 0.01 % of pressure drag. Do not read their survival as a
failure of the fix; the leading-edge eleven are the test.

## 5. What this still cannot settle

- **Tip-cap viscous quantities.** The cap's wall normal IS the spanwise
  direction. Measured cap y+ reached 4.2 against the OML's 0.9. Skin friction on
  the cap, and any drag decomposition including it, are not quotable.
- **Grid convergence.** `oh_L2` at 1.06 M cells needs 11.2 GiB and `oh_L1` at
  2.32 M needs 24.6 GiB, against 15.3 GiB here. Desktop or a coarser family.
  `oh_L1`'s refinement ratio is also 1.352, which is 0.002 over the ADR-0018
  ceiling and out of band until reduced.
- **Which fix moved cp.** Both land in the same solution.
- **Anything against experiment.** There is no experimental comparison anywhere
  in S8.
