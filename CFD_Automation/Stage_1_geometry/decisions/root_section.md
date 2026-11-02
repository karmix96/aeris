# Root section, section orientation and dihedral

| choice | why | source |
|---|---|---|
| Every section is vertical (parallel to the symmetry plane), twisted only about a spanwise axis through its leading edge | The root section then lies exactly in y = 0 whatever the dihedral, so the two mirrored halves meet without crossing. Wings need dihedral from the root. | AERIS (pyGeo adapter and its AVL path) rolled the root section with the first panel's dihedral (`span_axis = segment_axes[0]` at station 0), so the halves crossed and the root dihedral had to be pinned at 0 |
| One dihedral per straight panel: `dihedral_p1_deg`, `dihedral_p2_deg`, `dihedral_p3_deg` | Panels are straight, so each has one slope. Until 29 Oct 2026 four station values were given; only three panel slopes came out, so one input had no effect ([0, 3, 3, 6], [3, 0, 6, 3] and [1.5, 1.5, 4.5, 4.5] built the same wing to 0.003°). | decided 29 Oct 2026 (Mike) |
| Station height z_i = sum of tan(panel dihedral) x panel span, over the panels inboard | Exact for straight panels | — |
| Panels between stations are straight (ruled) | What a builder makes; matches the planform | Stage 1 brief |

pyGeo does not need a dihedral angle: the loft is built from our 3-D section points (`loft.py`), so it
inherits the vertical sections. AVL also places its sections in vertical x-z planes.

Checks (validity gate): the root section lies in y = 0 within 1e-9 m, and no point of the half wing has
y < -1e-9 m. The vector gate compares each measured panel dihedral with the vector within 0.2°.

Consequence: the section shape is the airfoil cut vertically. On a panel with dihedral Γ the
thickness normal to the panel is cos Γ smaller (at 10°: 1.5 %).

Published and hand-labelled wings were converted from station to panel values so that their station
heights are unchanged (NASA CRM: stations 0 / 3.67 / 2.50 / 9.84° became panels 1.84 / 3.09 / 6.18°).
