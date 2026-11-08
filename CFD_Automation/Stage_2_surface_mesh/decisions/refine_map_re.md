# The refine map by Re level (7 Nov 2026; redone 8 Nov at the new Re levels)

Where transition sits on each reference wing at the four Re levels, and whether the decided bands hold it.

## Update 8 Nov 2026: the new Re levels (decision 78)

The Re levels are now 10⁵, 3 × 10⁵, 10⁶ and 4 × 10⁶ (Stage 0, owner, 8 Nov; were 1.5 × 10⁶ and 3 × 10⁶ in place
of 10⁶ and 4 × 10⁶). The map was run again at the new levels, with the section tables extended to 1.5 × 10⁷ (rows
up to 6 × 10⁶ unchanged), and the as-built check again on its 16 surfaces. The 7 Nov run at the old levels is kept
in `data/studies/refine_map_re_levels_7nov.json`; the numbers further down are that run unless they say otherwise.

Upper side, −5° to 8°: share of the strips whose band fits inside 0–85 % c (in brackets: whose transition itself
stays inside):

| Re | BWB | Flying wing | Cranked | Tapered |
|---|---|---|---|---|
| 10⁵ | 31 % (42 %) | 0 % (0 %) | 0 % (0 %) | 0 % (0 %) |
| 3 × 10⁵ | 49 % (63 %) | 0 % (35 %) | 0 % (17 %) | 0 % (31 %) |
| 10⁶ (new) | 65 % (94 %) | 35 % (100 %) | 12 % (60 %) | 26 % (54 %) |
| 4 × 10⁶ (new) | 97 % (100 %) | 100 % (100 %) | 63 % (95 %) | 58 % (98 %) |
| 1.5 × 10⁶ (7 Nov) | 77 % (97 %) | 51 % (100 %) | 32 % (71 %) | 37 % (66 %) |
| 3 × 10⁶ (7 Nov) | 94 % (100 %) | 97 % (100 %) | 55 % (92 %) | 52 % (94 %) |

- The lower band (0–100 % c) still holds every strip at every level and angle.
- No strip is read at a table edge any more: on 7 Nov 5 BWB root strips were above the tables' top (6 × 10⁶) at
  3 × 10⁶; the tables now reach 1.5 × 10⁷.
- No XFOIL answer, as before, only on the tailless wings at negative angles: up to 46 % of the BWB and 42 % of
  the flying-wing strips (43 % on 7 Nov) at −5°.
- The conclusion stands: the written upper band (0–85 % c) misses the upper transition at 10⁵ and 3 × 10⁵ and on
  0–88 % of the strips at 10⁶ and 4 × 10⁶; as built the upper side has band-size cells to the trailing edge
  (as-built check below, redone on 8 Nov at the new levels: all 16 surfaces at VC pass; the largest upper cell over
  85–99.5 % c is 0.950–0.995 × the band cell, as on 7 Nov; written 0–100 % c, the same ring counts on 16 of 16, no
  node moved by more than 1.4 × 10⁻¹³ c).

Script: `scripts/refine_map_re.py` (about 10 s; `--built` adds the 16 surfaces of the as-built check, about 5 min).
Data: `data/studies/refine_map_re.json` (per wing, the same layout as the first approach, with the grid as "re";
plus the per-wing numbers, a summary, the as-built check and the figure captions). Figures:
`docs/page/refine_re_transition.png`, `refine_re_coverage.png`, `refine_re_no_answer.png`. Code: the Re mode of
`cfdauto/mesh/refine_map.py`. The first-approach refine map (`data/studies/refine_map_reference.json`,
`scripts/refine_map_data.py`) stays the record.

## What was done

- The refine map has a Re mode now (similarity, decision 70). A condition is a Re on the mean chord (10⁵, 3 × 10⁵,
  1.5 × 10⁶, 3 × 10⁶) and a root angle (−5° to 12°, 1° steps). Sea level, unit mean chord. The speed follows from
  the Re: V = Re / (ρ/μ) / mean chord (1.46, 4.38, 21.9 and 43.8 m/s for a 1 m mean chord). The 2-D tables are read
  at Mach 0.1. `strip_map(..., res=RE_LEVELS)`; the Mach mode (the first approach) still works and gives the same
  maps as before.
- Run on the 20 reference wings (5 per type), 13 strips per half wing (3 per panel, as before), with the section
  tables rebuilt on the fixed nose (decision 64, 7 Nov).
- For each wing, Re level, strip and side: where transition sits from −5° to 8° and from −5° to 12°; the band, as
  before (from the earlier of bubble start and transition − 10 % c to the latest of bubble end, transition + 10 % c
  and separation start); whether the decided bands (upper 0–85 % c, lower 0–100 % c) hold it, and by how much they
  fall short; the strips with no XFOIL answer, split by cause.
