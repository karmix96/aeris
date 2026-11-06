# Stage 2 — Surface mesh

> **6 Nov 2026: a new approach is decided, not built.** Levels VC, C, M, F (hard minimums at VC, accuracy targets
> at M, transition targets at F), a lighter band (bubble length floor 0.10 c from local Re 4 × 10⁵), tip gap
> 2 × s0, station gap 0.25 × chord at M, one matched C-H volume mesh for ADflow and SU2, similarity (unit mean
> chord). The rules and commands below are the first approach, which the code still builds. What was first and
> what changes: `decisions/STAGE2_STATUS.md` and the page `docs/SURFACE_MESH.html`.

One wing surface (the Stage 1 loft) in, one structured surface mesh out: a closed ring of points
around the section at every spanwise station, root to tip, plus one patch that closes the flat tip.
Every node is asked from the loft; nothing is interpolated between stored sections. The volume
mesh, the wake boxes and the CGNS file are Stage 3.

Run from this folder (the code is the shared `cfdauto` package in `../cfdauto/mesh/`; install once with
`pip install -e ..`). The loft needs pyGeo; without it the numpy twin of the loft is used (same surface, see
`Stage_1_geometry/decisions/loft.md`).

```
python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5   # one mesh
python scripts/screen.py                                                         # every built wing, all types
python scripts/make_figures.py                                                   # docs/*.png
python -m pytest                                                                 # tests (test_family is slow)
python scripts/refine_map_data.py && python scripts/make_refine_page.py          # the refine map: docs/REFINE_MAP.html
python scripts/band_count.py                                                     # Study 8: the lower band A against B (decision 74)
```

```
configs/surface.yaml       every rule value, with its source (read by cfdauto/mesh/laws.py)
decisions/surface_rules.md what was decided and why; what the screen showed
docs/                      pictures of the reference meshes
data/studies/screen_C.json the robustness screen (tracked)
data/meshes/               built meshes (not tracked; rebuild with the command above)
tests/mesh/                tests
../cfdauto/mesh/
  laws.py       one function per rule: the wing, the flow, the level in; the setting out
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

## The rules (level C; every spacing ÷ 1.3 per finer level, and the growth g becomes g^(1/1.3) so the finer level is a true scaled copy)

| Where | Rule | Source |
| --- | --- | --- |
| Nose | no node turns the surface by more than 10° (solved by bisection on the ring as built); away from the nose the same angle caps the cell from the local curvature | law 1 (S8) |
| Nose, along the semi-span | nose spacing / chord changes by at most 1.15 between stations (checked; holds by construction with one distribution for the wing) | law 2 (S8) |
| Trailing edge | 0.1 % of local chord at the corners; 8 cells across the base | laws 3, 6 (DPW; S8) |
| Transition band | upper 0–85 % c, lower 60–100 % c: cell = bubble length / 20; bubble length from local Re (Stage 1 table) | Stage 1 handover; Ansys CFX transition-model grid guide (20 nodes per bubble) |
| (candidate 65) | a per-wing band from the flow dataset: the envelope of bubbles, transition ± margin and separation over the conditions one mesh serves (`cfdauto/mesh/refine_map.py`, `docs/REFINE_MAP.html`); not a rule yet | Study 7; needs a 3-D transition check |
| Elsewhere | cells grow by at most 1.2 (checked: 1.25), never above 2 % c | DPW; Stage 1 handover |
| Stations | one exactly on every loft station; gap = 0.2 × local chord, at least 12 per panel; growth ≤ 1.2 (checked: 1.3) | laws 8, 9 |
| Tip | stations squeezed so the last gap = tip first cell s0 (y⁺ = 1 at the tip Re, flat plate) | laws 9, 10, 13 |

One node distribution in arc fraction for the whole wing, both sides: at every place the strictest station
and side wins. So node i sits at the same arc fraction on every station (clean quads between the squeezed
tip stations, upright cross lines on the cap), no cell is coarser than its station asks, and the spanwise
envelope holds by construction.

## Checks that refuse

nose turning (every node but the trailing-edge corners), geometry kinks (a kink of the section itself, which
no cell size can reduce), nose envelope, chord growth, band spacing, trailing-edge spacing, span growth, loft
stations hit, tip gap, every ring in its station plane, wing quads (scaled Jacobian ≥ 0.05), cap quads
(≥ 0.05, the two nose-corner cells reported apart and refused only if folded), ring count.
