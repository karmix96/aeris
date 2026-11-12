#!/bin/bash
SU2=/home/mike_kara/aeris/AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD
MPI=/home/mike_kara/miniconda3/pkgs/mpich-5.0.1-hfbb40bb_4/bin/mpiexec.hydra
for t in lm bcm; do
  cd /home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh/runs/su2t_VVC_a4/test_$t
  /home/mike_kara/aeris/.venv/bin/python /home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh/solve/rss_watch.py --match SU2_CFD --out rss.csv > rss_log.txt 2>&1 &
  W=$!
  U0=$(cut -d' ' -f1 /proc/uptime)
  $MPI -np 6 $SU2 test.cfg > log.txt 2>&1; echo "test_$t exit $? seconds $(echo "$(cut -d' ' -f1 /proc/uptime) - $U0" | bc)"
  wait $W
done
