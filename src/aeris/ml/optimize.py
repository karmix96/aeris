"""Design search over a trained/promoted surrogate. AERIS_ML_W3_OPTIMIZE_V1

Finds raw design/condition vectors that optimize one predicted target inside
the model's training design space (box bounds from the envelope), with
optional inequality constraints on OTHER predicted targets and optional
conformal risk-aversion (score = prediction -/+ k * q_hat, Wave-2 artifact).

Method (v1, deliberately derivative-free and reproducible): large LHS screen,
then Nelder-Mead refinement of the top seeds within bounds. Every evaluated
candidate is a legitimate model input built through the same feature-set
materialization used at inference time.
"""

from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.active_learning.pool import resolve_design_space, _expanded
from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso

_CONSTRAINT_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*(<=|>=)\s*([-+0-9.eE]+)\s*$")


@dataclass
class OptimizeResult:
    report_path: Path
    candidates_csv_path: Path
    best: dict[str, Any]


def parse_constraint(text: str) -> tuple[str, str, float]:
    m = _CONSTRAINT_RE.match(text)
    if not m:
        raise ValueError(
            f"Invalid constraint '{text}'. Use '<target><=value' or '<target>>=value', e.g. cm>=-0.05"
        )
    return m.group(1), m.group(2), float(m.group(3))


def _load_model(run: Path) -> tuple[Any, Path]:
    model_path = run / "models" / "model.pkl"
    if not model_path.exists():
        model_path = run / "model.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"Could not find model.pkl under {run}")
    with model_path.open("rb") as f:
        return pickle.load(f), model_path


