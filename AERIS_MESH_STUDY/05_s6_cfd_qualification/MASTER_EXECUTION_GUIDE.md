# AERIS S6 Automated CFD — Master Execution Guide

**Status date:** 30 August 2026  
**Execution constraint:** one desktop running WSL2; RAM, CPU and storage must be inventoried before the 16 GiB assumption is frozen  
**Flow authority:** the repository mission definition, after an explicit consistency audit  
**Validation scope:** NASA TMR NACA 0012 plus AERIS-specific verification and sensitivity studies  
**Primary pipeline:** pyGeo geometry → S6 structured surface → pyHyp volume → bounded atlas deformation/fallback → ADflow RANS-SA  
**Purpose:** finish the qualification work so that, after the desktop campaign, only writing Paper 1 remains.

### Non-destructive execution covenant

- No important source, codebase, mesh, result, report, restart or provenance record may be deleted, overwritten or silently pruned without Mike's explicit permission for the exact paths.
- Prohibit broad destructive commands and automatic cleanup in qualification tooling, including `rm -rf`, destructive Git reset/checkout, unresolved deletion globs and “delete old runs” policies.
- Every attempt—accepted, rejected, interrupted or superseded—remains addressable by an immutable attempt ID. A new run or classification creates a new artifact; it does not overwrite the previous one.
- Storage pressure terminates scheduling as `STORAGE_BLOCKED`. The system produces a path/size/hash/recoverability proposal and waits for explicit approval before archival relocation or deletion.
- Before material WSL/VHD relocation, resize or environment surgery, make and verify a recoverable backup/export when disk capacity permits. Never delete or replace an entire codebase.

---

## 0. Executive decision

### Honest status now

- [x] S6 is the strongest current meshing strategy and should remain the lead route.
- [x] Its fixed topology, exact-wall construction, atlas routing, bounded deformation, fallback, written-CGNS audit, hashing, cache and collection concepts are sound.
- [x] The 21-template **P0 candidate atlas** passed 100/100 development geometries in 162 attempts, with 74 first-pass routes.
- [x] Accepted P0 meshes had zero inverted cells; selected minimum/p05/median scaled quality was 0.146811/0.162193/0.219840.
- [x] Maximum wall, interface and surface-fidelity errors were approximately machine precision, 7.11e-15 m and 1.4322e-5 local chord respectively.
- [ ] S6 has **not** yet proved production CFD accuracy or unattended CFD reliability.
- [ ] P0 (`N=257` with smoke-level tangential resolution) is not a genuine production grid and must never be called G3.
- [ ] Three N65 ADflow cases converged by about 7.5–7.7 residual orders, but all three failed the present wall-y+ gate.
- [ ] The operating point, moment references, complete residual/conservation checks, physical trailing edge, farfield, all-direction grid family, model credibility and one-shot holdout are not yet qualified.

### The decisive reported-16-GiB consequence

- The former 2.3–3.5 million-cell P0 meshes are not an executable CFD route on this desktop.
- The desktop work must first prove a **coupled three-level grid family that both fits memory and resolves the required forces**.
- The recent `29 chord × 75 span × N97` result is only a candidate:
  - 9,508 surface quads;
  - `9,508 × (97−1) = 912,768` hexahedra;
  - forecast peak memory about 9.35 GiB;
  - reported available budget about 11.36 GiB.
- That gives only about 2 GiB operational headroom. It authorizes **one measured canary**, not a production claim.
- If M−1 confirms 16 GiB and the finest grid required by the uncertainty gate cannot run safely, the correct terminal state is `RESOURCE_BLOCKED_16GB`; otherwise report the actual host limit. Do not rename a coarse grid “production,” weaken the accuracy gate, or hide the limitation.

### What success means

S6 becomes trustworthy for automated fully turbulent RANS-SA labels only when all five claims are separately supported:

1. **Geometry correctness:** the intended BWB and declared trailing edge were meshed.
2. **Mesh validity:** every written volume is valid and independently re-audited.
3. **Iterative convergence:** every accepted solver result is finite, stable and conservative.
4. **Numerical verification:** grid, wall, trailing-edge and farfield uncertainty are controlled.
5. **Credibility/robustness:** the solver reproduces the TMR anchor and the frozen AERIS pipeline survives development plus untouched holdout cases without manual repair.

The existing atlas evidence establishes much of claim 2 at P0. It does not establish claims 3–5.

### Qualification operating scope: half aircraft

- The standard S6 research domain is the **right or left semi-span only**, with the aircraft center plane as an exact symmetry boundary.
- This is valid only for geometrically symmetric cases at `beta=0`, zero roll/yaw rates and neutral or symmetric control deflection. It represents the full aircraft physically; it does not turn `b_full` into a semi-span reference.
- A full-aircraft mesh is mandatory for sideslip, differential/asymmetric elevons, one-sided failures, roll/yaw-rate cases, asymmetric propulsion or any flow expected to break symmetry materially.
- Paper 1 qualifies the symmetric half-domain factory. Full-aircraft asymmetric automation is a separately versioned extension, not an untested implication of Paper 1.

---

# Part I — What the pipeline actually does

## 1. Geometry generation: one authoritative aircraft identity

### Current construction

- The live geometry authority is `configs/geometry/bwb.yaml`, parsed through `bwb_segmented_v1`.
- The neutral outer-mold-line family has stable semantic stations `b0`, `b1`, `b2`, `b3`, ordered from root/symmetry plane to physical tip.
- Stable entities include leading edge, trailing edge, root, tip, planform breaks and the symmetric trailing-edge elevon region.
- The current parser reports 20 active design-variable fields; `dihedral_b1_deg` remains in the schema but is pinned to zero by the flat-root-panel invariant.
- The current station airfoil sequence is `mh91 / mh91 / e374 / nlf1015` from `b0` to `b3`. Historical all-NACA4412 inputs are not production authority.
- pyGeo realizes upper and lower B-spline loft surfaces. S6 evaluates these surfaces directly at every requested span/chord parameter; it does not linearly interpolate a sparse set of realized sections.

One geometry is therefore produced in this order:

1. Parse and validate one design-variable vector against the live BWB ranges/invariants.
2. Construct the four span stations and their planform position, chord, twist and dihedral.
3. Place/transform the station airfoil sections while preserving their semantic roles.
4. Loft the upper and lower pyGeo B-spline surfaces through those sections.
5. Evaluate exact reference quantities and the physical OML.
6. Assign one immutable geometry identity from the input, implementation and output hashes.

The answer to the section question is **yes**: `b0…b3` are control/anchor sections of a continuous loft. Between them there are infinitely many distinct mathematical sections supplied by the upper/lower spline surfaces; S6 samples as many realized span sections as its mesh law requests. It is not the same four discrete airfoils copied unchanged across the span. The precise shape between anchors is the governed pyGeo/pySpline loft, so degree, knot vector, parameterization and generator version belong in the geometry hash.

### Final Phase-I AERIS geometry envelope

This is the geometry scope to freeze for S6 Paper 1 and the first AERIS high-fidelity data product. It deliberately describes one compact, low-subsonic, tailless BWB UAV family—not every possible BWB. Sweep, taper, twist and dihedral are legitimate coupled BWB design variables; however, trim, stability and tip-stall behavior must be evaluated as outputs, not assumed from the bounds.

| Quantity | Frozen Phase-I limit | Decision and defence |
|---|---:|---|
| Root chord `c1_m` | `0.70–1.10 m` | preserves the current rescaled AERIS product authority |
| Semi-span `b_total_m` | `0.75–1.25 m` | gives full span `1.50–2.50 m`; preserves the declared current small-UAV product scale |
| Station chord ratios | `c2/c1=0.45–0.65`, `c3/c1=0.30–0.45`, `c4/c1=0.08–0.20` | retains useful center-body/outer-wing taper authority while bounding the difficult tip |
| Segment sweeps `sw1/sw2/sw3` | `20–40° / 15–35° / 5–25°` | these are the confirmed current AERIS ranges; they explore strong inboard sweep and a progressively less swept outer planform without entering the old superseded airframe |
| Root/global geometric incidence | `0°` | angle of attack is a flow variable; freeing both creates an unidentifiable duplicate degree of freedom |
| Station twist | each active non-root station `−5°…+5°` | matches the already explored UAV-scale range and permits both washout and limited wash-in needed for trim/stability discovery |
| Twist coupling | adjacent station jump `≤5°`; realized tip-minus-root twist `−5°…+5°` | prevents a narrow span segment from hiding a 10° reversal while retaining the scientifically relevant range |
| Root-panel dihedral `dihedral_b1_deg` | exactly `0°` | preserves the existing center-plane/topology invariant and an exact symmetry surface |
| Next/outboard dihedral stations | intermediate `0–5°`; tip `0–10°` | admits lateral-stability authority while avoiding anhedral and extreme tip elevation in this compact product family |
| Dihedral coupling | non-decreasing root-to-tip; adjacent change `≤5°` | avoids an artificial gull-wing reversal and limits abrupt normal changes that are neither required by the product nor fair to a fixed-topology qualification |
| Station airfoils | fixed `mh91 / mh91 / e374 / nlf1015` | isolates planform/section-placement automation; airfoil-family optimization is a later design-space version |
| Neutral elevon region | span `0.60–0.95` semi-span; hinge at `0.75c`; deflection `0°` | keeps stable semantics and excludes deflected-CAD complexity from primary S6 qualification |
| Derived full-aircraft aspect ratio | `3.0≤AR≤7.0` | bounds the study around the compact BWB regime (current baseline about 4.13) and prevents span/chord corners from silently creating a different aircraft class |

Required coupled feasibility filters, applied before meshing:

- [ ] Positive, strictly decreasing station chords with at least `0.02 c1` between adjacent non-tip stations and at least `0.05 c1` between the last inboard station and tip.
- [ ] Physical tip chord `≥0.056 m`, matching the known current extreme; report tip thickness and trailing-edge manufacturability separately rather than inventing an unsupported structural limit.
- [ ] Positive panel lengths, ordered stations, no LE/TE crossing, no self-intersection, no negative local thickness and no center-plane gap/tangent discontinuity.
- [ ] Exact closed-form dihedral integration and continuous loft evaluation are station-count independent.
- [ ] Geometry validity is distinct from flight feasibility. Do **not** remove a geometrically valid design merely because low-fidelity analysis predicts poor trim, static margin or stall; retain that outcome as a product/DSE label.

