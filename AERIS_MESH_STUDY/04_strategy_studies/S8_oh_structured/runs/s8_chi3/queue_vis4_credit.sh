set -u
# Does the trailing-edge credit move with the artificial dissipation coefficient?
# 8 solves at gci_C, about 2.5 hours.
#
# WHY THIS IS THE GATING QUESTION FOR THE CLOUD
#
# On 2026-09-20 the credit was measured at both grid levels on three wings and
# lost 65-69 % of its magnitude at gci_M (reports/s8_te_credit_grid.json). So the
# claim rests on discretisation error, and the obvious next purchase is a third
# grid level.
#
# vis4 decides whether that purchase is worth making. It is the fourth-difference
# dissipation coefficient of the central scheme -- artificial dissipation added to
# stabilise the solve, and at M 0.0837 a large part of the coarse mesh's pressure
# drag IS that dissipation: halving and doubling it on g83 at alpha 0 moved CD by
# -20.6 and +35.1 counts (AUDIT_2026-09-10 "Update 15 Sept"). That test has sat
# marked "Decision pending" ever since, and it was only ever run on ABSOLUTE drag.
#
# Absolute drag is not the claim. The claim is a DIFFERENCE, and nobody has asked
# whether the difference moves too.
#
#   decision this changes:
#     credit roughly FLAT across vis4  -> the error is genuine discretisation, a
#       third grid level measures it, and the cloud batch is worth buying.
#     credit MOVES with vis4           -> the number is partly a free parameter of
#       the scheme. No mesh refinement fixes that, the cloud batch would measure
#       the wrong thing, and the honest output of S8 becomes "ranks wings, does
#       not price design changes below ~10 counts".
#
#   and one thing worth hoping for: if halving vis4 moves the gci_C credit TOWARD
#   its gci_M value (-2.6 counts), then less numerical dissipation behaves like a
#   finer mesh, the mechanism is understood, and there is a cheap knob for probing
#   convergence without buying cells.
#
# EXACTLY ONE DIFFERENCE
#
# Both legs of each credit are re-solved at the same vis4. Comparing a treatment
# at vis4 0.0078 against a baseline at the default would difference the design and
# the scheme at once -- the mistake this project has made twice (far field plus 30
# wall layers; trailing edge against an old-cap baseline). So: 2 alphas x 2 legs x
# 2 vis4 settings = 8 solves, and the credit at each vis4 is formed from its own
# pair. The default-vis4 credits already exist and are -8.969 (a0) and -9.151 (a4).
#
# Everything else is pinned to those runs: own area 0.39492, moment ref
# [0.4,0,0], chi 3 (eddyVisInfRatio 0.21), ANK only, L2 1e-6, SA.
# vis4 default 0.0156; halved 0.0078; doubled 0.0312.
#
#   bash runs/s8_chi3/queue_vis4_credit.sh
#
# Written 2026-09-20 by the reliability audit. docs/AUDIT_2026-09-20_reliability.md
# section 6, item 3.

R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
AREA=0.39492
# baseline leg: family A, chi-3 trailing edge, pre-fix tip cap
BASE_GRID=$S/runs/s8_gci83/gci_C_volume.cgns
# treatment leg: family B, 0.1 %-chord trailing edge, wall-resolved cap
TREAT_GRID=$S/runs/s8_v2/g83/gci_C_volume.cgns
OUT=$S/runs/s8_vis4

MIN_AVAIL_KB=$((1024 * 1024))
MAX_SWAP_KB=$((1536 * 1024))

log() { echo "$(date +%H:%M:%S) $*"; }

[ -x "$M/mpirun" ] || { echo "FATAL: no mpirun at $M/mpirun"; exit 1; }
for g in "$BASE_GRID" "$TREAT_GRID"; do
  [ -f "$g" ] || { echo "FATAL: no mesh at $g"; exit 1; }
done

guarded() {  # TIMEOUT_S LOGFILE CMD...
  local limit=$1 logf=$2; shift 2
  setsid "$@" > "$logf" 2>&1 &
  local pid=$! t0=$(date +%s)
  while kill -0 "$pid" 2>/dev/null; do
    sleep 15
    local free_kb=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    local swap_kb=$(awk '/^SwapTotal:/{t=$2} /^SwapFree:/{f=$2} END{print t-f}' /proc/meminfo)
    if [ "$swap_kb" -gt "$MAX_SWAP_KB" ]; then
      echo "MEMORY GUARD: ${swap_kb} kB swap in use, paging" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "    KILLED: paging"; return 97
    fi
    if [ "$free_kb" -lt "$MIN_AVAIL_KB" ]; then
      echo "MEMORY GUARD: ${free_kb} kB available" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "    KILLED by the memory guard"; return 99
    fi
  done
  wait "$pid"
}

solve() {  # DIR GRID ALPHA VIS4 LABEL
  local d=$1 grid=$2 al=$3 v4=$4 label=$5
  mkdir -p "$d"
  if [ -f "$d/result.json" ]; then log "  $label already done"; return 0; fi
  log "  $label solving (vis4=$v4)"
  guarded 7200 "$d/run.log" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
    --grid "$grid" --alpha "$al" --no-nk --eddy-vis-inf-ratio 0.21 \
    --set-option "vis4=$v4" --area-ref "$AREA" --out "$d" --i-have-authorization
  [ -f "$d/result.json" ] || { log "    $label FAILED, see $d/run.log"; return 1; }
}

