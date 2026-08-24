# ADR-0016 - S6 campaign quality and freeze policy

Date: 2026-08-16
Status: Accepted for development; hold-out remains locked

## Context

ADR-0011 defines the cross-strategy feasibility gate: every volume must have
strictly positive minimum scaled quality, and `0.30` is a ranking target rather
than a pass gate. That rule remains unchanged.

S6 is no longer only a tournament topology. It is a candidate production process
for an unattended 10,000-CFD campaign. A merely positive worst corner is too weak
as the only pre-solver screen for that use. Before the production seed run,
`S6_bounded_mesh_atlas/POLICY.yaml` recorded a stricter `0.10` campaign floor and
`0.15` preferred routing quality. The first production audit then rejected seeds
002 and 068 at `0.03433` and `0.03938`. Weakening the threshold after seeing those
results would be result-driven governance.

## Decision

1. ADR-0011's hard validity gate remains minimum scaled quality strictly above
   zero. It continues to determine topology feasibility and cross-strategy
   reporting.
2. S6 adds a separate campaign-qualification screen: independent hexahedral
   minimum scaled quality must be at least `0.10` before a mesh may reach CFD.
3. `0.15` is the preferred routing target. Routing may retain a mesh in
   `[0.10, 0.15)` only after all frozen candidates and the automatic fallback have
   been considered.
4. These numbers are conservative engineering screens, not universal CFD-quality
   truths. Their final scientific justification must come from solver convergence,
   y+, force stability, and grid-convergence evidence.
5. pyHyp's reported minimum quality and
   `shared.volume_qc.hex_scaled_jacobian` are different instruments. Reports must
   retain both; the independent written-CGNS metric controls the S6 screen.
6. Atlas freeze is permanently pinned to a complete production-level development
   report. No CLI or manifest may downgrade the required level to smoke or fine.
7. If solver evidence later requires a different `0.10` floor, a new ADR must be
   written, every affected development result becomes stale, and all validation
   must be repeated before hold-out release. The floor cannot be changed from
   hold-out outcomes.
8. The production wall spacing and epsE policy remain under development until the
   complete production seed set and post-solve y+ pass. This ADR does not freeze
   the current `3.0e-6`, `3.6e-6`, epsE 2.0, or epsE 1.5 candidates.
9. A true three-direction mesh family and GCI remain mandatory. Passing this mesh
   screen alone does not establish discretization accuracy.

## Consequences

- Seeds 002 and 068 are valid under ADR-0011 but rejected under the S6 campaign
  screen. Both facts must be reported.
- Failed candidates and all calibration attempts are retained; no threshold is
  relaxed to turn a failure into a pass.
- Production atlas qualification, development routing, fallback, written CGNS
  re-audit, and campaign execution must use the same independent metric.
- The locked hold-out remains untouched until ADR-0015 is resolved and the S6
  atlas, geometry, wall law, solver policy, and all acceptance gates are frozen.

## Implementation

- `S6_bounded_mesh_atlas/POLICY.yaml`
- `S6_bounded_mesh_atlas/deform.py`
- `S6_bounded_mesh_atlas/build_seeds.py`
- `S6_bounded_mesh_atlas/development_atlas.py`
- `S6_bounded_mesh_atlas/campaign.py`
- `S6_bounded_mesh_atlas/atlas.py`

The freeze-level CLI bypass identified during the independent Claude review was
removed in the same work session as this ADR.