The desktop must not copy this table blindly into code. Its first geometry job is to parse all 20 fields from the live `configs/geometry/bwb.yaml`, emit a semantic diff against this envelope, and ask for an ADR if a live name, meaning or bound differs. The values above then become `geometry_design_space_phase1_v1`; they remain frozen through M9.

This may change the meaning of the existing design space. If even one bound, coupling rule, loft implementation or active field differs from the live configuration, the desktop must:

1. preserve the old YAML and all old evidence as a named legacy version;
2. create a new config/hash rather than overwrite it;
3. regenerate and re-identify the development, calibration and locked holdout sets before they are used;
4. rebuild the final atlas in the new space; and
5. describe the existing P0 100/100 result only as legacy meshing evidence, not Phase-I coverage.

### Required geometry record for every case

- [ ] Stable geometry ID and design-set membership.
- [ ] All design variables in physical and normalized form.
- [ ] Geometry config hash, generator-source hash, pyGeo/pyspline versions and units.
- [ ] Full and half reference area, full span, MAC, root/tip chord and bounding-box diagonal.
- [ ] Exact station/airfoil assignment and neutral-control status.
- [ ] Physical OML hash and meshed-OML hash.
- [ ] Physical trailing-edge definition and numerical trailing-edge definition stored separately.
- [ ] Phase-I envelope version, all coupled-filter results and exact loft degree/knots/parameterization.
- [ ] A geometry build that fails any contract invariant terminates as `GEOMETRY_REJECTED`; it never reaches the mesher.

### Trailing-edge law

The current S6 surface uses

\[
t_{TE}(y)=\max\left(t_{abs},\;f_{TE}c(y)\right),
\]

with the present baseline `t_abs=1.0 mm` and `f_TE=0.005`. This is a declared **mesh-only numerical geometry**, not the physical CAD.

Required correction:

- [ ] Add an exact physical `1.0 mm absolute` option with the fractional floor disabled.
- [ ] Retain the current hybrid opening and larger/smaller numerical variants only as sensitivity cases.
- [ ] Never overwrite the physical OML with a numerical TE and then call the result exact CAD.

## 2. S6 surface mesh: fixed graph, moving coordinates

### Fixed topology

S6 reuses the successful S1/Openblademesh topology while replacing S1's span interpolation with exact pyGeo evaluation.

- Six OML blocks:
  - `oml_upper_aft`
  - `oml_upper_fore`
  - `oml_nose`
  - `oml_lower_fore`
  - `oml_lower_aft`
  - `oml_base`
- Seven tip-closing blocks generated by the S1 tip-domain construction.
- Total: 13 surface blocks and 20 paired internal edges.
- Connectivity and block semantics remain fixed; only coordinates and governed dimensions change.

### Point placement

- Each pyGeo section is sampled densely.
- The upper and lower curves are split at aft/fore/nose landmarks.
- Arc points are redistributed by curve length while their pyGeo parameters are retained.
- Every resulting OML node is independently re-evaluated on the declared pyGeo/TE surface at its recorded parameter.
- Span locations follow a fixed-count geometric distribution:
  - the first tip-adjacent span cell is tied to local tip chord;
  - cell width grows toward the root;
  - a maximum spanwise cell-size cap is enforced;
  - exact pyGeo sections are requested at every realized span position.

### Tip closure

- The exact tip section is projected into its local chord/thickness plane.
- The seven-block collar/end topology is created in this two-dimensional frame.
- Its outer edges are replaced with the exact OML tip arcs.
- The patches are mapped back to 3D and checked for planarity and conformity.
- `chord_points`, `end_points` and `collar_points` form one coupled family; they may not be tuned independently after a failure.

### Present resolution definitions — evidence, not the new production family

| Historical level | Chord points | End points | Collar points | Span cells | Role now |
|---|---:|---:|---:|---:|---|
| coarse | 25 | 3 | 5 | 63 | legacy candidate |
| smoke | 33 | 3 | 7 | 89 | topology/development evidence |
| medium | 49 | 4 | 9 | 127 | too expensive until measured |
| fine | 65 | 5 | 13 | 179 | too expensive for the assumed desktop |

These names must not become the new G1/G2/G3 automatically. The desktop-executable family is selected by mesh validity, refinement quality, measured memory and CFD uncertainty.

### Surface audit: blockers and policy classifications

- [ ] Exactly 13 expected blocks and 20 conformal internal edge pairs.
- [ ] Expected names, dimensions, boundary families and orientation.
- [ ] Maximum internal mismatch ≤ `1e-10 m`.
- [ ] Signed surface scaled Jacobian strictly `>0` everywhere.
- [ ] No duplicate, missing, non-finite or zero-area cells.
- [ ] Maximum independently measured OML/tip fidelity error ≤ `1e-4` local chord.
- [ ] The surface-report dimension signature exactly matches the requested settings.

Wrong topology/dimensions/identity, non-finite or zero-area cells, inconsistent orientation and a non-positive signed Jacobian are mathematical/identity blockers. The `1e-4` fidelity limit is a versioned policy classification and strong regression guard demonstrated by the implementation; it is **not** proof of aerodynamic accuracy. If a mesh evaluates the wrong OML, block it as an identity error. If it evaluates the correct governed source but an approximation exceeds `1e-4`, preserve the mesh and any scheduled valid diagnostic run, then reject/classify it after completion. Aerodynamic adequacy is decided by the surface/grid study.

### Mandatory identity regression

A previous UI state displayed `29 × 75` while the actual downstream surface remained `33 × 89`. Before any new CFD:

- [ ] Change one surface dimension and prove the surface node count changes.
- [ ] Prove the surface hash changes.
- [ ] Prove the volume cell count changes according to the new surface.
- [ ] Prove the case/cache fingerprint changes.
- [ ] Prove old meshes, solver results and reports are rejected as stale.
- [ ] Prove the report records requested, realized and source-template dimensions separately.

No expensive result is admissible until this end-to-end test passes.

## 3. pyHyp volume mesh: layered hyperbolic marching

### Meaning of the main controls

- `N`: number of points in the off-wall direction; there are `N−1` hexahedral layers.
- `s0`: dimensional first-cell spacing. A nondimensional law may generate it, but the exact value passed to pyHyp must be stored in metres.
- `marchDist`: dimensional distance to the outer boundary.
- `epsE`: explicit smoothing/dissipation control.
- `epsI`: implicit smoothing, kept at the governed ratio to `epsE` unless a new preregistered study changes it.
- `volCoef` and related corner/end controls: shape the march and must remain fixed across a grid triplet.

For a fixed S6 surface:

\[
N_{hex}=N_{surface\;quads}(N-1).
\]

This exact count must be calculated before every build and used by the memory preflight.

### Keep three length references separate

- `L_s0`: the exact characteristic length used by the wall-spacing law; currently the surface bounding-box diagonal unless superseded explicitly.
- `L_farfield`: full physical span `b_full`; use it to report/domain-screen `marchDist`.
- `Sref`, `cref`, `bref`: aerodynamic coefficient references from the mission/geometry contract.

Never use an unnamed generic `L` for all three. Store the value, definition and units beside every derived setting.

### Wall-normal law

- Initial candidate: current `s0/L_s0 = 3.6e-6` at the governed reference Reynolds number.
- Size each geometry for the highest wall-shear/Reynolds condition that its reused mesh must serve.
- A flat-plate estimate may initialize `s0`; only measured CFD y+ can qualify it.
- If calibration is required, use one global update on development cases:

\[
s_{0,new}=s_{0,old}\frac{0.8}{\max(y^+_{95})}.
\]

- Apply the same governed law to all affected templates, rebuild, re-audit and rerun the two wall canaries.
- If p95 passes but p99/max fails, first localize the hotspot and test whether it is a tip/TE/topology defect; do not over-refine the entire wall blindly from one isolated maximum.
- Do not enlarge `s0` merely because y+ is much lower than one; first establish the grid/cost trade.
- Stop after two unsuccessful global calibration rounds. The next action is a wall-law/grid redesign, not per-geometry rescue.

The target 0.8 leaves margin below the hard p95 limit of one. The linear correction is a calibration approximation and must be checked by the rerun.

### Farfield construction

- pyHyp's hyperbolic route remains the production method; elliptic mode is not introduced during qualification.
- Keep `b_full` as the distance reference even for a half mesh. The symmetry-domain solution represents the full aircraft, so using full span is not a double-counting error; the half model saves the mirrored cells but does not halve the physical disturbance length scale.
- The domain looked huge because `10–20 b_full` is genuinely conservative for this compact aircraft, not because the wrong span reference was used.
- Screen outer extents at `d_F/b_full = 5, 10, 15`; add `20` only if `10→15` fails the preregistered independence rule or the outer-front diagnostics remain coupled to the body.
- Prefer one largest marched layer sequence and truncate it at governed layer indices so the smaller domains share bit-identical near-body coordinates.
- If exact truncation cannot realize the requested extents, preserve `s0`, near-wall layers and smoothing and record the small realized distance mismatch.
- Domain extent is chosen by force/Cp independence, not by visual size.

The 5-span case is an intentionally economical lower bracket; it is not presumed adequate. The 10/15 cases cover the lower part of pyHyp's documented typical 10–20-span wing guidance, while the conditional 20-span case prevents a resource decision from replacing an independence demonstration.

### “Bumps” and outer-layer diagnostics

Visible waviness may arise from tip/corner propagation, competing normals, excessive smoothing or rapid cell growth. The user's proposed mechanism is credible: the seven-block planar tip collar/end closure is not literally a single rectangle, but its locally rectangular block directions meet the rounded physical tip and pyHyp propagates those competing normals outward. That can create ridges. It remains a hypothesis until localized by layer/block diagnostics.

- [ ] Plot every tenth off-wall layer in root, midspan and tip sections.
- [ ] Report layer-to-layer spacing ratio distributions by region.
- [ ] Report outer-boundary curvature/normal-angle and cell-volume-ratio distributions as diagnostics.
- [ ] Locate qmin and every cell below 0.15 by block, layer and physical region.
- [ ] Compare Cp/forces across farfield extents.
- [ ] Treat non-monotonic worsening under larger `epsE` as expected evidence; `epsE` is not a “more is always better” knob.

