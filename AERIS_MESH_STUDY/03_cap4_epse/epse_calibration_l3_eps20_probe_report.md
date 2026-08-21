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
- eps20 lhs7_00: clean=False, audit=inverted_localized, low_quality_layers=53, error=RuntimeError: pyHyp subprocess produced invalid marched volume metrics: min_volume=-4.52e-11, min_quality=-1.0, first_invalid_layer=42.
inverted_localized: 4 of 3690496 cells (0.00011%) inverted, min volume -4.519e-11
  domain.00005: 4 cells, layers 41-44, j[0, 0] i[47, 47], spanwise_edge=True, wall_adjacent=False, wall x[0.5852,0.5852] y[1.1830,1.1830]
Invalid CGNS moved to /home/mike/Desktop/Start_Up/Code/v.0.1_Project/AERIS_MESH_STUDY/artifacts/stage01/epse_calibration_l3_eps20_probe/remarch/eps20/lhs7_00/surface/wing_vol_smoke.invalid.cgns. Inspect /home/mike/Desktop/Start_Up/Code/v.0.1_Project/AERIS_MESH_STUDY/artifacts/stage01/epse_calibration_l3_eps20_probe/remarch/eps20/lhs7_00/surface/pyhyp_stdout.log.
