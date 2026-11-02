# Shape ranges and airfoils: where each one comes from (Stage 1)

Decided 29 Oct 2026 (Mike: "anchor our choices based on sources. everything must make sense").
Sizes (root chord, aspect ratio) come from real wings: see `conventional_ranges.md`.
Ranges live in `configs/wing.yaml`. Tags: **checked** = I read the source myself;
**agent** = read by the research agent only; **second-hand** = a textbook quoted by another page.

## Sources

| key | source | what it gives | tag |
|---|---|---|---|
| Raymer | aircraftdesign.com/?p=132 | "Normally the dihedral is about 0 to 5 degrees or so." | checked |
| Raymer (course) | computationaldesignlab.github.io/aircraft-design/wing_layout.html | taper about 0.4 for unswept wings; washout −3° for good stall; 0° c/4 sweep at low speed | second-hand |
| Lednicer | m-selig.ae.illinois.edu/ads/aircraft.html | NACA 4415 root and tip on RQ-2 Pioneer and Shadow 200 | checked |
| Wang & Zhou 2022 | Aerospace 9(1):36 | BWB sections at 0 / 0.48 / 1.00 / 2.00 m, chords 1.80 / 1.10 / 0.70 / 0.25 m (ratios 0.61 / 0.39 / 0.14); no twist | checked |
| Suewatanakul et al. 2022 | Aerospace 9(5):275 | BWB UAV: body MH 104 (15 %), wing MH 61 (10 %), reflexed; 30° c/4 sweep; 5° dihedral; twist 2.5 / 3 / 0° | checked |
| Lehmkuehler et al. 2012 | ICAS2012-675 | small BWB UAV (16 kg, 3 m): wing sweep limited to 15° for roll stability; S5010 wing | checked |
| Hainline & Agarwal 2017 | core.ac.uk/download/233235722.pdf | BWB: chord 0.667 at 10 %, 0.42 at 25 %, tip 0.13; twist 6° → −1° (7° washout); reflexed EH sections | checked |
| Milenković-Babić et al. 2024 | FME Trans. 52(4):556 | flying wing: taper 0.667, LE sweep 25°, AR 4.29, MH 60 | checked |
| Panknin example | b2streamlines.com/Panknin/Panknin.html | flying wing: taper 0.85, 17° c/4 sweep, AR 10, about 3.2° washout | checked |
| Hepperle MH 45 / MH 60 / MH 91 | mh-aerotools.de/airfoils | MH 45 and MH 60: tailless, low moment; MH 60 for Re ≥ 1.5 × 10⁵, MH 45 below. MH 91: paraglider and kite section | checked |
| Guiler & Huebsch 2008 | ICAS2008-335 | Horten-Panek PUL-10: 35° sweep, 4° dihedral | agent |
| Shams et al. 2020 | Micromachines 11(6):553 | flying-wing MAV: 40° LE sweep, 2° dihedral | agent |
| BlendedNet | arxiv.org/html/2509.07209 | Group 3 BWB, inner sweep 40–60°, tip 0.06–0.09, no twist: a different class, not used for ranges | agent |

## Changes made on 29 Oct 2026

| what | before | now | why |
|---|---|---|---|
| BWB airfoils | MH 91, MH 91, E374, NLF1015 (AERIS) | MH 104, MH 104, MH 61, MH 61 | MH 91 is a paraglider section; NLF(1)-1015 is a HALE section (Re 0.7–2 × 10⁶); the new pair flies on a small BWB UAV (Suewatanakul 2022) |
| Flying-wing airfoils | MH 45 root, MH 60 tip | MH 60 root, MH 45 tip | Hepperle: MH 60 for higher Re (root), MH 45 for lower Re (tip) |
| BWB tip chord | 0.08–0.20 | 0.06–0.20 | BlendedNet reaches 0.06 (edge case) |
| BWB sweep 1 | 20–40° | 15–40° | Lehmkuehler 15° |
| BWB dihedral panel 3 | 0–8° | 0–5° | Raymer 0–5° |
| Tailed sweeps | −10° to +20° | −5° to +15° | low-speed wings near 0° c/4; no UAV source for −10° |
| Tailed washout | up to 7° | up to 5° (root 0–2°, tip −3–0°) | Raymer about 3°; 5° as the edge |
| Tailed dihedral | −3° to +6° | 0–5° | Raymer 0–5° |
| Cranked per-panel chords | 0.80 / 0.70 / 0.50 – 1 | 0.85 / 0.75 / 0.65 – 1 | overall taper ≥ 0.41 (Raymer about 0.4) |
| Flying-wing taper | 0.30–0.80 | 0.30–0.90 | Panknin 0.85 |
| Flying-wing sweep | 10–35° | 10–40° | flying-wing MAV 40° |