Controlled smoothing ladder—nominal geometry plus the thinnest/smallest-tip development extreme, mesh-only first:

1. `B0`: current governed tip closure and pyHyp settings.
2. `B1`: constrained elliptic/Winslow-style smoothing of **tip-cap interior surface nodes only**; exact pyGeo OML arcs, semantic edges and all interfaces fixed.
3. `B2`: the smallest preregistered pyHyp smoothing adjustment justified by `B0/B1`, preserving the governed `epsI/epsE` relationship; never assume larger `epsE` is safer.
4. `B3` only if needed: constrained off-wall smoothing beginning after the protected near-wall layers, with wall, block interfaces and farfield fixed.

- Never smooth or round the physical pyGeo OML merely to help the mesh. A physical-tip redesign is a new geometry version and invalidates all comparable mesh/CFD identities.
- Select the cheapest valid candidate by written-CGNS validity, qmin distribution, orthogonality, growth, interface conformity and surface fidelity—not appearance.
- Run matched CFD only for `B0` and the selected smoother candidate on the nominal case, and only if both are mathematically valid. Require CL/CD/CMy and Cp differences to lie within combined iterative/discretization uncertainty.
- If no quantitative relationship to validity, convergence or forces is found, retain the visual diagnostic and do not create a fake “bump amplitude” gate.

### Written-volume gates

Every candidate must be written to CGNS, closed, reopened by an independent reader and rescored.

- [ ] Expected block count, dimensions, families and 20 paired volume interfaces.
- [ ] Zero inverted cells and zero negative/zero volumes.
- [ ] Minimum volume scaled quality strictly `>0` as mathematical validity.
- [ ] Record project classification floor `qmin ≥0.10` and preferred routing target `qmin ≥0.15`.
- [ ] Wall error and interface mismatch within the frozen tolerances.
- [ ] First-layer spacing finite, positive and consistent with the requested law.
- [ ] Geometry, surface, options, implementation and CGNS hashes all agree.

Strictly positive volume/quality and zero inversion are pre-run mathematical gates. The 0.10/0.15 values are inherited empirical S6 routing/classification limits that separated known usable and weak meshes; they are **not** reasons to terminate an already valid CFD execution. They control robustness classification and template preference, not force accuracy. Accuracy comes from CFD verification.

## 4. Atlas routing and bounded deformation

### Atlas construction

- Normalize the 16 neutral-OML-active variables; omit fixed/non-geometric variables.
- Select deterministic maximin templates to cover the development design space.
- Store each template's exact dimensions, surface, volume, pyHyp policy and hashes.
- Parameter distance orders attempts only. It never accepts a mesh.

### Deformation

The current method first applies a global root/chord/span affine map. It then adds an exact-wall residual down each structured off-wall column:

\[
\mathbf{x}'(\xi)=\mathbf{x}_{affine}(\xi)+w(\xi)\left[\mathbf{x}_{target,wall}-\mathbf{x}_{affine,wall}\right],
\qquad w(\xi)=(1-\xi^2)^2,
\]

where `ξ=0` is the wall and `ξ=1` the farfield. Thus the wall is exact, the farfield remains fixed and the correction decays smoothly.

### Production routing policy

1. Build and validate the target pyGeo geometry.
2. Build the exact target surface at the requested candidate/final grid.
3. Rank compatible frozen templates by normalized distance.
4. Try deterministic routes and retain the best result reaching the preferred 0.15 quality.
5. If none reaches 0.15, retain the best result ≥0.10 and record a quality warning.
6. If no template reaches 0.10, build a target-specific S1/pyHyp volume using the **same grid, TE, farfield, epsE and wall law**.
7. Correct it to the exact S6 wall, write it and run the full independent audit.
8. If the fallback is inverted, non-finite, zero-volume, topologically wrong or identity-inconsistent, terminate as `MESH_INVALID`; never repair manually.
9. If the best audited fallback is mathematically valid but misses the operational 0.10 quality floor, preserve it as `MESH_VALID_POLICY_FAIL`. It may receive a clearly labelled diagnostic CFD run under the normal resource policy, but it cannot enter the accepted production-label collection unless a versioned classification later passes.
10. Run ADflow only on a written, reopened and independently audited CGNS; never on an in-memory mesh.

### Critical atlas correction

The existing 21-template atlas is qualified only for the P0 candidate dimensions. After G* is chosen:

- [ ] Rebuild every required seed at G*.
- [ ] Requalify seed meshes.
- [ ] Repeat deterministic development coverage at G*.
- [ ] Enrich only from development failures, then rerun the entire development mesh audit.
- [ ] Bind the final registry to G*, wall, TE, farfield and implementation hashes.
- [ ] Do not claim that P0's 100/100 result automatically transfers to G*.

## 5. ADflow solve and acceptance

### Physical/solver contract

- Use the single repository mission definition as authority.
- Derive Mach, Reynolds number, velocity, altitude, temperature, density and viscosity in one audited function; reject inconsistent duplicate inputs.
- Qualification scope is neutral geometry, `beta=0`, rates zero and no control deflection.
- Use compressible ADflow RANS with Spalart–Allmaras and the frozen ANK→NK strategy.
- Use wall-resolved no-slip treatment; do not use wall functions as a memory shortcut.
- State the result as a **fully turbulent RANS-SA numerical label**. TMR verification does not prove transition/model adequacy for the small-UAV BWB.

### Coefficient and moment references

- Store full-aircraft `Sref_full`, `cref=MAC` and `bref_full`.
- Store solver-domain reference values separately.
- For a half-domain whose forces are not internally doubled, use `Sref_solver=Sref_full/2`; verify this convention with one symmetry-normalization regression.
- Record whether the solver or postprocessor applies a force multiplier. Never infer it from a directory name.
- Calculate CMy about:
  - the geometry-relative quarter-MAC point for aerodynamic comparison; and
  - the mission CG for flight-dynamics use.
- Store both reference coordinates and an audited moment transformation. No moment using the implicit origin is admissible.

### Required monitored and retained outputs

- Density/continuity, all momentum components, energy and SA residual histories.
- CL, CD, CMy and pressure/viscous drag histories.
- Surface Cp, Cf and y+ for every accepted research case.
- Restart, solver stdout/stderr, options and resource logs.
- Volume fields for the preregistered paper subset. Any later archival or deletion decision requires an exact, user-approved retention proposal; qualification code never prunes automatically.

### Run first, classify second

Solver execution and scientific acceptance are separate immutable records:

- `execution_result.json` states what actually ran, for how long, with which inputs, status, histories, resources and outputs. It is never rewritten.
- `classification_policy_vNN.yaml` contains versioned acceptance definitions.
- `classification_vNN.json` applies one policy to one execution. A changed threshold reclassifies retained evidence without rerunning and without erasing the old verdict.
- Solver convergence targets control how long the nonlinear solve runs; acceptance limits such as `1e-4` are not passed blindly to the solver as stopping tolerances. The solve target must be demonstrably stricter than the acceptance need or the governed maximum iteration must be reached.

Pre-run **non-negotiable blockers**—do not spend CFD time:

- wrong/stale geometry, mesh, mission, policy, cache or holdout identity;
- unreadable/unwritten CGNS, wrong topology/BC families, non-finite coordinates, inverted/folded/zero-volume cells or failed symmetry plane;
- missing coefficient/moment references or unresolved mission thermodynamics;
- resource/disk safety preflight failure, output path collision or missing provenance/retention destination.

Runtime **non-negotiable stops** only:

- NaN/Inf or a solver-declared fatal state from which the frozen restart policy cannot recover;
- catastrophic divergence under the preregistered protection rule, invalid mesh discovered at runtime, OS/OOM protection, disk-exhaustion protection or explicit user stop.

All other numerical criteria are evaluated **after the run finishes**. A poor qmin, residual drop, force tail, `1e-4` conservation result, y+, Cp/Cf pattern or grid/farfield difference yields a transparent rejection/classification—not a hidden early stop. This maximizes reusable evidence while keeping invalid mathematics and machine damage non-negotiable.

### Post-run CFD acceptance classification

- [ ] Process exit code zero and ADflow status `converged`.
- [ ] All residual/force histories present, sufficiently long and finite.
- [ ] Primary L2 residual drop ≥6 orders and the frozen ADflow convergence target met.
- [ ] No relevant residual has non-finite values or sustained late growth: classify as failed if the median log10 residual over the final 50 iterations is more than 0.5 decade above its best preceding 50-iteration rolling median.
- [ ] Final 200-iteration relative range ≤0.001 for **CL, CD and CMy**, using denominator floors CL=0.10, CD=0.01 and CMy=0.05; also report absolute ranges.
- [ ] Pressure + viscous force decomposition is finite and reconciles with total forces.
- [ ] Normalized global mass imbalance ≤`1e-4`; report the exact definition based on signed net/gross boundary flux.
- [ ] y+ is computed on no-slip walls and passes by region and globally: p95≤1, p99≤2, maximum≤5.
- [ ] Iterative uncertainty ≤10% of the estimated discretization uncertainty for CL/CD/CMy.
- [ ] Cp/Cf/y+ fields exist, are finite and have no unexplained discontinuity at conformal interfaces.

The six-order and 0.1% tail limits are existing conservative project gates, not universal physical constants. They remain fixed because prior solver experiments showed that accepted histories collapsed to essentially identical coefficients while rejected histories did not. TMR and the first AERIS grid triplet must confirm that the gates make iterative error subordinate to grid error; tighten them if necessary, never relax them to rescue a run.

If evidence justifies a different limit, create a prospective policy version with an ADR and reclassify **all** comparable development executions. Never edit a threshold in place, tune it for one geometry, or change it after the holdout is opened.

---

# Part II — Frozen decision table

Every production constant requires a machine-linked ADR stating: semantic quantity/units, source category (mathematical necessity, repository/product scope, primary literature, measured calibration or conservative resource protection), evidence files/hashes, alternatives considered, sensitivity result, scope, owner, version and invalidation trigger. A literature recommendation is a starting bracket, not a pass result; a visually pleasing mesh is not evidence; and a limit may not exist only in chat text.

