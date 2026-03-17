from __future__ import annotations

import numpy as np

from aeris.geometry.params import BWBDesignSample, BWBGeneratorConfig


def sample_bwb_design(
    config: BWBGeneratorConfig,
    rng: np.random.Generator,
) -> BWBDesignSample:
    pb = config.planform_bounds
    sb = config.section_bounds

    # YAML bounds are positive sweep magnitudes.
    # Internally we preserve the current generator convention:
    # aft sweep is stored as negative degrees.
    sw1_mag_deg = rng.uniform(pb.sw1_deg.min, pb.sw1_deg.max)
    sw2_mag_deg = rng.uniform(pb.sw2_deg.min, pb.sw2_deg.max)
    sw3_mag_deg = rng.uniform(pb.sw3_deg.min, pb.sw3_deg.max)

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
    )