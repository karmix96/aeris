# Stage 3 — status and handover (13 Nov 2026)

In main since 10 Nov 2026 (Mike: everything merged; main fast-forwarded to `stage3-volume-mesh`, which starts from
`stage2-surface-mesh`; decision 94). Run it locally: `CFD_Automation/RUN_LOCAL.md`; look at any wing's meshes:
`streamlit run CFD_Automation/app/app.py` (`app/README.md`). Code: `CFD_Automation/cfdauto/volume/`
(Stage 2's `cfdauto/mesh/` untouched). Rules: `configs/volume.yaml` (rule set 2; rule set 1 kept in
`configs/volume_rules1.yaml`). Plan, checks and results: `decisions/volume_rules.md`. Decisions 84–115 in
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
- **11 Nov: the size was studied; a lighter rule set is proposed, not decided (decision 114).** Three rules are
  stricter than the published guides (the tip gap, the wall-normal growth, the station growth); loosened, M is 5.5 M
  at Re 3 × 10⁵ and 6.4 M at 4 × 10⁶ (today 9.5 and 13.5 M). Rule set 2 stands until Mike decides.
- **11–13 Nov: the first solves, on Mike's desktop (16 GB, so VVC only: 1.08 M cells).** ADflow SA converges (one
  option changed); SU2 converges with an incompressible recipe; the wake stays inside the fan; the pyGeo meshes equal
  the numpy ones; Stage 1's transition prediction agrees with SU2's SA + LM to about 0.02 c. Open: an 18-count gap
  between the two codes, a 20-count spread between the transition models, the first cell 7–14 % too tall.
