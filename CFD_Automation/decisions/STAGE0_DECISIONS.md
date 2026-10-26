# Stage 0 decisions

Each value: what we chose, why, and the source. Values in `stage0_values.yaml`.
1 drag count = 0.0001 of CD.

## D1 — Accuracy targets

| value | choice | why | source |
|---|---|---|---|
| Increment target | ΔCD ≤ 2 counts, ΔCL ≤ 0.005 | We mostly rank wings, and wings differ by a few counts. Shared mesh errors cancel in the difference. | Morrison et al.: "Industry's goal is ±1 drag count." |
| Absolute drag | max(3 % of CD, 3 counts) | Can't be tighter than expert groups agree. | Levy et al. 2013: DPW-V spread σ = 0.00053 (≈ 5 counts) |
| Absolute lift | max(1 % of CL, 0.005) | Lift converges faster than drag. | our choice |
| Pitching moment | 0.002 | Starting value. | our choice |
| Grid split | chordwise 35 %, spanwise 15 %, wall-normal 20 %, edges/base 15 %, wake 15 % | Each mesh study gets a share to stop against. Revised after the first error map. | our choice |
| Other errors | iterative ≤ 10 %, domain ≤ 10 %, numerics ≤ 15 % of total | Every error source stays bounded. | Celik 2008 (iterative ≥ 1 order below grid error); Eça & Hoekstra 2006 (2–3 orders) |
| Grid share | 65 % of total | 100 − 10 − 10 − 15 = 65 | — |
| Turbulence-model error | own band, never in the grid budget | Mesh error and model error are different. | ASME V&V 20-2009 |

## D2 — Wings and sets

| value | choice | why | source |
|---|---|---|---|
| Reference wings | 5 per type: all mid-range; smallest area; largest area; most sweep + smallest tip chord; strongest twist | Few enough to study deeply, spread enough to show change. Fixed before any mesh. | our choice |
| Coverage check | coverage ≤ median of 1,000 random sets of five | Proves the five are spread out. Coverage = largest distance from a training wing to its nearest reference wing (variables in [0, 1]). | Johnson et al. 1990 |
| Training set | 100 per type, Latin hypercube, fixed seed | Even spread over all variables. | McKay et al. 1979 |
| Corner set 1 | 2 × n wings (each variable at each bound) | Shows where one variable breaks the rules. | our choice |
| Corner set 2 | smallest N with C(N−1, ⌈N/2⌉) ≥ n | Every pair of variables at all four low/high combinations. | Katona 1973; Kleitman & Spencer 1973 |
| Hold-out | 10 per type, Latin hypercube, other seed, opened once at the end | Only honest test on unseen wings. | Dwork et al. 2015, 2017 |
| Robustness | 0 failures in ≥ 150 wings → ≥ 98 % success, 95 % confidence | Zero-failure bound. | Hanley & Lippman-Hand 1983 |

**Corner set 2, n = 17:** N = 7 → C(6, 4) = 15 < 17. N = 8 → C(7, 4) = 35 ≥ 17. So N = 8.
Corner sets together: 2 × 17 + 8 = 42 wings.

**Robustness, n = 150:** failure bound = 1 − 0.05^(1/150) = 1 − e^(−2.9957/150) = 1 − 0.98022
= 1.98 %. Rule of three: 3/150 = 2.0 %.

## D3 — Conditions and measurement

| value | choice | why | source |
|---|---|---|---|
| Speed | Mach ≤ 0.3 | Class I–II fly subsonic. Transonic later. | our choice |
| Reynolds (on MAC) | 3 × 10⁵, 1.5 × 10⁶, 5 × 10⁶ | Covers small Class I and Class II (see below). | NATO class table; ISA; Sutherland |
| Angles | 0°, 4°, 8°; 12° for nose and wake | Cruise, climb, high lift. Nose needs finer cells at high angle. | our choice |
| Quantities | CL, CD (pressure + friction), CM, neutral point, cp at sections, y+ | Pass only if all pass at every angle. | our choice |
| Mesh family | ≥ 3 meshes, refinement ratio r ≥ 1.3 | Fewer than three give a trend, not an error. | Celik 2008 |
| Error estimate | GCI, safety factor 1.25; least squares if results scatter | Standard procedure. | Celik 2008; Roache 1994; Eça & Hoekstra 2014 |
| Oscillating results | no estimate; investigate | Meshes not yet where the estimate holds. | Celik 2008 |
| One change per run | one setting at a time; wing fixed in a mesh study | Otherwise the cause can't be named. | our choice |
| Turbulence model | Spalart–Allmaras, no transition; low-Re drag carries a model band | At low Re transition sets drag. | Crivellini et al. 2014 |

**Reynolds check.** Re = ρVc/μ, ISA atmosphere, Sutherland viscosity.

| altitude | ρ [kg/m³] | μ [Pa·s] | ρ/μ [s/m²] |
|---|---|---|---|
| 0 m | 1.2250 | 1.789e-5 | 6.85e4 |
| 1,524 m | 1.0555 | 1.741e-5 | 6.06e4 |
| 3,048 m | 0.9046 | 1.692e-5 | 5.35e4 |

| aircraft (class) | speed | Re per m chord | chord for 3e5 |
|---|---|---|---|
| Raven (I mini) | cruise 8.3 m/s, sea level | 5.7e5 | 0.53 m |
| ScanEagle (I small) | cruise 24.7 m/s, 1,524 m | 1.5e6 | 0.20 m |
| Shadow (II) | cruise 36 m/s, 3,048 m | 1.9e6 | 0.16 m |
| Hermes 450 (II) | max 48.9 m/s, sea level | 3.3e6 | 0.09 m |

Example: 6.06e4 × 24.7 = 1.50e6 per metre. Reaching 3 × 10⁵ needs 3e5 / 1.50e6 = 0.20 m chord.

Result: small Class I and Class II sit between 3 × 10⁵ and about 3 × 10⁶. Mini/micro Class I
(Raven, 1.4 m span) sit below 3 × 10⁵. 5 × 10⁶ is a safe upper end.

## D4 — Working rules

| rule | why | source |
|---|---|---|
| Mesh name `<family>_<level>_<wing_hash8>` | One name, one mesh. | — |
| Outcomes: accepted, rejected, needs review | Countable. | — |
| Failures stay in every count | No inflated success rates. | — |
| Thresholds written before results | No tuning the test to the answer. | Nosek et al. 2018 |
| Hold-out opened once, at the end | See D2. | Dwork et al. 2015 |
| Trial results kept apart from final results | Only the frozen setup is evidence. | — |
| Figures and tables built by scripts from stored data | Anyone can rebuild them. | — |
