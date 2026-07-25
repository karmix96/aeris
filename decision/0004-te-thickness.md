# DECISION-0004 — Trailing-edge thickness

Status: ACCEPTED (fractional/mesh floor pending pyHyp march validation)
Date: 2026-07-25
Owner: Mike (with Claude as lead engineer)
Evidence: `studies/trailing_edge_thickness.md`,
`configs/geometry/te_thickness_evidence/`

## Context

The station airfoils (mh91/mh91/e374/nlf1015) have sharp TEs. A flyable small BWB
ISR UAV cannot have a razor-sharp TE (manufacturing), and the AERIS structured
surface mesh needs a finite TE to march. The TE thickness must be chosen so it is
manufacturable, meshable, and aerodynamically negligible — and defensible to an
AIAA committee. Three bounds:

- **Aerodynamic ceiling — WING level is the driver (this study):** the aircraft ΔCD
  from applying the chosen floor over the whole wing (area-weighted, each section at
  its own Re/airfoil/floor) is **≈ −0.5 drag counts (< 0.5% of total CD) —
  negligible**, and slightly favorable (the largest %c TE is at the low-area tip,
  where blunting *helps* at low Re). Section-level: ΔCd is ~linear in TE thickness
  (Hoerner base drag), ≤~7 counts at ≤0.5%c, slightly *raising* CL_max (van Dam
  flatback); >1%c becomes material — but section drag is not the driver, the wing
  integral is.
- **Manufacturing floor:** ≈ **0.5 mm** absolute TE for a small composite/foam/FDM
  UAV.
- **Meshability floor:** pyHyp structured march needs a finite TE; assumed
  **~0.25%c** (UNVALIDATED).

## Decision

**As-built aircraft TE: a FIXED (constant along span) absolute thickness = 0.5 mm.**
(1.0 mm is equally acceptable if the build process wants a sturdier edge.)

Wing-level ΔCD (seed 1001, area-weighted): constant 0.5 mm → **−0.89 counts**;
constant 1.0 mm → −0.75; hybrid max(0.25%c,0.5mm) → −0.54. All negligible; the
**constant** options are the best (thinnest inboard, least base drag) **and** the
most manufacturable.

Why constant (not variable / not fractional):

- **Manufacturability (decisive):** a single constant TE thickness is the easiest to
  produce — one uniform mould land / foam-cut offset / print wall / finishing gauge.
  A spanwise-**varying** TE (a fractional or hybrid law: 2.4 mm at root tapering to
  0.5 mm) needs a spanwise-varying tool/process and is materially harder to build to
  tolerance. Mike's driver: pick the easiest-to-manufacture option that is
  aerodynamically free — that is the constant TE.
- **Aerodynamics:** wing ΔCD ≈ −0.9 counts (< 1% of total) — negligible and
  slightly favorable. Root 0.05%c (invisible), tip 0.52%c (negligible, beneficial at
  low Re). Constant is aerodynamically *better* than the hybrid because it is thinner
  inboard where the area (and thus base-drag weight) is largest.
- **0.5 vs 1.0 mm:** both give wing ΔCD ≈ 0. Use **0.5 mm** as the aerodynamic/clean
  default; step to **1.0 mm** only if a 0.5 mm edge is too fragile for the chosen
  material/process.

## Where it applies

- **Aircraft geometry / manufacturing:** constant 0.5 mm TE, the number that goes to
  the shop and to the as-built CAD.
- **Mesh:** model the AS-BUILT 0.5 mm TE. If a real pyHyp march cannot advance the
  thin inboard TE (0.5 mm ≈ 0.05%c at root), apply a **mesh-only** local inboard floor
  (~0.25%c) — a NUMERICAL artifact of the solver, not a change to the aircraft, and
  quantified here as ~0 drag. This keeps a simple, single-number as-built TE while
  the mesh handles its own marchability. Pending pyHyp validation (see Open items).
- Physical CAD `minimum_te_thickness_fraction` (deferred split-elevon path): align to
  a constant 0.5 mm when that path is revived.
- The pyGeo master surface keeps its sharp TE; the constant 0.5 mm blunt TE is a
  documented downstream manufacturing/mesh transform, quantified here.

## Open items

- **Validate the 0.25%c fractional term against a real pyHyp march** and tighten to
  the true marchability floor.
- **3-D confirmation:** verify the aircraft-level blunt-TE base-drag increment in the
  ADflow solution once CFD is run (the 2-D counts here are an upper bound per section;
  aircraft ΔCd is smaller, weighted by area with the largest %c at the low-area tip).
