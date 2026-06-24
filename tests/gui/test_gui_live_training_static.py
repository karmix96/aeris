from pathlib import Path

APP = Path("src/aeris/gui/app.py")


def test_gui_exposes_true_live_neural_mlp_training_panel() -> None:
    text = APP.read_text(encoding="utf-8")
    required = [
        "Live neural MLP training — epoch-by-epoch",
        "▶ Live train neural MLP",
        "run_live_neural_mlp_training",
        "epoch_callback=_on_live_epoch",
        "chart_slot.line_chart",
        "val_rmse_mean",
        "training_history.csv",
        "live_streaming_supported",
    ]
    for needle in required:
        assert needle in text
    assert "live_train_neural_mlp" in text
    assert "st.line_chart" in text
    assert "val_r2_mean" in text
