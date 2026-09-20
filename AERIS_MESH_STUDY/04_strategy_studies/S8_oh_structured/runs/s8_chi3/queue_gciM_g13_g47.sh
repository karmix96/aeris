set -u
# The chi-3 baseline at gci_M for g13 and g47: the 8 solves that decide whether
# S8's central claim survives grid refinement.
#
# WHY THESE EIGHT AND NOTHING ELSE
#
# The trailing-edge credit is quoted across ten wings at gci_C (-5.27 to -8.98
# counts, S8_REPORT 17 Sept addendum). On 20 September it was measured at gci_M
# for the one wing that could be -- g83, which already had both legs at both
# levels -- and it lost 67-74 % of its magnitude: -8.11...-9.15 counts at gci_C
# against -2.05...-3.03 at gci_M. The campaign had assumed discretisation error
# cancels in a same-grid difference. It does not.
#
# One wing is an observation. The decision that hangs on it -- whether to spend
# money on gci_F, and what to ask it -- needs to know if the loss is a property
# of the CHANGE or a property of g83. g13 and g47 are the only other wings with
# the treatment already solved at gci_M, so they are the only ones where the
# credit can be completed without also paying for the treatment leg.
#
#   decision this changes: if all three wings lose two-thirds of the credit, the
#   published range is withdrawn as a converged-grid number and the cloud batch
#   is re-scoped to measure the credit's grid dependence rather than absolute
#   drag. If g83 is an outlier, the range stands with a per-wing caveat.
#
# EXACTLY ONE DIFFERENCE (the rule that catches the usual defect)
#
# The credit is v2 minus this baseline. Against the v2 gci_M runs these differ in
# the MESH only -- family A (chi-3 trailing edge, pre-fix tip cap at ~10.2 x s0)
# against family B (0.1 %-chord trailing edge, wall-resolved cap at ~2.06 x s0).
# That bundling is deliberate and is what the published credit already means: a
# NET number, trailing edge plus the cap's cost.
#
# Everything else is pinned to the v2 runs and verified below before solving:
#   area_ref      each wing's OWN half area (defect 23), 0.5162 / 0.29775 m2
#   moment ref    [0.4, 0, 0]
#   freestream    eddyVisInfRatio 0.21, i.e. chi 3, the TMR prescription
#   solver        ANK only (--no-nk), L2Convergence 1e-6, SA
#
# The trap this avoids: runs/s8_pilot/g{13,47}/gci_M_* already exist on the same
# family-A meshes and look like the baseline. They are NOT -- they run ADflow's
# default freestream turbulence, not chi 3. Using them would difference the mesh
# AND the freestream at once, and chi default -> 3 is worth +0.8 to +2.1 counts
# (reports/s8_freestream_turbulence.json). That is 30 % of the answer.
#
# HOW IT RUNS
#
# Sequential, one solve at a time on an idle machine (PLAN 0.2). Resumable: any
# run whose result.json exists is skipped, so a restart costs nothing done.
# Memory-guarded -- g13's gci_M is 1,121,436 cells, predicted 12.12 GiB against
# 12.76 available, so this is the marginal level the memory law was fitted for
# and WSL has taken the VM down mid-solve before (queue17, 13 Sept 23:23).
#
# g83 is included as a CONTROL. Its solves already exist so it costs nothing, and
# the credit this script computes for it must reproduce -8.110 / -8.969 / -9.151 /
# -7.513 at gci_C and -2.081 / -2.757 / -3.034 / -2.046 at gci_M. If it does not,
# the arithmetic is wrong and the new wings mean nothing.
#
#   bash runs/s8_chi3/queue_gciM_g13_g47.sh
#
# Written 2026-09-20 by the reliability audit. See
# docs/AUDIT_2026-09-20_reliability.md section 6, item 2.

R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
ALPHAS="-2 0 4 8"

log() { echo "$(date +%H:%M:%S) $*"; }

# $PATH resolves mpirun to a DIFFERENT OpenMPI than mach-aero was built against.
# Launching mpi4py on the wrong runtime does not error: the ranks fail to form a
# communicator, all six believe they are rank 0 of 1, and they write over each
# other while reporting success. Use the env's own launcher, always.
[ -x "$M/mpirun" ] || { echo "FATAL: no mpirun at $M/mpirun"; exit 1; }
[ -x "$M/python" ] || { echo "FATAL: no python at $M/python"; exit 1; }

# Guard thresholds, set from the measured peaks rather than from caution.
#
# The twelve v2 gci_M runs peaked at 11.30-11.43 GiB resident with swap never
# above 0.06 GiB, and none aborted (runs/s8_v2/g*/gci_M_a*/memory_watch.json).
# On a 13.65 GiB VM that bottoms out near 1.7 GiB available -- so queue17's
# 1.5 GiB threshold sits almost exactly on a HEALTHY run's floor and would have
# killed one. These baseline meshes are ~60k cells smaller than those, so the
# expected floor is ~2.3 GiB, but the guard is set at 1.0 GiB to leave room for a
# false positive to be wrong quietly rather than expensively.
#
# Sustained paging is the real failure mode, and available memory does not show
# it: WSL took the VM down mid-solve on 13 Sept at 23:23 with memory that looked
# adequate. Swap in use is the signal, and 0.06 GiB is the measured normal.
MIN_AVAIL_KB=$((1024 * 1024))
MAX_SWAP_KB=$((1536 * 1024))

