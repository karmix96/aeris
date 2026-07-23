# Installing the pyGeo geometry backend

AERIS has two geometry backends: the legacy **AeroSandbox** path (default, no extra
deps) and the **pyGeo** path (structured B-spline BWB loft + physical-CAD control
surfaces + native IGES/Tecplot exports). The pyGeo backend is optional; the rest of
AERIS runs without it.

Validated dependency set (what AERIS is tested against):

| Package  | Version | Source          | Build needs        |
|----------|---------|-----------------|--------------------|
| pySpline | 1.5.4   | PyPI / mdolab   | Fortran + CMake    |
| pyGeo    | 1.17.0  | PyPI / mdolab   | pySpline           |
| CadQuery | 2.7.0   | PyPI            | (wheels)           |
| Gmsh     | 4.15.2  | PyPI            | (wheels)           |
| Plotly   | 6.7.0   | PyPI            | (wheels)           |

## Quick path (pure-PyPI deps only)

The CAD / meshing / viz deps install cleanly from wheels:

```bash
pip install -e ".[geometry]"
```

This enables physical-CAD control surfaces (CadQuery/OCC), the Gmsh import audit,
and Plotly geometry visualization — but **not** the pyGeo loft itself.

## Full path (pyGeo + pySpline)

pySpline compiles native (Fortran) extensions, so you need a compiler toolchain
first:

```bash
# Debian/Ubuntu
sudo apt-get install -y gfortran cmake build-essential

# then, from a venv:
pip install -e ".[geometry,geometry-mdolab]"
```

If the PyPI build fails on your platform, build from the vendored source instead:

```bash
pip install ./.deps/mdolab/pyspline
pip install ./.deps/mdolab/pygeo
```

## Verify

```bash
python -c "import pygeo, pyspline, cadquery, gmsh, plotly; \
print('pygeo', pygeo.__version__, '| pyspline', pyspline.__version__)"
```

Expected: `pygeo 1.17.0 | pyspline 1.5.4`.

## Selecting the backend in AERIS

Backend is chosen per geometry config:

- `geometry.outputs.build_aerosandbox` — build the AeroSandbox geometry (legacy)
- `geometry.pygeo.enabled` — build the pyGeo geometry

Set one, the other, or both (dual mode, for cross-validation). See
`src/aeris/generators/bwb_segmented_v1/PYGEO_BACKEND.md` and
`configs/geometry/paper1_bwb_pygeo.yaml`.
