# Future AI and FFD extensions

These are deliberately outside the validated S6 core.

The implementation order and release gates are fixed in [ROADMAP.md](ROADMAP.md).

## FFD

pyGeo currently constructs each geometry directly from the BWB design variables.
A future free-form deformation layer can be useful for local shape optimization or
new variables that preserve topology.

The mesh route would remain unchanged:

1. FFD changes the exact pyGeo wall.
2. IDWarp, RBF, or S6 bounded deformation moves a validated volume mesh.
3. The same surface, interface, volume, and CFD gates decide acceptance.

FFD does not remove the need for mesh validation.

## AI

AI should first be used for decisions, not coordinate authority:

- rank atlas templates;
- predict deformation failure risk;
- predict CFD convergence risk;
- choose high-value CFD samples;
- build aerodynamic surrogates.

A graph neural network or neural operator could later predict mesh displacement.
It must still write a normal CGNS and pass every deterministic S6 gate. An AI-only
mesh is not accepted.

## Adoption rule

Add an AI or FFD backend only after the deterministic S6 pipeline is frozen and has
enough labeled cases. Compare it on the same locked development and holdout sets.
Adopt it only if it reduces time or failures without weakening any gate.

For this campaign, AI is likely to save more compute through adaptive CFD sampling
and aerodynamic surrogates than by replacing a deformation step that already takes
seconds.
