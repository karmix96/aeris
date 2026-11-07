# Trailing edge

> **What changes (7 Nov 2026, decision 70: similarity).** Every wing is built at unit mean chord, so a wing has
> no millimetres. The trailing edge is now **0.2 % of the local chord on every wing**: the floors (0.5 mm
> Class I, 1.0 mm Class II), the wing class and the switch section are gone, and a config that still names them
> is refused. In the first approach the edges ran from 0.20 to 4.17 % c, and 370 of the 730 wings had at least
> one edge set by a floor. Check C3 (CFD, to come): 0.1 / 0.2 / 0.3 % c, and the real floor of small wings,
> about 0.42 % c. The method (pyGeo's ramp from x/c = 0.90) and the `as_is` mode of the published wings stay.

| choice | value | why |
|---|---|---|
| Thickness | 0.2 % of the local chord on every wing (since 7 Nov 2026). First approach: Class I max(0.5 mm, 0.2 % of local chord); Class II max(1.0 mm, 0.2 % of local chord) | A real wing has a blunt edge of finite thickness. CFD, CAD and the low-order model must all see the same one. |
| Where it is made | in the generator, on the 2-D airfoil, before lofting | One wing for every later stage. In AERIS the mesher opened the edge by thickening the whole section: 4.3 mm at one root, 2.4 times the rule. |
| How | **pyGeo's method**: the added thickness grows linearly from zero at x/c = 0.90 to the full amount at the edge, half up, half down | Same as pyGeo `readAirfoilFile(bluntTe=True, bluntThickness=0.002, bluntTaperRange=0.1)` (MDO Lab, MACH-Aero; source read in `pygeo/geo_utils/file_io.py`). An aircraft tool in our own chain, with the same 0.2 % default. The nose is untouched and the camber line does not move. AERIS's whole-section thickening acted like aft camber (lift moved 11–30 counts). |
| Files that already have a blunt edge | set to the rule (NACA 4415 file: 0.32 % → rule) | The rule decides, not the file. |
| Rule switch inside a panel | gone on 7 Nov 2026. First approach: a section where the chord equals 0.25 m (Class I) or 0.5 m (Class II) | The loft blends thickness linearly between sections; without it the edge would have fallen below the floor between them. A fraction of the chord holds between two sections by itself (the ruled loft blends chord and gap linearly), so no section is needed now. |

Why the edge matters: in AERIS the base carried about a fifth of the pressure drag at 0.5 % of
chord, against 2–4 % at 0.2 %.

Checks: built thickness = rule at every section within 1e-6 mean chords (1 µm on the real-size wings before
7 Nov); camber line unchanged to 1e-6 of chord.

History: until v0.4 the ramp was r = ((x − 0.65)/0.35)², a start point with no source. Replaced by
pyGeo's method so every part of the rule is cited.

The linear ramp leaves a small slope change at x/c = 0.90 (about 0.6° per side at 0.2 % chord on
a sharp-edged section); the loft's cubic sections round it over a few points (loft vs exact ramp
< 0.004 % chord).

Left for later (needs CFD): check C3, the 0.1 / 0.2 / 0.3 % chord sensitivity plus the real floor of small
wings, about 0.42 % c (it also shows if the slope change at 0.90 matters). No builder floor is needed any more.
