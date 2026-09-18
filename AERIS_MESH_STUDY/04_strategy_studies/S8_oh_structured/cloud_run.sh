#!/usr/bin/env bash
# Run the S8 high-fidelity batch on a rented host, end to end.
#
#   bash AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/cloud_run.sh [RANKS]
#
# Deliberately a thin wrapper over code that has already run 52 solves on the
# development host, rather than a new path written for the cloud. The one thing
# that IS new is the preflight, and it is the one thing that must not be
# skipped: on rented compute every failure it checks for bills.
#
# Meshes are built HERE, not uploaded. build_volume.py needs only the project
# venv and takes about 12 s per design; a gci_F CGNS is ~56 MB and gci_FF ~120
# MB, so uploading them trades gigabytes of transfer for seconds of compute.
set -euo pipefail

# 4, not 24. The measured rank probe gives 2121/1121/849/827 s at 1/2/4/6
# ranks: four is 2.7 % slower than six and costs 32 % fewer core-hours, and the
# batch buys throughput across 44 independent cases, not latency on one.
RANKS="${1:-4}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
S="$REPO/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured"
Q="$REPO/AERIS_MESH_STUDY/05_s6_cfd_qualification"
PY="$REPO/.venv/bin/python"
cd "$REPO"

echo "=== S8 high-fidelity batch, $RANKS ranks, repo $REPO"
echo "=== $(date -Is)"

# 1. Preflight. Fatal failures stop the run before anything bills.
echo -e "\n=== 1/5 preflight"
"$PY" "$S/cloud_preflight.py" --ranks "$RANKS" --smoke \
  || { echo "PREFLIGHT FAILED -- not starting. See $Q/reports/s8_cloud_preflight.json"; exit 1; }

# 2. gci_F on the ten authorized geometries.
#    --no-nk because Newton-Krylov FAILED at 1.11M cells with this project's
#    lean preconditioner; ANK alone is what is proven at these counts.
echo -e "\n=== 1b/5 scaling probe: time to answer at three rank counts"
# AUDIT C8: the batch estimate assumed 75 % efficiency on 24 ranks, and the desktop
# says otherwise. Measured here before the hours bill; a failure is not fatal.
"$PY" "$S/run_campaign.py" probe --probe-ranks $((RANKS / 4)) $((RANKS / 2)) "$RANKS" \
  --no-nk || echo "probe failed -- the batch runs, but its duration is unmeasured"

echo -e "\n=== 2/5 gci_F, ten geometries"
"$PY" "$S/run_campaign.py" pilot --level gci_F --ranks "$RANKS" \
  --watch-memory --no-nk

# 3. gci_FF on the reference geometry only. Without this the batch contains no
#    grid-convergence study: ten geometries at one fine level is not a family.
echo -e "\n=== 3/5 gci_FF, reference geometry"
"$PY" "$S/run_campaign.py" pilot --level gci_FF --indices 83 --ranks "$RANKS" \
  --watch-memory --no-nk

# 4. Archive everything trusted, with provenance, before the host goes away.
echo -e "\n=== 4/5 collect"
"$PY" "$S/collect_dataset.py" --out "$Q/dataset"

# 5. The grid-convergence study index 83 can finally support: four levels.
echo -e "\n=== 4b/5 audit the archive"
# Every check this campaign learned to make, on every archived row. A batch that
# produces rows nobody has judged is not a finished batch.
"$PY" "$S/audit_runs.py" || echo "ARCHIVE AUDIT FOUND PROBLEMS -- see reports/s8_archive_audit.json"

echo -e "\n=== 5/5 grid convergence on the reference"
C='{"gci_C":567256,"gci_M":1111152,"gci_F":2217680,"gci_FF":4504420}'
"$PY" "$S/convergence_gate.py" \
  --runs "$REPO/AERIS_MESH_STUDY/artifacts/s8_pilot/g83/*_a*" \
  --out "$Q/reports/s8_hf_gate.json"
for A in -2 0 4 8; do
  "$PY" "$S/gci.py" \
    --runs "$REPO/AERIS_MESH_STUDY/artifacts/s8_pilot/g83/*_a${A}" \
    --cells "$C" --gate "$Q/reports/s8_hf_gate.json" \
    --out "$Q/reports/s8_hf_gci_a${A}.json" || true
done
"$PY" "$S/stability_convergence.py" \
  --runs "$REPO/AERIS_MESH_STUDY/artifacts/s8_pilot/g83/*_a*" \
  --gate "$Q/reports/s8_hf_gate.json" \
  --out "$Q/reports/s8_hf_stability.json" || true

echo -e "\n=== done $(date -Is)"
echo "Keep: $Q/dataset and $Q/reports. artifacts/ is gitignored and gets wiped."