## Still our choice (no source)

- Layout shares `b3_ratio` 0.20–0.50 and `split_ratio` 0.30–0.70 for tailed and flying wings (breaks anywhere in
  25–80 % of the span). BWB values match Wang & Zhou (0.50, 0.48).
- Twist at b1 and b2 (between the root and tip values).
- Sweep falls outboard on the BWB (20–40 → 15–35 → 5–25°): matches the BWB papers' shape, not a cited number.

## Before the paper

- Check Raymer (taper 0.4, washout −3°, Table 4.2 dihedral) in print.
- Read Guiler & Huebsch 2008 and Shams 2020 directly.

## Two spaces: full and focus (decided 30 Oct 2026)

Mike: design everything, but make the wings and the simulations dense where the real wings are.

- **Focus** (`ranges`, `airfoils`): the ranges above, from real wings and papers. Sets: training 100,
  reference 5, hold-out 10 per type.
- **Full** (`full_ranges`, `full_airfoils`): everything the generator supports. Sets: training 40,
  hold-out 5, corner 1 and corner 2 per type. The corners now test the edges of the full space.
- The focus box must lie inside the full box, and each suggested section must be a full candidate
  (the YAML is refused otherwise).
- Airfoils: **supported** = any database file, local file or NACA formula; **suggested** = the
  per-type list with a source (focus). The full space draws every sourced section on any type.
- Full bounds (our choice, the widest value in any source): Pliakos et al. 2025 design-space bounds
  (twist ±5° at the breaks, ±7° at the tip; dihedral ±10°; c/4 sweep 0–60°), BlendedNet (sweep 60°,
  tip 0.06), Wang & Zhou (root 1.8 m), Hainline (root twist 6°), Prandtl-D (washout about 10°).

## AUTh (Panagiotou, Yakinthos) BWB work, read 30 Oct 2026

| source | what it gives | tag |
|---|---|---|
| Antoniou et al. 2025, Eng. Proc. 90(1):18 | RX-3 tactical BWB: MTOW 260 kg, S 4.9 m², c/4 sweep 33°, AR 8, cruise 160 km/h | checked |
| Panagiotou et al. 2021, Aerospace 8(1):13 | tactical BWB 200–600 kg; kink at y/b 0.32; Re 1.8–2.9 × 10⁶ on the MAC; SA, y+ < 5, 8 M nodes | checked |
| Pliakos et al. 2025, Eng. Proc. 90(1):52 | automated CFD preprocessing for UAV wings; planform bounds (Table 2); TE 1 % chord; first TE cell ¼ of TE thickness | checked |
| Kapsalis et al. 2026, Eng. Proc. 133(1):95 | RX-3 1:3 subscale: span 2.4 m, 6 kg, 70 km/h | agent |
| AST 2018 (MALE BWB), AST 2021, AIAA 2020/2022, ICUAS 2020 | airfoils and station chords | paywalled, not read |

Effect: BWB focus root chord 0.40–0.80 → 0.40–1.80 m (the old range was sized on small flying wings);
RX-3 added to `configs/real_uavs.yaml` (span from √(AR·S) = 6.26 m; Wikipedia gives 7.2 m).
No AUTh paper names its BWB airfoils in an open text, so the suggested BWB pair stays MH 104 / MH 61.

## Aspect-ratio fix found by the full space (30 Oct 2026)

With large washout, 4 full-space wings missed their aspect ratio by 0.11–0.24 %. Causes: the mean
chord assumed a linear chord (the true chord of a twisted ruled panel is shorter mid-panel), and the
extra section at the trailing-edge switch used the linear chord and twist, so it sat off the panel.
Now K integrates the true chord and the switch section sits on the ruled panel. Worst error on 730
built wings: 0.00004 %.

## Cranked made distinct from tapered (30 Oct 2026)

Mike: the two looked alike. The old cranked focus (per-panel chords 0.85/0.75/0.65–1, sweeps −5–15°
each) gave mostly straight-tapered wings with faint breaks. Now: constant-chord centre (inner 0.95–1,
sweep −3–3°), mildly tapered middle (0.80–1, sweep −5–10°), clearly tapered outer panel (0.50–0.85,
sweep 0–15°); overall taper 0.38–0.85. Layout as on Hermes 450 and Heron (from photos; our choice).

## XFOIL model-band proxy (30 Oct 2026)

`scripts/xfoil_band.py`: each suggested section, free transition (Ncrit 9) vs tripped at 1 % chord,
Re 1e5 / 3e5 / 1.5e6 / 3e6, 0–8°. Tripped profile drag is +37–128 % (median 76 %) at Re ≥ 3e5, 0–4° (2-D proxy); close at 1e5 (long bubble).
