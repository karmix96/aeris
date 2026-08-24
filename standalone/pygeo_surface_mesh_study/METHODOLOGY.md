# AIAA-grade methodology: geometry-conditioned pyGeo surface-mesh laws

## Scope and claim

This is a deterministic computer experiment for the following bounded claim:

> For the canonical clean BWB outer mold line, fixed station airfoils, fixed
> cap4 OML topology, fixed quad-only airfoil-face tip closure, and registered
> geometry domain, predict the surface-quality
> metrics at each member of the L1-L5 mesh family, select the coarsest family
> member that satisfies every user-authored limit, and estimate which
> individual numerical mesh controls are most useful for measured retry actions.

The study does **not** claim CFD solution independence, universal airfoil
generality, or validity outside the registered factor ranges. Surface-cell
quality is a meshing response, not a flow-solution quantity; Richardson
extrapolation and GCI belong to a separate CFD solution-verification study.

## Factor audit

### The original 17 generator controls

The original screening study exposed these 17 stored BWB controls:

1. root chord c1;
2. c2/c1;
3. c3/c1;
4. c4/c1;
5. b_total_m;
6. outer-panel fraction b3_ratio;
7. remaining-inner-span split split_ratio;
8. inner leading-edge sweep;
9. middle leading-edge sweep;
10. outer leading-edge sweep;
11. root twist;
12. b1 twist;
13. b2 twist;
14. tip twist;
15. b1 dihedral;
16. b2 dihedral;
17. tip dihedral.

That list describes the data structure, but it is not the defensible
inferential dimension of the current canonical geometry. The canonical
enforce_flat_root_panel invariant pins b1 dihedral to zero. A zero-width factor
cannot have a sensitivity distribution. The clean-OML study therefore has
**16 independent factors**, with b1 dihedral stored explicitly as fixed.

The three elevon geometry fields are also fixed. They belong to a separate
split-CAD/topology study; with physical CAD disabled they do not alter the
neutral outer mold line. Including them here would create repeated geometries
and a false impression of statistical information.

b_total_m is treated according to the implementation, where it is the
**semispan** and the full span is 2b. The public study factor is therefore
named semi_span_m, avoiding the ambiguous internal name.

### The 16 independent attribution factors

| Group | Public factor | Aeris field | Range | Baseline |
|---|---|---|---:|---:|
| Scale | root chord [m] | c1_m | 0.70-1.10 | 0.90 |
| Chord | b1/root chord ratio | c2_ratio | 0.55-0.80 | 0.675 |
| Chord | b2/root chord ratio | c3_ratio | 0.30-0.55 | 0.425 |
| Chord | tip taper ratio | c4_ratio | 0.08-0.20 | 0.14 |
| Span | semispan [m] | b_total_m | 0.75-1.25 | 1.00 |
| Span | outer-panel span fraction | b3_ratio | 0.40-0.55 | 0.475 |
| Span | inner remaining-span split | split_ratio | 0.40-0.60 | 0.50 |
| Sweep | inner LE sweep [deg] | sw1_deg | 20-40 | 30 |
| Sweep | middle LE sweep [deg] | sw2_deg | 15-35 | 25 |
| Sweep | outer LE sweep [deg] | sw3_deg | 5-25 | 15 |
| Twist | root twist [deg] | twist_b0_deg | -1 to 1 | 0 |
| Twist | b1 twist [deg] | twist_b1_deg | -3 to 0 | -1.5 |
| Twist | b2 twist [deg] | twist_b2_deg | -5 to -1 | -3 |
| Twist | tip twist [deg] | twist_b3_deg | -8 to -2 | -5 |
| Dihedral | b2 dihedral [deg] | dihedral_b2_deg | 0-6 | 3 |
| Dihedral | tip dihedral [deg] | dihedral_b3_deg | 0-10 | 5 |

The inferential baseline is the center of the feasible domain. A zero-sweep
geometry is useful as a mesher smoke anchor, but it is outside the current
production sweep domain and cannot provide symmetric derivatives for that
domain.

