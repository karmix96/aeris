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
| the full story of S8 | `docs/S8_REPORT_2026-09-15.md` — a running account with dated addenda |
| the SU2 track alone | `docs/SU2_REPORT_2026-09-18.md` |
| how to run the cloud batch | `docs/CLOUD_RUNBOOK.md`, then `docs/S8_CLOUD_BATCH_PLAN.md` for why |
| what state the campaign is in | `docs/STATE_2026-09-10.md` — resume here |
| a number quoted in a report | `reports/s8_*.json` — every figure has a file behind it |
| a specific run's forces | `runs/<campaign>/g<index>/<level>_a<alpha>/result.json` |
| whether a run was accepted | the same directory's `*_gate.json` |
| a readable version of anything | `html/` |

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
