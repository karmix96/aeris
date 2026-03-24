from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from aeris.dataset.dataset_run import run_dataset_generation, _resolve_dataset_request
from aeris.dataset.models import DatasetPaths


@dataclass(frozen=True)
class DummyGeneratorConfig:
    family: str
    version: str


@dataclass(frozen=True)
class DummyOutputsConfig:
    save_plot: bool
    build_aerosandbox: bool


@dataclass(frozen=True)
class DummyControlsConfig:
    n_points: int
    n_spline_inboard: int
    n_spline_outboard: int
    segment_length_variation: float
    sweep_variation: float


@dataclass(frozen=True)
class DummySectionBoundsConfig:
    airfoil_name: str


@dataclass(frozen=True)
class DummyConfig:
    name: str
    generator: DummyGeneratorConfig
    outputs: DummyOutputsConfig
    controls: DummyControlsConfig
    section_bounds: DummySectionBoundsConfig


def _make_dataset_paths(root: Path) -> DatasetPaths:
    geometry_dir = root / "geometry"
    configs_dir = root / "configs"
    logs_dir = root / "logs"

    geometry_dir.mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    return DatasetPaths(
        root=root,
        geometry_dir=geometry_dir,
        configs_dir=configs_dir,
        logs_dir=logs_dir,
        manifest_path=root / "dataset_manifest.json",
        metadata_csv_path=root / "metadata.csv",
        failures_csv_path=root / "failures.csv",
        input_config_path=configs_dir / "input_config.yaml",
        resolved_config_json_path=configs_dir / "resolved_dataset_config.json",
    )


def _make_config() -> DummyConfig:
    return DummyConfig(
        name="baseline_cfg",
        generator=DummyGeneratorConfig(family="bwb_segmented", version="v1"),
        outputs=DummyOutputsConfig(save_plot=False, build_aerosandbox=False),
        controls=DummyControlsConfig(
            n_points=25,
            n_spline_inboard=5,
            n_spline_outboard=5,
            segment_length_variation=0.0,
            sweep_variation=0.0,
        ),
        section_bounds=DummySectionBoundsConfig(airfoil_name="naca0012"),
    )

def _make_sample(i: int) -> dict[str, float]:
    return {
        "c1_m": 1.0 + i,
        "c2_ratio": 0.5,
        "c3_ratio": 0.4,
        "c4_ratio": 0.2,
        "b_total_m": 3.0,
        "b3_ratio": 0.6,
        "split_ratio": 0.35,
        "sw1_deg": 10.0,
        "sw2_deg": 5.0,
        "sw3_deg": 2.0,
        "twist_b0_deg": 1.0,
        "twist_b1_deg": 0.5,
        "twist_b2_deg": 0.0,
        "twist_b3_deg": -1.0,
        "dihedral_b1_deg": 3.0,
        "dihedral_b2_deg": 2.0,
        "dihedral_b3_deg": 1.0,
    }


def _make_result(sample: dict[str, float], output_dir: Path) -> SimpleNamespace:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = output_dir / "summary.json"
    control_points = output_dir / "control_points.csv"
    planform_sections = output_dir / "planform_sections.csv"
    section_3d = output_dir / "section_3d.csv"

    for p in [summary, control_points, planform_sections, section_3d]:
        p.write_text("x", encoding="utf-8")

    return SimpleNamespace(
        sample=sample,
        section_geometry=SimpleNamespace(
            twist_array_deg=[1.0, 0.5, 0.0, -1.0],
            dihedral_array_deg=[3.0, 2.0, 1.0],
        ),
        planform=SimpleNamespace(
            semi_span_m=1.5,
            full_span_m=3.0,
            approx_area_m2=1.2,
            approx_aspect_ratio=7.5,
            num_sections=4,
        ),
        aerosandbox_result=None,
        artifact_paths=SimpleNamespace(
            summary_path=summary,
            control_points_path=control_points,
            planform_sections_path=planform_sections,
            section_3d_path=section_3d,
            plot_path=None,
        ),
    )


class DummySampler:
    def __init__(self, samples):
        self._samples = samples

    def sample(self, *, config, n_samples, sampler_seed):
        return list(self._samples)


class DummyGenerator:
    def __init__(self, fail_on_indices: set[int] | None = None):
        self.fail_on_indices = fail_on_indices or set()
        self.calls = 0

    def run_full_case(self, *, sample, config, output_dir):
        self.calls += 1
        if self.calls in self.fail_on_indices:
            raise RuntimeError(f"boom_{self.calls}")
        return _make_result(sample, output_dir)


