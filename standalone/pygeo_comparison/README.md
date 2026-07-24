# Standalone pyGeo comparison

This folder is independent of the Aeris Python package. The script does not
import or register anything in `aeris`.

From the project root:

```bash
.venv/bin/python standalone/pygeo_comparison/compare.py \
  --mode pygeo \
  --output-dir artifacts/pygeo_standalone
```

That generates pyGeo alone, including a PNG visualization, IGES, Tecplot,
sampled surfaces, station CSV, and JSON report.

For the visual and numerical comparison against AeroSandbox:

```bash
.venv/bin/python standalone/pygeo_comparison/compare.py \
  --mode compare \
  --output-dir artifacts/pygeo_comparison
```

The comparison uses exactly the same station positions, chords, twists, and
airfoil coordinates. It writes:

- `pygeo_standalone.png`
- `pygeo_vs_aerosandbox.png`
- `comparison_report.json`
- `comparison_metrics.csv`
- `pygeo_surface.igs` and `pygeo_surface.dat`

Numerical surface metrics compare the positive half-wing upper/lower
outer-mold-line surfaces. Root, tip, trailing-edge caps, and the mirrored side
are excluded. Distances are evaluated from sampled points to triangulated
surfaces in both directions. Increase `--chordwise-points` and
`--spanwise-points` for a convergence check.

The project-local `.venv` currently contains pyGeo and pySpline. Their source
trees are retained under the project-local, git-ignored `.deps/mdolab/`
directory, so this setup does not rely on a temporary directory.
