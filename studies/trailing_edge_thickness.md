# Study — Trailing-edge thickness for the small BWB ISR UAV

Date: 2026-07-25 · Config: `configs/geometry/bwb.yaml` · Related: DECISION-0004 ·
Code: `standalone/te_thickness_study/` · Evidence:
`configs/geometry/te_thickness_evidence/te_thickness_aero.{md,json}`

## Description

Our four station airfoils (mh91 / mh91 / e374 / nlf1015) all have **sharp**
trailing edges. A flyable UAV cannot be built with a razor-sharp TE, and the AERIS
structured surface mesh requires a **finite** (blunt) TE to march. We must therefore
choose a TE thickness that is simultaneously **manufacturable**, **meshable**, and
**aerodynamically negligible** — and defend that choice. This study quantifies the
aerodynamic cost of blunting the TE, on our exact airfoils at our exact Reynolds
numbers, and combines it with the manufacturing and meshing constraints.

## Assumptions

- Aircraft: small BWB ISR UAV. Chords root 0.95 m → tip 0.10 m (seed-1001 baseline);
  cruise V ≈ 28 m/s, sea level.
- **Reynolds regime** (V·c/ν, ν≈1.46×10⁻⁵): root ≈ 1.8×10⁶, MAC ≈ 7.7×10⁵,
  **tip ≈ 1.85×10⁵** — low-to-moderate Re; the tip is the hard case.
- Blunt-TE construction: open the TE to gap t/c by a linear symmetric opening about
  the chord line (Δy = ±½·t·x/c) — sharp LE and camber preserved, gap = t at x/c=1.
  This is the standard flatback construction and matches how the AERIS mesh/CAD open
  the TE (`minimum_te_thickness_fraction`).
- Aerodynamics: NeuralFoil (XFoil-trained) via `get_aero_from_coordinates`,
  n_crit=9, α ∈ [−6,14]°, at Re = tip/MAC/root. Operating CL = 0.4.
- Manufacturing: molded composite / foam / FDM small-UAV TE floor ≈ **0.5 mm**.
- Meshing: pyHyp structured-march needs a finite TE; an assumed **~0.25%c**
  marchability floor (UNVALIDATED — see Open items).

## Literature anchors

- **Hoerner, *Fluid-Dynamic Drag* (1965):** base (afterbody) drag of a blunt TE
  grows ≈ linearly with TE thickness — the mechanism behind the ΔCd trend below.
- **Standish & van Dam, "Aerodynamic Analysis of Blunt Trailing Edge Airfoils"
  (J. Solar Energy Eng., 2003)** and **Winnemöller & van Dam (AIAA 2007):** blunt /
  "flatback" TEs raise CL and CL_max and add base drag; below ~0.5%c the lift/moment
  change is minor and the drag penalty is small — reproduced here for our case.

## Method

`standalone/te_thickness_study/study.py`: for each airfoil × Re, sweep TE gap ∈
{0, 0.25, 0.5, 1.0, 2.0}%c, run a NeuralFoil α-polar, and report ΔCd at the
operating CL (in **drag counts**, 1 count = 1×10⁻⁴), ΔCL_max, and ΔCm0 vs the sharp
baseline.

## Results

Representative (full tables in the evidence file):

| TE %c | ΔCd @CL=0.4 (counts) | ΔCL_max | ΔCm0 | verdict |
|---|---|---|---|---|
| 0.25 | ~0–5 (mh91/e374/nlf1015) | +3…+5% | small | negligible |
| **0.50** | **~1–7** | **+4…+6%** | **small (nlf1015 larger)** | **negligible** |
| 1.00 | ~5–12 | +5…+8% | moderate | marginal |
| 2.00 | ~13–19 | +8…+11% | notable | significant |

- **Drag is ~linear in TE thickness** (Hoerner). ≤0.5%c ⇒ a few drag counts at the
  section level; since the largest %c falls at the **tip** (smallest area), the
  aircraft-level ΔCd is far smaller than any section number.
- **CL_max increases** with blunting (van Dam flatback effect) — a *benefit* for
  stall margin, not a penalty.
- **Cm0** shifts slightly negative; small for mh91/e374. nlf1015 shifts more but its
  tip location carries little area, so the aircraft trim impact is small.
- **Low-Re tip bonus:** at Re≈1.85×10⁵ a blunt TE on nlf1015 *reduces* Cd
  (0.0283 → 0.0230 at 0.5%c) by mitigating laminar trailing-edge separation — so at
  the tip, where a manufacturing TE is largest in %c, blunting *helps*.

## Wing-level increment (the actual driver)

Section drag is informative but **not** the driver — the aircraft ΔCD is. Integrating
the per-section blunt-TE increment over the actual wing, area-weighted
(`standalone/te_thickness_study/wing.py`, seed 1001, each section blunted to its own
floor `max(0.25%c, 0.5 mm)` at its own Re/airfoil):

    ΔCD_wing = (2/S_ref) ∫ ΔCd(y)·c(y) dy = **−0.5 drag counts**

(worst single *section* only +0.5 counts). It is slightly **negative** because the
tip carries the largest %c TE but the least area, and the outboard low-Re sections
get the separation *benefit* — so the tiny inboard base-drag penalty is offset.
Against a total wing CD ≈ 100–120 counts this is **< 0.5% of total drag** — negligible.
This is the number that defends the decision, not the section counts.

## Conclusions

1. **Wing-level ΔCD ≈ −0.5 drag counts (< 0.5% of total) — negligible.** The blunt-TE
   floor has no meaningful aircraft-drag cost; the largest %c TE sits at the low-area
   tip and is aerodynamically benign (beneficial at low Re).
2. **≤0.5%c is the aerodynamically negligible range** for our airfoils and Re:
   ≤~7 drag counts at the section level, CL_max slightly improved, Cm small. Above
   ~1%c the drag penalty becomes material.
3. A **0.5 mm absolute** manufacturing TE maps to **0.05%c at root, ~0.5%c at tip** —
   entirely inside the negligible range, and at the tip it is aerodynamically
   *beneficial* at low Re.
4. **Recommendation (DECISION-0004): a FIXED constant 0.5 mm absolute TE along the
   whole span** (1.0 mm if a sturdier edge is needed). Constant wins on both counts:
   most manufacturable (one uniform TE, no spanwise-varying tooling) AND
   aerodynamically best (wing ΔCD −0.9 counts, thinner inboard than the hybrid). Root
   0.05%c / tip 0.52%c — all negligible. The mesh models the as-built 0.5 mm; a
   mesh-only inboard floor (~0.25%c) is applied only if pyHyp cannot march the thin
   root (a numerical artifact, ~0 drag).

## Open items

- The ~0.25%c **pyHyp marchability floor is assumed, not validated** — confirm by a
  real march once the volume mesh is run; tighten the fractional term to the true
  floor.
- This is a 2-D section study (NeuralFoil). A 3-D check (the blunt-TE base drag in
  the ADflow solution) should confirm the aircraft-level ΔCd once CFD is run.