def optimize_design(
    *,
    model_run_dir: str | Path,
    objective_target: str,
    mode: str = "maximize",
    target_value: float | None = None,
    n_samples: int = 4000,
    n_refine: int = 8,
    refine_iters: int = 60,
    seed: int = 123,
    risk_k: float = 0.0,
    fixed: dict[str, float] | None = None,
    constraints: list[str] | None = None,
    expand_frac: float = 0.0,
    require_promoted_model_gate: bool = True,
    output_dir: str | Path | None = None,
    top_k: int = 20,
) -> OptimizeResult:
    run = Path(model_run_dir).expanduser().resolve()
    if mode not in {"maximize", "minimize", "target"}:
        raise ValueError("mode must be maximize | minimize | target")
    if mode == "target" and target_value is None:
        raise ValueError("mode='target' requires target_value")
    if n_samples < 1 or top_k < 1 or n_refine < 0 or refine_iters < 0:
        raise ValueError("n_samples/top_k must be >=1; n_refine/refine_iters >=0")
    if risk_k < 0:
        raise ValueError("risk_k must be >= 0")
    fixed = {k: float(v) for k, v in (fixed or {}).items()}
    parsed_constraints = [parse_constraint(c) for c in (constraints or [])]

    if require_promoted_model_gate:
        from aeris.ml.model_promotion import require_promoted_model
        require_promoted_model(run)

    space = resolve_design_space(run)
    model, model_path = _load_model(run)
    train_config = space.train_config
    feature_columns = list(train_config.get("feature_columns", []))
    target_columns = list(train_config.get("target_columns", []))
    if objective_target not in target_columns:
        raise ValueError(f"objective_target '{objective_target}' not in model targets {target_columns}")
    for tgt, _, _ in parsed_constraints:
        if tgt not in target_columns:
            raise ValueError(f"constraint target '{tgt}' not in model targets {target_columns}")
    ti = target_columns.index(objective_target)

    unknown = sorted(set(fixed) - set(space.source_columns))
    if unknown:
        raise ValueError(f"fixed columns not in design space: {unknown}")
    free_cols = [c for c in space.source_columns if c not in fixed]
    lo = np.array([_expanded(space.bounds[c]["min"], space.bounds[c]["max"], expand_frac)[0] for c in free_cols])
    hi = np.array([_expanded(space.bounds[c]["min"], space.bounds[c]["max"], expand_frac)[1] for c in free_cols])

    q_hat: dict[str, float] | None = None
    calibration_sha: str | None = None
    if risk_k > 0.0:
        from aeris.ml.conformal import load_conformal_calibration
        cal_path = run / "conformal_calibration.json"
        calibration = load_conformal_calibration(cal_path)
        q_hat = {k: float(v) for k, v in calibration.q_hat.items()}
        calibration_sha = file_sha256(cal_path)

    fs_name = space.feature_set_name

    def predict_raw(raw: np.ndarray) -> np.ndarray:
        df = pd.DataFrame(
            {c: (raw[:, free_cols.index(c)] if c in free_cols else np.full(raw.shape[0], fixed[c]))
             for c in space.source_columns}
        )
        if fs_name:
            from aeris.ml.feature_set_inference import prepare_dataframe_for_feature_set_inference
            prepared = prepare_dataframe_for_feature_set_inference(
                df, train_config=train_config, feature_set_name=fs_name
            )
            df = prepared.df
        missing = [c for c in feature_columns if c not in df.columns]
        if missing:
            raise ValueError(f"Prepared frame missing model feature columns: {missing}")
        X = df[feature_columns].to_numpy(dtype=float)
        pred = np.asarray(model.predict(X), dtype=float)
        if pred.ndim == 1:
            pred = pred.reshape(-1, 1)
        if pred.shape[1] != len(target_columns):
            raise ValueError(
                f"Model predicted {pred.shape[1]} targets, train_config declares {len(target_columns)}."
            )
        return pred

    def score(pred: np.ndarray) -> np.ndarray:
        p = pred[:, ti]
        if mode == "maximize":
            obj = p - (risk_k * q_hat[objective_target] if q_hat else 0.0)
        elif mode == "minimize":
            obj = -(p + (risk_k * q_hat[objective_target] if q_hat else 0.0))
        else:
            obj = -(np.abs(p - float(target_value)) + (risk_k * q_hat[objective_target] if q_hat else 0.0))
        penalty = np.zeros_like(obj)
        for tgt, op, val in parsed_constraints:
            v = pred[:, target_columns.index(tgt)]
            viol = np.maximum(0.0, val - v) if op == ">=" else np.maximum(0.0, v - val)
            penalty += viol / (abs(val) + 1e-9)
        return obj - 1e3 * penalty

    from scipy.stats import qmc
    rng_unit = qmc.LatinHypercube(d=len(free_cols), seed=seed).random(n=n_samples) if free_cols else np.zeros((n_samples, 0))
    raw = qmc.scale(rng_unit, lo, hi) if free_cols else rng_unit
    preds = predict_raw(raw)
    scores = score(preds)

    order = np.argsort(-scores)
    cand_raw = [raw[i] for i in order[: max(top_k, n_refine)]]
    cand_scores = [float(scores[i]) for i in order[: max(top_k, n_refine)]]

    n_local_evals = 0
    if free_cols and n_refine > 0 and refine_iters > 0:
        from scipy.optimize import minimize

        def neg_score_single(x: np.ndarray) -> float:
            nonlocal n_local_evals
            n_local_evals += 1
            x = np.clip(x, lo, hi)
            return -float(score(predict_raw(x.reshape(1, -1)))[0])

        refined: list[tuple[np.ndarray, float]] = []
        for x0 in cand_raw[:n_refine]:
            res = minimize(
                neg_score_single, np.asarray(x0, dtype=float), method="Nelder-Mead",
                bounds=list(zip(lo, hi)), options={"maxiter": refine_iters, "xatol": 1e-4, "fatol": 1e-6},
            )
            refined.append((np.clip(res.x, lo, hi), -float(res.fun)))
        cand_raw = cand_raw + [r[0] for r in refined]
        cand_scores = cand_scores + [r[1] for r in refined]

    all_raw = np.asarray(cand_raw, dtype=float).reshape(len(cand_raw), len(free_cols))
    all_pred = predict_raw(all_raw)
    all_score = score(all_pred)
    final_order = np.argsort(-all_score)[:top_k]

    rows: list[dict[str, Any]] = []
    for rank, i in enumerate(final_order, start=1):
        row: dict[str, Any] = {"rank": rank, "objective_score": float(all_score[i])}
        for j, c in enumerate(free_cols):
            row[c] = float(all_raw[i, j])
        for c, v in fixed.items():
            row[c] = float(v)
        for tj, t in enumerate(target_columns):
            row[f"pred__{t}"] = float(all_pred[i, tj])
        for tgt, op, val in parsed_constraints:
            v = float(all_pred[i, target_columns.index(tgt)])
            row[f"constraint_slack__{tgt}"] = (v - val) if op == ">=" else (val - v)
        if q_hat:
            row[f"q_hat__{objective_target}"] = q_hat[objective_target]
        rows.append(row)

    out = Path(output_dir).expanduser().resolve() if output_dir else run / "optimization" / f"opt_{objective_target}_{mode}"
    out.mkdir(parents=True, exist_ok=True)
    cand_csv = out / "top_candidates.csv"
    pd.DataFrame(rows).to_csv(cand_csv, index=False)

    report = {
        "schema_version": "aeris.design_optimization_report.v1",
        "created_utc": utc_now_iso(),
        "model_run_dir": str(run),
        "model_pkl_sha256": file_sha256(model_path),
        "promoted_model_gate": bool(require_promoted_model_gate),
        "feature_set_name": fs_name,
        "decision_columns": space.source_columns,
        "bounds": space.bounds,
        "expand_frac": float(expand_frac),
        "fixed": fixed,
        "objective": {"target": objective_target, "mode": mode, "target_value": target_value,
                       "risk_k": float(risk_k), "conformal_calibration_sha256": calibration_sha},
        "constraints": [{"target": t, "op": o, "value": v} for t, o, v in parsed_constraints],
        "search": {"n_samples": int(n_samples), "n_refine": int(n_refine),
                    "refine_iters": int(refine_iters), "n_local_evals": int(n_local_evals),
                    "seed": int(seed), "top_k": int(top_k)},
        "best": rows[0] if rows else None,
        "candidates_csv": str(cand_csv),
        "honesty_note": (
            "Optimum of the SURROGATE inside its training envelope — a design "
            "candidate for solver verification, not a certified aerodynamic optimum."
        ),
    }
    report_path = out / "optimization_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return OptimizeResult(report_path, cand_csv, rows[0] if rows else {})
