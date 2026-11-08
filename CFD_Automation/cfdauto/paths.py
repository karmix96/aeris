"""Where things live. The package is shared by every stage; each stage keeps its own
configs, data, docs and tests in its own folder (Stage_<N>_<topic>/)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # CFD_Automation/
REPO = ROOT.parent                              # the aeris repository
STAGE1 = ROOT / "Stage_1_geometry"              # geometry and flow maps: configs, data, docs
STAGE2 = ROOT / "Stage_2_surface_mesh"          # surface mesh: configs, data, docs
STAGE0 = ROOT / "Stage_0_decisions"             # the owner's values: values.yaml


def re_levels() -> tuple[float, ...]:
    """The Re levels on the mean chord (area / full span), from Stage 0 values.yaml (D3, reynolds_levels): the one
    place every script reads them. 1e5, 3e5, 1e6, 4e6 since 8 Nov 2026 (owner); 1e5, 3e5, 1.5e6, 3e6 before."""
    import yaml
    d = yaml.safe_load((STAGE0 / "values.yaml").read_text())
    return tuple(sorted(float(x) for x in d["D3_conditions_and_measurement"]["reynolds_levels"]["value"]))
