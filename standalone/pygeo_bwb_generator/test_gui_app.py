from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_compatibility_gui_opens_integrated_aeris_geometry_page() -> None:
    app = AppTest.from_file(
        "standalone/pygeo_bwb_generator/gui.py"
    ).run(timeout=60)
    assert not app.exception
    labels = {tab.label.strip() for tab in app.tabs}
    assert {
        "① Generate",
        "② Visualize",
        "③ Design variables",
        "④ Inspect run",
        "⑤ CAD export",
    }.issubset(labels)
