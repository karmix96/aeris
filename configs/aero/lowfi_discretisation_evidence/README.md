# Evidence — low-fidelity discretisation (Task 4 + chordwise spacing)

Backs `decision/0009-lowfi-discretisation.md`,
`studies/section_and_panel_convergence.md` and `studies/hinge_panel_alignment.md`.
Rescued out of `data/` (gitignored, regenerable).

Conditions throughout: `configs/geometry/bwb.yaml`, α = 6°, δe = 4°, β = 0°,
V = 28 m/s, sea level, viscous on. Multiple DoE seeds, **worst seed reported**
alongside the median — a discretisation is only converged if it is converged
everywhere in the design space, not on average.

| file | what it is |
|---|---|
| `4a_geometry_sections_chord8.txt` | Geometry-section independence, 5 seeds, with the **total spanwise panel count pinned at 96 per side** so only geometric fidelity varies. Section counts chosen so (n−1) divides 96 exactly → identical 192-strip lattices at every level. Regenerate: `python standalone/lowfi_avl_study/convergence_study.py --mode geometry` |
| `4a_geometry_sections_chord16_replication.txt` | The same study re-run at chordwise 16 (3 seeds), to prove 4a is not an artefact of the unconverged chordwise-8 grid. Regenerate: add `--nchordwise 16 --tag _chord16` |
| `4b_avl_panels.txt` | AVL panel independence at fixed 25 sections: spanwise 1–10 and chordwise 4–20, swept one at a time. Regenerate: `--mode panels --n-sections 25` |
| `hinge_alignment.txt` / `.json` | Chordwise spacing law vs the elevon hinge at x/c = 0.75, including the hinge-to-nearest-panel-edge distance for every configuration, and a uniform-40 vs cosine-40 cross-check confirming both spacing laws converge to the same physics. Regenerate: `python standalone/lowfi_avl_study/probe_hinge_panel_alignment.py` |
| `joint_grid_total_error.txt` | Total discretisation error of the old and new production grids against the best reference that fits AVL's array limits (33 sections / 4 spanwise / 20 chordwise). |
| `joint_grid_check.py` | The joint-check script — kept here because it is a one-off verification, not a reusable study tool. Run from the repo root. |

## Headline numbers

- **`nchordwise` 8 → 24 (DECISION-0009).** At 8 the elevon derivative CL_δe carried
  **7.7 %** error — the largest single discretisation error in the low-fidelity
  chain, and comparable to the AeroSandbox elevon bias that DECISION-0007 judged
  disqualifying. Cause: the hinge at x/c = 0.75 sits 0.059 c from the nearest
  cosine panel edge, so AVL smears the control gain across a panel. At 24 → ~1.1 %.
- **Joint total error, 25/4/8 → 25/4/24:** CL 1.07 % → 0.15 %,
  CDind 3.20 % → 0.51 %, Cm 1.70 % → 0.11 %, **CL_δe 7.06 % → 0.38 %**
  (against the chordwise-20 reference; quote ~1.1 % from the finer cosine-40 one).
- **`n_sections = 25`** gives ≤0.56 % worst-seed on all forces and stability
  derivatives, and is robust to the chordwise grid (verified by replication).
- **Geometric metrics converge far earlier than aerodynamics** — Sref within
  0.05 % by n = 9 while the aerodynamics still carries 1.9 % at n = 13. Area/MAC
  convergence must therefore NEVER be used as a proxy for aerodynamic convergence.
- **CL_δe is non-monotonic in `n_sections`** (n = 13 beats n = 17 and n = 25,
  reproducibly in both the 5-seed and 3-seed runs): an oscillatory ±1.5 % floor set
  by where sections fall relative to the elevon band edges, which uniform
  refinement cannot reliably remove. This is the motivation for adaptive placement.
- **Spanwise 4 panels/interval is adequate** (≤0.54 % worst-seed).
- **Uniform chordwise spacing is rejected.** It halves the elevon error at equal
  cost (3.82 % vs 7.71 % at 8 panels, confirming the hinge-alignment mechanism) but
  degrades Xnp and Cmq by **14–15×**, and the penalty persists under refinement —
  leading-edge clustering is what resolves the pitching moment.
- **Hard AVL array limits:** (n_sections − 1) × spanwise_panels ≤ 250 strips
  (NSMAX = 500 both halves), and strips × nchordwise ≤ ~6000 vortices. 49/4/16
  (6144) and 65/4/anything (512 strips) both fail. A quantified ceiling on what
  uniform refinement can buy.
