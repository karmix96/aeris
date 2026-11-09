# Stage 3 — status and handover (10 Nov 2026, 02:00)

Branch `stage3-volume-mesh` (from `stage2-surface-mesh`; Stage 2 is not merged into main). Push access was not granted
in this session: the branch is handed over as a git bundle (decision 94). Code: `CFD_Automation/cfdauto/volume/`
(Stage 2's `cfdauto/mesh/` untouched). Rules: `configs/volume.yaml` (rule set 2; rule set 1 kept in
`configs/volume_rules1.yaml`). Plan, checks and results: `decisions/volume_rules.md`. Decisions 84–113 in
`CFD_Automation/OPEN_DECISIONS.md`.

## In one breath

- One matched C-H volume mesh per wing, Re and level on the frozen Stage 2 surface; 15 checks written before any mesh.
- The first rule set worked but cost too much (M 20.8 M cells, F 45 M). **Mike, 9 Nov: cut it; M about 10 M
  (decision 107); angles −5° to +10° (decision 111).**
- **Rule set 2 as it stands: M 9.5 M cells (median), F 20.7 M.** One mesh serves every angle from −5° to +10°.
- The first builds of rule set 2 found three faults in how the mesh is built. All three are fixed; no check limit
  changed (decisions 108–110).
- **Memory: 10 M cells do not fit 48 GB** by S8's laws for ADflow (48 GB holds 4.6–5.9 M). VC and C fit; M and F need
  the HPC. Mike: keep the mesh; V7 measures the real memory first (decision 113).
- Not done: the first solves (V7) and the hold-outs (V8).

## Where each step stands (rule set 2 as it stands)

| Step | State | Result |
| --- | --- | --- |
| V0 | done | 15 checks and limits written first; approved by Mike; none changed since |
| V1 | done | BWB reference wing 0, VC, Re 3 × 10⁵: every check passes; 2,324,016 cells (rule set 1: 4,930,448) |
| V2 | done | 20 reference wings × 4 Re at VC: 80 of 80 pass; 1.16–3.36 M cells |
| V3 | done | the cap and the outboard blocks pass on all 80; the tip vortex is carried, not resolved |
| V4 | done | check 13 passes on 20 of 20 families (VC/C; worst 2.0 % off); M and F built on 4 wings: flying wing 0 at M: 9.20 M, passed; cranked 0 at M: 8.70 M, passed; tapered 0 at M: 8.77 M, passed; BWB 0 at M: 10.61 M, passed; BWB 0 at F: 23.10 M, passed |
| V5 | done | CGNS (ADF) and `.su2` read back exactly, the CGNS also by the CGNS library; check 15 on every export |
| V6 | done | every built set at VC (702 wings) + the 20 reference wings: 721 of 722 pass; refused 1 (BWB corner2 6, cell quality 0.032); the focus set 400 of 400 |
| V7 | written, not run | `solve/`: the case, the ADflow run with S8's safeguards and the memory record, SU2 SA and SST + LM configs, the acceptance rule, the runbook (with the memory and the wake steps) |
| V8 | waits (104) | the hold-outs, once, with the rules frozen and Mike's OK |
| V9 | done | page, summary, this file, OPEN_DECISIONS, the Approach map, the flowchart, the project docs |

## Numbers to remember (rule set 2 as it stands; the 20 reference wings at Re 3 × 10⁵)

| Level | Cells, median (range) | ADflow RAM: ANK only · ANK then NK | Fits 48 GB? | Built here |
| --- | --- | --- | --- | --- |
| VC | 2.08 M (1.87–2.58) | 18 · 21 GiB | yes | 20 of 20 pass |
| C | 4.43 M (3.99–5.54) | 35 · 43 GiB | yes (the largest only just) | 20 of 20 pass |
| M | 9.53 M (8.56–11.81) | 72 · 92 GiB | no | built on 4: 4 pass |
| F | 20.7 M (18.7–25.7) | 152 · 197 GiB | no | built on 1: 1 pass |

