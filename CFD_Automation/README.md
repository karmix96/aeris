# CFD_Automation

Automated CFD workflow — **geometry → mesh → solver → judgement** — for Class I and Class II
UAV wings (BWB and conventional), over angles of attack and Reynolds numbers. Subsonic first.
Open-source tools: pyGeo, ADflow, SU2.

Standalone; merged into AERIS when finished.

- **Stage 0** (done): starting values — `Stage 0_Decisions/` (open `STAGE0_DECISIONS.html` for the readable version).
- **Stage 1** (done): the wing generator — `geometry/` (see `geometry/README.md`).
- Next: Stage 2, the mesher.

```
Stage 0_Decisions/stage0_values.yaml     Stage 0 values
Stage 0_Decisions/STAGE0_DECISIONS.md    value, why, source
Stage 0_Decisions/STAGE0_DECISIONS.html  the same, as one readable page
Stage 0_Decisions/OPEN_DECISIONS.md      still to decide (Stage 0 and Stage 1)
geometry/decisions/*.md                  Stage 1 notes: trailing_edge, loft, root_section, conventional_ranges
geometry/                      Stage 1: config, code, tests, sets
references/                    sources (REFERENCES.md, references.bib)
```
