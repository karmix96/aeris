# M2 terminal report — NO-GO

The candidate `17×43×61 → 23×57×73 → 29×75×97` family meets its coupled
refinement target (`r_eff = 1.308, 1.311`) and the inventoried desktop resource
screen. It does not meet mathematical mesh validity.

Written ADF-CGNS files were closed, reopened independently with cgnsUtilities,
and rescored with the repository signed-volume/scaled-Jacobian authority. The
nominal finest B0 mesh contained 18 inverted cells. The best controlled B3
attempt (`epsE=3`, `epsI=6`, ten protected constant-spacing layers) still had
six inverted cells and `qmin=-0.3114`. Tip-cap-only smoothing and the governed
`epsE` ladder did not remove the defect.

Therefore the required A/B/C/E family screen stops at nominal geometry A and no
CFD canary is authorized. The next scientific action is a versioned tip/collar
topology redesign, not a weaker zero-volume gate.
