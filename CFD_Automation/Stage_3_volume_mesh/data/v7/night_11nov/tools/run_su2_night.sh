#!/bin/bash
# One SU2 run of the V7 night plan (NIGHT_11NOV.md section 4, "One SU2 run"), with the plan's watchdog, the host
# logger, the start and end times and the exit code (timing.json).
#   run_su2_night.sh <run id> <case dir> <model: sa | sst_lm> <cap minutes>
# SU2 8.5.0 here is a static MPICH build: it must be launched with MPICH's hydra. Under Open MPI's mpirun it runs as
# separate 1-rank copies (measured 11 Nov 23:50: two banners, no partitioning, exit 0).
set -u
STAGE=/home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh
PY=/home/mike_kara/aeris/.venv/bin/python
SU2=/home/mike_kara/aeris/AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD
MPI_SU2=/home/mike_kara/miniconda3/pkgs/mpich-5.0.1-hfbb40bb_4/bin/mpiexec.hydra
RID=$1; C=$2; M=$3; CAP=$4
cd "$STAGE/$C" && mkdir -p "su2_$M" && cd "su2_$M"
$PY "$STAGE/solve/rss_watch.py" --match SU2_CFD --out rss.csv > rss_log.txt 2>&1 &
W1=$!
HOST_WATCH_MATCH=SU2_CFD $PY "$STAGE/data/v7/night_11nov/tools/host_watch.py" --out host.csv > host_log.txt 2>&1 &
W2=$!
CMD="timeout ${CAP}m $MPI_SU2 -np 6 $SU2 ../su2_$M.cfg"
echo "[$RID] solve $(date '+%F %T'): $CMD"
T0=$(date +%s); U0=$(cut -d' ' -f1 /proc/uptime)
timeout ${CAP}m $MPI_SU2 -np 6 $SU2 "../su2_$M.cfg" > log.txt 2>&1
RC=$?
T1=$(date +%s); U1=$(cut -d' ' -f1 /proc/uptime)
# the watchers end 30 s (rss_watch) and up to 120 s (host_watch) after the ranks are gone; one that never saw
# a rank (a solve that died before its first sample) would wait 10 min: stop both after 150 s at most
for i in $(seq 150); do kill -0 $W1 2>/dev/null || kill -0 $W2 2>/dev/null || break; sleep 1; done
kill -TERM $W1 $W2 2>/dev/null; wait $W1 $W2 2>/dev/null
cat > timing.json <<J
{"run": "$RID", "command": "$CMD", "cwd": "$(pwd)", "start": "$(date -d @$T0 '+%F %T')", "end": "$(date -d @$T1 '+%F %T')",
 "wall_seconds": $((T1 - T0)), "wall_seconds_monotonic": $(echo "$U1 - $U0" | bc), "exit": $RC, "note": "exit 124 = stopped by timeout at the cap", "ranks": 6}
J
cd "$STAGE"
$PY solve/read_results.py --case "$C" > "$C/su2_${M}_read_results.txt" 2>&1
echo "[$RID] done $(date '+%F %T') exit=$RC wall=$((T1 - T0)) s"