### Realised descriptors recorded in every case

Attribution uses independent factors. Deployment/applicability uses the
geometry actually seen by the mesher. Every case therefore records:

- full span, area, aspect ratio \(AR=(2b)^2/S\), and span/root-chord ratio;
- total and panel taper ratios;
- panel and break span fractions;
- three sweep magnitudes and two sweep jumps;
- nondimensional chord, LE, and TE rates/curvatures;
- twist and dihedral station values and panel rates;
- minimum/maximum/range of realised thickness ratio;
- minimum/maximum dimensional thickness;
- thickness-ratio and camber-ratio rates across semispan.

Independent variables and derived descriptors must not be mixed in an
unregularized causal regression because many are algebraically dependent.

## Fixed-airfoil thickness limitation

The station mapping is fixed to MH-91, MH-91, E374, and NLF1015 at b0-b3.
Consequently, the study measures the thickness distribution presented by that
loft and its interaction with planform station placement, but it **cannot
identify a causal independent airfoil-thickness-ratio effect**. The agent law
contains the exact airfoil signature and must reject a different signature.

A general thickness law requires a separately pre-registered morphology
campaign that independently perturbs thickness and camber about each base
profile while preserving LE/TE and smoothness. Combining that future campaign
with this one without a block/categorical term would be statistically invalid.

## Experimental design and exact count

The registered campaign has two layers because they answer different causal
questions. The geometry-law layer asks how geometry moves mesh quality across
the bundled L1-L5 mesh family. The mesh-control layer asks which individual
mesh knob should move when a measured candidate fails.

Geometry-law layer:

| Block | Geometry cases | Purpose |
|---|---:|---|
| Center baseline | 1 | Reference and reproducibility anchor |
| Nine-point OFAT curves | 16 x 8 = 128 | Signed deltas, local slopes, curvature, non-monotonicity |
| All two-factor corners | C(16,2) x 4 = 480 | Direct pair non-additivity, without response-based pair selection |
| Scrambled-Sobol training | 1,024 | All 16 variables change simultaneously; fit global laws |
| Independent IID uniform validation | 512 | Untouched holdout for prediction and false-accept audits |
| **Geometry-law total** | **2,145 geometries** | |
| Five levels per geometry | **10,725 meshes** | Complete L1-L5 response data |

Mesh-control layer:

| Block | Cases | Purpose |
|---|---:|---|
| Joint 20-factor scrambled-Sobol training | 2,048 | Fit geometry-conditioned knob effects |
| Independent 20-factor IID uniform validation | 1,024 | Audit knob-action predictions and false accepts |
| **Mesh-control total** | **3,072 meshes** | One explicit mesh per sampled case |

The complete registered execution plan is therefore **5,217 cases** and
**13,797 surface-mesh builds**.

An exhaustive two-level factorial would require \(2^{16}=65,536\) geometries
before mesh refinement and is unnecessary for a second-order bounded law. The
design instead measures every pair explicitly and samples multiway combinations
globally.

If pre-declared validation criteria fail, this study revision remains
non-deployable. Enrichment must be registered as a new training campaign with
a fresh independent validation set; the original holdout is not tuned against
and then reused.

## Delta definition

For factor \(x_i\), define the signed normalized coordinate

\[
\xi_i =
\begin{cases}
(x_i-x_{i,0})/(x_{i,0}-x_{i,L}), & x_i<x_{i,0},\\
(x_i-x_{i,0})/(x_{i,H}-x_{i,0}), & x_i\ge x_{i,0}.
\end{cases}
\]

Thus -1 is the low bound, 0 is baseline, and +1 is the high bound.
For metric \(y_m\),

\[
\Delta y_{im}(\xi)=y_m(x_0,\ldots,x_i(\xi),\ldots)-y_m(\mathbf{x}_0).
\]

The report retains absolute delta, relative delta when the baseline is
non-zero, the raw nine points, the fitted baseline slope in normalized and
physical units, curvature, trend, and passing interval. No percentage change
is used near a zero baseline.

