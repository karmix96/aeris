# ADR-0013 — S3 is scoped as a sweep experiment with a declared shared tip control

Date: 2026-08-15
Status: Accepted

Amends **ADR-0011 §4** (the independence line) for S3, and only for S3.
Does not amend it for S0, S1, S2, S4 or S5.

---

## 1. The problem

ADR-0011 §4 makes **tip closure per-strategy, written from scratch**. That rule
exists because Stage 02's S3, S4 and S5 all inherited S1's tip closure, so the
tournament compared one topology wearing four labels.

S3 cannot satisfy it. Its canonical section split has **five** corners — the leading
edge, the two blunt-trailing-edge base corners, and the two thickness maxima — while
a structured centre block needs four. Five constructions were built and measured:

| option | outcome |
|---|---|
| merge the fore/aft arcs | becomes S1's three-corner split |
| camber-line split into halves | both halves degenerate to triangles at the LE |
| six-corner ring, six collars | hexagonal centre — not structured |
| H-grid with ribs at the thickness maxima | nose region is a two-corner lens — not a quad |
| four-corner ring at {thickness maxima, base corners} | opposite arcs must pair, forcing 31 points on a 1.0 mm base: 33 um cells, min-cell/`s0` about 2.5, which explodes |

## 2. The underlying result, established three times independently

Capping a thin blunt-trailing-edge contour with structured quads requires an O-H ring
whose **opposite arcs carry equal point counts**. That constraint forces the nose
wrap and the blunt base to be the same size, and there are essentially two ways to
satisfy it on this section:

- **short nose wrap + short base**, LE inside the wrap, long chord arcs — **S1**;
- **narrow wraps at both ends**, corners on the contour at +/- `wrap_x`, two collars
  meeting at each shoulder — **S0**.

S3's feature set does not generate a third. This was reached from S0 (where the
one-block face failed), from S1 (where the LE arc was tied to the base count), and
again from S3. **Any tip closure S3 adopts is structurally S0's or S1's.**

## 3. What S3 actually claims

RUNBOOK §6 S3 is explicit, and it is not a claim about tip closure:

> "Connect one interval at a time instead of performing one uninterrupted root-tip
> extrusion... Enforce compatible node counts and exact first/last cell-size matching
> across interfaces. **This is expected to handle the segmented AERIS planform better
> than pure tip-to-root sweeping.**"

The hypothesis is the **spanwise sweep**. The tip is a confound.

## 4. Decision

**S3 runs as a controlled sweep experiment**: it holds the chordwise blocking and the
tip closure fixed at **S1's**, and varies only the spanwise law —

- S1: one tip-anchored geometric series over the whole span, growth-limited,
  sweeping straight through the planform breaks;
- S3: per-interval sweeps anchored **on** the breaks, with the paper's Eq. 5
  two-sided logarithmic layer law (Yu et al. §3.4) inside each interval.

Its results are reported as a **sweep comparison against S1**, never as an
independent sixth topology.

### Why this is not the Stage 02 failure repeating

Stage 02's collapse was that strategies **silently** shared a component, so a
comparison that looked like four topologies was one. Here the sharing is the point:
one variable is deliberately isolated and the shared component is declared in
advance, in the strategy's `STUDY.md`, in `status`, and in this ADR.

An undeclared shared component makes a comparison meaningless. A declared one makes
it a controlled experiment. The difference is whether the reader can tell.

## 5. Consequences

- **S3 is unranked as a topology.** It cannot win the tournament, because it is not
  offering an independent topology. ADR-0011 §6.3 ranks topologies.
- **S3 can still decide something real:** if the interval-anchored sweep beats S1's
  on the same surface, that result transfers to S1 — and to whichever topology wins —
  as a spanwise law. If it does not, RUNBOOK §6 S3's expectation is falsified, which
  is also worth knowing.
- **The amendment is strictly limited to S3.** S4 and S5 must still bring their own
  tip closures; if either hits the same wall, that is a separate decision and this
  ADR is not a precedent for waving it through.
- The structural result in §2 is added to `COMMON_BRIEF` as general knowledge, so S4
  and S5 meet it before spending effort rather than after.

## 6. Evidence

- `04_strategy_studies/S3_station_sweep/STUDY.md` §4, the five measured constructions
- `04_strategy_studies/S0_cap4/STUDY.md` §§4-6 and `S1_tip_first/STUDY.md` §3, the two
  independent derivations of the same constraint
- Yu et al. §3.4, Eqs. 5-6 — S3's spanwise law, implemented and verified
- RUNBOOK §6 S3; ADR-0011 §§4, 6.3