- At VC over the 4 Re: 1.16–3.36 M cells (median 2.42 M).
- Counted on 94 wings of every set (a seeded 10 % of each set and type and the 20 reference wings, Re 3 × 10⁵): M 8.2–12.8 M (median 9.6 M), F 17.7–27.8 M (median 20.7 M).
- RAM laws: S8's two-point fits at 0.57 and 1.11 M cells (ADR-0020). ANK only (what runs here): 2.69 + 7.23 GiB per
  million cells. ANK then NK (what check 14 reports): 1.51 + 9.46. Neither is measured at these sizes (decision 112).
- The V7 mesh (BWB 0, VC): 2.32 M cells; 62 layers, 53 wake nodes, 335 C-line nodes, 61 + 49 stations; CGNS 59.0 MB,
  `.su2` 322.8 MB; about 20–24 GiB for ADflow.
- Building is cheap: VC 5–15 s. The solver is the cost.

## What changed on 9–10 Nov, in order

| Decision | What |
| --- | --- |
| 101 | The cap's two nose-corner cell columns are exempt from check 3, as in Stage 2 (Mike) |
| 105 | The cells must drop drastically (Mike); V6 of rule set 1 stopped at 427 of 702 wings; seven packages counted |
| 107 | Rule set 2 = package P2: outboard growth 1.3; 30 boundary-layer cells at M; the first cell behind the base = the wing's last chordwise cell; a coarser wake band (Mike: "M about 10 M") |
| 108 | Fault: the band was sized from the wake line, the fan is straight from the base. Now the exact envelope |
| 109 | Fault: each cell took the band limit at its start. Now at its centre (check 13 failed on 11 of 20 before) |
| 110 | Fault: far cells sheared between very close stations. Now neighbouring stations' far parts are lined up (three versions; BWB corner2 6 stays refused) |
| 111 | Angles −5° to +10° (Mike); the fan follows: 12 cells across 15° at M; no extra angle on top of the 0.05 c margin |
| 112 | Check 14's RAM law was mislabelled: it is S8's ANK-then-NK law; ANK only is about 20 % less. Both are shown |
| 113 | 48 GB: keep the mesh; VC and C on the desktop, M and F on the HPC; V7 measures the memory (Mike) |

## Mike's calls

1. **Where the solves run (103):** open. The V7 mesh needs about 20–24 GiB for ADflow: not the 16 GB desktop.
2. **The hold-outs (104):** not yet.
3. Decided on 9 Nov: 101, 105, 107, 111, 113 (above).

## Weak points (rule set 2)

- **No solve yet** on a Stage 3 mesh. So the memory at these sizes and where the wake goes are not measured.
- **Memory:** by S8's laws M (9.5 M cells) needs 72–92 GiB for ADflow. The plan assumed 10 M cells in 48 GB.
- **The fan ends at +10°.** Above it the wake leaves the fine cells; post-stall needs its own mesh (decision 69).
- **Very close stations with fast-changing chords** (steep BWB centre bodies, corner wings) sit nearest the
  cell-quality limit (decision 110); one corner wing is refused (BWB corner2 6). In the screen: 3 of 722 meshes have their worst cell under 0.06, 1 under 0.05; the lowest: BWB corner2 6 0.032, BWB corner2 0 0.052, BWB full-space 31 0.056.
- **A coarser wake band and tip vortex than rule set 1:** 1.25° per fan cell at M (was 0.63°); the tip vortex in cells
  1.2–1.7 × larger across its path; station gaps up to 0.54 c 30 stations past the tip.
