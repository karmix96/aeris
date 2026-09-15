set -u
# THE RE-RUN, approved 2026-09-15 with the wall-resolved tip cap -- sequenced behind a
# converged SU2 check. Runs after queue18.
#
# Why SU2 comes first. On the same coarse mesh and freestream, stopped by its 4 h limit
# with drag still falling, SU2 had about 25 % MORE friction drag than ADflow (112 against
# 92 counts at alpha 0, 122 against 96 at alpha 4) and far less pressure drag (67 against
# 119). The pressure-drag gap is what a coarse mesh does to one code and not the other --
# ADflow's own chordwise extrapolation puts its CDp near 76 -- and gates nothing here.
# The friction gap cannot be mesh: ADflow's friction drag moves 1 % from gci_C to gci_M.
# If it survives convergence it is a setup or model difference that sits under every one
# of the re-run's sixty solves. So:
#   1. SU2 continues from its restart at both angles until drag settles (Cauchy);
#   2. the re-run starts only if SU2's friction drag is within 10 % of ADflow's and its
#      lift within 3 %, at both angles, against ADflow on the same mesh and freestream
#      (s8_chi3/g83), and
#   3. only if the tip cap is the only wing test that moved drag by a count or more and
#      every wing test finished -- the scope of the approval.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
Q=$R/AERIS_MESH_STUDY/05_s6_cfd_qualification
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
SU2=$R/AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD
MIN_FREE_GIB=1.5

log() { echo "$(date +%H:%M) $*"; }

guarded() {  # TIMEOUT_S LOGFILE CMD...
  local limit=$1 logf=$2; shift 2
  setsid "$@" > "$logf" 2>&1 &
  local pid=$! t0=$(date +%s)
  while kill -0 "$pid" 2>/dev/null; do
    sleep 10
    local free_kb=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    if [ "$free_kb" -lt $((${MIN_FREE_GIB%.*} * 1024 * 1024 + 512 * 1024)) ]; then
      echo "MEMORY GUARD: ${free_kb} kB free, killing" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "  killed by the memory guard"; return 99
    fi
    if [ $(( $(date +%s) - t0 )) -gt "$limit" ]; then
      echo "TIME LIMIT ${limit}s, killing" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "  killed at the time limit"; return 98
    fi
  done
  wait "$pid"
}

until grep -q "^=== done" "$O/queue18.out" 2>/dev/null; do sleep 60; done
log "queue18 finished"

log "=== 1/3 SU2 continued from its restart until drag settles, two ranks"
for AL in 0 4; do
  d=$A/su2_check/a$AL
  if [ -f "$d/settled.ok" ]; then log "  a$AL already settled"; continue; fi
  $V - "$d" <<'PY'
import sys
from pathlib import Path
d = Path(sys.argv[1])
# a relative change in drag under 1e-6 per iteration, averaged over 500 iterations, is
# under 0.1 count per 500 iterations; the 4 h run ended at about 2.7
change = {"RESTART_SOL": "YES", "SOLUTION_FILENAME": "restart.dat",
          "RESTART_FILENAME": "restart_settled.dat", "CONV_FILENAME": "history_settled",
          "BREAKDOWN_FILENAME": "forces_breakdown_settled.dat",
          "SURFACE_FILENAME": "surface_settled", "ITER": "15000", "CONV_FIELD": "DRAG",
          "CONV_CAUCHY_ELEMS": "500", "CONV_CAUCHY_EPS": "1E-6", "CONV_STARTITER": "10",
          "OUTPUT_WRT_FREQ": "250"}
out, seen = [], set()
for line in (d / "case.cfg").read_text().splitlines():
    key = line.split("=")[0].strip()
    if key in change:
        out.append(f"{key}= {change[key]}"); seen.add(key)
    else:
        out.append(line)
out += [f"{k}= {v}" for k, v in change.items() if k not in seen]
(d / "case_settled.cfg").write_text("\n".join(out) + "\n")
PY
  ( cd "$d" && guarded 43200 run_settled.log "$M/mpirun" -np 2 "$SU2" case_settled.cfg )
  if grep -q "Exit Success" "$d/run_settled.log"; then touch "$d/settled.ok"; log "  a$AL settled"
  else log "  a$AL did NOT finish, see $d/run_settled.log"; fi
