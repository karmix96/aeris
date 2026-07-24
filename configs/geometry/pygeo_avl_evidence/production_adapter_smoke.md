# Production pyGeo → AVL adapter — end-to-end smoke (roadmap step 4)

`src/aeris/generators/bwb_segmented_v1/pygeo_avl_adapter.py` drives the existing
production `AeroSandboxAVLSolver` from a pyGeo realized loft, with the section-CST
viscous correction wired through `solver_options` (`section_map` + `polar_store`).
No new AVL / CDCL-injection / strip-drag code — the adapter is assembly over
production components.

## Chain

```
pyGeo realized sections (CST)
  ├─ build_aerosandbox_airplane  → ASB Airplane (AVL serializer only)
  └─ per-section CST coords        → NeuralFoilPolarSource + SectionAirfoilMap
→ AeroSandboxAVLSolver.run_case → AVL induced drag
    + inject_polar_cdcl (CDCL injection)
    + _compute_strip_profile_drag (independent strip integration)
→ cd_total = cd_induced_AVL + cd_profile_NeuralFoil
```

Viscous model default = **realized_sections**: each realized extracted section's
own CST shape governs its spanwise neighbourhood (nearest-section, midpoint
boundaries) — section-resolved correction from the master surface, matching the
standalone study rather than the coarse 4-airfoil step.

## Result (paper1_bwb_pygeo, 13 sections, α=4°, V=28 m/s, sea level)

| quantity | value |
|---|---|
| status | SUCCESS |
| CL | 0.225 |
| cd_ind (AVL induced) | 0.00624 |
| cd_profile (NeuralFoil strip integration) | 0.00613 |
| cd_total = ind + profile | 0.01237 |
| L/D viscous | 18.2 |

Regression tests: `tests/generators/bwb_segmented_v1/test_pygeo_avl_adapter.py`
(assembly always; end-to-end AVL run when the `avl` binary is present — passes).

## Still open in step 4 (refinements on the working chain)

- **NeuralFoil confidence gate** — surface `min_confidence` per section and gate /
  warn below threshold (study flagged it ungated).
- **Drag-agreement tolerance** — cross-check AVL-internal CDvis vs the independent
  strip integration and flag divergence (study saw ~4.1% agreement).
- **CDCL negative-side endpoint fitter** — the fitter can pick a poor negative
  endpoint; needs the fixed variant.
- **Explicit Mach** — currently metadata (mach=0 → derived from velocity/atmosphere
  for polar-bin selection); make the intended Mach handling explicit.
- **Native AVL writer** — remove the AeroSandbox serializer coupling entirely.

See `standalone/pygeo_avl_study/` for the proven feasibility study and
`README.md` here for the rescued reports.
