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

Adopt a **hybrid per-section TE floor**:

    t_TE(section) = max( 0.25%c · chord,  0.5 mm )

- Inboard (large chord) the **fractional** term governs → ~0.25%c (root ≈ 2.4 mm),
  set by meshability, aerodynamically invisible.
- At the **tip** (small chord) the **absolute** term governs → 0.5 mm ≈ 0.5%c, set
  by manufacturing, at the negligible-aero boundary and beneficial at low Re.
- Every section stays **≤ ~0.5%c** → inside the aerodynamically negligible range,
  while never thinner than 0.5 mm (buildable) or ~0.25%c (meshable).

This matches the mechanism AERIS already implements (mesh/CAD open the TE as
`max(fractional·chord, absolute floor)`).

## Where it applies

- **Mesh** (the path that matters now): set the structured surface-mesh TE to this
  floor — fractional 0.25%c + absolute 0.5 mm — when meshing `bwb.yaml` geometry.
- Physical CAD `minimum_te_thickness_fraction` currently defaults 0.05%c; it is on
  the deferred split-elevon path, so leave it until that path is revived, then align
  to this decision.
- The pyGeo master surface keeps its sharp TE; the blunt TE is a documented
  manufacturing/mesh transformation applied downstream, quantified here.

## Open items

- **Validate the 0.25%c fractional term against a real pyHyp march** and tighten to
  the true marchability floor.
- **3-D confirmation:** verify the aircraft-level blunt-TE base-drag increment in the
  ADflow solution once CFD is run (the 2-D counts here are an upper bound per section;
  aircraft ΔCd is smaller, weighted by area with the largest %c at the low-area tip).
