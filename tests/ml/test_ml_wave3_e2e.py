"""Wave-3 E2E regression tests. AERIS_ML_W3_TESTS_V1

Covers: pool bounds/seed/fixed determinism, campaign stopping verdicts,
round recording, optimizer convergence on a known analytic optimum,
constraint steering, conformal risk-aversion, and GUI wiring markers.
Pure unit tests: no solvers, no promoted datasets, no Streamlit runtime.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


FEATURES = ["x1", "x2"]


def _make_run(tmp_path: Path, model, targets: list[str]) -> Path:
    run = tmp_path / "run"
    (run / "models").mkdir(parents=True)
    with (run / "models" / "model.pkl").open("wb") as f:
        pickle.dump(model, f)
    (run / "train_config.json").write_text(
        json.dumps({"feature_columns": FEATURES, "target_columns": targets}),
        encoding="utf-8",
    )
    (run / "training_envelope.json").write_text(
        json.dumps({"feature_ranges": {
            "x1": {"min": -1.0, "max": 1.0},
            "x2": {"min": -1.0, "max": 1.0},
        }}),
        encoding="utf-8",
    )
    return run


class _QuadModel:
    """cl = -(x1-0.3)^2 - (x2+0.2)^2  -> unique max 0 at (0.3, -0.2)."""

    def predict(self, X):
        X = np.asarray(X, dtype=float)
        cl = -((X[:, 0] - 0.3) ** 2) - ((X[:, 1] + 0.2) ** 2)
        return cl.reshape(-1, 1)


class _QuadPlusCdModel:
    """targets [cl, cd]; cd = x1 so 'cd<=0' forces x1 <= 0."""

    def predict(self, X):
        X = np.asarray(X, dtype=float)
        cl = -((X[:, 0] - 0.3) ** 2) - ((X[:, 1] + 0.2) ** 2)
        return np.column_stack([cl, X[:, 0]])


# ---------------------------------------------------------------- pool
def test_pool_respects_bounds_seed_and_fixed(tmp_path: Path) -> None:
    from aeris.ml.active_learning.pool import generate_candidate_pool

    run = _make_run(tmp_path, _QuadModel(), ["cl"])
    r1 = generate_candidate_pool(model_run_dir=run, n_samples=200, seed=7,
                                 fixed={"x2": 0.5})
    df1 = pd.read_csv(r1.pool_csv_path)
    assert list(df1.columns) == FEATURES
    assert len(df1) == 200
    assert df1["x1"].between(-1.0, 1.0).all()
    assert (df1["x2"] == 0.5).all()
    manifest = json.loads(r1.manifest_path.read_text())
    assert manifest["bounds"]["x1"]["source"] == "training_envelope"

    r2 = generate_candidate_pool(model_run_dir=run, n_samples=200, seed=7,
                                 fixed={"x2": 0.5},
                                 output_dir=tmp_path / "pool2")
    df2 = pd.read_csv(r2.pool_csv_path)
    assert np.allclose(df1["x1"].to_numpy(), df2["x1"].to_numpy())  # seed-deterministic


def test_pool_expand_frac_widens_bounds(tmp_path: Path) -> None:
    from aeris.ml.active_learning.pool import generate_candidate_pool

    run = _make_run(tmp_path, _QuadModel(), ["cl"])
    r = generate_candidate_pool(model_run_dir=run, n_samples=500, seed=1,
                                expand_frac=0.25)
    df = pd.read_csv(r.pool_csv_path)
    assert df["x1"].min() < -1.0 and df["x1"].max() > 1.0


# ---------------------------------------------------------------- campaign
def _fake_round_run(tmp_path: Path, idx: int, r2: float, n_groups: int) -> Path:
    run = tmp_path / f"round_run_{idx}"
    run.mkdir()
    (run / "metrics.json").write_text(json.dumps(
        {"val": {"overall": {"r2_mean": r2, "rmse_mean": 1.0 - r2}},
         "test": {"overall": {"r2_mean": r2 - 0.01}}}))
    (run / "train_config.json").write_text(json.dumps(
        {"feature_columns": FEATURES, "target_columns": ["cl"],
         "group_column": "geometry_id"}))
    rows = pd.DataFrame({"geometry_id": np.repeat(np.arange(n_groups), 3),
                         "x1": 0.0, "x2": 0.0})
    rows.to_csv(run / "train_rows.csv", index=False)
    return run


def test_campaign_continue_then_stop_on_plateau(tmp_path: Path) -> None:
    from aeris.ml.active_learning.campaign import evaluate_stopping, record_round

    camp = tmp_path / "camp"
    r2s = [0.80, 0.86, 0.90, 0.902, 0.903]  # clear gains, then plateau
    for i, r2 in enumerate(r2s, start=1):
        run = _fake_round_run(tmp_path, i, r2, n_groups=10 * i)
        rec = record_round(camp, model_run_dir=run, notes=f"round {i}")
        assert rec["round"] == i and rec["n_train_groups"] == 10 * i

    early = evaluate_stopping(camp, min_rounds=6, patience=2, min_delta=0.005,
                              make_plot=False)
    assert early.verdict == "CONTINUE"          # min_rounds gate

    final = evaluate_stopping(camp, min_rounds=3, patience=2, min_delta=0.005,
                              make_plot=False)
    assert final.verdict == "STOP"
    assert final.best_round == 5
    assert final.recent_improvement is not None and final.recent_improvement < 0.005
    report = json.loads((camp / "campaign_report.json").read_text())
    assert report["verdict"] == "STOP"


def test_campaign_continue_while_improving(tmp_path: Path) -> None:
    from aeris.ml.active_learning.campaign import evaluate_stopping, record_round

    camp = tmp_path / "camp2"
    for i, r2 in enumerate([0.70, 0.78, 0.85, 0.91], start=1):
        record_round(camp, model_run_dir=_fake_round_run(tmp_path, 100 + i, r2, 5 * i))
    d = evaluate_stopping(camp, min_rounds=3, patience=2, min_delta=0.005,
                          make_plot=False)
    assert d.verdict == "CONTINUE"


# ---------------------------------------------------------------- optimizer
def test_optimizer_finds_analytic_optimum(tmp_path: Path) -> None:
    from aeris.ml.optimize import optimize_design

    run = _make_run(tmp_path, _QuadModel(), ["cl"])
    res = optimize_design(model_run_dir=run, objective_target="cl",
                          mode="maximize", n_samples=1500, n_refine=4,
                          refine_iters=80, seed=3,
                          require_promoted_model_gate=False,
                          output_dir=tmp_path / "opt")
    best = res.best
    assert abs(best["x1"] - 0.3) < 0.05 and abs(best["x2"] + 0.2) < 0.05
    assert best["pred__cl"] > -0.005
    assert -1.0 <= best["x1"] <= 1.0 and -1.0 <= best["x2"] <= 1.0
    report = json.loads(res.report_path.read_text())
    assert report["objective"]["target"] == "cl"


def test_optimizer_constraint_steers_solution(tmp_path: Path) -> None:
    from aeris.ml.optimize import optimize_design

    run = _make_run(tmp_path, _QuadPlusCdModel(), ["cl", "cd"])
    res = optimize_design(model_run_dir=run, objective_target="cl",
                          mode="maximize", n_samples=1500, n_refine=4,
                          refine_iters=80, seed=3,
                          constraints=["cd<=0.0"],
                          require_promoted_model_gate=False,
                          output_dir=tmp_path / "optc")
    assert res.best["x1"] <= 0.02                      # pushed to the boundary
    assert res.best["constraint_slack__cd"] >= -0.02   # feasible (numerical slack)


def test_optimizer_risk_k_uses_conformal(tmp_path: Path) -> None:
    from aeris.ml.conformal import fit_conformal, save_conformal_calibration
    from aeris.ml.optimize import optimize_design

    run = _make_run(tmp_path, _QuadModel(), ["cl"])
    rng = np.random.default_rng(0)
    Xc = rng.uniform(-1, 1, size=(40, 2))
    yc = _QuadModel().predict(Xc) + rng.normal(0, 0.05, size=(40, 1))
    cal = fit_conformal(_QuadModel(), Xc, yc, ["cl"], alpha=0.10,
                        model_path=run / "models" / "model.pkl")
    save_conformal_calibration(cal, run / "conformal_calibration.json")

    with pytest.raises(FileNotFoundError):
        optimize_design(model_run_dir=_make_run(tmp_path / "norun", _QuadModel(), ["cl"]),
                        objective_target="cl", risk_k=1.0,
                        require_promoted_model_gate=False)

    res = optimize_design(model_run_dir=run, objective_target="cl",
                          mode="maximize", n_samples=800, n_refine=2,
                          refine_iters=40, seed=3, risk_k=1.0,
                          require_promoted_model_gate=False,
                          output_dir=tmp_path / "optr")
    q = float(cal.q_hat["cl"])
    best = res.best
    assert best[f"q_hat__cl"] == pytest.approx(q)
    assert best["objective_score"] == pytest.approx(best["pred__cl"] - q, abs=1e-6)


def test_constraint_parser_rejects_garbage() -> None:
    from aeris.ml.optimize import parse_constraint

    assert parse_constraint("cm>=-0.05") == ("cm", ">=", -0.05)
    with pytest.raises(ValueError):
        parse_constraint("cm == 5")


# ---------------------------------------------------------------- GUI wiring
def test_gui_contains_wave3_wiring() -> None:
    # Path-based (no streamlit import): repo layout tests/ml/ -> ROOT/src/aeris/gui/app.py
    app_path = Path(__file__).resolve().parents[2] / "src" / "aeris" / "gui" / "app.py"
    if not app_path.exists():  # installed-package fallback
        import aeris.gui.app as gui_app
        app_path = Path(gui_app.__file__)
    text = app_path.read_text(encoding="utf-8")
    # whitespace-insensitive so black formatting cannot break source markers
    squeezed = "".join(text.split())
    for marker in ("⑬ E2E Campaign", "⑭ Optimizer", "al-generate-pool",
                   "al-status", "--uq-method",
                   "calibrate-conformal", "with tabs[12]:", "with tabs[13]:"):
        assert marker in text, f"GUI missing Wave-3 marker: {marker}"
    assert '"ml","optimize"' in squeezed, "GUI missing Wave-3 marker: ml optimize args"
