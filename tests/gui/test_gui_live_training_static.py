from pathlib import Path

APP = Path("src/aeris/gui/app.py")


def test_gui_exposes_true_live_neural_mlp_training_panel() -> None:
    text = APP.read_text(encoding="utf-8")
    required = [
        "Live neural MLP training — epoch-by-epoch",
        "live_train_neural_mlp",
        "▶ Live train neural MLP",
        "run_live_neural_mlp_training",
        "epoch_callback=_on_live_epoch",
        "loss_chart_slot.line_chart",
        "rmse_chart_slot.line_chart",
        "r2_chart_slot.line_chart",
        "norm_chart_slot.line_chart",
        "target_rmse_chart_slot.line_chart",
        "gap_chart_slot.line_chart",
        "val_rmse_mean",
        "val_nrmse_scale_mean",
        "training_history.csv",
        "training_history_long.csv",
        "per_target_rmse_curves.png",
        "normalized_error_curves.png",
        "generalization_gap_curves.png",
        "overfit_warning",
        "plateau_warning",
        "live_streaming_supported",
        "tracking_backends=live_tracking_backends",
        "tracking_experiment_name",
        "W&B offline",
        "TensorBoard event logs",
        "MLflow local tracking",
        "_stream_metric_chart",
        "streamlit_add_rows_disabled",
        "live_training_plot_df_name_repair",
        "live_chart_state",
        "x-axis: epoch",
        "y-axis: metric value",
    ]
    for needle in required:
        assert needle in text


def test_gui_live_training_has_path_sanitizer_marker() -> None:
    text = APP.read_text(encoding="utf-8")
    assert "_aeris_clean_gui_path_text" in text
