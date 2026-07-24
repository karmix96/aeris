# pyGeo as the master geometry for Aeris/AVL

Run directory: `/home/mike/Desktop/Start_Up/Code/v.0.1_Project/artifacts/pygeo_avl_study/full_study_20260723T155248+0300`  
Baseline: `/home/mike/Desktop/Start_Up/Code/v.0.1_Project/configs/geometry/paper1_bwb_naca_stations.yaml`  
Environment: Python 3.13.9, pyGeo 1.17.0, pySpline 1.5.4, AeroSandbox 4.2.10, NeuralFoil 0.3.2.

## Decision

**Use pyGeo as the master 3-D geometry and retain AeroSandbox as a complementary AVL serializer plus NeuralFoil interface.** The standalone chain works end to end:

`design variables -> pyGeo loft -> physical-span slices -> CST -> NeuralFoil -> CDCL + strip integration -> AVL`.

Do not replace the current path by merely handing pyGeo's authored control stations to AVL. For `kSpan > 2`, extract sections from the *realised B-spline surface*. The recommended initial setting is `kSpan=3`, exact AeroSandbox-compatible station frames, CST order 8, and at least 17 AVL sections (then demonstrate convergence for each design family).

This is a useful PhD contribution because the master CAD loft and the aerodynamic section polars are now generated from the same realised geometry. The defensible novelty is **geometry-consistent, section-resolved viscous drag correction**, not a claim that AVL becomes a nonlinear viscous solver.

## What changed in the geometry

`kSpan=2` is the control case: it reproduces piecewise-linear lofting. `kSpan=3/4` smooth the spanwise control net, so interior authored sections are control points rather than guaranteed interpolation points. This changes chord, sweep, twist, camber transition, area, and hence AVL loads.

| geometry | area_delta_pct | surface_rms_mm | surface_p95_mm | surface_max_mm | max_plane_warp_chord | max_cst_rms_chord | cst_valid_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pyGeo kSpan=2 | -0.0480 | 0.4451 | 0.8981 | 3.0916 | 0.0045 | 6.120e-04 | 100.0000 |
| pyGeo kSpan=3 | -0.0661 | 0.6799 | 1.3230 | 8.4711 | 0.0042 | 7.506e-04 | 100.0000 |
| pyGeo kSpan=4 | -0.0640 | 0.8630 | 1.7853 | 10.5020 | 0.0036 | 7.274e-04 | 100.0000 |
| pyGeo global-y | -0.0625 | 0.6701 | 1.3197 | 8.4345 | 0.0058 | 7.482e-04 | 100.0000 |

The baseline smooth loft (`kSpan=3`) changes projected reference area by **-0.066%** relative to the intended AeroSandbox model. Its bidirectional outer-surface RMS difference is **0.680 mm**. The piecewise-linear pyGeo control has **0.445 mm** RMS difference.

The extracted curves are not perfectly planar when frames, twist, dihedral, and airfoil shape all vary through a B-spline. That is why the bridge records a plane-warp metric and explicitly projects onto the local chord/span frame before CST fitting.

Visual evidence: [geometry comparison](geometry/geometry_comparison.png), [section/CST overlays](geometry/section_reconstruction.png). The recommended baseline CAD is [IGES](geometry/baseline_kspan3.igs), with [Tecplot surface/control data](geometry/baseline_kspan3.dat).

## CST and NeuralFoil

| cst_order | median_RMS | worst_RMS | worst_point | valid_pct |
| --- | --- | --- | --- | --- |
| 3.0000 | 9.411e-04 | 0.0012 | 0.0082 | 100.0000 |
| 4.0000 | 7.378e-04 | 9.383e-04 | 0.0080 | 100.0000 |
| 5.0000 | 5.105e-04 | 8.521e-04 | 0.0079 | 100.0000 |
| 6.0000 | 3.307e-04 | 7.809e-04 | 0.0078 | 100.0000 |
| 7.0000 | 2.231e-04 | 7.036e-04 | 0.0076 | 100.0000 |
| 8.0000 | 1.855e-04 | 6.618e-04 | 0.0075 | 100.0000 |
| 10.0000 | 1.648e-04 | 5.905e-04 | 0.0072 | 100.0000 |
| 12.0000 | 1.479e-04 | 5.357e-04 | 0.0069 | 100.0000 |

CST order 8 is the practical default: it is already the Aeris convention, is rich enough for these NACA-to-NACA blended sections, and is converted through coordinates to NeuralFoil's canonical eight-weight Kulfan representation. The conversion is deliberately not a coefficient copy because the two parameterisations are not identical.

The NeuralFoil CSV and plot retain `analysis_confidence`; the current production source does not gate on it. The raw NeuralFoil core is incompressible, so its `mach` argument has no effect in the current Aeris source. AeroSandbox's extended wrapper adds its own compressibility correction. At the audited Mach 0.103, the raw-core max CD change was 0.000e+00, while the extended-interface max CD change was 0.000e+00.

The current batched strip query also evaluates all strips of one shape at their median Reynolds number. Across Re=2e5..2e6, the measured worst CD error in this audit was **37.50%**. The standalone source groups by both shape and Reynolds bin instead.

Visual/numerical evidence: [polar plot](cst_neuralfoil/neuralfoil_polars.png), [polar CSV](cst_neuralfoil/neuralfoil_polars.csv), [CDCL audit](cst_neuralfoil/cdcl_fit_audit.csv), and [Re batching audit](implementation_audit/neuralfoil_batch_reynolds_audit.csv).

## AVL comparison at alpha = 4 deg

