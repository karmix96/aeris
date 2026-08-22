"""The locked geometry sets — SHARED CONTROL.

ADR-0011 section 4: the geometry sets are shared, so every strategy is developed
and judged on the same aircraft. ADR-0011 section 7.4 fixes their roles:

============================  ==========================================
set                           role
============================  ==========================================
``lhs100_seed42``             development and refinement
``round_c_lhs10_seed42``      **HOLD-OUT. No tuning, ever.**
``epse_calibration_lhs10_seed7``  Stage 01/02 evidence basis; permitted for
                              like-for-like comparison against a recorded
                              number, declared in the strategy's STUDY.md
============================  ==========================================

**Set identity is the quadruple (sampler id, seed, n, geometry-config sha256)**
(ADR-0001). A seed alone is NOT an identifier: Latin hypercube stratification
depends on n, so seed 42 at n=100 and seed 42 at n=10 share **zero** rows.
Authority is ``00_governance/lhs_authority.yaml``; regenerate and verify with
``00_governance/make_lhs_sets.py --check``.

The hold-out guard below is deliberate friction. It is not a permission system —
anyone can pass ``i_have_finished_developing_this_strategy=True`` — it is a
tripwire that makes reaching for the hold-out a visible, deliberate act rather
than an absent-minded one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GOVERNANCE = REPO_ROOT / "AERIS_MESH_STUDY/00_governance"
GEOMETRY_CONFIG = REPO_ROOT / "configs/geometry/bwb.yaml"

#: name -> (seed, n, role)
SETS = {
    "lhs100_seed42": (42, 100, "development_and_refinement"),
    "round_c_lhs10_seed42": (42, 10, "HOLD_OUT_no_tuning"),
    "epse_calibration_lhs10_seed7": (7, 10, "stage01_02_evidence_basis"),
}

HOLD_OUT = "round_c_lhs10_seed42"


def _config():
    from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

    return build_bwb_generator_config(yaml.safe_load(GEOMETRY_CONFIG.read_text()))


def design_matrix(set_name: str) -> tuple[np.ndarray, list[str]]:
    """Regenerate a locked set's design matrix in memory, with its column names.

    Regenerating rather than reading the CSV keeps the sampler as the single
    source of truth. ``make_lhs_sets.py --check`` is what asserts the CSVs on
    disk still agree with it.
    """
    from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix

    if set_name not in SETS:
        raise KeyError(f"unknown geometry set {set_name!r}; known: {sorted(SETS)}")
    seed, n, _role = SETS[set_name]
    cfg = _config()
    matrix = build_lhs_design_matrix(cfg, n, np.random.default_rng(seed))
    return matrix, cfg.active_design_variable_names()


def sample(set_name: str, index: int, *, i_have_finished_developing_this_strategy: bool = False):
    """One ``BWBDesignSample`` from a locked set.

    Accessing :data:`HOLD_OUT` requires the caller to state, in the call itself,
    that the strategy is frozen. ADR-0011 section 7.1 step 8: the hold-out is run
    **once**, after the user's freeze signal, with no tuning.
    """
    from aeris.generators.bwb_segmented_v1.params import BWBDesignSample

    if set_name == HOLD_OUT and not i_have_finished_developing_this_strategy:
        raise PermissionError(
            f"{HOLD_OUT} is the ADR-0011 hold-out. No strategy sees it during "
            "development, and no tuning of any kind is permitted on it. It is run "
            "once, after the user's freeze signal. If this really is the frozen "
            "hold-out run, pass i_have_finished_developing_this_strategy=True and "
            "record the freeze in the strategy's STUDY.md and in `status`."
        )
    matrix, names = design_matrix(set_name)
    row = matrix[index]
    return BWBDesignSample(**{n: float(v) for n, v in zip(names, row, strict=True)})


def geometry_id(set_name: str, index: int) -> str:
    """Stable identifier for one geometry, e.g. ``lhs100_seed42_017``."""
    return f"{set_name}_{index:03d}"


def wing(
    set_name: str,
    index: int,
    *,
    output_dir: Path | None = None,
    i_have_finished_developing_this_strategy: bool = False,
):
    """Build one geometry and return its AeroSandbox wing.

    Shared for the reason ADR-0011 section 4 gives: geometry is generated the same
    way for every strategy; how each turns it into blocks is the experiment.
    """
    from aeris.geometry.registry import get_geometry_generator

    smp = sample(
        set_name,
        index,
        i_have_finished_developing_this_strategy=i_have_finished_developing_this_strategy,
    )
    out = output_dir or (
        REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/geom" / geometry_id(set_name, index)
    )
    case = get_geometry_generator("bwb_segmented").run_full_case(
        sample=smp,
        config=_config(),
        output_dir=out,
        save_plot=False,
        build_aerosandbox=True,
    )
    return case.wing


def authority() -> dict:
    """The frozen set authority, for embedding in a results manifest."""
    return yaml.safe_load((GOVERNANCE / "lhs_authority.yaml").read_text())
