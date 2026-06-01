from pathlib import Path
import pandas as pd

from aeris.dataset.training_data import load_training_data


def test_training_data_basic(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    # fake curated dataset
    df = pd.DataFrame({
        "geometry_id": ["g1", "g2"],
        "alpha": [0.0, 2.0],
        "CL": [0.1, 0.2],
        "CD": [0.01, 0.02],
    })

    df.to_csv(dataset / "curated_aero_dataset.csv", index=False)

    # fake promotion manifest
    (dataset / "promotion_manifest.json").write_text("{}")

    # monkeypatch gate
    from aeris.dataset import training_data as td

    def fake_gate(dataset_root, allow_forced=False):
        return {"status": "promoted"}

    td.require_promoted_aero_dataset = fake_gate

    data = load_training_data(
        dataset,
        feature_columns=["alpha"],
        target_columns=["CL"],
    )

    assert len(data.X) == 2
    assert "alpha" in data.X.columns
    assert "CL" in data.y.columns


def test_missing_columns(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    df = pd.DataFrame({"A": [1, 2]})
    df.to_csv(dataset / "curated_aero_dataset.csv", index=False)

    (dataset / "promotion_manifest.json").write_text("{}")

    from aeris.dataset import training_data as td

    td.require_promoted_aero_dataset = lambda *args, **kwargs: {}

    try:
        load_training_data(
            dataset,
            feature_columns=["missing"],
            target_columns=["A"],
        )
    except ValueError:
        assert True
    else:
        assert False