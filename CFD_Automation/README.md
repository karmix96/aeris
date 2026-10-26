# CFD_Automation

Automated CFD workflow — **geometry → mesh → solver → judgement** — for Class I and Class II
UAV wings (BWB and conventional), over angles of attack and Reynolds numbers. Subsonic first.
Open-source tools: pyGeo, ADflow, SU2.

Standalone; merged into AERIS when finished.

- **Stage 0** (done): starting values — `decisions/`.
- **Stage 1** (done): the wing generator — `geometry/` (see `geometry/README.md`).
- Next: Stage 2, the mesher.

```
decisions/stage0_values.yaml   Stage 0 values
decisions/STAGE0_DECISIONS.md  value, why, source
decisions/*.md                 Stage 1 notes: trailing_edge, loft, root_section, conventional_ranges
decisions/OPEN_DECISIONS.md    still to decide
geometry/                      Stage 1: config, code, tests, sets
references/                    sources (REFERENCES.md, references.bib)
```
