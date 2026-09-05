# S8 — status, continuation, and exact next steps

**Last updated:** 2026-09-05, end of session · **Read this first** if you are
picking S8 up cold. The full technical account is `AUDIT_2026-09-05.md`; the
desktop commands are `HANDOFF_desktop.md`; this file is what to *do*.

---

## 1. Status in one table

| | state |
|---|---|
| topology | O-H, 3 volume blocks, 2 surface blocks, no collars |
| design-space meshing | **100/100 build, 100/100 valid** at `gci_C`, default path |
| fine-level meshing | index 83 clean at all 4 levels; index 65 at 3; a 51-design `gci_F` screen was clean when stopped |
| determinism (ADR-0011 §6.1) | **PASSES** — `o_wing` identical on all 100 |
| CFD | 4 angles on index 83 at `gci_C`, 3 converged, 1 solver-frozen |
| AVL cross-check | CL agrees to 1.9 % at alpha 8; neutral point to 3.7 % of MAC |
| grid convergence | **not started** — this is the next real deliverable |
| experimental validation | none |
| ready for a design-space campaign | **not yet** — see §4 |

**The headline of this session:** the fold defect that failed 15 of 100 designs
is fixed. Cause was a marching plane best-fitted to each section by SVD, sitting
up to 8 degrees off square-to-span; the far-field blend could not remove that
tilt before a 40 m radius amplified it into a ~2 m spanwise excursion against
4 cm cells. Forcing the plane square to the span removes the tilt at source.

---

## 2. The fold fix is in, and it is the default

`FRAME_MODE_DEFAULT = "span_normal"` in `march_o.py`, and the same in
`build_volume.py` and `robustness_screen.py`. The old behaviour stays selectable
as `--frame-mode svd`, and the pre-fix tree is tagged `s8-svd-frame-baseline`.

**What the fix is.** The marching plane was best-fitted to each section ring by
SVD. On a swept, tapered, twisted section that plane sits up to 8 degrees off
square-to-span, and the far-field blend could not remove the tilt before a 40 m
radius amplified it into a ~2 m spanwise excursion against 4 cm cells.
Neighbouring rings interleaved, spanwise edges reversed, 15 of 100 designs
folded. The plane is now square to the span by construction.

**And the correction to that fix, which matters as much.** The march works in
2-D in-plane coordinates, so the wall layer it produces is the ring PROJECTED
onto the marching plane. With the SVD frame that cost nothing; with a
span-normal plane it moved the wing surface by up to 1.194e-03 m — the same
order as the 1.0 mm blunt trailing edge. Every node now keeps its own
out-of-plane displacement, decayed to zero by the far field, so eta 0 is the
exact loft and the far field is a clean cylinder.

| | folds | wall vs exact loft |
|---|---|---|
| `svd` (old default) | 645 on index 65 | 7.296e-06 m |
| `span_normal`, projected | 0 | **1.194e-03 m** — deformed the wing |
| `span_normal` + offset restored | **0** | **2.220e-16 m** |

**Verified:** 100/100 designs build with zero inverted cells (11.0 min); index 83
clean at all four ladder levels and index 65 at three; the grid family untouched
(LE 1.310/1.286/1.335, TE 1.300/1.308/1.298, s0 1.298/1.299/1.300, global r_h
1.2512/1.2590/1.2664, identical to the baseline).

**A guard now enforces it.** `build_volume` asserts the wall layer IS the
surface ring to 1e-9 m and records the measured error in every summary. It
exists because defect 21 was silent: wall orthogonality, first-cell height,
scaled Jacobian and inverted-cell count were ALL unchanged while the wing moved
1.2 mm. Quality metrics do not check position.

## 3. Exact next steps

### Step 1 — DONE. The fold fix is validated and is the default.

```bash
# check the fine screen that was running
.venv/bin/python -c "
import json; d=json.load(open('AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_robustness_screen_gciF.json'))
b=[x for x in d['records'] if x.get('built')]
print(len(d['records']),'attempted |',len(b),'built |',sum(1 for x in b if x['negative_cells']==0),'clean')
print('folding:',[x['index'] for x in b if x['negative_cells']>0] or 'none')"
```

