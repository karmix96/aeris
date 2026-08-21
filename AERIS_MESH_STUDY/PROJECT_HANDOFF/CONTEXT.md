# Context

## User goal

The target is not one attractive mesh. It is a reproducible open-source process
that can produce useful CFD results for approximately 10,000 configurations in a
design-space exploration campaign, with no manual mesh repair and explicit
quality/failure accounting.

## Why S6 was created

The earlier studies showed that direct structured marching can work very well but
is sensitive to the surface topology and spanwise interface law. Fully rebuilding
every mesh also makes 10,000-case reliability harder to control. S6 therefore
uses a bounded atlas of already validated S1/pyHyp volume meshes, deforms the best
candidate to an exact target surface, checks every result deterministically, and
falls back to target-specific remeshing when deformation is not acceptable.

This follows the practical pattern used in large aerodynamic optimization and
design studies: parameterized CAD/FFD-like geometry changes, robust volume-mesh
warping, strict mesh checks, solver automation, and remeshing/fallback outside the
safe deformation envelope. The atlas is tailored to large geometric variation;
one universal seed is not assumed.

## Current architecture

1. pyGeo creates the geometry from design variables.
2. Maximin atlas metadata orders robust structured templates.
3. S6 maps an affine frame and bounded volume columns to the exact target surface.
4. Hard surface/interface/volume/Jacobian checks accept or reject the mesh.
5. Routing tries another template, then target-specific S1/pyHyp fallback.
6. ADflow runs RANS-SA and deterministic CFD/y+ acceptance.
7. Atomic reports, hashes, checkpoints, caches, Slurm, and collection support
   unattended operation.

## FFD, IDWarp/RBF, and AI memory

- Current geometry is pyGeo parameterized B-spline construction, not an FFD
  workflow.
- Current volume movement is custom bounded column deformation, not IDWarp or a
  generic RBF warper.
- FFD plus IDWarp/RBF remains a valid future comparison or replacement if S6's
  safe envelope is too small.
- AI can later select templates and predict deformation failure/quality. A graph
  network or neural operator could predict displacement, but every output still
  needs complete deterministic checks and fallback.
- AI is likely to save more total campaign cost in case selection and aerodynamic
  surrogates than by replacing an already fast deformation step.
- Planned paper direction: "Quality-Constrained AI-Assisted Mesh Atlas
  Deformation for Automated CFD Design Campaigns."

## Literature and method record

The detailed paper-by-paper notes, links, and applicability limits are in:

- `../04_strategy_studies/S6_bounded_mesh_atlas/RESEARCH.md`
- `../04_strategy_studies/S6_bounded_mesh_atlas/STUDY.md`
- `../04_strategy_studies/S6_bounded_mesh_atlas/FUTURE_EXTENSIONS.md`
- `../01_references/`
- `../papers/`

Do not claim an implementation is "according to a paper" only because it shares
a name. Check the equations, boundary conditions, topology assumptions, quality
definition, and experiment controls against the original source. S6 is a
tailored engineering synthesis, not a verbatim implementation of one paper.

## Working rules for future agents

- Preserve unrelated dirty worktree changes.
- Use existing AERIS geometry and shared gates rather than cloning behavior.
- Keep development and hold-out evidence separate.
- Keep smoke, fine, and production numbers separate.
- Record failed attempts, not only winners.
- Treat geometry fidelity, mesh validity, CFD convergence, y+, and grid
  convergence as separate gates.
- Update this folder and `memories/memories.md` after material results.
