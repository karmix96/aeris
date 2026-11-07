# Stage 2 — Surface mesh

> **7 Nov 2026: the new rules are built** (decisions 71, 72, 74). Levels VC, C, M, F; each rule is met at its
> anchor level (hard minimums at VC, accuracy targets at M, transition targets at F) and follows the family rule
> elsewhere; a lighter band (bubble length floor 0.10 c from local Re 4 × 10⁵); tip gap 2 × s0; station gap
> 0.25 × chord at M; lower band from the leading edge. The rules and commands below are the new ones. The first
> approach (2–3 Nov, every rule met at C, the coarsest of C, M, F, FF) is kept in `configs/surface_first.yaml`
> (`--config`). How the anchors are built: `decisions/surface_rules.md`, section 13. Also on 7 Nov, in Stage 1: the
> nose fix (decision 64) and similarity (decision 70: every wing at unit mean chord; the sets rebuilt). The new screen
> on the rebuilt sets (section 14): @@OK_NEW@@ of @@N_NEW@@ builds passed at VC, C, M and F. Still to come: Mike's
> confirmation of two builder choices (decision 77; the third, the nose, is answered: solved at every level, the
> strictest wins), the pyGeo run, the matched C-H volume mesh (Stage 3).

One wing surface (the Stage 1 loft) in, one structured surface mesh out: a closed ring of points
around the section at every spanwise station, root to tip, plus one patch that closes the flat tip.
Every node is asked from the loft; nothing is interpolated between stored sections. The volume
mesh, the wake boxes and the CGNS file are Stage 3.

Run from this folder (the code is the shared `cfdauto` package in `../cfdauto/mesh/`; install once with
`pip install -e ..`). The loft needs pyGeo; without it the numpy twin of the loft is used (same surface, see
`Stage_1_geometry/decisions/loft.md`).

```
python -m cfdauto.mesh --type bwb --set reference --index 0 --level VC --re 3e5  # one mesh (levels VC, C, M, F)
python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5 \
       --config configs/surface_first.yaml                                       # the same wing, first approach
python scripts/screen.py                                                         # every built wing, all types, at VC
python scripts/screen.py --level F --resume part.jsonl                           # at F; goes on after a stop
python scripts/screen_study.py                                                   # Study 9: merge, summary, figures
python scripts/similarity_check.py                                               # Study 10: the similarity check
python scripts/make_figures.py --code <checkout of 7bcb7067>/CFD_Automation       # docs/*.png (first approach, as drawn)
python -m pytest                                                                 # tests (test_family is slow)
python scripts/refine_map_data.py && python scripts/make_refine_page.py          # the refine map: docs/REFINE_MAP.html
python scripts/band_count.py                                                     # Study 8: the lower band A against B (decision 74)
```

```
configs/surface.yaml       every rule value with its anchor level and its source (read by cfdauto/mesh/laws.py)
configs/surface_first.yaml the first approach (2–3 Nov), unchanged, for rebuilding the first meshes
configs/surface_plan_VC.yaml the planned rules written at the coarsest level (Study 8 only, scripts/band_count.py)
decisions/surface_rules.md what was decided and why; what the screen showed; section 13: the new rules, built
docs/                      pictures of the reference meshes (first approach); the page, the summary, the refine map
data/studies/screen_C.json the robustness screen of the first approach (tracked)
data/studies/screen_VC.json, screen_F.json, screen_reference_new.json, screen_new_summary.json   the new screen (7 Nov)
data/studies/similarity_check.json   the similarity check (7 Nov)
data/meshes/               built meshes (not tracked; rebuild with the command above)
tests/mesh/                tests
../cfdauto/mesh/
  laws.py       one function per rule: the wing, the flow, the level in; the setting (moved from its anchor) and its reason out
  spacing.py    one spacing tool: target size along a line, growth limit, equidistribution
  ring.py       the ring at one station: nose solve (law 1), bands, trailing edge, base
  stations.py   where the stations go: on every loft station, chord-scaled, squeezed to the tip
  cap.py        the tip cap (ported from S8)
  checks.py     scaled Jacobian of surface quads
  surface.py    the build, the checks that refuse, the files
  figures.py    pictures from the mesh arrays
```

## What one mesh is

- **Name:** `mesh_<level>_<wing_hash8>_re<Re>`. The surface depends on the Reynolds number (the tip
  gap and the transition-band cells do), so the name carries the Re on the mean chord.