guarded() {  # TIMEOUT_S LOGFILE CMD...
  local limit=$1 logf=$2; shift 2
  setsid "$@" > "$logf" 2>&1 &
  local pid=$! t0=$(date +%s)
  while kill -0 "$pid" 2>/dev/null; do
    sleep 15
    local free_kb=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    local swap_kb=$(awk '/^SwapTotal:/{t=$2} /^SwapFree:/{f=$2} END{print t-f}' /proc/meminfo)
    if [ "$swap_kb" -gt "$MAX_SWAP_KB" ]; then
      echo "MEMORY GUARD: ${swap_kb} kB of swap in use, this run is paging" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "    KILLED: paging (swap ${swap_kb} kB). An answer from disk is not an answer."
      return 97
    fi
    if [ "$free_kb" -lt "$MIN_AVAIL_KB" ]; then
      echo "MEMORY GUARD: ${free_kb} kB available, killing before WSL does" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "    KILLED by the memory guard"; return 99
    fi
    if [ $(( $(date +%s) - t0 )) -gt "$limit" ]; then
      echo "TIME LIMIT ${limit}s, killing" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "    KILLED at the time limit"; return 98
    fi
  done
  wait "$pid"
}

# Refuse to solve unless this run differs from its v2 counterpart in the mesh
# ALONE. Checked against the artifact, not against my memory of it.
verify_pairing() {  # INDEX
  $V - "$1" "$S" <<'PY'
import json, sys
from pathlib import Path
idx, S = sys.argv[1], Path(sys.argv[2])
area = json.load(open(S / "reference_areas.json"))["areas"][idx]["half_area_m2"]
v2 = json.load(open(S / f"runs/s8_v2/g{idx}/gci_M_a0/result.json"))
base = json.load(open(S / f"runs/s8_pilot/g{idx}/gci_M_summary.json"))
problems = []
if abs(v2["area_ref_m2"] - area) > 1e-9:
    problems.append(f"v2 area_ref {v2['area_ref_m2']} != own area {area}")
if v2["moment_ref_xyz_m"] != [0.4, 0.0, 0.0]:
    problems.append(f"v2 moment ref {v2['moment_ref_xyz_m']}")
ov = v2.get("solver_overrides") or {}
if ov.get("eddyVisInfRatio") != 0.21 or ov.get("useNKSolver") is not False:
    problems.append(f"v2 overrides {ov} are not (chi 3, ANK only)")
if base["outboard"]["first_cell_in_s0"] < 5:
    problems.append("runs/s8_pilot mesh is not the pre-fix cap: wrong baseline family")
if problems:
    print("PAIRING REFUSED: " + "; ".join(problems)); raise SystemExit(1)
print(f"    pairing ok: own area {area} m2, chi 3, ANK only, "
      f"baseline cap {base['outboard']['first_cell_in_s0']:.2f} x s0, "
      f"{base['cells']} cells")
PY
}

for IDX in 13 47; do
  log "=== geometry $IDX: chi-3 baseline at gci_M, 4 angles"
  GRID=$S/runs/s8_pilot/g$IDX/gci_M_volume.cgns
  [ -f "$GRID" ] || { log "  FATAL: no mesh at $GRID"; exit 1; }
  AREA=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['$IDX']['half_area_m2'])")
  verify_pairing "$IDX" || { log "  refusing geometry $IDX"; exit 1; }

  for AL in $ALPHAS; do
    D=$S/runs/s8_chi3/g$IDX/gci_M_a$AL
    mkdir -p "$D"
    if [ -f "$D/result.json" ]; then log "  a$AL already done"; continue; fi
    log "  a$AL solving (6 ranks, ANK only, chi 3, area $AREA)"
    guarded 10800 "$D/run.log" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
      --grid "$GRID" --alpha "$AL" --no-nk --eddy-vis-inf-ratio 0.21 \
      --area-ref "$AREA" --out "$D" --i-have-authorization
    if [ -f "$D/result.json" ]; then
      $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CD {1e4*f['cd']:.3f} ct  CDp {1e4*f['cdp']:.3f}  CDv {1e4*f['cdv']:.3f}  CL {f['cl']:+.5f}  converged={r['converged']} res={r['relative_residual']:.2e}\")"
    else
      log "    a$AL produced no result.json -- see $D/run.log"
    fi
  done
done

log "=== gating the new runs"
for IDX in 13 47; do
  DIRS=$(ls -d $S/runs/s8_chi3/g$IDX/gci_M_a* 2>/dev/null | tr '\n' ' ')
  [ -n "$DIRS" ] && $V "$S/convergence_gate.py" --runs $DIRS \
      --out "$S/runs/s8_chi3/g$IDX/gci_M_gate.json" 2>&1 | tail -6
done

log "=== the credit, all three wings, both levels"
$V "$S/te_credit_grid.py" --indices 13 47 83 2>&1 | tail -40
log "=== done"
