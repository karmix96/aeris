# AERIS Production Runbook

## 1. Recommended Commands

### Geometry dataset
aeris dataset generate \
  -c configs/geometry/baseline_bwb_25.yaml \
  --n 10000 \
  --sampler lhs_v1 \
  --qc-preset production

### Aero dataset
aeris dataset aero-generate \
  -c configs/geometry/baseline_bwb_25.yaml \
  --n 10000 \
  --sampler lhs_v1 \
  --name aero_dataset_prod \
  --alpha-values -2,0,2,4 \
  --velocity-values 28 \
  --altitude-values 1500 \
  --control-input-values -5,0,5 \
  --qc-preset production

---

## 2. QC Preset Rules

| Preset             | Use case                     |
|------------------|-----------------------------|
| debug             | quick testing / dev         |
| production        | long runs (default choice)  |
| promotion_strict  | dataset acceptance / ML     |

---

## 3. Key Outputs

After run completes:

- aero_dataset.csv
- aero_failures.csv
- aero_dataset_manifest.json
- final_run_summary.json   ✅ MAIN ENTRY POINT
- qc/ (if enabled)

---

## 4. How to Check a Run

Open:

final_run_summary.json

Check:
- exit_code == 0
- successful_aero_rows > 0
- failed_aero_rows reasonable
- QC passed if enabled

---

## 5. Exit Codes

| Code | Meaning |
|-----|--------|
| 0   | success or partial success |
| 1   | failure or QC failure |

---

## 6. Retention Policy (initial)

- KEEP:
  - final dataset root
  - final_run_summary.json
  - manifest
  - CSVs

- OPTIONAL:
  - geometry dataset (production only)

- HEAVY:
  - aero_runs → consider deleting after validation

---

## 7. Common Failures

### AVL not found
→ check --avl-command

### Empty dataset
→ bad sampling or invalid geometry space

### QC failure
→ inspect qc reports

---

## 8. Naming Rules

Always use:
- unique dataset names
- include purpose + timestamp if needed

BAD:
test, dataset1

GOOD:
aero_bwb_prod_2026_03
