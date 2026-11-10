# Wings and meshes: the app

Load a wing from the sets, make one from its numbers, or open a wing file; build its surface mesh and its volume
mesh at any level and Re; look at them in 3-D and plane by plane, with every check; write the files.

The app runs the stage code itself (`cfdauto`: Stage 1 geometry, Stage 2 surface mesh, Stage 3 volume mesh,
rule set 2) with the same rules and checks as the studies. It copies no rule and changes nothing in `cfdauto`.

## Run it

```bash
cd aeris                                   # the repo; the AERIS .venv active
pip install -e CFD_Automation              # once (cfdauto)
pip install streamlit plotly pandas        # once
streamlit run CFD_Automation/app/app.py    # opens http://localhost:8501
```

Tests (no browser needed): `python -m pytest CFD_Automation/app/tests -q` (about 20 s).

## What it does

| Sidebar | |
| --- | --- |
| **1 · The wing** | *A set wing*: type, set (reference, training_focus, training_full, corner1, corner2), number. *Create one*: the type's free numbers on sliders (focus or full ranges), the four sections by name (any project section, AERIS database name or NACA 4/5-digit); start from the middle of the ranges or from a set wing. *A file*: this app's wing file or a Stage 1 `vector.json`. |
| **2 · The mesh** | Level (VC, C, M, F), Re on the mean chord (1e5, 3e5, 1e6, 4e6 or any), then **Build surface** or **Build volume**. |

| Tab | |
| --- | --- |
| **Geometry** | Stage 1 gates and labels; the planform, the four sections, the wing in 3-D; the 17 numbers with their ranges. |
| **Surface mesh** | The mesh in 3-D (every line, or every n-th on fine levels), one station ring with its nodes, the Stage 2 checks. |
| **Volume mesh** | Cells (counted before the build), the RAM by S8's laws, any station plane (root to far field: close, wake or whole view, the wake fan, the block names), a 3-D look at a few planes, the Stage 3 checks, the 13 blocks. |
| **Files** | Download the wing file; write the wing folder, the surface mesh folder, or the volume mesh with `volume.cgns` (ADflow) and `volume.su2` (SU2) into `CFD_Automation/app/output/` (not in git). |

## Limits

- **The hold-out sets are not offered** (sealed: never used to develop or tune the meshes).
- **Time and memory:** VC builds in seconds. M (about 10 M cells) and F (about 21 M) take minutes and several GB of
  RAM to build. The pictures thin the lines past about 160,000 points: zoom in to see every line.
- **A created wing can be refused** by Stage 1 (the gates), Stage 2 or Stage 3 (the checks): the app says which check
  and why, as the studies do. A wing from a file may lie outside the full ranges: it is built, but untested there.
- **RAM** is S8's two laws (decision 112), a guide only, until V7 measures it (decision 113).
