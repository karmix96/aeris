# Wing ranges (Stage 1)

Ranges live in `geometry/configs/wing.yaml`. Same 18 variables for every type.

## Size: from real wings, not from a target Reynolds number

Decided 29 Oct 2026 (Mike): take the size ranges from a short, sourced table of real Class I and II
UAVs; compute the Re those wings fly at; if it does not reach 5 × 10⁶, lower the top Re level and do
not stretch the wings.

Before, the conventional root chord went up to 1.35 m only so that the mean chord would reach
Re 5 × 10⁶ at 56.6 m/s. Neither number had a source (Stage 0's fastest aircraft was 48.9 m/s), and
the BWB sizes were the old AERIS design space.

Evidence: `configs/real_uavs.yaml` (every number with its link). A real wing counts for the ranges
only if its wing area is published, because only then is its mean chord (area / span) known.

| family | real wings with a published area | span | mean chord | aspect ratio |
|---|---|---|---|---|
| tailless (our `bwb` type) | eBee, Trimble UX5, Gatewing X100, Skywalker X8, DeltaQuad Pro, DeltaQuad Evo | 0.96–2.69 m | 0.23–0.38 m | 2.9–8.6 |
| with a tail (our `conventional` and `tapered` types) | Black Swift S0, Penguin B, AAI Pioneer | 1.39–5.15 m | 0.14–0.55 m | 9.4–13.8 |

New size ranges (`python scripts/real_uav_check.py` checks that every real wing above has a
generated wing within 10 % in span and in mean chord):

| type | root chord | semi-span | generated span | generated mean chord |
|---|---|---|---|---|
| bwb | 0.40–0.80 m (was 0.70–1.10) | 0.45–1.40 m (was 0.75–1.25) | 0.90–2.80 m | 0.17–0.47 m |
| conventional | 0.13–0.60 m (was 0.15–1.35) | 2–6 root chords (unchanged) | 0.56–7.0 m | 0.09–0.58 m |
| tapered | 0.13–0.60 m | 2–6 root chords | 0.55–6.9 m | 0.09–0.60 m |

All nine real wings are covered.

## Reynolds number

Re = (ρ/μ) · V · mean chord, with Stage 0's air (ρ/μ 6.85 × 10⁴ s/m² at sea level, 5.35 × 10⁴ at 3,048 m).
Low: cruise speed at 3,048 m. High: top speed (cruise if none published) at sea level.

- Real wings in our families: **1.2 × 10⁵ (Black Swift S0) to 2.1 × 10⁶ (AAI Pioneer)**.
- None reaches 5 × 10⁶. The only one that does is the Sperwer (delta wing with a V-tail, outside our
  families, area from a secondary site).
- So the Stage 0 top level is lowered from 5 × 10⁶ to **2 × 10⁶** (`Stage 0_Decisions/stage0_values.yaml`).

## What the evidence cannot cover yet

- Hermes 450 (10.5 m), Watchkeeper (10.9 m), Aerostar (8.7 m), Shadow V2 (6.2 m) and Ranger (5.71 m)
  have published spans but no published wing area. The ranges stop at the Pioneer (5.15 m span), so
  the generator covers Class I and small Class II. Find those areas before widening.
- Mini Class I wings fly at 1.2–2 × 10⁵, below the lowest Re level (3 × 10⁵).
- With real flying-wing sizes, about a quarter of the bwb-type wings are slim flying wings without a
  centre body; the label rule calls them "conventional".

## Shape ranges (unchanged, our choice)

| variable | BWB | conventional (cranked) | tapered |
|---|---|---|---|
| chord ratios | c2 0.55–0.80, c3 0.30–0.55, c4 0.08–0.20 of the root (AERIS) | per panel: 0.80–1, 0.70–1, 0.50–1 | taper 0.40–1 |
| sweeps | 20–40°, 15–35°, 5–25° (AERIS, signed) | −10° to +20° each panel | one sweep, −10° to +20° |
| twist b0 / b1 / b2 / b3 | −1–1 / −3–0 / −5 to −1 / −8 to −2° | 0–3 / −1–2 / −2–1 / −4–0° | same as conventional |
| dihedral | b0, b1 0–3°; b2 0–6°; b3 0–10° | −3° to +6° each station | same as conventional |
| airfoils | MH91, MH91, E374, NLF1015 | NACA 4415, 4415, 4412, 4412 | same as conventional |
