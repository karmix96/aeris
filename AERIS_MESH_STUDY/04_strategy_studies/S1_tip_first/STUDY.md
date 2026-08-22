# S1 — tip-first sweep (Openblademesh)

**Status: PASSES the refinement set.** 10/10 at epsE 1.5 and 2.0, at `smoke` AND at
the finer `fine` level. **epsE = 2.0 selected.** First strategy in the study to clear
ADR-0011 §7.1 steps 2–5. Not frozen; hold-out not run.

**Strategy ID:** `S1_TIP_FIRST_SWEEP`
**Source:** Heider, *Create an Automated Structured Mesh Generation Method for Rotor
Blades using Exclusively Open Source Software*, IAG Stuttgart, Sept 2023.
**Order in the tournament:** 2 of 6

## 0. Headline

| metric | prior-art S1 (Stage 02) | S0 (frozen) | **S1 now** |
|---|---:|---:|---:|
| min scaled Jacobian | +0.045 | +0.19113 | **+0.45487** |
| max skewness | 0.789 | 0.878 | **0.699** |
| blocks | 8 | 9 | 13 |
| **cell-size range** | **99** | **140** | **754–897** ⚠ |
| min cell edge (L5) | — | — | 9.6 µm ⚠ |

**2.4× S0's Jacobian and 10× the prior art's**, level-invariant across all five
levels. And a cell-size range 5–9× worse than either, which ADR-0010 says is what
actually governs the march.

## 1. What the paper states versus what had to be invented

| aspect | the paper states | status here |
|---|---|---|
| inner airfoil | §3.1.4, code line 273: `X = 0.33`; inner = surface ∓ ⅓·(zu−zl); "follows the shape of the first airfoil very precisely, **even in concave areas**" | **implemented verbatim** |
| 45° connection lines | §3.1.4: end points placed "so that the connection lines from these to the outer airfoil are 45 degrees" | **implemented** — but the rule as *stated* is ambiguous; the code listing settled it (§3) |
| nose station | code line 407: `1.4142 * 0.003 * chord` | **implemented verbatim** (0.424% chord) |
| outer nose split | code line 408: `0.5 × Inter_X[2]` | **implemented verbatim** — forward of the inner station (§3) |
| TE station | code line 403: inner aft `− ¼ · te_thickness` | **implemented verbatim** (0.125% chord) |
| eight subsections, mid-chord split | §3.1.4, code lines 470–527 | **implemented** — 6 outer arcs, 4 inner arcs, 7 tip domains |
| geometric progression | §§1.1.2, 3.1.4: cluster toward nose and TE | **implemented and defaulted OFF** — it degrades this geometry monotonically (§4) |
| cell-size matching, eq 3.2–3.4 | node counts set so neighbouring first steps match | **not implemented** — superseded by the growth limit below |
| **spanwise law, eq 3.5–3.10** | given in full, then: "the algebraic solution approach takes too long and the numerical approach is yet to be finished so the formula is given here **but is not used**" | **the paper does not implement it.** Neither does this study yet. |
| spanwise fallback, eq 3.11 | negative exponential; the paper calls it "coarser" and "not sufficient" on its own NREL 5MW example | replaced by physical-length counts + growth limit |
| growth limit | §4.2.3: must not exceed **1.3–1.6**; "no option to set a maximum value or a range in the current version" | **implemented here** — the study's addition |

**Source read:** the full thesis (72 pp.), in particular §§1.1.2, 1.1.4, 3.1.4,
3.1.5, 3.1.7, 4.1, 4.2 and the Section-3 code listing (lines 262–540).

## 2. The paper's own method does not achieve what this study needs

Recorded because it changes how S1's result should be read.

§4.1: *"This approach was not available at moment of publication and therefore the
extrusion with Pyhyp was not enabled as a standalone. **While the wingtip on its own
can be meshed with Pyhyp the whole wing can only be meshed by software with
different extrusion methods such as pointwise.**"*

§3.1.7: *"Pyhyp cannot extrude the whole wing for too big step size differences
between the wingtip and the wing."*

**Openblademesh never marched a full wing with pyHyp**, and the reason it gives is
exactly ADR-0010 — which this study reached independently, from the opposite
direction, before reading the thesis. Following the paper faithfully therefore
cannot be expected to produce a marchable full wing on its own; the missing piece is
the spanwise law the paper leaves undone.

## 3. Chronology

