# ADR-0014 — the volume gate for a strategy that does not march

Date: 2026-08-16
Status: Accepted

Amends **ADR-0011 §6.1** (the volume half of the hard gate) so that it can be
applied to a strategy that generates its volume directly. Written **before any S4
volume exists**, which is the only condition under which ADR-0011 §6 permits a gate
to be touched at all.

---

## 1. The problem

ADR-0011 §6.1's volume gate is phrased in terms of pyHyp's report:

| ADR-0011 §6.1 condition | where the number comes from |
|---|---|
| pyHyp status is `valid` | pyHyp's own status string |
| march completed | `"pyHyp done"` in the log (instrument bug 10) |
| inverted cells = 0 | pyHyp's volume audit |
| min volume > 0 | pyHyp's volume audit |
| min scaled quality > 0 | pyHyp's per-layer quality report |
| low/negative-quality layers = 0 | pyHyp's per-layer quality report |

RUNBOOK §6 S4 says, of S4: *"Generate the volume directly using TFI/elliptic/Poisson
methods; **do not require pyHyp for this candidate**."*

So S4 is required by the RUNBOOK to produce a volume that ADR-0011 §6.1 has no way
to score. Two of the six conditions (`status`, `march completed`) are statements
about a program S4 does not run, and two more (`min quality`, `low-quality layers`)
are reported per *marching layer*, a structure S4's volume does not have.

Left unresolved, this has exactly one outcome: S4's volume gets built, and then the
rule for scoring it gets chosen with the results already visible. That is the
failure ADR-0011 §6 exists to prevent, and it does not become acceptable because the
strategy in question was granted an exemption elsewhere.

## 2. What is actually being tested

Strip the tool out of the six conditions and three questions remain:

1. **Did the generator finish?** Every block it declared exists, at the declared
   dimensions, with no NaN or Inf.
2. **Is every cell a real cell?** No inverted hexahedra, and the smallest cell
   volume is strictly positive.
3. **Is the worst cell usable?** Minimum scaled quality strictly greater than zero,
   with no *region* of the mesh failing that.

Those questions are about the mesh. They are not about pyHyp. The gate is therefore
restated in terms of the mesh, and the pyHyp phrasing becomes one implementation of
it rather than the definition of it.

## 3. Decision

### 3.1 The restated volume gate

A strategy's volume passes when **all** of the following hold. Thresholds are
unchanged from ADR-0008/ADR-0011 §6.1 — only the source of each number moves.

| # | condition | pyHyp route (S0, S1, S3) | direct route (S4) |
|---|---|---|---|
| V1 | generation completed | `"pyHyp done"` in the log **and** status `valid` | every declared block returned at its declared shape; zero non-finite nodes |
| V2 | inverted cells = 0 | pyHyp volume audit | count of hexahedra with any negative corner Jacobian determinant |
| V3 | min cell volume > 0 | pyHyp volume audit | minimum hexahedral volume over every cell |
| V4 | min scaled quality > 0 | pyHyp per-layer report | minimum corner scaled Jacobian over every cell |
| V5 | no failing region | low/negative-quality layers = 0 | no *block* whose min scaled quality is ≤ 0 |

`0.30` remains a **ranking target and never a gate**, on both routes. That
distinction is the whole reason `shared/gates.py` exists as one file.

### 3.2 The metric is defined once, shared, and identical in kind

The hexahedral scaled Jacobian is added to `shared/volume_qc.py` as the single
authority for the direct route, mirroring `aeris.cfd.meshing.quality.scaled_jacobian`
for quads: at each of the 8 corners, the determinant of the three outgoing edge
vectors normalised by their lengths; the cell's value is the minimum over corners.
Cell volume is the sum of the five-tetrahedron decomposition of the hexahedron.

**Instrument bug 9 is the precedent.** A quality number computed a second way, for
one strategy's convenience, produced a false result (`-0.132`, "7 folded cells") on a
mesh that was fine. So `volume_qc.py` is written once, in `shared/`, under the same
rule as every other control module, and it is verified in §3.4 below rather than
trusted.

### 3.3 What this ADR does NOT do

- It does **not** relax any threshold. Every number in §3.1 is the ADR-0008 number.
- It does **not** exempt S4 from the surface half of ADR-0011 §6.1. S4's surface is
  scored by the same `surface_gate_checklist` as everyone else, including the
  fidelity condition, which is currently open for all strategies.
- It does **not** make S4's volume quality directly comparable to S1's *as a number*.
  See §4.

### 3.4 The equivalence is verified, not asserted

Before any S4 volume is scored, `shared/volume_qc.py` is run on a volume pyHyp has
already reported on — **S1's**, which passed 10/10 — and the two routes are compared.
If the in-house metric disagrees with pyHyp about S1's volume, the in-house metric is
wrong and S4 waits. This is a cheap check and it is mandatory.

## 4. The honest limit on comparing S4 with S1

pyHyp marches to a far-field. S4, per its implementation note, defers the far-field
("farfield extent must wait for the farfield independence study") and builds the
**near-field** volume: the boundary-layer blocks and the interior-field blocks
bounded by Type 3 control vertices.

So:

- **Validity (V1-V5) is comparable.** A mesh either has inverted cells or it does
  not, and the near field is where every strategy's inverted cells have appeared.
- **Minimum quality is comparable**, because on every march so far the worst cell has
  been in the near-wall region, which both routes contain.
- **Cell counts and total-mesh statistics are NOT comparable**, and any table that
  puts them side by side must say so on the same page.

This limit is recorded here so that it is a known property of the comparison rather
than a discovery made while writing the final report.

## 5. Consequences

- S4 can be scored, on frozen thresholds, decided before its results existed.
- `shared/gates.py` gains `volume_gate_checklist_direct`, alongside the existing
  pyHyp checklist rather than replacing it. Neither route can silently become the
  other.
- If S5 is ever built and also does not march, it inherits this route with no
  further decision.
- If the in-house metric fails the §3.4 equivalence check, **S4 is blocked**, and
  that is the correct outcome — an unverified instrument is how Stage 02 produced
  four wrong numbers.

## 6. Evidence

- RUNBOOK §6 S4 (the pyHyp exemption); ADR-0011 §6.1; ADR-0008 §3 (the thresholds)
- `COMMON_BRIEF.md` §5 items 9 and 10 — instrument bugs 9 and 10, the two precedents
  for §3.2 and for V1
- `04_strategy_studies/S4_analytic_multiblock/STUDY.md` §4
- `01_references/S4_analytic_multiblock_implementation_note.md` — the far-field defer