- Not done: a solve at VC or finer (no machine yet), the hold-outs (V8).

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
| V7 | run at VVC only (11–13 Nov) | BWB 0, Re 3 × 10⁵: ADflow SA converged at −5°, 4°, +10° (CL 0.1907, CD 185.5 counts at 4°); SU2 SA accepted (0.1958, 167.8); SA-BCM accepted; SA + LM and SST + LM oscillate. VC (the plan's level) needs about 22 GiB: not run. `decisions/volume_rules.md` section 22 |
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
  Measured on 11–12 Nov at 1.08 M cells (VVC): ADflow 11.0 GiB, 10.2 GiB per million cells (the ANK-only law within
  5 %); SU2 SA 7.1 GiB, 6.6 per million. Scaled to VC (2.3 M cells): about 22 GiB for ADflow, 15 for SU2 SA.
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

## 11 Nov: the size study and a lighter ladder (not decided)

Mike: "for a structured mesh, pre-stall, above 10 M is too much"; then: change only the too-strict things, or make
today's M the F, starting from 800 k. What-if studies on copies of the rules files; no rule changed. The record:
`decisions/volume_rules.md`, sections 18–21; on the page: *The size*.

- **The mesh follows the wing and the Re** (702 wings): every count follows the wing quantity its rule uses; the counts
  give the cells (correlation 0.995). The angle of attack costs no cells up to +10°.
- **Today's sizes grow with Re:** M 5.7 / 9.1 / 11.2 / 13.5 M and F 12 / 20 / 24 / 29 M at Re 10⁵ / 3 × 10⁵ / 10⁶ /
  4 × 10⁶ (wing 0 of each type).
- **21 rules loosened one at a time (M, Re 3 × 10⁵):** the tip gap 2 → 100 × s0 −34 %; the band off −31 %; 10 cells
  per bubble −25 %; the far field 40 c̄ −11 %; the wall-normal growth 1.30 at VC −10 %; the rest 0–6 %; 8 rules 0 %.
- **Against the guides:** the tip gap (2 × s0) is 36–1,100 × finer than DPW's 0.1 % of the semi-span, because the cap
  is a wall reached along the stations; the wall-normal growth is one level stricter than DPW; the rest sit at the
  guides (the cells per bubble meet the transition guide only at F).
- **The light rules:** wall-normal growth 1.28 at VC (1.30 is refused on BWB reference wing 3: growth 1.0105 against
  1.01), station growth 1.25 at VC, the tip gap at DPW's value. Every level moves one step down in size and no
  accuracy target moves:

  | 20 reference wings, Re 3 × 10⁵, median | VC | C | M | F |
  | --- | --- | --- | --- | --- |
  | today | 2.08 M | 4.46 M | 9.53 M | 20.7 M |
  | light | 1.25 M | 2.63 M | 5.53 M | 12.0 M |

  Counted (the count can run one layer high: the built C median of today is 4.43 M). At Re 4 × 10⁶ (wing 0 of each
  type): M 13.5 → 6.4 M, F 29.4 → 13.9 M. Every mesh built passes (180 of 180 at VVC, VC and C); the family check 13
  passes on BWB 0 from VVC to M.
- **Renaming today's levels one step down** gives the same sizes with every level one step coarser on the wing: not
  advised. A VVC level (one step under VC: 0.4–0.7 M light) is past the hard minimums (y⁺ 1.3): a preview level only.
- **What the light rules give up:** the wall-resolved tip cap (its first cell at y⁺ about 50–800 at M). One solver
  check is needed: the same wing on both meshes. The way without that cost is a tip wrapped by the wall-normal lines
  (an O-type cap): a large change.
- **Not to loosen:** 20 cells per bubble at F, the trailing-edge cell, the first cell, the far field (Stage 4 measures
  40 / 80 / 160), the growth around the section (breaks the tip cap at Re 10⁵). The band off breaks the BWB cap at M.
- Found on the way: the count runs one layer high on about a fifth of the meshes (1.5–1.8 %; not fixed); the rules
  loaders cache a file by its name (the what-if scripts now write a new name per text).

## 11–13 Nov: the first solves (the record: `decisions/volume_rules.md` section 22)

Run by the Claude Code agent on Mike's desktop: `data/v7/night_11nov/REPORT.md`, `data/v7/su2_transition/REPORT.md`,
`data/v7/DECISIONS.html`. One wing (BWB reference 0), Re 3 × 10⁵, Mach 0.1, today's VVC mesh (1,075,074 cells).

| | Result |
| --- | --- |
| ADflow SA | converges to 6 orders at −5°, 4°, +10° with `ANKUseTurbDADI=false`; 31 min and 11.0 GiB at 4° |
| SU2 | the compressible case files never converged; the incompressible solver with the limiter frozen after the start-up and the CFL capped at 50 does |
| ADflow against SU2, both SA, 4° | CL 0.1907 / 0.1958 (+2.7 %); CD 185.5 / 167.8 counts (−17.7, 13.8 of it friction). Not the ft2 term (0.03 counts) |
| Transition (SU2) | every model: laminar bubbles on the upper side, a laminar lower side, 18–38 counts less drag. Only SA-BCM converges (CL 0.206, CD 130.0); SA + LM and SST + LM swing by 4–6 counts. Between models: CD 130–150, the moment changes sign |
| Stage 1's strips against SU2 | the upper transition within 0.03 c of SA + LM at every station (0.01 c on average); SST + LM 0.10 c later |
| The wake | inside the fan at −5° and +10°, at least 0.067 local chords from its edges |
| y⁺ | median 1.39–1.48 against the design 1.3; about 2 × at the nose, 2.5 × on the tip cap |
| pyGeo against numpy | the same meshes on 20 of 20 reference wings (nodes 4 × 10⁻¹¹ apart) |
| Memory | ADflow 10.2 GiB per million cells; SU2 SA 6.6, SA + LM 7.8. The desktop has 16 GB: about 1.1 M cells (ADflow), 1.5 M (SU2 SA) |
| The acceptance rule | changed on 13 Nov (Mike): 4 orders of the continuity residual and flat forces (`solve/read_results.py`) |

Read here (section 22.4): the code gap is likely ADflow's scalar dissipation on a coarse mesh (S8 measured −20.6
counts for half `vis4` on its coarse level); "SA-BCM because it converges" and "SA + LM is validated on E387" do not
stand yet (S8's E387 runs were compressible and not converged); the two codes must not be mixed in one difference
(the transition effect is the size of the gap). The next desktop runs: `solve/DESKTOP_13NOV.md`.

## Mike's calls

1. **Where the solves run (103):** open, and now pressing. The desktop has 16 GB: VVC only. VC needs about 22 GiB
   for ADflow (15 for SU2 SA); the light M 45–56 GiB.
2. **The hold-outs (104):** not yet.
3. **A rule set 3 with the light rules (114):** open. It needs a new Stage 2 law for the tip gap (so the frozen
   surface is reopened) and a re-screen of Stages 2 and 3.
4. Decided on 9 Nov: 101, 105, 107, 111, 113 (above).

## Weak points (rule set 2)

- **Solved at VVC only**, one wing, one Re: past the hard minimums (y⁺ 1.3, wall growth 1.34), no grid convergence.
- **The two codes differ on the same mesh and model:** CD by 17.7 counts, CL by 2.7 % (above the Stage 0 targets of
  3 counts and 1 %). The likely cause (ADflow's dissipation on a coarse mesh) is not measured yet.
- **The transition models disagree** (CD 130–150 counts, the moment changes sign) and no measurement says which is
  right; two of three do not converge.
- **The first cell is 7–14 % taller than designed** (y⁺ median; about 2 × at the nose, 2.5 × on the tip cap).
- **Two leading-edge corners hold SU2's residual** under a live limiter: the root on the symmetry plane and the
  planform kink (the loft's sharp kink with a station on it). The frozen limiter hides it.
- **Built here on the numpy twin of the loft** (the production loft is pyGeo). Checked on 11 Nov on Mike's machine:
  the 20 reference wings at VC give the same volume meshes on both lofts (nodes 4 × 10⁻¹¹ apart); the other 702
  wings are not compared.
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

0. **The desktop runs of `solve/DESKTOP_13NOV.md`** (VVC what-ifs, about 13 h of machine time): what each light rule
   changes in the answer (decision 114), the code gap (ADflow's `vis4`), the band in a fully turbulent run, the other
   three wing types, the four Re levels, the far field 40 / 80 / 160, one family step in SU2, and E387 on the recipe.
1. **Mike's word on decision 114** with those numbers. If yes: build rule set 3 and re-screen Stages 2 and 3.
2. **Where VC and finer run (103):** a machine with at least 32 GB for VC, 64 GB for the light M, or the HPC.
3. Into `solve/case.py`, with Mike's yes: `ANKUseTurbDADI`, the SU2 recipe, Tu 0.07 %; commit the `run_adflow.py` fixes.
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
