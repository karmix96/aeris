# Claude Opus Max Review

Date: 2026-08-21

All Claude Code review passes used `--model opus --effort max`, as required by
the user.

## Findings and closure

1. The first broad review found three high-severity risks: the collector could
   overwrite historical evidence, production CFD cache identity omitted MPI and
   output hashes, and mesh fingerprints omitted implementation dependencies.
   All three were fixed.
2. The second broad review found no critical or high issue. It found two medium
   fingerprint gaps for surface ingestion and LHS sampling. Both were fixed.
3. The third narrow review found one remaining medium gap: ingestion was a shim,
   while the real implementation in `src/aeris/mesh/surface.py` was not hashed.
   The campaign now fingerprints all `src/aeris/mesh/*.py` files.

## Final local verification

- `src/aeris/mesh/surface.py` is present in the campaign mesh fingerprint.
- 41 focused S6 tests pass; 51 pass with the ADflow adapter tests.
- Ruff, formatting, and Python compilation pass.
- The historical laptop summary remains unchanged at sha256
  `88c745656afe218a1a6bd031c931b9d6c380debb3fb19657f1a08cd18d1889b8`.
- The three historical N65 runs are integrity-checked but correctly rejected as
  current-cache evidence.

No known code or provenance blocker remains before the P0 N257 HPC canary. S6
is still not campaign-ready because production y+, TE sensitivity, true grid
convergence, and locked hold-out evidence are incomplete.
