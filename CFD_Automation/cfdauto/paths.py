"""Where things live. The package is shared by every stage; each stage keeps its own
configs, data, docs and tests in its own folder (Stage_<N>_<topic>/)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # CFD_Automation/
REPO = ROOT.parent                              # the aeris repository
STAGE1 = ROOT / "Stage_1_geometry"              # geometry and flow maps: configs, data, docs
STAGE2 = ROOT / "Stage_2_surface_mesh"          # surface mesh: configs, data, docs
