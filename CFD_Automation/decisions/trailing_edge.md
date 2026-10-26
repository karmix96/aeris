# Trailing edge

| choice | value | why |
|---|---|---|
| Thickness | Class I: max(0.5 mm, 0.2 % of local chord); Class II: max(1.0 mm, 0.2 % of local chord) | A real wing has a blunt edge of finite thickness. CFD, CAD and the low-order model must all see the same one. |
| Where it is made | in the generator, on the 2-D airfoil, before lofting | One wing for every later stage. In AERIS the mesher opened the edge by thickening the whole section: 4.3 mm at one root, 2.4 times the rule. |
| How | ramp from x/c = 0.65 to the edge, r = ((x − 0.65)/0.35)², half up, half down | The nose is untouched and the camber line does not move. AERIS's whole-section thickening acted like aft camber (lift moved 11–30 counts). |
| Files that already have a blunt edge | set to the rule (NACA 4415 file: 0.32 % → rule) | The rule decides, not the file. |
| Rule switch inside a panel | add a section where the chord equals 0.25 m (Class I) or 0.5 m (Class II) | The loft blends thickness linearly between sections; without it the edge would fall below the floor between them. |

Why the edge matters: in AERIS the base carried about a fifth of the pressure drag at 0.5 % of
chord, against 2–4 % at 0.2 %.

Checks: built thickness = rule at every section within 1 µm; camber line unchanged to 1e-6 of chord.

Left for later (needs CFD): the 0.1 / 0.2 / 0.3 % chord sensitivity; confirming the floor with
the builder.
