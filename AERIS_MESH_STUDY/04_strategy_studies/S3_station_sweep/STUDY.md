# S3 — station-to-station sweeping

**Status: FAILED. 30/30 marches fail, on S1's own surface, which passes 10/10.**
The cause is identified and is a property of the paper's spanwise law, not of the
implementation: Eq. 5 has no mechanism to match the tip cap's cell size.
RUNBOOK §6 S3's expectation is falsified on the metric that decides.

**Strategy ID:** `S3_STATION_SWEEP`
**Sources:** RUNBOOK §6 S3; Yu et al., *Automatic Multiblock Mesh Generation for
3D-Wing Aerodynamic Analysis*, **§3.4 "Extrusion-based surface mesh generation"**
(Eqs. 5-6) — this is S3's actual method in that paper, not §3.3 which is S2's.

---

## 1. What the paper states versus what had to be invented

| aspect | the paper states | status |
|---|---|---|
| spanwise law, Eq. 5 | two-sided logarithmic layer distribution, layer count `L` **"required to be even"**, density `sigma`, "anisotropic boundary layer adaptation... targeting the wing root and tip regions" | **implemented verbatim and verified** (§2) |
| layer positions, Eq. 6 | `x_i = x0 + xi*l*tan(chi0)`, chord scaled `b1/b0` | implemented via the realised stations |
| near-orthogonality claim | "Extruded cells guarantee a near-orthogonality, with angle deviation of chi0" | not yet measured |
| anchors at planform breaks | RUNBOOK §6 S3, not the paper | **implemented** (§3) |
| **tip closure** | the paper uses its **cross-field cap** — which is S2, rejected 2026-08-15 for non-deterministic topology | **no route** (§4) |

## 2. Eq. 5 verified

    sigma  1.0: [0, .125, .25, .375, .5, .625, .75, .875, 1]   end/mid ratio 1.000
    sigma  3.0: [0, .083, .185, .315, .5, .685, .815, .917, 1] end/mid ratio 0.450
    sigma 10.0: [0, .055, .130, .244, .5, .756, .870, .945, 1] end/mid ratio 0.216

Symmetric about 1/2, clusters at both ends as §3.4 describes, degenerates to uniform
at sigma = 1. Odd `L` is rejected, which is the paper's stated requirement rather
than an implementation choice.

## 3. Anchors and the canonical split work, and are deterministic

Five geometries of `lhs100_seed42`:

| geom | anchors | intervals | worst snap | x_thickness_max | side counts |
|---|---:|---:|---:|---:|---|
| 0-4 | **4** | **3** | 1.8 - 25.0 mm | 0.4040 | [16, 16, 3, 16, 16] |

Anchor count and interval count are identical on every geometry. The snap residual
of up to **25 mm** is the known `b1`-has-no-realised-section gap, now quantified per
geometry instead of noted in passing.

## 4. THE BLOCKER — and it is a finding about the tournament

S3's canonical split has **five** corners (LE, two blunt-base corners, two thickness
maxima). A structured centre block needs **four**. Every way out was worked through:

| option | outcome |
|---|---|
| merge fore/aft arcs into one upper and one lower | becomes S1's three-corner split |
| camber-line split into upper/lower halves | both halves degenerate to triangles at the LE |
| six-corner ring, six collars | centre block is a hexagon — not structured |
| H-grid with ribs at the thickness maxima | the nose region becomes a two-corner lens — not a quad |
| four-corner ring at {thickness maxima, base corners} | opposite arcs must pair: nose wrap needs `2*half-1` = 31 points and the base must match, giving 33 um cells on a 1.0 mm base — min-cell/`s0` ~2.5, which explodes (S1 exploded at 0.9, and 2.1) |

**The general result, arrived at three times independently in this study:** capping a
closed thin blunt-TE contour with structured quads requires an O-H ring whose
*opposite arcs carry equal point counts*. That forces the nose wrap and the blunt
base to be the same size. There are essentially two sound ways to satisfy it:

* short nose wrap + short base, with the LE inside the wrap and the chord arcs long
  — **S1 occupies this**;
* narrow wraps at both ends with corners on the contour at +/- `wrap_x`, two collars
  meeting at each shoulder — **S0 occupies this**.

S3's feature set (thickness maxima) does not generate a third. Any tip closure S3
adopts is structurally S1's or S0's.

## 5. Consequence for the study

