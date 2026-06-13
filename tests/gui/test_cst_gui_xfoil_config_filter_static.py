from pathlib import Path


def test_airfoil_gui_filters_xfoil_configs_away_from_cst_library_configs():
    text = Path('src/aeris/gui/app.py').read_text(encoding='utf-8')
    assert 'AERIS_PATCH_CST_GUI_V1_1_XFOIL_CONFIG_FILTER' in text
    assert 'xfoil_cfg_files' in text
    assert '"xfoil" in Path(f).stem.lower()' in text
    assert 'st.selectbox("XFOIL sweep config"' in text
    assert 'cst_library_v1.yaml generate airfoil shapes' in text


def test_airfoil_gui_resets_stale_xfoil_config_session_state():
    text = Path('src/aeris/gui/app.py').read_text(encoding='utf-8')
    assert 'st.session_state.get("af_cfg") not in cfg_opts' in text
    assert 'st.session_state.pop("af_cfg", None)' in text
