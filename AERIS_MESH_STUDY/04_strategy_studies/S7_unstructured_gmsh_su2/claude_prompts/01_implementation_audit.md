Act as the independent frontier-model peer reviewer for the AERIS S7 unstructured
Gmsh + SU2 strategy. Work read-only: do not edit, create, delete, stage, or run
production artifacts. Do not inspect or construct the locked hold-out
`round_c_lhs10_seed42`.

Repository root:
`/home/mike/Desktop/Start_Up/Code/v.0.1_Project`

Read these authoritative files first:

1. `AERIS_MESH_STUDY/00_governance/decisions/ADR-0017-s7-unstructured-gmsh-su2-preregistration.md`
2. `AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/POLICY.yaml`
3. all current Python files, all `test_*.py`, shell launchers, and documentation in
   that S7 directory
4. `AERIS_MESH_STUDY/04_strategy_studies/COMMON_BRIEF.md`
5. S6 `POLICY.yaml`, `campaign.py`, and `qualification.py` only where needed to
   verify compatibility and inherited gates.

Audit the current implementation, not the prose intent. Focus on:

- correctness of the closed full-wing surface topology and numerical TE law;
- correctness of exact-node and triangle-centroid pyGeo fidelity instrumentation;
- Gmsh discrete surface, normal extrusion, farfield hole, prism/tet generation,
  physical groups, and SU2 writer;
- inversion, prism-column, first-height/growth, skewness, non-orthogonality,
  aspect-ratio, volume-ratio, TE/tip, and self-intersection audits;
- whether every policy metric is measured with a scientifically suitable
  definition and missing evidence fails closed;
- deterministic retry/restart preservation, hashes, hold-out quarantine, and
  laptop resource safety;
- fixed-wall retry semantics, case/batch terminal verification, unequal-grid
  Richardson/GCI, and S6/S7 normalization compatibility;
- correctness of the SU2 convergence, force-tail, y+, and restart logic if that
  module exists by the time you inspect;
- test gaps and any misleading readiness claim.

You may run read-only inspection commands and laptop-safe unit tests. Do not run a
pyGeo campaign case, Gmsh production grid, SU2 CFD, or any hold-out operation.

Return a concise review with findings ordered Critical/High/Medium/Low. For every
finding give exact file and line, why it matters numerically or operationally, and
a concrete repair. Explicitly distinguish implementation defects from unverified
campaign evidence. If there is no finding at a severity, say so. End with the
single highest-value next verification action. Do not declare S7 accepted or
campaign-ready.
