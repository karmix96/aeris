"""Can the tetrahedral core be optimized without disturbing the prism layers?

Post-generation optimization is currently frozen off because an early diagnostic
found that Gmsh relocation moved intermediate prism nodes and corrupted the
prescribed layer schedule.  That conclusion predates the corrected prism audit,
so it is re-tested here with instruments that can actually see the schedule.

For each optimizer this reports tetrahedral shape quality (SICN, the metric that
is meaningful for linear simplices) and, critically, whether the prism first-layer
height, growth ratio and scaled Jacobian are unchanged.  An optimizer is only
usable if the prism schedule is bit-comparable to the unoptimized baseline.
"""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2 import geometry as G  # noqa: E402
from S7_unstructured_gmsh_su2 import gmsh_pipeline as P  # noqa: E402
from S7_unstructured_gmsh_su2.common import load_policy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / (
    "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/optimizer"
)


def measure(msh: Path) -> dict:
    import gmsh

    gmsh.initialize([])
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.open(str(msh.resolve()))
    out: dict = {}
    tags, flat, _ = gmsh.model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    coords = np.asarray(flat, dtype=float).reshape(-1, 3)
    order = np.argsort(tags)
    tags, coords = tags[order], coords[order]
    for et, etags, conn in zip(*gmsh.model.mesh.getElements(3), strict=True):
        name = gmsh.model.mesh.getElementProperties(int(et))[0]
        if int(et) == 4:
            sicn = np.asarray(gmsh.model.mesh.getElementQualities(etags, "minSICN"))
            out["tet_count"] = len(etags)
            out["tet_sicn_min"] = float(sicn.min())
            out["tet_sicn_p01"] = float(np.percentile(sicn, 1))
            out["tet_below_005"] = int(np.count_nonzero(sicn < 0.05))
        elif int(et) == 6:
            sj = np.asarray(gmsh.model.mesh.getElementQualities(etags, "minSJ"))
            rows = np.asarray(conn, dtype=np.int64).reshape(-1, 6)
            idx = np.searchsorted(tags, rows)
            pts = coords[idx]
            # first-layer thickness: bottom triangle to top triangle
            h = np.linalg.norm(pts[:, 3:6, :] - pts[:, 0:3, :], axis=2).mean(axis=1)
            out["prism_count"] = len(etags)
            out["prism_sj_min"] = float(sj.min())
            out["prism_h_min"] = float(h.min())
            out["prism_h_max"] = float(h.max())
        else:
            out.setdefault("other", []).append(name)
    gmsh.finalize()
    return out


def main() -> int:
    base = load_policy()
    case = G.build_pygeo_case(
        "lhs100_seed42", 0, ROOT / "pygeo"
    )
    surface = G.build_surface(case, level="laptop_smoke", te_variant="te_1p0mm")

    trials = [
        ("baseline (no optimize)", None, 0),
        ("Relocate3D core-only", "Relocate3D", 2),
        ("Netgen core-only", "Netgen", 1),
        ("HighOrderFast core-only", "HighOrderFast", 1),
    ]
    results = []
    for label, method, passes in trials:
        policy = copy.deepcopy(base)
        policy["gmsh"]["post_generation_optimization"] = (
            "disabled_preserve_prism_schedule" if method is None else "core_volume_only"
        )
        cand = policy["gmsh"]["retries"][0]
        if method is not None:
            cand["optimize"] = method
        cand["optimize_passes"] = passes
        target = ROOT / label.split()[0].lower().replace("(", "")
        if target.exists():
            shutil.rmtree(target)
        try:
            report = P.generate_mesh(
                surface, output_dir=target, level="laptop_smoke",
                candidate_index=0, policy=policy,
            )
            m = measure(Path(report["mesh_msh"]))
            results.append((label, m))
            print(
                f"{label:<26s} tets {m['tet_count']:6d} "
                f"SICN min {m['tet_sicn_min']:.5f} p01 {m['tet_sicn_p01']:.4f} "
                f"below0.05 {m['tet_below_005']:4d} | "
                f"prisms {m['prism_count']} SJ {m['prism_sj_min']:.4f} "
                f"h [{m['prism_h_min']:.6e}, {m['prism_h_max']:.6e}]",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - failure is a result
            print(f"{label:<26s} FAILED {type(exc).__name__}: {str(exc)[:70]}", flush=True)
    if len(results) >= 2:
        b = results[0][1]
        print("\nprism schedule preserved? (baseline is the reference)")
        for label, m in results[1:]:
            same = (
                abs(m["prism_h_min"] - b["prism_h_min"]) < 1e-15
                and abs(m["prism_h_max"] - b["prism_h_max"]) < 1e-15
                and abs(m["prism_sj_min"] - b["prism_sj_min"]) < 1e-12
            )
            print(
                f"  {label:<26s} {'YES' if same else 'NO'}"
                f"   dSJ {m['prism_sj_min'] - b['prism_sj_min']:+.3e}"
                f"   dh_min {m['prism_h_min'] - b['prism_h_min']:+.3e}"
                f"   tets<0.05 {b['tet_below_005']} -> {m['tet_below_005']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