done

log "=== 2/3 cross-code gate: SU2 settled against ADflow, same mesh, same freestream"
$V - "$A" > "$O/su2_gate.txt" 2>&1 <<'PY'
import json, re, sys
from pathlib import Path
A = Path(sys.argv[1]); ok = True
number = r"([-\d.eE+]+)"
for al in (0, 4):
    d = A / f"su2_check/a{al}"
    if not (d / "settled.ok").exists():
        print(f"a{al}: SU2 did not settle"); ok = False; continue
    t = (d / "forces_breakdown_settled.dat").read_text()
    def total(key):
        m = re.search(rf"Total {key}:\s+{number} \| Pressure \(\s*-?\d+%\):\s+{number} \| "
                      rf"Friction \(\s*-?\d+%\):\s+{number}", t)
        return [float(v) for v in m.groups()]
    cl = total("CL")[0]
    cd, cdp, cdf = total("CD")
    r = json.load(open(A / f"s8_chi3/g83/gci_C_a{al}/result.json"))
    f = {k.split("_")[-1]: v for k, v in r["functions"].items()}
    friction, lift = (cdf - f["cdv"]) / f["cdv"], (cl - f["cl"]) / abs(f["cl"])
    agree = abs(friction) <= 0.10 and abs(lift) <= 0.03
    ok &= agree
    print(f"a{al}: friction SU2 {1e4*cdf:.1f} ADflow {1e4*f['cdv']:.1f} counts ({100*friction:+.1f} %); "
          f"pressure {1e4*cdp:.1f} / {1e4*f['cdp']:.1f}; total {1e4*cd:.1f} / {1e4*f['cd']:.1f}; "
          f"CL {cl:+.4f} / {f['cl']:+.4f} ({100*lift:+.1f} %)  {'agree' if agree else 'DISAGREE'}")
print("GATE", "PASS" if ok else "FAIL")
PY
cat "$O/su2_gate.txt"
if ! grep -q "^GATE PASS" "$O/su2_gate.txt"; then
  log "=== NOT STARTING THE RE-RUN: SU2 and ADflow disagree on friction or lift, or SU2 did not settle"
  echo "=== done $(date -Is)"
  exit 0
fi

others=$(grep -v "^tip cap " "$O/decision_needed.txt" 2>/dev/null || true)
unfinished=$(grep -E "(tip cap|preconditioner a|vis4|far field|trailing edge)[^:]* FAILED|build of .* FAILED" \
             "$O/queue17.out" 2>/dev/null || true)
if [ -n "$others" ] || [ -n "$unfinished" ]; then
  log "=== NOT STARTING THE RE-RUN: it was approved for the tip cap, and something else needs a decision"
  if [ -n "$others" ]; then echo "  other wing tests that moved drag by a count or more:"; echo "$others"; fi
  if [ -n "$unfinished" ]; then echo "  wing tests that did not finish:"; echo "$unfinished"; fi
  echo "=== done $(date -Is)"
  exit 0
fi

log "=== 3/3 the re-run: gci_C, ten wings, four angles"
$V "$S/run_campaign.py" pilot --level gci_C --ranks 6 --no-nk --eddy-vis-inf-ratio 0.21 \
  --out-root "$A/s8_v2" > "$O/rerun_gci_C.log" 2>&1
log "  gci_C exit $?"
log "=== the re-run: gci_M, five wings, four angles"
$V "$S/run_campaign.py" pilot --level gci_M --indices 83 29 65 47 13 --ranks 6 --watch-memory \
  --no-nk --eddy-vis-inf-ratio 0.21 --out-root "$A/s8_v2" > "$O/rerun_gci_M.log" 2>&1
log "  gci_M exit $?"
log "=== dataset v2 and its audit"
$V "$S/collect_dataset.py" --runs "$A/s8_v2" --out "$Q/dataset_v2" 2>&1 | tail -2
$V "$S/audit_runs.py" --rows "$Q/dataset_v2/rows.json" --out "$Q/reports/s8_archive_audit_v2.json" | tail -4
echo "=== done $(date -Is)"
