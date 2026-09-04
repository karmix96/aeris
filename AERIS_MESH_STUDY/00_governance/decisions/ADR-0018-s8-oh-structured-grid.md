# ADR-0018 — S8: an O-H structured grid, and authorization for its first CFD point

- Status: accepted
- Date: 2026-09-03
- Supersedes nothing. Does not retire S6.

## Context

The C candidate family splits every section into six blocks, two of which are
collars at the leading and trailing edges. The nose collar's width is a block
dimension, `end_points`, and that dimension is shared with the trailing-edge
base block. Two measured consequences follow.

First, the leading edge is starved at every level: 2, 3 and 4 wrap cells absorb
37.9, 31.8 and 25.7 degrees of surface turning per cell against a conventional
wall-resolved reference of 10. On C03 this drives surface pressure above its
physical bound on 137 of the 296 leading-edge collar faces, peaking at cp 5.328,
and that strip supplies roughly 80 percent of pressure drag
(`m2_a_c03_leading_edge_collar_defect_20260903.json`). A census found the same
construction in all 65 surface meshes in the study; zero pass
(`m2_leading_edge_wrap_census_20260903.json`).

Second, the attempt to fix it inside that topology failed. The D family raises
`end_points` and shrinks the nose block, reaching 10.6 degrees per cell, and
then will not march: `candidate_d03` segmentation-faults at every value in the
governed epsE ladder and at every `nConstantStart` / `volBlend` pair tried, 25
marches in total (`m2_leading_edge_wrap_redesign_20260903.json`). The cause is
now measured: `end_points` also sets the point count across the 1.0 mm blunt
trailing edge, and `end_scale` also contracts the tip cap, so both levers drove
min-cell/`s0` from 21.4 to 8.8 — below the ADR-0010 marchability floor of about
13, which separates every march on record.

The coupling, not the parameter values, is the defect.

## Decision

Add **S8**, an O-H structured grid after Zhang et al. (2026), *Engineering
Applications of Computational Fluid Mechanics*, figure 28.

    xi    one closed O-ring per section. ONE block, no collars.
    eta   wall-normal, marched in the section plane to a circular far field.
    zeta  spanwise, root symmetry plane -> tip -> spanwise far field.

Leading-edge resolution is requested in **degrees of turning per cell** and the
spacing is solved for on the ring that was actually built. There is no
`end_points`, so nothing the leading edge asks for can shrink the trailing edge
or the tip cap. The tip closes with a single chordwise transfinite patch whose
perimeter *is* the tip ring, node for node, with zero collapsed edges.

The volume grid is built directly rather than marched hyperbolically. This is
deliberate: pyHyp's march is what failed 25 times, it is tuned to one exact
surface, and its failure mode is a crash with no diagnosis. An algebraic march
with an explicit orthogonality condition cannot crash, and its cells can be
checked afterwards. They are: 0 inverted cells of 567,256.

**Delivered on `lhs100_seed42[83]`, level oh_L3**, against the C and D families:

| | C03 | D03 | S8 oh_L3 |
|---|---|---|---|
| leading-edge turning per cell | 25.74 deg | 10.63 deg | **10.02 deg** |
| minimum scaled Jacobian, OML | 0.241 | 0.051 | **0.681** |
| min-cell/`s0` | 21.41 | 8.83 | **19.31** |
| volume march | completes | segmentation fault | not applicable |
| inverted cells | — | — | **0 of 567,256** |
| surface blocks | 13 | 13 | **2** |

## Authorization for the first CFD point

`05_s6_cfd_qualification/POLICY.yaml` blocks heavy work with a single exception
for the M2 A/C03 canary. S8 had no entry, so its first solve was blocked. The
principal investigator authorized it explicitly on 2026-09-03, for at least six
MPI ranks, and `POLICY.yaml` gains a matching `run-s8-first-point` exception.

Scope of that authorization, and the limits of what the run can settle:

- **Geometry and operating point are unchanged**: `lhs100_seed42[83]` and
  `mission_authority_v1.yaml` verbatim, so the reference area
  0.394918242017589 m2 and moment reference [0.4, 0, 0] are the C03 values and
  the result is directly comparable rather than a separate experiment.
- **It can settle the defect S8 exists for**: whether surface pressure stays
  inside the 1.0018 physical bound for this Mach 0.0837 case.
- **It cannot settle tip-cap viscous quantities.** The tip cap's wall normal IS
  the spanwise direction, so its first cell is set by the span law. It is now
  10.2 `s0`, matched to the OML's tip spanwise cell so the o_wing/o_out
  interface carries no cell-size jump, but y+ on the cap is still about ten
  times the OML's. Tip-cap skin friction and any drag decomposition including it
  are not quotable from this mesh.
- **It authorizes no freeze and no paper claim.** The hold-out
  `round_c_lhs10_seed42` stays locked.

## Consequences

- S6 is not retired. S8 is a fourth strategy under ADR-0011, measured on the
  same gates and the same shared QC definitions.
- The grid family oh_L3 / oh_L2 / oh_L1 has effective refinement ratios 1.295
  and 1.352. The second is 0.002 over the 1.35 ceiling and is recorded as out
  of band, not rounded in; oh_L1 needs a small reduction before it is used for
  a convergence study.
- Eleven construction defects found while building this are recorded in
  `05_s6_cfd_qualification/reports/s8_oh_grid_20260903.json`. Three of them
  produced volume reports that read exactly like folded cells and were not:
  reversed handedness, in the far-field frame, in the cap patch assembly, and in
  the cap's outboard extrusion. That failure mode is worth knowing by name.