| Item | Qualification setting/gate | Why this is defensible | What it does **not** prove |
|---|---|---|---|
| Surface validity | signed scaled Jacobian `>0` | mathematical non-folding condition | force accuracy |
| Volume validity | positive volume, zero inverted cells | mathematical cell validity | low discretization error |
| S6 operational quality | classify at `qmin≥0.10`, prefer/rank at `≥0.15`; mathematical pre-run floor is `>0` | preserves the empirical routing policy while retaining diagnostic evidence | universal mesh quality |
| Surface fidelity | `≤1e-4` local chord | catches wrong sampling/identity regressions | aerodynamic insignificance |
| Interfaces | 20 pairs, `≤1e-10 m` surface mismatch | exact conformal graph requirement | farfield independence |
| y+ | p95≤1, p99≤2, max≤5 | conservative wall-resolved SA policy; controls bulk and tails | turbulence-model validation |
| Residual | ≥6 L2 orders + ADflow convergence | makes a strong reduction necessary | force convergence by itself |
| Force tail | last 200, relative range≤0.001 for CL/CD/CMy | makes iterative oscillation small and measurable | grid independence |
| Conservation | normalized mass imbalance≤`1e-4` | direct global consistency screen | physical validation |
| Grid count | three systematic levels minimum | permits observed-order/asymptotic assessment | that any arbitrary triplet is valid for GCI |
| Grid spacing | target effective ratio `1.30±0.05` | separates solutions while keeping the measured desktop cost practical | a universal optimum |
| Grid force screen | CL 1%, CD 3%, CMy 2%, with floors | initial engineering ceilings from current policy | scientific constants |
| Design-resolution gate | uncertainty ≤25% of minimum material AERIS design signal | ties numerical error to the intended DSE decision | experimental truth |
| Farfield | 5/10/15 full spans; 20 conditional | brackets a cheaper domain while retaining pyHyp's 10–20-span guidance | independence until CFD comparison passes |
| Holdout | `round_c_lhs10_seed42`, opened once after freeze | prevents tuning on final evidence | 99% population reliability from ten cases |
| Resource | measured-host policy; forecast≤75% WSL memory limit and forecast+2 GiB≤`MemAvailable` | protects Windows/WSL and leaves failure/restart headroom | that the forecast is correct; canary must measure it |

### Grid comparison metric

Keep the existing screen, but label it correctly:

\[
\delta_Q=\frac{|Q_{fine}-Q_{medium}|}{\max(|Q_{fine}|,Q_{floor})},
\]

with floors `CL=0.10`, `CD=0.01`, `CMy=0.05`. Report CD differences additionally in drag counts (`1 count = 1e-4`).

Production G* must satisfy both:

- the initial coefficient ceilings; and
- estimated 95% discretization uncertainty no larger than 25% of the smallest aerodynamic change the AERIS DSE needs to distinguish.

If the low-fidelity data cannot define that design signal, preregister a mission-level minimum before seeing the high-fidelity results.

### Mandatory visual evidence for every step

Every command—including dry runs, failures and reclassifications—emits:

1. atomic machine-readable JSON;
2. concise Markdown with a gate matrix and links to evidence;
3. one self-contained HTML report for interactive inspection; and
4. publication-ready PNG plus vector SVG/PDF for every applicable scientific figure.

| Report class | Minimum visual panels |
|---|---|
| Host/resource | RAM limit/available/RSS/swap timeline; CPU/rank utilization; disk/VHD used and campaign forecast |
| Geometry | top/front/side OML; anchor and realized loft sections; planform dimensions; twist/dihedral/sweep distributions; limit/coupling matrix |
| Surface mesh | 13 blocks colored by semantic ID; root/mid/tip sections; edge spacing; signed Jacobian distribution; worst-cell locations; fidelity heat map |
| Volume mesh | root/mid/tip layer slices; near-wall close-up; every tenth layer; qmin histogram/CDF; cells below 0.15; growth/orthogonality; outer-front curvature and bumps |
| Routing/atlas | normalized-design-space coverage projection; attempt sequence; selected template/fallback; qmin and time distributions; failures by geometry/region |
| Solver | all equation residual histories; CL/CD/CMy and pressure/viscous tails; mass imbalance; status/restart timeline; RSS/swap/disk timeline |
| Surface physics | Cp and Cf maps/sections; global and regional y+ maps/histograms; interface discontinuity checks |
| Sensitivity/grid | raw coefficient deltas; Cp overlays; uncertainty/GCI or envelope; cell/time/memory scaling; written pass/fail rationale |
| Campaign/holdout | terminal-state matrix; accepted/rejected counts; failure taxonomy; exact confidence intervals; provenance completeness |

- [ ] Use fixed units, axis ranges, color maps and semantic region names within each study so comparisons are honest.
- [ ] Mark thresholds and rejected cases visibly; never omit a failed curve or rescale an axis to make it look benign.
- [ ] Every image records case/attempt, commit, policy and source-data hashes in metadata/caption.
- [ ] `report_index.html` links all milestones and remains regenerable from retained JSON/CSV/CGNS evidence.
- [ ] Visual review can find a problem but cannot overrule a quantitative failure. Conversely, “the picture looks smooth” is never a pass criterion.

### AI division of work and independent review

AI assists; Mike remains the scientific decision owner. Use the two systems asymmetrically so credits buy independent evidence rather than duplicated prose.

| Work | Primary | Independent check |
|---|---|---|
| Experimental design, geometry envelope, uncertainty/gate changes, freeze/holdout and final scientific claims | ChatGPT/Codex `gpt-5.6-sol` at max/ultra reasoning | Claude Code Opus at maximum effort, read-only adversarial review |
| Core orchestrator, identity/provenance, mesh/CFD QC and difficult debugging | Codex `gpt-5.6-sol` | Claude Opus on milestone diffs and evidence |
| Mechanical schemas, unit tests, report plumbing, routine refactors and plot generation | lower-cost ChatGPT/Codex model such as Terra/Luna | Claude Sonnet/default or deterministic tests where sufficient |
| Paper evidence interpretation | `gpt-5.6-sol` max/ultra after M9 freeze | Claude Opus checks claim-to-evidence traceability; neither invents results |

Mandatory Claude Opus/max reviews:

1. M0/M1: geometry/design-space, half-domain, gate/classification and no-deletion contracts;
2. M2: candidate grid/resource/smoothing choice before more than the canary runs;
3. M4/M5: frozen wall/TE/farfield and grid-uncertainty decisions;
4. M8: production freeze and holdout-lock integrity before unlocking;
5. M9: paper package, limitations and every proposed claim.

Review protocol:

- [ ] A governed wrapper records Claude Code version, model/effort, exact prompt, commit, input manifest, stdout/stderr and exit status. Detect supported CLI flags instead of assuming a command syntax.
- [ ] Give the reviewer the requirements, source diff and raw evidence **without** first asking it to endorse Codex's conclusion. Require severity, file/evidence citation, falsification test and recommended disposition.
- [ ] Claude is an evaluator at freeze checkpoints, not a silent second editor. Codex/human implements accepted findings in a new commit; Claude then rechecks closure.
- [ ] Record every finding as `accepted`, `rejected-with-reason`, `deferred-with-owner` or `false-positive`; never cherry-pick only favourable comments.
- [ ] Never expose the locked holdout geometry/results to either model before M8 authorization.
- [ ] No AI agent may delete, overwrite, weaken a gate, change geometry scope or unlock holdout autonomously.

---

# Part III — Realistic experiment and run budget

## 6. Base campaign

| Study | New CFD solves | Cases | Decision produced |
|---|---:|---|---|
| NASA TMR NACA 0012 | 5 | Family II levels 5/4/3 at α=10°; α=0° and 15° on the selected level | solver/SA implementation credibility and current drag-offset resolution |
| Resource + wall canaries | 2–4 | nominal and worst-wall-shear development geometries; repeat both only after one global s0 update | measured peak RAM and wall law |
| Tip/outer-front smoothing | 1 incremental | four mesh-only candidates on nominal + tip extreme; one selected smoother CFD compared with a reused B0 nominal solve | whether visible bumps need and survive a controlled fix |
| TE screen | 4 | one nominal middle-grid case: physical absolute, small numerical, current baseline, large numerical | exact production TE law |
| Farfield screen | 3–4 | nominal middle-grid at 5/10/15 spans; 20 only under the written trigger | production outer extent |
| Coupled grid verification | 18 | five geometries × three grids at primary flow, plus one geometry × three grids at high-loading flow | G*, observed order, GCI/envelope |
| Deformed-vs-fresh CFD | 3 incremental | three already-solved deformed cases receive fresh-mesh counterparts | deformation aerodynamic neutrality within numerical uncertainty |
| Frozen development CFD | 15 incremental maximum | 20 total; reuse the selected-grid runs of the five grid-study geometries | unattended robustness, restart/cache/failure evidence |
| Locked holdout | 10 | one primary flow per untouched geometry | one-shot generalization evidence |
| **AERIS total** | **about 56–59** | reuse is mandatory | qualification plus paper dataset |

Authorized contingency:

- Up to six extra grid solves, one fourth level for each non-asymptotic sequence, only after a written trigger report.
- No 150-run `5 geometries × 3 grids × 10 AoA` factorial.
- No 500–1,000-case rehearsal. Controlled fault injection inside the 20-case development campaign proves recovery more efficiently.
- No 100-case CFD pilot before the lean qualification campaign passes.

## 7. Exact geometry selections

Use development data only and write the IDs before launching CFD:

- `A`: nominal/medoid geometry.
- `B`: geometry 007 or the final hardest routing case.
- `C`: worst accepted qmin/deformation case.
- `D`: opposing geometric extreme selected by normalized maximin distance.
- `E`: highest predicted loading/wall-shear geometry under the repository mission envelope.

Grid study at primary flow: `A–E`.  
High-loading grid triplet: geometry `A` at the highest **pre-stall mission AoA** declared by the repository; do not invent 8° if the mission file defines another value.

Development-20 composition:

- five predeclared geometric extremes;
- ten maximin-spread interior designs;
- five deterministic random designs not used to tune settings.

The same geometry cannot appear in the locked holdout.

## 8. TMR minimum programme

Use the official NASA TMR NACA 0012 geometry, boundary conditions and nested grids exactly; do not remesh it with S6.