- **The base is not at y⁺ 1** (its first cell is the wing's last chordwise cell); in exchange the spacing jump across
  the trailing-edge line fell from up to 537 to about 1.03.
- **18–29 cells across the boundary layer at VC** (30 at M).
- Planar stations: in-plane angle ≤ 0.18°, but up to 40° to the surface normal at swept noses on the reference
  wings and 74° on the most swept corner wing (reported, no limit; y⁺ only falls).
- The cap's two nose-corner columns: exempt (decision 101), not fixed.
- C built only on the reference wings, M on four, F on one; the rest counted (time on 2 cores, not memory).
- The CGNS library check used VTK's copy of CGNS; `cgns.libcgns_check` runs with Mike's 4.5.2 too (`CGNS_LIB=`).
- My own errors on 9 Nov, on the record: the fix of decision 106 was incomplete (108); I sized the fan for post-stall
  although decision 69 gives post-stall its own study (111); I labelled the RAM law wrongly (112) and showed the RAM
  at VC only when Mike set "M about 10 M" (113).

## Next

1. **V7 on Mike's machine** (`solve/RUNBOOK.md`): ADflow SA, SU2 SA, SU2 SST + LM on BWB 0 at VC, α 4°.
2. In the same session: **the memory** (ADflow as run, ADflow with ILU fill 0, SU2) and **the wake at −5° and +10°**
   (two more points with the volume solution kept).
3. With those numbers: whether M can run on 48 GB, and whether the fan's top angle stays at +10°.
4. V8, the hold-outs, when Mike says, with the rules frozen.

## Handover to Stage 4

**What Stage 4 gets.** Per wing, Re and level, one folder `volume_<level>_<hash8>_re<Re>/`:

| File | What |
| --- | --- |
| `blocks.npz` | the 13 blocks, (ni, nj, nk, 3) each, right-handed, k = +y |
| `quality.json` | every check with value and limit, the review flags, the info (counts, stations, quality by block, the smoothing ramps) |
| `manifest.json` | the hashes (volume code, surface code, rules, nodes), the BCs, the interfaces, the files |
| `volume.cgns` | ADflow: structured CGNS in ADF; BCWallViscous / BCFarfield / BCSymmetryPlane with families; 1-to-1 |
| `volume.su2` | SU2: hexahedra; markers `wall`, `symmetry`, `farfield` |
| `refusal.json` | instead of all the above when a check refuses the mesh |

**How to make one.**

```python
from cfdauto.mesh.surface import build_surface, wing_from_set
from cfdauto.volume.volume import build_volume, count_volume, write
w = wing_from_set("bwb", "reference", 0)
s = build_surface(w.loft, 3e5, "VC")          # the frozen Stage 2 surface, band on
print(count_volume(s))                        # cells and RAM first
vm = build_volume(s)                          # the mesh and checks 1-14
write(vm, w, "out/", formats=("npz", "cgns", "su2"))   # + check 15 on the solver files
```

**Conventions.** Lengths in mean chords (unit mean chord); Re on the mean chord; the semi-span along +y, lift +z (ADflow liftIndex 3;
SU2 turns α in x–z); the symmetry plane at y = 0; the far field 80 c from the wing; the band on (decision 81);
**angles −5° to +10° on this mesh** (the fan's two angles are in `configs/volume.yaml`; another range is another
mesh from the same code).

**What not to do.** Do not edit `cfdauto/mesh/` (the surface code hash); do not move a wall node; do not open the old
sealed set (`AERIS_MESH_STUDY/00_governance/round_c_lhs10_seed42_samples.csv`); do not tune anything on the hold-outs.

## The first rule set (the record)

V0–V6 with rule set 1 are kept in `decisions/volume_rules.md` (sections 6–14). `STAGE3_RULESET=1` builds its rules
with today's construction; the recorded numbers came from the construction before decisions 106 and 108–110 (commit `3ddc29c`):
V2 80 of 80; V4 check 13 on 20 of 20; V6 stopped at 427 of 702 wings (focus set 400 of 400; 20 full-space wings
refused by the wake band: the fault of decision 108). Cells: VC 4.55 M, C 9.73 M, M 20.8 M, F 45.4 M (medians).
The seven packages counted for decision 105 are in section 14.