**If 100/100 clean at `gci_F`:** flip the default. In `march_o.py` set
`FRAME_MODE_DEFAULT = "span_normal"`, and in `build_volume.py` change the
`--frame-mode` default to match. Then re-run the coarse screen once with no flag
to confirm the default path gives 100/100, and commit.

**If any design still folds at `gci_F`:** do NOT flip the default. Record which
designs and at which level, and treat it as the same investigation — the
mechanism is understood, so a residual failure is a new sub-case, not a mystery.

Also worth running once the default is flipped:

```bash
# spot-check the finest level on the designs that used to fail worst
for i in 65 23 16 13 2; do
  .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/build_volume.py \
    --level gci_FF --index $i --frame-mode span_normal \
    --out $(pwd)/AERIS_MESH_STUDY/artifacts/s8_ff_check --no-plot3d | grep folded
done
```

### Step 2 — rebuild the GCI family and re-run the alpha 0 point

The frame change moves every cell, so **the four-angle sweep on index 83 was run
on meshes that no longer exist**. Before any grid convergence:

```bash
R=$(pwd)
for L in gci_C gci_M; do
  .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/build_volume.py \
    --level $L --index 83 --frame-mode span_normal \
    --out $R/AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh
  /home/mike/miniconda3/envs/mach-aero/bin/python \
    AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/write_cgns.py \
    --blocks $R/AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/${L}_blocks.npz
done

# alpha 0 on the rebuilt gci_C -- the regression check
/home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
  /home/mike/miniconda3/envs/mach-aero/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py \
  --grid $R/AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/gci_C_volume.cgns \
  --alpha 0.0 --out $R/AERIS_MESH_STUDY/artifacts/s8_cfd/sn_gci_C_a0 \
  --i-have-authorization
```

**Compare against the pre-fix values.** The frame change should barely move the
forces — it changes the far field, not the wing — so a large shift means
something else changed and the sweep should stop:

| | pre-fix, `oh_L3` |
|---|---|
| CL | −0.159963 |
| CD | 0.020838 |
| CDp | 0.011841 |
| CDv | 0.008996 |
| CMy | +0.001280 |

A shift in the third or fourth decimal of CD is the mesh. A shift in the second
is a problem.

### Step 3 — grid convergence

Three levels is a valid GCI; the fourth is optional confirmation of asymptotic
behaviour and is not worth 44.6 GiB on its own.

```bash
for L in gci_C gci_M; do
  for A in 0 4 8; do
    /home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
      /home/mike/miniconda3/envs/mach-aero/bin/python \
      AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py \
      --grid $R/AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/${L}_volume.cgns \
      --alpha $A --out $R/AERIS_MESH_STUDY/artifacts/s8_cfd/${L}_a${A} \
      --i-have-authorization
  done
done
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/convergence_gate.py \
  --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a*'
```

`gci_F` needs ~21 GiB and does not fit a 16 GB host — that level is the only part
that genuinely needs a bigger machine.

**Four things this study must respect:**

1. **Use the GLOBAL refinement ratio, not 1.300.** `o_wing` refines at 1.30 in
   all three directions, but `o_out`/`cap_out` do not refine spanwise (their
   count follows a far-field growth law: 47, 48, 49, 50). The characteristic
   ratios are **1.2512, 1.2590, 1.2664** and those are what Richardson gets. The
   per-block table is in `AUDIT_2026-09-05.md` §6.
2. **Exclude any `ACCEPTED_SOLVER_FROZEN` point from Richardson.** A GCI needs
   iterative error much smaller than discretization error, and a solver taking
   null steps gives no bound on iterative error at all.
3. **New authorization required.** `POLICY.yaml`'s `run-s8-corrected-sweep`
   exception covers `oh_L3` only. Grid convergence on other levels needs its own
   entry.
4. **`artifacts/` is globally gitignored and gets wiped.** Anything worth keeping
   goes in `05_s6_cfd_qualification/`; images need `git add -f`.

### Step 4 — pilot across geometries

5 to 10 diverse designs, full chain: mesh → CGNS → solve → gate → forces. This is
where cross-geometry problems appear that one design cannot show — solver stalls,
gate edge cases, y+ drift with planform.

