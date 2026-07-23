# Mesh family v2 — cap4 wide-wrap, 5 levels (2026-07-23)

The surface recipe selected by the 2026-07-22/23 study, expanded into a
5-level family suitable for grid-convergence work. Derivation and evidence:
`SURFACE_MESH_LAWS.md` (laws 1-15).

**Status: surface validated, volume NOT yet marched.** Every level below
builds and passes surface QC, and the L3 recipe holds 100% success over 50
sampled design-space geometries. No level has been through pyHyp.

---

## The five levels

| level | points_per_side | spanwise_panels | cap_wrap_points | tip_radial_points | surface cells |
|---|---|---|---|---|---|
| **L1_coarse** | 25 | 8 | 11 | 5 | 7,516 |
| **L2_smoke** | 33 | 12 | 15 | 7 | 15,352 |
| **L3_medium** | 49 | 16 | 21 | 9 | 30,608 |
| **L4_fine** | 65 | 24 | 29 | 13 | 61,592 |
| **L5_production** | 97 | 32 | 43 | 17 | 122,712 |

Held constant at every level (see "why" below):

    oml_topology          cap4
    spanwise_allocation   proportional
    cap_wrap_x            0.15
    tip_smooth_iters      20
    te_thickness          0.005

Volume side, family-wide (one policy, no per-case tuning):

    epsE   3.0     <- NOT the shipped 6.0; see the epsE law
    epsI   6.0
    cMax   0.5
    volSmoothIter    1200
    nConstantStart   3

## Refinement ratio

    cells   7,516   15,352   30,608   61,592   122,712
    ratio        2.04     1.99     2.01     1.99
    linear r     1.43     1.41     1.42     1.41

**r ~ 1.42, essentially constant** — on the 1.4 target used for GCI
(Celik et al. 2008). Cell count doubles per level, so a 3-grid GCI study
costs L3+L4+L5 or L1+L2+L3 depending on budget.

## Measured quality (baseline_bwb_25, seed 100)

| level | OML shape | OML skew | OML AR | growth | TE angle | tip jac | tip skew | tip AR |
|---|---|---|---|---|---|---|---|---|
| L1_coarse | 0.496 | 0.625 | 3.2 | 1.407 | 154.0 | 0.133 | 0.901 | 11.7 |
| L2_smoke | 0.466 | 0.630 | 3.3 | 1.369 | 148.8 | 0.139 | 0.900 | 12.4 |
| L3_medium | 0.491 | 0.633 | 3.5 | 1.407 | 140.2 | 0.126 | 0.902 | 14.6 |
| L4_fine | 0.474 | 0.636 | 3.5 | 1.407 | 127.3 | 0.129 | 0.904 | 14.5 |
| L5_production | 0.483 | 0.637 | 3.8 | 1.407 | 104.0 | 0.111 | 0.908 | 17.0 |

**The family is geometrically self-similar**, which is the property GCI
actually requires: OML Shape 0.466-0.496, aspect ratio 3.2-3.8, growth
1.369-1.407 and tip skewness 0.900-0.908 are all effectively flat across a
16x range of cell count. Only the trailing-edge turn improves with
refinement (154 -> 104 deg), which is correct behaviour — the same geometry
resolved better.

Remember when quoting these: seed 100 is the **best** geometry in the design
space (law 15). The 50-sample median OML Shape for L3 is **0.231**, not 0.49.

## Why these parameters scale, and these do not

**Scale with the family** — everything that sets cell size:

* `points_per_side`, `spanwise_panels` — the two resolution controls.
* `cap_wrap_points` — **must** scale. It was fixed at 17 in the first
  attempt and OML aspect ratio then degraded 3.5 -> 8.1 from L2 to L5,
  because the wrap block kept 17 points over 15% chord while the chord
  blocks refined. The rule is equal cell size across the seam:

      cap_wrap_points ~ points_per_side * cap_wrap_x / (0.5 - cap_wrap_x)
                      = points_per_side * 0.15 / 0.35

* `tip_radial_points` — **must** scale. Fixed at 9 it left tip aspect ratio
  running 9.9 -> 32.1 across the family, because the collar's
  circumferential resolution follows the OML while its radial resolution
  did not. This overturns the older "the tip cap does NOT coarsen with the
  family" policy from `aeris.mesh.presets`: that policy is right for the
  cap's *geometry* (`cap_wrap_x`, `te_thickness` tile a fixed-size feature)
  and wrong for its *resolution*.

**Held constant** — everything that sets geometry rather than resolution:

* `cap_wrap_x = 0.15` — a seam location. Changing it per level would change
  the blocking, not the grid density, and break self-similarity.
* `te_thickness = 0.005` — a geometric property of the aircraft (0.5% chord;
  see the TE law). It must be identical at every level or the levels are
  not the same aircraft, which would invalidate any GCI study.
* `spanwise_allocation = proportional` — a rule, not a count.
* `tip_smooth_iters = 20` — cosmetic relaxation, converged by 20.

## What is still wrong at every level

These are constant across the family and across the design space, and are
documented limits rather than open questions:

* **tip skewness ~0.90** — laws 12-14. Not fixable by any blocking
  arrangement; needs a rounded tip geometry or an overset tip cap. Constant
  across all 50 sampled geometries, so it is a quality ceiling, not a
  robustness risk.
* **TE normal rotation 104-154 deg** — the blunt-TE turn. Improves with
  refinement. `te_base_points` is the right lever but needs an absolute
  thickness floor first (law 10).
* **growth ratio ~1.4** — now isolated to the TE wrap block after the
  spanwise fix (law 11).

## Not yet wired as presets

These are **not** in `src/aeris/cfd/presets/data/` yet. Two blockers, both
deliberate:

1. `GRID_LEVELS` has only three `coarsen=1` entries (smoke/fine/production,
   N=129/193/257). A 5-level family needs five, with the wall-spacing law
   `s0_frac = 4.4e-6 * (97 / points_per_side)` applied per level:

       L1  N=65   s0_frac 1.71e-5
       L2  N=97   s0_frac 1.29e-5
       L3  N=129  s0_frac 8.71e-6
       L4  N=193  s0_frac 6.57e-6
       L5  N=257  s0_frac 4.40e-6

2. `mesh_family` presets must share one march policy by design (C1/C2). The
   epsE 6.0 -> 3.0 move therefore has to happen for every member at once,
   and should be validated by a march first.

Both are one coherent change, best done together with a canary extrusion.

## Metric names corrected 2026-07-23

What this document calls the OML/tip quality number is Verdict's quad
**Shape** metric (`min_shape_metric`), not the scaled Jacobian — see the
METRIC CORRECTION section of `SURFACE_MESH_LAWS.md`. Every level scores
**3/4** on the corrected target set, missing only growth ratio.