- As-built check: reference wing 0 of each type at the four Re levels, level VC, the decided rules
  (`configs/surface.yaml`): 16 surfaces. On each, the largest ring cell over 85–99.5 % c against the station's band
  cell. Then the same 16 with the upper band written as 0–100 % c.

## The numbers

**Lower side.** The band 0–100 % c holds every strip at every Re level. The lower transition comes to the leading
edge at negative angles: at −5° its median is 4–29 % c (BWB), 0–10 % c (flying wing), 6–18 % c (cranked, tapered),
lowest at the highest Re.

**Upper side, as written (0–85 % c), −5° to 8°.** Share of strips whose band fits (65 strips per type); in brackets,
the share whose transition itself (no margin) stays inside 0–85 % c:

| Re on the mean chord | BWB | flying wing | cranked | tapered |
| --- | --- | --- | --- | --- |
| 10⁵ | 31 % (42 %) | 0 % (0 %) | 0 % (0 %) | 0 % (0 %) |
| 3 × 10⁵ | 49 % (63 %) | 0 % (35 %) | 0 % (17 %) | 0 % (31 %) |
| 1.5 × 10⁶ | 77 % (97 %) | 51 % (100 %) | 32 % (71 %) | 37 % (66 %) |
| 3 × 10⁶ | 94 % (100 %) | 97 % (100 %) | 55 % (92 %) | 52 % (94 %) |

- How far past 85 % c, for the strips that do not fit (median / largest, % c): at 10⁵, 15 / 15 on every type (the
  band runs to the trailing edge); at 3 × 10⁵, 14–15 / 15; at 1.5 × 10⁶, 3.6 / 11.6 (BWB), 2.1 / 4.8 (flying wing),
  9.3 / 15 (cranked), 10.5 / 15 (tapered); at 3 × 10⁶, 2.2 / 4.7, 0.1 / 0.1, 5.9 / 13.7, 5.8 / 12.6.
- Every wing has a strip that does not fit at 10⁵, 3 × 10⁵ and 1.5 × 10⁶; at 3 × 10⁶, 3 of 5 BWB, 2 of 5 flying
  wings and all cranked and tapered wings.
- The cause is always the transition itself (+ 10 % c), never a bubble or separation, from −5° to 8°. It sits aft at
  low angle and low Re: at −5° the median upper transition is 88 % c (BWB), 100 % c (flying wing), 94–95 % c
  (cranked, tapered) at 10⁵; 46–74 % c at 3 × 10⁶. At 10⁵ some strips stay laminar to the trailing edge (XFOIL
  x_tr = 1): 24 (BWB), 40 (flying wing), 8 (cranked), 9 (tapered) of 65.
- To 12°: the same on the tailless wings. On the conventional wings the trailing-edge separation start (aft of
  85 % c) then sets the band's end on 11–22 strips, and the share that fits falls to 6–9 % at 1.5 × 10⁶ and 25–39 %
  at 3 × 10⁶.

**Upper side, as built.** On all 16 surfaces (all passed every check) the largest upper cell over 85–99.5 % c is
0.950–0.995 × the band cell. So the upper side already has band cells to the trailing edge. Why: both sides of a
ring share one node distribution in arc fraction, and the stricter side wins (decision 60); the lower band is
0–100 % c (decision 74 A), so it sets the upper side's aft part too (within the ratio of the two sides' arc
lengths, 1.01–1.03 on the ten study sections). With the upper band written as 0–100 % c the 16 surfaces come out
the same: the same ring count, and no node moves by more than 1.4 × 10⁻¹³ c (round-off).

**That holds at VC only** (Stage 2, 7 Nov; `data/studies/upper_band_check.json`). On the 20 reference wings × 4 Re,
rebuilt with the upper band written as 0–100 % c and compared with the screen: at VC the same mesh to round-off (the
same ring and station counts on 80 of 80, no node moved by more than 3.0 × 10⁻¹³ c; the node hash rounds to
10⁻¹² c, so 63 of the 80 hashes differ). At F, 0–100 % c adds 2 ring nodes (one per side) on 42 of 80 builds (BWB 16,
cranked 12, tapered 13, flying wing 1), the stations unchanged: +0.39 % cells median, +0.55 % at most. With 0–85 % c
the upper cells over 85–100 % c at F can sit a little above the band cell, inside the 1 % check (BWB reference wing 0
at Re 3 × 10⁵: 0.00501 c against 0.0050 c). So the written rule stays 0–85 % c (7 Nov): writing 0–100 % c is for the
owner to decide, and the screen would need a re-run (about 1.5 h on two cores).

**No XFOIL answer.**

- No strip is below the tables' lowest Re (1.5 × 10⁴): the lowest is 1.77 × 10⁴ (BWB at 10⁵). Five BWB root strips
  are above the highest (6 × 10⁶) at 3 × 10⁶; they are read at the table edge (field `re_clamped`).