For a limit \(L_m\), use an oriented signed margin:

\[
g_m =
\begin{cases}
(L_m-y_m)/s_m, & y_m\le L_m\text{ required},\\
(y_m-L_m)/s_m, & y_m\ge L_m\text{ required},
\end{cases}
\]

where \(s_m=\max(|L_m|,|y_m|,\epsilon)\). A mesh passes when every
\(g_m\ge0\). The operational response is \(g_{min}=\min_m g_m\).

## Interaction definition

Every factor pair is evaluated at four low/high corners. At one corner, the
direct non-additivity residual is

\[
I_{ij,m}=y_m(x_i,x_j)-[y_m(x_i)+y_m(x_j)-y_m(\mathbf{x}_0)].
\]

A large residual means an OFAT law is not safely additive. The global
surrogate also estimates a second-order interaction coefficient and a
second-order Sobol contribution for every pair. Agreement between the direct
corner residual and global estimate is evidence; disagreement triggers a new
registered campaign or a higher-order/local model.

## Global response law and influence

For each mesh level and metric, normalized factors are expanded in an
orthonormal Legendre basis over independent uniform factors:

\[
\hat y =
\beta_0 + \sum_i \beta_i\phi_1(\xi_i)
+ \sum_i \beta_{ii}\phi_2(\xi_i)
+ \sum_{i<j}\beta_{ij}\phi_1(\xi_i)\phi_1(\xi_j).
\]

For 16 factors this has 153 coefficients. The 1,024 training cases give 6.7
observations per coefficient. Ridge strength is chosen only by deterministic
10-fold cross-validation inside the training set.

Because the basis is orthonormal, surrogate variance contributions are
coefficient squares. For factor i,

\[
S_i = (\beta_i^2+\beta_{ii}^2)/V, \qquad
S_{T_i}=S_i+\sum_{j\ne i}\beta_{ij}^2/V.
\]

- \(S_i\): main effect;
- \(S_{T_i}\): main effect plus every represented interaction;
- \(S_{T_i}-S_i\): interaction burden.

Reference-level indices include 95% fixed-design residual-bootstrap intervals
from 200 replicates. They quantify finite-design/surrogate uncertainty, not
physical randomness.
Influence is reported **per metric**. After limits are inserted, the primary
operational ranking is the total-effect ranking for \(g_{min}\), not an
arbitrary average across unrelated quality metrics. OFAT slope, pair residual,
and Sobol total effect are retained as separate evidence rather than collapsed
into one opaque score.

## Validation and uncertainty

The 512 IID uniform validation geometries are not used for fitting or ridge
selection.
Half calibrate an absolute residual bound; half audit:

- normalized RMSE;
- R-squared;
- empirical interval coverage;
- maximum absolute error;
- conservative false accepts and false rejects.

Default deployment gates are normalized RMSE <= 0.05, R-squared >= 0.90,
empirical coverage consistent with the target, zero conservative false accepts
in the audit subset, and a one-sided exact 95% false-accept probability upper
bound <= 0.02 when the model predicts any passes. These thresholds are
pre-registered in YAML. Failure marks the law non-deployable; it does not
silently relax a metric limit.

The simulator is deterministic, so these intervals quantify finite-design and
surrogate error, not physical aleatory uncertainty. Process-level determinism
and output hashes must be checked separately.

## Registered surface-quality limits

The acceptance limits are hard pre-volume surface-mesh gates, not claims of CFD
solution independence. They combine four considerations:

1. algebraic quad-quality guidance from the Verdict/CUBIT/Knupp metric family;
2. CFD meshing practice for skewness, aspect ratio, and smooth size transition;
3. OpenFOAM-style hard validity floors for determinant/twist-like quantities;
4. empirical pre-flight screening of the fixed cap4 OML plus quad-only
   airfoil-face BWB tip topology.

