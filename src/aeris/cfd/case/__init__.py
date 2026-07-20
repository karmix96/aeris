"""Case specification: one YAML describing geometry → mesh → solve → post."""

from aeris.cfd.case.loader import load_case_spec
from aeris.cfd.case.spec import CASE_SCHEMA_VERSION, CaseSpec

__all__ = ["CASE_SCHEMA_VERSION", "CaseSpec", "load_case_spec"]