- So every strip without an answer is beyond its section's 2-D stall or a failed point. On the tailless wings they
  come at negative local angles (−4.3° to −11.6°, at root angles −5° to 4°: the outboard panels are washed out). At
  −5°: 7 (10⁵), 24, 28 and 30 (3 × 10⁶) of 65 BWB strips; 1, 27, 27 and 28 of 65 flying-wing strips (up to 46 % and
  43 %). That is below the lowest angle XFOIL converges at on the outboard sections (Mach 0.1 tables): MH 61 −6.5° at
  Re 10⁵ to −3.5° at 4 × 10⁶; MH 60 and MH 45 about −6° from 2.5 × 10⁵. Also 2 BWB strip-conditions at 11–12° at 10⁵.
- Conventional wings: none, except at 10⁵ (cranked, 8 strip-conditions at 10–12°; tapered, 5 at 8°; local angles
  5.8–6.6°).
- A strip without an answer at one angle drops out of the band at that angle only. No strip lost every angle, so
  none fell back to the generic band.

## Figures

**`refine_re_transition.png`.**
What it shows: the median transition position over the 65 strips of each type against the root angle, at the four
Re levels, upper and lower side, with the decided bands (upper 0–85 % c, shaded beyond; lower 0–100 % c).
Conclusion: the upper transition moves aft as the angle and the Re fall (at 10⁵ its median sits at 88–100 % c at −5°
on every type, past the upper band's end), and the lower transition comes to the leading edge at negative angles
(median 0–29 % c at −5°), which the lower band holds.

**`refine_re_coverage.png`.**
What it shows: per type and Re level, from −5° to 8°, the share of strips whose band fits inside the written upper
band 0–85 % c (bars), the share whose transition itself fits (ticks), and how far the band's aft end goes past
85 % c.
Conclusion: as written, the upper band misses the upper transition on most strips at 10⁵ and 3 × 10⁵ (0–49 % fit,
short by up to 15 % c, to the trailing edge) and on 3–68 % at 1.5 × 10⁶ and 3 × 10⁶; as built this is no gap,
because the shared node distribution (decision 60) and the lower band 0–100 % c already give the upper side band
cells to the trailing edge.

**`refine_re_no_answer.png`.**
What it shows: the share of strips with no XFOIL answer against the root angle, per type and Re level (none is
below the tables' lowest Re).
Conclusion: only the tailless wings lose answers in numbers, at negative root angles (up to 46 % of the BWB and 43 %
of the flying-wing strips at −5°), where their outboard sections are below the lowest angle XFOIL converges at; the
band there rests on the other angles.

## What changes against the first-approach refine map

- **Conditions.** First approach: each wing at its real size and real speed, Mach 0.03–0.20 at sea level, the
  tables at the flight Mach. The Re on the mean chord then followed the wing's size: 8.7 × 10⁴ – 4.5 × 10⁶ over the
  20 old reference wings, but each wing saw only a × 6.7 slice of it (Mach 0.03 to 0.20). Now every wing is at each
  of the four Re levels, with the tables at Mach 0.1. The grid is recorded as "re" instead of "mach".
- **Wings and tables.** 13 of the 20 reference wings are new picks (similarity). The tables are the rebuilt ones
  (fixed nose).
- **Lower side.** The first approach measured against the old lower band (60–100 % c) and found the lower transition
  near the leading edge at negative angles, outside it. The decided band (0–100 % c) holds it now.
- **Upper side.** The same finding as before (decision 65): at low angle the upper transition can sit past 85 % c.
  First approach (Mach 0.03–0.13, −5° to 8°, all its Re mixed): the band fitted on 48 % (BWB), 9 % (flying wing),
  0 % (cranked, tapered) of the strips. Now, split by Re level, it is mainly a low-Re matter: 0–49 % fit at 10⁵ and
  3 × 10⁵, 52–97 % at 3 × 10⁶. New: the as-built check shows the mesh already has band cells there.

## Limits

The same as the flow dataset: 2-D strips (XFOIL e^N, N_crit 9 = calm air) with one uniform induced angle; no
crossflow transition on swept panels, no 3-D relief of bubbles, no tip effects. Where to look, not the 3-D answer.
XFOIL gives x_tr = 1 when a side stays laminar to the trailing edge; those strips count as transition at the
trailing edge. The as-built check covers wing 0 of each type, not all 20 wings.

## Conclusion

Written per side, the upper band (0–85 % c) does not hold the upper transition at low Re and low angle: at 10⁵ and
3 × 10⁵ only 0–49 % of the strips fit, short by up to 15 % c. As built, the mesh still has band cells there, because
both sides share one node distribution and the lower band is 0–100 % c; so no mesh change is needed, but the rule
as written should say that the upper side's aft part comes from the lower band (or the upper band be written as
0–100 % c, which gives the same 16 surfaces to round-off at VC, but 2 more ring nodes at F on 42 of the 80 reference
builds, +0.39 % cells, and a re-run of the screen). The rules text now says what the built mesh does; the written
band stays 0–85 % c. For the owner to decide.
