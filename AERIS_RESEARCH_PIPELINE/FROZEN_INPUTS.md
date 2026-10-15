# Frozen-input contract

This pipeline must not write to or modify:

- `AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/march_o.py`;
- mesh definitions or generated mesh/run directories;
- ADflow settings or policy files;
- convergence-gate implementations or gate evidence;
- `AERIS_MESH_STUDY/05_s6_cfd_qualification/dataset/` and `reports/`;
- any ongoing measurement.

All code and default outputs live under `AERIS_RESEARCH_PIPELINE/`. The default
generated directory is ignored by Git. The CLI rejects explicit output paths
inside qualification inputs, strategy code, or CFD artifacts.

The campaign monitor is observational only. It does not acquire or clear the
campaign lock, run a convergence gate, generate a dataset row, restart a solver,
or overwrite a run directory. Restart output is a recommendation document with
`automatic_action_taken: false` and `overwrite_existing_directory: false`.

Accepted releases use copied, deterministic gzip payloads rather than links to
mutable artifact files. Every source is checked before and after reading and is
rechecked before release publication.
