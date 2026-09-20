# Validating S8 against a low-speed 3-D measurement

Written 2026-09-21. Supersedes the claim in `AUDIT_2026-09-20_reliability.md` §2 that "no low-speed
3-D BWB experimental dataset exists anywhere". That was too strong, and it was the audit's worst
error: it treated an exact-configuration match as the only kind of validation worth having, and so
concluded that nothing could be done. Several usable datasets exist. None is a BWB, and none
validates drag increments — but that is a much more precise and much more useful statement.

---

## 1. What S8 actually needs validated, separated into two questions

Conflating these is what made the earlier conclusion useless.

| question | what answers it | status |
|---|---|---|
| **A. Does the solver + mesher get the low-speed 3-D pressure field and loads right?** | an experiment at the right Reynolds and Mach number with sectional C_p and integrated C_L, C_m | **open — and closeable, see §2** |
| **B. Does the drag INCREMENT converge, and to what?** | grid refinement. A third level | **open — no experiment can close this, see §4** |

The 20 September audit treated the failure of question A as the headline. It is serious, but B is
what blocks the engineering claim, and B is a numerical question. RIBES does not help with B, and no
dataset will.

## 2. RIBES — the case to implement first

EU FP7 project, tested in the University of Naples "Federico II" closed-circuit low-speed tunnel,
2.0 × 1.4 m test section.

| | RIBES | AERIS S8 |
|---|---|---|
| Mach | **0.10 – 0.12** | **0.0837** |
| Reynolds (MAC) | **1.0 – 1.4 × 10⁶** | **1.53 × 10⁶** |
| Geometry | 3-D tapered half wing | 3-D BWB half wing |
| Measured | C_L, C_D, C_m, sectional C_p, deformation, strain | — |
| Instrumentation | **81 pressure taps over 6 sections**, 25 strain-gauge signals | — |
| Transition | natural **and tripped** (trip ~1–2 % chord) | fully turbulent assumed |

**This is the closest regime match available**, and unlike ONERA M6 it is the *right physics*: low
speed, attached-to-mildly-separated, no shock. The `T40` point (40 m/s, Re ≈ 1.43e6, M ≈ 0.12) sits
within 7 % of S8's Reynolds number. The tripped cases matter especially, because S8 runs fully
turbulent and a tripped experiment is the only fair comparison for that assumption — an untripped
low-Re wing carries a laminar run S8 cannot represent.

**What it will close:** question A. C_L and C_m against measurement at the right Re; sectional C_p at
six stations against a mesher that has never been shown a low-speed 3-D pressure field. That is the
gap the ONERA-M6-on-our-mesh failure left open, and it is the gap that matters for trusting the lift,
moment and neutral-point results S8 already leans on.

### What RIBES will NOT close, and why this needs saying

**It is an aeroelastic database, not a drag database.** The model was built to replicate a metallic
wing box and *deform*; the campaign's purpose was validating fluid–structure coupling, and the
measured deformation is part of the deliverable. Three consequences:

1. **The wing is flexible.** Rigid CFD on the CAD shape compares against a shape the wing was not in.
   The measured deformation lets this be handled, but only by meshing the deformed geometry — which is
   a separate capability S8 does not have. Start at α ≈ 0° and 4°, where loads and therefore
   deflections are smallest.
2. **Half model, closed section, with a standoff.** Balance drag on that arrangement carries blockage,
   wall and mounting-interference corrections. The resulting drag uncertainty is far above the 5–9
   counts S8 cares about.
3. So **do not use RIBES to validate drag.** Use it as a bound — if S8's C_D is within the
   experiment's stated uncertainty, good; if it is wildly outside, that is a real finding. Do not read
   agreement as validation of a drag increment.

**Access:** `ribes-project.eu` currently serves an **expired TLS certificate**, so automated fetching
fails and a browser will warn. The database and the experimental test report are linked from
`/experiments/` and `/Documents/RIBES-ExperimentalTestReport.pdf`. If the certificate blocks
retrieval, the University of Naples Federico II Department of Industrial Engineering is the contact.
Confirmed from the literature rather than from the site: Re 1.0–1.4e6, 30–40 m/s, M 0.1–0.12, 81 taps
over 6 sections, 25 strain-gauge signals, 2 × 1.4 m closed-circuit section.

## 3. The rest of the ladder