### Step 5 — the campaign, and the multifidelity plan

The arithmetic that shapes it: meshing is 12 s per design, CFD is ~2 hours for a
four-angle polar. **100 designs is ~8 days of continuous solving; 1000 is ~80.**

So the campaign is not "RANS on 1000 wings". It is:

- RANS on **100–200** well-chosen designs,
- used to **correct AVL + NeuralFoil**, which AERIS already has,
- the cheap method run across the full set.

The AVL cross-check is the evidence this works: 1.9 % on CL at alpha 8 and 3.7 %
of MAC on neutral point, at seconds per case against 30 minutes.

**Dataset schema — decide before the first campaign case runs.** Every row
carries: geometry index, mesher and frame mode, grid level, convergence gate
verdict, relative residual, force-tail spreads, and the freestream-direction
verification block. Retrofitting provenance is much harder than recording it.

---

## 4. Why S8 is not yet ready for a campaign

Not because of meshing — that gate is now passed. Because:

1. **Nothing is grid-converged.** CDp moved 5.2 % and CMy 18 % from a single
   respacing. No drag or moment figure may be quoted, including the neutral
   point, which is a design output.
2. **The alpha 4 Newton–Krylov stall is undiagnosed.** Residual frozen at
   5.2371905e-05 to eight significant figures, NK step length 0.00, linear
   residual 1.000. **Not a mesh problem** — zero inverted cells, forces settled
   to 9.2e-09. Untested candidates: the tip-cap cell at scaled Jacobian 0.049,
   and a cell-volume span of ~1e15 across the domain.
3. **Leading-edge resolution is operating-point dependent.** Over-bound cp cells
   go from 3 at cruise to 36 at alpha 8. The level definitions treat resolution
   as a property of the mesh; it is not. The GCI will test whether refinement
   clears it — if 36 → 12 → 3, it is discretization.

A fallback mesher is **insurance, not infrastructure**, now that meshing is
100/100. If one is ever built, use **deformation from a validated S8 mesh**, not
S6: S6 carries the leading-edge collar defect S8 exists to fix, and 15 % of a
dataset built on it would have contaminated drag on exactly the hard geometries.
Whatever the fallback, run both paths on ~10 designs where both work and measure
the systematic offset before either enters a dataset.

---

## 5. Defects fixed this session

| # | defect | how it was found |
|---|---|---|
| 14 | `liftIndex` omitted; alpha applied as **sideslip** on a span-+y mesh. Every S8 CFD result void. | alpha 8 reported cp_max 0.0072 — impossible at incidence |
| 15 | leading-edge spacing stepped **2.6×** between adjacent stations, invisible to the turning metric | reading per-station spacing off the delivered mesh |
| 16 | convergence readback read a non-existent attribute; a converged run recorded as failed | the gate rejected a run that had reached 9.14e-9 |
| 17 | the CFD-vs-AVL stability "disagreement" was **two sign errors of the assistant's own** | the PI noticed the two Cm curves were mirror images |
| 18 | `build_volume` built an entire S6 surface to read the loft off it, inheriting S6's constraints | the 100-design screen died on its first design |
| 19 | the fold check was **in-plane per section**, so folds between sections were invisible; builds shipped invalid grids and exited 0 | 645 folded hexes with a clean 2-D check at every section |
| 20 | the marching plane was SVD-fitted, tilting up to 8 deg off span; the far-field blend could not remove it in time | 643 spanwise edges running backwards in y |

Four hypotheses and one repair were tested and **refuted** on the way to 20, all
recorded in `AUDIT_2026-09-05.md` §3 so they are not retried.

---

## 6. Where everything lives

| | |
|---|---|
| full technical audit | `AUDIT_2026-09-05.md` |
| desktop commands | `HANDOFF_desktop.md` |
| governance | `00_governance/decisions/ADR-0018`, `ADR-0019` |
| reports | `05_s6_cfd_qualification/reports/s8_*.json` |
| figure | `05_s6_cfd_qualification/viz/s8_sweep_polars_20260905.png` |
| pre-fix baseline | git tag `s8-svd-frame-baseline` |

Hold-out `round_c_lhs10_seed42` remains locked and untouched.
