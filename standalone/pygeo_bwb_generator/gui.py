# ruff: noqa: E402, I001
"""Compatibility launcher for the integrated Aeris geometry GUI.

The pyGeo realization is now part of the production ``bwb_segmented_v1``
generator workflow. This entry point preserves the previous launch command
while using the same Aeris config, CLI, run folders, manifests, and artifacts.

Canonical launch: ``aeris gui run``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aeris.gui.app import main  # noqa: E402


st.session_state.setdefault("active_page", "geometry")
main()
