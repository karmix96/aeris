# S8 ten-wing end-to-end multifidelity pilot

This directory contains the compact, versioned evidence emitted by the full
ten-wing pilot. Raw CalculiX decks and field files remain in the ignored local
run directory; these JSON reports are the review package.

Execution command:

```bash
aeris fea study run configs/fea/study_s8_pilot.yaml \
  --workdir <run-directory>
```

The campaign executed geometry generation, OpenAeroStruct comparison, rich
topology static FEA for positive/negative limit cases, reduced-topology modal,
linear-buckling and geometrically nonlinear checks, authority qualification,
post-processing gates, caching metadata, and DSE ranking/Pareto identification.

Result: all 10 variants passed the study, static verification, physics, and
conceptual qualification gates. The physical-validation gate remains explicitly
missing, so this is evidence for governed conceptual screening—not certification
or released detailed design.

Visual outputs are in [the pilot visualization report](../../fea_visuals/s8_pilot_e2e/FEA_VISUAL_REPORT.md).
