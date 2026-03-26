from __future__ import annotations

import json
from pathlib import Path

RUNS_ROOT = Path("data/runs")


def _latest_run_matching_all(required_tags: list[str]) -> Path:
    matches: list[Path] = []

    for p in RUNS_ROOT.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if all(tag in name for tag in required_tags):
            matches.append(p)

    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if not matches:
        raise FileNotFoundError(f"No run directory found containing all tags: {required_tags}")

    return matches[0]


def _find_aero_result_json(run_root: Path) -> Path:
    candidates = [
        run_root / "aero" / "aero_result.json",
        run_root / "aero_result.json",
        run_root / "artifacts" / "aero_result.json",
    ]
    for path in candidates:
        if path.exists():
            return path

    recursive = list(run_root.rglob("aero_result.json"))
    if recursive:
        return recursive[0]

    raise FileNotFoundError(f"No aero_result.json found under {run_root}")


def load_result(run_root: Path) -> dict:
    path = _find_aero_result_json(run_root)
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value) -> str:
    if value is None:
        return "None"
    return f"{float(value):+.6f}"


def main() -> None:
    run_zero = _latest_run_matching_all(["ctrl0", "recheck"])
    run_plus = _latest_run_matching_all(["ctrlp5", "recheck"])
    run_minus = _latest_run_matching_all(["ctrlm5", "recheck"])

    zero = load_result(run_zero)
    plus = load_result(run_plus)
    minus = load_result(run_minus)

    print("\n=== CONTROL RESPONSE SUMMARY ===\n")
    print("Runs used:")
    print(f"  minus5: {run_minus}")
    print(f"  zero  : {run_zero}")
    print(f"  plus5 : {run_plus}")

    print("\nScalars:")
    for key in ["cl", "cd", "cm", "l_over_d", "x_np"]:
        z = zero["scalars"].get(key)
        p = plus["scalars"].get(key)
        m = minus["scalars"].get(key)

        print(
            f"{key.upper():<8} "
            f"minus5={fmt(m)}   zero={fmt(z)}   plus5={fmt(p)}   "
            f"d(+5-0)={fmt(None if z is None or p is None else p - z)}   "
            f"d(-5-0)={fmt(None if z is None or m is None else m - z)}"
        )

    print("\nControl diagnostics:")
    for label, payload in [("minus5", minus), ("zero", zero), ("plus5", plus)]:
        meta = payload["solver_metadata"]
        diag = meta["control_diagnostics"]
        print(
            f"{label:<6} "
            f"u={meta['control_input_deg']:+.1f}  "
            f"declares={meta['geometry_declares_controls']}  "
            f"airplane_has={meta['airplane_has_controls']}  "
            f"CONTROL={diag['airplane_avl_has_control_blocks']}  "
            f"d1={diag['keystrokes_has_d1_command']}  "
            f"n_ctrl={diag['stdout_control_variables']}"
        )

    print("\nQuick sanity:")
    cl0 = zero["scalars"]["cl"]
    clp = plus["scalars"]["cl"]
    clm = minus["scalars"]["cl"]

    cm0 = zero["scalars"]["cm"]
    cmp = plus["scalars"]["cm"]
    cmm = minus["scalars"]["cm"]

    print(f"CL ordering:  minus5 < zero < plus5  ->  {clm < cl0 < clp}")
    print(f"Cm ordering:  plus5 < zero < minus5 ->  {cmp < cm0 < cmm}")


if __name__ == "__main__":
    main()