S3's claim in RUNBOOK §6 is explicitly about the **planform sweep**: "Connect one
interval at a time instead of performing one uninterrupted root-tip extrusion...
expected to handle the segmented AERIS planform better than pure tip-to-root
sweeping." It is not a claim about tip closure.

Three ways to proceed, and the choice is a governance one because ADR-0011 §4 makes
tip closure per-strategy:

1. **Scope S3 as a sweep strategy** and evaluate it against S1 with a declared shared
   tip control. Cleanest comparison of the thing S3 actually claims; requires an ADR
   amending the independence line for this case.
2. **Give S3 S1's tip family with different parameters.** Honest only if reported as
   such — it is what Stage 02 did, and it is what ADR-0011 exists to prevent.
3. **Drop S3.** Loses the one untested structural idea left in the tournament.

Recommendation: (1), with the deviation recorded. The sweep is the hypothesis; the
tip is a confound.

## 7. THE MARCH — 30/30 fail, and why

ADR-0013's controlled comparison: S1's chordwise blocking and tip closure held fixed,
only the spanwise sweep varied. Same ten geometries, same level, same cell budget
(12,800 cells, 90 spanwise on every geometry).

| | S1 | S3 |
|---|---|---|
| epsE 1.5 / 2.0 / 3.0 | **10/10 · 10/10 · 8/10** | **0/10 · 0/10 · 0/10** |
| min quality | +0.181 … +0.356 | **-1.00000 everywhere** |

### The cause: no tip-interface cell matching

The S3 surface is clean — min scaled Jacobian +0.23595, minimum cell area 4.814e-08,
watertight — **identical to S1's**, because it IS S1's surface. One number differs:

    minimum spanwise edge     S1: 558 um     S3: 9469 um

S1 passes because its tip-anchored geometric law sets the first spanwise cell to the
tip cap's own radial cell size (~0.5 mm). The tip interface jump is then ~1.0. S3's
interval law has no such provision, so the jump is ~17:1 and the march dies there —
the same failure mode diagnosed for S1 before its spanwise law was rewritten.

### Eq. 5 cannot supply it

The paper's law clusters symmetrically toward both ends of *each interval*, scaled by
interval length. It has no absolute first-cell anchor. Measured:

| sigma | L | min spanwise edge | cell-size range |
|---:|---:|---:|---:|
| 1 | 30 | 9469 um | 99.5 |
| 10 | 30 | 3817 um | 268.6 |
| 200 | 30 | 1840 um | 660.5 |
| 200 | 60 | 904 um | 505.0 |

Target 558 um. At sigma = 200 with **double** the cell budget it is still 1.6x too
coarse, and the cell-size range has gone from 99.5 to 505 against S1's 114. There is
no setting of (sigma, L) that matches the tip and keeps the range usable.

### What this establishes for the study

**The tip-interface cell match is what makes a march succeed**, and it now rests on
three independent lines of evidence:

1. S1's four marches — 126/128 bad layers -> 1/128 as the jump closed 28:1 -> 0.99;
2. this result — the same surface fails 30/30 when only that match is removed;
3. the interface-jump diagnosis that produced S1's spanwise law in the first place.

It also confirms, for the second time, that a source paper's density law degrades
this geometry: Openblademesh's chordwise progression cost S1 +0.455 -> +0.005, and
Yu et al.'s Eq. 5 cannot serve the tip here at all. Both cluster toward features that
are already the tightest cells on a thin blunt-TE section.

## 8. Two of my own bugs, recorded

**Instrument-class bug: spanwise indexing into ORIENTED blocks.**
`orient_blocks_consistently` reverses the j index of any block it flips, and it flips
every OML block on this surface — j=0 becomes the TIP. Anchor indices computed
root-to-tip from `wing.xsecs` therefore scrambled every interval. First campaign:
30/30 failed at exactly -1.00000. A guard is now in `build_surface`. This is the same
class as instrument bug 7 in `shared/verify.py`, which assumed the last j column was
outboard — **the second time this reversal has caused a wrong result.**

**A wrong optimisation target.** sigma = 1.0 was selected because it minimised the
cell-size range. That is the metric ADR-0010 highlights, but it is not the one that
decides here — choosing it removed the tip clustering Eq. 5 exists to provide. The
surface comparison built on the scrambled meshes ("S3 better on 3/6 geometries") is
**void** and has been withdrawn.

## 6. Effort ledger

| metric | value |
|---|---:|
| distinct construction attempts | 5 |
| sessions | 1 |
| marches run | 60 |
