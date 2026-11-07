# Families, types, span words and the focus cap (Stage 1)

Decided 31 Oct 2026 (Mike).

> **What changes (7 Nov 2026, decision 70: similarity).** The focus cap of 7 m full span is gone: every wing is
> now built at unit mean chord, so its full span equals its aspect ratio (in mean chords), which has its own
> range. A config that still has `max_full_span_m` is refused. The families, the types, the type rules and the
> span words stay. The type rules use ratios, so they work the same at unit mean chord.

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
- Check on the focus training sets (100 wings each, the sets of 7 Nov 2026): the rules return the drawn type
  for 100 % of flying-wing, cranked and tapered wings and 85 % of BWB wings (15 slim BWBs read as flying wings;
  86 % and 14 on the sets before 7 Nov). Full space: BWB 31 of 40, flying wing 39 of 40, cranked and tapered
  40 of 40. Test:
  `test_type_rules_inside_each_family` (≥ 95 % cranked/tapered, ≥ 75 % tailless).
- Labels: `[family, type, shape labels...]`.

## Span words

- **Full span b**: tip to tip, both halves.
- **Semi-span S = b / 2**: root to one tip; the half wing we build, mesh and mirror at y = 0.
- `semi_span_m` is always S. Tables and figures say "full span" or "semi-span", never "span" alone.
- At unit mean chord (since 7 Nov 2026) b = aspect ratio and S = AR / 2, in mean chords.

## Focus space ended at b = 7 m (first approach, 31 Oct–6 Nov 2026; gone 7 Nov)

- Then: `focus: max_full_span_m: 7.0` in `wing.yaml`, for every type; the full space had no cap.
- Then: focus sets were a Latin hypercube over the box, keeping only wings with b ≤ 7 m in draw order until
  the set was full (`sample.lhs`); the strata were not exactly balanced near the cap.
- Now: the same draw of 2n rows, the first n kept (`sample.focus_rows`), so 99 / 90 / 91 / 88 of the 100
  focus shapes stay the same (BWB / flying wing / cranked / tapered; the cap had chosen by root chord). The
  strata are still not exactly balanced (the first n of 2n rows).
- Effect on the real wings then: 32 of 34 with an area were in the focus space (not: Hermes 450, 10.5 m;
  Götten UAV 9, 8.7 m); every real full span was inside the full space; span-only Class II wings above
  7.7 m (Atlante, Searcher, Aerostar, Seeker 400, Watchkeeper, Herti and others) were full space only. At unit
  mean chord this check means nothing: a real full span is only a scale, set through the Re of a solve.
