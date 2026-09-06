# ADR-0020 — S8 desktop campaign: a refinement trend, a ten-geometry pilot, and an external validation

**Status:** accepted · **Date:** 2026-09-06 · **Supersedes the scope of:** ADR-0019
**Plan:** `04_strategy_studies/S8_oh_structured/PLAN_desktop_campaign.md`
**Policy:** `05_s6_cfd_qualification/policies/s8_campaign_v1.yaml`

## Context

The S8 O-H mesher builds 100/100 designs with zero inverted cells and the wall
layer 2.22e-16 m from the exact loft. Meshing is no longer the blocker. What S8
has never had is a statement of how much of its answer is discretization, a look
at more than one geometry, and any comparison against experiment.

`PLAN_desktop_campaign.md` sets out the work. This ADR records the one place
where the executed campaign departs from it, and why.

## Decision

Authorize the plan, minus the grid levels that do not fit.

### The departure: two levels, not three

The plan's §2.1 asks that the third grid level be chosen from **actual available
RAM**, and gives the rule. Measured on this host on 2026-09-06:

| | |
|---|---|
| Windows physical memory | 15.86 GiB |
| WSL2 cap (`.wslconfig` `memory=13GB`) | 13 GiB |
| available inside WSL | **12.4 GiB** |

Against the memory law `1.51 GiB + 9.46 GB per million cells`:

| level | cells | required | fits |
|---|---|---|---|
| `gci_C` | 567,256 | 6.9 GiB | yes |
| `gci_M` | 1,111,152 | 12.0 GiB | at the ceiling |
| `gci_MF` | ~1.6 M | 16.6 GiB | **no** |
| `gci_F` | 2,217,680 | 22.5 GiB | **no** |

`gci_F` and the `gci_MF` fallback are not reachable by raising the WSL memory
cap, because the *host* has 15.86 GiB in total. §2.1's third branch applies:

> **available < 14 GiB** → two levels only. That is a trend, not a GCI. Say so.

So it is said, here and in every artefact the campaign writes. Two levels give
a **refinement trend**: a direction and a magnitude of movement between two
grids. They do not give an observed order of accuracy, a Richardson
extrapolation, or an uncertainty band, because all three need a third point.
`gci.py` refuses to produce a GCI from two levels; a separate, explicitly named
`--two-level-trend` path reports the movement and states what it is not.

This is the plan's own preferred outcome over the alternative it warns against.
§2.1 says of the `gci_MF` fallback that a smaller ratio "**weakens the GCI**"
and to "prefer finding a bigger machine". Here even that fallback does not fit,
and the choice is between an honest trend and no measurement at all.

### What that costs, and what it does not

The campaign level chosen in §3.5 is chosen on a weaker basis than planned:
between two levels rather than three, with the movement itself as the evidence
and no band around it. The pilot, the dataset schema, the AVL cross-check, the
far-field sensitivity run and the ONERA M6 validation are unaffected — none of
them needed the third level.

The third level remains the single outstanding requirement for a defensible
uncertainty statement on S8 drag and moment, and until it is run, **no drag,
moment or neutral-point figure from S8 carries a discretization uncertainty**.
That was already true before this ADR; it stays true after it.

### Also decided

1. **The ten pilot geometries are fixed before the pilot runs**, by maximin over
   the 20 normalised design variables, and the selection is reproducible from a
   script rather than a document — `select_pilot_geometries.py`.
2. **The dataset schema is fixed before the first pilot case**, per §4.4, and
   emitted by `dataset_row.py` from the run's own artefacts. Provenance recorded
   at write time, not retrofitted.
3. **The ONERA M6 validation validates the solver configuration and the
   convergence gate, not the mesher.** No public experimental case is an AERIS
   BWB. Both halves of that sentence are to be reported together.
4. **The far-field sensitivity run** (§2.2, `farfield_chords` 40 → 60 at `gci_C`,
   α = 0) is run, because the family refines the near body systematically and
   the far field only weakly, and one cheap run makes that defensible.

## Consequences

- S8 can select a campaign level and can quote how far its outputs moved under
  one refinement step. It cannot quote a GCI band.
- Every artefact that reports the refinement study carries the two-level
  limitation in the artefact itself, not only in this ADR.
- `round_c_lhs10_seed42` stays locked. No family freeze. No paper claim.
