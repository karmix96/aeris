# S8 O-H first CFD — runbook

Not authorized and not launched. `05_s6_cfd_qualification/POLICY.yaml` sets
`heavy_work.blocked: true` with exactly one exception, the M2 A/C03 canary, which
this is not; and S8 is not in the governed policy at all. Running this needs a
policy entry and an ADR first. The commands are here so that when it is
authorized, nothing has to be reconstructed.

## What is already verified, without CFD

| check | result |
|---|---|
| ADflow accepts `oh_probe_volume.cgns` | yes, 181,680 cells, 0.000 load imbalance |
| ADflow accepts `oh_L3_volume.cgns` | yes, 555,144 cells, 0.040 load imbalance on 4 ranks |
| BC families resolved | `wall`, `sym`, `far` — exactly as written |
| unclaimed faces | none: `cgns_utils fillOpenBCs` adds nothing |
| inverted cells | 0 of 555,144 |
| root symmetry plane | planar to 8e-18 m |

Re-run the acceptance check any time:

```bash
/home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 4 \
  /home/mike/miniconda3/envs/mach-aero/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/preflight_adflow.py \
  --grid AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/oh_L3_volume.cgns
```

## Rebuild the mesh and its CGNS from scratch

```bash
cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
L=oh_L3   # or oh_probe, oh_L2, oh_L1

.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/build_volume.py --level $L
/home/mike/miniconda3/envs/mach-aero/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/write_cgns.py \
  --blocks AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/${L}_blocks.npz
```

## The solve, when authorized

Operating point is `mission_authority_v1.yaml` verbatim: 28 m/s at 1500 m,
M = 0.0837, Re = 1,530,708, T = 278.4 K, alpha in {-2, 0, 4, 8}.
Solver settings follow `policies/m2_a_c03_canary_v4.yaml`.

```bash
cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
/home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
  /home/mike/miniconda3/envs/mach-aero/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py \
  --grid AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/oh_L3_volume.cgns \
  --alpha 0.0 --out AERIS_MESH_STUDY/artifacts/s8_cfd/oh_L3_a0
```

Memory: 555,144 cells at the 10,620 bytes/cell measured in attempt04 is
5.49 GiB, against the 9.499 GiB verified WSL limit. It fits with margin, which
the C03 mesh at 943,104 cells did not.

## Read the result honestly

Two things this run can and cannot prove.

**Can**: whether the O-ring removes the impossible surface pressure. That is the
whole reason S8 exists. Check `cp` on the wall and confirm nothing exceeds the
1.0018 physical maximum for this Mach number. On C03, 137 of the 296
leading-edge collar faces did, peaking at 5.328.

**Cannot**: tip forces. The tip cap's wall normal IS the spanwise direction, so
its first cell is set by the outboard span law — currently 20 s0, about 20 times
the OML's y+. Tip-cap skin friction and any drag decomposition that includes it
are not trustworthy on this mesh. Fix that before quoting a tip contribution.
