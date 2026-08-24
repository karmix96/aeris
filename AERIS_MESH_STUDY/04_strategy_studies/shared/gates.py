"""Gate thresholds and pass/fail checklists — SHARED CONTROL.

ADR-0011 section 6 freezes these **before any strategy is implemented or
optimised**. Nothing here may be chosen, reweighted or relaxed after seeing
results. Thresholds are migrated unchanged from Stage 00 / ADR-0005 / ADR-0008 so
every number already recorded in `status` stays directly comparable.

Two distinctions this module exists to hold:

1. **`0.30` is a RANKING TARGET, never a gate.** The frozen hard gate on volume
   min scaled quality is strictly `> 0`. Stage 02 audited every use of 0.30 across
   `gate_registry.yaml`, `verify_strategies.py` and the narrative and found no
   misuse; keeping the two in one file with the distinction stated is how it stays
   that way.
2. **A surface can pass every shape gate and be unmarchable.** ADR-0010. The two
   marchability metrics — staged cell-size range and min-cell/`s0` — are therefore
   *reported* by `marchability_metrics` and included in Round A per ADR-0011
   section 3.2. They are deliberately **not** hard gates: no threshold on them has
   been established, and inventing one after the fact is exactly what ADR-0011
   section 6 forbids.
"""

from __future__ import annotations

# --- hard gates, ADR-0011 section 6.1 --------------------------------------

#: Geometry fidelity, as a fraction of local chord. Stage 00; 0.01% = 1.0e-4.
#: Measured point-to-SEGMENT against a CLOSED reference contour — both were
#: instrument bugs in Stage 02 (COMMON_BRIEF section 5, items 1 and 2).
FIDELITY_FRAC_OF_LOCAL_CHORD = 1.0e-4

#: Surface min scaled Jacobian must be strictly greater than this. ADR-0005.
SURFACE_MIN_SCALED_JACOBIAN_FLOOR = 0.0

#: Volume min scaled quality must be strictly greater than this. ADR-0008.
VOLUME_MIN_SCALED_QUALITY_FLOOR = 0.0

#: Node rounding for coincidence tests. 1e-7 m = 0.1 micron; finer compares float
#: noise rather than nodes.
NODE_DECIMALS = 7

# --- ranking targets, NOT gates --------------------------------------------

#: RUNBOOK section 7 Round B quality target. Used only for ranking commentary.
#: It is never a pass threshold. See the module docstring.
VOLUME_QUALITY_RANKING_TARGET = 0.30

# --- epsE protocol, ADR-0008 as amended by ADR-0011 section 5 --------------

#: The declared ladder. NOT extended after a failure without a further ADR
#: stating the physical reason (ADR-0008 section 6).
EPSE_LADDER = (1.5, 2.0, 3.0)

#: epsI is tied to epsE at this ratio throughout the study.
EPSI_OVER_EPSE = 2.0

#: Calibration and confirmation levels. Only the coarsen=1 family
#: (smoke -> fine -> production) is a refinement ladder at full surface
#: resolution. The `L*` family uses coarsen=4, so `L4` (N=37) is COARSER than
#: `smoke` (N=129) and would confirm nothing — that error is recorded in
#: ADR-0008 and repeated in ADR-0011 section 5.4 so it cannot recur.
CALIBRATION_LEVEL = "smoke"  # N=129, coarsen=1
CONFIRMATION_LEVEL = "fine"  # N=193, coarsen=1
REFINEMENT_LADDER = ("smoke", "fine", "production")

#: Stage 01 cap4 control on lhs7_00 at the calibration level, for like-for-like
#: comparison. Reproduced through a new code path in Stage 02 at 54/128, which is
#: the study's regression anchor.
CAP4_REFERENCE = {
    "bad_layers": 53,
    "layer_count": 128,
    "min_quality": -0.90808,
    "reproduced_via_new_code_path": {"bad_layers": 54, "min_volume": 2.11e-11},
}


def surface_gate_checklist(
    qc: dict,
    fidelity: dict,
    orientation: dict,
    watertight: bool,
    deterministic_connectivity: bool,
) -> tuple[bool, list[str]]:
    """ADR-0011 section 6.1, surface half. Returns (passed, failure reasons).

    ``qc`` is :func:`shared.qc.qc_blocks` output, ``fidelity`` is
    :func:`shared.verify.oml_fidelity` output, ``orientation`` is the info dict
    from :func:`shared.qc.orient_blocks_consistently`.
    """
    fails: list[str] = []

    frac = fidelity.get("worst_frac_of_local_chord")
    if frac is None or float(frac) > FIDELITY_FRAC_OF_LOCAL_CHORD:
        fails.append(
            f"geometry fidelity {frac} of local chord, gate is "
            f"<= {FIDELITY_FRAC_OF_LOCAL_CHORD}"
        )
    if fidelity.get("fidelity_unverified_for_refined_blocks"):
        # COMMON_BRIEF section 5: silently skipping spanwise-refined blocks would
        # report a refined mesh as fidelity-perfect while its interpolated columns
        # sit off the loft entirely. Unverified is not the same as passing.
        fails.append(
            "fidelity unverified for spanwise-refined blocks: "
            f"{fidelity.get('skipped_spanwise_refined_blocks')}"
        )
    if not watertight:
        fails.append("surface is not watertight at the tip")
    if not orientation.get("all_blocks_connected", False):
        fails.append(
            "orientation edge-walk did not reach every block "
            f"({orientation.get('blocks_reached_by_edge_walk')} of "
            f"{orientation.get('block_count')}) — surface is disconnected"
        )
    if float(orientation.get("signed_volume_before_global_flip", 0.0)) == 0.0:
        fails.append("enclosed signed volume is zero; normals cannot be verified outward")
    jac = (qc.get("global") or {}).get("min_scaled_jacobian")
    if jac is None or float(jac) <= SURFACE_MIN_SCALED_JACOBIAN_FLOOR:
        fails.append(f"surface min scaled Jacobian {jac}, gate is strictly > 0")
    area = (qc.get("global") or {}).get("min_area")
    if area is None or float(area) <= 0.0:
        fails.append(f"minimum surface cell area {area}, gate is strictly > 0")
    if not deterministic_connectivity:
        fails.append("connectivity signature is not deterministic across geometries")

    return (not fails), fails


