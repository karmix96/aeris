# ADR-0004: Stage 01 Cap4 Control Blocker

Date: 2026-08-11
Status: Accepted as blocking evidence

## Context

Stage 01 required a TMR anchor reproduction and a current-design-space cap4/epsE control that could provide epsE_common_start for later strategy comparisons.

The TMR anchor passed. The current cap4 L3 surfaces generated successfully for all 10 locked seed-7 samples, but pyHyp marching failed the quality gate on the first locked sample for every declared epsE candidate.

## Decision

Do not promote an epsE_common_start from Stage 01. Treat Stage 01 as failed and blocked pending a cap4/pyHyp replan. Stage 02 is not authorized.

## Evidence

- L3 epsE 1.5: invalid volume, 10 inverted cells, min_volume -5.44e-10, min_quality -1.0.
- L3 epsE 2.0: invalid volume, 4 inverted cells, min_volume -4.52e-11, min_quality -1.0.
- L3 epsE 3.0: valid volume with zero inverted cells, but 53 low/negative-quality layers and min_quality -0.90808.
- L1 and L2 first-row probes also failed the quality rule, with 60 and 55 low/negative-quality layers respectively.

## Consequences

Stage 01 must be replanned around the cap4 tip/control topology or pyHyp start policy before any fair S0-S5 comparison can begin.