The OML receives tighter shape/angle limits because it is the aerodynamic
surface that seeds the volume mesh. The collar-free airfoil-face tip cap
receives separate relaxed limits because it is a small all-quad closure around
the blunt, thin BWB leading/trailing-edge wrap. Applying near-square
finite-element quad limits to that cap would
reject the verified topology rather than identify a CFD-relevant failure.

| Metric | Limit | Role |
|---|---:|---|
| `oml.min_shape_metric` | >= 0.08 | Rejects highly collapsed OML cells while allowing structured aerodynamic stretching. |
| `oml.min_scaled_jacobian` | >= 0.50 | CUBIT/Verdict acceptable lower bound for linear quads. |
| `oml.min_triangle_normal_alignment` | >= 0.95 | Requires the two triangles inside each quad to be nearly co-planar and consistently oriented. |
| `oml.max_equiangle_skewness` | <= 0.50 | Keeps OML skewness in the good mapped-quad band. |
| `oml.max_aspect_ratio` | <= 25 | Allows aerodynamic surface stretching but rejects extreme tangential anisotropy. |
| `oml.max_growth_ratio` | <= 2.50 | Hard upper gate on adjacent surface-size jumps; 1.1-1.5 remains the design target. |
| `oml.max_adjacent_normal_angle_deg` | <= 170 | Fold/edge-wrap sentinel; not interpreted as a curvature-resolution target at LE/TE wraps. |
| `tip.min_shape_metric` | >= 0.03 | Non-degenerate tip-cap floor for the small closure block. |
| `tip.min_scaled_jacobian` | >= 0.03 | Positive, non-collapsed tip-cap Jacobian floor. |
| `tip.min_triangle_normal_alignment` | >= 0.95 | Same quad-orientation/planarity gate as OML. |
| `tip.max_equiangle_skewness` | <= 0.98 | Absolute tip-cap skewness gate; tighter values are reported but not used as a hard topology rejection. |
| `tip.max_aspect_ratio` | <= 10 | Keeps the closure blocks below the usual non-boundary-layer CFD aspect-ratio target. |
| `tip.max_growth_ratio` | <= 2.50 | Same hard size-jump gate as OML. |
| `tip.max_adjacent_normal_angle_deg` | <= 10 | Tip cap should remain locally smooth; large jumps indicate a bad closure. |

These limits deliberately separate hard acceptance from design aspiration. For
example, surface growth rates near 1.2 and skewness below 0.8 are better design
targets, but setting them as absolute gates would make the current structured
tip closure non-deployable before the DOE can identify which geometry/mesh
variables cause the excursions. The study therefore records the continuous
metrics and trains laws on them; acceptance only rejects meshes that cross the
pre-registered hard limits.

The limit set is valid only for this fixed airfoil signature, cap4 OML
topology, and airfoil-face structured tip closure.
Changing the airfoils, enabling split physical CAD, changing the tip topology,
or using the surface mesh as final CFD evidence requires a new pre-registration
and a separate CFD solution-verification study.

## Why every geometry runs L1-L5

The research campaign evaluates the complete family for every geometry.
Stopping after the first passing level would make fine-level observations
missing-not-at-random and bias refinement laws. Complete ladders permit honest
level-transition, non-monotonicity, and coarsest-passing-level analysis.

Quality extrema need not improve monotonically under refinement because the
identity/location of the worst cell can change. The study therefore records
non-monotone cases and fits each level separately. It does not force a
monotonic model.

The four resolution controls are coupled into one registered family. The
resulting agent law selects a family level; it does not prove which individual
resolution knob is causal. The added mesh-control DOE therefore varies
individual controls directly while preserving the same OML, airfoil, topology,
and distribution family.

## Geometry-conditioned mesh-control DOE

The second law layer is explicitly designed for autonomous retry actions. It
keeps the mesher topology and distribution model fixed and varies only four
numerical controls:

- chordwise/block-side points;
- spanwise panels per realised source-section interval;
- cap wrap points;
- LE/TE curvature-blend control (`tip_radial_points` compatibility field).

