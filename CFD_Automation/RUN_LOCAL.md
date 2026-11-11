# Run it locally: Stage 1 to Stage 3, the app, and V7

The commands to rebuild and check everything from Stage 1 to today (11 Nov 2026) on your machine. Times are measured
here (2 cores, 7 GB RAM, numpy loft); your machine is faster. Run each block from the folder it names.

**Two rules first**

- Never pass `--open-holdouts`: the hold-outs were opened once for the surface mesh (decision 83) and stay sealed for
  the volume mesh (decision 104). The app and `one_mesh.py` refuse them.
- No `git add -A` or `git commit -a` while the 1,622 locally deleted files (`AERIS_MESH_STUDY`, `AERIS_MESH_AGENT`, 3
  top files) are not sorted out. They are still in git; `git restore AERIS_MESH_STUDY AERIS_MESH_AGENT
  CFD_PIPELINE_DEFENSE_STUDIES.txt mesh_paper_roadmap.md mesh_paper_roadmap_review.md` brings them back.

## 0. Once

```bash
git checkout main && git pull                  # main holds Stages 0-3 and the app (merged 10 Nov 2026)
source <your AERIS .venv>/bin/activate          # pyGeo 1.17.0, pySpline 1.5.4
pip install -e CFD_Automation                   # the cfdauto package (every stage)
pip install streamlit plotly pandas             # only for the app
# pandoc is needed only to rebuild the pages (section 6)
```

## 1. The tests (about 2.5 min here: Stage 1 25 s without pyGeo, Stage 2 75 s, Stage 3 20 s, the app 20 s)

```bash
cd CFD_Automation/Stage_1_geometry      && python -m pytest -q          # 178 + the pyGeo ones; without pyGeo: -m "not pygeo"
cd ../Stage_2_surface_mesh              && python -m pytest -q          # 45 tests
cd ../Stage_3_volume_mesh               && python -m pytest -q          # 45 tests, about 20 s
cd .. && python -m pytest app/tests -q                                   # the app, 7 tests, about 20 s
```

## 2. Stage 1: the wings

```bash
cd CFD_Automation/Stage_1_geometry
python -m cfdauto.geometry.build --type bwb --set reference --index 0   # one wing -> data/wings/...
python -m cfdauto.geometry.build --all          # every set wing with pyGeo (722; open item of 9 Nov: new input
                                                #   hashes after the label fix) -> commit only data/sets/*_manifest.json
python -m cfdauto.geometry.published_wings --build all                   # M6, RIBES, CRM, BlendedNet (pyGeo)
python scripts/verify_geometry.py               # is the surface the intended wing (published wings)
# the flow data (no XFOIL run needed):
tar -xzf data/section_cache.tar.gz -C data && python -m cfdauto.flowmap.tables --assemble
```

The sets themselves (`data/sets/`) are in git: do not rerun `cfdauto.geometry.sample`.

**The run still owed (open since 8 Nov):** `build --all` with pyGeo, then push the manifests. One script does the
tests, the build and the comparison with git, and prints the three git commands (it commits nothing itself):

```bash
python CFD_Automation/Stage_1_geometry/scripts/pygeo_build_all.py    # from the repo root, in the AERIS .venv
```

## 3. Stage 2: the surface meshes

```bash
cd CFD_Automation/Stage_2_surface_mesh
python -m cfdauto.mesh --type bwb --set reference --index 0 --level VC --re 3e5          # one mesh
python -m cfdauto.mesh --type bwb --set reference --index 0 --family --re 3e5            # VC, C, M, F of one wing
# Study 12, every set at every level (3,128 builds; about 2.9 h per process): run the two in two terminals
python scripts/screen.py --family --types bwb cranked --tag bwb_cranked
python scripts/screen.py --family --types flying_wing tapered --tag flying_wing_tapered
python scripts/screen_study.py --family                                                   # the summary and figures
```

## 4. Stage 3: the volume meshes (rule set 2)

One mesh, any wing (writes `data/meshes/<name>/`, not in git):

```bash
cd CFD_Automation/Stage_3_volume_mesh
python scripts/one_mesh.py --type bwb --set reference --index 0 --level VC --re 3e5
python scripts/one_mesh.py --type cranked --set training_focus --index 12 --level M --formats npz cgns su2
python scripts/one_mesh.py --type tapered --set reference --index 3 --level F --count     # cells and RAM only
```

Every study of rule set 2, as rerun on 9-10 Nov: two queues, one per terminal (about 1.7 h each here).

