# ADR-0008 — epsE Selection Protocol

Date: 2026-08-13
Status: Proposed for Stage 02 approval
Fixes the rule **before any result is seen**, per RUNBOOK §2 (no threshold may be
chosen or revised after seeing the answer).

## Context

ADR-0007 moved `epsE_common_start` from cap4 to the first strategy passing all
hard surface gates on all ten calibration geometries, in an implementation order
fixed in advance. That order makes **S1 tip-first** the calibration host. S1 is
the only prototype that is surface-valid, watertight, deterministic and clean on
all ten (`status` §4.2, §4.3).

Nothing about the march is known yet. cap4 passed surface QC and still produced
53 of 128 bad layers, nearly invariant to both epsE and mesh level. This ADR fixes
the selection rule so that result cannot be rationalised after the fact.

## Decision

### 1. Candidate ladder

`epsE ∈ {1.5, 2.0, 3.0}` — identical to Stage 01, so the numbers are directly
comparable to cap4's.

The ladder is **not extended in response to a failure**. Extending it requires a
new ADR stating the physical reason, written before the extra values are run. The
known-bad shipped value `6.0` is excluded.

### 2. Mesh levels

- **Calibration:** L3, matching Stage 01 §3.2 exactly, so the bad-layer count is
  comparable to cap4's 53/128 on the same basis.
- **Confirmation:** the selected value is re-run at one genuinely finer level,
  **`fine`** (coarsen=1, N=193, s0_frac 6e-06) against the calibration level
  `smoke` (coarsen=1, N=129, s0_frac 8.8e-06). A value that passes at `smoke` and
  fails at `fine` is **not** selected.

  *Corrected 2026-08-14.* This ADR originally named `L4` as the confirmation
  level. That was wrong: `L4` is N=37 with coarsen=4, which is substantially
  COARSER than the calibration level, so it would have confirmed nothing. Only
  the `coarsen=1` family (`smoke` -> `fine` -> `production`) forms a refinement
  ladder at full surface resolution.

### 3. Hard pass criteria — verbatim checklist

A run passes only if **all** hold:

- [ ] pyHyp completes the full march (an early-layer march is a preflight, never
      evidence)
- [ ] **zero inverted cells**
- [ ] **zero negative-volume cells**
- [ ] **minimum volume scaled quality strictly > 0** — this is the hard gate.
      `0.30` is a *target and ranking metric only* and must never be applied as a
      pass threshold (ADR-0005, `status` invariant 7)
- [ ] zero negative-quality layers
- [ ] boundary families and connectivity correct and solver-readable
- [ ] deterministic cell and block counts across all ten geometries
- [ ] surface displacement within the geometry-fidelity gate
- [ ] **no per-geometry manual repair of any kind**

### 4. Selection rule

`epsE_common_start` = the **highest** candidate passing the checklist on **all
ten** calibration geometries, then confirmed at the finer level.

### 5. Tie-break

If two values both pass all ten, take the higher — it is the less dissipative
start and leaves more headroom for per-strategy Round B calibration. If they tie
on that too (impossible for distinct values, stated for completeness), take the
one with the higher minimum volume scaled quality on the worst geometry.

### 6. Early-stop rule

- If a candidate fails on **any** geometry, that candidate is out. Do not tune it.
- If **all three** candidates fail the canary geometry (`lhs7_00`), the phase
  **halts immediately**. Do not march the remaining nine geometries and do not
  march S3/S4/S5, which share `stage02_common.py` ingestion and the same tip
  closure — that would buy ten expensive copies of one failure. Diagnose the
  shared tip cap or the marching setup and report.
- RUNBOOK §16 then applies: stop and request a decision.

### 7. Host is not re-chosen

S1 is the host by ADR-0007's pre-fixed order. If S1 fails, the host does **not**
silently pass to S3/S4/S5. A different host requires an explicit ADR recording
why, written before that host is run.

## Conditionality on provisional Reynolds numbers

Operating points are **provisional** (`status` §2.4): no mission YAML exists, the
values are README/RUNBOOK defaults, and no freestream velocity or Mach is stored
per CFD point. First-cell height and boundary-layer spacing derive from Reynolds
number, and pyHyp's marching behaviour depends on that spacing.

Per the Stage 02 close-out plan Phase 0.2, option **(b)** is taken: this
calibration proceeds on provisional Reynolds numbers, explicitly conditional.

**Named re-check task:** `EPSE-RECHECK-ON-MISSION-FREEZE` — when an authoritative
mission source is adopted and `operating_points.yaml` is promoted from
`STAGE_00_PROPOSED` to authoritative, `epsE_common_start` must be re-run under
this same ADR before any Stage 03+ result depending on it is treated as final.
The task is recorded in `operating_points.yaml` under `pending_recheck` so it
cannot be lost.

## Consequences

- Phase 1 may proceed once this ADR and the operating-point resolution are in
  place.
- Any `epsE_common_start` produced now carries the provisional-Re caveat in its
  evidence artifact and in the Stage 02 report. It is not a frozen production
  constant until the re-check clears.
- S1's spanwise geometric-progression law is currently **computed but realised at
  native sections**; Stage 03 redistributes spanwise points. epsE is therefore
  calibrated on the present S1 prototype and needs re-checking after
  redistribution. This is recorded alongside the result, not omitted.
