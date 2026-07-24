# pyGeo → CST → NeuralFoil → AVL study — rescued reports

These are the findings from the standalone pyGeo→AVL viscous-correction feasibility
study (Stream B). The generating code is `standalone/pygeo_avl_study/`; the full run
outputs (geometry `.dat`, plots, per-section data) live under `artifacts/pygeo_avl_study/`,
which is **gitignored** — only these REPORTs are versioned as evidence.

| File | Source run |
|---|---|
| `final_study_REPORT.md` | `artifacts/pygeo_avl_study/final_study_20260723T160420+0300/` |
| `full_study_REPORT.md` | `artifacts/pygeo_avl_study/full_study_20260723T155248+0300/` |
| `quick_validation_REPORT.md` | `artifacts/pygeo_avl_study/quick_validation_20260723T152643+0300/` |

Headline (α=4°, pyGeo kSpan=3 vs intended AeroSandbox): CL −2.13%, CDi −5.63%,
corrected CD −2.91%; AVL-CDvis vs independent strip integration agree ~4.10%.
Section convergence 17→33 sections: CL 0.161%, CDi 0.180%. Wide-bound DoE 24/24 pass.
