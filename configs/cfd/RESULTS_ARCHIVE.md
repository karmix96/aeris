# CFD verification results — archived record (2026-07-19/20)

**The run directories this describes were deleted on 2026-07-22** in a
deliberate clean-slate reset before the first full DoE campaign. This file
is the surviving record of what those runs established, and it lives in
`configs/` (tracked) rather than `data/cfd_cases/` (gitignored) precisely
so a `rm -rf` of the artifacts cannot destroy the findings again.

Every number below was produced by the `aeris cfd` suite with a full
provenance chain (`*_effective_options.json`, `solve_report.json`,
`verification.json`, `case_manifest.json`). The artifacts are regenerable
from the case YAMLs in this directory — see `RETENTION.md` for what is
kept versus recomputed, and `RUNBOOK.md` for the commands.

**These results are historical, not current.** They were produced with the
`epsE=6.0` pyHyp default, which was shown on 2026-07-22 to be the cause of
the localized trailing-edge cell inversion (see `SURFACE_MESH_LAWS.md`).
Wing/BWB mesh results below therefore predate that fix. The 2D NACA0012
validation is unaffected — it uses an airfoil O-grid, not the cap4 wing
topology.

## naca0012_tmr_a10/  — the validation anchor (ADflow)
NACA 0012 (NASA TMR closed-TE geometry), α=10°, M=0.15, Re=6e6, SA.
**CL = 1.0918 vs TMR CFL3D 1.0909 (+0.08%), CD = 0.01316 (+8.5 counts)**
— converged at the documented 2e-6 relative target
(`configs/cfd/validation_naca0012_tmr.yaml` has the measured
force-vs-residual ladder).

ParaView:
- `surface/wing_vol_smoke.cgns` — the pyHyp O-grid (513×2×193, march
  valid, zero low-quality layers)
- `solve/aeris_cfd_000_surf.cgns` — surface solution: color by
  **CoefPressure / SkinFrictionMagnitude / YPlus** (check y+ ≤ ~1)
- `solve/aeris_cfd_000_vol.cgns` — full volume solution
- `solve/adflow_run.log` — residual history (Res_rho = 5th float column)

## naca0012_tmr_a10_su2/  — same grid, second solver (SU2 8.5.0)
The identical O-grid converted to `mesh.su2` (node set preserved; the
one-cell strip is y/z-swapped + j-reversed so SU2's lift-z convention and
right-handedness hold — `mesh.convert.json` documents everything).
**Cross-solver result (same grid, independent codes): CL 1.0945 (SU2) vs
1.0918 (ADflow) vs 1.0909 (NASA TMR) — 0.25% inter-code spread.  CD
0.01790 vs 0.01316 (+47 counts): drag is scheme-sensitive; a
scheme-matched CD comparison is the documented follow-up.**  SU2's
side-force ~1e-22 confirms clean symmetry.  Converged to rms[Rho] -7.0
in 2049 iterations.  `cross_solver_summary.json` (one level up) holds
the normalized table.
ParaView: `.vtu` volume output; `history.csv` for convergence + CL/CD.

## GCI ladder (naca0012_tmr_a10_coarse / _a10 [medium] / _a10_fine)
Three-grid family, r ~ 1.4 in all directions (Celik et al. 2008
procedure; `gci_study_naca0012.json` holds both studies):

    grid    CL       CD        (both converged, ADflow)
    coarse  1.1093   0.01357
    medium  1.0918   0.01316   <- the validation anchor vs TMR 1.0909
    fine    1.0821   0.01301

- CL: monotone, observed order p = 1.75 (theoretical 2), GCI_fine 1.40%,
  Richardson CL_inf = 1.0700.  The extrapolated offset vs TMR (-1.9%) is
  the documented 100-chord farfield bias (TMR grids reach ~500c / use
  farfield vortex corrections) — the designated follow-up study
  (march_dist_factor 500 or ADflow's vortex correction).
- CD: monotone, p = 2.90, GCI_fine 0.88%, CD_inf = 0.01292
  (TMR 0.01231).
- Fine-grid meshing required native pyHyp `cornerAngle=110` via raw
  pass-through (finding documented in
  `configs/cfd/validation_naca0012_tmr_fine.yaml`).

## bwb_smoke_a2_adflow/  — BWB half-model RANS (ADflow)
Smoke-family cap4 mesh (grid: `data/meshes/bwb_smoke/surface/
wing_vol_smoke.cgns`), α=2°, M=0.2, Re=1e6, ANK-only (NK OOMs at this
mesh size on 16 GB — see solver notes in the user guide, ch. 19).
**CL = 0.3980, CD = 0.02640, CMy = −0.3423**, 6.0 orders dropped.
ParaView: `aeris_cfd_000_surf.cgns` (cp/cf/y+), `aeris_cfd_000_vol.cgns`.

## naca0012_gmsh_tri/  — unstructured Gmsh mesh (no solve yet)
True-2D triangle mesh + quad boundary layer, `surface/mesh.su2`
(SU2-native; gmsh can also re-open it: `gmsh surface/mesh.su2`).

## sensitivity_studies/  — post-hoc, zero-extra-compute artifacts (2026-07-20)
- `iterative_tolerance_{coarse,medium,fine}.json` — force-vs-stopping-
  criterion table reconstructed from the *existing* GCI-ladder logs (no
  rerun: a completed log already contains the answer for every looser
  tolerance target). CL settles to within ~0.2% of its final value by 5.5
  orders on all three grids.
- `determinism_check.json` — mesh and solver determinism, both confirmed:
  the surface mesh is byte-identical across reruns; the pyHyp volume-mesh
  CGNS differs in raw bytes but every one of its 29 HDF5 datasets (all
  coordinates/connectivity) is bit-identical (the byte diff is non-semantic
  HDF5/CGNS container metadata, not the mesh — compare dataset contents, not
  raw file hashes, when checking mesh determinism); the ADflow solver
  reproduced bit-identical CL/CD/CMy on an independent rerun.

## mesh_robustness_n10_cap4/ — the campaign that exposed the epsE defect
10 random BWB geometries, cap4 smoke recipe. Reported 7/10 "ok" at the
time. Re-analysed 2026-07-22: all 10 pyHyp runs actually *completed*; 3 of
the written meshes carried 14-100 inverted cells (of 1,703,936) at the
blunt-TE crown on a spanwise extremity, and one of the 7 "ok" meshes
(seed 6) had 30 layers of negative scaled quality. Full analysis and the
`epsE` dose-response that resolved it: `SURFACE_MESH_LAWS.md`.

## Staged but not yet run (2026-07-20)
Three targeted 2D sensitivity studies (farfield distance, wall spacing,
Euler-vs-RANS), a second validation anchor (alpha=0), the wing-level 3-grid
GCI family, and a 100-geometry mesh-robustness DOE campaign are all built
and `--dry-run`/import validated but deliberately not executed — Mike asked
for heavy/long runs to be staged for him to launch on his own schedule
rather than run automatically in-session. Exact commands, runtime estimates,
and RAM caveats: `configs/cfd/RUNBOOK.md`.
