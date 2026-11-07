# Wing ranges (Stage 1)

Ranges live in `Stage_1_geometry/configs/wing.yaml`. Same 17 variables for every type (18 before 7 Nov 2026).

> **What changes (7 Nov 2026, decision 70: similarity).** Every wing is now built at unit mean chord
> (mean chord = area / full span = 1), so a wing has no size and the root chord left the vector. The real
> wings below now set only the aspect-ratio ranges and the Re range: they fly at 1.22 × 10⁵ – 3.10 × 10⁶ on
> the mean chord (area / full span), inside the four levels 1 × 10⁵ – 3 × 10⁶ (1 × 10⁵ sits 18 % below the
> slowest real UAV: kept as a margin, Mike, 7 Nov). The root-chord ranges, the generated spans and mean chords
> in metres, and the full-span coverage below are the **first approach** (29 Oct–6 Nov), kept as the record. At unit
> mean chord the coverage check of `scripts/real_uav_check.py` compares real wings with wings of a 1 m mean
> chord, so it means nothing now; the script still runs.

## Size: from real wings, not from a target Reynolds number (first approach, until 6 Nov 2026)

Decided 29 Oct 2026 (Mike): take the size ranges from real Class I and II UAVs; compute the Re those
wings fly at; if it does not reach 5 × 10⁶, lower the top Re level and do not stretch the wings.

Before, the conventional root chord went up to 1.35 m only so that the mean chord would reach
Re 5 × 10⁶ at 56.6 m/s. Neither number had a source, and the BWB sizes were the old AERIS space.

Evidence: `configs/real_uavs.yaml`, every number with its link and its source type (`stype`).
A real wing sets the ranges only if its wing area is published (then mean chord = area / full span).

| family | real wings with a published area | full span | mean chord | aspect ratio |
|---|---|---|---|---|
| tailless (`bwb`, `flying_wing`) | eBee, Trimble UX5, Gatewing X100, Skywalker X8, DeltaQuad Pro, DeltaQuad Evo, Aquila | 0.96–3.76 m | 0.23–0.78 m | 2.9–8.6 |
| conventional (`cranked`, `tapered`) | Black Swift S0, Penguin B, Pioneer, Götten UAVs 1–9, Hermes 450, Ranger, Seeker, Shadow 600, Doyosae, Pchela, Sky Eye | 1.39–10.5 m | 0.14–0.76 m | 4.9–16.0 |

Götten UAVs 1–9: Götten et al. 2021, CEAS Aeronaut. J., Table 2 (open access). Anonymised, 25–230 kg
(five of them Class II, 150–230 kg). Their geometry was "derived from drawings and images" and
remodelled in OpenVSP; stated accuracy of the wetted area about 10–15 %. UAV 10 (630 kg) is above
Class II and is shown but not used.

Hermes 450, Ranger, Seeker, Shadow 600, Doyosae, Pchela: Essari 2015 PhD thesis (Univ. Belgrade),
chapter 2, data "from (1) & (20)" in Jane's style; the references could not be read. Sky Eye: NASA
TM-80132 (full-scale vehicle in the tunnel). Aquila: Lockheed final report USARTL-TR-78-37A, Table 1(A).

Wings with a full span only (sourced, or from the HCDI UAS database v13) are checked on full span alone.

Size ranges of the first approach (`python scripts/real_uav_check.py` checked that every real wing with an area has a
generated wing within 10 % in full span and in mean chord, and that every wing with only a full span is inside
the full-span range):

| type | root chord | aspect ratio (sampled) | generated full span | generated mean chord |
|---|---|---|---|---|
| bwb | 0.40–0.80 m | 3–9 | 0.6–3.8 m | 0.17–0.47 m |
| flying_wing | 0.25–1.05 m | 3–9 | 0.5–7.6 m | 0.16–0.92 m |
| cranked | 0.13–0.75 m | 4.5–16.5 | 0.5–10.2 m | 0.09–0.71 m |
| tapered | 0.13–0.75 m | 4.5–16.5 | 0.4–11.0 m | 0.09–0.73 m |

Since 29 Oct 2026 the aspect ratio is sampled and the semi-span derived (`planform_laws.md`). All 26
real wings with an area are covered (the Aquila by the flying-wing type), and all 59 real spans are
inside a generated range.

History: BWB root chord was 0.70–1.10 m and semi-span 0.75–1.25 m (AERIS). Conventional root chord was
0.15–1.35 m. On 29 Oct 2026 the BWB semi-span was briefly set in metres (0.45–1.75 m), which gave flying
wings an aspect ratio up to 19 (real: at most 8.6); it is now set in root chords, like the other types.

Result (first approach): every real wing with an area was covered (the Aquila by the flying-wing type); every
span-only conventional wing (Class I and II, up to the Watchkeeper's 10.9 m) and every Class I tailless wing was
inside the full-span range. Since 7 Nov 2026 there is no full-span range in metres.

## HCDI UAS database v13 (Mike's dashboard)

794 entries; 76 fixed-wing Class I–II; 18 give a full span; none gives a wing area. Weak points: no source
per row; 28 rows share cruise 35 m/s, endurance 6 h and range 100 km (defaults); on 8 rows cruise is
above top speed; Orlan-10 listed as Class II at 18 kg; Puma LE as a flying wing; XQ-58 Valkyrie (a jet)
as Class II. Only full span, class, MTOW and payload are used.

## Reynolds number

Re = (ρ/μ) · V · mean chord, with Stage 0's air (ρ/μ 6.85 × 10⁴ s/m² at sea level, 5.35 × 10⁴ at 3,048 m).
Low: cruise speed at 3,048 m. High: top speed (cruise or loiter if none) at sea level.

- Real wings in our families: **1.2 × 10⁵ (Black Swift S0) to 2.74 × 10⁶ (RUAG Ranger at top speed)**.
- Class II wings at top speed and sea level: Ranger 2.74, Hermes 450 2.20, Pioneer 2.13, Seeker 2.12 × 10⁶.
  Götten et al. give loiter speeds only (Re ≤ 1.5 × 10⁶).
- None reaches 5 × 10⁶ (only the Sperwer does: a delta wing outside our families, area from a
  secondary site; and the Vindicator, a target drone above Mach 0.3). So the Stage 0 top level is
  lowered from 5 × 10⁶ to **3 × 10⁶** (2.74 × 10⁶ rounded up).

## What the evidence cannot cover yet

- Tailless Class II wings (Fury 5.2 m, Albatroz 7 m, Shahed 191 7.3 m) have no published area and stay
  outside the BWB full-span range.
- Generated conventional wings reached AR 21 (before the aspect ratio was sampled, 29 Oct); real ones with a
  known area reach 16.5.
- Mini Class I wings fly at 1.2–2 × 10⁵, below the lowest Re level of that time (3 × 10⁵); the 1 × 10⁵ level
  was added on 30 Oct 2026.
- The NTNU UAV database (93 UAVs, full span, AR, estimated chord; DataverseNO, CC0) is blocked from the
  cloud workspace.
- The Verstraete et al. 2018 sizing correlations (856 UAVs) could not be read (paywall).

## Shape ranges

Since 29 Oct 2026 every shape range and airfoil has its source in `shape_ranges.md`.
