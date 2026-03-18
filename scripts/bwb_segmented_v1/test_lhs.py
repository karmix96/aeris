from __future__ import annotations

from pathlib import Path

from aeris.common.config import load_yaml_config
from aeris.dataset.lhs import generate_lhs_samples
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "configs" / "geometry" / "wing_bwb.yaml"

    raw = load_yaml_config(config_path)
    cfg = build_bwb_generator_config(raw)

    samples = generate_lhs_samples(
        config=cfg,
        n_samples=5,
        lhs_seed=123,
    )

    print("\n=== LHS SAMPLES ===\n")
    for i, sample in enumerate(samples, start=1):
        print(f"Sample {i}")
        for key, value in sample.to_dict().items():
            print(f"  {key}: {value:.6f}")
        print()


if __name__ == "__main__":
    main()