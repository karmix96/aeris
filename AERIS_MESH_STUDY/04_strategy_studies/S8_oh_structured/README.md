# S8 — everything in one place

The O-H structured mesher and its CFD campaign. **All S8 material lives under this directory**,
consolidated on 2026-09-19 so that there is one place to look for any of it.

```
S8_oh_structured/
  *.py *.sh        the code. Left at the top level deliberately -- moving it a
                   level down would shift 33 files' worth of parents[N] path
                   arithmetic, which has already produced three silent bugs
  docs/            reports, plans, runbooks, state, audits        (markdown)
  html/            the rendered, readable versions of those       (published)
  reports/         every machine-readable result                  (json)
  data/            the collected datasets: dataset, dataset_v2, dataset_v2_partial
  external/        experimental and reference data we grade against
  policies/        the signed authorisations for what may run
  runs/            raw run output, 17 GB, never wiped
```

## Where to look for a given thing

| you want | look in |
|---|---|
| **what S8 can and cannot claim** | **`docs/AUDIT_2026-09-20_reliability.md` — read this first** |
| the full story of S8 | `docs/S8_REPORT_2026-09-15.md` — a running account with dated addenda |
| **how the mesh is actually built** | **`html/S8_MESH_METHOD.html` — seven steps, a figure at every step, all drawn from the built mesh** |
| the SU2 track alone | `docs/SU2_REPORT_2026-09-18.md` |
| how to run the cloud batch | `docs/CLOUD_RUNBOOK.md`, then `docs/S8_CLOUD_BATCH_PLAN.md` for why |
| what state the campaign is in | `docs/STATE_2026-09-10.md` — resume here |
| a number quoted in a report | `reports/s8_*.json` — every figure has a file behind it |
| a specific run's forces | `runs/<campaign>/g<index>/<level>_a<alpha>/result.json` |
| whether a run was accepted | `runs/<campaign>/g<index>/<level>_gate.json`, per geometry and level; for the whole campaign, `reports/s8_v2_gate.json` |
| a readable version of anything | `html/` |

## Which `gci_C` do you mean?

**`gci_C` and `gci_M` each name two different meshes**, and nothing in a filename distinguishes
them. Check the tip cap in the mesh summary before combining anything across campaigns:

| family | `gci_C` / `gci_M` cells | tip-cap first cell | where | what it holds |
|---|---|---|---|---|
| **A** | 567,256 / 1,111,152 | **10.20 × s0** (the cap declared defective 13 Sept) | `runs/s8_gci83`, `runs/s8_pilot`, `runs/s8_cfd`, `runs/s8_aniso`, `runs/s8_checklist`, `runs/s8_chi3` | the whole grid-convergence, directional and iterative evidence base |
| **B** | 603,592 / 1,172,856 (g83) | **2.04 × s0** (rebuilt) | `runs/s8_v2` | the 52-run production campaign and `data/dataset_v2` |

The production dataset was re-run after the cap fix; **the verification was not**. The difference is
worth 5.4–7.2 counts of C_D at `gci_C`, so the error bar and the number it decorates currently come
from different meshes. `docs/AUDIT_2026-09-20_reliability.md` §3.1.

## What is in git and what is not

`runs/` holds 17 GB. The **evidence** is committed — 626 files, about 12 MB: `result.json`,
`run_manifest.json`, `memory_watch.json`, gate verdicts, mesh summaries, SU2 histories and
configs. The **bulk** is not: meshes, volume solutions and logs, which are reproducible from the
mesher at the recorded commit and whose `sha256` is in the evidence, so a regenerated file can be
checked against the one that produced a published number.

`runs/` is **never wiped.** Its predecessor, `AERIS_MESH_STUDY/artifacts/`, was documented as
"wiped between campaigns", and that is the reason the first leg of three SU2 runs no longer
exists.

## What did not move

`AERIS_MESH_STUDY/05_s6_cfd_qualification/` keeps the S6-era material and the shared governance
file `POLICY.yaml`, which authorises work across studies. S8's own policies moved here; the
resolvers look in both places, S8 first, so an entry named in the shared policy resolves either
way. `AERIS_MESH_STUDY/artifacts/strategy_studies/` still holds S1, S6 and S7 run data.