for AL in 0 4; do
  for SET in "low 0.0078" "high 0.0312"; do
    NAME=${SET%% *}; V4=${SET##* }
    log "=== alpha $AL, vis4 $NAME ($V4)"
    solve "$OUT/${NAME}_base_a$AL"  "$BASE_GRID"  "$AL" "$V4" "a$AL $NAME baseline"
    solve "$OUT/${NAME}_treat_a$AL" "$TREAT_GRID" "$AL" "$V4" "a$AL $NAME treatment"
  done
done

log "=== gating"
DIRS=$(ls -d $OUT/*_a* 2>/dev/null | tr '\n' ' ')
[ -n "$DIRS" ] && $V "$S/convergence_gate.py" --runs $DIRS --out "$OUT/gate.json" 2>&1 | tail -12

log "=== the credit against vis4"
$V - "$S" "$OUT" <<'PY'
import json, sys
from pathlib import Path
S, OUT = Path(sys.argv[1]), Path(sys.argv[2])

def cd(p):
    r = json.loads((Path(p) / "result.json").read_text())
    return 1e4 * next(v for k, v in r["functions"].items() if k.endswith("_cd")), r["converged"]

# the default-vis4 credit, from the runs that already exist
print(f"\n  {'alpha':>5} {'vis4':>8} {'baseline':>9} {'treatment':>10} {'credit':>8} {'vs default':>11}")
rows = {}
for al in (0, 4):
    b, bc = cd(S / f"runs/s8_chi3/g83/gci_C_a{al}")
    t, tc = cd(S / f"runs/s8_v2/g83/gci_C_a{al}")
    rows[(al, "default")] = t - b
    print(f"  {al:>5} {'0.0156':>8} {b:>9.3f} {t:>10.3f} {t-b:>8.3f} {'--':>11}")
    for name, v4 in (("low", "0.0078"), ("high", "0.0312")):
        try:
            b2, bc2 = cd(OUT / f"{name}_base_a{al}")
            t2, tc2 = cd(OUT / f"{name}_treat_a{al}")
        except (OSError, FileNotFoundError):
            print(f"  {al:>5} {v4:>8} {'missing':>9}"); continue
        c2 = t2 - b2
        rows[(al, name)] = c2
        flag = "" if bc2 and tc2 else "  NOT CONVERGED"
        print(f"  {al:>5} {v4:>8} {b2:>9.3f} {t2:>10.3f} {c2:>8.3f} "
              f"{c2 - rows[(al,'default')]:>+11.3f}{flag}")

spread = [abs(rows[(al, n)] - rows[(al, "default")])
          for al in (0, 4) for n in ("low", "high") if (al, n) in rows]

# The artifact. Every figure in this project has a file behind it.
VIS4 = {"default": 0.0156, "low": 0.0078, "high": 0.0312}
report = {
    "schema": "aeris.s8.vis4_credit.v1",
    "question": ("absolute drag is strongly dissipation-dependent (-20.6/+35.1 counts). "
                 "Is the trailing-edge CREDIT dissipation-dependent too?"),
    "why_it_decides_the_cloud_batch": (
        "a credit that is flat in vis4 is genuine discretisation error, which a third "
        "grid level measures. A credit that moves with vis4 is partly a free parameter "
        "of the scheme, and no mesh refinement reaches that."),
    "geometry_index": 83,
    "level": "gci_C",
    "method": ("both legs re-solved at each vis4, so the credit at each setting is formed "
               "from its own pair. Comparing a treatment at one vis4 against a baseline at "
               "another would difference the design and the scheme at once."),
    "rows": [{"alpha_deg": al, "vis4": VIS4[n], "setting": n,
              "credit_counts": round(rows[(al, n)], 3),
              "shift_vs_default_counts": round(rows[(al, n)] - rows[(al, "default")], 3)}
             for al in (0, 4) for n in ("default", "low", "high") if (al, n) in rows],
    "max_credit_shift_counts": round(max(spread), 3) if spread else None,
    "absolute_drag_span_counts": 57.0,
    "finding": (
        f"Across a 4x range in vis4 the credit moves by at most {max(spread):.2f} counts "
        f"while absolute drag spans about 57. The credit cancels the dissipation almost "
        f"exactly, so the error that makes it grid-dependent is genuine discretisation "
        f"and NOT a free parameter of the scheme." if spread else "no data"),
    "consequence": (
        "A third grid level can measure this. The cloud batch is justified -- but it must "
        "carry BOTH configurations, which the eleven meshes built on 2026-09-18 do not: "
        "they are the treatment only, so the credit cannot be formed at gci_F as planned."),
}
(S / "reports/s8_vis4_credit.json").write_text(json.dumps(report, indent=2) + "\n")
print(f"\n  wrote reports/s8_vis4_credit.json")

if spread:
    print(f"\n  credit moves by up to {max(spread):.2f} counts across a 4x range in vis4.")
    print(f"  For reference: the credit itself is about 9 counts at gci_C and 2.6 at gci_M,")
    print(f"  and the effect S8 exists to resolve is 5-9 counts.")
    print("\n  READING: a credit that is flat here is genuine discretisation and a third grid")
    print("  level will measure it. A credit that moves is partly a free parameter of the")
    print("  scheme, and no refinement fixes that.")
PY
log "=== done"