def volume_gate_checklist(vol: dict) -> tuple[bool, list[str]]:
    """ADR-0008 section 3, verbatim; ADR-0011 section 6.1 volume half.

    The hard gate is `> 0`, never 0.30. Migrated unchanged from
    `03_cap4_epse/s1_volume_canary.py::_checklist`.
    """
    m = vol.get("march_metrics") or {}
    a = vol.get("volume_audit") or {}
    fails = []
    # **Instrument bug 10**, found 2026-08-14 while collecting a 30-march campaign.
    # The checklist scored an INCOMPLETE march as PASS: `lhs100_seed42_009` at
    # epsE 3.0 was still running, had reached 95 of 128 layers with no bad layer
    # yet, and satisfied every other condition. A march that has not finished has
    # not passed anything.
    if vol.get("march_completed") is False:
        fails.append("march did not complete (no 'pyHyp done' in the log)")
    if vol.get("status") != "valid":
        fails.append(f"pyHyp status {vol.get('status')!r}, expected 'valid'")
    if (a.get("inverted_cells") or 0) != 0:
        fails.append(f"inverted cells = {a.get('inverted_cells')}, must be 0")
    minvol = a.get("min_volume")
    if minvol is not None and float(minvol) <= 0:
        fails.append(f"min volume = {minvol}, must be > 0")
    mq = m.get("min_quality")
    if mq is None or float(mq) <= VOLUME_MIN_SCALED_QUALITY_FLOOR:
        fails.append(
            f"min scaled quality = {mq}, must be strictly > 0 (0.30 is a target, not a gate)"
        )
    if (m.get("low_quality_layers") or 0) != 0:
        fails.append(f"low/negative-quality layers = {m.get('low_quality_layers')}, must be 0")
    return (not fails), fails


def volume_gate_checklist_direct(vol: dict) -> tuple[bool, list[str]]:
    """ADR-0014 section 3.1 — the SAME gate for a volume that was not marched.

    Thresholds are the ADR-0008 thresholds, unchanged; only the source of each
    number moves, from pyHyp's report to `shared/volume_qc.volume_report`. This
    lives beside `volume_gate_checklist` rather than replacing it so that neither
    route can quietly become the other (ADR-0014 section 5).

    V5 has no marching layers to count, so the equivalent "no failing region" test
    is per block.
    """
    fails: list[str] = []
    if not vol.get("generation_completed"):
        fails.append(
            "volume generation did not complete "
            f"({vol.get('reason') or vol.get('non_finite_by_block') or vol.get('degenerate_block_shapes')})"
        )
        return False, fails
    if (vol.get("inverted_cells") or 0) != 0:
        fails.append(f"inverted cells = {vol.get('inverted_cells')}, must be 0")
    minvol = vol.get("min_volume")
    if minvol is None or float(minvol) <= 0.0:
        fails.append(f"min volume = {minvol}, must be > 0")
    mq = vol.get("min_scaled_quality")
    if mq is None or float(mq) <= VOLUME_MIN_SCALED_QUALITY_FLOOR:
        fails.append(
            f"min scaled quality = {mq}, must be strictly > 0 (0.30 is a target, not a gate)"
        )
    bad = vol.get("low_quality_blocks") or []
    if bad:
        fails.append(f"blocks with min scaled quality <= 0: {bad}")
    return (not fails), fails


def marchability_metrics(qc: dict, s0: float) -> dict:
    """The two ADR-0010 metrics. REPORTED, not gated — see the module docstring.

    ``cell_size_range`` is max/min surface cell edge over the staged surface, and
    ``min_cell_over_s0`` compares the smallest surface cell against pyHyp's first
    marching layer. Reference points measured in Stage 02 on lhs7_00:

    | surface                | range  | min/s0 | march                       |
    |------------------------|-------:|-------:|-----------------------------|
    | cap4 control           |   153x |   48.7 | completes, 54/128 bad       |
    | S1 as first built      |  3462x |    0.9 | explodes at layer 2         |
    | S1 after redistribution|    99x |   15.4 | 0/128 bad, min quality +0.224 |

    ``cell_size_range`` requires ``qc_blocks`` to have been given the *staged*
    surface — the one actually written for pyHyp — because staging is where the
    distribution is decided.
    """
    min_edge = qc.get("min_cell_edge_m")
    max_edge = qc.get("max_cell_edge_m")
    out: dict = {
        "min_cell_edge_m": min_edge,
        "min_cell_edge_block": qc.get("min_cell_edge_block"),
        "max_cell_edge_m": max_edge,
        "s0": s0,
    }
    if min_edge and max_edge:
        out["cell_size_range"] = float(max_edge) / float(min_edge)
    if min_edge and s0:
        out["min_cell_over_s0"] = float(min_edge) / float(s0)
    out["note"] = (
        "ADR-0010: reported, not gated. Cell-size range predicts catastrophic "
        "explosion; it does NOT predict marginal single-layer failure "
        "(COMMON_BRIEF section 3)."
    )
    return out
