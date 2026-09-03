"""The governed conservation metric lives inside the static runner template, so
these tests execute that template against a stubbed ADflow/MPI environment.
ADflow itself is never initialized."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from aeris.cfd.solvers.adflow.adapter import _RUNNER_TEMPLATE

REQUIRED_DEFINITION = "signed_net_boundary_mass_flux_over_gross_boundary_mass_flux"

STUB = '''
import sys, types
import numpy

class _Comm:
    rank = 0
    def allreduce(self, value, op=None):
        return value

mpi4py = types.ModuleType("mpi4py")
mpi_mod = types.ModuleType("mpi4py.MPI")
mpi_mod.COMM_WORLD = _Comm()
mpi_mod.SUM = "sum"
mpi4py.MPI = mpi_mod
sys.modules["mpi4py"] = mpi4py
sys.modules["mpi4py.MPI"] = mpi_mod

class AeroProblem:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.xRef, self.yRef, self.zRef = kwargs.get("xRef"), kwargs.get("yRef"), kwargs.get("zRef")

baseclasses = types.ModuleType("baseclasses")
baseclasses.AeroProblem = AeroProblem
sys.modules["baseclasses"] = baseclasses

MDOT = __MDOT__
FAIL_EVAL = __FAIL_EVAL__

class _State:
    nw = 6

class _Inner:
    flowvarrefstate = _State()

class ADFLOW:
    def __init__(self, options=None):
        self.adflow = _Inner()
        self.families = dict(__FAMILIES__)
        self.allFamilies = "allSurfaces"
        self.allWallsGroup = "allWalls"
        self._registered = {}
    def __call__(self, ap):
        return None
    def getConvergenceHistory(self):
        return {"RSDMassRMS": [1.0, 1e-6], "RSDMomentumXRMS": [1.0, 1e-7],
                "RSDMomentumYRMS": [1.0, 1e-7], "RSDMomentumZRMS": [1.0, 1e-7],
                "RSDEnergyStagnationDensityRMS": [1.0, 1e-7],
                "RSDTurbulentSANuTildeRMS": [1.0, 1e-9], "totalR": [1.0, 1e-9]}
    def getResidual(self, ap):
        return numpy.ones(12, dtype=float)
    def addFunction(self, funcName, groupName, name=None):
        self._registered[name] = (funcName, groupName)
        return [name]
    def evalFunctions(self, ap, funcs, evalFuncs=None, ignoreMissing=False):
        if evalFuncs is None:
            evalFuncs = ["cl", "cd", "cmy", "cdp", "cdv"]
        for handle in evalFuncs:
            low = handle.lower()
            if low.startswith("aeris_mdot_"):
                if FAIL_EVAL:
                    raise RuntimeError("stub mdot failure")
                funcs["%s_%s" % (ap.name, low)] = MDOT[low[len("aeris_mdot_"):]]
            elif low.startswith("aeris_area_"):
                funcs["%s_%s" % (ap.name, low)] = 1.0
            else:
                funcs["%s_%s" % (ap.name, low)] = 0.5
    def checkSolutionFailure(self, ap, funcs):
        funcs["fail"] = False

adflow = types.ModuleType("adflow")
adflow.ADFLOW = ADFLOW
sys.modules["adflow"] = adflow
'''

CASE = {
    "name": "aeris_cfd",
    "alpha": 8.0,
    "mach": 0.0837,
    "reynolds": 1.5e6,
    "reynolds_length_ref": 0.9,
    "temperature": 278.4,
    "area_ref": 0.39,
    "chord_ref": 0.49,
    "moment_reference": [0.4, 0.0, 0.0],
    "secondary_moment_reference": None,
    "eval_funcs": ["cl", "cd", "cmy", "cdp", "cdv"],
}


def _run(tmp_path: Path, mdot: dict, families=None, fail_eval: bool = False) -> dict:
    if families is None:
        families = {
            "farfieldbczone2": [1],
            "farfieldbczone11": [2],
            "nswalladiabaticbczone1": [3],
            "symmetrybczone1": [4],
            "allSurfaces": [1, 2, 3, 4],
            "allWalls": [3],
        }
    # repr() of float("nan") is not valid Python source, so emit it explicitly.
    mdot_src = "{%s}" % ", ".join(
        "%r: %s" % (k, "float('nan')" if v != v else repr(v)) for k, v in mdot.items()
    )
    stub = (
        STUB.replace("__MDOT__", mdot_src)
        .replace("__FAMILIES__", repr(families))
        .replace("__FAIL_EVAL__", repr(fail_eval))
    )
    (tmp_path / "adflow_options.json").write_text(json.dumps({"gridFile": "x.cgns"}))
    (tmp_path / "adflow_case.json").write_text(json.dumps(CASE))
    script = tmp_path / "driver.py"
    script.write_text(stub + "\n" + textwrap.dedent(_RUNNER_TEMPLATE))
    proc = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads((tmp_path / "adflow_run.json").read_text())


def test_governed_definition_replaces_residual_cancellation_ratio(tmp_path):
    report = _run(tmp_path, {"farfieldbczone2": 10.0, "farfieldbczone11": -10.0,
                             "nswalladiabaticbczone1": 0.0, "symmetrybczone1": 0.0})
    assert report["mass_imbalance_definition"] == REQUIRED_DEFINITION
    # net cancels exactly; gross is 20.0
    assert report["mass_imbalance_normalized"] == pytest.approx(0.0)
    assert report["boundary_mass_flux"]["gross"] == pytest.approx(20.0)
    assert report["boundary_mass_flux"]["complete"] is True
    # the old interior metric survives only as a clearly labelled diagnostic
    assert "residual_cancellation_ratio_diagnostic" in report
    assert "acceptance" in report["residual_cancellation_ratio_definition"]


def test_signed_net_over_gross_arithmetic(tmp_path):
    report = _run(tmp_path, {"farfieldbczone2": 10.0, "farfieldbczone11": -9.0,
                             "nswalladiabaticbczone1": 0.0, "symmetrybczone1": 0.0})
    flux = report["boundary_mass_flux"]
    assert flux["signed_net"] == pytest.approx(1.0)
    assert flux["gross"] == pytest.approx(19.0)
    assert report["mass_imbalance_normalized"] == pytest.approx(1.0 / 19.0)


def test_walls_and_symmetry_are_measured_not_assumed(tmp_path):
    report = _run(tmp_path, {"farfieldbczone2": 5.0, "farfieldbczone11": -5.0,
                             "nswalladiabaticbczone1": 0.0, "symmetrybczone1": 0.0})
    per_family = report["boundary_mass_flux"]["per_family"]
    assert set(per_family) == {
        "farfieldbczone2", "farfieldbczone11",
        "nswalladiabaticbczone1", "symmetrybczone1",
    }
    assert per_family["nswalladiabaticbczone1"]["mdot"] == pytest.approx(0.0)
    assert per_family["nswalladiabaticbczone1"]["area"] == pytest.approx(1.0)
    assert report["boundary_mass_flux"]["family_count"] == 4


def test_group_families_are_not_double_counted(tmp_path):
    report = _run(tmp_path, {"farfieldbczone2": 3.0, "farfieldbczone11": -3.0,
                             "nswalladiabaticbczone1": 0.0, "symmetrybczone1": 0.0})
    assert "allSurfaces" not in report["boundary_mass_flux"]["per_family"]
    assert "allWalls" not in report["boundary_mass_flux"]["per_family"]


def test_failed_integration_fails_closed(tmp_path):
    report = _run(tmp_path, {"farfieldbczone2": 1.0}, fail_eval=True)
    flux = report["boundary_mass_flux"]
    assert flux["complete"] is False
    assert flux["error"] is not None
    assert report["mass_imbalance_normalized"] is None


def test_nonfinite_family_flux_fails_closed(tmp_path):
    report = _run(tmp_path, {"farfieldbczone2": float("nan"), "farfieldbczone11": -1.0,
                             "nswalladiabaticbczone1": 0.0, "symmetrybczone1": 0.0})
    assert report["boundary_mass_flux"]["complete"] is False
    assert report["mass_imbalance_normalized"] is None
