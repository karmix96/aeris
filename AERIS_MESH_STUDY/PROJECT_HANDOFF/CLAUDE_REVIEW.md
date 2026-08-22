# Independent Claude Code Review

Review date: 2026-08-16

Claude Code ran for about 20 minutes with only `Read`, `Glob`, and `Grep` tools.
It made no edits, ran no heavy commands, and did not open the locked hold-out.
It read the handoff, S6 source/docs, shared gates, ADRs, and canonical reports.

## Verdict

Claude judged the deformation kernel, deterministic maximin selection, cache/hash
design, atomic recovery, and y+ rejection logic technically sound. It also found
that S6 is not ready for production validation/freeze because several gates and
claims are weaker than the campaign path.

## Blockers found

1. **Smoke freeze was still bypassable.** `run_s6.py` allowed callers to set the
   required freeze level to smoke and to inject a missing validation level.
2. **The `0.10` and `0.15` S6 thresholds lacked an ADR.** ADR-0011 freezes `>0` as
   the tournament gate and `0.30` as a ranking target. A separate campaign-level
   screen needed explicit governance.
3. **ADR-0015 is unresolved.** It changes station-independent dihedral integration,
   requires exact sections at arbitrary stations, set re-identification, full
   tests, and fidelity verification before acceptance.

## High findings

- The first production run changed wall-normal `N` and first-cell spacing at the
  same time, so the quality loss was confounded.
- pyHyp and the independent corner-scaled-Jacobian metric disagree strongly on the
  same CGNS. Both must be retained and their roles stated clearly.
- S6's fidelity result checks resampled chordwise arcs against their own dense
  source. It does not independently exercise every fidelity condition discussed in
  ADR-0015/COMMON_BRIEF.
- The declared TE opening is a chordwise linear thickness wedge, not a local TE-only
  change. Its aerodynamic effect remains unmeasured.
- Deformation does not report or gate the target mesh's realized first-cell law.
- S1 templates use a constant 1 mm TE while S6 targets may use `max(1 mm, 0.5%c)`;
  that mismatch is absorbed in the same aft/base blocks that govern quality.
- `development_atlas.py` accepts in-memory meshes without written-CGNS re-audit and
  does not run every surface/fidelity gate used by `campaign.py`.
- The smoke 100/100 result contains 16 identity template cases; independent
  deformations should also be reported as 84/84.
- The highest-Reynolds-flow wall-spacing rule in `POLICY.yaml` is not implemented.
- Seed pruning had no known-unbuildable/backfill state and could cycle through
  failed enrichment candidates.

## Medium findings

- `cmy` has no explicit moment reference location across changing geometries.
- Force plausibility checks are only finite values and positive drag.
- Collection can report stale results because it checks fewer hashes than caches.
- y+ percentiles are node-weighted, and expected wall-zone count is not gated.
- Written re-audit reuses pre-write wall/interface metadata.
- The volume metric materialized eight full corner arrays, wasting memory.
- `surface_level` is hardcoded and not verified from seed provenance.
- No true three-direction S6 refinement family exists; current production work is
  `L2_smoke` tangentially and `N=257` wall-normal.
- The worst cell location was not recorded.
- S6 imports S1-private topology symbols without a dedicated independence ADR.
- Several fallback, stale-cache, interface-break, y+-missing, and wall-spacing
  negative tests are absent.

## What Claude found sound

- The C1 bounded deformation profile preserves wall/farfield behavior and shared
  eta protects interfaces.
- Campaign acceptance consistently uses the stricter S6 screen, not merely the
  positive-volume gate.
- The new production seed qualification is complete, traceable, and cannot freeze.
- Maximin normalization and ordering are deterministic and defensive.
- Implementation/config/file hashes, atomic writes, and stale-lock recovery are
  strong campaign engineering.
- The coarse CFD pilot was correctly rejected on y+ despite convergence.

## Codex disposition

- **Freeze bypass: confirmed and fixed.** Freeze is now pinned to production; CLI
  overrides were removed; a regression test covers the attempted smoke override.
- **Threshold governance: confirmed and fixed without weakening.** ADR-0016 keeps
  ADR-0011's `>0` feasibility gate and separately governs S6's `0.10` campaign
  screen and `0.15` preferred target.
- **ADR-0015: confirmed, with timing nuance.** The exact-integration source changed
  at 15:22 local time; the production seed report was generated at 19:26, so the
  new production seeds used the changed source. ADR-0015 is still Proposed because
  exact-station wiring, tests, set hashes, and fidelity evidence are incomplete.
- **Confounding: confirmed.** A controlled development calibration is under way.
  epsE 1.5 plus first-cell fraction `3.6e-6` passed difficult seeds 002/068 at
  `0.10535`/`0.12314`; this remains provisional until all seeds and CFD y+ pass.
- **Worst-cell diagnostics/memory: fixed.** Reports now include block, `(k,j,i)`,
  wall layer/distance, edge lengths, center, and sub-threshold counts. The corner
  reduction now uses a running minimum.
- **Quality-floor recommendation: not accepted.** Claude suggested reverting the
  campaign screen to ADR-0011's `>0`. The project goal needs a stricter unattended
  screen; ADR-0016 preserves `0.10` while requiring solver correlation.
- **Fidelity, TE wedge, realized wall spacing, campaign-equivalent development
  audit, true grid family, Reynolds rule, moment reference, and missing tests:
  confirmed open.** They must be closed before freeze or hold-out.

## Claude's recommended order

Stop before freeze; resolve ADR-0015; deconfound `N`, s0, and epsE; report the
worst cell; reconcile wall/quality instruments; close the freeze bypass; run the
development audit through written campaign gates; add realized wall-spacing
checks; then use >=64 GB hardware for production CFD. Never touch the hold-out in
this sequence.
