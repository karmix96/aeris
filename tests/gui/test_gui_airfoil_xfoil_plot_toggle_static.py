from pathlib import Path


APP = Path("src/aeris/gui/app.py")


def test_airfoil_gui_exposes_xfoil_plot_toggle() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "Show XFOIL plots (--show-plots)" in text
    assert "af_show_plots" in text
    assert "Xplot11 ON" in text
    assert "headless, no windows" in text


def test_airfoil_gui_appends_show_plots_only_when_checked() -> None:
    text = APP.read_text(encoding="utf-8")

    assert "_sweep_args.append(\"--show-plots\")" in text
    assert '"airfoil", "dataset", "generate"' in text
    assert '"--library", str(lib_dir)' in text
    assert '"--n-airfoils", str(n_airfoils)' in text
