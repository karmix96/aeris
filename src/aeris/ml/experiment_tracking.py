from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# AERIS_MLFLOW_SQLITE_BACKEND_V2_2
def _aeris_mlflow_sqlite_uri(tracking_dir: Path) -> str:
    tracking_dir = Path(tracking_dir).expanduser()
    tracking_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(tracking_dir / 'mlflow.db').resolve()}"
from typing import Any, Iterable


def _json_default(value: Any) -> Any:
    try:
        from pathlib import Path as _Path
        if isinstance(value, _Path):
            return str(value)
    except Exception:
        pass
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except Exception:
        pass
    return str(value)


def _metric_value(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _flatten_metrics(row: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in row.items():
        if key == "epoch":
            continue
        val = _metric_value(value)
        if val is not None:
            # Keep MLflow/TensorBoard metric names path-like and stable.
            out[str(key).replace(" ", "_")] = val
    return out


@dataclass
class TrackerState:
    backends_requested: list[str]
    backends_active: list[str] = field(default_factory=list)
    backends_unavailable: dict[str, str] = field(default_factory=dict)
    tracking_dir: Path | None = None
    mlflow_tracking_uri: str | None = None
    tensorboard_log_dir: str | None = None
    wandb_mode: str | None = None
    warnings: list[str] = field(default_factory=list)


class ExperimentTracker:
    """Optional local/offline experiment-tracking fanout for AERIS training.

    This adapter is intentionally optional: AERIS keeps writing its native CSV/JSON/PNG
    evidence even if MLflow, TensorBoard, or W&B are not installed.
    """

    def __init__(
        self,
        *,
        output_dir: Path,
        backends: Iterable[str] | None,
        experiment_name: str = "aeris",
        run_name: str | None = None,
        params: dict[str, Any] | None = None,
        tags: dict[str, Any] | None = None,
        wandb_mode: str = "offline",
    ) -> None:
        self.output_dir = Path(output_dir).expanduser()
        self.tracking_dir = self.output_dir / "tracking"
        self.backends_requested = [str(b).strip().lower() for b in (backends or []) if str(b).strip()]
        self.experiment_name = experiment_name
        self.run_name = run_name or self.output_dir.name
        self.params = dict(params or {})
        self.tags = dict(tags or {})
        self.wandb_mode = wandb_mode or "offline"
        self.state = TrackerState(
            backends_requested=list(self.backends_requested),
            tracking_dir=self.tracking_dir,
            wandb_mode=self.wandb_mode,
        )
        self._mlflow = None
        self._mlflow_run = None
        self._tb_writer = None
        self._wandb = None
        self._wandb_run = None

    def start(self) -> TrackerState:
        self.tracking_dir.mkdir(parents=True, exist_ok=True)
        if "mlflow" in self.backends_requested:
            self._start_mlflow()
        if "tensorboard" in self.backends_requested or "tb" in self.backends_requested:
            self._start_tensorboard()
        if "wandb" in self.backends_requested:
            self._start_wandb()
        self._write_state()
        return self.state

    def log_epoch(self, row: dict[str, Any]) -> None:
        step = int(row.get("epoch", 0) or 0)
        metrics = _flatten_metrics(row)
        if not metrics:
            return
        if self._mlflow is not None:
            for key, value in metrics.items():
                try:
                    self._mlflow.log_metric(key, value, step=step)
                except Exception as exc:  # pragma: no cover - depends on optional backend
                    self.state.warnings.append(f"MLflow metric log failed for {key}: {exc}")
                    break
        if self._tb_writer is not None:
            for key, value in metrics.items():
                try:
                    self._tb_writer.add_scalar(key, value, step)
                except Exception as exc:  # pragma: no cover
                    self.state.warnings.append(f"TensorBoard scalar log failed for {key}: {exc}")
                    break
            try:
                self._tb_writer.flush()
            except Exception:
                pass
        if self._wandb_run is not None:
            try:
                payload = dict(metrics)
                payload["epoch"] = step
                self._wandb.log(payload, step=step)
            except Exception as exc:  # pragma: no cover
                self.state.warnings.append(f"W&B metric log failed: {exc}")
        self._write_state()

    def log_final_artifacts(self, artifact_paths: Iterable[Path | str]) -> None:
        paths = [Path(p) for p in artifact_paths if p]
        if self._mlflow is not None:
            for path in paths:
                try:
                    if path.exists():
                        if path.is_dir():
                            self._mlflow.log_artifacts(str(path), artifact_path=path.name)
                        else:
                            self._mlflow.log_artifact(str(path), artifact_path=path.parent.name)
                except Exception as exc:  # pragma: no cover
                    self.state.warnings.append(f"MLflow artifact log failed for {path}: {exc}")
        if self._wandb_run is not None:
            # Keep W&B minimal/offline. Detailed artifact objects can be added later.
            for path in paths:
                try:
                    if path.exists() and path.is_file():
                        self._wandb.save(str(path))
                except Exception as exc:  # pragma: no cover
                    self.state.warnings.append(f"W&B artifact save failed for {path}: {exc}")
        self._write_state()

    def close(self) -> TrackerState:
        if self._tb_writer is not None:
            try:
                self._tb_writer.close()
            except Exception:
                pass
        if self._wandb_run is not None:
            try:
                self._wandb.finish()
            except Exception:
                pass
        if self._mlflow is not None and self._mlflow_run is not None:
            try:
                self._mlflow.end_run()
            except Exception:
                pass
        self._write_state()
        return self.state

    def _start_mlflow(self) -> None:
        try:
            import mlflow  # type: ignore
        except Exception as exc:
            self.state.backends_unavailable["mlflow"] = f"import failed: {exc}"
            return
        tracking_uri = _aeris_mlflow_sqlite_uri(self.tracking_dir)
        try:
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment(self.experiment_name)
            self._mlflow_run = mlflow.start_run(run_name=self.run_name)
            if self.params:
                mlflow.log_params(_stringify_flat_params(self.params))
            for key, value in self.tags.items():
                mlflow.set_tag(str(key), str(value))
            mlflow.set_tag("aeris.output_dir", str(self.output_dir.resolve()))
            self._mlflow = mlflow
            self.state.backends_active.append("mlflow")
            self.state.mlflow_tracking_uri = tracking_uri
        except Exception as exc:
            self.state.backends_unavailable["mlflow"] = f"start failed: {exc}"
            self._mlflow = None

    def _start_tensorboard(self) -> None:
        writer_cls = None
        try:
            from torch.utils.tensorboard import SummaryWriter  # type: ignore
            writer_cls = SummaryWriter
        except Exception:
            try:
                from tensorboardX import SummaryWriter  # type: ignore
                writer_cls = SummaryWriter
            except Exception as exc:
                self.state.backends_unavailable["tensorboard"] = f"import failed: {exc}"
                return
        log_dir = self.tracking_dir / "tensorboard" / self.run_name
        try:
            self._tb_writer = writer_cls(log_dir=str(log_dir))
            self.state.backends_active.append("tensorboard")
            self.state.tensorboard_log_dir = str(log_dir.resolve())
        except Exception as exc:
            self.state.backends_unavailable["tensorboard"] = f"start failed: {exc}"
            self._tb_writer = None

    def _start_wandb(self) -> None:
        # Privacy-first: default to offline mode unless the user explicitly changes it.
        os.environ.setdefault("WANDB_MODE", self.wandb_mode)
        try:
            import wandb  # type: ignore
        except Exception as exc:
            self.state.backends_unavailable["wandb"] = f"import failed: {exc}"
            return
        try:
            self._wandb_run = wandb.init(
                project=self.experiment_name,
                name=self.run_name,
                dir=str(self.tracking_dir.resolve()),
                mode=self.wandb_mode,
                config=self.params,
                tags=[str(k) for k, v in self.tags.items() if bool(v)],
            )
            self._wandb = wandb
            self.state.backends_active.append("wandb")
        except Exception as exc:
            self.state.backends_unavailable["wandb"] = f"start failed: {exc}"
            self._wandb = None
            self._wandb_run = None

    def _write_state(self) -> None:
        path = self.tracking_dir / "experiment_tracking_manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.state.__dict__, indent=2, default=_json_default), encoding="utf-8")


def _stringify_flat_params(params: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    out: dict[str, str | int | float | bool | None] = {}
    for key, value in params.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[str(key)] = value
        else:
            out[str(key)] = json.dumps(value, default=_json_default, sort_keys=True)
    return out


def build_experiment_tracker(
    *,
    output_dir: Path,
    backends: Iterable[str] | None,
    experiment_name: str = "aeris",
    run_name: str | None = None,
    params: dict[str, Any] | None = None,
    tags: dict[str, Any] | None = None,
    wandb_mode: str = "offline",
) -> ExperimentTracker:
    tracker = ExperimentTracker(
        output_dir=output_dir,
        backends=backends,
        experiment_name=experiment_name,
        run_name=run_name,
        params=params,
        tags=tags,
        wandb_mode=wandb_mode,
    )
    tracker.start()
    return tracker
