# AERIS FEA visual report

This report is generated from hashed case/study artifacts; PNGs are diagnostic views, not additional acceptance gates.

## Included evidence

- `mesh_topology.png`: audited shell elements colored by region.
- `oas_comparison.png`: S8 CFD authority versus OpenAeroStruct global lift.
- `study_comparison.png`: mass, displacement, and stress across each supplied study.

## Pilot/study execution summary

### bwb_s8_ten_wing_pilot

Status: **pass**; variants: 10.

Pareto candidates: `index12, index13, index16, index47, index65`.

## Next three steps toward robust FEA design-space exploration

1. **Release structural authorities:** replace provisional box depth, spar locations, aircraft mass, and typical aluminum values with versioned released geometry, mass, material allowables, and manufacturing knockdowns. The governance gate will fail closed until hashes and provenance are updated.
2. **Expand the parameterized structural model:** promote rib pitch, fittings, hinge loads, cut-out envelopes, laminate/metal section definitions, and joint stiffness to explicit study variables; add response surfaces for mass, stress, deflection, and buckling margin.
3. **Close the validation loop:** calibrate modal/buckling/nonlinear settings against a coupon and representative-wing test, then enable the untouched hold-out for threshold freeze and automated DSE ranking.

Current status: conceptual screening and software verification are automated; physical evidence and released structural authorities remain required for detailed-design use.
