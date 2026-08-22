"""Diagnostic: does wall y+ fall below 1 at coarse (production) resolution?

The diagnostic tier measured y+ around 44 with a first cell of 2.0e-3 L.  Coarse
uses 7.2e-6 L, 278 times finer, so y+ should land well under the policy limits.
That is a prediction, and this measures it.

It reuses the real config writer so the test is representative, but bounds the
iteration count: coarse would otherwise inherit the 20 000-iteration production
budget.  Diagnostic only - no campaign claim may rest on it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2.common import atomic_write_text, load_policy  # noqa: E402
from S7_unstructured_gmsh_su2.su2_pipeline import (  # noqa: E402
    fixed_su2_options,
    read_surface_vtk_yplus,
)

ROOT = Path(__file__).resolve().parents[2] / (
    "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/coarse_yplus"
)


def main() -> int:
    mesh = Path(sys.argv[1])
    iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    ranks = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    policy = load_policy()
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    shutil.copy2(mesh, ROOT / "mesh.su2")

    options = fixed_su2_options(
        ROOT / "mesh.su2",
        flow=dict(policy["flow_conditions"]["baseline"]),
        references={"area_ref": 0.9610974474634779, "chord_ref": 0.5349896481665188},
        iterations=iterations,
        restart=False,
    )
    options["ITER"] = iterations
    lines = [f"{k}= {v}" for k, v in sorted(options.items())]
    atomic_write_text(ROOT / "case.cfg", "\n".join(lines) + "\n")

    command = ["mpirun", "-np", str(ranks), "SU2_CFD", "case.cfg"]
    started = time.time()
    with (ROOT / "su2.log").open("w", encoding="utf-8") as log:
        code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
    print(f"SU2 exit={code} wall={time.time() - started:.0f}s ranks={ranks} iter={iterations}",
          flush=True)

    report = read_surface_vtk_yplus(ROOT / "surface_flow.vtk")
    if not report["values"]:
        print("no y+ values; tail of log:")
        print("\n".join((ROOT / "su2.log").read_text(errors="replace").splitlines()[-15:]))
        return 1
    values = np.asarray(report["values"], dtype=float)
    limits = policy["su2"]["wall_y_plus"]
    print(f"wall points {report['point_count']} complete={report['complete']}")
    print(
        "y+  min %.4f  p50 %.4f  p95 %.4f  p99 %.4f  max %.4f"
        % (
            values.min(),
            np.percentile(values, 50),
            np.percentile(values, 95),
            np.percentile(values, 99),
            values.max(),
        )
    )
    print(
        "limits p95<=%s p99<=%s max<=%s -> p95 %s  p99 %s  max %s"
        % (
            limits["p95_max"],
            limits["p99_max"],
            limits["max_max"],
            "PASS" if np.percentile(values, 95) <= limits["p95_max"] else "FAIL",
            "PASS" if np.percentile(values, 99) <= limits["p99_max"] else "FAIL",
            "PASS" if values.max() <= limits["max_max"] else "FAIL",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
