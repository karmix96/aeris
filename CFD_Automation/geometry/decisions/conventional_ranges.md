# Wing ranges (Stage 1)

Ranges live in `geometry/configs/wing.yaml`. Same 18 variables for both types.

## BWB — taken from AERIS `configs/geometry/bwb.yaml`

Unchanged, except:
- sweeps are signed (+ aft); the AERIS values were already aft, so the numbers stay;
- `dihedral0_deg` 0–3° and `dihedral1_deg` 0–3° (AERIS pinned both at 0, because it rolled the
  root section; see `root_section.md`);
- `split_ratio` now splits the inner span between panels 1 and 2 (AERIS used the same split).

## Conventional — proposed

| variable | range | why |
|---|---|---|
| root chord | 0.15–1.35 m | Raven-size (≈ 0.2 m) up to Hermes-450-size wings; 1.35 m lets the mean chord reach Re 5 × 10⁶ at top speed |
| semi-span / root chord | 2–6 | gives aspect ratio 4–16.5 with the tapers below |
| c2 / c3 / c4 ratio | 0.85–1 / 0.65–1 / 0.40–1 | rectangular to taper 0.4 |
| b3_ratio, split_ratio | 0.20–0.50, 0.30–0.70 | crank anywhere from 25 % to 80 % of span |
| sweeps (each panel) | −10° to +20° | forward to moderate aft, as on Class I–II wings |
| twist b0 / b1 / b2 / b3 | 0–3 / −1–2 / −2–1 / −4–0° | root incidence, washout to the tip |
| dihedral (each station) | −3° to +6° | anhedral to normal dihedral |
| airfoils | NACA 4415 (b0, b1), NACA 4412 (b2, b3) | common thick-root / thinner-tip choice for small UAVs |

Spans from sampling 20,000 vectors: full span 0.63–16.1 m, aspect ratio 4.1–16.5, taper 0.40–1.00.

## Reynolds check

Re = (ρ/μ) · V · MAC. Speeds and air from Stage 0: V = 8.3–56.6 m/s; ρ/μ = 5.346e4 s/m²
(3,048 m) to 6.846e4 s/m² (sea level). MAC range from sampling 20,000 vectors.

| type | MAC [m] | lowest Re (MAC min, 8.3 m/s, 3,048 m) | highest Re (MAC max, 56.6 m/s, 0 m) | at 25 m/s, sea level |
|---|---|---|---|---|
| BWB | 0.369–0.789 | 0.369 × 8.33 × 5.346e4 = 1.6 × 10⁵ | 0.789 × 56.6 × 6.846e4 = 3.1 × 10⁶ | 6.3 × 10⁵ – 1.35 × 10⁶ |
| conventional | 0.120–1.327 | 0.120 × 8.33 × 5.346e4 = 5.3 × 10⁴ | 1.327 × 56.6 × 6.846e4 = 5.1 × 10⁶ | 2.0 × 10⁵ – 2.3 × 10⁶ |

- Conventional covers 3 × 10⁵, 1.5 × 10⁶ and 5 × 10⁶.
- BWB covers 3 × 10⁵ and 1.5 × 10⁶, but not 5 × 10⁶ (stops at ≈ 3 × 10⁶). See OPEN_DECISIONS.
