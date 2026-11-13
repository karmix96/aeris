#!/bin/bash
# 13 Nov desktop plan (solve/DESKTOP_13NOV.md), ADflow block in the order of worth: G1, M1, M2. One run at a time,
# each with solve/rss_watch.py; no time limit (timeLimit = the case file's 86400 s); ended by L2Convergence 1e-6.
cd /home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh
T=data/v7/desktop_13nov/tools; Q=runs/d13_queue_log.txt
LD="--lift-distribution 150 --slices 0.5,0.8,0.9,0.95,0.98"
run() { [ -f runs/STOP_D13 ] && { echo "$(date '+%F %T') STOP_D13: skipping $1" >> $Q; return; }; echo "$(date '+%F %T') start $1" >> $Q; $T/run_adflow_d13.sh "$@" >> $Q 2>&1; echo "$(date '+%F %T') end $1" >> $Q; }
run G1 runs/d13_G1 86400 runs/d13_G1/adflow adflow --set-option vis4=0.0078 $LD
run M1 runs/d13_M1 86400 runs/d13_M1/adflow adflow $LD
run M2 runs/d13_M2 86400 runs/d13_M2/adflow adflow $LD
echo "$(date '+%F %T') d13 ADflow queue done" >> $Q