| geometry | CL | CD_induced | CD_profile_integrated | CD_corrected | L_over_D_corrected | delta_CL_pct_vs_intended | delta_CDi_pct_vs_intended | delta_CDcorr_pct_vs_intended |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pyGeo kSpan=2 | 0.2987 | 0.0069 | 0.0058 | 0.0127 | 23.5415 | -1.9882 | -5.3663 | -2.7372 |
| pyGeo kSpan=3 | 0.2983 | 0.0069 | 0.0058 | 0.0127 | 23.5498 | -2.1325 | -5.6302 | -2.9144 |
| pyGeo kSpan=4 | 0.2979 | 0.0069 | 0.0058 | 0.0126 | 23.5658 | -2.2572 | -5.8408 | -3.1041 |
| AeroSandbox production | 0.1981 | 0.0032 | 0.0058 | 0.0090 | 22.0661 | -35.0230 | -56.1561 | -31.2082 |
| AeroSandbox intended | 0.3048 | 0.0073 | 0.0057 | 0.0130 | 23.3616 | 0.0000 | 0.0000 | 0.0000 |

`CD_corrected = CDind_AVL + CDprofile_NeuralFoil` is the primary viscous-corrected result. AVL's own CDCL integration is retained as an independent cross-check. With profile forces actually enabled, AVL `CDvis` and the strip-integrated profile drag differed by **4.10%** in the controlled case.

The production runner currently sends `v` in AVL's OPER options. AVL starts with viscous/profile forces **on**, so that command toggles them **off**: the controlled production-semantics run produced `CDvis=0.00000` despite injecting 17 section polars. Omitting that toggle produced `CDvis=0.00553`. The surface-level zero placeholder did not change the result when every section contained CDCL.

Visual/numerical evidence: [AVL plot](avl_comparison/avl_geometry_comparison.png), [all AVL cases](avl_comparison/avl_geometry_comparison.csv), and [CDCL semantics](avl_comparison/cdcl_semantics_audit.csv).

## Section convergence and DOE stress test

At 17 extracted sections, the worst error against the densest tested model was **1.903% in CL** and **1.633% in CDi** over the tested angles. See [convergence plot](section_convergence/section_convergence.png) and [CSV](section_convergence/section_convergence.csv).

The wide-bound DOE completed **24/24** cases; failures: **0**. Across successful cases, the 95th-percentile absolute kSpan=3 area shift was **0.263%**, the alpha=4 deg pyGeo-vs-intended-ASB CL shift was **2.597%**, and the CDi shift was **7.785%**. Worst extracted-plane warp was **0.828% chord** and worst CST RMS was **0.078% chord**. See [DOE plot](doe_stress/doe_stress.png) and [CSV](doe_stress/doe_stress.csv).

## Existing-code findings that must be resolved before integration

1. `station_airfoils` is configured as `naca23012, naca4412, naca2412, naca0012`, but the current section builder produced only `naca23012`. The standalone intended case applies the four configured shapes without changing Aeris.
2. The AVL `v` option currently disables the injected CDCL contribution. Strip post-integration still creates a corrected total, but the claimed AVL-vs-strip cross-check is otherwise ineffective.
3. A relative AVL working directory causes AeroSandbox's AFILE path to be resolved twice after AVL changes directory. The standalone runner resolves every case directory to an absolute path.
4. The raw NeuralFoil core ignores Mach; use the AeroSandbox extended interface if its compressibility model is desired, and document that this is a wrapper correction rather than network output.
5. The current NeuralFoil batch query collapses different strip Reynolds numbers to one median Re and does not use confidence as a QC gate.
6. Audit the negative-side CDCL endpoint selector: with multiple consecutive high-drag points it can choose another point outside the intended threshold. Both production and symmetric corrected fits are saved for comparison.

## Interpretation limits

- CDCL changes profile drag only. It does **not** change AVL circulation, CL(alpha), stall, separation, or nonlinear lift. CLAF can alter the linear section lift slope but is not a nonlinear viscous coupling.
- For a swept, low-aspect-ratio BWB, assigning a 2-D polar to AVL's local strip `cl` is a model assumption. The AVL documentation itself warns that local section lift and stall interpretation is ambiguous for strongly three-dimensional wings.
- NeuralFoil is a fast XFoil-trained surrogate. Confidence filtering, XFoil spot checks, and selected RANS/experimental validation remain necessary for thesis-grade claims.
- A smooth loft is not automatically “more accurate” than a piecewise model. It is a new geometry definition whose area and aerodynamic shifts must be included in the design variables and convergence/validation story.

## Recommended integration boundary

Keep the implementation boundary narrow:

1. pyGeo owns the master outer mould line and CAD export.
2. A deterministic extractor returns normalised section coordinates, CST coefficients, physical LE/chord/twist, plane-warp QC, and a stable shape ID.
3. AeroSandbox receives those realised sections only to serialize/run AVL and to access its maintained NeuralFoil wrapper.
4. Run both section CDCL injection and independent strip-area profile-drag integration; require agreement within a declared tolerance.
5. Store loft order, section count, CST order/error, NeuralFoil model/version/confidence, Re/Mach, and all raw AVL files in every case manifest.

Primary references: [MIT AVL user primer](https://web.mit.edu/drela/Public/web/avl/AVL_User_Primer.pdf), [pyGeo documentation](https://mdolab-pygeo.readthedocs-hosted.com/), [NeuralFoil repository](https://github.com/peterdsharpe/NeuralFoil), and [NeuralFoil paper](https://arxiv.org/abs/2503.16323).