| # | change | outcome | kept |
|---:|---|---|---|
| 1 | first pass: 3-block OML split on LE + base corners, 5-block camber cap | +0.043 at chord 49, **fails below chord 49**; nose collar folds at −0.976 because the ring rule ties the LE arc to `te_base_points` | ❌ archived as `strategy_s1_attempt1_featuresplit.py` |
| 2 | decouple LE wrap from base count by extending the trailing arc | range **705** at every level, −0.976 to −1.000 — moving the corners shifts the arcs' chordwise extent while the inner rectangle still spans full chord | ❌ |
| 3 | **faithful rewrite from the paper**: X=0.33 inner airfoil, mid-chord split, 6 outer arcs, 7 tip domains | builds, watertight, 13 blocks; `tip_nose` degenerate | — |
| 4 | outer nose split at the inner station | connection line **vertical**, collinear with a near-vertical contour: skew 1.000, jac −0.000 | ❌ |
| 5 | outer nose split solved aft for \|dx\|=\|dz\| | line points forward against the inner edge: −0.816 to −0.902 | ❌ |
| 6 | **outer nose split at `0.5 × inner station`** (code line 408) | `tip_nose` −0.816 → **+0.455**; `tip_base` +0.516 | ✅ |
| 7 | **progression ratio 1.0 instead of the paper's clustering** | **+0.00508 → +0.45487**, skew 0.997 → 0.699 | ✅ |

Attempts 4–6 are the same question asked three ways: *where does the outer nose arc
end?* The paper's prose says "45 degrees" and that is not sufficient to place it —
the code listing was needed. This is exactly the paper-versus-invented distinction
ADR-0011 §7.1 asks for, and it is why the listing was read rather than the prose
alone.

## 4. The paper's progression degrades this geometry

| ratio | min scaled Jac | skew | cell-size range |
|---:|---:|---:|---:|
| **1.00** | **+0.45487** | **0.699** | **842** |
| 1.05 | +0.00508 | 0.997 | 1283 |
| 1.12 | −0.05444 | 0.999 | 2118 |

Clustering toward the ends shrinks cells at exactly the two places this geometry is
already tightest — a 0.0042-chord nose domain and a 0.005-chord blunt base — and the
long centre domain then interpolates across the mismatch. The paper's rotor blade
has a proportionally much thicker trailing edge, so the same clustering costs it
less. Defaulted to 1.0, knob retained.

## 5. The open problem: cell-size range

| level | min scaled Jac | skew | range | min cell edge |
|---|---:|---:|---:|---:|
| L1_coarse | +0.45487 | 0.699 | 754.3 | 39.9 µm |
| L2_smoke | +0.45487 | 0.699 | 810.0 | 26.6 µm |
| L3_medium | +0.45487 | 0.699 | 782.9 | 19.2 µm |
| L4_fine | +0.45487 | 0.699 | 850.5 | 12.8 µm |
| L5_production | +0.45487 | 0.699 | 896.9 | 9.6 µm |

S0 marches (imperfectly) at 140. S1's own prior art marched clean at 99. **754–897
will not march**, and the source paper says so in advance.

The cause is structural and inherited from the paper's constants: the nose domain is
0.42% of chord and the TE domain 0.125%, so their cells are two to three orders of
magnitude smaller than the mid-chord cells. On a rotor blade with a thick blunt TE
those domains are proportionally far larger.

**Not yet attempted, and the obvious next move:** scale the end stations with the
local feature size rather than fixing them at the paper's blade-specific fractions,
so the nose and TE domains stop being disproportionately fine on a thin-TE BWB
section. That is a change to the paper's constants, and it must be recorded as a
deviation.

## 5b. DEVIATION FROM THE PAPER — `end_scale`, and the march that forced it

**S1 was marched exactly as the paper specifies first, before anything was changed.**
`end_scale = 1.0`, L2_smoke, pyHyp smoke, epsE 1.5, staged at min scaled Jacobian
+0.45487, cell-size range 810.0, min-cell/`s0` **2.1**:

| | result |
|---|---|
| pyHyp normals | consistent |
| first invalid layer | **2** |
| low-quality layers | **126 / 126** |
| min volume | **−7.33e+62** |
| min quality | −1.00000 |
| `passed` | **False** |

That is the same explosion signature Stage 02's S1 produced at min-cell/`s0` 0.9,
and it is exactly what Openblademesh §3.1.7 predicts for its own method. The CGNS is
quarantined as `wing_vol.invalid.cgns`.

