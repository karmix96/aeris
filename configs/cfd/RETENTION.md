# CFD artifact retention policy

`data/cfd_cases/` and `data/meshes/` are gitignored. Nothing in them is
backed up, and a full DoE campaign writes tens of GB of volume meshes, so
the default assumption must be that **bulk mesh artifacts are a cache, not
data**. This file defines what survives.

Apply it with `aeris cfd prune` (dry-run by default).

## Why meshes are safe to delete

A pyHyp volume mesh is a deterministic function of `surface.fmt` plus
`pyhyp_options.json`. This is established, not assumed:

- `determinism_check.json` (2026-07-20): the surface mesh is byte-identical
  across reruns, and every one of the volume CGNS's 29 HDF5 datasets is
  bit-identical. (The raw *file* bytes differ — that is non-semantic
  HDF5/CGNS container metadata. Compare dataset contents, never file
  hashes, when checking mesh determinism.)
- Reconfirmed 2026-07-22 by the `remarch` control: re-marching three failed
  geometries with unmodified options reproduced exactly 53 / 100 / 14
  inverted cells at identical block, index and layer ranges.

A 0.85 MB `surface.fmt` therefore substitutes for a 41.6 MB CGNS at a
regeneration cost of ~2 minutes. That is a 50x saving for a 2-minute debt.

The caveat: bit-reproducibility holds *for a given pyHyp/mach-aero build*.
An upgrade could change results, which is why rule 4b keeps frozen
exemplars.

## Rules

**1. Evidence — never delete.**
`*.json` (reports, manifests, provenance), `*.log`, `*.csv`,
`run_pyhyp.py`, case YAMLs. A few MB across all runs. These *are* the
findings; everything else can be recomputed from them.

**2. Reproducibility inputs — keep.**
`surface.fmt`, `pyhyp_options.json`, `pyhyp_effective_options.json`.
Keeping these is what makes rule 3 safe.

**3. Bulk mesh and field artifacts — delete.**
`*.cgns`, `*.vtk`, `*.npz`, `*.vtu`, `*.su2`, `restart.dat`, `*.dat`
solution files produced by campaigns.

**4. Exceptions that override rule 3.**
   a. **Validation anchors.** Runs whose artifacts cost real solver time
      (minutes to hours, not the ~2 min a mesh re-march costs) and which
      form the V&V trust chain: the NACA0012 TMR validation, the SU2
      cross-solver comparison, the 3-grid GCI ladder. Keep until
      superseded by a better run of the same case.
   b. **One frozen exemplar per documented failure mode.** Insurance
      against a pyHyp/mach-aero upgrade breaking bit-reproducibility. Name
      it in the failure-mode writeup so it is obvious why it exists.

**5. Superseded runs — delete whole.**
Wiring/smoke tests once the real run exists; any campaign run against a
recipe that has since been corrected.

## Findings live in `configs/`, not `data/`

`data/cfd_cases/README.md` once held the only copy of the TMR validation
numbers, the GCI table and the cross-solver comparison — in a gitignored
directory. It was nearly destroyed by a routine cleanup. Results writeups
belong in `configs/cfd/` (tracked): see `RESULTS_ARCHIVE.md` and
`SURFACE_MESH_LAWS.md`. When a run establishes something, write the number
into a tracked file; do not leave it in the run directory.
