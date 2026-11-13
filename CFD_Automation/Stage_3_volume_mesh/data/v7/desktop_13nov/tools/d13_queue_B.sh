#!/bin/bash
# 13 Nov desktop plan, the rest, as Claude set it on Mike's word ("I leave it up to you all 3 decisions"):
#  1. the plan's quick ADflow block first (M5, W1-W3, Q1-Q3), then the SU2 SA+LM continuation R2c (it decides the
#     transition model), S1, S2, R4c, M3, M4, M2b, F1, F2, G2, R6c, E3;
#  2. ADflow L2Convergence 1e-7 where runs are compared below a count (M3, M4, M5, M2b, F1, F2); 1e-6 elsewhere;
#  3. the SU2 continuations judged on the joined record, stall window 4,000 iterations.
# One run at a time, each with solve/rss_watch.py; no time limit. Waits for the E queue (E2) to end.
cd /home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh
A=data/v7/desktop_13nov/tools/run_adflow_d13.sh; S=data/v7/su2_transition/tools/run_su2.sh; Q=runs/d13_queue_log.txt
R=/home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh/runs/su2t_VVC_a4
LD="--lift-distribution 150 --slices 0.5,0.8,0.9,0.95,0.98"; T7="--set-option L2Convergence=1e-7"
while pgrep -f "runs/d13_queue_E.sh" > /dev/null || pgrep -x SU2_CFD > /dev/null || pgrep -f "solve/run_adflow.py" > /dev/null; do sleep 30; done
echo "$(date '+%F %T') queue B begins" >> $Q
go() { [ -f runs/STOP_D13 ] && { echo "$(date '+%F %T') STOP_D13: skipping $1" >> $Q; return 1; }; echo "$(date '+%F %T') start $1" >> $Q; return 0; }
ad() { go "$1" || return; $A "$1" runs/d13_$1 86400 runs/d13_$1/adflow adflow "${@:2}" >> $Q 2>&1; echo "$(date '+%F %T') end $1" >> $Q; }
su() { go "$1" || return; $S "$1" "$2" "$3" "$4" >> $Q 2>&1; echo "$(date '+%F %T') end $1" >> $Q; }
cont() { go "$1" || return; mkdir -p $R/$3 && cp -p $R/$2/restart.dat $R/$3/$4_restart.dat
  MONITOR_ARGS="--prev-history $R/$2/history.csv --stall-window 4000" $S "$1" runs/su2t_VVC_a4 "$5" "$3" >> $Q 2>&1; echo "$(date '+%F %T') end $1" >> $Q; }
ad M5 $T7 $LD
ad W1 $LD
ad W2 $LD
ad W3 $LD
ad Q1 $LD
ad Q2 $LD
ad Q3 $LD
cont R2c R2_sa_lm R2c_sa_lm_cont r2 r2c_cont.cfg
su S1 runs/d13_S1 su2_sa.cfg su2_sa
su S2 runs/d13_S2 su2_sa.cfg su2_sa
cont R4c R4_sst_lm R4c_sst_lm_cont r4 r4c_cont.cfg
ad M3 $T7 $LD
ad M4 $T7 $LD
ad M2b $T7 $LD
ad F1 $T7 $LD
ad F2 $T7 $LD
ad G2 --set-option "discretization=central plus matrix dissipation" $LD
cont R6c R6_sa_lm_lightvc R6c_sa_lm_lightvc_cont r6 r6c_cont.cfg
su E3 runs/d13_E e3_sst_lm.cfg E3_sst_lm
echo "$(date '+%F %T') d13 queue B done" >> $Q