Pre-flight structural screening bounds the cap-wrap and curvature-blend ranges
to the verified nonfolding airfoil-face tip domain. Values outside that domain
fold the thin BWB LE/TE wrap corners and are excluded from this law; they
require a separate topology-redesign campaign.

Each mesh-control case samples all 16 geometry variables and these four mesh
variables jointly. The training design is a 20-dimensional scrambled Sobol
sequence with 2,048 cases. The validation design is an independent
20-dimensional IID uniform sample with 1,024 cases. Each case runs one explicit
mesh named mesh_control, not the full L1-L5 ladder.

For each metric, the fitted law uses the same orthonormal quadratic Legendre
form as the geometry layer, now with \(p=20\) factors:

\[
1 + 2p + \binom{p}{2} = 231
\]

coefficients. The 2,048 training samples provide 8.9 observations per
coefficient before regularization. Ridge strength is still selected only by
training-set cross-validation, and deployment still requires the independent
validation/conformal false-accept gates.

The emitted mesh-control law reports, per metric:

- total and first-order effect of each mesh knob;
- the local center derivative and the beneficial local direction implied by
  the metric limit;
- the strongest geometry-mesh interactions, e.g. whether sweep or dihedral
  changes make a specific knob more important.

The beneficial direction is a local derivative at the registered center, not a
global monotonicity guarantee. The agent must combine it with the current
geometry, the interaction table, the predicted uncertainty bound, and measured
QC results.

## Autonomous-agent contract

The generated agent_mesh_law.json is usable only when all gates pass. An agent
must:

1. read the current 16 factors and realised descriptors;
2. verify every factor lies inside its registered range;
3. verify exact airfoil and topology signatures;
4. evaluate conservative predictions for L1-L5 and, when deployable, the
   geometry-conditioned mesh-control law;
5. choose the coarsest level predicted to pass every metric;
6. generate the mesh and calculate the actual metrics;
7. accept only measured pass results;
8. if measured metrics fail, identify the failed metric family and use the
   mesh-control action ranking plus geometry-mesh interactions to choose the
   smallest allowed knob move in the beneficial direction;
9. regenerate and remeasure; if the knob law is absent, non-deployable, or
   the retry remains outside the audited margin, move to the next predicted
   passing L-level;
10. stop and escalate if L5 fails, the response is non-monotone in a harmful
   way, or the geometry is outside the law domain.

The law is decision support, never a replacement for mesh QC.

## Reproducibility and paper reporting

The run manifest hashes the study YAML, canonical geometry config, study code,
mesher code, BWB generator code, pyGeo adapter, and exact airfoil files. It
records Python, platform, and package versions. Case identities are
deterministic and runs resume only under the same fingerprint.

Report geometry failures, rejected lofts, missing cases, newly registered
enrichment campaigns, and L5 failures. Do not analyze only successful meshes.
Archive raw case JSON, surface reports, plans, manifest, law artifact, and
plotting scripts.

## Primary methodological references

- M. D. McKay, R. J. Beckman, and W. J. Conover, "A Comparison of Three
  Methods for Selecting Values of Input Variables in the Analysis of Output
  from a Computer Code," *Technometrics*, 1979.
  https://doi.org/10.1080/00401706.1979.10489755
- A. Saltelli et al., "Variance Based Sensitivity Analysis of Model Output:
  Design and Estimator for the Total Sensitivity Index," *Computer Physics
  Communications*, 2010. https://doi.org/10.1016/j.cpc.2009.09.018
- J. Sacks et al., "Design and Analysis of Computer Experiments,"
  *Statistical Science*, 1989. https://doi.org/10.1214/ss/1177012413
- P. M. Knupp, "Algebraic Mesh Quality Metrics," *SIAM Journal on Scientific
  Computing*, 2001. https://doi.org/10.1137/S1064827500371499
- AIAA G-077-1998, *Guide for the Verification and Validation of
  Computational Fluid Dynamics Simulations*; see NASA's V&V tutorial:
  https://www.grc.nasa.gov/www/wind/valid/tutorial/tutorial.html

