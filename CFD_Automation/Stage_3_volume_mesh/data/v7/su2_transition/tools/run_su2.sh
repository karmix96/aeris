#!/bin/bash
# One SU2 run of the 12 Nov 2026 SU2 study, with NO time limit: the memory watchdog (solve/rss_watch.py, as every
# solve here), the host logger, the convergence monitor (monitor.py: stops the run only when read_results.py's
# acceptance rule holds) and timing.json.
#   [MONITOR_ARGS="--res-ref -4.73"] run_su2.sh <run id> <case dir, relative to Stage_3_volume_mesh> <cfg file in the case dir> <run folder name>
# SU2 8.5.0 here is a static MPICH build: launch it with MPICH's hydra (under Open MPI it runs as 1-rank copies).
set -u
STAGE=/home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh
PY=/home/mike_kara/aeris/.venv/bin/python
SU2=/home/mike_kara/aeris/AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD
MPI_SU2=/home/mike_kara/miniconda3/pkgs/mpich-5.0.1-hfbb40bb_4/bin/mpiexec.hydra
T=$STAGE/data/v7/su2_transition/tools
RID=$1; C=$2; CFG=$3; RUN=$4
cd "$STAGE/$C" && mkdir -p "$RUN" && cd "$RUN" || exit 2
cp -p "../$CFG" ./case.cfg
$PY "$STAGE/solve/rss_watch.py" --match SU2_CFD --out rss.csv > rss_log.txt 2>&1 &
W1=$!
HOST_WATCH_MATCH=SU2_CFD $PY "$STAGE/data/v7/night_11nov/tools/host_watch.py" --out host.csv > host_log.txt 2>&1 &
W2=$!
$PY "$T/monitor.py" --folder "$(pwd)" ${MONITOR_ARGS:-} > monitor_stdout.txt 2>&1 &
W3=$!
CMD="$MPI_SU2 -np 6 $SU2 case.cfg"
echo "[$RID] solve $(date '+%F %T'): $CMD (in $(pwd))"
T0=$(date +%s); U0=$(cut -d' ' -f1 /proc/uptime)
$MPI_SU2 -np 6 $SU2 case.cfg > log.txt 2>&1
RC=$?
T1=$(date +%s); U1=$(cut -d' ' -f1 /proc/uptime)
for i in $(seq 150); do kill -0 $W1 2>/dev/null || kill -0 $W2 2>/dev/null || kill -0 $W3 2>/dev/null || break; sleep 1; done
kill -TERM $W1 $W2 $W3 2>/dev/null; wait $W1 $W2 $W3 2>/dev/null
cat > timing.json <<J
{"run": "$RID", "command": "$CMD", "cwd": "$(pwd)", "start": "$(date -d @$T0 '+%F %T')", "end": "$(date -d @$T1 '+%F %T')",
 "wall_seconds_monotonic": $(echo "$U1 - $U0" | bc), "exit": $RC, "ranks": 6, "time_limit": "none"}
J
echo "[$RID] done $(date '+%F %T') exit=$RC wall=$(echo "$U1 - $U0" | bc) s"