class DummyLogger:
    def info(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    samples,
    generator: DummyGenerator | None = None,
    dataset_name: str = "ds1",
) -> Path:
    root = tmp_path / dataset_name
    dataset_paths = _make_dataset_paths(root)
    generator = generator or DummyGenerator()

    monkeypatch.setattr(
        "aeris.dataset.dataset_run._resolve_dataset_request",
        lambda **kwargs: {
            "resolved_config_path": tmp_path / "input.yaml",
            "generator_id": "bwb_segmented_v1",
            "effective_config": _make_config(),
            "sampler_id": "lhs_v1",
            "sampler_seed": 42,
            "dataset_name": dataset_name,
        },
    )
    monkeypatch.setattr("aeris.dataset.dataset_run.get_geometry_generator", lambda _: generator)
    monkeypatch.setattr("aeris.dataset.dataset_run.get_dataset_sampler", lambda _: DummySampler(samples))
    monkeypatch.setattr("aeris.dataset.dataset_run.ensure_dataset_paths", lambda _: dataset_paths)
    monkeypatch.setattr("aeris.dataset.dataset_run.setup_logger", lambda *a, **k: DummyLogger())
    monkeypatch.setattr("aeris.dataset.dataset_run.shutil.copy2", lambda *a, **k: None)

    return root


def test_run_dataset_generation_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    samples = [_make_sample(1), _make_sample(2)]
    root = _patch_common(monkeypatch, tmp_path, samples=samples)

    rc = run_dataset_generation(config_path="unused.yaml", n_samples=2)

    assert rc == 0

    manifest = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    metadata = pd.read_csv(root / "metadata.csv")
    failures = pd.read_csv(root / "failures.csv")

    assert manifest["status"] == "success"
    assert manifest["requested_n"] == 2
    assert manifest["attempted_n"] == 2
    assert manifest["succeeded_n"] == 2
    assert manifest["failed_n"] == 0
    assert len(metadata) == 2
    assert len(failures) == 0


def test_run_dataset_generation_marks_partial_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    samples = [_make_sample(1), _make_sample(2), _make_sample(3)]
    generator = DummyGenerator(fail_on_indices={2})
    root = _patch_common(monkeypatch, tmp_path, samples=samples, generator=generator)

    rc = run_dataset_generation(config_path="unused.yaml", n_samples=3)

    assert rc == 0

    manifest = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    metadata = pd.read_csv(root / "metadata.csv")
    failures = pd.read_csv(root / "failures.csv")

    assert manifest["status"] == "partial_success"
    assert manifest["attempted_n"] == 3
    assert manifest["succeeded_n"] == 2
    assert manifest["failed_n"] == 1
    assert len(metadata) == 2
    assert len(failures) == 1
    assert failures.iloc[0]["error_type"] == "RuntimeError"


def test_run_dataset_generation_rejects_wrong_sampler_count_too_few(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    samples = [_make_sample(1)]
    root = _patch_common(monkeypatch, tmp_path, samples=samples)

    rc = run_dataset_generation(config_path="unused.yaml", n_samples=2)

    assert rc == 1

    manifest = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error"]["type"] == "ValueError"
    assert "wrong number of samples" in manifest["error"]["message"]


def test_run_dataset_generation_rejects_wrong_sampler_count_too_many(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    samples = [_make_sample(1), _make_sample(2), _make_sample(3)]
    root = _patch_common(monkeypatch, tmp_path, samples=samples)

    rc = run_dataset_generation(config_path="unused.yaml", n_samples=2)

    assert rc == 1

    manifest = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error"]["type"] == "ValueError"
    assert "wrong number of samples" in manifest["error"]["message"]

@pytest.mark.parametrize("bad_name", ["", ".", "..", "bad/name", "bad\\name"])
def test_resolve_dataset_request_rejects_bad_dataset_names(
    bad_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aeris.dataset.dataset_run import _resolve_dataset_request

    monkeypatch.setattr(
        "aeris.dataset.dataset_run.load_yaml_config",
        lambda path: {"dummy": "cfg"},
    )
    monkeypatch.setattr(
        "aeris.dataset.dataset_run.resolve_generator_and_config",
        lambda raw: ("bwb_segmented_v1", _make_config()),
    )
    monkeypatch.setattr(
        "aeris.dataset.dataset_run.resolve_dataset_sampler",
        lambda raw_config, sampler_override, sampler_seed_override: ("lhs_v1", 42),
    )

    with pytest.raises(ValueError, match="dataset_name"):
        _resolve_dataset_request(
            config_path=tmp_path / "cfg.yaml",
            n_samples=2,
            dataset_name=bad_name,
            save_plot=None,
            build_aerosandbox=None,
            sampler=None,
            sampler_seed=None,
        )