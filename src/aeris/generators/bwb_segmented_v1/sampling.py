"""
Per-sample BWB design generator.

Produces a single BWBDesignSample from a BWBGeneratorConfig and a NumPy rng.
Used by:
    - single-case geometry generation (one design, one rng)
    - dataset sampling, where the dataset-level sampler (e.g. LHS) is
      responsible for any cross-sample coordination

Each design variable is drawn independently with rng.uniform() from its
configured [min, max] bounds. The dataset-level LHS sampler (Layer 4)
arranges for the rng draws to follow a Latin Hypercube pattern when needed.

Sign conventions:
    sw1_deg, sw2_deg, sw3_deg
        YAML bounds declare positive sweep magnitudes. This function negates
        them so the stored sample carries the BWB internal convention
        (negative = aft sweep). See BWBDesignSample docstring.
"""

from __future__ import annotations

import numpy as np

from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    BWBGeneratorConfig,
)


def sample_bwb_design(
    config: BWBGeneratorConfig,
    rng: np.random.Generator,
) -> BWBDesignSample:
    """Draw one explicit BWB design from the configured bounds.

    Args:
        config: typed BWB generator configuration.
        rng:    NumPy random Generator. Must be deterministic when given the
                same seed.

    Returns:
        BWBDesignSample with negated sw*_deg (BWB internal convention).
    """
    pb = config.planform_bounds
    sb = config.section_bounds

    # YAML bounds are positive magnitudes; convert to BWB's negative-aft
    # internal convention.
    sw1_mag_deg = rng.uniform(pb.sw1_deg.min, pb.sw1_deg.max)
    sw2_mag_deg = rng.uniform(pb.sw2_deg.min, pb.sw2_deg.max)
    sw3_mag_deg = rng.uniform(pb.sw3_deg.min, pb.sw3_deg.max)

    # Elevon geometry DVs — sample when bounds provided, else use defaults
    _eb = config.elevon_bounds
    if _eb is not None:
        _es = float(rng.uniform(_eb.elevon_start_frac.min, _eb.elevon_start_frac.max))
        _ee = float(rng.uniform(_eb.elevon_end_frac.min,   _eb.elevon_end_frac.max))
        _eh = float(rng.uniform(_eb.elevon_hinge_frac.min, _eb.elevon_hinge_frac.max))
        if _es >= _ee:
            _es, _ee = min(_es, _ee), max(_es, _ee)
    else:
        _es, _ee, _eh = 0.60, 0.95, 0.75

    return BWBDesignSample(
        c1_m=rng.uniform(pb.c1_m.min, pb.c1_m.max),
        c2_ratio=rng.uniform(pb.c2_ratio.min, pb.c2_ratio.max),
        c3_ratio=rng.uniform(pb.c3_ratio.min, pb.c3_ratio.max),
        c4_ratio=rng.uniform(pb.c4_ratio.min, pb.c4_ratio.max),
        b_total_m=rng.uniform(pb.b_total_m.min, pb.b_total_m.max),
        b3_ratio=rng.uniform(pb.b3_ratio.min, pb.b3_ratio.max),
        split_ratio=rng.uniform(pb.split_ratio.min, pb.split_ratio.max),
        sw1_deg=-sw1_mag_deg,
        sw2_deg=-sw2_mag_deg,
        sw3_deg=-sw3_mag_deg,
        twist_b0_deg=rng.uniform(sb.twist_b0_deg.min, sb.twist_b0_deg.max),
        twist_b1_deg=rng.uniform(sb.twist_b1_deg.min, sb.twist_b1_deg.max),
        twist_b2_deg=rng.uniform(sb.twist_b2_deg.min, sb.twist_b2_deg.max),
        twist_b3_deg=rng.uniform(sb.twist_b3_deg.min, sb.twist_b3_deg.max),
        dihedral_b1_deg=rng.uniform(sb.dihedral_b1_deg.min, sb.dihedral_b1_deg.max),
        dihedral_b2_deg=rng.uniform(sb.dihedral_b2_deg.min, sb.dihedral_b2_deg.max),
        dihedral_b3_deg=rng.uniform(sb.dihedral_b3_deg.min, sb.dihedral_b3_deg.max),
        elevon_start_frac=_es,
        elevon_end_frac=_ee,
        elevon_hinge_frac=_eh,
    )