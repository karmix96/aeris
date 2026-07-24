# DECISION-0002 — DoE design space, controls, and output policy

Status: ACCEPTED (ranges PROPOSED — adjust the aircraft scale freely)
Date: 2026-07-24
Owner: Mike (with Claude as lead engineer)

Answers Mike's questions on `configs/geometry/bwb.yaml`.

## 1. Generator name

`geometry.generator.id: bwb_segmented` (was `bwb_segmented_v1`). The registry key
`GENERATOR_ID` is now `bwb_segmented`; a suffix-less id resolves to family
`bwb_segmented` / internal version `v1`. The Python package path
`aeris.generators.bwb_segmented_v1` is unchanged (internal import path only).

## 2. `section_bounds.airfoil_name`

It is the single FALLBACK airfoil, used only when `station_airfoils` is absent.
With `station_airfoils` present (our case), it is overridden per station, so it is
just a schema default. Kept = the root airfoil (`mh91`) to avoid confusion. (Future
cleanup option: make it optional and default to `station_airfoils.b0`.)

## 3. Root dihedral = 0 (enforced)

Yes. `dihedral_root_deg: 0.0` (fixed) + `dihedral_b1_deg: {0, 0}` (pinned) +
`pygeo.enforce_flat_root_panel: true`. The whole b0→b1 root panel is flat, so the
root airfoil sits at zero dihedral by construction. `dihedral_b1` stays pinned to 0
across the DoE (only b2/b3 dihedral vary).

## 4. DoE ranges — small BWB ISR UAV (PROPOSED)

Bounds are ranges (this file IS the DoE design space; one sample = the baseline).
Confirm/adjust the SCALE (root chord, span) — these are my proposed values:

| var | range | | var | range |
|---|---|---|---|---|
| c1_m (root chord) | 0.55–0.90 m | | twist_b0 | −1..+1° |
| c2_ratio | 0.55–0.80 | | twist_b1 | −3..0° |
| c3_ratio | 0.35–0.60 | | twist_b2 | −5..−1° |
| c4_ratio | 0.10–0.25 | | twist_b3 | −8..−2° (washout) |
| b_total_m (span) | 1.80–2.80 m | | dihedral_b1 | 0 (pinned, flat root) |
| b3_ratio | 0.40–0.55 | | dihedral_b2 | 0–6° |
| split_ratio | 0.40–0.60 | | dihedral_b3 | 0–10° |
| sw1/sw2/sw3 | 20–40 / 15–35 / 5–25° | | | |

## 5. Control surfaces — symmetric AND asymmetric

One trailing-edge elevon pair, driven by two AVL controls on the same hinge:
`elevon_sym` (SgnDup +1 → d1) = symmetric **pitch** (δe); `elevon_diff`
(SgnDup −1 → d2) = differential **roll** (δa). Net: right = δe+δa, left = δe−δa.
`aeris aero pygeo-native --control-input-deg <δe> --diff-input-deg <δa>`.
Verified: δe drives Cm (pitch, no roll); δa drives Cl_roll (roll, no pitch). The
native-AVL result now reports Cm / Cl_roll / Cn / CY for controllability.

## 6. Save nothing unless requested

All outputs default OFF in the config (`save_plot: false`, `physical_cad.enabled:
false`, every `pygeo.outputs.*: false`). Artifacts are enabled per run via CLI
flag / GUI toggle. (Follow-up: add explicit output flags to the geometry/aero CLI
+ GUI so runs can opt specific artifacts back in.)

## 7. Design variables — 20 total

10 planform (c1_m, c2/c3/c4_ratio, b_total_m, b3_ratio, split_ratio, sw1/sw2/sw3) +
7 section (twist_b0..b3, dihedral_b1..b3) + **3 elevon geometry** (elevon_start_frac,
elevon_end_frac, elevon_hinge_frac). Adding `elevon_bounds` activated the elevon
DVs, so the DoE now varies the elevon size/position — the optimizer can search for
the elevon that meets the controllability requirement. Deflections (δe, δa) are
flight/control inputs, swept at aero time per geometry, NOT geometry DVs.
