"""Open-source finite-element automation for AERIS wing geometries."""

from aeris.fea.case.loader import load_case_spec
from aeris.fea.case.runner import run_case

__all__ = ["load_case_spec", "run_case"]
