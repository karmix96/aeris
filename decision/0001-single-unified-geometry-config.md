# DECISION-0001 — Single unified geometry config

Status: ACCEPTED
Date: 2026-07-24
Owner: Mike (with Claude as lead engineer)

## Resolution (Mike, 2026-07-24)

**Option A.** The four fixed airfoils sit at the existing **b0 / b1 / b2 / b3**
station positions (the planform group boundaries), via the existing
`station_airfoils` schema — "as is the plan already". No new schema. The earlier
0.00/0.35/0.60/1.00 fractions were conceptual; b0–b3 is the actual placement.
"Airfoils from the database" = swap the four `station_airfoils` names for any of
the 2181 database airfoils. Controls with/without deflection = one elevon block +
a deflection field (0 = neutral).

## Context

AERIS currently has 14 geometry configs under `configs/geometry/` and two
*parallel, un-unified* airfoil-assignment mechanisms in the schema:

- `section_bounds.station_airfoils` (`b0/b1/b2/b3`) — drives the **geometry loft**;
  airfoils land at the **planform kink positions** (group boundaries), which for
  the nominal BWB are ~0.225 / 0.50 of semispan, NOT arbitrary fractions.
- `section_bounds.segment_airfoils` (`[{airfoil_id, y_frac_end}]`) — drives the
  **AVL polar bridge** (2D airfoil per span segment).

This split is confusing and means "which airfoil is where" is answered differently
for geometry vs aero.

## Decision

1. **One geometry config** replaces all of `configs/geometry/*.yaml`:
   `configs/geometry/bwb.yaml`. It is **backend-agnostic** — the same file drives
   AeroSandbox and/or pyGeo via `outputs.build_aerosandbox` and `pygeo.enabled`.

2. **One airfoil-station schema** — a position-explicit list, used by BOTH the
   geometry loft and the polar bridge, for BOTH backends:

   ```yaml
   section_airfoils:
     stations:
       - {span_frac: 0.00, airfoil: mh91}
       - {span_frac: 0.35, airfoil: mh91}
       - {span_frac: 0.60, airfoil: e374}
       - {span_frac: 1.00, airfoil: nlf1015}
   ```

   - Any `airfoil` name resolves against `data/airfoil_database` (2181 airfoils),
     so "4 fixed" and "chosen from the database" are the same mechanism — just
     different names/positions. 4 entries = the Paper-1 baseline; N entries = a
     free choice.
   - Airfoils are placed at the **exact** span fractions given (not planform
     kinks), so the baseline sits at 0.00/0.35/0.60/1.00 as intended.

3. **Paper-1 fixed-airfoil baseline** (Panagiotou & Yakinthos BWB UAV):
   `mh91 / mh91 / e374 / nlf1015` at `0.00 / 0.35 / 0.60 / 1.00`.
   Explicitly NOT AH 94-145 (drives Cm too negative → constant trim).
   Later sensitivity set: `mh104 / mh104 / mh18 / fx76mp120`.

4. **Control surfaces with or without deflection** — one `control_surfaces` block
   defines the elevon; a single deflection field (`0` = neutral/no deflection,
   nonzero = deflected) drives both the pyGeo split-CAD and the AVL/native-AVL
   control command. No separate "controls" vs "no-controls" config.

## Refinement (from Codex's `pygeo_surface_study_simple.yaml` reference)

That config already runs the `mh91/mh91/e374/nlf1015` baseline via the EXISTING
`station_airfoils` schema, with **3 equal semispan panels** → kinks at ~0.333/0.667
(≈ the requested 0.35/0.60). And on the pyGeo master path the **viscous polar is
built from the realized surface sections** (`build_realized_section_polar_bridge`),
not from `segment_airfoils` — so `station_airfoils` alone drives the loft AND the
aero follows automatically. The geometry/polar split only mattered for the legacy
ASB polar bridge.

⇒ The 4-airfoil baseline needs **no new schema**. Reuse `station_airfoils`.

## Open fork (needs Mike) — airfoil-station positions

- **Option A (recommended, low-churn):** reuse `station_airfoils` with **3 equal
  panels** → airfoils at 0.00 / ~0.333 / ~0.667 / 1.00. No code change; matches
  Codex's working reference; "airfoils from the database" = just change the four
  names. Downside: positions are the planform kinks (~0.333/0.667), not exactly
  0.35/0.60.
- **Option B (exact positions):** introduce the `section_airfoils.stations`
  list with explicit `span_frac`, decoupling airfoil position from the planform
  kinks so 0.35/0.60 are hit exactly. Cost: params/sections parser + wiring +
  validation code, and a compatibility path for the loft's station-boundary logic.

Both keep everything else identical. The difference is only whether the two inner
airfoil stations sit at the planform kinks (A) or at user-chosen fractions (B).

## Migration plan (either option)

- Author `configs/geometry/bwb.yaml`; verify it builds with pyGeo AND AeroSandbox
  and runs native-AVL viscous.
- Repoint the ~30 src references (CLI help/defaults, GUI config list) and ~40 test
  references to `bwb.yaml` (or parametrize tests). Delete the other 13 configs only
  after references are migrated and the suite is green.
- Record the airfoil-baseline rationale here; future airfoil swaps update this doc.