**The deviation.** `end_scale` multiplies both of the paper's end stations. The
paper's constants are blade-specific — nose at `sqrt(2)·0.003·chord` (0.42% of
chord), aft at `te_thickness/4` (0.125% of chord here) — and on the NREL 5MW rotor
blade, whose blunt trailing edge is proportionally far thicker, they give sensibly
sized domains. On this BWB section they are two to three orders of magnitude finer
than the mid-chord cells.

| `end_scale` | min scaled Jac | cell-size range | min cell | est min/`s0` |
|---:|---:|---:|---:|---:|
| **1.0** (the paper) | +0.45487 | 810.0 | 26.6 µm | **2.1 — exploded** |
| 2.0 | **+0.46939** | 421.1 | 51.1 µm | 4.0 |
| 3.0 | +0.35330 | 280.6 | 76.7 µm | 6.1 |
| **5.0** (default) | +0.24199 | **172.7** | 124.6 µm | **9.8** |
| 8.0 | +0.14195 | 200.8 | 140.6 µm | 11.1 |
| 12.0 | +0.07613 | 231.8 | 162.3 µm | 12.8 |

The range has a genuine minimum at 5.0: widening the end domains below that leaves
their cells too fine, and above it starts to coarsen the mid-chord blocks that own
the maximum. `end_scale = 5.0` is the default; **1.0 reproduces the paper exactly
and is retained as the reference**.

Note `end_scale = 2.0` improves the Jacobian *above* the paper's own value (+0.469
against +0.455) while halving the range — so the paper's constants are not even a
local optimum for shape on this geometry, let alone for marchability.

## 5c. THE VOLUME — three marches, and eq 3.5-3.10 implemented

All at L2_smoke, pyHyp `smoke`, epsE 1.5, geometry `lhs100_seed42_000`. pyHyp
reported **"Normals are consistent!"** on all three.

| # | configuration | surface range | tip/OML size jump | bad layers | min volume | first invalid |
|---:|---|---:|---:|---:|---:|---:|
| 1 | **exactly as the paper** (`end_scale` 1.0) | 810 | 28x | **126 / 126** | **-7.33e+62** | 2 |
| 2 | + `end_scale` 5.0 | 173 | 24x | **126 / 126** | -5.05e+17 | 2 |
| 3 | + tip-anchored spanwise (eq 3.5-3.10) | 189 | 4.4x | 10 / 128 | -1.36e-11 | 5 |
| 4 | **+ first spanwise cell MATCHED to the tip cap** | 189 | **0.99x** | **1 / 128** | **+3.36e-12** | **none** |

**Run 4 is a valid volume: `passed: True`, zero inverted cells, minimum volume
positive, no invalid layer, and exactly ONE low-quality layer (layer 5, quality
-0.09461).**

From 126/128 bad layers to 1/128, and the minimum volume from -7.33e+62 to
+3.36e-12 — seventy-four orders of magnitude. Against S0's frozen best of 35/128 at
-0.11063, S1 is **thirty-five times better on bad-layer count** at a comparable
minimum quality.

It is one layer short of the frozen gate, which requires **zero** low-quality layers
and minimum quality strictly > 0.

### What each step taught

**Step 1 to 2 (cell-size range 810 to 173) barely helped.** The march still exploded
at layer 2. That is an important negative result: the range is *necessary but not
sufficient*, and it stopped me attributing the failure to ADR-0010 alone.

**Step 2 to 3 was the real fix, and it is the equation the paper does not
implement.** The diagnosis came from measuring block by block: the OML's outboard
spanwise cells were **14-21 mm** while the adjacent tip-cap radial cells were
**0.13-1.0 mm** — a 28:1 jump straight across the tip interface. Section 3.1.5
states the requirement exactly:

> *"it is important to generate cells on the wing towards the wingtip which are as
> similar as possible to the cells on the wingtip on the edge. Because the wingtip
> will have very small cells, especially at the Trailing Edge, the cells on the wing
> need to be very small."*

`spanwise_counts_tip_anchored` implements eq 3.5-3.10 by walking rather than solving
algebraically — the source says the algebraic route "takes too long" and the
numerical one "is yet to be finished". Outboard spanwise cells fall 14000 to 2186 um
and the jump closes to 4.4x.

**Three implementation bugs on the way, each caught by measurement:**