```bash
# queue a                                                                                     # time here
python scripts/v1_study.py                                                                     # 10 s
python scripts/screen.py --sets reference --types bwb flying_wing --tag ref_VC_a              # 8.5 min (V2, V3)
python scripts/family_study.py --types bwb flying_wing --levels VC C --tag ref_a              # 9 min (V4)
python scripts/screen.py --sets training_full corner1 corner2 --types bwb flying_wing --tag s_a1   # 30 min (V6)
python scripts/family_study.py --types bwb --indices 0 --levels VC C M F --tag f1             # (V4: F built)
python scripts/screen.py --sets training_focus --types bwb flying_wing --tag s_a2             # 41 min (V6)
python scripts/screen.py --sets training_focus training_full corner1 corner2 --types bwb flying_wing --count --levels F --sample 0.1 --tag F_sample_a
python scripts/screen.py --sets training_focus training_full corner1 corner2 --types bwb flying_wing --count --levels M --sample 0.1 --tag M_sample_a

# queue b
python scripts/v5_export.py                                                                    # 30 s (CGNS, .su2; the V7 mesh)
python scripts/screen.py --sets reference --types cranked tapered --tag ref_VC_b
python scripts/family_study.py --types cranked tapered --levels VC C --tag ref_b
python scripts/screen.py --sets training_full corner1 corner2 --types cranked tapered --tag s_b1
python scripts/family_study.py --types flying_wing cranked tapered --indices 0 --levels VC C M --tag m4
python scripts/screen.py --sets training_focus --types cranked tapered --tag s_b2
python scripts/screen.py --sets training_focus training_full corner1 corner2 --types cranked tapered --count --levels F --sample 0.1 --tag F_sample_b
python scripts/screen.py --sets training_focus training_full corner1 corner2 --types cranked tapered --count --levels M --sample 0.1 --tag M_sample_b

# then the summaries (seconds each)
python scripts/v23_study.py && python scripts/v4_study.py && python scripts/v6_study.py
```

A screen stopped half way goes on with the same command plus `--resume`. What to expect: V2 80 of 80, V4 20 of 20,
V6 721 of 722 (BWB corner2 wing 6 refused: cell quality 0.032). The results land in `data/studies/` (`r2_*`); `git
diff` on them shows whether your machine gives the same numbers.

The size studies of 10–11 Nov (what-if copies of the rules files; nothing is changed; `decisions/volume_rules.md`,
sections 18–21). Times here, on 2 cores:

```bash
python scripts/far_field_study.py                 # smaller domains (section 18)
python scripts/size_factors.py                    # the cells against Re, band on and off (section 19)
python scripts/size_drivers.py                    # the counts against the wing (20.1; reads the V6 screen files)
python scripts/knob_study.py                      # 21 rules loosened one at a time (20.2); about 50 min
python scripts/light_set.py --packages A2,B2_100,B2_dpw,C2    # the loosened rules together (20.4); about 30 min
python scripts/ladder_study.py                    # the ladder VVC to F, today and lighter (21); about 15 min
python scripts/ladder_study.py --ref20            # the same on the 20 reference wings; about 30 min
python scripts/ladder_study.py --family           # the lighter rules built on BWB 0, VVC to M, check 13; 2 min
python scripts/size_figures.py && python scripts/blocks_figure.py   # their figures
```

## 5. The app

```bash
streamlit run CFD_Automation/app/app.py          # http://localhost:8501; see CFD_Automation/app/README.md
```

## 6. The pages (optional; needs pandoc)

```bash
cd CFD_Automation/Stage_3_volume_mesh
python scripts/make_flowchart_values.py && python scripts/make_stage3_page.py
python scripts/make_summary_page.py && python scripts/page_to_markdown.py
cd .. && python overview/make_approach_map.py
```

## 7. V7: the first solves (needs ADflow and SU2)

`CFD_Automation/Stage_3_volume_mesh/solve/RUNBOOK.md`, in short:

```bash
cd CFD_Automation/Stage_3_volume_mesh
python scripts/v5_export.py
python solve/case.py --mesh data/meshes/volume_VC_e32d995a_re3e5 --alpha 4 --mach 0.1 --re 3e5 --out runs/v7_a4
P=<your MACH-Aero env>/bin
$P/mpirun -np 6 $P/python solve/run_adflow.py --case runs/v7_a4 --preflight
$P/mpirun -np 6 $P/python solve/run_adflow.py --case runs/v7_a4                       # ADflow SA (about 1.4 h)
cd runs/v7_a4 && mkdir -p su2_sa su2_sst_lm
(cd su2_sa && mpirun -np 6 SU2_CFD ../su2_sa.cfg > log.txt 2>&1)
(cd su2_sst_lm && mpirun -np 6 SU2_CFD ../su2_sst_lm.cfg > log.txt 2>&1)
cd ../.. && python solve/read_results.py --case runs/v7_a4                              # results.json, results.md
```

Memory (decision 113): the runbook's section 5. The wake at −5° and +10° (decision 111): its section 6.
