# AERIS Mesh Study

This folder is the single workspace for the AERIS structured and future unstructured meshing studies.

## Agent entry point

1. Read `RUNBOOK.md` completely.
2. Execute Stage 00 only.
3. Create the complete folder tree declared in the runbook.
4. Write the Stage 00 report and gate artifacts.
5. Stop at `AWAITING_USER_APPROVAL`.
6. Continue only after receiving `APPROVE STAGE 00`.

Routine safe work inside an approved stage does not require repeated permission. Starting the next stage always requires the explicit approval token.

## Storage rule

All study configurations, commands, logs, quality tables, reports, plots, manifests and results belong under this folder. Reusable source-code changes remain in the normal AERIS package, with their code/config hashes recorded here.

Large mesh files belong under `artifacts/`; their manifests and hashes must remain available even when the mesh bytes are excluded from Git.