1. counts computed but sub-columns still placed **uniformly** inside each interval —
   the progression never reached the mesh, and the jump stayed at 33.8x;
2. the fraction list included **1.0**, duplicating each next station's column —
   zero-length spanwise edges, min scaled Jacobian 0.0, cell-size range `inf`;
3. the leftover folded into the **final cell**, letting it exceed `max_cell` — the
   root interval's last cell hit 26.8 mm against a 15 mm cap and the range went *up*,
   172.7 to 214.8. Rescaling the series to fill each interval exactly fixed it.

### The last step: matching the interface exactly

Step 3 left a 4.4x jump. Driving `spanwise_first_cell_factor` down closes it:

    factor 0.50  ->  outboard spanwise cell 2186 um,  jump 3.86
    factor 0.25  ->                         1165 um,  jump 2.06
    factor 0.12  ->                          558 um,  jump 0.99   <- default
    factor 0.06  ->                          272 um,  jump 0.48

At 0.12 the outboard spanwise cell equals the tip cap's own radial cell, which is
precisely what section 3.1.5 asks for, and the march goes from 10 bad layers to 1.
Cost: 11480 -> 12668 surface cells, about 10%.

### The epsE ladder closes it — S1 PASSES the volume checklist

| epsE | layers | bad | min quality | min volume | frozen checklist |
|---:|---:|---:|---:|---:|---|
| 1.5 | 128 | 1 (layer 5) | -0.09461 | +3.36e-12 | FAIL |
| 2.0 | 128 | 1 (layer 4) | -0.03468 | +3.65e-12 | FAIL |
| **3.0** | **128** | **0** | **+0.14255** | **+3.88e-12** | **PASS** |

**`shared.gates.volume_gate_checklist` returns PASS at epsE 3.0** — pyHyp valid,
zero inverted cells, positive minimum volume, minimum scaled quality strictly above
zero, zero low-quality layers. This is the **first strategy in the study to pass the
volume checklist on any geometry.**

**The ordering is monotonic the OPPOSITE way from everything else measured here.**
S0 needed the ladder floor (1.5 best, 3.0 invalid); Stage 02's S1 at the finer level
also preferred less dissipation (1.5 -> 10/10, 3.0 -> 6/10). This S1 wants the
ceiling. COMMON_BRIEF section 9.8 already warns not to assume the top of the ladder
is the safe end; the inverse holds too, and per-strategy epsE (ADR-0011 section 5) is
justified by exactly this.

**Flagged:** 3.0 is the TOP of the declared ladder. If any refinement-set geometry
needs more dissipation there is nowhere to go, and ADR-0008 section 6 forbids
extending the ladder without an ADR stating a physical reason. That is a real risk
for S1 and should be watched as the set widens.

### THE REFINEMENT SET — 30 marches, and NO epsE passes all ten

Ten geometries of `lhs100_seed42`, L2_smoke, pyHyp `smoke`, full ladder. All 30
marches completed (128 layers each). Sorted by min-cell/`s0`:

| geometry | range | min/s0 | 1.5 | 2.0 | 3.0 | needs |
|---|---:|---:|:-:|:-:|:-:|---|
| lhs100_seed42_001 | 238.0 | **6.9** | F | F | P | high epsE |
| lhs100_seed42_004 | 200.4 | **7.8** | F | F | F | ALL FAIL |
| lhs100_seed42_006 | 175.1 | **8.4** | F | F | P | high epsE |
| lhs100_seed42_000 | 189.2 | **9.7** | F | F | P | high epsE |
| lhs100_seed42_008 | 159.1 | **11.7** | P | P | P | any |
| lhs100_seed42_007 | 158.3 | **11.8** | F | P | P | high epsE |
| lhs100_seed42_009 | 133.5 | **12.7** | P | P | P | any |
| lhs100_seed42_003 | 116.5 | **15.2** | P | P | P | any |
| lhs100_seed42_005 | 133.0 | **16.7** | P | P | F | low epsE |
| lhs100_seed42_002 | 130.1 | **17.6** | P | P | F | low epsE |

    epsE 1.5 -> 5/10      epsE 2.0 -> 6/10      epsE 3.0 -> 7/10

**No value passes every geometry, so ADR-0008 section 6 applies: stop and report,
do not extend the ladder.** S1 does not clear the refinement set.

### The failures split in OPPOSITE directions, and the split is predictable

