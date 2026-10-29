# Wing ranges (Stage 1)

Ranges live in `geometry/configs/wing.yaml`. Same 18 variables for every type.

## Size: from real wings, not from a target Reynolds number

Decided 29 Oct 2026 (Mike): take the size ranges from real Class I and II UAVs; compute the Re those
wings fly at; if it does not reach 5 × 10⁶, lower the top Re level and do not stretch the wings.

Before, the conventional root chord went up to 1.35 m only so that the mean chord would reach
Re 5 × 10⁶ at 56.6 m/s. Neither number had a source, and the BWB sizes were the old AERIS space.

Evidence: `configs/real_uavs.yaml`, every number with its link and its source type (`stype`).
A real wing sets the ranges only if its wing area is published (then mean chord = area / span).

| family | real wings with a published area | span | mean chord | aspect ratio |
|---|---|---|---|---|
| tailless (`bwb`) | eBee, Trimble UX5, Gatewing X100, Skywalker X8, DeltaQuad Pro, DeltaQuad Evo, Aquila (not covered) | 0.96–3.76 m | 0.23–0.78 m | 2.9–8.6 |
| with a tail (`conventional`, `tapered`) | Black Swift S0, Penguin B, Pioneer, Götten UAVs 1–9, Hermes 450, Ranger, Seeker, Shadow 600, Doyosae, Pchela, Sky Eye | 1.39–10.5 m | 0.14–0.76 m | 4.9–16.0 |

Götten UAVs 1–9: Götten et al. 2021, CEAS Aeronaut. J., Table 2 (open access). Anonymised, 25–230 kg
(five of them Class II, 150–230 kg). Their geometry was "derived from drawings and images" and
remodelled in OpenVSP; stated accuracy of the wetted area about 10–15 %. UAV 10 (630 kg) is above
Class II and is shown but not used.

Hermes 450, Ranger, Seeker, Shadow 600, Doyosae, Pchela: Essari 2015 PhD thesis (Univ. Belgrade),
chapter 2, data "from (1) & (20)" in Jane's style; the references could not be read. Sky Eye: NASA
TM-80132 (full-scale vehicle in the tunnel). Aquila: Lockheed final report USARTL-TR-78-37A, Table 1(A).

Wings with a span only (sourced, or from the HCDI UAS database v13) are checked on span alone.

New size ranges (`python scripts/real_uav_check.py` checks that every real wing with an area has a
generated wing within 10 % in span and in mean chord, and that every span-only wing is inside the span
range):

| type | root chord | semi-span | generated span | generated mean chord | generated AR |
|---|---|---|---|---|---|
| bwb | 0.40–0.80 m | 0.75–2.2 root chords | 0.62–3.46 m | 0.17–0.47 m | 2.7–10.2 |
| conventional | 0.13–0.75 m | 2–7.5 root chords | 0.58–11.0 m | 0.09–0.72 m | 4.5–21 |
| tapered | 0.13–0.75 m | 2–7.5 root chords | 0.56–10.7 m | 0.09–0.75 m | 4.1–21 |

History: BWB root chord was 0.70–1.10 m and semi-span 0.75–1.25 m (AERIS). Conventional root chord was
0.15–1.35 m. On 29 Oct 2026 the BWB span was briefly set in metres (0.45–1.75 m), which gave flying
wings an aspect ratio up to 19 (real: at most 8.6); it is now set in root chords, like the other types.

Result: every real wing with an area is covered except the Aquila (a swept, moderately tapered flying
wing: neither type makes it); every span-only wing with a tail (Class I and II, up to
the Watchkeeper's 10.9 m) and every Class I tailless wing is inside the span range.

## HCDI UAS database v13 (Mike's dashboard)

794 entries; 76 fixed-wing Class I–II; 18 give a span; none gives a wing area. Weak points: no source
per row; 28 rows share cruise 35 m/s, endurance 6 h and range 100 km (defaults); on 8 rows cruise is
above top speed; Orlan-10 listed as Class II at 18 kg; Puma LE as a flying wing; XQ-58 Valkyrie (a jet)
as Class II. Only span, class, MTOW and payload are used.

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
  outside the BWB span range.
- Generated wings with a tail reach AR 21; real ones with a known area reach 16.5.
- Swept, moderately tapered flying wings (Aquila: taper 0.58, LE sweep 28°) are not made by any type.
- Mini Class I wings fly at 1.2–2 × 10⁵, below the lowest Re level (3 × 10⁵).
- 14 % of bwb-type wings are slim flying wings without a centre body; the label rule calls them
  "conventional".
- The NTNU UAV database (93 UAVs, span, AR, estimated chord; DataverseNO, CC0) is blocked from the
  cloud workspace.
- The Verstraete et al. 2018 sizing correlations (856 UAVs) could not be read (paywall).

## Shape ranges (unchanged, our choice)

| variable | BWB | conventional (cranked) | tapered |
|---|---|---|---|
| chord ratios | c2 0.55–0.80, c3 0.30–0.55, c4 0.08–0.20 of the root (AERIS) | per panel: 0.80–1, 0.70–1, 0.50–1 | taper 0.40–1 |
| sweeps | 20–40°, 15–35°, 5–25° (AERIS, signed) | −10° to +20° each panel | one sweep, −10° to +20° |
| twist b0 / b1 / b2 / b3 | −1–1 / −3–0 / −5 to −1 / −8 to −2° | 0–3 / −1–2 / −2–1 / −4–0° | same as conventional |
| dihedral | b0, b1 0–3°; b2 0–6°; b3 0–10° | −3° to +6° each station | same as conventional |
| airfoils | MH91, MH91, E374, NLF1015 | NACA 4415, 4415, 4412, 4412 | same as conventional |
