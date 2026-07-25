# DECISION-0005 — Native pyGeo→AVL: complete output capture, full-span extraction, exact elevon extent

Status: ACCEPTED (three sub-decisions; (2) and (3) change every low-fi number and
are flagged for Mike's review)
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Supersedes nothing. Evidence: `studies/native_avl_output_and_fidelity.md`,
`configs/aero/native_avl_verification_evidence/`.

Task-1 outcome of the low-fi AVL hardening pass. Confirming that the pyGeo→AVL
chain "runs clean" surfaced two modelling defects that were silently corrupting
every low-fidelity number; both are fixed here, and the fixes are recorded as
decisions because they move the answers by 30–110 %.

---

## 1. The native path captures the complete AVL output family

**Decision.** `run_native_avl_case` dumps and parses everything AVL can export
and stores it in the result plus `native_avl_result.json`.

Before: totals only (CL, CD, CDind, CDvis, Cm, Cl, Cn, CY, CDff). After:

| group | captured |
|---|---|
| totals | + CX, CZ, CLff, **e** (span efficiency), Sref/Cref/Bref, all reduced rates, every control deflection, `# Surfaces / # Strips / # Vortices` |
| stability axis (`st`) | all 25 derivatives (CLa…Cnr) + **Xnp** + `Xnp/Cref` |
| body axis (`sb`) | all 18 derivatives (CXu…Cnw) |
| **control authority** (`st`) | per control: CL_δ, CY_δ, Cl_δ, Cm_δ, Cn_δ, CDff_δ, e_δ — mapped from AVL's `d01`/`d02` slots back onto `elevon_sym` / `elevon_diff` |
| hinge moments (`hm`) | Chinge per control (actuator sizing) |
| surface forces (`fn`) | per-surface breakdown, both Sref- and Ssurf-normalised |
| strips (`fs`) | full strip table → `strips_parsed.csv` |
| shear/bending (`vm`) | Vz/qSref, Mx/qBrefSref vs 2y/b → `strip_shear_moment.csv` (structural loads) |
| body forces (`fb`) | raw file retained |
| derived | spiral metric Clb·Cnr/(Clr·Cnb) |

**Parser is now shared.** The AVL text parsers moved into
`src/aeris/aero/solvers/avl_output.py` (pure `re` + pandas, imports no
aerosandbox). `aerosandbox_avl.py` re-exports them under their historical private
names, so the native path and the AeroSandbox reference path read AVL through
**one** validated parser instead of two divergent copies. Unit-tested against
verbatim AVL dumps in `tests/aero/test_avl_output_parsers.py`.

**Keystrokes aligned.** The native runner now drives AVL with the same keystroke
sequence as the reference path (graphics off; `o r d` for body-axis rate
convention + derivative output; explicit Mach/velocity/density/g; body rates p/q/r
from the FlightCondition, which the native path previously ignored).

**Verification.** `standalone/lowfi_avl_study/verify_native_vs_asb.py` runs both
solvers off the *same* pyGeo sections and compares field by field. Fields present
in the ASB result but missing from the native result: **NONE**. On the clean
symmetric case every shared field agrees to ≤ 0.6 %, and the physics-carrying ones
far better: CLa 8e-7, Xnp 4e-6, CD 5e-4, e 2e-3, Clp 5e-5, Cmq 2.5e-3.

**Static margin is NOT reported by default.** AVL's moment reference is
Xref=(0,0,0), the geometry origin — not the CG. `x_np_over_c_ref` is always
reported; `static_margin` is only filled when the caller passes a CG via
`moment_reference_m=` and asserts `moment_reference_is_cg=True`, otherwise a
warning explains why. Reporting `(Xnp − 0)/Cref` as a static margin would have
been a fabricated number.

## 2. Section extraction spans the FULL span (`span_margin` 0.02 → 0.0)

**Decision.** `build_pygeo_sections_from_config(..., span_margin=0.0)` is the
default. Sections are extracted at `linspace(0, 1, n)`; both span ends are exact.

**Why.** The old default inset the extraction by 2 % at both ends. Under
`YDUPLICATE` the innermost section at y>0 is mirrored about y=0, so the AVL model
was **two half-wings separated by a 33 mm centreline gap** — AVL shed a spurious
inboard tip-vortex pair — while the tip was simultaneously truncated. This also
contradicted the existing rule that integrated metrics must be extracted over the
full span.

**Magnitude** (baseline seed, α=3°, 25 sections, viscous;
`standalone/lowfi_avl_study/probe_span_margin.py`):

| margin | gap (m) | CL | CLα /rad | e | L/D | Bref | CL err | CLα err |
|---|---|---|---|---|---|---|---|---|
| **0.02** (old default) | 0.0326 | 0.02230 | 2.741 | 0.316 | 3.39 | 1.5666 | **−54.9 %** | **−26.2 %** |
| 0.01 | 0.0163 | 0.02657 | 2.863 | 0.334 | 4.01 | 1.5992 | −46.3 % | −22.9 % |
| 0.005 | 0.0082 | 0.03021 | 2.982 | 0.358 | 4.52 | 1.6156 | −38.9 % | −19.7 % |
| 0.001 | 0.0016 | 0.03842 | 3.288 | 0.437 | 5.70 | 1.6286 | −22.3 % | −11.5 % |
| 1e-4 | 0.0002 | 0.04729 | 3.632 | 0.537 | 6.94 | 1.6315 | −4.4 % | −2.2 % |
| **0.0** (new default) | 0.0000 | 0.04945 | 3.715 | 0.562 | 7.25 | 1.6319 | — | — |

The error is monotonic in the gap and vanishes only at margin exactly 0 — the
1e-4 margin used elsewhere for metric extraction still costs 2.2 % of CLα here,
because the AVL model is far more sensitive to the centreline gap than an
integrated geometric metric is.

CLα = 3.72 /rad for this swept AR≈4.1 wing is physically sensible; 2.74 /rad was
not. **Every low-fi aero number produced before this change is invalid.**

A guard now warns whenever the innermost section sits at >0.1 % of semi-span, so
this cannot regress silently.

## 3. The elevon spans exactly its geometric extent

**Decision.** Two changes make the AVL control extent equal the geometry's
`[elevon_start_frac, elevon_end_frac]`:

- the extraction grid **snaps two sections onto the band edges**
  (`snap_sections_to_control=True`);
- the writer tags **every** section inside the band including both boundary
  sections (previously the outboard-most section of the band was skipped).

**Why.** AVL interpolates the control gain linearly between sections, so a band
edge is only where a section declares it. The old rule let the gain taper 1→0
across the outboard-most interval, silently losing part of the elevon — and
because the extent was quantised to the section grid, the DoE's three elevon DVs
would have produced a **staircase** control response instead of a smooth one,
which would break gradient-based controllability optimisation.

**Magnitude.** Elevon pitch authority CL_δe: 0.00810 → **0.00945 /deg (+16.7 %)**;
Cm_δe −0.004399 → −0.005138 /deg. Tagged span is now exactly 0.600–0.950 of
semi-span, matching the sampled `elevon_start_frac`/`end_frac`.

**Residual, stated honestly.** A perfectly sharp cutoff would need duplicated
break sections at the band edges. Without them the gain still tapers over the
half-interval just outside each edge — ≈6 % of elevon span at 25 sections, and it
shrinks as sections increase. Quantified in the section-count study (Task 4a).

## 4. Consequence for the AeroSandbox reference path (finding, not a change)

The comparison exposed two structural limits of the ASB path, which is why the
lateral case disagrees while the symmetric case matches to <0.6 %:

- **It cannot deflect an elevon differentially.** AeroSandbox's AVL exporter
  collapses all control surfaces into a single variable `all_deflections` with
  SgnDup +1. AVL reports `1 Control variables`. The `d2` keystroke targets a
  variable that does not exist, so δa is silently ignored: measured Cl_roll is the
  sideslip contribution alone (−0.00093 vs the native −0.00583 at δa=2°, β=2°).
- **Its elevon over-extends to the wing tip** (tagged span 0.600–1.000 vs the
  geometry's 0.600–0.950).

The native path is therefore not merely an AeroSandbox-free replacement — it is
the only one of the two that can model the roll authority the DoE's elevon DVs
exist to optimise. The ASB path stays as the symmetric-case cross-check only.
This is left unfixed deliberately: fixing AeroSandbox's exporter is out of scope
and the native path supersedes it.

## Open

- Duplicated break sections for an exactly sharp elevon cutoff (quantified, not
  implemented).
- Cref definition differs 0.13 % between paths (native ∫c²dy/S vs ASB
  `mean_aerodynamic_chord()`); harmless but worth unifying.
- The ASB path warns about a Mach/velocity inconsistency on every run
  (`input mach=0` vs derived 0.082) — pre-existing, metadata only.
