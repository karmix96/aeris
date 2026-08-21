# ADR-0009 — S2 Cross-Field Tip: Formal Deferral

Date: 2026-08-13
Status: **SUPERSEDED by ADR-0012 (2026-08-15)**

> **Superseded.** Both grounds for the deferral are falsified.
>
> 1. This ADR states the quad-layout-to-structured-block step "does not exist".
>    **It is printed in the source paper as Algorithm 2** ("Multiblock extraction
>    algorithm", p. 157): trace separatrices from singularities to mark domain
>    borders, then breadth-first flood-fill the quads between them. About forty
>    lines of array code, needing only numpy.
> 2. This ADR states there is "no concrete route" from the available tooling.
>    **gmsh 4.15.2 — installed throughout — provides `Mesh.Algorithm = 11`, a
>    cross-field-driven quasi-structured quad mesher**, which is the component that
>    was actually missing. Verified 2026-08-15.
>
> The observation that the paper's own minimum volume hex scaled Jacobian was
> 0.0539 stands, but it is an argument about how S2 will RANK, not whether it can
> be BUILT — and ADR-0011 §6.3 makes 0.30 a ranking target, never a gate.

## Context

S2 is the cross-field tip strategy from *Automatic Multiblock Mesh Generation for
3D-Wing Aerodynamic Analysis*. It has been listed as "blocked on dependencies"
since Stage 00, with `igl / QEx / meshio / shapely` recorded as unavailable.

That framing was lazy. The four are not equally hard: `meshio` and `shapely` are
ordinary pip installs. The real question is not whether packages can be installed
but whether the method produces something this study can use.

## The question that actually matters

> Does a cross-field / quad-extraction tip layout map to **structured multiblock**
> blocks that pyHyp can march and that CGNS can carry with per-block families?

Assessed on paper, before installing anything:

**The method's output is a quad-dominant unstructured patch layout**, produced by
tracing a cross-field and extracting quads around singularities. Its natural
product is a quad *mesh* with irregular vertices, not a small set of structured
logically-rectangular blocks.

**pyHyp requires structured multiblock input.** Every block must be a logically
rectangular (ni x nj) patch with conformal interfaces. Converting a cross-field
quad layout into that form means identifying separatrices, cutting the patch into
four-sided regions along them, and enforcing compatible point counts around every
irregular vertex. That is a substantial piece of work — a quad-layout-to-block-
decomposition step — and it is *not* supplied by any of the listed packages.
`igl` and `QEx` would give the cross-field and the quad extraction; the structured
decomposition afterwards is the part that does not exist.

**The paper's own volume result argues against urgency.** RUNBOOK §1 records that
its minimum volume hex scaled Jacobian was **0.0539** — an order of magnitude
below the 0.30 ranking target this study uses, and barely above the `> 0` hard
gate. The method's advertised strength is surface appearance in the tip; its
weakness is exactly the volume quality this study selects on.

**There is no concrete route** from the available tooling to a pyHyp-marchable
structured multiblock tip within Stage 02's scope.

## Decision

**S2 is formally deferred**, not blocked pending an install.

Installing four packages to complete a six-item list would be box-ticking: it
would produce a cross-field, and then leave the actual gap — quad layout to
structured blocks — untouched.

If S2 is revived it is scoped as its own task with its own budget, whose first
deliverable is the decomposition step, not the cross-field.

## Consequence — the tournament resolves to one topology

This must be stated plainly rather than left implicit behind a table of green
rows. After Stage 02:

| strategy | outcome |
| --- | --- |
| S0 cap4 | **failed** the volume gate (ADR-0006) |
| S1 tip-first sweep | surface-valid; the reference candidate |
| S2 cross-field tip | **deferred** — no route to structured multiblock (this ADR) |
| S3 station sweep | surface-valid; **same OML and tip closure as S1**, differing only in spanwise block splitting |
| S4 analytic multiblock | **bit-identical to S1** on all ten geometries (zero coordinate difference) — one candidate, two derivations |
| S5 RBF + reprojection | S1's layout with RBF confined to the tip-cap interior; pure frozen transfer failed fidelity by 250-350x |

**The six-strategy tournament has resolved to essentially one surviving surface
topology**, reached by several derivations, with S3 as the only genuine structural
variant (spanwise splitting) and S5 as a deformation technique layered on top.

This is a defensible finding, not a failure of the tournament. It is what the
evidence says: the corner-on-features section blocking plus the camber-split
rectangle tip closure is the construction that works for this geometry family, and
independent derivations converge on it. It also means the Round A/B/C structure in
the runbook — which assumes several genuinely distinct candidates — needs
re-scoping before Stage 03, and that re-scoping should be an explicit decision
rather than a silent narrowing.

**None of this is settled until the volume march.** Every strategy above is
surface-valid only. cap4 was surface-valid too.
