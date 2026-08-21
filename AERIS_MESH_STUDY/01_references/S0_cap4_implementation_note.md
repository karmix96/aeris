# S0 Implementation Note - Existing Cap4 Control

S0 is the control strategy. It preserves the current cap4 surface topology and uses it as the baseline against which every new strategy is judged.

## Algorithm

Run the existing cap4 surface builder, export PLOT3D/CGNS/VTK/NPZ artifacts, march the surface with pyHyp, audit the written CGNS volume, and record regional quality and failure locations. The baseline behavior must be reproduced before any cap4 improvement is introduced.

## Inputs

- Geometry contract: `00_governance/geometry_topology_contract.json`
- Current geometry authority: `configs/geometry/bwb.yaml`
- Frozen epsE calibration geometries: `00_governance/epse_calibration_lhs10_seed7_samples.csv`
- Recovered historical cap4 campaign config, **historical regression only**:
  `00_governance/historical_reference_inputs/bwb_explore_wide.yaml`
- Current mesh code: `src/aeris/mesh/surface.py`, `src/aeris/mesh/topologies.py`, `src/aeris/mesh/pyhyp_runner.py`, `src/aeris/cfd/meshing/pyhyp_options.py`, `src/aeris/cfd/meshing/pyhyp_extrude.py`, and `src/aeris/cfd/meshing/volume_audit.py`
- Prior evidence: `configs/cfd/RESULTS_ARCHIVE.md`, `configs/cfd/RETENTION.md`, `configs/cfd/SURFACE_MESH_LAWS.md`, `configs/cfd/evidence/mesh_robustness_n10_cap4_report.json`, and `configs/cfd/evidence/remarch_te_inversion_report.json`

## Outputs

- `strategy_manifest.json`
- `surface_report.json`
- `surface.fmt`
- optional surface CGNS/VTK/NPZ inspection files
- `pyhyp_options.json` and `pyhyp_effective_options.json`
- `volume_report.json`
- regional failure table keyed by block, layer, i/j range, and semantic region

## Missing Details

The old bulk run directory `data/cfd_cases/mesh_robustness_n10_cap4/` is absent, so Stage 01 must generate and freeze new surface hashes. Raw volume-CGNS byte hashes must not be used for determinism; compare HDF5 dataset contents.

The historical config describes a superseded airframe: root chord 1.2-2.0 m, full span 2.4-4.0 m, `naca4412` over the whole wing, and `dihedral_b1_deg` free to 5 deg, which breaks the flat-root-panel invariant in the topology contract. It has 17 active design variables, not 20. It is therefore usable only as a qualitative historical regression, never as the source of a production constant. See `00_governance/reference_package_manifest.yaml`, key `historical_config_divergence`.

Its per-sample design variables were never stored, and the generator moved eight commits since, so seeds 0-9 cannot be proven to reproduce the July geometries. Expect the same failure mechanism and region; do not expect identical numbers.

`epsE_common_start` must therefore be calibrated on the current design space, using the ten predeclared geometries in `00_governance/epse_calibration_lhs10_seed7_samples.csv`.

## Dependencies

Available in the current environments: AERIS mesh code, `pygeo`, `pyspline`, `gmsh`, `pyhyp`, `cgnsutilities`, `h5py`, `numpy`, and `scipy`. ADflow is available in the `mach-aero` environment for the later smoke solve.

## Risks

The archived headline of 7/10 clean is misleading after the negative-quality-layer recheck. Treat the old campaign as 6/10 clean under the current policy. The known weak region is the blunt trailing-edge crown at root and tip spanwise extremities.

## Smallest Feasible Prototype

After the TMR anchor passes, in this order:

1. Historical check: regenerate surfaces for seeds 0-4 from the historical config and confirm the trailing-edge-crown inversion mechanism still appears on the seed 1/3/4 equivalents with baseline options. Report it qualitatively.
2. Current control: generate all ten geometries from `epse_calibration_lhs10_seed7_samples.csv` on `configs/geometry/bwb.yaml`, freeze their surface hashes, and run the full `epsE={1.5, 2.0, 3.0}` sweep on those ten to select `epsE_common_start`.
