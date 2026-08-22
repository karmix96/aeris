"""One-shot migration of `04_strategy_prototypes/stage02_common.py` per ADR-0011 §4.1.

This script is kept as the **provenance record** of the migration, not as a build
step. It was run once, on 2026-08-14, to create `04_strategy_studies/shared/` and
`04_strategy_studies/S1_tip_first/s1_internals.py`.

Why a script rather than retyping: ADR-0011 requires that **metric definitions and
gate thresholds migrate unchanged**, so results stay comparable to what is already
recorded in `status`. Extracting the exact source text guarantees that; retyping
does not. Every function that moves is copied byte-for-byte, and the two deliberate
edits (stripping S1's chordwise defaults out of `feature_split_sides`) are applied
explicitly and printed, so they are auditable.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/migrate_from_stage02.py

Re-running it overwrites the generated modules with the Stage 02 originals and would
discard any subsequent edits. It is not idempotent with respect to later development
and should not be re-run.
"""

from __future__ import annotations

import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "04_strategy_prototypes" / "stage02_common.py"

# ADR-0011 section 4.1. Left column is the symbol, right column is where it goes.
SHARED_QC = [
    "winslow_smooth_2d",
    "orient_patches_2d",
    "_boundary_edges",
    "spanwise_interpolation_error",
    "orient_blocks_consistently",
    "qc_blocks",
    "worst_corner_angle_deg",
    "write_surface_artifacts",
]
SHARED_INGESTION = ["section_loop_2d", "feature_split_sides"]
S1_PRIVATE = [
    "geometric_progression_counts",
    "camber_and_thickness",
    "_point_at_x",
    "_arc_between_x",
    "butterfly_cap_2d",
    "_closed_arclength_fractions",
    "_match_closed_parameterisation",
    "oml_tip_ring_2d",
    "butterfly_from_ring",
    "map_2d_patch_to_tip",
    "realise_spanwise_law",
]


def extract(text: str) -> dict[str, str]:
    """Exact source text of every top-level function, keyed by name."""
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = "".join(lines[node.lineno - 1 : node.end_lineno])
    return out


def strip_s1_chordwise_defaults(src: str) -> str:
    """The one deliberate edit: `feature_split_sides` must not choose a chordwise law.

    ADR-0011 section 4.1. `distribution` is a chordwise distribution law and
    `te_base_points` is a chordwise point allocation; both are per-strategy under
    the independence line. Stage 02 defaulted them to S1's answers, so importing
    the function unchanged would hand every strategy S1's blocking decision.
    """
    before = src
    src = src.replace(
        "    te_base_points: int = 3,\n    distribution: str = \"uniform\",\n    beta: float = 2.0,\n",
        "    te_base_points: int,\n    distribution: str,\n    beta: float = 2.0,\n",
    )
    if src == before:
        raise SystemExit(
            "feature_split_sides signature did not match the expected Stage 02 text; "
            "inspect it by hand rather than migrating silently."
        )
    # Replace the S1-specific defence of `uniform` with a neutral contract note.
    doc_start = src.index('    """Split a section')
    doc_end = src.index('    """', doc_start + 8) + len('    """\n')
    new_doc = '''    """Split a section into sides whose corners are all genuine features.

    Returns three sides in order: upper (LE -> upper TE), lower (LE -> lower TE),
    and the blunt TE base as its own short side. Corners land on the leading edge
    and on the two trailing-edge base corners - all real curvature features.

    SHARED CONTROL (ADR-0011 section 4). This function is ingestion: it turns the
    generator's section into side curves. It does NOT choose a chordwise law.
    ``distribution``, ``beta`` and ``te_base_points`` are **required** and must be
    supplied by the calling strategy, because chordwise clustering and point
    allocation are per-strategy under the independence line. Stage 02 defaulted
    these to S1's answers, which is exactly what ADR-0011 exists to prevent.

    COMMON_BRIEF section 9.2 records the measurement behind S1's own choice - on
    lhs7_00, cosine gave a 396x cell-size range and uniform gave 99x - as prior
    knowledge available to every strategy, not as a default.
    """
'''
    return src[:doc_start] + new_doc + src[doc_end:]


