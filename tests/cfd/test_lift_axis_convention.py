"""Every ADflow driver must set the AERIS lift axis.

AERIS meshes span +y and lift +z.  ADflow's own default is `liftIndex 2`, which
makes angle of attack a rotation about z -- into the spanwise direction, against
a root symmetry plane that forbids spanwise crossflow.  A driver that omits the
option therefore solves sideslip and reports the spanwise force as lift, without
failing, without warning, and without any sign in the residual history.

That is exactly what happened: `solve_s8.py` omitted it and every S8 CFD result
was void until it was found by noticing that a wing at 8 degrees reported a
maximum surface cp of 0.0072.  See
`AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/reports/s8_lift_index_defect_20260904.json`.

These tests are cheap and static.  They do not need ADflow installed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: Drivers that construct ADFLOW and then call the solver.  A construction site
#: that never solves cannot apply a direction to anything, but it is listed
#: anyway where it exists, because a complete-looking options dict missing this
#: one option is how the defect spread.
DRIVERS = [
    "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py",
    "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/preflight_adflow.py",
    "apps/aeris_workbench/solvers.py",
    "scripts/adflow_smoke.py",
]


def test_curated_schema_still_carries_the_convention() -> None:
    """The single source of truth must exist and must say 3."""
    from aeris.cfd.solvers.adflow.options_schema import ADFLOW_SCHEMA

    lift = [o for o in ADFLOW_SCHEMA.curated if o.native == "liftIndex"]
    assert lift, "the curated ADflow schema no longer carries liftIndex"
    assert lift[0].default == 3, (
        f"AERIS meshes span +y and lift +z, so liftIndex must be 3; "
        f"the schema says {lift[0].default}"
    )


def test_resolved_options_carry_lift_index() -> None:
    from aeris.cfd.solvers.adflow.options_schema import build_adflow_options

    effective = build_adflow_options(mesh_cgns="x.cgns", output_directory=".")
    assert effective.values["liftIndex"] == 3


@pytest.mark.parametrize("relative", DRIVERS)
def test_driver_sets_lift_index(relative: str) -> None:
    """Every driver names liftIndex somewhere in its options."""
    path = REPO / relative
    if not path.exists():  # pragma: no cover - the tree moved
        pytest.skip(f"{relative} is not present")
    source = path.read_text(encoding="utf-8")
    assert "liftIndex" in source, (
        f"{relative} constructs ADflow without setting liftIndex, so it takes "
        f"ADflow's default of 2 and applies angle of attack as sideslip on an "
        f"AERIS mesh. Set it to 3."
    )


def test_workbench_reads_the_convention_rather_than_retyping_it() -> None:
    """The workbench must take the axis from the schema, not a literal.

    A second hard-coded 3 is a second place for the convention to drift, which
    is how one driver came to disagree with the rest of the tree in the first
    place.
    """
    source = (REPO / "apps/aeris_workbench/solvers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assigned = {
        node.targets[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and node.targets
        and isinstance(node.targets[0], ast.Name)
    }
    assert "_CURATED_LIFT_INDEX" in assigned
    assert '"liftIndex": _CURATED_LIFT_INDEX' in source, (
        "the workbench should pass the schema's value, not a literal"
    )


def test_s8_solver_verifies_the_direction_it_was_given() -> None:
    """Setting the option is not enough; solve_s8.py must check it took effect.

    The check reads velDirFreeStream and liftDirection back out of ADflow after
    setAeroProblem and before the solve, so a wrong setup costs seconds instead
    of hours, and it fails closed when the arrays cannot be read at all.
    """
    source = (
        REPO / "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py"
    ).read_text(encoding="utf-8")
    assert "def verify_flow_directions" in source
    assert "veldirfreestream" in source
    assert "liftdirection" in source

    # The check must actually be CALLED, and called before the solve.  Matching
    # the bare name finds the `def` line too and passes even when the call has
    # been deleted -- confirmed by deleting it and watching this test go green.
    # So walk the AST and look for a real call inside main().
    tree = ast.parse(source)
    main = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [
        node for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "verify_flow_directions"
    ]
    assert calls, "main() never calls verify_flow_directions"

    def line_of(predicate) -> int:
        return min(
            node.lineno for node in ast.walk(main)
            if isinstance(node, ast.Call) and predicate(node)
        )

    solve_line = line_of(
        lambda n: isinstance(n.func, ast.Name) and n.func.id == "solver"
    )
    assert calls[0].lineno < solve_line, (
        "the direction check runs after the solve, which spends the run before "
        "discovering it was mis-set"
    )