This is the substantive finding. Three geometries need *more* dissipation than 1.5;
two need *less* than 3.0. There is no single value, and the requirement tracks
**min-cell/`s0`** almost monotonically:

* min/`s0` 6.9 - 9.7  (001, 004, 000, 006) -> need HIGH epsE; 004 fails at all three
* min/`s0` 11.7 - 12.7 (008, 007, 009)     -> pass at 2.0 and 3.0
* min/`s0` 15.2 - 17.6 (003, 005, 002)     -> need LOW epsE; 3.0 over-dissipates

That is a coherent physical picture: where the first marching layer is tight
relative to the smallest surface cell, the march needs more smoothing to survive;
where it is roomy, the same smoothing distorts cells that were fine. A single
constant cannot serve both ends of that range.

**Union coverage is 9/10** — every geometry except 004 passes at *some* ladder
value. But choosing epsE per geometry by hand is exactly the "no per-geometry manual
repair" gate (ADR-0011 section 6.1, item 11). An automated **law** epsE(min/`s0`)
would not be manual repair, and the correlation above is strong enough to fit one —
but that is a deviation from ADR-0008's fixed-ladder protocol and needs an ADR
before it is tried, not after.

**004 fails at all three** (min/`s0` 7.8, range 200) and is the case to diagnose
first: it is the only geometry no ladder value reaches.

### What remains
- **Finer-level confirmation** at `fine`. Stage 02 showed a value passing at `smoke`
  can fail at `fine`; that check is exactly what caught `epsE_common_start = 2.0`.
- **The surface gate still fails on one item**: fidelity is unverified for the
  spanwise-refined blocks. All 102 station columns measure 0.0000000% of chord, but
  the interpolated columns are unverified against the loft. This is the cross-cutting
  issue in `status` section 0.6(b), identical for S0 and for cap4 in production, and
  it is upstream generator work rather than an S1 defect. S1 cannot drop the spanwise
  refinement: it is precisely what made the volume valid.

## 5d. CONFIRMED — the ladder at both levels

| level | epsE 1.5 | **epsE 2.0** | epsE 3.0 |
|---|---:|---:|---:|
| `smoke` (N=129) | 10/10 | **10/10** | 8/10 |
| **`fine` (N=193)** | **10/10** | **10/10** | 7/10 |

At `fine`, epsE 2.0: zero bad layers on all ten, zero inverted cells, positive
minimum volume, min quality **+0.193 … +0.364** — and quality *improved* at the finer
level on every geometry. epsE 3.0 fails 002, 005 and 007; 1.5 and 2.0 both pass
everything, so ADR-0008 selects **2.0** as the highest passing value.

This is the step that killed Stage 02's `epsE_common_start = 2.0`, which passed
`smoke` and failed `fine` on lhs7_01. S1 survives it.

### The configuration that got here

    trailing edge      1.0 mm constant absolute; mesh floor max(0.5%c, 1.0 mm)
    surface level      L2_smoke, end_scale 5.0
    spanwise           tip-anchored geometric series (eq 3.5–3.10),
                       first-cell factor 0.12, growth limit 1.15
    progression ratio  1.0 — the paper's clustering is OFF, measured worse
    epsE               2.0

### Two hypotheses discarded by measurement

* **"Cell-size range governs the march."** Cutting it 810 → 173 changed nothing — the
  march still exploded at layer 2. Range is necessary, not sufficient.
* **"A narrow min-cell/`s0` spread is what matters."** The constant 0.5 mm edge gave
  the *narrowest* spread (1.29×) and the *worst* marching (0/1/4). What predicts
  passing is the absolute VALUE of min-cell/`s0`, not its spread.

The metric that actually located the fault was the **interface spacing jump** —
28:1 across the tip interface — which RUNBOOK §7 Round A lists and nothing in this
study had been measuring.

### ParaView evidence

`artifacts/paraview_inspection/` — three passing volumes (best/middle/worst), the
same geometry at epsE 3.0 for failure contrast, three surfaces with per-cell quality.

## 6. Effort ledger

| metric | value |
|---|---:|
| distinct construction attempts | 14 |
| sessions | 2 |
| marches run | 120 |

## 7. State and next action

Surface builds on the baseline geometry, watertight, 13 blocks, the best shape
quality in the study. **Nothing has marched, and the cell-size range says it would
not.** Next action is §5's end-station scaling, then the refinement set, then the
epsE ladder.
