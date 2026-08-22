# Stage 01 cap4 / epsE Calibration Report

- Mode: `full`
- Status: `FAIL`
- Geometry config: `/home/mike/Desktop/Start_Up/Code/v.0.1_Project/configs/geometry/bwb.yaml`
- Sample CSV: `/home/mike/Desktop/Start_Up/Code/v.0.1_Project/AERIS_MESH_STUDY/00_governance/epse_calibration_lhs10_seed7_samples.csv`
- Surface count: 1
- epsE common start: `None`

## Surface References
- lhs7_00: surface_ok, surface.fmt `f2850c00701589395e58d645994573d1f3e159d9bafa4ffc9d853bc1df218d49`

## Remarch Rows
- eps15 lhs7_00: clean=False, audit=inverted_localized, low_quality_layers=53, error=RuntimeError: pyHyp subprocess produced invalid marched volume metrics: min_volume=-5.44e-10, min_quality=-1.0, first_invalid_layer=39.
inverted_localized: 10 of 3690496 cells (0.00027%) inverted, min volume -5.442e-10
  domain.00005: 10 cells, layers 38-47, j[0, 0] i[47, 47], spanwise_edge=True, wall_adjacent=False, wall x[0.5852,0.5852] y[1.1830,1.1830]
Invalid CGNS moved to /home/mike/Desktop/Start_Up/Code/v.0.1_Project/AERIS_MESH_STUDY/artifacts/stage01/epse_calibration_l3_probe/remarch/eps15/lhs7_00/surface/wing_vol_smoke.invalid.cgns. Inspect /home/mike/Desktop/Start_Up/Code/v.0.1_Project/AERIS_MESH_STUDY/artifacts/stage01/epse_calibration_l3_probe/remarch/eps15/lhs7_00/surface/pyhyp_stdout.log.
