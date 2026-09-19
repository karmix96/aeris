set -u
# Pre-cloud checklist, resumed. queue.sh finished steps 1-2 (gci_FF build, ONERA M6)
# and was stopped at step 3 because a concurrent test had contaminated the
# multigrid timing. One solve at a time (PLAN 0.2); timing steps see an idle host.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N=$A/tmr_naca0012
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
G83=$A/s8_gci83/gci_C_volume.cgns
# From the o256 configuration test: ANK alone stalled at line-search step 0.01 on
# this case (campaign settings, stronger ANK, and chi 3 all did), while ANK -> NK
# with stronger preconditioners converged in 56 iterations. These change the path
# to the converged solution, never the equations, so the verification still
# speaks for the campaign's discretization. o2048 is left out: NK at these
# settings on 1.05M cells would not fit in 12.8 GiB.
NACA_FLAGS="--l2 1e-8 --set ANKSubspaceSize=50 --set ANKPCILUFill=2 --set ANKCoupledSwitchTol=1e-4 --set NKSwitchTol=1e-4 --set NKSubspaceSize=60 --set NKPCILUFill=2"

area() { $V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['$1']['half_area_m2'])"; }
forces() {
  $V - "$1" "$2" <<'PY' 2>/dev/null || echo "  $2 FAILED"
import json, sys
r = json.load(open(sys.argv[1] + "/result.json"))
f = r.get("coefficients") or {k.split("_")[-1]: v for k, v in r["functions"].items()}
g = lambda k: f.get(k, f.get(k.upper(), float("nan")))
res = r.get("relative_residual")
print(f"  {sys.argv[2]} CL={g('cl'):+.6f} CD={g('cd'):.6f} CDp={g('cdp'):.6f} "
      f"CDv={g('cdv'):.6f} converged={r.get('converged')} "
      f"res={res if res is None else f'{res:.2e}'}")
PY
}
iters() { awk '/^ +1 +[0-9]+ +[0-9]+ /{i=$2} END{print i+0}' "$1"; }
timed() {  # NAME DIR NP SCRIPT ARGS...; run.log inside the run directory, where the gate looks
  local name=$1 dir=$2 np=$3 script=$4; shift 4; mkdir -p "$dir"
  local t0=$(date +%s)
  "$M/mpirun" -np "$np" "$M/python" "$script" "$@" --out "$dir" > "$dir/run.log" 2>&1
  echo "  $name np=$np wall=$(( $(date +%s) - t0 )) s outer_iters=$(iters "$dir/run.log")"
  forces "$dir" "$name"
}
solve() { timed "$1" "$2" "$3" "$S/solve_s8.py" "${@:4}" --i-have-authorization; }
naca() { timed "$1" "$N/runs/$1" 6 "$S/naca0012_tmr.py" solve "${@:2}" $NACA_FLAGS; }
A83=$(area 83)

echo "=== 3/8 multigrid vs ANK-only, geometry 83 gci_C alpha 0 $(date -Is)"
solve mg_base "$O/mg/base" 6 --grid "$G83" --alpha 0 --no-nk --area-ref "$A83"
solve mg_2w   "$O/mg/mg2w" 6 --grid "$G83" --alpha 0 --no-nk --area-ref "$A83" \
  --mg-cycle 2w --smoother DADI --ank-switch-tol 1e-2 --time-limit 3600
solve mg_3w   "$O/mg/mg3w" 6 --grid "$G83" --alpha 0 --no-nk --area-ref "$A83" \
  --mg-cycle 3w --smoother DADI --ank-switch-tol 1e-2 --time-limit 3600

echo "=== 4/8 NACA 0012 low-speed verification (TMR), M 0.15 Re 6e6 alpha 10 $(date -Is)"
$M/python "$S/naca0012_tmr.py" grid --levels o512 o1024 > "$N/grid.log" 2>&1 \
  || echo "  grid FAILED, see $N/grid.log"
grep -E "cells, s0" "$N/grid.log"
for L in o256 o512 o1024; do naca "${L}_m0.15" --grid "$N/$L.cgns"; done
naca o1024_m0.15_chi3 --grid "$N/o1024.cgns" --eddy-vis-inf-ratio 0.21
naca o1024_m0.0837 --grid "$N/o1024.cgns" --mach 0.0837
$V "$S/naca0012_tmr.py" compare

echo "=== 5/8 S8 freestream turbulence chi 3, geometry 83 gci_C $(date -Is)"
for AL in 0 4; do
  solve "chi3 a$AL" "$O/chi3/a$AL" 6 --grid "$G83" --alpha $AL --no-nk --area-ref "$A83" \
    --eddy-vis-inf-ratio 0.21
done

echo "=== 6/8 gci_M on the smallest (47) and largest (13) wing $(date -Is)"
$V $S/run_campaign.py pilot --level gci_M --indices 47 13 --ranks 6 --watch-memory \
  --no-nk > "$O/gciM_pilot.log" 2>&1
grep -E "abort|FAIL|refus" "$O/gciM_pilot.log" | tail -5
for I in 47 13; do for AL in -2 0 4 8; do
  forces "$A/s8_pilot/g$I/gci_M_a$AL" "g$I gci_M a$AL"; done; done

echo "=== 7/8 chordwise refinement on the smallest and largest wing $(date -Is)"
L=gci_C_chord
for I in 47 13; do
  D=$O/dir_g$I
  $V $S/build_volume.py --level $L --index $I --out "$D" --no-plot3d 2>&1 \
    | grep -oE '"(total_cells|negative_cells_all_blocks)": [0-9]*' | tr '\n' ' '; echo
  $M/python $S/write_cgns.py --blocks "$D/${L}_blocks.npz" > /dev/null 2>&1
  for AL in 0 4; do
    solve "g$I $L a$AL" "$D/${L}_a$AL" 6 --grid "$D/${L}_volume.cgns" --alpha $AL \
      --no-nk --area-ref "$(area $I)"
  done
done

echo "=== 8/8 turbulence model and time-to-residual, geometry 83 gci_C $(date -Is)"
for AL in 0 4; do
  solve "sst a$AL" "$O/sst/a$AL" 6 --grid "$G83" --alpha $AL --no-nk --area-ref "$A83" \
    --turbulence-model "Menter SST" --time-limit 5400
done
# time to the 1e-6 target, not a fixed cycle budget; np 6 is mg_base above
for NP in 1 2 4; do
  solve "ttr np$NP" "$O/ttr/np$NP" $NP --grid "$G83" --alpha 0 --no-nk --area-ref "$A83"
done

echo "=== done $(date -Is)"
