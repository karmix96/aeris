# S7 overnight — status 2026-09-04 ~07:50 EEST

## DONE: three meshes, all built and accepted on this desktop

| level   | cells     | cell ratio | build time |
|---------|-----------|-----------|------------|
| xcoarse | 610 612   | -         | 3m46s      |
| mcoarse | 963 317   | 1.578     | 5m59s      |
| coarse  | 1 549 111 | 1.608     | 9m50s      |

Policy minimum is 1.35 on cell count, so both steps clear it. Linear h ratios
1.164 and 1.171 are close to uniform. Committed as 6b33188.

`medium` and `fine` remain unbuildable here: 12.01 and 13.63 GiB against 11.57
available. The family is closed up between the rungs this host does build rather
than stretched below them, because a rung below xcoarse would push y+ p95 to
about 1.1 against a 1.0 gate.

## RUNNING: the anisotropy screen — this is the real blocker

The first CFD ran the shipped policy config and STALLED, exactly as documented:
1.93 orders and flat at rms -5.07 after 11 500 iterations, against a requirement
near -9.66. That is the known S7 plateau, and the cause is already diagnosed in
the code: the shortlisted Newton-Krylov variants were selected on a laptop mesh
and "plateaued at ~2.1 orders on a mesh 119x more anisotropic".

The fix has been sitting unscreened in `ANISOTROPY_SHORTLIST`: LINELET
preconditioning. Screening all three now on xcoarse, 4000 iterations, 1 rank,
3 workers.

Early signal at ~100 iterations, against 11 500 for 1.93 orders on the old
config:
  L_nk_linelet      1.09 orders
  M_nk_linelet_cfl  0.87
  K_linelet         0.76

Log: aniso.log   Results: s7/aniso_screen.json

## Rank finding, measured twice
6 ranks is SLOWER, not faster: 3.75 s/iter at 6 against 2.6 at 1 on the same
mesh. S7's own rank sweep said the same. Every rank replicates the whole mesh,
so ranks cost memory and buy nothing here. Single rank is fastest and smallest.

## Your decisions waiting
1. Adopt the screen winner into POLICY.yaml `su2.numerical_method` (M1C). The
   guide requires this be done from coarse measurements and deliberately, never
   silently, so I have not written it.
2. Whether a 1.17 linear ratio is acceptable for GCI, or whether the study
   reports the raw envelope instead. Less grid separation means iterative error
   must be shown small before any GCI is believed.