- **Ring order:** upper trailing-edge corner → nose → lower corner → across the blunt base;
  `2 n_side + n_base − 3` unique nodes, the same at every station.
- **Files:** `surface.npz` (wing `(n_ring, n_span, 3)`, cap `(n_chord, n_base, 3)`, `u` = x/c of every node,
  station `y` and `v`), `surface.xyz` (Plot3D, opens in ParaView), `stations.csv` (one row per station: what
  was asked, what was delivered), `quality.json` (every check with its value and limit), `manifest.json`
  (hashes: wing input, loft surface, mesh code, mesh nodes). A refused mesh writes only `refusal.json`.

## The rules (levels VC, C, M, F; each rule met at its anchor level, every spacing ÷ 1.3 per finer level and the growth g^(1/1.3), so each level is a true scaled copy)

| Where | Rule (anchor level) | VC | C | M | F | Source |
| --- | --- | --- | --- | --- | --- | --- |
| Nose | no ring cell turns the surface by more than 10° at M (solved by bisection on the ring as built, at every level for its own angle; the strictest spacing wins); away from the nose the same angle caps the cell from the local curvature | 16.9° | 13° | 10° | 7.7° | law 1 (S8); decision 71 |
| Nose, along the semi-span | nose spacing / chord changes by at most 1.15 between stations (checked; holds by construction with one distribution for the wing) | 1.15 | 1.15 | 1.15 | 1.15 | law 2 (S8) |
| Trailing edge | 0.1 % of local chord at the corners (M) | 0.169 % c | 0.13 % c | 0.1 % c | 0.077 % c | law 3 (DPW) |
| Blunt base | at least 8 cells across the base (VC), even counts | 8 | 10 | 14 | 18 | law 6 (S8) |
| Transition band | upper 0–85 % c, lower 0–100 % c (decision 74, option A); cell = bubble length / 20 at F; bubble length 0.40, 0.30, 0.10, 0.10 c at local Re 6 × 10⁴, 10⁵, 4 × 10⁵, 10⁶ (log-log, constant outside) | / 9.1 | / 11.8 | / 15.4 | / 20 | Stage 1 handover; Ansys CFX transition-model grid guide (20 per bubble); decision 72 |
| (candidate 65) | a per-wing band from the flow dataset: the envelope of bubbles, transition ± margin and separation over the conditions one mesh serves (`cfdauto/mesh/refine_map.py`, `docs/REFINE_MAP.html`); not a rule yet | | | | | Study 7; needs a 3-D transition check |
| Elsewhere | cells never above 2 % c (M) | 3.38 % c | 2.6 % c | 2 % c | 1.54 % c | our choice |
| Growth along the ring | 1.2 built, 1.25 checked (VC) | 1.2 / 1.25 | 1.15 / 1.19 | 1.11 / 1.14 | 1.087 / 1.11 | DPW; Stage 1 handover |
| Stations | one exactly on every loft station; gap = 0.25 × local chord (M); at least 12 gaps per panel (M) | 0.4225 c, 8 | 0.325 c, 10 | 0.25 c, 12 | 0.192 c, 16 | laws 8, 9; decision 72 |
| Growth between station gaps | 1.2 built, 1.3 checked (VC) | 1.2 / 1.3 | 1.15 / 1.22 | 1.11 / 1.17 | 1.087 / 1.13 | Stage 1 handover |
| Tip | stations squeezed so the last gap = 2 × the tip first cell s0; s0 from y⁺ = 1 at VC (flat plate, tip Re) | y⁺ 1 | 0.77 | 0.59 | 0.46 | laws 9, 10, 13; decision 72 |

One node distribution in arc fraction for the whole wing, both sides: at every place the strictest station
and side wins. So node i sits at the same arc fraction on every station (clean quads between the squeezed
tip stations, upright cross lines on the cap), no cell is coarser than its station asks, and the spanwise
envelope holds by construction.

## Checks that refuse

Each check reads the level's own value (the turning limit is 17.1° at VC, 13.2° at C, 10.2° at M, 7.89° at F: the
level's angle + 0.2°). nose turning (every node but the trailing-edge corners), geometry kinks (a kink of the section itself, which
no cell size can reduce), nose envelope, chord growth, band spacing, trailing-edge spacing, station-gap growth, loft
stations hit, tip gap, every ring in its station plane, wing quads (scaled Jacobian ≥ 0.05), cap quads
(≥ 0.05, the two nose-corner cells reported apart and refused only if folded), ring count.
