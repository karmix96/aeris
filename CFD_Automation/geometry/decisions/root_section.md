# Root section and section orientation

| choice | why | source |
|---|---|---|
| Every section is vertical (parallel to the symmetry plane), twisted only about a spanwise axis through its leading edge | The root section then lies exactly in y = 0 whatever the dihedral, so the two mirrored halves meet without crossing. Conventional wings need dihedral from the root. | AERIS rolled the root section by the first panel's dihedral, so it had to force zero dihedral there |
| Leading-edge height z from integrating tan(dihedral), dihedral linear between stations | Exact, and independent of how the span is cut | copied from AERIS `_segment_z_integral` |
| Panels between stations are straight (ruled) | What a builder makes; matches the planform | Stage 1 brief |

Consequence: on straight panels, each panel has one dihedral, the slope between its two stations.
That is the exact mean of the linear dihedral over the panel. The station dihedral values set z;
the built wing has a kink at each station, not a smooth change. Checks compare panel dihedral.

Consequence: the section shape is the airfoil cut vertically. On a panel with dihedral Γ the
thickness normal to the panel is cos Γ smaller (at 10°: 1.5 %).
