# Loft

| choice | value | why | source |
|---|---|---|---|
| Spanwise order | kSpan = 2 | Straight (ruled) panels between sections, which is what a builder makes and what the planform says. Edges match the exact planform to 0.0000 % of chord. | pyGeo docs: "The spline order in span-wise direction. 2 for linear, 3 for quadratic and 4 for cubic" ([pyGeo API](https://mdolab-pygeo.readthedocs-hosted.com/en/latest/pyGeo.html)) |
| Sections | b0–b3, plus trailing-edge switch points | Enough for straight panels; more would only add knots. | — |
| Section parameter | the same for every section, s = √(x/c) | All sections share one knot vector. The upper/lower split falls exactly on the nose, and u in `upper(u, v)` is the chord fraction. √ keeps the nose round (vertical tangent). | — |
| Built with | pySpline surfaces, the same way `liftingSurface` builds them, held in a pyGeo object | `liftingSurface` merges each section's own knots and splits at a knot that is not the nose: 0.51 % of chord off (BWB), 0.21 % (conventional). See below. | pyGeo 1.17.0 source, `_init_lifting_surface` |
| Tip | open, flat (no cap surface) | Rounded tips are a later study. | — |
| Export | IGES from the same surfaces | STEP: no STEP writer in pyGeo; not done. | — |

## kSpan = 2 against kSpan = 3

Error of the lofted leading edge and trailing-edge midpoint against the exact straight panels,
max over 401 span points, % of local chord. From `geometry/scripts/loft_kspan_study.py` →
`geometry/data/studies/loft_kspan.json`.

| wing | kSpan 2 | kSpan 3 | kSpan 3 + 1 section/panel | kSpan 3 + 3 sections/panel |
|---|---|---|---|---|
| BWB mid-range | 0.0000 / 0.0000 | 1.31 / 1.24 | 0.82 / 0.50 | 0.39 / 0.28 |
| strongest sweep change (40° → 15° → 25°) | 0.0000 / 0.0000 | 4.82 / 3.30 | 1.35 / 2.13 | 0.73 / 1.05 |
| strongest panel-dihedral change (−3° → 1.5° → 6°) | 0.0000 / 0.0000 | 2.22 / 2.26 | 0.70 / 0.73 | 0.40 / 0.42 |

(leading edge / trailing edge)

kSpan = 3 uses the sections as control points, not as points the surface passes through, so it
cuts the corners at every panel break: up to 4.8 % of chord. Extra sections reduce it, but never
to zero. kSpan = 2 is exact.

## Straight panels and linear twist cannot both hold

On a straight panel the trailing-edge height is z_le − c·sin(twist). With chord and twist both
linear in span, that is quadratic, not straight. We keep the straight panel; so between stations
the twist is not exactly linear. Size: sections added with exactly linear twist sit 0.11–0.30 % of
chord off the straight trailing edge (kSpan 2 + 3 sections/panel, same study). At the stations
twist is exact.

Left for later (needs CFD): "forces change by less than one drag count when sections double".