- [ ] Mach 0.15 and Reynolds number 6 million, with the official reference definitions.
- [ ] Use the TMR's corrected, scaled, sharp-TE NACA 0012 definition—not an ordinary blunt NACA formula.
- [ ] Use Family II levels 5, 4 and 3 (`449×129`, `897×257`, `1793×513`) at α=10°. They are exactly nested every-other-point grids, have a farfield near 500 chords and keep the largest base case near the present 16 GiB AERIS canary size.
- [ ] Select the cheapest of those levels supported by the convergence evidence, then run it at α=0° and α=15°.
- [ ] Compare CL and CD trends and Cp at α=0°, 10° and 15°; retain Cf as a numerical diagnostic because the official page does not provide experimental Cf validation data.
- [ ] Use the TMR-recommended fully turbulent setup and report the turbulence inflow quantities.
- [ ] Explain the existing local result (`CL≈1.091774`, `CD≈0.013164`) and the roughly 8.5-drag-count discrepancy before using the word “validated.”
- [ ] Treat TMR as a solver/turbulence-model implementation anchor. It does not validate the AERIS BWB, transition behavior or low-Re mission regime.

---

# Part IV — Milestones and stop/go gates

## M−1 — Inspect and configure the desktop/WSL2 host

**Cost:** no CFD. This is the first desktop job, before pulling work or generating large data. The present report cannot see Mike's desktop, so no RAM, processor or disk value may be assumed until this inventory runs there.

### M−1A read-only inventory

From Windows PowerShell, save the output as `host_inventory_windows.json/txt`:

```powershell
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory,Manufacturer,Model
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
Get-PhysicalDisk | Select-Object FriendlyName,MediaType,BusType,Size,HealthStatus
Get-Volume | Select-Object DriveLetter,FileSystemLabel,FileSystem,Size,SizeRemaining,HealthStatus
wsl --version
wsl --status
wsl -l -v
wsl --list --running
if (Test-Path "$env:USERPROFILE\.wslconfig") { Get-Content "$env:USERPROFILE\.wslconfig" }
```

Locate but do not move or edit the distro VHD, and record its physical size and host free space. From inside the target WSL distro, save `host_inventory_linux.json/txt`:

```bash
uname -a
free -h
nproc
lscpu
df -hT / /home
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
swapon --show --bytes
ulimit -a
pwd
```

- [ ] Confirm WSL2, distro/version, physical RAM, WSL memory limit, cores/logical CPUs, swap, VHD path/max/physical size, SSD/HDD type and free space on both ext4 and the Windows host volume.
- [ ] Confirm the active repository and run data reside in the Linux filesystem under `/home/...`, not `/mnt/c/...`; Microsoft recommends the Linux filesystem for Linux-command-line performance.
- [ ] Measure existing code, environments and data by category. Do not delete anything during inventory.

### M−1B produce and approve the settings proposal

The orchestrator writes `desktop_resource_policy_v1.yaml`, `wslconfig_proposal.txt` and a before/after explanation. Proposed WSL memory is:

\[
M_{WSL}=\left\lfloor\min(0.80M_{host},\;M_{host}-4\,\mathrm{GiB})\right\rfloor,
\]

with a 3 GiB Windows reserve allowed only for a confirmed 16 GiB machine dedicated to the run. Thus, if the desktop really has 16 GiB and no conflicting workload, the starting proposal is:

```ini
[wsl2]
memory=13GB
swap=8GB

[experimental]
autoMemoryReclaim=gradual
```

Defence:

- WSL's default memory limit is 50% of host RAM, which would expose only about 8 GiB on a 16 GiB host and cannot run the present 9.35 GiB canary forecast.
- `13GB` leaves about 3 GiB for Windows while making the canary testable. It is a ceiling, not permission to consume all 13 GiB.
- `8GB` swap is emergency containment, not CFD capacity. Any material solver swap is recorded and the run is resource-failed even if it completes; scientific timing from a swapping run is inadmissible.
- Omit `processors` initially so WSL sees the supported logical processors. Select ADflow/MPI ranks later from measured aggregate RSS and time; more ranks are not automatically faster or safer on a memory-bound desktop.
- Use `autoMemoryReclaim=gradual` only if the installed WSL version supports it; otherwise omit the experimental section and record that decision.

Never apply the example blindly. Show the exact diff and obtain Mike's confirmation before changing global WSL settings, terminating other distros, relocating/resizing a VHD or making a large backup. Apply with `wsl --shutdown`, restart, and prove the effective values with `free -h`, `nproc` and `swapon --show`.

### M−1C storage and reproducibility policy

- [ ] Benchmark read/write throughput in the proposed Linux data root; never place active CGNS/restart workloads on `/mnt/c`.
- [ ] From the first mesh and first complete canary, measure sizes for mesh, restart, logs, surface fields and optional volume fields. Forecast the complete 56–59-run campaign before M3.
- [ ] Predeclare which cases write full volume fields; all runs retain logs, histories, surface Cp/Cf/y+, restart-policy artifacts and hashes. Avoid creating unnecessary full fields rather than generating and deleting them later.
- [ ] Require free physical host storage and ext4 capacity of at least `1.30 × forecast_remaining + 3 active-case footprints + 20 GiB`.
- [ ] Remember that WSL's ext4 VHD is dynamically expanding: the Linux-reported maximum is not proof that the Windows host has that physical space.
- [ ] Create and verify Git remote recovery for source/small evidence plus a governed backup destination for large evidence. A VHD export/resize must never overwrite its only recoverable copy.
- [ ] On insufficient capacity, stop as `STORAGE_BLOCKED` and ask whether to add storage, reduce *future output generation*, or approve a specific archive action. Never auto-prune.

**GO:** signed inventory, applied/verified resource policy, fast Linux-native data root, campaign storage forecast and recovery plan exist.  
**NO-GO:** a heavy command is launched from an assumed 16 GiB configuration or without physical-host disk headroom.

## M0 — Put the qualification experiment in Git

**Cost:** no CFD.  
**Important:** the current workspace contains reports/attachments, not the live Git repository, so no repository commit or push can be performed from here.

Create in the real repository:

```text
AERIS_MESH_STUDY/05_s6_cfd_qualification/
├── MASTER_EXECUTION_GUIDE.md
├── README.md
├── POLICY.yaml
├── experiment_manifest.yaml
├── run.py
├── schemas/
├── tests/
├── reviews/
├── reports/
│   └── figure_specs.yaml
├── studies/
│   ├── tmr/
│   ├── resource_wall/
│   ├── trailing_edge/
│   ├── farfield/
│   ├── grid/
│   ├── deformation/
│   ├── development/
│   └── holdout/
└── paper/
    ├── collect.py
    └── figure_specs.yaml
```

- [ ] Copy this guide into that directory.
- [ ] Commit the M−1 host inventory, effective resource policy and storage forecast with sensitive machine identifiers redacted if necessary.
- [ ] Create `geometry_design_space_phase1_v1.yaml` from the live-parser semantic diff; never overwrite the old geometry config or design sets.
- [ ] Implement schemas and a single orchestrator before any heavy run.
- [ ] Implement immutable execution results plus versioned, repeatable classification policies.
- [ ] Encode `deletion_policy: explicit_human_approval_only` and tests that reject broad/destructive cleanup requests.
- [ ] Implement the standard JSON/Markdown/HTML/PNG/SVG report contract and a report gallery index before the first mesh study.
- [ ] Commit code, policy, tests, small JSON/CSV/Markdown evidence and environment locks.
- [ ] Do not commit large CGNS/restart/field files; store durable hashes and locations.
- [ ] Push and record the exact commit hash used by the desktop.
- [ ] Obtain the M0/M1 Claude Opus/max adversarial report and close every high-severity finding before the canary.

**GO:** a fresh clone can execute dry-run tests and reconstruct every manifest.  
**NO-GO:** any manual setting exists only in a chat, GUI or shell history.

## M1 — Repair the scientific and automation contract

**Cost:** tests only.

- [ ] Locate exactly one mission authority; fail if none or multiple contradictory authorities exist.
- [ ] Parse every live geometry variable/bound/semantic and resolve the Phase-I table diff before regenerating development and holdout identities.
- [ ] Freeze primary/high-load flows and all derived thermodynamic values.
- [ ] Freeze half-domain eligibility (`beta=0`, zero rates, symmetric geometry/control) and add explicit full/half reference-area, force-multiplier and symmetry-plane regression tests.
- [ ] Add quarter-MAC and mission-CG moment references; remove implicit origin use.
- [ ] Add CMy to monitor variables and the force-tail gate.
- [ ] Parse/store momentum, energy and SA residuals, not only density and turbulence.
- [ ] Add normalized mass imbalance.
- [ ] Retain surface Cp/Cf/y+ for all research runs.
- [ ] Add physical absolute-1-mm TE mode.
- [ ] Add the 29×75 identity/cache invalidation regression.
- [ ] Make `round_c_lhs10_seed42` inaccessible unless a valid freeze manifest is supplied.
- [ ] Separate terminal states: geometry, mesh, resource, solver, convergence, y+, physics/QC and accepted.
- [ ] Separate non-negotiable pre/runtime stops from post-run scientific classification.
- [ ] Make every threshold machine-readable, versioned and re-applicable to old executions; prohibit in-place or case-specific runtime overrides.
- [ ] Prove a changed classification threshold creates a new verdict while retaining the original execution and verdict.

**GO:** focused tests, full mesh/CFD tests, formatting and an independent report audit pass.  
**NO-GO:** one stale result can be accepted after changing geometry, grid, MPI, solver or policy.

## M2 — Prove a three-level family exists inside the inventoried WSL limit

**Cost:** mesh builds only, then one CFD canary.

1. Generate candidate levels `C01…Cnn`; do not name them G1/G2/G3 yet.
2. Keep the 13-block graph, TE, farfield, smoothing and wall treatment fixed.
3. Refine chord, span, endpoint, collar, `N` and first-cell spacing together.
4. Prefer pyHyp/solver multigrid-friendly dimensions: document the factorization of every `points−1` count and reject a nominal refinement that cannot be coarsened consistently by the intended solver sequence.
5. Target successive effective ratios

\[
r_{eff}=\left(\frac{N_{cells,fine}}{N_{cells,coarse}}\right)^{1/3}=1.30\pm0.05.
\]

