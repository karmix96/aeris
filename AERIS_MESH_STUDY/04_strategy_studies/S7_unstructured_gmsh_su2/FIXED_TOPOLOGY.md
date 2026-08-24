# Can S7 freeze its surface topology across the design family?

S6 generalises by meshing a few templates to full quality and deforming them onto
the rest of the family.  That needs exact, index-based node correspondence between
designs.  S7 cannot do it today because its sampling counts are derived per design.
This is the measurement of whether that is fixable and what it would cost.

Nothing here was meshed.  It reads the surface reports already on disk with
`fixed_topology_probe.py`, runs in about a second, and can be re-run any time.

## Where the counts come from

`geometry.py` derives the grid from the design's own dimensions:

    n_u = max(17, ceil(1.15 * max_chord / surface_h) + 1)
    n_v = max(13, ceil(1.10 * semi_span / surface_h) + 1)

with `surface_h = surface_edge_over_L * L` and `L` the mean aerodynamic chord.
So the counts track the dimensionless ratios `max_chord / L` and `semi_span / L`,
both of which move with planform across the LHS space.  Two extra `while` loops
add points if cosine clustering cannot reach the declared TE and tip edge targets.

The counts therefore vary **by construction**, not by accident.

## What the spread actually is

At production `coarse`, over the five production designs:

| level | cases | n_u | n_v | mean cost | worst cost |
|---|---|---|---|---|---|
| `coarse` | 6 | 31-34 (4 distinct) | 33-40 (2 distinct) | 1.11x | 1.34x |
| `laptop_smoke` | 227 | 17-26 (5) | 13-31 (14) | 2.97x | 3.91x |

"Cost" is the surface-cell inflation from freezing the grid to the family maximum.
Freezing to the maximum only ever raises a design's resolution, so it is inflation
and never a loss of fidelity.

Two caveats, both material:

- **The `coarse` row is six cases.**  1.11x is encouraging, not established.  The
  number to trust comes after the 95-design desktop campaign.
- **The `laptop_smoke` row pools runs with different level specs**, so its 2.97x
  mixes between-run variation into what should be within-family spread.  It
  overstates the real cost and should not be quoted as the family number.

On the 100-design sweep at smoke level, `n_u` was **17 on all 100 designs** - the
floor bound every one of them.  That is a property of the coarse smoke spacing, not
evidence that the chordwise count is naturally uniform; at `coarse` it varies 31-34.

## The finding

**The wall surface is already a structured tensor grid.**  Each side is built as an
`(n_v, n_u)` array of nodes.  Freeze the two counts and node correspondence is
exact and index-based, for roughly 1.11x mean surface-cell inflation at `coarse`.
That is cheap, and it is the whole prerequisite for S6-style deformation.

**The tip cap is the blocker.**  `_polygon_delaunay_triangles` triangulates the
projected perimeter of *that design*, so connectivity follows geometry: two designs
with identical counts can still get different cap connectivity.  Worse, the routine
returns `None` on any conformity, area or Qhull failure and the caller falls back to
the ladder, so some designs may be capped by a different algorithm entirely.

**Which designs took which path is not recorded.**  The surface report carries
`sampling`, `topology`, `fidelity` and the rest, but nothing identifying the cap
method.  So the existing artifacts cannot answer how often the fallback fires.
That instrumentation gap has to close before the risk can even be sized.

## What follows, in order

1. **Record the cap method** in `source_surface_report.json` - Delaunay or ladder,
   plus the resulting connectivity hash.  One field, no meshing cost.  Until this
   exists the question is unanswerable from artifacts.
2. **Re-run the surface sweep** (surface only, cheap) and count how many designs
   fall back.  If the fallback never fires, the problem is only connectivity
   variation, not algorithm variation.
3. **Freeze the counts** to the family maximum behind a policy flag, leaving the
   present behaviour as the default until the evidence supports switching.
4. **Compute the cap pattern once on a template** and apply it by index everywhere,
   validating per design with the instruments that already exist - conformity,
   minimum area, self-intersection.  Any design that fails validation is excluded
   from the deform family rather than silently re-triangulated.
5. Only then attempt template-and-deform, and audit the deformed result with the
   same gates as a directly meshed one.

## Honest status

This establishes that freezing is **affordable** and identifies **exactly what
blocks it**.  It does not establish that template-and-deform works for S7; nothing
has been deformed yet.  The cost figure rests on six production cases and needs the
full campaign behind it.