| case | Re / Ma | what it is genuinely for | verdict |
|---|---|---|---|
| **RIBES** | 1.0–1.4e6 / 0.10–0.12 | **C_L, C_m, sectional C_p at the right regime.** Tripped cases available | **First. Implement this.** |
| **NASA Juncture Flow** | 2.4e6 / 0.189 | Fully public CAD, C_p, LDV/PIV, oil flow, **measured separation extent**. Tripped, 3-D swept | **Second.** Tests separation and turbulence modelling, which RIBES cannot. No usable integrated drag |
| **SACCON** | 1.6e6 / 0.149 | Swept **tailless** UCAV — closest physics to a BWB. Forces, moments, 200+ taps, PIV | **Best physical match, worst access.** Full data went to NATO AVT-161 participants. Worth a request to DLR/NATO; do not block on it |
| **CRM-HL low-speed** | 1.2–1.8e6 / 0.15–0.23 | Forces, moments, pressures, transition visualisation | Later. Slat/flap complexity is disproportionate for a first validation |
| **NASA BWB low-speed** | — | Actual BWB force/moment testing | **Unusable.** Scales and database proprietary |
| ONERA M6 *(already done)* | 11.7e6 / 0.8395 | Transonic 3-D regression | Keep as a regression only. Wrong Mach, wrong Re, wrong physics. Our mesh misses both preset criteria |

## 4. The honest limit, stated once

**No publicly available dataset validates a 5–9 count drag increment on a low-speed 3-D wing.** Not
RIBES (flexible, half model, FSI-focused), not Juncture Flow (no integrated drag), not SACCON
(access), not CRM-HL (configuration). Wind-tunnel drag at this scale and Reynolds number carries
uncertainty of the same order as the effect or larger.

That is not a gap in this project's diligence. It is a property of the measurement problem. The
consequence is specific:

- **Drag increments can only ever be established numerically here** — by grid convergence, with a
  declared uncertainty. That makes the third grid level and the wall-normal diagnosis the critical
  path, not a validation campaign.
- **What validation buys** is confidence that the pressure field, loads and separation behaviour are
  right at this Reynolds number. Without it, a converged drag number is converged to the wrong answer.
  With it, the numerical uncertainty is the whole uncertainty.
- So the two tracks are **complementary and neither substitutes for the other**. Run RIBES for the
  physics; run `gci_F` for the numerics.

## 5. Acceptance criteria, set before any run

Written now so the result cannot be graded after the fact.

**RIBES, tripped, α 0° and 4°:**

| quantity | accept | note |
|---|---|---|
| C_L | within 5 % **and** within the experiment's stated uncertainty | at matched α, corrections applied |
| C_m | within 0.01 absolute, sign and trend correct | the BWB trim question depends on this |
| sectional C_p | RMS Δc_p ≤ 0.10 at all six stations; suction peak within 5 % | the M6-on-our-mesh test managed 0.074 RMS and 2.6 % peak in transonic flow |
| C_D | **recorded, not graded** | flexibility and half-model corrections exceed the effect size |
| deformation | checked for materiality: if predicted tip deflection changes C_L by >2 %, the rigid comparison is void at that α | decides whether α 6° is usable at all |

**Fail conditions that stop the campaign rather than get explained away:** C_m sign wrong at any α;
sectional C_p RMS > 0.15; or the tripped and untripped cases indistinguishable in the CFD, which would
mean the fully-turbulent assumption is not doing what it is assumed to do.

## 6. Cost, honestly

Not a night's work and not on the critical path for the cloud decision.

| step | effort |
|---|---|
| Obtain RIBES geometry, report and tunnel corrections | hours to days, and may need an email |
| Build the O-H mesh on a tapered rectangular-ish wing | the mesher was written for BWB planforms; expect real work, not a config change |
| Three levels at two angles, tripped | ~12 solves at `gci_C`-scale, fits this host |
| Compare C_p at six stations | a new comparison script; the M6 slicer is a starting point and its defects are documented |
| Juncture Flow afterwards | similar again, plus separation-extent extraction |

**Sequencing recommendation:** do **not** put this ahead of the wall-normal diagnosis or the third
grid level. Those are cheap, they are blocking a spend decision, and they are the reason the current
numbers cannot be quoted. RIBES is the right *next* project — it converts S8 from "verified" to
"validated" — but it answers a different question than the one currently blocking.

---

## Sources

- [RIBES database](http://ribes-project.eu/experiments/) — expired TLS certificate as of 2026-09-21
- [RIBES experimental test report](https://ribes-project.eu/Documents/RIBES-ExperimentalTestReport.pdf)
- [Structural validation of a realistic wing structure: the RIBES test article](https://www.sciencedirect.com/science/article/pii/S2452321618301768) — Re 1.0–1.4e6, 81 taps over 6 sections, 25 strain-gauge signals, 30–40 m/s, M 0.1–0.12, 2 × 1.4 m closed-circuit section
- [Wind Tunnel Model Design and Aeroelastic Measurements of the RIBES Wing](https://ascelibrary.org/doi/abs/10.1061/%28ASCE%29AS.1943-5525.0001199) — confirms the aeroelastic/FSI purpose
- [NASA Juncture Flow experimental database](https://tmbwg.github.io/turbmodels/Other_exp_Data/junctureflow_exp.html)
- [AVT-189 / SACCON, NASA NTRS 20110016545](https://ntrs.nasa.gov/api/citations/20110016545/downloads/20110016545.pdf)
