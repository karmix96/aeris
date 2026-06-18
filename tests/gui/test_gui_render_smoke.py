"""GUI render smoke test — every page must render without raising.

Uses Streamlit's native headless testing harness (streamlit.testing.v1.AppTest)
to actually RUN the app and render each of the 11 pages. This catches the class
of bugs that the command-contract test cannot:
  * NameError / AttributeError at render time
  * Duplicate widget-key errors (st.* key collisions)
  * Import errors, bad f-strings, typos in page functions
  * Exceptions in the "no data present" branches

It runs with NO project data, so it exercises every page's empty-state path.
Data-dependent paths (e.g. the aero sweep "Polar curves" view, inspect cards)
are covered separately by test_gui_render_with_fixtures.py, which seeds minimal
artifacts first.

Requires: streamlit installed in the same environment (it is — the GUI needs it).
"""
from __future__ import annotations

import pytest

st_testing = pytest.importorskip(
    "streamlit.testing.v1",
    reason="Streamlit AppTest harness not available in this environment",
)
AppTest = st_testing.AppTest

import aeris.gui.app as gui_app

PAGE_IDS = [pid for pid, _icon, _name in gui_app.PAGES]


def _make_app(tmp_path) -> "AppTest":
    """Build an AppTest pointed at an EMPTY project root so no data paths fire."""
    at = AppTest.from_file(gui_app.__file__, default_timeout=60)
    # Point the GUI at an empty temp dir. _repo_ok() will be False, which is the
    # intended 'no repo' branch — pages must still render their guidance without crashing.
    at.session_state["sb_root"] = str(tmp_path)
    at.session_state["sb_exe"] = "aeris"
    at.session_state["sb_tmo"] = 1800
    at.session_state["sb_dry"] = True  # never execute any command during the test
    return at


@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_page_renders_without_exception(page_id, tmp_path):
    at = _make_app(tmp_path)
    at.session_state["active_page"] = page_id
    at.run()
    assert not at.exception, (
        f"Page '{page_id}' raised on render:\n{at.exception}"
    )


def test_all_pages_in_dispatch(tmp_path):
    """Every page in PAGES must have a dispatch entry (no dead nav buttons)."""
    # Render home, then confirm each PAGES id is routable by running each.
    for page_id in PAGE_IDS:
        at = _make_app(tmp_path)
        at.session_state["active_page"] = page_id
        at.run()
        # A routable page renders at least one markdown/header element.
        assert (at.markdown or at.header or at.subheader or at.title), (
            f"Page '{page_id}' produced no output — likely missing dispatch entry."
        )


def test_repo_connected_root_renders(tmp_path):
    """With a minimal src/aeris/ present (repo_ok True), home still renders."""
    (tmp_path / "src" / "aeris").mkdir(parents=True)
    at = AppTest.from_file(gui_app.__file__, default_timeout=60)
    at.session_state["sb_root"] = str(tmp_path)
    at.session_state["sb_dry"] = True
    at.session_state["active_page"] = "home"
    at.run()
    assert not at.exception, f"Home raised with repo_ok=True:\n{at.exception}"