6. Screen nominal plus geometries B/C/E with written-CGNS audit.
7. Forecast memory for every candidate using the current measured/forecast model and a conservative safety factor.
8. Treat `29×75×N97` as the tentative **finest candidate**, not as G1.
9. Run geometry A at the worst required mission Reynolds/wall-shear condition on the tentative finest candidate, one rank, under `/usr/bin/time -v`; record peak RSS and wall time. This is also the first M4A wall case and must be reused by complete hash.
10. Increase MPI ranks only if measured aggregate peak plus 25% headroom remains below the resource gate.

Resource GO:

- [ ] Forecast ≤75% of the verified WSL memory limit.
- [ ] Forecast +2 GiB ≤ `MemAvailable` immediately before launch.
- [ ] Free disk ≥ three active-case footprints +20 GiB.
- [ ] Measured peak RSS ≤ forecast and leaves ≥2 GiB available.
- [ ] No OOM, swap storm or kernel kill.

Family GO:

- [ ] Three valid coupled levels on A/B/C/E.
- [ ] Every declared direction refines monotonically.
- [ ] Actual effective ratios are within the target band or explicitly justified before CFD.
- [ ] The finest canary meets all mesh/resource/solver gates.
- [ ] Claude Opus/max independently reviews the grid, memory and smoothing evidence and all findings have dispositions.

**Hard stop:** `RESOURCE_BLOCKED_HOST` (reported as `RESOURCE_BLOCKED_16GB` only if inventory confirms 16 GiB) if no credible finest candidate fits. That result requires more memory or a materially different numerical method; it does not authorize weaker science.

### M2B — Diagnose and freeze tip/outer-front smoothing

**Cost:** eight mesh builds plus one incremental CFD solve; the B0 nominal solve is the M2 canary and is reused.

- [ ] Build `B0…B3` from the controlled ladder in Section 3 on A and the predeclared smallest/thinnest-tip extreme.
- [ ] Generate the standard layer/block/quality visual report for every candidate, including failures.
- [ ] Eliminate only mathematical invalidity before CFD; classify qmin/smoothness criteria after generation.
- [ ] Select one policy by written metrics and fixed-wall/interface preservation. If B0 is not measurably worse, retain B0 and spend no extra CFD.
- [ ] If a smoother candidate is selected, run its one matched nominal CFD case to completion and compare it with the hash-identical B0 flow/reference case.
- [ ] Freeze the smoothing/tip policy before M4/M5; no geometry-specific smoothing knob.

**GO:** one defensible global policy, exact OML, positive volumes and no resolved force bias.  
**NO-GO:** the “fix” moves the physical wall, hides a topology defect or is selected only because a screenshot looks rounder.

## M3 — Reproduce the TMR anchor

**Cost:** five quasi-2D CFD solves, each subject to the same desktop resource preflight.

- [ ] Generate a locked TMR manifest from official inputs.
- [ ] Run the five-case programme in Section 8.
- [ ] Calculate grid convergence with actual nested-grid counts.
- [ ] Compare to official numerical/experimental quantities.
- [ ] Diagnose geometry, normalization, transition/turbulence, farfield, solver and convergence causes of the current drag offset.
- [ ] Save Cp comparison data and plots.

**GO:** results are reproducible, asymptotic behavior is understood, and differences are within a predeclared benchmark tolerance or honestly explained and bounded.  
**NO-GO:** the local anchor is accepted merely because CL looks plausible.

## M4 — Freeze nuisance parameters: wall, TE and farfield

### M4A wall law — 2 to 4 solves

- [ ] Reuse the hash-identical M2 canary for A, then run E at the worst required Reynolds/wall-shear condition on the finest executable candidate.
- [ ] Apply global y+ gates by wall region.
- [ ] If needed, apply the one global `s0` correction and rerun A/E.
- [ ] Freeze the law; no per-geometry `s0`.

### M4B trailing edge — 4 solves

On A at the middle candidate, compare:

1. `TE-P`: physical 1.0 mm absolute, no fraction floor;
2. `TE-S`: `max(0.5 mm, 0.25%c)` — sensitivity only;
3. `TE-B`: `max(1.0 mm, 0.50%c)` — current baseline;
4. `TE-L`: `max(1.5 mm, 0.75%c)` — deliberately larger bias.

- [ ] All four use identical non-TE settings.
- [ ] Compare CL, total/pressure/viscous CD, CMy and aft Cp.
- [ ] Reject numerical variants that contradict manufacturability/physical scope.
- [ ] Prefer TE-P if it meshes and converges.
- [ ] If TE-P fails, numerical-TE bias must be ≤20% of final grid uncertainty and ≤25% of the minimum design signal. Otherwise S6 is not trustworthy for drag labels.

### M4C farfield — 3 to 4 solves

- [ ] Run A at 5, 10 and 15 full spans using the selected TE and middle candidate; run 20 only if `10→15` fails or outer-front/body coupling remains suspected.
- [ ] Compare CL/CD/CMy and surface Cp.
- [ ] Select the smallest domain for which the two largest relevant domains differ by ≤10% of final grid uncertainty; provisional ceilings are `|ΔCL|≤1e-3`, `|ΔCD|≤1e-4` (one drag count), `|ΔCMy|≤1e-4`.
- [ ] Re-evaluate the decision after M5 computes final uncertainty.
- [ ] Add one confirmation only if TE/grid interaction changes the decision.

**M4 GO:** one wall law, one TE law and one farfield extent are frozen with evidence.  
**NO-GO:** a threshold is edited in place or changed for one case; an evidence-driven prospective version requires an ADR and uniform reclassification.

- [ ] Claude Code independently reviews the nuisance freeze without access to future holdout evidence; Sonnet/default is sufficient here because the Opus/max M5 review will re-audit the complete M4+M5 decision.

## M5 — Verify discretization and select G*

**Cost:** 18 base solves; up to six conditional.

- [ ] Rename the selected candidates G1/G2/G3 only now.
- [ ] Run A–E at the primary mission flow on all three grids.
- [ ] Run A at the high-loading mission flow on all three grids.
- [ ] Use identical geometry, TE, farfield, flow, turbulence model, solver and gates within each triplet.
- [ ] Calculate actual cell-count ratios and effective h.
- [ ] Report raw CL/CD/CMy/L/D and Cp/Cf/y+ changes.
- [ ] Estimate iterative uncertainty from tails/restarts.
- [ ] Use observed-order/Richardson/GCI only for monotonic, asymptotic-looking sequences; use the actual unequal refinement ratios and GCI safety factor 1.25 for a valid three-or-more-grid sequence.
- [ ] For oscillatory/non-asymptotic sequences, report the raw envelope and add one fourth level only under the preregistered trigger.
- [ ] Check that iterative uncertainty ≤10% of discretization uncertainty.
- [ ] Choose the cheapest G* satisfying the coefficient ceilings and design-signal gate on every critical case.

**GO:** an executable G* exists, wall y+ still passes on G*, and uncertainty is small enough for AERIS decisions.  
**NO-GO:** the only accurate level exceeds the inventoried-host resource gate.

- [ ] Claude Opus/max verifies the M4 nuisance decisions, sequence classification, uncertainty arithmetic, resource compliance and the G* choice before atlas rebuild.

## M6 — Rebuild the final atlas and quantify deformation

**Cost:** mesh-only atlas work + three incremental fresh CFD solves.

- [ ] Rebuild/qualify the atlas at G* with frozen wall/TE/farfield settings.
- [ ] Repeat the 100-development-geometry written-CGNS audit.
- [ ] Enrich deterministically only from development evidence; re-audit all 100 after enrichment.
- [ ] Benchmark 20 predeclared target/template pairs:
  - fresh target-specific S1/pyHyp volume;
  - atlas deformation to the same exact target;
  - full mesh QC, runtime and peak memory.
- [ ] For three spread cases, compare CFD from deformed and fresh meshes at identical flow/settings.
- [ ] Require differences to lie within combined iterative + discretization uncertainty.
- [ ] Record speedup as median, p05/p95 and worst case; do not report only the best speedup.

**GO:** 100/100 development meshes are valid at G*, deformation causes no resolved aerodynamic bias, and fallback works without manual repair.

## M7 — Frozen unattended 20-case development campaign

**Cost:** 20 total final-grid solves; normally ≤15 are new after reuse.

- [ ] Freeze code, environment, policy, atlas, retry policy and output schema.
- [ ] Run the predeclared 20 geometries at one primary flow.
- [ ] Permit only deterministic, predeclared retries.
- [ ] Deliberately interrupt two copied jobs; prove restart and exact terminal recovery.
- [ ] Repeat two accepted jobs; prove deterministic cache/collection behavior within iterative tolerance.
- [ ] Deliberately exercise an alternate-template route and fresh-mesh fallback on development cases.
- [ ] Never tune a single case.

Pass:

- [ ] 20/20 reach an auditable terminal state.
- [ ] At least 19/20 produce accepted CFD unattended.
- [ ] Zero invalid/unconverged cases are falsely accepted.
- [ ] Every failure has one deterministic classification.
- [ ] All retained outputs and provenance pass an independent collector audit.

If 19/20 passes, the paper may claim a bounded fail-closed development yield, not universal success.

## M8 — Freeze, then open the holdout once

**Cost:** ten solves.

- [ ] Write a freeze manifest containing Git commit, environment, geometry, mission, G*, atlas, wall, TE, farfield, solver, gates, retries and schema hashes.
- [ ] Verify that `round_c_lhs10_seed42` has never been generated, visualized, meshed or inspected.
- [ ] Obtain and close the pre-unlock Claude Opus/max review of the freeze manifest and holdout-lock test; the reviewer sees lock metadata, not holdout geometries/results.
- [ ] Change the holdout lock state in one auditable commit.
- [ ] Run all ten once at the primary flow.
- [ ] Do not tune from their results.
- [ ] Report accepted yield, all failure classes and exact binomial intervals.

Interpretation:

- 10/10 terminal classifications and zero false-safe cases are mandatory.
- Prefer 10/10 accepted.
- 9/10 may support a bounded fail-closed claim, but not a universal robust-coverage claim.
- 10/10 or even 100/100 is not proof of 99% population reliability. For zero failures, about 299/299 trials are needed for a one-sided 95% lower bound of roughly 99%.

## M9 — Generate the complete Paper 1 evidence package