def main() -> int:
    text = SOURCE.read_text()
    fns = extract(text)
    missing = [
        n for n in SHARED_QC + SHARED_INGESTION + S1_PRIVATE if n not in fns
    ]
    if missing:
        raise SystemExit(f"symbols not found in {SOURCE}: {missing}")

    shared = HERE / "shared"
    shared.mkdir(parents=True, exist_ok=True)

    ingestion_header = '''"""Section ingestion — SHARED CONTROL (ADR-0011 section 4).

Every strategy reads the generator's sections through this module, so the
comparison measures meshing methods rather than section readers. Migrated
byte-for-byte from `04_strategy_prototypes/stage02_common.py` except for the
chordwise defaults stripped out of `feature_split_sides` per ADR-0011 section 4.1.

Do not add a blocking, distribution or tip-closure decision here. Those are
per-strategy.
"""

from __future__ import annotations

import numpy as np

from aeris.mesh.surface import (  # noqa: F401 - re-exported for strategies
    MeshBuildError,
    SurfaceBlock,
    _block_qc,
    _map_sides_to_wing,
    _open_trailing_edge,
    _resample_piecewise,
    _resample_polyline,
    _smooth_patch_interior,
    _split_counts,
    _tfi_patch,
    _write_npz,
    _write_plot3d_formatted,
)

Array = np.ndarray


'''
    parts = [ingestion_header, fns["section_loop_2d"], "\n\n", strip_s1_chordwise_defaults(fns["feature_split_sides"])]
    (shared / "ingestion.py").write_text("".join(parts))

    qc_header = '''"""QC metric definitions, orientation and artifact writing — SHARED CONTROL.

ADR-0011 section 4: QC metric *definitions*, gate thresholds, and the verifier are
shared so that a comparison between strategies is a comparison between meshing
methods and not between quality metrics. **Migrated unchanged** from
`04_strategy_prototypes/stage02_common.py`, so every number recorded in `status`
remains directly comparable.

`winslow_smooth_2d` is a generic operator and is shared under ADR-0011 section 4.1;
using it is a per-strategy decision. COMMON_BRIEF section 1 records that it made
S1's Stage 02 tip cap **worse** (-0.0363 -> -0.0499), which is a measurement about
that cap, not about the operator.
"""

from __future__ import annotations

import numpy as np

from .ingestion import Array, SurfaceBlock, _block_qc, _write_npz, _write_plot3d_formatted


'''
    body = []
    for name in SHARED_QC:
        body.append(fns[name])
        body.append("\n\n")
    (shared / "qc.py").write_text(qc_header + "".join(body).rstrip("\n") + "\n")

    s1 = HERE / "S1_tip_first"
    s1.mkdir(parents=True, exist_ok=True)
    s1_header = '''"""S1's private construction — tip closure and spanwise distribution.

ADR-0011 section 4.1 moved these out of the Stage 02 shared module. They are S1's
blocking decisions, not infrastructure: `butterfly_from_ring` is a tip closure,
`oml_tip_ring_2d` is tip staging, `realise_spanwise_law` and
`geometric_progression_counts` are a spanwise distribution law, and
`butterfly_cap_2d` / `camber_and_thickness` / `map_2d_patch_to_tip` are S1 cap
internals. Under the independence line no other strategy may import from this file.

Migrated byte-for-byte from `04_strategy_prototypes/stage02_common.py`. Docstrings
still describe the Stage 02 development history, including `butterfly_cap_2d`,
which is a **recorded negative result** kept for provenance and is not on S1's
working path.

NOTE for the S1 study: this file is the Stage 02 implementation. ADR-0011 requires
S1 to be re-implemented from scratch like every other strategy. Treat this as the
prior art to read and beat, not as the S1 entry.
"""

from __future__ import annotations

import numpy as np

from shared.ingestion import (
    Array,
    MeshBuildError,
    _map_sides_to_wing,
    _resample_piecewise,
    _resample_polyline,
    _smooth_patch_interior,
    _split_counts,
    _tfi_patch,
)
from shared.qc import orient_patches_2d


'''
    body = []
    for name in S1_PRIVATE:
        body.append(fns[name])
        body.append("\n\n")
    (s1 / "s1_stage02_prior_art.py").write_text(s1_header + "".join(body).rstrip("\n") + "\n")

    print(f"shared/ingestion.py      {len(SHARED_INGESTION)} symbols (1 edited)")
    print(f"shared/qc.py             {len(SHARED_QC)} symbols, unchanged")
    print(f"S1_tip_first/s1_stage02_prior_art.py  {len(S1_PRIVATE)} symbols, unchanged")
    moved = set(SHARED_QC) | set(SHARED_INGESTION) | set(S1_PRIVATE)
    left = sorted(set(fns) - moved)
    print(f"not migrated (private Stage 02 helpers): {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
