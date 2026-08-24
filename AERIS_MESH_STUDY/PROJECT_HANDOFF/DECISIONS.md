# Decisions

## Strategy tournament

| Strategy | State | Decision |
|---|---|---|
| S0 cap4 | Comparable re-run still pending | Baseline topology works on the surface, but old results used the wrong TE law and volume marching failed. |
| S1 Openblademesh | Working seed topology | Retained as the structured seed generator and pyHyp fallback. |
| S2 cross-field | Closed/rejected | Gmsh output did not yield a deterministic, geometry-independent block decomposition. |
| S3 station sweep | Closed/falsified | Controlled test failed 30/30 marches after the reversal guard; its hypothesis was false. |
| S4 analytic multiblock | Unfinished | Still a useful independent topology study, but it is not the campaign pipeline. |
| S5 | Not started | Superseded for now by the tailored S6 direction. |
| S6 bounded mesh atlas | Primary candidate | Selected because it amortizes expensive robust seeds and uses deterministic deformation plus hard validation and fallback. |

## S6 geometry and trailing edge

- The master geometry is the exact pyGeo outer mold line.
- The physical trailing-edge thickness is `1.0 mm` absolute.
- The current CFD mesh uses a numerical opening floor of
  `max(1.0 mm, 0.5% of local chord)`.
- That larger mesh-only opening is declared and audited; it is not allowed to
  silently redefine the CAD geometry.
- Aerodynamic sensitivity to the numerical TE floor is still an open validation
  gate. Do not call it physically neutral until tested.

## Atlas and routing

- Atlas selection uses 16 geometry-active normalized variables. Variables that
  are fixed or do not change the current geometry are excluded from distance.
- Initial maximin template indices are:
  `42, 70, 16, 56, 65, 92, 29, 90, 81, 47, 43, 41, 88, 24, 2, 68`.
- Distance only orders candidates; it is not a quality guarantee.
- Routing tries compatible templates nearest-first, continues past weak passes,
  and retains the best mesh meeting hard quality.
- Preferred minimum volume quality is `0.15`; production hard floor is `0.10`.
- The qualified development atlas keeps all 16 original maximin templates. It is
  not frozen until the complete 100-target production report is accepted.
- If atlas deformation fails, build a target-specific S1 plus pyHyp mesh at the
  same resolution and wall-spacing law.
- Smoke validation may enrich the atlas but cannot set `freeze_ready=true`.
  Only a complete production-level validation can unlock freeze.

## Resolution and wall treatment

- Smoke normal first-cell fraction: `8.8e-6` of surface bounding-box diagonal.
- Fine fraction: `6.0e-6`.
- Current fixed development candidate: `3.6e-6`, `epsE=1.5`, and `N=257` at
  reference Reynolds number `1e6`.
- This pair passed 16/16 production seed meshes. It remains provisional because
  only production CFD can validate wall y+.
- Target-specific fallback must use the epsE and first-cell law recorded in the
  registry; it may not fall back to a hidden hard-coded policy.

## CFD

- Primary solver path: ADflow, compressible RANS with Spalart-Allmaras.
- Nonlinear sequence: ANK then NK, with NK20 settings recorded by the adapter.
- Acceptance requires at least six residual orders, stable force tails, complete
  finite positive drag, and wall y+ limits p95 <= 1, p99 <= 2, max <= 5.
- A converged residual history alone is not an accepted CFD case.
- One accepted mesh is shared by all flow points for one design. It is pruned
  only after every required flow is accepted and the design report is durable.

## Governance

- The 100 development geometries may be used for selection and tuning.
- The locked hold-out is one-shot evidence. No tuning from hold-out outcomes.
- Quality thresholds, atlas contents, fallback rules, solver settings, and
  acceptance rules must be frozen before hold-out release.
- Preserve failed attempts and reasons; failures are research data and are
  needed for the later AI work.

## Planned second pipeline and AI work

- Finish S6 plus ADflow first.
- Then add wall-resolved Gmsh prism/tetra meshes plus SU2 as an independent
  fallback and cross-check. Current Gmsh foundations are tetra-only and are not
  equivalent yet.
- Then expose `structured_atlas_adflow`, `unstructured_gmsh_su2`, `auto`, and
  `compare` through one geometry input and acceptance schema.
- AI is an assistant, not the validity authority: template selection and failure
  prediction first; deterministic meshing and hard gates remain mandatory.