**Cost:** analysis only.

- [ ] One immutable `paper_data_manifest.json` with every source/hash.
- [ ] Machine-generated methods/configuration table.
- [ ] Geometry and 13-block surface schematic data.
- [ ] P0 versus G* status table.
- [ ] TMR convergence and Cp/CD comparison.
- [ ] Memory/cell/time scaling.
- [ ] Wall-y+ regional plots.
- [ ] TE and farfield sensitivity plots.
- [ ] Six grid-triplet plots/tables with GCI or raw-envelope classification.
- [ ] Atlas routing attempts, qmin distribution and failure map.
- [ ] Fresh-versus-deformed quality, time and force comparisons.
- [ ] Development and holdout terminal-state/yield tables with exact confidence intervals.
- [ ] A machine-readable limitations/allowed-claims file.
- [ ] A reproducible command that regenerates every table and figure from retained evidence.
- [ ] Claude Opus/max claim-to-evidence review, with all findings and dispositions included in the evidence manifest.

**Completion:** all technical work and paper figures/tables are frozen; only manuscript writing remains.

---

# Part V — Exact desktop implementation and execution checklist

## 9. Start the desktop session

Run M−1 inventory/configuration first from PowerShell and WSL. Do not assume the old 16 GiB/11.36 GiB values. After the WSL policy is verified and the guide has been committed to the real repository:

```bash
cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
git status --short
git branch --show-current
git pull --ff-only
git rev-parse HEAD
free -h
nproc
df -h .
```

Stop if the worktree has unexplained changes, the expected guide/commit is absent, or available memory/disk is below the inventoried policy. Preserve the worktree exactly; never “clean it up” destructively.

### First prompt to desktop Codex

```text
Read AERIS_MESH_STUDY/05_s6_cfd_qualification/MASTER_EXECUTION_GUIDE.md,
PROJECT_HANDOFF/LIVE_STATE.md, CURRENT_STATUS.md, DECISIONS.md,
RISKS_AND_OPEN_GATES.md, the S6 README/STUDY/RESEARCH/ROADMAP files, and the
governance mission/geometry/gate files. Treat the master guide as the work order.

First execute M-1, then implement and test M0-M2 only. Inspect the real desktop,
propose/verify WSL RAM/swap/storage settings, and parse/diff the live geometry
space against geometry_design_space_phase1_v1. Do not launch a heavy solve until
the contract, holdout lock, 29x75 identity regression, resource estimator and
candidate-grid written-CGNS screens pass. Never assume 16 GiB or bypass the
inventoried resource gate. Never access round_c_lhs10_seed42 before the M8 freeze.
Use the repository mission file as the only flow authority. Preserve all failed
attempts, provenance and unrelated worktree changes. Never delete, overwrite,
prune, reset or replace important artifacts/codebases without my explicit approval
for the exact paths. Separate immutable run completion from versioned post-run
classification; only mathematical, identity, holdout, disk/memory-safety or fatal
runtime conditions may stop a run early. Produce the governed visual report for
every command and failed case. Use gpt-5.6-sol max/ultra for scientific decisions,
lower-cost models for mechanical tasks, and Claude Code Opus/max as the independent
reviewer at the five required Opus/max checkpoints, with the lighter M4 preliminary
review as specified. Commit and push small source, policy and
report changes after each accepted milestone; do not commit CGNS or field files.
Continue milestone by milestone only when the preceding GO report is machine-green.
Finish by generating the M9 paper evidence package.
```

## 10. Required orchestrator interface

The following commands are the required stable interface. They do not yet exist in the attached snapshot; implementing them is the first desktop coding task.

```bash
QUAL=AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py
PY=.venv/bin/python

$PY $QUAL audit-contract
$PY $QUAL inventory-host
$PY $QUAL propose-wsl-config
$PY $QUAL verify-host-policy
$PY $QUAL audit-geometry-space
$PY $QUAL write-plan
$PY $QUAL check-holdout-lock
$PY $QUAL test-identity
$PY $QUAL check-resources
$PY $QUAL screen-grid-family
$PY $QUAL screen-tip-smoothing
$PY $QUAL run-canary
$PY $QUAL run-tmr
$PY $QUAL run-wall
$PY $QUAL run-te
$PY $QUAL run-farfield
$PY $QUAL run-grid
$PY $QUAL freeze-nuisance-policy
$PY $QUAL build-final-atlas
$PY $QUAL benchmark-deformation
$PY $QUAL run-development
$PY $QUAL freeze-production
$PY $QUAL unlock-holdout --freeze-manifest <path>
$PY $QUAL run-holdout --freeze-manifest <path>
$PY $QUAL classify --execution <path> --policy <path>
$PY $QUAL render-report --scope <scope>
$PY $QUAL prepare-independent-review --milestone <M0|M2|M4|M5|M8|M9>
$PY $QUAL collect-paper-package
$PY $QUAL audit-all
```

Every subcommand must support `--dry-run`, emit atomic JSON plus concise Markdown and the standard HTML/figure package, include source/input hashes, and return nonzero on a failed gate/classification. A CFD command must still finish and write its immutable execution record before returning the post-run classification code unless a non-negotiable stop occurs.

## 11. Stable work order

### Phase 0 — desktop/WSL setup before project work

- [ ] Run the M−1 PowerShell and Linux read-only inventory.
- [ ] Review the generated `.wslconfig` and storage proposal; apply only the confirmed values.
- [ ] Restart WSL with `wsl --shutdown`, then verify effective RAM/swap/CPU/disk values.
- [ ] Confirm the active repository/data root is Linux-native and the backup/retention plan has enough physical capacity.
- [ ] Commit/push the non-sensitive inventory, resource policy and storage forecast before any heavy solve.

### Phase A — implement without heavy runs

```bash
$PY $QUAL audit-contract
$PY $QUAL audit-geometry-space
$PY $QUAL write-plan
$PY $QUAL check-holdout-lock
$PY $QUAL test-identity
$PY -m pytest -q AERIS_MESH_STUDY/05_s6_cfd_qualification/tests
$PY -m pytest -q AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py
```

- [ ] Review the plan diff.
- [ ] Resolve the Phase-I geometry diff and regenerate/re-identify sets if required.
- [ ] Close the M0/M1 independent Claude review.
- [ ] Commit/push source and small policy artifacts.
- [ ] Do not open the holdout.

### Phase B — mesh-only candidate family

```bash
$PY $QUAL check-resources
$PY $QUAL screen-grid-family
$PY $QUAL screen-tip-smoothing
$PY $QUAL audit-all --scope grid_mesh_screen
```

- [ ] Candidate labels remain Cxx.
- [ ] Written CGNS, not in-memory coordinates, controls acceptance.
- [ ] Select one tentative triplet and one finest canary.
- [ ] Freeze or explicitly retain B0 tip/outer-front smoothing policy.
- [ ] Commit/push the selection report before CFD.

### Phase C — one measured canary

```bash
$PY $QUAL check-resources --next canary
/usr/bin/time -v $PY $QUAL run-canary
$PY $QUAL audit-all --scope canary
```

- [ ] Inspect peak RSS, swap, return code, residuals, forces, y+ and retained surface fields.
- [ ] Let the mathematically valid canary finish; then classify it under the frozen policy. Do not launch the second case until the first execution/classification/visual package is reviewed.
- [ ] If memory fails, record `RESOURCE_BLOCKED_HOST` (or the confirmed 16 GiB subtype) and stop heavy S6 work.

### Phase D — validation and nuisance studies

```bash
$PY $QUAL run-tmr
$PY $QUAL run-wall
$PY $QUAL run-te
$PY $QUAL run-farfield
$PY $QUAL audit-all --scope validation_nuisance
$PY $QUAL freeze-nuisance-policy
```

- [ ] Run sequentially by default; concurrency is earned only by measured memory.
- [ ] Reuse identical accepted cases by complete hash, never by filename.
- [ ] Any setting change creates a new policy version and invalidates dependent results.

### Phase E — grid verification

```bash
$PY $QUAL run-grid
$PY $QUAL audit-all --scope grid
```

- [ ] Review the first A triplet before submitting B–E.
- [ ] Trigger fourth grids only from the machine-readable non-asymptotic rule.
- [ ] Freeze G* only if resource, y+, convergence and uncertainty all pass.

### Phase F — final atlas and deformation

```bash
$PY $QUAL build-final-atlas
$PY $QUAL benchmark-deformation
$PY $QUAL audit-all --scope atlas_deformation
```

- [ ] Rebuild at G*; never reuse a dimension-incompatible P0 seed.
- [ ] Require the complete 100-development mesh audit after any enrichment.

### Phase G — unattended development

```bash
$PY $QUAL run-development
$PY $QUAL audit-all --scope development
```

- [ ] Start with one case, then batches that obey the measured resource limit.
- [ ] Inject the two planned interruptions only on copied development jobs.
- [ ] No case-specific editing or threshold overrides.

### Phase H — production freeze and holdout

```bash
$PY $QUAL freeze-production
git status --short
git add <only-small-source-policy-report-files>
git commit -m "Freeze qualified S6 CFD policy"
git push
FREEZE=<path-written-by-freeze-production>
$PY $QUAL unlock-holdout --freeze-manifest "$FREEZE"
$PY $QUAL run-holdout --freeze-manifest "$FREEZE"
$PY $QUAL audit-all --scope holdout
```

- [ ] No modifications after `freeze-production` except the auditable holdout state transition and collection code that cannot affect runs.
- [ ] A holdout failure is reported, not repaired.

### Phase I — paper package

```bash
$PY $QUAL collect-paper-package
$PY $QUAL audit-all
git status --short
```

- [ ] Regenerate all figures/tables twice and compare hashes.
- [ ] Commit/push small tables, figure sources, captions, manifest and final reports.
- [ ] Back up large raw evidence and verify its checksums.

## 12. Per-run preflight

- [ ] Case ID, geometry ID, flow ID, grid ID and policy version are unique.
- [ ] Geometry/mission/mesh/solver/environment hashes resolve.
- [ ] Holdout state is allowed.
- [ ] Required parent milestone is green.
- [ ] Exact cell count and memory/disk forecast pass.
- [ ] CGNS is reopened and has correct identity/topology/BCs, finite coordinates, positive volumes and zero inversions; policy-quality misses are recorded but do not masquerade as mathematical invalidity.
- [ ] No incompatible heavy process is active.
- [ ] Output directory is new or a hash-valid restart; no existing attempt can be overwritten.
- [ ] Surface solution retention is enabled.
- [ ] Moment references and half/full reference convention are printed before solve.
- [ ] Non-negotiable runtime-stop rules and the post-run classification policy/version are printed separately.

