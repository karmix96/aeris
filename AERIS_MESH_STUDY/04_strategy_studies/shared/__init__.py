"""The shared experimental control for the six independent strategy studies.

ADR-0011 section 4 draws the independence line. **Shared** — one implementation,
used by all six:

- ``ingestion``    CAD/section ingestion and 2D->3D mapping through the wing
- ``qc``           QC metric *definitions*, orientation, artifact writing
- ``gates``        gate thresholds and the pass/fail checklists
- ``geometry_sets``the locked geometry sets and their identity rule
- ``pyhyp_runner`` the pyHyp invocation and its argument construction
- ``verify``       the verifier

**Per-strategy**, and therefore absent from this package: all blocking and
block-graph construction, tip closure, spanwise distribution and station
placement, chordwise laws and point counts, any smoothing/projection/deformation
the method calls for, and the strategy's own pyHyp-facing surface staging.

Geometry is generated the same way for every strategy; how each turns it into
blocks is the experiment. If each study wrote its own section reader and its own
quality metric, the comparison would measure readers and metrics rather than
meshing methods.

**This line is not re-litigated mid-study.** If a strategy genuinely cannot work
within it, that is a finding to record and raise — not a reason to copy shared
code into a strategy folder, or strategy code into this package.

Usage from a strategy module::

    import sys
    from pathlib import Path
    STUDIES = Path(__file__).resolve().parents[1]
    REPO_ROOT = STUDIES.parents[1]
    sys.path.insert(0, str(REPO_ROOT / "src"))
    sys.path.insert(0, str(STUDIES))

    from shared.ingestion import section_loop_2d, feature_split_sides
    from shared.qc import qc_blocks, orient_blocks_consistently
"""

__all__ = ["ingestion", "qc", "gates", "geometry_sets", "pyhyp_runner", "verify"]
