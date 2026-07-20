"""Active-learning campaign rounds + stopping criterion. AERIS_ML_W3_CAMPAIGN_V1

A campaign directory holds rounds.jsonl (one record per completed retrain
round). evaluate_stopping() turns that history into an explicit, reasoned
CONTINUE/STOP verdict — the "train in batches until the learning curve says
we are good" logic, with patience + minimum-improvement rules and a written
campaign_report.json (+ optional curve plot).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from aeris.ml.manifest import utc_now_iso

ROUNDS_FILENAME = "rounds.jsonl"


@dataclass
class StopDecision:
    verdict: str                      # "CONTINUE" | "STOP"
    reasons: list[str]
    metric: str
    mode: str                         # "maximize" | "minimize"
    n_rounds: int
    best_round: int | None
    best_value: float | None
    recent_improvement: float | None
    series: list[dict[str, Any]] = field(default_factory=list)
    report_path: Path | None = None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _dotted(d: dict[str, Any], path: str) -> float:
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError(f"Metric path '{path}' not found (missing '{key}').")
        cur = cur[key]
    return float(cur)


def record_round(
    campaign_dir: str | Path,
    *,
    model_run_dir: str | Path,
    batch_csv: str | Path | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Append one completed retrain round to the campaign ledger."""
    camp = Path(campaign_dir).expanduser().resolve()
    camp.mkdir(parents=True, exist_ok=True)
    run = Path(model_run_dir).expanduser().resolve()

    metrics = _read_json(run / "metrics.json")
    train_config = _read_json(run / "train_config.json")

    n_train_rows: int | None = None
    n_train_groups: int | None = None
    rows_path = run / "train_rows.csv"
    if rows_path.exists():
        rows_df = pd.read_csv(rows_path)
        n_train_rows = int(len(rows_df))
        group_col = str(train_config.get("group_column") or "geometry_id")
        if group_col in rows_df.columns:
            n_train_groups = int(rows_df[group_col].nunique())

    ledger = camp / ROUNDS_FILENAME
    prior = 0
    if ledger.exists():
        prior = sum(1 for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())

    record = {
        "schema_version": "aeris.al_campaign_round.v1",
        "round": prior + 1,
        "recorded_utc": utc_now_iso(),
        "model_run_dir": str(run),
        "batch_csv": None if batch_csv is None else str(Path(batch_csv).expanduser().resolve()),
        "notes": notes,
        "n_train_rows": n_train_rows,
        "n_train_groups": n_train_groups,
        "metrics": metrics,
    }
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def _load_rounds(campaign_dir: Path) -> list[dict[str, Any]]:
    ledger = campaign_dir / ROUNDS_FILENAME
    if not ledger.exists():
        raise FileNotFoundError(
            f"No {ROUNDS_FILENAME} in {campaign_dir}. Record at least one round "
            "(aeris ml al-status --record-run <model_run_dir>)."
        )
    rounds = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rounds:
        raise ValueError(f"{ledger} contains no rounds.")
    return rounds


def evaluate_stopping(
    campaign_dir: str | Path,
    *,
    metric: str = "val.overall.r2_mean",
    mode: str | None = None,
    min_rounds: int = 3,
    patience: int = 2,
    min_delta: float = 0.005,
    write_report: bool = True,
    make_plot: bool = True,
) -> StopDecision:
    """CONTINUE/STOP verdict from the recorded round history.

    STOP iff n_rounds >= min_rounds AND the best value achieved in the last
    `patience` rounds improves on the best value before that window by less
    than `min_delta` (direction-aware). Reasons are always spelled out.
    """
    camp = Path(campaign_dir).expanduser().resolve()
    rounds = _load_rounds(camp)

    if mode is None:
        mode = "minimize" if ("rmse" in metric.lower() or "mae" in metric.lower()) else "maximize"
    if mode not in {"maximize", "minimize"}:
        raise ValueError("mode must be 'maximize' or 'minimize'")
    sign = 1.0 if mode == "maximize" else -1.0

    series: list[dict[str, Any]] = []
    for rec in rounds:
        series.append({
            "round": int(rec["round"]),
            "value": _dotted(rec.get("metrics", {}), metric),
            "n_train_rows": rec.get("n_train_rows"),
            "n_train_groups": rec.get("n_train_groups"),
            "model_run_dir": rec.get("model_run_dir"),
        })

    values = [s["value"] for s in series]
    oriented = [sign * v for v in values]
    best_idx = max(range(len(oriented)), key=lambda i: oriented[i])
    best_round = series[best_idx]["round"]
    best_value = values[best_idx]

    n = len(series)
    reasons: list[str] = []
    recent_improvement: float | None = None
    if n < min_rounds:
        verdict = "CONTINUE"
        reasons.append(f"only {n} round(s) recorded < min_rounds={min_rounds}")
    else:
        window = min(patience, n - 1)
        if window <= 0:
            verdict = "CONTINUE"
            reasons.append("not enough history for a patience window")
        else:
            best_before = max(oriented[: n - window])
            best_recent = max(oriented[n - window :])
            recent_improvement = sign * (best_recent - best_before)
            improved = (best_recent - best_before) >= min_delta
            if improved:
                verdict = "CONTINUE"
                reasons.append(
                    f"best {metric} improved by {recent_improvement:+.6g} over the last "
                    f"{window} round(s) (>= min_delta={min_delta:g})"
                )
            else:
                verdict = "STOP"
                reasons.append(
                    f"best {metric} improved by only {recent_improvement:+.6g} over the last "
                    f"{window} round(s) (< min_delta={min_delta:g}) — learning curve plateau"
                )
    reasons.append(f"best so far: round {best_round} with {metric}={best_value:.6g} ({mode})")

    decision = StopDecision(
        verdict=verdict, reasons=reasons, metric=metric, mode=mode, n_rounds=n,
        best_round=best_round, best_value=best_value,
        recent_improvement=recent_improvement, series=series,
    )

    if write_report:
        pd.DataFrame(series).to_csv(camp / "campaign_curve.csv", index=False)
        report = {
            "schema_version": "aeris.al_campaign_report.v1",
            "created_utc": utc_now_iso(),
            "campaign_dir": str(camp),
            "metric": metric, "mode": mode,
            "rules": {"min_rounds": min_rounds, "patience": patience, "min_delta": min_delta},
            "verdict": verdict, "reasons": reasons,
            "best_round": best_round, "best_value": best_value,
            "recent_improvement": recent_improvement,
            "series": series,
            "next_step_note": (
                "If CONTINUE: rank the pool with `aeris ml suggest-samples`, run the "
                "selected batch through the dataset aero pipeline, re-curate + promote, "
                "retrain, then record the new run here. Batch->aero ingestion is the "
                "dataset module's job (tracked as ML-W3B)."
            ),
        }
        rp = camp / "campaign_report.json"
        rp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        decision.report_path = rp
        if make_plot:
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt

                xs = [s["n_train_groups"] or s["round"] for s in series]
                xlabel = "training geometries" if all(s["n_train_groups"] for s in series) else "round"
                fig, ax = plt.subplots(figsize=(6.0, 3.6))
                ax.plot(xs, values, marker="o")
                ax.set_xlabel(xlabel); ax.set_ylabel(metric)
                ax.set_title(f"AL campaign — verdict: {verdict}")
                ax.grid(True, alpha=0.3)
                fig.tight_layout()
                fig.savefig(camp / "campaign_curve.png", dpi=140)
                plt.close(fig)
            except Exception:
                pass  # plotting is best-effort; the JSON/CSV verdict is authoritative
    return decision