## 13. Per-run post-completion classification

- [ ] Geometry contract pass.
- [ ] Surface pass.
- [ ] Written-CGNS volume pass.
- [ ] Resource pass.
- [ ] Solver/status pass.
- [ ] Full residual pass.
- [ ] CL/CD/CMy tail pass.
- [ ] Conservation pass.
- [ ] Global and regional y+ pass.
- [ ] Cp/Cf/y+ retained and finite.
- [ ] All reports/hashes durable.
- [ ] Terminal state cannot be changed without a new attempt ID.
- [ ] Immutable execution status is distinct from the versioned acceptance verdict.
- [ ] Reclassification reproduces the same result from retained evidence and keeps every older verdict.
- [ ] Standard visual report exists even when the case is rejected.

## 14. Failure handling

- Geometry failure → record and stop.
- Atlas mesh failure → next deterministic compatible template.
- All atlas routes fail → governed fresh S1/pyHyp fallback.
- Mathematically invalid fresh fallback → `MESH_INVALID`; do not launch CFD.
- Positive but policy-weak fallback → retain and, if scheduled, let diagnostic CFD finish; classify afterward.
- Memory forecast fails → `RESOURCE_REJECTED`; do not launch.
- OOM/disk protection → stop as `RESOURCE_BLOCKED_HOST`; retain partial execution evidence. Material swap without OOM may finish but fails resource classification and timing credibility.
- Solver process fails → one frozen restart if permitted; otherwise `SOLVER_FAILED`.
- Residual/force/conservation/y+/qmin/fidelity threshold fails → let a valid run complete, preserve it, then record the exact policy/version; do not call it accepted.
- Holdout failure → final evidence; no new tuning round.
- Storage pressure → `STORAGE_BLOCKED`, exact proposal, explicit user decision; never delete or prune automatically.

---

# Part VI — Paper plan and permitted claims

## 15. Paper 1

**Working title:**  
**“A Fail-Closed, Resource-Constrained Automated RANS Data Factory for Parametric Blended-Wing-Body UAV Design”**

### Core contribution

- One fixed-semantic pyGeo BWB family.
- Exact-wall, fixed-graph 13-block structured surface construction.
- pyHyp volume generation with explicitly qualified wall/TE/farfield/grid policy.
- Deterministic maximin atlas, bounded exact-wall deformation and fresh-mesh fallback.
- Independent written-mesh and CFD fail-closed gates.
- Verification under the measured desktop/WSL compute constraint (reported as 16 GiB only if M−1 confirms it).
- TMR anchor, development campaign and untouched holdout.
- Measured cost, recovery behavior and honest failure accounting.

### Paper structure

1. Motivation and credibility problem in automated CFD datasets.
2. Parametric geometry and fixed surface graph.
3. Volume marching, atlas deformation, routing and fallback.
4. Fail-closed mesh/CFD/provenance architecture.
5. TMR and AERIS verification design.
6. Wall, TE, farfield and grid results.
7. Atlas/deformation and unattended development results.
8. Locked holdout, cost and statistical interpretation.
9. Limits and implications for multi-fidelity AI.

### Claims allowed if all gates pass

- The pipeline produced auditable terminal outcomes without manual mesh repair on the declared sets.
- The selected G* met the declared numerical-uncertainty requirement for the tested flows/geometries.
- Atlas deformation reduced cost by the measured distribution and introduced no resolved bias above combined uncertainty in the three matched tests.
- The observed development and holdout acceptance rates are exactly those measured.
- Outputs are fully turbulent ADflow RANS-SA labels within the declared geometry/flow scope.

### Claims prohibited

- “100% robust over all possible BWB geometries.”
- “Validated aircraft aerodynamics” without BWB experimental data.
- “Production resolution” for P0 or any grid not selected by M5.
- “99% reliable” from 100/100, or from the ten-case holdout.
- “Physical trailing edge has no effect” unless TE-P is selected or sensitivity is below the declared uncertainty gate.
- “AI-generated trustworthy data.” AI can assist code, review and writing; deterministic evidence and the researcher remain authoritative.

### AI use

- Preserve AI-assisted code/review provenance as required by the university and target journal.
- Independently test every AI-generated implementation and recalculate every number from artifacts.
- Report the governed Codex/Claude division of work and independent finding dispositions; do not describe two AI opinions as experimental replication.
- Use AI for drafting only after M9 freezes the evidence.
- An AI template-ranking ablation belongs in Paper 1 only if a grouped-by-geometry untouched test shows lower attempts/runtime with zero observed false-safe decisions. It is optional and must not delay S6 qualification.

## 16. Paper 2 and S7

Paper 2 should use qualified S6 as infrastructure:

**“Safety-Aware Multi-Fidelity Active Learning for Control-Constrained BWB UAV Design.”**

- low-fidelity AVL/NeuralFoil coverage;
- sequential S6 high-fidelity batches;
- geometry-grouped splits;
- calibrated uncertainty and failure labels;
- aerodynamic plus trim/flyability objectives;
- active learning versus random/LHS selection.

S7 remains outside this critical path. After S6 qualification, run 3–5 predeclared matched S6/S7 cases only if S7 independently passes mesh, y+, convergence and grid gates. Never use S7 only where S6 fails and mix both as one homogeneous fidelity; that would create geometry-correlated method bias.

---

# 17. Final green-button checklist

S6 is approved for automated high-fidelity data generation only when every applicable box is green:

- [ ] Desktop/WSL RAM, swap, CPU, Linux-native storage, backup and full-campaign capacity are inventoried and verified.
- [ ] Phase-I geometry envelope and every live variable/semantic are frozen; any changed space has newly identified development/holdout sets.
- [ ] Repository mission and thermodynamics are internally consistent.
- [ ] Continuous-loft identity, geometry, TE, half-domain eligibility and full/half coefficient references are explicit.
- [ ] 29×75 identity/cache regression passes.
- [ ] A true coupled three-grid family fits the inventoried desktop/WSL memory limit.
- [ ] TMR discrepancy is resolved or honestly bounded.
- [ ] Physical/numerical TE policy is qualified.
- [ ] Farfield independence passes.
- [ ] Tip/outer-front smoothing policy is frozen from quantitative and visual evidence without moving the OML.
- [ ] Global wall law passes worst required conditions and final G*.
- [ ] Grid uncertainty is below coefficient and design-signal limits.
- [ ] Full residuals, CL/CD/CMy tails and conservation pass.
- [ ] Final G* atlas passes 100/100 development mesh audit.
- [ ] Fresh/deformed mesh and CFD comparison passes.
- [ ] Frozen 20-case development campaign reaches the declared yield unattended.
- [ ] Restart, cache, failure and collection tests pass.
- [ ] Holdout is opened once after hash freeze and reported without tuning.
- [ ] Every failure remains visible; zero false-safe cases.
- [ ] M9 regenerates all paper evidence reproducibly.
- [ ] Every step, including every failure, has JSON/Markdown/HTML and applicable paper-ready visual evidence.
- [ ] All required Claude Opus/max reviews and finding dispositions are retained.
- [ ] No threshold was edited in place or weakened for a case; any prospective policy revision has an ADR and uniform reclassification.
- [ ] No important artifact or codebase was deleted, overwritten or pruned without explicit exact-scope permission.

## Final judgement

The likely executable path is to test whether the `29×75×N97` mesh can serve as the finest member of a cheaper, genuinely coupled family. It is not yet known whether that family is accurate enough. This uncertainty is the first desktop question, not a detail to postpone.

If that family passes M2–M5, S6 has a credible path to a trustworthy, resource-constrained automated RANS factory with roughly 56–59 AERIS qualification solves plus five TMR solves. If it fails accuracy or memory, the research result is still clear: the inventoried desktop constraint is incompatible with the required structured wall-resolved fidelity, and more memory or a different method is required.

---

## Primary technical basis

- [pyGeo DVGeometry and spline-based geometry mapping](https://mdolab-pygeo.readthedocs-hosted.com/en/latest/DVGeometry.html)
- [pyGeo wing surfacing/global design-variable example](https://mdolab-pygeo.readthedocs-hosted.com/en/latest/advanced_ffd.html)
- [pyHyp options: wall spacing, marching distance, hyperbolic/elliptic modes and smoothing](https://mdolab-pyhyp.readthedocs-hosted.com/en/latest/options.html)
- [ADflow options: turbulence model, wall treatment, monitoring and convergence](https://mdolab-adflow.readthedocs-hosted.com/en/latest/options.html)
- [ADflow force and moment definitions](https://mdolab-adflow.readthedocs-hosted.com/en/latest/costFunctions.html)
- [ADflow nonlinear solver strategy](https://mdolab-adflow.readthedocs-hosted.com/en/latest/solvers.html)
- [NASA verification/validation and grid-convergence guidance](https://www.grc.nasa.gov/www/wind/valid/tutorial/overview.html)
- [NASA TMR NACA 0012 validation case](https://tmbwg.github.io/turbmodels/naca0012_val.html)
- [NASA TMR nested NACA 0012 grids](https://tmbwg.github.io/turbmodels/naca0012numerics_grids.html)
- [NIST exact binomial confidence limits](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbici.htm)
- [Secco et al.: structured mesh generation/deformation for aerodynamic optimization](https://mdolab.engin.umich.edu/bibliography/Secco2021a)
- [Microsoft WSL advanced settings](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
- [Microsoft guidance on Linux/Windows filesystem performance](https://learn.microsoft.com/en-us/windows/wsl/filesystems)
- [Microsoft WSL virtual-disk capacity and resize guidance](https://learn.microsoft.com/en-us/windows/wsl/disk-space)
- [Lyu and Martins: BWB aerodynamic optimization with sweep, chord, span, twist, trim and stability constraints](https://doi.org/10.2514/1.C032491)
- [Wauters et al.: UAV BWB design-under-uncertainty example using ±5° twist/dihedral variables](https://doi.org/10.1177/17568293221092139)
