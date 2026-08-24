# S7 desktop runbook - coarse volume over the development set

Everything here is measured on the laptop, not estimated.  One `coarse` case at
index 0: **2 549 227 cells** (2 295 259 tetrahedra, 253 968 prisms), meshed in
**245 s at 1.8 GB peak RSS**, audited in **325 s at 5.3 GB peak**, writing
**263 MB**.  Roughly **9.5 minutes and 263 MB per case**, single-threaded.

For the full development set budget about **16 hours and 26 GB**.  The audit is
about 57 percent of the wall time and is single-threaded Python, so running
several cases in parallel scales almost linearly if the machine has the RAM.

## Before starting

    cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
    git switch s7-unstructured-lead
    .venv/bin/python -m pytest -q AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2

Expect 26 passed.  Confirm the machine clears the declared floors - 12 GiB
available RAM and 40 GiB free disk - with `free -g` and `df -h .`.  The campaign
refuses to start otherwise; it never silently coarsens.

## Run the whole development set

    AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/production_desktop.sh \
      --development \
      --indices 0-99 \
      --level coarse \
      --te-variant te_1p0mm \
      --output /path/to/output_root

Sequential and resumable.  Progress:

    find /path/to/output_root -name case_result.json | wc -l

## Run several cases at once

Each case is single-threaded, so on a machine with N cores and enough RAM
(about 6 GB per concurrent case) split the range and run the parts side by side,
each with **its own output root**:

    for part in "0-24" "25-49" "50-74" "75-99"; do
      AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/production_desktop.sh \
        --development --indices "$part" --level coarse --te-variant te_1p0mm \
        --output "/path/to/output_${part}" &
    done
    wait

Four-way splits the 16 hours to about four.  Do not point two runs at one output
root: each batch owns an immutable request identity there.

## If it stops

Re-run the identical command against the same output root.  Completed cases are
reloaded from their digest-verified terminals and only the unfinished work runs
again.  This was exercised during development: a run killed mid-case resumed from
31 verified terminals and regenerated only the incomplete one.

If a case was killed part-way through writing, the campaign refuses to resume it
rather than trust a partial artifact.  Delete only that case directory and re-run:

    rm -rf /path/to/output_root/campaign_runs/*/cases/dev_0NN__coarse__te_1p0mm__mesh
    rm -f  /path/to/output_root/campaign_runs/*/campaign_terminal.json \
           /path/to/output_root/campaign_runs/*/campaign_result.json

## Reading the result

    .venv/bin/python - <<'PY'
    import json, glob
    root = "/path/to/output_root"
    rows = [json.load(open(f)) for f in
            glob.glob(root + "/campaign_runs/*/cases/*/case_result.json")]
    bad = [r["case_id"] for r in rows if not r["accepted"]]
    print("cases %d accepted %d failed %d" % (len(rows), len(rows) - len(bad), len(bad)))
    for b in bad:
        print("  ", b)
    PY

`accepted` means the declared technical scope passed.  It is **not** a
campaign-readiness claim: `campaign_ready` stays false until the readiness targets
in `POLICY.yaml` are met and the independent review is resolved.

## Confirm multigrid (open item 1)

This is the blocker on every accuracy claim, and it is the one experiment that was
started and never finished.  The first round of six variants ran to completion and
identified multigrid: **3.250 orders** dropped against the baseline's 1.658, with
the CD spread tightening from 1.8e-3 to **2.4e-6**, a factor of 770, at the same
CD of 0.09099.  Non-dimensionalisation and limiter freezing at 400 and 1200 were
refuted and should not be retried.

Round two - G longer multigrid, H multigrid plus a late freeze, I multigrid at
higher CFL - was killed mid-flight at about a third of the way.  Last readings
were **G -5.40, H -5.83, I -3.28**, all still falling.  H had not yet reached the
six-order gate but was closest.  Those numbers are trajectories, not results; the
runs must be repeated to completion before anything is concluded from them.

    export PATH="$PWD/AERIS_MESH_STUDY/tools/su2_8.5.0/bin:$PATH"
    export SU2_RUN="$PWD/AERIS_MESH_STUDY/tools/su2_8.5.0/bin"
    .venv/bin/python \
      AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/convergence_matrix.py \
      /path/to/coarse_mesh.su2  6000  2  3  round-two

The arguments are mesh, iterations, MPI ranks per variant, concurrent variants,
and any fifth argument to select G/H/I instead of the full six.  Drop the fifth
argument to re-run the whole matrix from scratch.

**Watch the memory.**  Every rank reads the entire mesh before partitioning, so a
2.55 M cell coarse mesh costs about **3 GB per rank** and the concurrent variants
multiply it: `workers x ranks x 3 GB` must fit in RAM with room to spare.  On the
16 GiB laptop eight ranks were OOM-killed and four ranks drove free memory to
290 MB; two ranks were stable.  The `2 3` above is six ranks, about 18 GB, which
needs a 32 GiB machine.  On 16 GiB use `2 1` and accept the serial wall time.

Read the result from the printed table or `conv_matrix/matrix.json`, ranked by
`best_drop`.  Two outcomes, both decisive:

- **A variant reaches six orders.**  Adopt it through a superseding ADR amendment
  that carries the measurements, then proceed to item 3.
- **None reaches six orders while CD stays flat.**  The residual gate itself was
  mis-derived and must be re-derived, with the force plateau as the candidate
  criterion.  This is a gate *re-derivation* with evidence, which the
  preregistration allows; it is not gate weakening, which it forbids.  Write it as
  a superseding ADR that states what was measured and why the old gate was wrong.

## HPC

`production_hpc_slurm.sh` maps `SLURM_ARRAY_TASK_ID` to `--index` and passes the
allocated ranks to SU2 only; Gmsh stays single-threaded for determinism.

    sbatch --array=0-99 \
      AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/production_hpc_slurm.sh \
      --development --level coarse --te-variant te_1p0mm --output /shared/aeris/s7_coarse

## What this does not do

The mesh campaign above runs no CFD; `--run-cfd` requires the pinned SU2 8.5.0,
which is now installed under `AERIS_MESH_STUDY/tools/su2_8.5.0` and is gitignored
as a reproducible download.  The hold-out `round_c_lhs10_seed42` is forbidden and
the runner has no bypass.
