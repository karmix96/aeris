# Families, types, span words and the focus cap (Stage 1)

Decided 31 Oct 2026 (Mike).

## Two families, two types each

| family | types | told apart by (our rules, `labels.classify`) |
|---|---|---|
| tailless | `bwb`, `flying_wing` | `bwb` when root chord ≥ 2.2 × the outer-half mean chord and ≥ 0.5 × the semi-span (or ≥ 2.0 with a 25 % chord loss in the inner 30 %); else `flying_wing` |
| conventional | `cranked`, `tapered` | `cranked` when the leading edge or the chord breaks (a kink: sweep change ≥ 5°, or chord slope × 1.5 across a point); else `tapered` |

- The family is an input (the generator type, or the user for a given wing). A tailless wing must trim
  itself (reflexed sections, sweep with washout); a conventional wing does not, because the aircraft
  trims it elsewhere. That is a property of the aircraft, so it cannot be measured on the wing.
  (Mike, 31 Oct 2026: do not describe conventional wings by a tail; the tail belongs to the aircraft.)
- `wing_type` in `wing.yaml` may be a type, a family (draws its two types) or `mixed` (all four).
- The type formerly called `conventional` is now `cranked`; `conventional` is the family name.
  In `real_uavs.yaml` the family `tailed` is now `conventional`.
- Check on the focus training sets (100 wings each): the rules return the drawn type for 100 % of
  flying-wing, cranked and tapered wings and 86 % of BWB wings (14 slim BWBs read as flying wings).
  Full space: BWB 31 of 40, flying wing 39 of 40, cranked and tapered 40 of 40. Test:
  `test_type_rules_inside_each_family` (≥ 95 % cranked/tapered, ≥ 75 % tailless).
- Labels: `[family, type, shape labels...]`.

## Span words

- **Full span b**: tip to tip, both halves.
- **Semi-span S = b / 2**: root to one tip; the half wing we build, mesh and mirror at y = 0.
- `semi_span_m` is always S. Tables and figures say "full span" or "semi-span", never "span" alone.

## Focus space ends at b = 7 m

- `focus: max_full_span_m: 7.0` in `wing.yaml`, for every type; the full space has no cap.
- Focus sets: a Latin hypercube over the box, keeping only wings with b ≤ 7 m in draw order until
  the set is full (`sample.lhs`). Near the cap the strata are no longer exactly balanced.
- Effect on the real wings: 32 of 34 with an area are in the focus space (not: Hermes 450, 10.5 m;
  Götten UAV 9, 8.7 m); every real span is inside the full space; span-only Class II wings above
  7.7 m (Atlante, Searcher, Aerostar, Seeker 400, Watchkeeper, Herti and others) are full space only.
