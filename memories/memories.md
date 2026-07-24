# AERIS — Memories

Single consolidated project memory (Mike's convention: all memories live here).
Decisions live in `decision/` (ADR-style); study write-ups in `studies/`.

---

## User & working style

- **Mike** — founder + lead researcher of AERIS, a BWB-UAV aircraft-design codebase.
  Building toward a defensible PhD multifidelity workflow. Works collaboratively and
  fast; wants decisions made deliberately and documented, and honest/calibrated
  reporting (no overclaiming — say what's verified vs not).
- **Full authority:** act as lead research engineer without asking approval, EXCEPT
  (a) important physics/modelling decisions → surface and confirm; (b) never delete
  the codebase, important files, memory, or evidence; (c) never force-push / rewrite
  history. Emit a clear progress message per change.

## Working conventions (feedback)

- **Decisions → `decision/`** (ADR files, numbered, e.g. `0001-...md`).
- **Studies → `studies/`** (each study: short description, assumptions, results,
  conclusions).
- **Memories → `memories/memories.md`** (this single file).
- **Heavy compute → desktop:** don't launch long/heavy runs in-session (big DoEs,
  full CFD, CAD/Gmsh/pyHyp campaigns, 50-case visual batches). Prepare runnable
  runbook commands for Mike; a single case / modest sweep in-session is fine.
- **Findings live in `configs/`:** rescue REPORT/evidence out of `data/`+`artifacts/`
  (gitignored, regenerable) into tracked `configs/` before anything is wiped.
- **Save data in the project tree** (never /tmp or scratch for deliverables).
- **Nothing saved by default:** geometry/CAD/mesh/plot outputs off unless requested
  at run time (CLI flag / GUI toggle).
- **Mesh inspection:** Mike inspects meshes in ParaView, not custom plots.

## Key decisions (see decision/ for full ADRs)

- **Master geometry = the smooth MACH-Aero pyGeo B-spline loft.** Do NOT force it to
  interpolate the piecewise Aeris authored stations. The pyGeo loft's metrics are
  authoritative; sub-% smooth-vs-piecewise shifts live in the design space, not
  errors. (Validation gate = frame reconstruction + reference metrics + control
  invariance; all pass.)
- **ASB-free AVL target:** AERIS must not construct an `asb.Airplane` for the
  AVL+viscous path. aerosandbox may be IMPORTED (NeuralFoil hard-depends on it).
  Native AVL writer + coordinate-NeuralFoil satisfy this; the geometry path is truly
  aerosandbox-free (guard test).
- **One geometry config:** `configs/geometry/bwb.yaml` for BOTH backends. All other
  geometry configs deleted (suite RED by design until tests are rebuilt).
- **Fixed airfoils at b0/b1/b2/b3:** mh91 / mh91 / e374 / nlf1015 (Panagiotou &
  Yakinthos BWB UAV baseline). NOT AH 94-145. Swap the four `station_airfoils` names
  for any `data/airfoil_database` entry.

## Project state (2026-07-24)

- **pyGeo backend committed** and decoupled from AeroSandbox (geometry import graph
  is asb-free; regression-guarded).
- **Native pyGeo→AVL+viscous chain** (no asb.Airplane): `native_avl.py` +
  `pygeo_avl_adapter.run_pygeo_native_avl_case` + `NeuralFoilCoordinateSource`.
  CLI `aeris aero pygeo-native`; GUI Aero page tab "④ pyGeo native". Matches the
  asb-serialized numbers to 0.1–0.4%.
- **Elevon does pitch + roll:** native AVL emits `<name>_sym` (d1, δe pitch) +
  `<name>_diff` (d2, δa roll); result reports Cm/Cl_roll/Cn/CY. `--control-input-deg`
  (δe) + `--diff-input-deg` (δa). Verified δe→pitch, δa→roll.
- **DoE design space** = `bwb.yaml` ranges (small BWB ISR UAV, full span 1.5–2.5 m,
  AR 2.6–6.2). **20 design variables** = 10 planform + 7 section + 3 elevon geometry
  (start/end/hinge via `elevon_bounds`, so the DoE varies the elevon for the later
  controllability optimization). Root dihedral enforced 0.
- **pyGeo vs ASB comparison** done (`studies/pygeo_vs_aerosandbox_geometry.md`):
  50/50 build both backends; metrics agree <1.3%. Interactive side-by-side 3D viewer
  exists.
- Generator id renamed `bwb_segmented_v1` → **`bwb_segmented`** (config-facing;
  package path unchanged).
- **Geometry creation is opt-in + backend-selectable.** `aeris geometry generate`
  flags: `--backend aerosandbox|pygeo|both`, `--exports iges,tecplot,sections,npz,
  step,stl,obj,vtk` (default NONE; CAD-family auto-enables physical CAD),
  `--physical-cad`, `--save-metrics` (→ `geometry_metrics.json` with span/area/AR/
  MAC/volume/wetted + taper/root/tip, attributed to the backend(s) that built),
  `--seed`. Nothing (CAD/VTK/STEP/plots) written unless requested. GUI geometry page
  "① Create geometry" has two backend tabs (AeroSandbox | pyGeo), pyGeo tab exposes
  the export checkboxes + physical-CAD + save-metrics.

## Technical gotchas (hard-won)

- **`planform_bounds.b_total_m` is the SEMI-span** (full span = 2×). Config comments
  it now.
- **Integrated-metric comparisons MUST extract pyGeo over the FULL span** (margin
  1e-4). A [0.02, 0.98] margin understates span ~4% and biases every integral.
- **NeuralFoil hard-depends on aerosandbox** (imports it at load) — zero-aerosandbox
  viscous is impossible while using NeuralFoil; the target is only "no asb.Airplane".
- **AVL `.avl` airfoil files must be ≤ IBX (~360 pts)** — native writer downsamples
  (cst_points=80 → 159-pt loop); AeroSandbox uses ~99.
- **`section_bounds.airfoil_name`** is the fallback airfoil (overridden per station
  by `station_airfoils`); kept = root airfoil to avoid confusion.
- **Generator-id rename gotcha:** renaming GENERATOR_ID to `bwb_segmented` broke
  code that hardcoded `generator_id != "bwb_segmented_v1"` (neutral + deflected CAD
  export). Fixed to accept `("bwb_segmented","bwb_segmented_v1")`. If more id-gated
  code surfaces, apply the same. Package import path stays `bwb_segmented_v1`.
- **Geometry runs are LEAN by default:** write-only inspection CSVs (control_points/
  planform_sections/section_3d + pyGeo authored/extracted/cst) are gated behind
  `geometry.outputs.save_detail_csv` / `--save-detail` (off). Empty `sections/` dir
  only created when section DATs are written. GUI Visualize tab embeds the pyGeo
  interactive 3-D HTML in-page (streamlit.components.v1.html).

## Key references

- Config: `configs/geometry/bwb.yaml` (the one config).
- Backend: `src/aeris/generators/bwb_segmented_v1/` (pygeo_*.py, PYGEO_BACKEND.md).
- Native AVL: `src/aeris/aero/solvers/native_avl.py`; adapter
  `pygeo_avl_adapter.py`; polar `src/aeris/airfoil/neuralfoil_coordinate_source.py`.
- Comparison tooling: `standalone/pygeo_asb_comparison/`.
- Evidence: `configs/geometry/{pygeo_avl_evidence,pygeo_validation_evidence,pygeo_asb_comparison_evidence}/`.
- Parallel work: Codex owns `standalone/pygeo_surface_mesh_study/` — leave it alone.
