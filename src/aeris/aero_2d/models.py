"""2D aerodynamic result model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Aero2DResult:
    """One (airfoil × alpha × Re × Mach × Ncrit) XFOIL result row."""
    airfoil_id: str
    airfoil_name: str
    source_file: str
    alpha_deg: float
    reynolds: float
    mach: float
    ncrit: float
    cl: float | None
    cd: float | None
    cm: float | None
    cp_min: float | None
    converged: bool
    solver_id: str = "xfoil_python"
    solver_version: str = "unknown"

    def to_row(self) -> dict[str, Any]:
        """Flat dict for one CSV row."""
        import math
        re = self.reynolds
        return {
            "airfoil_id":       self.airfoil_id,
            "airfoil_name":     self.airfoil_name,
            "source_file":      self.source_file,
            "alpha_deg":        self.alpha_deg,
            "reynolds":         re,
            "log10_reynolds":   math.log10(re) if re > 0 else None,
            "mach":             self.mach,
            "ncrit":            self.ncrit,
            "cl":               self.cl,
            "cd":               self.cd,
            "cm":               self.cm,
            "cp_min":           self.cp_min,
            "converged":        self.converged,
            "solver_id":        self.solver_id,
            "solver_version":   self.solver_version,
        }
