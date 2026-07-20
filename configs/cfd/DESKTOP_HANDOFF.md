# Picking this up on your desktop — step by step

This machine's work transfers to another machine via git (remote:
`github.com/karmix96/aeris.git`). As of 2026-07-20 there is a large amount of
**uncommitted** work from this session (the whole `aeris.cfd` suite, studies,
campaign tool, RUNBOOK, this file) — it will NOT exist on the desktop until
committed and pushed here first.

## 1. On this machine (laptop), before switching
```bash
cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
git add -A
git commit -m "cfd suite: sensitivity studies, mesh-robustness campaign, wing GCI staging"
git push origin main   # or your working branch
```
(Ask me to do this if you'd rather I run it — I don't commit/push without
being asked, per your standing rule.)

## 2. On the desktop
```bash
git clone https://github.com/karmix96/aeris.git   # first time only
cd aeris
git pull                                          # if already cloned
conda activate mach-aero                          # pyHyp/ADflow env must exist there too
```
If `mach-aero` (and, for SU2 work, the `su2` env) aren't set up on the
desktop yet, that's a prerequisite — the CFD suite calls those envs by name/
path (`env.py`, `AERIS_SU2_CONDA_PREFIX` if SU2's path differs there).

## 3. Open Claude Code there and say:
> "Read configs/cfd/RUNBOOK.md and configs/cfd/DESKTOP_HANDOFF.md, and
> continue from where the AERIS CFD session left off."

A fresh session will pick up full context from the repo files (this doc,
RUNBOOK.md, DSE_READINESS.md, memory) — you don't need to re-explain the
project.

## 4. Run the heavy items, in this order (all pre-staged, exact commands in RUNBOOK.md)
1. Mesh-robustness campaign, full `--n 100`, cap4 (already know ~60-70%
   clean at n=10 with 2 unexplained failure modes — this run gives real
   statistical power).
2. Same campaign with `--topology mid4 --volume-level L4` for comparison.
3. Wing-level 3-grid GCI (`wing_gci_{smoke,fine,production}.yaml`).
4. 2D sensitivity studies (farfield/wall-spacing/Euler-vs-RANS) — cheap
   individually but bundled here for one clean "heavy session."
5. Deflected-CAD path (`export-deflected-cad` -> `cad_gmsh_tet_v1`) — not
   yet wired into the campaign tool, biggest remaining infra gap.

Everything writes its own provenance (manifests, sha256 chains) — nothing
here depends on remembering context between sessions.
