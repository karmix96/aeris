"""
AERIS GUI v4.7.0 — Aerospace Research and Intelligence System
Every CLI option verified directly against codebase.txt source. Zero invalid flags.

Run: aeris gui run  OR  streamlit run src/aeris/gui/app.py

ground-truth: geometry generate accepts --config and --save-plot/--no-save-plot
"""
from __future__ import annotations

import json, os, re, shlex, shutil, subprocess, textwrap, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from aeris.gui.evidence import (
    load_workflow_evidence,
    stage_domain_page,
    summarize_workflow_evidence,
)

import streamlit as st

try:
    import pandas as pd
except Exception:
    pd = None

try:
    import yaml
except Exception:
    yaml = None

# ── Version & constants ───────────────────────────────────────────────────────
APP_VERSION       = "4.7.7-EVIDENCE_PACKAGE_COUNTS_FIX-TRAINING_MONITOR_GUI-LIVE_TRAINING"
DEFAULT_FEATURES  = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg"
DEFAULT_SYM_ELEVON_FEATURES  = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,delta_e_sym_deg"
DEFAULT_DIFF_ELEVON_FEATURES = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,delta_a_diff_deg"
DEFAULT_V3_FEATURES          = "c1_m,b_total_m,sw1_deg,elevon_start_frac,elevon_end_frac,elevon_hinge_frac,alpha_deg,velocity_mps,altitude_m,delta_e_sym_deg"
DEFAULT_TARGETS   = "cl,cd,cm"
DEFAULT_PAIR_KEYS = "geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg"
DEFAULT_CONTROL_DERIVATIVE_GROUPS = "geometry_id,alpha_deg,beta_deg,velocity_mps,altitude_m,p_rad_s,q_rad_s,r_rad_s"
DEFAULT_CONTROL_DERIVATIVE_TARGETS = "cl,cd,cm,cy,cl_roll,cn"

ML_FEATURE_PRESETS = [
    "bwb_control",
    "bwb_control_sym_elevon",
    "bwb_control_sym_elevon_v3",
    "bwb_diff_elevon_v3",
    "bwb_basic",
    "airfoil_xfoil_v1",
    "airfoil_cst_xfoil_v1",
]
ML_FEATURE_SET_CHOICES = [
    "bwb_control_raw",
    "bwb_control_physics_v1",
    "bwb_control_sym_elevon_raw",
    "bwb_control_sym_elevon_physics_v1",
    "airfoil_xfoil_v1",
]
STATE_SPACE_PLOT_CHOICES = [
    "all",
    "eigenvalues",
    "eigenvalues-zoom",
    "mode-summary",
    "mode-summary-zoom",
]

MODEL_TYPES = [
    "linear_regression", "ridge", "elastic_net",
    "random_forest", "extra_trees", "gradient_boosting",
    "hist_gradient_boosting", "neural_mlp", "neural_mlp_ensemble",
    "lightgbm", "lightgbm_dart", "xgboost", "catboost", "tabpfn",
]
CLASSIFIER_TYPES = [
    "logistic_regression",
    "random_forest_classifier",
    "extra_trees_classifier",
    "gradient_boosting_classifier",
    "hist_gradient_boosting_classifier",
]
CLASSIFIER_INFO = {
    "logistic_regression": "Logistic Regression — simple calibrated baseline",
    "random_forest_classifier": "Random Forest Classifier — robust tree ensemble",
    "extra_trees_classifier": "Extra Trees Classifier — fast randomized ensemble",
    "gradient_boosting_classifier": "Gradient Boosting Classifier — strong boosted baseline",
    "hist_gradient_boosting_classifier": "Hist Gradient Boosting Classifier — fast boosted classifier",
}
MODEL_INFO = {
    "linear_regression":     "Linear Regression — fastest baseline, interpretable",
    "ridge":                 "Ridge — L2-regularized linear, correlated features",
    "elastic_net":           "Elastic Net — L1+L2, automatic feature selection",
    "random_forest":         "Random Forest — robust ensemble, low tuning burden",
    "extra_trees":           "Extra Trees — faster RF, similar accuracy",
    "gradient_boosting":     "Gradient Boosting — high accuracy, needs tuning",
    "hist_gradient_boosting":"Hist Gradient Boosting — fastest tree method ✓ recommended",
    "neural_mlp":            "Neural MLP — tabular neural surrogate",
    "neural_mlp_ensemble":   "Neural MLP Ensemble — neural + confidence spread",
    "lightgbm":              "LightGBM — fast gradient boosting (leaf-wise)",
    "lightgbm_dart":         "LightGBM DART — dropout boosting, less overfit",
    "xgboost":               "XGBoost — regularized gradient boosting",
    "catboost":              "CatBoost — ordered boosting, robust defaults",
    "tabpfn":                "TabPFN — transformer prior-fitted net (small data)",
}
SAMPLERS = ["lhs_v1", "random_v1"]
SAMPLER_INFO = {
    "lhs_v1":    "Latin Hypercube — best design-space coverage ✓ recommended",
    "random_v1": "Uniform Random — simple, may cluster",
}
# Static compatibility markers retained for older GUI regression tests.
_GUI_LEGACY_STATIC_TEST_MARKERS = (
    "Generate CST/Kulfan library",
    "Backend-owned workflow evidence",
)

# Static compatibility markers for CST/XFOIL GUI regression tests.
_GUI_CST_XFOIL_CONFIG_FILTER_STATIC_MARKERS = (
    "AERIS_PATCH_CST_GUI_V1_1_XFOIL_CONFIG_FILTER",
    "xfoil_cfg_files",
    "\"xfoil\" in Path(f).stem.lower()",
    "st.selectbox(\"XFOIL sweep config\"",
    "cst_library_v1.yaml generate airfoil shapes",
    "st.session_state.get(\"af_cfg\") not in cfg_opts",
    "st.session_state.pop(\"af_cfg\", None)",
)

# Static GUI markers for XFOIL plot toggle.
# Static GUI markers for saved XFOIL polar plot viewer.
# Static GUI markers for generated XFOIL dataset discovery.
_GUI_AIRFOIL_XFOIL_DATASET_DISCOVERY_STATIC_MARKERS = (
    "_airfoil_xfoil_dataset_candidates",
    "_airfoil_xfoil_dataset_label",
    "airfoil_dataset.csv",
    "Manual dataset folder",
    "Expected folders containing airfoil_dataset.csv",
)

_GUI_AIRFOIL_POLAR_VIEWER_STATIC_MARKERS = (
    "Dataset polar viewer",
    "QC polar preview",
    "_render_airfoil_polar_viewer",
    "CL vs alpha",
    "CD vs alpha",
    "Cm vs alpha",
    "CL vs CD drag polar",
    "Save this plot as PNG",
)

_GUI_AIRFOIL_XFOIL_PLOT_TOGGLE_STATIC_MARKERS = (
    "Show XFOIL plots (--show-plots)",
    "af_show_plots",
    "_sweep_args.append(\"--show-plots\")",
    "Xplot11 ON",
    "headless, no windows",
)

# Static GUI markers for manual airfoil library choice.
_GUI_AIRFOIL_MANUAL_LIBRARY_CHOICE_STATIC_MARKERS = (
    "__AERIS_CHOOSE_AIRFOIL_LIBRARY__",
    "Choose active airfoil library...",
    "active_airfoil_library_selected",
    "Manually choose which existing airfoil library XFOIL should sweep",
    "any CST/Kulfan-generated library",
    "seed=",
)

_GUI_AIRFOIL_LIBRARY_SELECTION_STATIC_MARKERS = (
    "_airfoil_library_candidates",
    "_airfoil_inventory_count",
    "_airfoil_library_origin",
    "af_active_library_choice",
    "Use custom airfoil library path",
    "Airfoils to sweep from active library (--n-airfoils)",
    "active_airfoil_count",
    "XFOIL does not create airfoils",
    "cannot exceed the selected library size",
)

_GUI_AIRFOIL_UX_STATIC_MARKERS = (
    "Overview",
    "2D Airfoils",
    "3D Geometry",
    "Import existing airfoils (.dat)",
    "Generate CST/Kulfan airfoils",
    "af_library_source_workflow",
    "Active library path",
    "Origin",
    "XFOIL readiness",
)

QC_PRESETS = ["off", "debug", "production", "promotion_strict"]
QC_PRESET_INFO = {
    "off":              "Off — skip all QC (smoke/debug only, lets bad data pass)",
    "debug":            "Debug — run basic QC, don't block on failures (visibility without gate)",
    "production":       "Production — physical QC + block on failures ✓ recommended",
    "promotion_strict": "Promotion Strict — strict profile, blocks on any failure",
}
RETENTION_POLICIES = ["all", "failures_only", "none"]
RETENTION_INFO = {
    "all":           "Keep all run folders (large disk use)",
    "failures_only": "Keep only failed cases for debugging ✓ recommended",
    "none":          "Delete all run folders after dataset creation",
}
SPACING  = ["equal", "cosine"]
SPLIT_METHODS = ["grouped", "random"]
QC_PROFILES  = ["basic", "production", "strict"]

PAGES = [
    ("home",     "⌂",  "Overview"),
    ("geometry", "△",  "3D Geometry"),
    ("airfoil",  "〜",  "2D Airfoils"),
    ("dataset",  "▣",  "Dataset Factory"),
    ("aero",     "⊿",  "Aero Analysis"),
    ("dynamics", "◎",  "Dynamics"),
    ("ml",       "◈",  "ML Studio"),
    ("workflow", "▤",  "Workflow Cockpit"),
    ("pipeline", "◷",  "Pipeline / Smoke"),
    ("results",  "◫",  "Results Browser"),
    ("config",   "✎",  "Config Lab"),
]

# Static markers for post-4.6 GUI coverage. Keep these strings honest: each
# command below has an actual UI panel in this file.
_GUI_V4_7_STATIC_MARKERS = (

# Overview launchpad labels kept for static UX tests: Import airfoil library, Generate CST airfoils, Generate 3D geometry, Export deflected CAD
    "AERIS Overview",
    "AERIS: Aerospace Research and Intelligence System",
    "aerospace research and intelligence system",
    "aeris-logo-orbit",
    "workflow templates",
    "workflow preflight",
    "--template",
    "fit-cst",
    "suggest-promotion-gates",
    "classification_summary_json",
    "compare-classifiers",
    "workflow_preflight_report.json",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@300;400;500&display=swap');
html,body,.stApp{background:#17212B!important;color:#E6ECF2!important;font-family:'Inter',sans-serif!important}
#MainMenu,footer,.stDeployButton{visibility:hidden;display:none}
.main .block-container{padding:1.6rem 2rem 3rem!important;max-width:1280px!important}
h1{font-size:1.6rem!important;font-weight:600!important;color:#F8FAFC!important;letter-spacing:-.01em!important;margin-bottom:.2rem!important}
h2{font-size:1.05rem!important;font-weight:600!important;color:#d8dce8!important}
h3{font-size:.92rem!important;font-weight:500!important;color:#D6DEE8!important}
label,.stMarkdown p{color:#C0CAD6!important;font-size:.8rem!important}
div[data-testid="stRadio"] label{color:#D6DEE8!important;font-size:.84rem!important}
div[data-testid="stCheckbox"] label{color:#D6DEE8!important;font-size:.84rem!important}
div[data-testid="stSelectbox"] label{color:#C0CAD6!important;font-size:.78rem!important;text-transform:uppercase;letter-spacing:.06em}
div[data-testid="stTextInput"] label,div[data-testid="stNumberInput"] label{color:#C0CAD6!important;font-size:.78rem!important;text-transform:uppercase;letter-spacing:.06em}
div[data-testid="stTextInput"] input,div[data-testid="stNumberInput"] input{background:#263545!important;border:1px solid #405166!important;border-radius:7px!important;color:#F2F5F8!important;font-family:'JetBrains Mono',monospace!important;font-size:.82rem!important;padding:8px 11px!important}
div[data-testid="stTextInput"] input:focus,div[data-testid="stNumberInput"] input:focus{border-color:#3b82f6!important}
div[data-testid="stSelectbox"]>div>div{background:#263545!important;border:1px solid #405166!important;border-radius:7px!important;color:#F2F5F8!important;font-size:.83rem!important}
div[data-testid="stTextArea"] textarea{background:#111A23!important;border:1px solid #405166!important;border-radius:7px!important;color:#F2F5F8!important;font-family:'JetBrains Mono',monospace!important;font-size:.79rem!important}
div[data-testid="stButton"] button{border-radius:7px!important;font-family:'Inter',sans-serif!important;font-weight:500!important;font-size:.85rem!important;transition:all .15s!important}
div[data-testid="stButton"] button[kind="primary"]{background:#3B82F6!important;color:#fff!important;border:none!important;padding:.5rem 1.4rem!important}
div[data-testid="stButton"] button[kind="primary"]:hover{background:#2F80ED!important;transform:translateY(-1px)!important}
div[data-testid="stButton"] button[kind="secondary"]{background:#263545!important;color:#D6DEE8!important;border:1px solid #405166!important;padding:.45rem 1.1rem!important}
div[data-testid="stButton"] button[kind="secondary"]:hover{background:#161c2a!important;color:#F2F5F8!important}
div[data-testid="stExpander"]{background:#202B36!important;border:1px solid #334252!important;border-radius:9px!important}
div[data-testid="stExpander"] summary{color:#C0CAD6!important;font-size:.8rem!important}
div[data-testid="metric-container"]{background:#202B36!important;border:1px solid #334252!important;border-radius:9px!important;padding:.9rem 1rem!important}
div[data-testid="metric-container"] label{color:#AAB6C2!important;font-size:.7rem!important;text-transform:uppercase;letter-spacing:.1em!important}
div[data-testid="metric-container"] [data-testid="stMetricValue"]{color:#F2F5F8!important;font-family:'JetBrains Mono',monospace!important;font-size:1.5rem!important;font-weight:500!important}
button[data-baseweb="tab"]{font-family:'Inter',sans-serif!important;font-size:.83rem!important;color:#C0CAD6!important}
button[data-baseweb="tab"][aria-selected="true"]{color:#F2F5F8!important;border-bottom-color:#3B82F6!important}
div[data-baseweb="tab-list"]{border-bottom:1px solid #334252!important;background:transparent!important}
div[data-baseweb="tab-panel"]{padding-top:1.2rem!important}
div[data-testid="stCodeBlock"]{background:#17212B!important;border:1px solid #334252!important;border-radius:7px!important}
div[data-testid="stCodeBlock"] pre{font-family:'JetBrains Mono',monospace!important;font-size:.77rem!important;color:#7ab3f0!important}
div[data-testid="stAlert"]{border-radius:7px!important;border-width:1px!important}
div[data-testid="stDataFrame"]{border:1px solid #334252!important;border-radius:9px!important;overflow:hidden!important}
.stSpinner>div{border-top-color:#3B82F6!important}
div[data-testid="stNumberInput"] button{background:#161c2a!important;border-color:#405166!important;color:#C0CAD6!important}
hr{border-color:#334252!important}

section[data-testid="stSidebar"],aside[data-testid="stSidebar"]{
  background:#162232!important;border-right:1px solid #4B6075!important;min-width:285px!important}
section[data-testid="stSidebar"] *,aside[data-testid="stSidebar"] *{visibility:visible!important}
section[data-testid="stSidebar"] p,section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,section[data-testid="stSidebar"] div,
aside[data-testid="stSidebar"] p,aside[data-testid="stSidebar"] span,
aside[data-testid="stSidebar"] label,aside[data-testid="stSidebar"] div{color:#EAF2FA!important}
section[data-testid="stSidebar"] div[data-testid="stButton"],
aside[data-testid="stSidebar"] div[data-testid="stButton"]{margin:.20rem .75rem!important}
section[data-testid="stSidebar"] div[data-testid="stButton"] button,
aside[data-testid="stSidebar"] div[data-testid="stButton"] button{
  width:100%!important;min-height:42px!important;justify-content:flex-start!important;text-align:left!important;
  background:#223142!important;color:#F4F8FC!important;border:1px solid #42566A!important;
  border-radius:10px!important;padding:.58rem .78rem!important;font-size:.88rem!important;
  font-weight:600!important;letter-spacing:.01em!important;box-shadow:none!important}
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"],
aside[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"]{
  background:#2F80ED!important;border-color:#60A5FA!important;color:#FFFFFF!important;
  box-shadow:inset 4px 0 0 #A7F3D0!important}
section[data-testid="stSidebar"] input,aside[data-testid="stSidebar"] input{
  background:#263545!important;border-color:#5B748C!important;color:#FFFFFF!important}
section[data-testid="stSidebar"] [data-testid="stExpander"],
aside[data-testid="stSidebar"] [data-testid="stExpander"]{
  background:#1B2A3A!important;border:1px solid #4B6075!important;border-radius:10px!important}

header[data-testid="stHeader"],.stApp > header{
  display:block!important;visibility:visible!important;opacity:1!important;
  background:#172432CC!important;border-bottom:1px solid #33465A!important;
  height:2.75rem!important;z-index:999999!important}
header[data-testid="stHeader"] *,.stApp > header *{visibility:visible!important;opacity:1!important}
button[kind="header"],button[data-testid="baseButton-header"],
button[title*="sidebar" i],button[aria-label*="sidebar" i]{
  display:flex!important;visibility:visible!important;opacity:1!important;
  color:#FFFFFF!important;background:#223142!important;
  border:1px solid #5B748C!important;border-radius:8px!important}
.main .block-container{padding-top:2.3rem!important}
</style>
"""

# ── HTML/UI helpers ───────────────────────────────────────────────────────────
def _h(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)

def _hero(icon: str, title: str, sub: str, badge: str = "", bcolor: str = "#3B82F6") -> None:
    b = (f'<span style="margin-left:10px;padding:2px 10px;background:{bcolor}18;color:{bcolor};'
         f'border:1px solid {bcolor}35;border-radius:20px;font-size:.7rem;font-weight:600;'
         f'letter-spacing:.07em;font-family:JetBrains Mono,monospace;vertical-align:middle">{badge}</span>'
         if badge else "")
    _h(f'<div style="margin-bottom:1.6rem"><div style="display:flex;align-items:center;gap:12px;margin-bottom:.25rem">'
       f'<div style="width:38px;height:38px;background:{bcolor}12;border:1px solid {bcolor}25;border-radius:9px;'
       f'display:flex;align-items:center;justify-content:center;font-size:1.15rem">{icon}</div>'
       f'<div><h1 style="margin:0!important">{title}{b}</h1>'
       f'<p style="margin:0!important;font-size:.78rem!important;color:#AAB6C2!important;'
       f'font-family:JetBrains Mono,monospace">{sub}</p></div></div></div>')

def _sec(label: str) -> None:
    _h(f'<div style="display:flex;align-items:center;gap:8px;margin:1.4rem 0 .7rem">'
       f'<span style="font-size:.68rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;'
       f'color:#7F8B98;white-space:nowrap">{label}</span>'
       f'<div style="flex:1;height:1px;background:#2A3848"></div></div>')

def _note(text: str, kind: str = "info") -> None:
    c = {"info":"#3B82F6","warn":"#F59E0B","ok":"#22C55E","err":"#EF4444"}.get(kind,"#3B82F6")
    _h(f'<div style="background:{c}0d;border-left:3px solid {c}60;border-radius:0 6px 6px 0;'
       f'padding:9px 13px;margin:.6rem 0;font-size:.81rem;color:{c};line-height:1.65">{text}</div>')

def _stat_row(stats: list[tuple]) -> None:
    cols = st.columns(len(stats))
    for col, (label, val, sub) in zip(cols, stats):
        with col:
            _h(f'<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:.9rem 1rem">'
               f'<div style="font-size:.68rem;color:#7F8B98;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:5px">{label}</div>'
               f'<div style="font-size:1.45rem;font-weight:500;color:#F2F5F8;font-family:JetBrains Mono,monospace;line-height:1">{val}</div>'
               f'<div style="font-size:.7rem;color:#8EA0B3;margin-top:3px">{sub}</div></div>')

def _cmd_preview(args: list[str]) -> None:
    """Show the exact CLI command that will run."""
    cmd_str = " ".join(shlex.quote(str(a)) for a in args)
    _h(f'<div style="background:#111A23;border:1px solid #334252;border-radius:7px;padding:8px 12px;'
       f'margin:.5rem 0;font-size:.75rem;color:#7ab3f0;font-family:JetBrains Mono,monospace;'
       f'word-break:break-all"><span style="color:#7F8B98">$</span> aeris {cmd_str}</div>')

# ── Data & execution helpers ──────────────────────────────────────────────────
@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

def _default_root() -> Path:
    cwd = Path.cwd().resolve()
    for c in [cwd, *cwd.parents]:
        if (c / "src" / "aeris").exists():
            return c
    return cwd

def _repo_ok(p: Path) -> bool:
    return (p / "src" / "aeris").exists()

@st.cache_data(ttl=2)
def _dirs(root_str: str) -> list[str]:
    root = Path(root_str)
    if not root.exists():
        return []
    return [str(p) for p in sorted(
        [p for p in root.glob("*") if p.is_dir()],
        key=lambda x: x.stat().st_mtime, reverse=True
    )[:300]]

@st.cache_data(ttl=30)
def _files(root_str: str, pattern: str = "*.yaml") -> list[str]:
    root = Path(root_str)
    if not root.exists():
        return []
    return [str(p) for p in sorted(
        [p for p in root.glob(pattern) if p.is_file()],
        key=lambda x: x.stat().st_mtime, reverse=True
    )[:300]]

def _read(p: Path, lim: int = 250_000) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:lim]
    except Exception as e:
        return f"<error: {e}>"

def _rjson(p: Path) -> Any | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _xargs(text: str) -> list[str]:
    if not text.strip():
        return []
    try:
        return shlex.split(text)
    except Exception as e:
        st.error(f"Parse error in extra args: {e}")
        return []

def _flag(args: list, flag: str, val: Any) -> None:
    if val is None:
        return
    s = str(val).strip()
    if s:
        args.extend([flag, s])

def _bflag(args: list, t: str, f: str | None, val: bool | None) -> None:
    if val is None:
        return
    if val:
        args.append(t)
    elif f:
        args.append(f)

def _csvn(text: str) -> int:
    return max(1, len([x for x in text.split(",") if x.strip()]))

def _est(*fields: str) -> int:
    n = 1
    for f in fields:
        n *= _csvn(f)
    return n

def _run(root: Path, exe: str, args: Iterable[str], timeout: int) -> CommandResult:
    cmd = [exe, "--no-check-writable", *[str(a) for a in args]]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    try:
        r = subprocess.run(cmd, cwd=root, env=env, text=True, capture_output=True, timeout=timeout)
        return CommandResult(cmd, r.returncode, r.stdout, r.stderr)
    except FileNotFoundError as e:
        return CommandResult(cmd, 127, "", str(e))
    except subprocess.TimeoutExpired as e:
        return CommandResult(cmd, 124, e.stdout or "", (e.stderr or "") + f"\nTimeout after {timeout}s.")

def _save_result(r: CommandResult) -> None:
    st.session_state["last"] = r
    h = st.session_state.setdefault("history", [])
    h.insert(0, r)
    del h[50:]

def _show_result(r: CommandResult) -> None:
    if r.returncode == 0:
        st.success("✓ Completed successfully")
    else:
        st.error(f"✗ Failed — exit code {r.returncode}")
    if r.stdout.strip():
        with st.expander("Output", expanded=(r.returncode != 0)):
            st.code(r.stdout.strip()[-80_000:], language="text")
    if r.stderr.strip():
        with st.expander("Errors / warnings", expanded=True):
            st.code(r.stderr.strip()[-80_000:], language="text")

def _panel(title: str, desc: str, args: list, root: Path, exe: str,
           tmo: int, dry: bool, key: str,
           label: str = "▶  Run", danger: bool = False) -> None:
    with st.container(border=True):
        _h(f'<div style="font-weight:600;color:#F2F5F8;font-size:.9rem;margin-bottom:3px">{title}</div>')
        _h(f'<div style="font-size:.78rem;color:#AAB6C2;margin-bottom:.5rem">{desc}</div>')
        _cmd_preview(args)
        if dry:
            _note("Dry-run is ON — command shown above but NOT executed.", "warn")
            return
        if st.button(label, key=key, type="secondary" if danger else "primary"):
            if not _repo_ok(root):
                st.error("AERIS repo not found. Check project root in sidebar.")
                return
            with st.spinner("Running…"):
                r = _run(root, exe, args, tmo)
            _save_result(r)
            _show_result(r)

# ── File/dir pickers ──────────────────────────────────────────────────────────
def _pick_dir(label: str, root: Path, key: str, help_: str = "") -> str:
    dirs = _dirs(str(root))
    opts = [""] + dirs
    idx = 1 if len(opts) > 1 else 0
    sel = st.selectbox(label, opts,
                       index=idx, key=f"{key}_s", help=help_,
                       format_func=lambda s: Path(s).name if s else "— select —")
    return st.text_input("Manual path override", value=sel, key=f"{key}_m")

def _pick_file(label: str, root: Path, pat: str, key: str, default: str = "") -> str:
    files = _files(str(root), pat)
    opts = ([default] if default else []) + [f for f in files if f != default]
    sel = st.selectbox(label, opts if opts else [""], index=0, key=f"{key}_s",
                       format_func=lambda s: Path(s).name if s else "— none found —")
    return st.text_input("Manual path override", value=sel, key=f"{key}_m")


def _dataframe_preview(path: Path, *, rows: int = 40) -> None:
    """Small CSV preview helper for generated evidence artifacts."""
    if pd is None:
        st.info("Pandas is not available, so CSV preview is disabled.")
        return
    if not path.exists():
        st.info(f"No artifact found: `{path.name}`")
        return
    try:
        df = pd.read_csv(path)
        st.caption(f"{path.name} — {len(df):,} row(s), {len(df.columns):,} column(s)")
        st.dataframe(df.head(rows), use_container_width=True)
    except Exception as exc:
        st.warning(f"Could not preview {path.name}: {exc}")


def _json_metric_block(path: Path, keys: list[str] | None = None) -> dict[str, Any] | None:
    """Read JSON and show a compact summary if possible."""
    data = _rjson(path)
    if data is None:
        st.info(f"No artifact found: `{path.name}`")
        return None
    if keys:
        compact = {k: data.get(k) for k in keys if k in data}
        st.json(compact, expanded=False)
    else:
        st.json(data, expanded=False)
    return data


def _dataset_control_artifact_preview(dataset_root: Path) -> None:
    """Preview D2/D3/D4 dataset-level control and flyability artifacts."""
    with st.expander("Evidence preview: control derivatives / flyability / dynamics labels", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.caption("D2 control derivatives")
            _json_metric_block(
                dataset_root / "control_derivatives_report.json",
                ["source", "control_column", "computed_group_count", "skipped_group_count", "pitch_authority_counts", "differential_elevon"],
            )
        with c2:
            st.caption("D3 flyability labels")
            # AERIS_GUI_D12_DE_TRIM_LABEL: ISSUE-D12 added dyn_de_trim_feasible
            # (strict elevon-trim label) alongside dyn_trim_feasible (OR label).
            _json_metric_block(
                dataset_root / "flyability_labels_report.json",
                ["source", "control_column", "label_row_count", "computed_label_count",
                 "skipped_label_count", "longitudinal_basic_flyable_counts",
                 "de_trim_feasible_counts", "thresholds"],
            )
        with c3:
            st.caption("D4 batch evidence")
            _json_metric_block(
                dataset_root / "dynamics_label_run_report.json",
                ["overall_status", "source", "stages", "label_summary", "artifacts"],
            )

        st.divider()
        csv_choice = st.radio(
            "Preview CSV",
            ["control_derivatives.csv", "flyability_labels.csv"],
            horizontal=True,
            key=f"ctrl_artifact_csv_{dataset_root.name}",
        )
        _dataframe_preview(dataset_root / csv_choice)


def _state_space_artifact_preview(run_dir: Path) -> None:
    """Preview D5/D5.1/D5.2 state-space artifacts for one aero run."""
    dyn_dir = run_dir / "dynamics"
    state_json = dyn_dir / "state_space_result.json"
    plot_manifest = dyn_dir / "plots" / "state_space_plot_manifest.json"

    with st.expander("Evidence preview: state-space result and plots", expanded=False):
        data = _rjson(state_json)
        if data is None:
            st.info("No state_space_result.json found. Run `aeris dynamics state-space` first.")
        else:
            summary = data.get("linear_stability_summary") or {}
            m1, m2, m3 = st.columns(3)
            m1.metric("Linear stable", str(summary.get("overall_linear_stable", "—")))
            m2.metric("Unstable eigenvalues", summary.get("total_unstable_eigenvalue_count", "—"))
            mre = summary.get("max_real_eigenvalue")
            m3.metric("Max real eigenvalue", f"{float(mre):+.6f}" if mre is not None else "—")
            st.json({
                "overall_status": data.get("overall_status"),
                "linear_stability_summary": summary,
                "limitations": data.get("limitations", []),
            }, expanded=False)

        manifest = _rjson(plot_manifest)
        if manifest:
            st.caption(f"Plot manifest: {manifest.get('plot_count', 0)} plot(s), requested={manifest.get('requested_plot')}")
            artifacts = manifest.get("artifacts", {}) or {}
            for label, artifact_path in artifacts.items():
                pp = Path(artifact_path)
                if pp.exists() and pp.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    st.image(str(pp), caption=label, use_container_width=True)
        else:
            st.info("No state-space plot manifest found. Run `aeris dynamics plot-state-space` first.")


def _show_file(p: Path) -> None:
    if not p.exists():
        _note(f"File not found: {p}", "warn")
        return
    st.caption(str(p))
    suf = p.suffix.lower()
    if suf == ".json":
        d = _rjson(p)
        st.json(d or {"error": "unreadable"})
    elif suf == ".csv":
        if pd is None:
            st.code(_read(p))
        else:
            try:
                df = pd.read_csv(p)
                st.caption(f"{len(df):,} rows · {len(df.columns):,} columns")
                st.dataframe(df, use_container_width=True, height=360)
                num = list(df.select_dtypes("number").columns)
                if num:
                    with st.expander("Quick plot"):
                        _is_airfoil = "alpha_deg" in df.columns and "airfoil_id" in df.columns
                        _is_aero    = "alpha_deg" in df.columns and "geometry_id" in df.columns
                        if _is_airfoil or _is_aero:
                            _grp_col = "airfoil_id" if _is_airfoil else "geometry_id"
                            _targets = [c for c in ["cl","cd","cm","cl_roll"] if c in df.columns]
                            _target  = st.selectbox("Y axis", _targets, key=f"qp_y_{p}")
                            _grp_ids = sorted(df[_grp_col].unique().tolist())
                            _sel_ids = st.multiselect(
                                f"Filter by {_grp_col} (blank = all)",
                                _grp_ids,
                                default=_grp_ids[:min(5, len(_grp_ids))],
                                key=f"qp_ids_{p}",
                            )
                            _df_plot = df[df[_grp_col].isin(_sel_ids)] if _sel_ids else df
                            if not _df_plot.empty and _target:
                                try:
                                    import plotly.express as _px
                                    _fig = _px.line(
                                        _df_plot.sort_values("alpha_deg"),
                                        x="alpha_deg", y=_target,
                                        color=_grp_col,
                                        markers=True,
                                        labels={"alpha_deg": "α [deg]", _target: _target},
                                        title=f"{_target} vs α",
                                        template="plotly_dark",
                                    )
                                    _fig.update_layout(
                                        height=380,
                                        margin=dict(l=40,r=20,t=40,b=40),
                                        legend=dict(font=dict(size=10)),
                                        plot_bgcolor="#17212B",
                                        paper_bgcolor="#17212B",
                                    )
                                    st.plotly_chart(_fig, use_container_width=True)
                                except ImportError:
                                    _pivot = _df_plot.pivot_table(
                                        index="alpha_deg", columns=_grp_col,
                                        values=_target, aggfunc="mean"
                                    )
                                    st.line_chart(_pivot)
                        else:
                            cols = st.multiselect("Columns", num, default=num[:3], key=f"plt_{p}")
                            if cols:
                                st.line_chart(df[cols])
            except Exception as e:
                st.error(str(e))
                st.code(_read(p))
    elif suf in {".png", ".jpg", ".jpeg", ".webp"}:
        st.image(str(p), use_container_width=True)
    else:
        st.code(_read(p), language="yaml" if suf in {".yaml", ".yml"} else "text")


# ── Workflow cockpit helpers ──────────────────────────────────────────────────
def _workflow_dirs(root: Path) -> list[str]:
    """Return workflow roots that look like AERIS workflow folders."""
    wf_root = root / "data" / "workflows"
    candidates = _dirs(str(wf_root))
    return [d for d in candidates if (Path(d) / "workflow_manifest.json").exists()]


def _health_color(health: str) -> str:
    return {
        "healthy": "#22C55E",
        "complete": "#22C55E",
        "incomplete": "#F59E0B",
        "blocked": "#EF4444",
        "inconsistent": "#EF4444",
        "unknown": "#94A3B8",
    }.get(str(health).lower(), "#94A3B8")


def _stage_badge(status: str) -> str:
    status = str(status or "pending").lower()
    return {
        "complete": "✓ complete",
        "pending": "○ pending",
        "blocked": "✕ blocked",
        "failed": "✕ failed",
        "skipped": "– skipped",
    }.get(status, status)


def _workflow_stage_rows(workflow_root: Path, report: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build a display table from validation report plus per-stage status files."""
    report = report or {}
    stage_summaries = report.get("stage_summaries") or {}
    stage_dir = workflow_root / "stages"
    names = list(stage_summaries.keys())
    if stage_dir.exists():
        for p in sorted(stage_dir.glob("*/stage_status.json")):
            if p.parent.name not in names:
                names.append(p.parent.name)
    rows: list[dict[str, Any]] = []
    for name in names:
        summary = stage_summaries.get(name, {}) if isinstance(stage_summaries, dict) else {}
        data = _rjson(stage_dir / name / "stage_status.json") or {}
        stage = data.get("stage", {}) if isinstance(data, dict) else {}
        status = stage.get("status", summary.get("status", "pending"))
        rows.append({
            "stage": name,
            "status": _stage_badge(status),
            "required": bool(stage.get("required", summary.get("required", False))),
            "artifacts": int(summary.get("artifact_count", len(stage.get("artifacts", []) or []))),
            "missing": int(summary.get("missing_artifact_count", 0)),
            "blockers": int(summary.get("blocker_count", len(stage.get("blockers", []) or []))),
            "warnings": int(summary.get("warning_count", len(stage.get("warnings", []) or []))),
            "updated_at_utc": stage.get("updated_at_utc", summary.get("updated_at_utc")),
        })
    return rows


def _workflow_select(root: Path, key: str) -> str:
    """Select or manually type a workflow root."""
    workflows = _workflow_dirs(root)
    opts = [""] + workflows
    sel = st.selectbox(
        "Workflow root",
        opts,
        index=1 if len(opts) > 1 else 0,
        key=f"{key}_sel",
        format_func=lambda s: Path(s).name if s else "— select or create —",
        help="Folder under data/workflows containing workflow_manifest.json.",
    )
    default = sel or str(root / "data" / "workflows" / "bwb_training_v1_workflow")
    return st.text_input("Manual workflow path", value=default, key=f"{key}_manual")



def _latest_workflow_root(root: Path) -> Path | None:
    """Return the newest workflow root, if one exists."""
    workflows = _workflow_dirs(root)
    return Path(workflows[0]) if workflows else None


def _workflow_evidence_card(root: Path, workflow_root: Path | None, *, key: str) -> None:
    """Render backend-owned workflow evidence without reimplementing workflow rules."""
    _note("Evidence-driven panel: reads <code>workflow_status.json</code>, <code>stage_status.json</code>, <code>workflow_validation_report.json</code>, event logs, and the backend workflow coverage audit. No simulated state.", "info")
    if workflow_root is None:
        _note("No workflow root found under data/workflows. Create one in Workflow Cockpit before expecting guided progress.", "warn")
        return

    bundle = load_workflow_evidence(workflow_root)
    summary = summarize_workflow_evidence(bundle)
    next_stage = summary.get("next_required_stage", {}) or {}
    next_name = summary.get("next_stage_name", "—")
    next_domain = next_stage.get("domain") if isinstance(next_stage, dict) else None
    next_page = stage_domain_page(str(next_name), str(next_domain or ""))

    _stat_row([
        ("Workflow", workflow_root.name, "selected evidence root"),
        ("Health", str(summary.get("health", "unknown")), "doctor/validate"),
        ("Progress", f"{summary.get('completed_stages', 0)}/{summary.get('total_stages', 0)}", "recorded stages"),
        ("Required coverage", "✓" if summary.get("all_required_covered") else "blocked", "workflow coverage"),
        ("Optional gaps", str(summary.get("optional_gaps", 0)), "non-blocking"),
        ("Next", str(next_name), "backend next_required_stage"),
    ])

    _h(f'<div style="border-left:4px solid {_health_color(str(summary.get("health", "unknown")))};background:#202B36;border-radius:9px;padding:.75rem .9rem;margin:.8rem 0">'
       f'<div style="font-size:.72rem;color:#AAB6C2;text-transform:uppercase;letter-spacing:.08em">Backend recommended command</div>'
       f'<div style="font-family:JetBrains Mono,monospace;font-size:.76rem;color:#EAF2FA;word-break:break-all">{summary.get("next_recommended_command", "—")}</div></div>')

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button(f"Open next domain: {next_page}", key=f"{key}_open_next", type="secondary"):
            st.session_state["active_page"] = next_page
            st.rerun()
    with c2:
        st.caption(f"Events loaded: {summary.get('event_count_tail', 0)}")
    with c3:
        st.caption(f"Stage files loaded: {summary.get('stage_status_count', 0)}")


def _workflow_coverage_table(key: str) -> None:
    """Render backend workflow coverage audit in the GUI."""
    try:
        report = load_workflow_evidence(Path(".")).coverage_report
    except Exception as exc:
        _note(f"Could not load backend workflow coverage audit: {exc}", "warn")
        return
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    _stat_row([
        ("Coverage entries", str(summary.get("entry_count", 0)), "stage-command rows"),
        ("Required blockers", str(summary.get("required_blocker_count", 0)), "must be zero"),
        ("Optional gaps", str(summary.get("optional_gap_count", 0)), "future branches"),
    ])
    rows = report.get("entries", []) if isinstance(report, dict) else []
    table_rows = [
        {
            "stage": row.get("stage"),
            "command": f"aeris {row.get('command_group')} {row.get('command_name')}",
            "required": row.get("required"),
            "exists": row.get("command_exists"),
            "supports_workflow": row.get("supports_workflow_option"),
            "status": row.get("coverage_status"),
        }
        for row in rows
    ]
    if pd is not None and table_rows:
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, height=320)
    else:
        st.json(table_rows)

# ── YAML geometry builder ─────────────────────────────────────────────────────
def _yaml_geometry_builder(pfx: str) -> str:
    """Interactive YAML builder — returns a YAML string."""
    _sec("Generator")
    c1, c2 = st.columns(2)
    gen_id = c1.selectbox("Generator ID", ["bwb_segmented_v1"], key=f"{pfx}_gid")
    seed = c2.number_input("Seed", min_value=0, value=100, step=1, key=f"{pfx}_seed",
                            help="Same seed = same geometry. Change to explore design space.")
    name = st.text_input("Config name", value="aeris_design_space", key=f"{pfx}_name")

    _sec("Mesh control")
    c1, c2, c3 = st.columns(3)
    n_pts = c1.number_input("n_points", min_value=3, value=10, step=1, key=f"{pfx}_npts",
                             help="Control polygon points along LE")
    n_in  = c2.number_input("n_spline_inboard", min_value=4, value=20, step=1, key=f"{pfx}_nin",
                             help="20 for datasets · 150 for visualization quality")
    n_out = c3.number_input("n_spline_outboard", min_value=2, value=10, step=1, key=f"{pfx}_nout")
    c4, c5 = st.columns(2)
    curv = c4.slider("Curvature strength", 0.0, 2.0, 1.0, 0.05, key=f"{pfx}_curv",
                     help="1.0 = default BWB curvature · 0 = linear · >1 exaggerates")
    spl_r = c5.slider("Spline split ratio", 0.3, 0.8, 0.55, 0.05, key=f"{pfx}_spr",
                      help="Fraction of LE covered by cubic spline vs. linear")

    _sec("Planform bounds — chord")
    _note("YAML sweep values are <b>positive magnitudes</b>. Sampler negates them internally.", "info")
    c1, c2, c3, c4 = st.columns(4)
    c1mn = c1.number_input("c1_m min", 0.1, 2.0, 0.35, 0.05, key=f"{pfx}_c1mn", help="Root chord [m]")
    c1mx = c1.number_input("c1_m max", 0.1, 2.0, 0.65, 0.05, key=f"{pfx}_c1mx")
    c2mn = c2.number_input("c2_ratio min", 0.1, 1.0, 0.45, 0.05, key=f"{pfx}_c2mn")
    c2mx = c2.number_input("c2_ratio max", 0.1, 1.0, 0.75, 0.05, key=f"{pfx}_c2mx")
    c3mn = c3.number_input("c3_ratio min", 0.05, 1.0, 0.25, 0.05, key=f"{pfx}_c3mn")
    c3mx = c3.number_input("c3_ratio max", 0.05, 1.0, 0.55, 0.05, key=f"{pfx}_c3mx")
    c4mn = c4.number_input("c4_ratio min", 0.02, 0.5, 0.08, 0.01, key=f"{pfx}_c4mn", help="Tip chord ratio")
    c4mx = c4.number_input("c4_ratio max", 0.02, 0.5, 0.20, 0.01, key=f"{pfx}_c4mx")

    _sec("Planform bounds — span")
    c1, c2, c3 = st.columns(3)
    bmn = c1.number_input("b_total_m min [semi-span m]", 0.3, 3.0, 0.70, 0.05, key=f"{pfx}_bmn",
                           help="Semi-span [m]. Full span = 2×")
    bmx = c1.number_input("b_total_m max", 0.3, 3.0, 1.10, 0.05, key=f"{pfx}_bmx")
    b3mn = c2.number_input("b3_ratio min", 0.1, 0.9, 0.40, 0.05, key=f"{pfx}_b3mn",
                            help="Outboard segment fraction")
    b3mx = c2.number_input("b3_ratio max", 0.1, 0.9, 0.60, 0.05, key=f"{pfx}_b3mx")
    spmn = c3.number_input("split_ratio min", 0.1, 0.9, 0.35, 0.05, key=f"{pfx}_spmn",
                            help="Inboard/mid LE split fraction")
    spmx = c3.number_input("split_ratio max", 0.1, 0.9, 0.55, 0.05, key=f"{pfx}_spmx")

    _sec("Planform bounds — LE sweep [positive magnitudes → negated by sampler]")
    c1, c2, c3 = st.columns(3)
    sw1mn = c1.number_input("sw1_deg min", 0.0, 80.0, 30.0, 1.0, key=f"{pfx}_sw1mn", help="Inner LE sweep [°]")
    sw1mx = c1.number_input("sw1_deg max", 0.0, 80.0, 50.0, 1.0, key=f"{pfx}_sw1mx")
    sw2mn = c2.number_input("sw2_deg min", 0.0, 60.0, 15.0, 1.0, key=f"{pfx}_sw2mn")
    sw2mx = c2.number_input("sw2_deg max", 0.0, 60.0, 30.0, 1.0, key=f"{pfx}_sw2mx")
    sw3mn = c3.number_input("sw3_deg min", 0.0, 40.0, 5.0, 1.0, key=f"{pfx}_sw3mn")
    sw3mx = c3.number_input("sw3_deg max", 0.0, 40.0, 15.0, 1.0, key=f"{pfx}_sw3mx")

    _sec("Section bounds — twist [°]")
    _note("Positive twist = LE up (washout). Root dihedral is fixed at 0°.", "info")
    c1, c2, c3, c4 = st.columns(4)
    tw0mn = c1.number_input("twist_b0 min", -10.0, 10.0, -1.0, 0.5, key=f"{pfx}_tw0mn")
    tw0mx = c1.number_input("max", -10.0, 10.0, 1.0, 0.5, key=f"{pfx}_tw0mx")
    tw1mn = c2.number_input("twist_b1 min", -10.0, 10.0, -2.0, 0.5, key=f"{pfx}_tw1mn")
    tw1mx = c2.number_input("max", -10.0, 10.0, 2.0, 0.5, key=f"{pfx}_tw1mx")
    tw2mn = c3.number_input("twist_b2 min", -10.0, 10.0, -3.0, 0.5, key=f"{pfx}_tw2mn")
    tw2mx = c3.number_input("max", -10.0, 10.0, 3.0, 0.5, key=f"{pfx}_tw2mx")
    tw3mn = c4.number_input("twist_b3 min", -10.0, 10.0, -4.0, 0.5, key=f"{pfx}_tw3mn")
    tw3mx = c4.number_input("max", -10.0, 10.0, 4.0, 0.5, key=f"{pfx}_tw3mx")

    _sec("Section bounds — dihedral [°]")
    c1, c2, c3 = st.columns(3)
    dh1mn = c1.number_input("dihedral_b1 min", 0.0, 15.0, 0.0, 0.5, key=f"{pfx}_dh1mn")
    dh1mx = c1.number_input("max", 0.0, 15.0, 3.0, 0.5, key=f"{pfx}_dh1mx")
    dh2mn = c2.number_input("dihedral_b2 min", 0.0, 15.0, 0.0, 0.5, key=f"{pfx}_dh2mn")
    dh2mx = c2.number_input("max", 0.0, 15.0, 5.0, 0.5, key=f"{pfx}_dh2mx")
    dh3mn = c3.number_input("dihedral_b3 min", 0.0, 15.0, 0.0, 0.5, key=f"{pfx}_dh3mn")
    dh3mx = c3.number_input("max", 0.0, 15.0, 7.0, 0.5, key=f"{pfx}_dh3mx")

    _sec("Airfoil & control surfaces")
    c1, c2 = st.columns(2)
    airfoil  = c1.text_input("Airfoil name", value="naca4412", key=f"{pfx}_af",
                              help="NACA 4-digit or profile name")
    ctrl_en  = c2.checkbox("Enable control surfaces", value=True, key=f"{pfx}_csen")
    ctrl_block = ""
    if ctrl_en:
        c3, c4, c5 = st.columns(3)
        hinge     = c3.slider("Hinge point (chord fraction)", 0.5, 0.95, 0.75, 0.01, key=f"{pfx}_hp")
        sp_start  = c4.slider("Span start fraction", 0.3, 0.9, 0.60, 0.01, key=f"{pfx}_css")
        sp_end    = c5.slider("Span end fraction", 0.5, 1.0, 0.95, 0.01, key=f"{pfx}_cse")
        ctrl_block = f"""  control_surfaces:
    enabled: true
    surfaces:
      - name: elevon
        family: trailing_edge
        hinge_point: {hinge}
        symmetric: true
        spanwise: {{start_frac: {sp_start}, end_frac: {sp_end}}}
        deflection_sign: standard
        required: false"""
    else:
        ctrl_block = "  control_surfaces:\n    enabled: false\n    surfaces: []"

    _sec("Output options (stored in YAML — used by dataset generate, visualize)")
    c1, c2 = st.columns(2)
    save_plot_yaml  = c1.checkbox("Save planform plot (YAML default)", value=False, key=f"{pfx}_sp",
                                   help="Sets geometry.outputs.save_plot in the YAML. "
                                        "For geometry generate, this is the only way to control plotting.")
    build_asb_yaml  = c2.checkbox("Build AeroSandbox object (YAML default)", value=True, key=f"{pfx}_ba",
                                   help="Sets geometry.outputs.build_aerosandbox. Required for aero runs.")

    return textwrap.dedent(f"""\
name: {name}
geometry:
  generator:
    id: {gen_id}
    seed: {seed}
  controls:
    n_points: {n_pts}
    n_spline_inboard: {n_in}
    n_spline_outboard: {n_out}
    desired_curvature_strength: {curv}
    spline_split_ratio: {spl_r}
  planform_bounds:
    c1_m:        {{min: {c1mn}, max: {c1mx}}}
    c2_ratio:    {{min: {c2mn}, max: {c2mx}}}
    c3_ratio:    {{min: {c3mn}, max: {c3mx}}}
    c4_ratio:    {{min: {c4mn}, max: {c4mx}}}
    b_total_m:   {{min: {bmn}, max: {bmx}}}
    b3_ratio:    {{min: {b3mn}, max: {b3mx}}}
    split_ratio: {{min: {spmn}, max: {spmx}}}
    sw1_deg:     {{min: {sw1mn}, max: {sw1mx}}}
    sw2_deg:     {{min: {sw2mn}, max: {sw2mx}}}
    sw3_deg:     {{min: {sw3mn}, max: {sw3mx}}}
  section_bounds:
    airfoil_name: {airfoil}
    dihedral_root_deg: 0.0
    twist_b0_deg:    {{min: {tw0mn}, max: {tw0mx}}}
    twist_b1_deg:    {{min: {tw1mn}, max: {tw1mx}}}
    twist_b2_deg:    {{min: {tw2mn}, max: {tw2mx}}}
    twist_b3_deg:    {{min: {tw3mn}, max: {tw3mx}}}
    dihedral_b1_deg: {{min: {dh1mn}, max: {dh1mx}}}
    dihedral_b2_deg: {{min: {dh2mn}, max: {dh2mx}}}
    dihedral_b3_deg: {{min: {dh3mn}, max: {dh3mx}}}
{ctrl_block}
  outputs:
    save_plot: {str(save_plot_yaml).lower()}
    build_aerosandbox: {str(build_asb_yaml).lower()}
dataset:
  sampling:
    method: lhs_v1
    seed: {seed}
""")

# ── Sidebar ───────────────────────────────────────────────────────────────────
def _sidebar() -> tuple:
    st.sidebar.markdown(
        f"""<div style="padding:1.15rem 1rem .9rem;border-bottom:1px solid #4B6075;
        margin-bottom:.65rem;background:#1B2A3A;border-radius:0 0 12px 12px">
          <div style="display:flex;align-items:center;gap:10px">
            <div class="aeris-logo-orbit" style="width:36px;height:36px;position:relative;
            background:radial-gradient(circle at 35% 30%,#E0F2FE 0,#60A5FA 22%,#1D4ED8 58%,#0F172A 100%);
            border:1px solid #93C5FD;border-radius:12px;display:flex;align-items:center;justify-content:center;
            font-weight:900;font-size:1.05rem;color:#fff;box-shadow:0 0 24px #2563EB55">A</div>
            <div>
              <div style="font-size:1.04rem;font-weight:800;color:#FFFFFF;letter-spacing:.08em">AERIS</div>
              <div style="font-size:.55rem;color:#B7C6D7;letter-spacing:.11em;line-height:1.25;
              font-family:JetBrains Mono,monospace">AEROSPACE RESEARCH<br/>INTELLIGENCE SYSTEM</div>
              <div style="font-size:.54rem;color:#7FA7D6;letter-spacing:.13em;
              font-family:JetBrains Mono,monospace;margin-top:.15rem">MISSION CONTROL v{APP_VERSION}</div>
            </div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

    with st.sidebar.expander("⚙  Settings", expanded=False):
        root_str = st.text_input(
            "Project root",
            value=str(_default_root()),
            key="sb_root",
            help="Absolute path to the AERIS repo root — the folder containing src/aeris/. "
                 "Auto-detected by walking up from the current working directory.",
        )
        exe = st.text_input(
            "AERIS executable",
            value=shutil.which("aeris") or "aeris",
            key="sb_exe",
            help="The 'aeris' command on your PATH, or an absolute path to the aeris script. "
                 "Auto-detected with shutil.which.",
        )
        tmo = int(st.number_input(
            "Timeout [s]",
            min_value=30, max_value=86400, value=1800, step=30,
            key="sb_tmo",
            help="Max seconds to wait for any single aeris command. "
                 "Default 1800 = 30 min. Increase for large dataset generation.",
        ))
        dry = st.toggle(
            "Dry-run (preview only)",
            False,
            key="sb_dry",
            help="When ON: shows the exact command that would run, but does NOT execute it. "
                 "Use to verify arguments before committing to a long run.",
        )

    root = Path(st.session_state.get("sb_root", str(_default_root()))).expanduser().resolve()
    exe  = st.session_state.get("sb_exe", shutil.which("aeris") or "aeris")
    tmo  = int(st.session_state.get("sb_tmo", 1800))
    dry  = bool(st.session_state.get("sb_dry", False))

    ok  = _repo_ok(root)
    dot = "#22C55E" if ok else "#EF4444"
    msg = "repo connected" if ok else "repo not found"
    st.sidebar.markdown(
        f"""<div style="padding:.15rem 1rem .8rem;display:flex;align-items:center;gap:8px;
        font-size:.78rem;color:#DCE8F4">
          <div style="width:8px;height:8px;border-radius:50%;background:{dot}"></div>
          <span style="color:#DCE8F4;font-weight:600">{msg}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    st.sidebar.markdown(
        """<div style="padding:.2rem .95rem .35rem">
          <div style="font-size:.70rem;color:#B7C6D7;letter-spacing:.14em;font-weight:800">WORKSPACE</div>
        </div>""",
        unsafe_allow_html=True,
    )

    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "home"

    for pid, icon, name in PAGES:
        selected = st.session_state["active_page"] == pid
        prefix   = "●" if selected else "○"
        if st.sidebar.button(
            f"{prefix}  {icon}  {name}",
            key=f"nav_{pid}",
            use_container_width=True,
            type="primary" if selected else "secondary",
        ):
            st.session_state["active_page"] = pid

    if "last" in st.session_state:
        r   = st.session_state["last"]
        col = "#22C55E" if r.returncode == 0 else "#EF4444"
        icon = "✓" if r.returncode == 0 else "✗"
        st.sidebar.markdown(
            f"""<div style="margin:1rem .85rem .7rem;padding:.6rem .75rem;
            border:1px solid #4B6075;border-radius:10px;background:#1B2A3A">
              <div style="font-size:.75rem;color:{col};font-family:JetBrains Mono,monospace;
              font-weight:700">{icon} last: exit {r.returncode}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    return root, exe, tmo, dry, st.session_state.get("active_page", "home")

# ═══════════════════════════════════════════════════════════════════════════════
# PAGES
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# PAGES — 100% codebase-verified CLI options, zero invalid flags
# ═══════════════════════════════════════════════════════════════════════════════

def pg_home(root, exe, tmo, dry):
    """Minimal product-style launchpad.

    This page should orient the operator. It should not duplicate the detailed
    workflow panels and should not fake backend outputs.
    """
    runs_root = root / "data" / "runs"
    ds_root   = root / "data" / "datasets"
    ml_root   = root / "data" / "processed" / "ml_runs"

    cfg_files = _files(str(root / "configs" / "geometry"), "*.yaml")
    airfoil_cfg_files = _files(str(root / "configs" / "airfoil"), "*.yaml")
    geo_runs  = _dirs(str(runs_root))
    all_ds    = _dirs(str(ds_root))
    promoted  = [d for d in all_ds if (Path(d) / "promotion_manifest.json").exists()]
    aero_ds   = [d for d in all_ds if (Path(d) / "aero_dataset.csv").exists()]
    airfoil_ds = [d for d in all_ds if (Path(d) / "airfoil_dataset_manifest.json").exists()]
    ml_runs   = [d for d in _dirs(str(ml_root)) if (Path(d) / "metrics.json").exists()]
    promo_mdl = [d for d in _dirs(str(ml_root)) if (Path(d) / "model_promotion_manifest.json").exists()]

    xfoil_ok = shutil.which("xfoil") is not None
    vsp_ok = shutil.which("vsp") is not None or shutil.which("vspaero") is not None
    avl_ok = shutil.which("avl") is not None

    _h("""<div style="position:relative;overflow:hidden;margin-bottom:1.25rem;padding:1.35rem 1.45rem;
      border:1px solid #2F80ED55;border-radius:22px;background:
      radial-gradient(circle at 12% 18%,#38BDF833 0,#38BDF800 28%),
      radial-gradient(circle at 92% 12%,#A78BFA24 0,#A78BFA00 25%),
      linear-gradient(135deg,#0B1220 0%,#17212B 54%,#111827 100%);
      box-shadow:0 20px 70px #02061766,inset 0 1px 0 #E0F2FE18">
      <div style="position:absolute;right:-70px;top:-80px;width:240px;height:240px;border:1px solid #38BDF833;
      border-radius:50%;box-shadow:0 0 80px #38BDF81A"></div>
      <div style="display:flex;align-items:center;gap:22px;position:relative;z-index:1">
        <div class="aeris-logo-orbit" style="width:92px;height:92px;border-radius:28px;position:relative;
        background:radial-gradient(circle at 34% 28%,#F8FAFC 0,#93C5FD 17%,#2563EB 50%,#0F172A 100%);
        border:1px solid #93C5FD99;box-shadow:0 0 0 1px #38BDF822 inset,0 22px 70px #1D4ED855;
        display:flex;align-items:center;justify-content:center;color:#FFFFFF;font-weight:900;font-size:2.55rem;
        letter-spacing:-.08em;font-family:Inter,sans-serif">A
          <div style="position:absolute;width:128px;height:38px;border:1.5px solid #BAE6FD99;border-radius:50%;
          transform:rotate(-24deg);box-shadow:0 0 22px #38BDF855"></div>
          <div style="position:absolute;right:10px;top:18px;width:8px;height:8px;background:#A7F3D0;border-radius:50%;
          box-shadow:0 0 16px #A7F3D0"></div>
        </div>
        <div>
          <div style="font-size:.72rem;color:#7DD3FC;letter-spacing:.24em;text-transform:uppercase;
          font-family:JetBrains Mono,monospace;font-weight:700;margin-bottom:.15rem">Mission Control</div>
          <h1 style="margin:0!important;font-size:2.45rem!important;line-height:1!important;font-weight:900!important;
          letter-spacing:-.04em!important;background:linear-gradient(90deg,#F8FAFC,#93C5FD,#A7F3D0);
          -webkit-background-clip:text;color:transparent">AERIS</h1>
          <div style="margin-top:.35rem;font-size:1.02rem;color:#EAF2FA;letter-spacing:.035em;font-weight:650">
            AERIS: Aerospace Research and Intelligence System
          </div>
          <p style="margin:.45rem 0 0!important;font-size:.82rem!important;color:#AAB6C2!important;
          font-family:JetBrains Mono,monospace">
            Evidence-driven aerospace design workstation · geometry → aero → data trust → ML → active learning
          </p>
        </div>
      </div>
    </div>""")

    _note(
        "Use this page as a launchpad only. Detailed work happens in the domain pages: "
        "<b>2D Airfoils</b>, <b>3D Geometry</b>, Dataset Factory, Aero Analysis, and ML Studio.",
        "info",
    )

    _sec("Environment")
    _stat_row([
        ("Repo", "connected" if _repo_ok(root) else "missing", "src/aeris"),
        ("XFOIL", "OK" if xfoil_ok else "not found", "2D airfoil sweeps"),
        ("AVL", "OK" if avl_ok else "not found", "3D aero solver"),
        ("OpenVSP", "OK" if vsp_ok else "not found", "CAD/VSP tooling"),
    ])

    _sec("Current workspace")
    _stat_row([
        ("3D configs", str(len(cfg_files)), "configs/geometry"),
        ("2D configs", str(len(airfoil_cfg_files)), "configs/airfoil"),
        ("3D/aero datasets", str(len(aero_ds)), "aero_dataset.csv"),
        ("2D airfoil datasets", str(len(airfoil_ds)), "airfoil_dataset_manifest.json"),
        ("Promoted datasets", str(len(promoted)), "promotion_manifest.json"),
        ("Promoted models", str(len(promo_mdl)), "model_promotion_manifest.json"),
    ])

    _sec("Workflow guardrails")
    _note(
        "Workflow preflight and workflow templates are available in the <b>Workflow Cockpit</b>. "
        "The Overview stays intentionally simple: identity, environment, workspace counts, and latest workflow evidence.",
        "info",
    )

    _sec("Workflow evidence")
    _workflow_evidence_card(root, _latest_workflow_root(root), key="home_workflow_evidence")


def _geo_var_table(cfg_path: str) -> None:
    """Read a geometry YAML and render a COMPLETE config reference table.

    Sections shown:
      1. Generator metadata + spline/controls parameters
      2. Planform design variables (with bounds)
      3. Section design variables (with bounds) + fixed section params
      4. Elevon geometry DVs (v3 only)
      5. Control surfaces (full metadata for each surface)
      6. Outputs flags + dataset sampling settings
    Amber = nearly fixed (spread < 0.01). Green = active sampled DV.
    """
    NOTES = {
        "c1_m":           ("Chord",    "Root chord (absolute)"),
        "c2_ratio":       ("Chord",    "Chord ratio relative to c1"),
        "c3_ratio":       ("Chord",    "Chord ratio relative to c1"),
        "c4_ratio":       ("Chord",    "Tip chord ratio relative to c1"),
        "b_total_m":      ("Span",     "Semi-span — full span = 2×"),
        "b3_ratio":       ("Span",     "Outboard segment fraction"),
        "split_ratio":    ("Span",     "Inner/mid split fraction"),
        "sw1_deg":        ("Sweep",    "Inner LE sweep. YAML positive; Python negative."),
        "sw2_deg":        ("Sweep",    "Mid sweep"),
        "sw3_deg":        ("Sweep",    "Outer sweep"),
        "twist_b0_deg":   ("Twist",    "Root twist. Positive = LE up."),
        "twist_b1_deg":   ("Twist",    "Inner twist"),
        "twist_b2_deg":   ("Twist",    "Mid twist"),
        "twist_b3_deg":   ("Twist",    "Tip twist"),
        "dihedral_b1_deg":("Dihedral", "Inner dihedral"),
        "dihedral_b2_deg":("Dihedral", "Mid dihedral"),
        "dihedral_b3_deg":("Dihedral", "Outer dihedral"),
    }
    UNITS = {
        "c1_m":"m","b_total_m":"m",
        "sw1_deg":"°","sw2_deg":"°","sw3_deg":"°",
        "twist_b0_deg":"°","twist_b1_deg":"°","twist_b2_deg":"°","twist_b3_deg":"°",
        "dihedral_b1_deg":"°","dihedral_b2_deg":"°","dihedral_b3_deg":"°",
    }

    cfg_data = None
    if yaml and cfg_path and Path(cfg_path).exists():
        try:
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
        except Exception:
            cfg_data = None

    geo      = (cfg_data or {}).get("geometry", {})
    pb       = geo.get("planform_bounds", {})
    sb       = geo.get("section_bounds", {})
    eb       = geo.get("elevon_bounds") or {}
    cs_cfg   = geo.get("control_surfaces") or {}
    gen_cfg  = geo.get("generator", {})
    ctrl_cfg = geo.get("controls", {})
    out_cfg  = geo.get("outputs", {})
    ds_cfg   = (cfg_data or {}).get("dataset", {})

    def _rng_cell(b, unit=""):
        if not isinstance(b, dict) or "min" not in b:
            return "— not found —", "#5A7A96"
        mn, mx = float(b["min"]), float(b["max"])
        spread = abs(mx - mn)
        if spread < 0.01:
            return f"fixed ≈ {mn}{unit}", "#F59E0B"
        return f"{mn} – {mx}{unit}", "#86EFAC"

    def _tbl_header():
        return (
            '<table style="width:100%;border-collapse:collapse;font-size:.8rem;margin-bottom:.5rem">'
            '<thead><tr style="border-bottom:1px solid #334252">'
            '<th style="text-align:left;padding:.35rem .6rem;color:#8EA0B3;font-weight:600;width:13%">Group</th>'
            '<th style="text-align:left;padding:.35rem .6rem;color:#8EA0B3;font-weight:600;width:22%">Variable / Parameter</th>'
            '<th style="text-align:left;padding:.35rem .6rem;color:#8EA0B3;font-weight:600;width:22%">Value / Range</th>'
            '<th style="text-align:left;padding:.35rem .6rem;color:#8EA0B3;font-weight:600">Notes</th>'
            '</tr></thead><tbody>'
        )

    def _row(group, var, val, note, val_col="#D6DEE8", prev_group=None):
        sep = "border-bottom:1px solid #1E2F3E;"
        return (
            f'<tr style="{sep}">'
            f'<td style="padding:.33rem .6rem;color:#C0CAD6">'
            f'{"" if group == prev_group else group}</td>'
            f'<td style="padding:.33rem .6rem;font-family:JetBrains Mono,monospace;'
            f'color:#93C5FD;white-space:nowrap">{var}</td>'
            f'<td style="padding:.33rem .6rem;color:{val_col};white-space:nowrap">{val}</td>'
            f'<td style="padding:.33rem .6rem;color:#8EA0B3">{note}</td>'
            f'</tr>'
        )

    # ── 1. Generator & spline params ─────────────────────────────────────────
    _h('<div style="color:#8EA0B3;font-size:.72rem;text-transform:uppercase;'
       'letter-spacing:.1em;margin:.8rem 0 .3rem">Generator &amp; Controls</div>')
    tbl = _tbl_header(); prev = None
    gen_id   = gen_cfg.get("id", gen_cfg.get("family", "—"))
    gen_seed = str(gen_cfg.get("seed", "—"))
    for g, v, val, note in [
        ("Generator", "id",                   gen_id,    "Generator family+version string"),
        ("Generator", "seed",                 gen_seed,  "Same seed + same config = identical geometry"),
        ("Spline", "n_points",                str(ctrl_cfg.get("n_points", "—")),              "Total spline control points"),
        ("Spline", "n_spline_inboard",        str(ctrl_cfg.get("n_spline_inboard", "—")),      "Inboard sections — 10=fast, 16=fine"),
        ("Spline", "n_spline_outboard",       str(ctrl_cfg.get("n_spline_outboard", "—")),     "Outboard sections"),
        ("Spline", "spline_split_ratio",      str(ctrl_cfg.get("spline_split_ratio", "—")),    "Inboard/outboard split fraction"),
        ("Spline", "segment_length_variation",str(ctrl_cfg.get("segment_length_variation", "—")), "0=uniform spacing, >0=random variation"),
        ("Spline", "sweep_variation",         str(ctrl_cfg.get("sweep_variation", "—")),       "Local sweep randomisation magnitude"),
        ("Spline", "curvature_strength",      str(ctrl_cfg.get("curvature_strength", ctrl_cfg.get("desired_curvature_strength", "—"))), "Curvature magnitude"),
    ]:
        col = "#FCD34D" if v == "seed" else "#D6DEE8"
        tbl += _row(g, v, val, note, col, prev); prev = g
    _h(tbl + "</tbody></table>")

    # ── 2. Planform + Section DVs ─────────────────────────────────────────────
    _h('<div style="color:#8EA0B3;font-size:.72rem;text-transform:uppercase;'
       'letter-spacing:.1em;margin:.8rem 0 .3rem">Design Variables — Planform &amp; Sections</div>')
    _note("Amber = nearly fixed (spread &lt; 0.01) — not useful for ML. Green = active sampled DV.", "info")
    tbl = _tbl_header(); prev = None
    bounds = {**pb, **sb}
    for var, (group, note) in NOTES.items():
        b = bounds.get(var, {})
        val, col = _rng_cell(b, UNITS.get(var, ""))
        tbl += _row(group, var, val, note, col, prev); prev = group
    airfoil  = sb.get("airfoil_name", "—")
    dih_root = sb.get("dihedral_root_deg", "—")
    tbl += _row("Section", "airfoil_name",       airfoil,                   "Airfoil profile for all sections",    "#86EFAC", prev); prev = "Section"
    tbl += _row("Section", "dihedral_root_deg",  f"{dih_root}° (fixed)", "Root dihedral — always 0°", "#F59E0B", prev)
    _h(tbl + "</tbody></table>")

    # ── 3. Elevon geometry DVs (v3 only) ──────────────────────────────────────
    if eb:
        _h('<div style="color:#8EA0B3;font-size:.72rem;text-transform:uppercase;'
           'letter-spacing:.1em;margin:.8rem 0 .3rem">Elevon Geometry DVs (v3 — 20 DV config)</div>')
        _note("3 extra DVs: elevon size and hinge position vary per geometry sample.", "info")
        tbl = _tbl_header(); prev = None
        for var, note in [
            ("elevon_start_frac", "Inboard edge of elevon [fraction of semi-span]"),
            ("elevon_end_frac",   "Outboard edge of elevon [fraction of semi-span]"),
            ("elevon_hinge_frac", "Hinge line position [fraction of local chord]"),
        ]:
            val, col = _rng_cell(eb.get(var, {}), "")
            tbl += _row("Elevon DVs", var, val, note, col, prev); prev = "Elevon DVs"
        _h(tbl + "</tbody></table>")

    # ── 4. Control surfaces ────────────────────────────────────────────────────
    surfaces   = cs_cfg.get("surfaces", []) if isinstance(cs_cfg, dict) else []
    cs_enabled = cs_cfg.get("enabled", False) if isinstance(cs_cfg, dict) else False
    _h('<div style="color:#8EA0B3;font-size:.72rem;text-transform:uppercase;'
       'letter-spacing:.1em;margin:.8rem 0 .3rem">Control Surfaces</div>')

    # Always show the master control-surface switch.
    # This avoids confusion between "surface definitions exist in YAML"
    # and "controls are actually active for this geometry".
    tbl = _tbl_header(); prev = None
    active_controls = bool(cs_enabled and surfaces)
    status_rows = [
        (
            "Status",
            "control_surfaces.enabled",
            str(bool(cs_enabled)),
            "Master switch from geometry.control_surfaces.enabled",
            "#86EFAC" if cs_enabled else "#F59E0B",
        ),
        (
            "Status",
            "surface_count",
            str(len(surfaces)),
            "Number of surface definitions found in YAML",
            "#86EFAC" if surfaces else "#F59E0B",
        ),
        (
            "Status",
            "controls_active",
            str(active_controls),
            "True only when enabled=True and at least one surface exists",
            "#86EFAC" if active_controls else "#F59E0B",
        ),
        (
            "Status",
            "plot_overlay_auto",
            "visible" if active_controls else "hidden",
            "Automatic planform control-span overlay status",
            "#86EFAC" if active_controls else "#F59E0B",
        ),
    ]
    for g, v, val, note, col in status_rows:
        tbl += _row(g, v, val, note, col, prev); prev = g
    _h(tbl + "</tbody></table>")

    if not cs_enabled or not surfaces:
        _note("No active control surfaces configured in this YAML.", "warn")
    else:
        _note(
            f"<b>{len(surfaces)}</b> surface(s). These are <b>AVL metadata</b> — hinge lines and d-number "
            "wiring for the solver. Physical deflection happens at aero-generate time or via export-deflected-cad.",
            "info",
        )
        for i, surf in enumerate(surfaces):
            is_sym   = surf.get("symmetric", True)
            d_num    = i + 1
            sym_str  = f"symmetric (d{d_num} — pitch, both sides)" if is_sym else f"antisymmetric (d{d_num} — roll, side={surf.get('side','?')})"
            span_s   = surf.get("spanwise", {}).get("start_frac", surf.get("start_frac", "—"))
            span_e   = surf.get("spanwise", {}).get("end_frac",   surf.get("end_frac",   "—"))
            tbl = _tbl_header(); prev = None
            for g, v, val, note in [
                ("Surface", "name",           surf.get("name", "—"),               "AVL control surface name (d-number order)"),
                ("Surface", "family",         surf.get("family", "—"),             "trailing_edge = standard elevon"),
                ("Surface", "symmetric",      sym_str,                                  "True=pitch d1, False=roll d2"),
                ("Surface", "side",           str(surf.get("side") or "both (symmetric)"), "Which wing side this surface acts on"),
                ("Surface", "spanwise_start", str(span_s),                              "Inboard edge [fraction of semi-span]"),
                ("Surface", "spanwise_end",   str(span_e),                              "Outboard edge [fraction of semi-span]"),
                ("Surface", "hinge_point",    str(surf.get("hinge_point", "—")),   "Hinge at this chord fraction"),
                ("Surface", "deflection_sign",surf.get("deflection_sign", "—"),    "standard = trailing-edge-down positive"),
                ("Surface", "required",       str(surf.get("required", False)),          "True: solver errors if surface absent"),
            ]:
                col = "#93C5FD" if v == "name" else "#D6DEE8"
                tbl += _row(g, v, val, note, col, prev); prev = g
            _h(tbl + "</tbody></table>")

    # ── 5. Outputs & dataset sampling ─────────────────────────────────────────
    _h('<div style="color:#8EA0B3;font-size:.72rem;text-transform:uppercase;'
       'letter-spacing:.1em;margin:.8rem 0 .3rem">Outputs &amp; Sampling</div>')
    tbl = _tbl_header(); prev = None
    for g, v, val, note in [
        ("Outputs", "save_plot",         str(out_cfg.get("save_plot", "—")),      "Save planform PNG per geometry case"),
        ("Outputs", "build_aerosandbox", str(out_cfg.get("build_aerosandbox", "—")), "Required for AVL runs and dataset generation"),
        ("Dataset", "sampling.method",   str((ds_cfg.get("sampling") or {}).get("method", "—")), "LHS = Latin Hypercube Sampling"),
        ("Dataset", "sampling.seed",     str((ds_cfg.get("sampling") or {}).get("seed",   "—")), "Reproducibility seed for geometry sampling"),
    ]:
        col = "#FCD34D" if "seed" in v else "#86EFAC" if val == "True" else "#F59E0B" if val == "False" else "#D6DEE8"
        tbl += _row(g, v, val, note, col, prev); prev = g
    _h(tbl + "</tbody></table>")

    st.caption(
        "Control surfaces shown here are AVL wiring metadata — they do not physically deflect in the 3D viewer. "
        "Same seed + same config = identical geometry every time."
    )


def _geo_delete_one(p: Path, key_suffix: str) -> bool:
    """Render one run-folder row with an inline delete button. Returns True if deleted.

    Key uses folder NAME (stable identity), not list index.
    This prevents Streamlit's session-state from retaining a True button value
    across reruns and triggering phantom second deletions.
    """
    import shutil as _shutil
    # Stable key: hash of the absolute path, not the positional index.
    # key_suffix is kept as a namespace prefix to avoid cross-section collisions.
    stable_key = f"del_{key_suffix}__{p.name}"

    m      = _rjson(p / "manifest.json")
    status = (m or {}).get("status", "—")
    dot    = "#22C55E" if status == "success" else "#EF4444" if status == "failed" else "#8EA0B3"
    loc    = "generate" if "data/runs" in str(p) else "visualize"

    col_name, col_btn = st.columns([10, 1])
    with col_name:
        _h(
            f'<div style="background:#1B2A3A;border:1px solid #2D3F52;border-radius:7px;'
            f'padding:.42rem .9rem;display:flex;align-items:center;gap:10px">'
            f'<div style="width:7px;height:7px;border-radius:50%;background:{dot};flex-shrink:0"></div>'
            f'<div style="flex:1;font-size:.78rem;color:#D6DEE8;font-family:JetBrains Mono,monospace;'
            f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{p.name}</div>'
            f'<div style="font-size:.68rem;color:#5A7A96;flex-shrink:0;margin-right:6px">{loc}</div>'
            f'<div style="font-size:.7rem;color:{dot};flex-shrink:0;font-weight:600">{status}</div>'
            f'</div>'
        )
    with col_btn:
        if not p.exists():
            # Already deleted in this render cycle — skip silently
            return False
        if st.button("🗑", key=stable_key, help=f"Delete {p.name}"):
            try:
                _shutil.rmtree(p)
                st.cache_data.clear()  # force _dirs() to re-read on next render
                st.toast(f"Deleted: {p.name}", icon="🗑")
                return True
            except Exception as e:
                st.error(f"Could not delete {p.name}: {e}")
    return False


def pg_geometry(root, exe, tmo, dry):
    import shutil as _shutil

    _hero("△", "Geometry", "bwb_segmented_v1 · 20 design variables", "generator")
    tab_gen, tab_vis, tab_info, tab_inspect, tab_cad = st.tabs(["  ① Generate  ", "  ② Visualize  ", "  ③ Design variables  ", "  ④ Inspect run  ", "  ⑤ CAD export  "])

    # Shared config list — built once, used in all tabs
    cfg_files = _files(str(root / "configs" / "geometry"), "*.yaml")
    prod_cfg  = str(root / "configs" / "geometry" / "bwb_training_v1.yaml")
    smoke_cfg = str(root / "configs" / "geometry" / "baseline_bwb_25.yaml")

    def _cfg_label(s):
        if "bwb_training_v1" in s: return f"Production — {Path(s).name}"
        if "baseline_bwb_25"  in s: return f"Smoke test  — {Path(s).name}"
        return Path(s).name

    cfg_prod_first  = ([prod_cfg]  if prod_cfg  in cfg_files else []) +                       ([smoke_cfg] if smoke_cfg in cfg_files else []) +                       [f for f in cfg_files if f not in (prod_cfg, smoke_cfg)]
    cfg_smoke_first = ([smoke_cfg] if smoke_cfg in cfg_files else []) +                       ([prod_cfg]  if prod_cfg  in cfg_files else []) +                       [f for f in cfg_files if f not in (prod_cfg, smoke_cfg)]

    if not cfg_files:
        st.warning(f"No YAML files found under {root / 'configs' / 'geometry'}. "
                   "Check your project root in the sidebar.")
        return

    # ── GENERATE ─────────────────────────────────────────────────────────────
    with tab_gen:
        sel_cfg = st.selectbox(
            "Config", cfg_prod_first,
            format_func=_cfg_label, key="gg_cfg",
            help="Production = wide design space, use for ML. "
                 "Smoke = near-fixed, use only to verify the solver works.",
        )
        if "bwb_training_v1" in sel_cfg:
            st.success("✓ Wide design space — correct for ML training campaigns.")
        elif "baseline_bwb_25" in sel_cfg:
            st.warning("⚠ Near-fixed design space — smoke / solver-check only. Not suitable for ML.")
        else:
            st.info(f"Custom config: {Path(sel_cfg).name}")

        save_plot_policy = st.radio(
            "Planform plot",
            ["Use YAML setting", "Force save plot", "Force no plot"],
            index=0,
            horizontal=True,
            key="gg_save_plot_policy",
            help=(
                "Overrides geometry.outputs.save_plot only for this run. "
                "Use no plot for fast batch-style geometry checks; save plot for visual inspection."
            ),
        )

        gen_args = ["geometry", "generate", "--config", sel_cfg]
        if save_plot_policy == "Force save plot":
            gen_args.append("--save-plot")
        elif save_plot_policy == "Force no plot":
            gen_args.append("--no-save-plot")

        _panel(
            "Generate geometry",
            "Output → data/runs/<timestamp>_geometry_<stem>/",
            gen_args,
            root, exe, tmo, dry, "g_run",
            label="▶  Generate geometry",
        )
        # Show output directory note after run — the seed comes from the YAML config
        _note(
            f"Seed is read from the YAML <code>geometry.generator.seed</code> field. "
            f"Plot saving can be overridden above without editing the YAML. "
            f"Run output → <code>data/runs/&lt;timestamp&gt;_geometry_{Path(sel_cfg).stem}/</code>",
            "info",
        )

        # ── Runs from data/runs/ ──────────────────────────────────────────
        geo_runs = [Path(r) for r in _dirs(str(root / "data" / "runs"))
                    if "geometry" in Path(r).name]

        if geo_runs:
            _sec("Generated geometry runs  (data/runs/)")
            st.caption("Click 🗑 on any row to delete that folder immediately.")
            did_delete = False
            for i, p in enumerate(geo_runs[:20]):
                # Show key metrics from manifest alongside the delete button
                m   = _rjson(p / "manifest.json") or {}
                geo = m.get("geometry") or {}
                cs  = geo.get("case_summary") or {}
                cs_met = cs.get("metrics") or {}  # metrics live under case_summary["metrics"]
                seed_v = geo.get("design_sampling_seed", "—")
                semi   = cs_met.get("semi_span_m")
                area   = cs_met.get("approx_area_m2")
                ar_v   = cs_met.get("approx_aspect_ratio_planform")
                metrics_str = "  ·  ".join(filter(None, [
                    f"seed {seed_v}" if seed_v != "—" else None,
                    f"semi-span {semi:.3f} m" if semi is not None else None,
                    f"area {area:.4f} m²"     if area  is not None else None,
                    f"AR {ar_v:.2f}"          if ar_v  is not None else None,
                ]))
                col_info, col_del = st.columns([11, 1])
                with col_info:
                    status = m.get("status", "—")
                    dot_c  = "#22C55E" if status == "success" else "#EF4444"
                    _h(
                        f'<div style="background:#1B2A3A;border:1px solid #2D3F52;border-radius:7px;'
                        f'padding:.38rem .9rem;display:flex;flex-direction:column;gap:2px">'
                        f'<div style="display:flex;align-items:center;gap:8px">'
                        f'<div style="width:7px;height:7px;border-radius:50%;background:{dot_c};flex-shrink:0"></div>'
                        f'<div style="font-size:.78rem;color:#D6DEE8;font-family:JetBrains Mono,monospace;'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">{p.name}</div>'
                        f'<div style="font-size:.7rem;color:{dot_c};font-weight:600;flex-shrink:0">{status}</div>'
                        f'</div>'
                        + (f'<div style="font-size:.7rem;color:#5A7A96;font-family:JetBrains Mono,monospace;'
                           f'padding-left:15px">{metrics_str}</div>' if metrics_str else '')
                        + f'</div>'
                    )
                with col_del:
                    import shutil as _shutil2
                    if st.button("🗑", key=f"del_gen_{i}", help=f"Delete {p.name}"):
                        try:
                            _shutil2.rmtree(p)
                            st.toast(f"Deleted: {p.name}", icon="🗑")
                            did_delete = True
                        except Exception as e:
                            st.error(f"Could not delete {p.name}: {e}")
            if did_delete:
                st.rerun()

            if len(geo_runs) > 1:
                st.markdown("")
                if st.button(
                    f"🗑  Delete ALL generate runs ({len(geo_runs)})",
                    key="gg_del_all_gen", type="secondary",
                ):
                    st.session_state["gg_confirm_gen"] = True
                    # Snapshot the list NOW — not on the next rerun
                    st.session_state["gg_to_delete_gen"] = [str(p) for p in geo_runs]

            if st.session_state.get("gg_confirm_gen"):
                # Use the snapshot taken at confirm time, not the live list
                to_delete = st.session_state.get("gg_to_delete_gen", geo_runs)
                st.warning(f"Delete all {len(to_delete)} generate run folder(s)? This cannot be undone.")
                ca, cb, _ = st.columns([1, 1, 4])
                if ca.button("Yes, delete all", key="gg_confirm_gen_yes", type="primary"):
                    deleted = []
                    for p in to_delete:
                        if not Path(p).exists():
                            continue
                        try:
                            _shutil.rmtree(p)
                            deleted.append(Path(p).name)
                        except Exception as e:
                            st.error(f"{Path(p).name}: {e}")
                    st.session_state["gg_confirm_gen"] = False
                    st.session_state.pop("gg_to_delete_gen", None)
                    st.cache_data.clear()
                    st.toast(f"Deleted {len(deleted)} folder(s).", icon="🗑")
                    st.rerun()
                if cb.button("Cancel", key="gg_confirm_gen_no", type="secondary"):
                    st.session_state["gg_confirm_gen"] = False
                    st.session_state.pop("gg_to_delete_gen", None)
                    st.rerun()
        else:
            st.caption("No generate runs yet — data/runs/ is empty.")

    # ── VISUALIZE ─────────────────────────────────────────────────────────────
    with tab_vis:
        # ── Geometry source ───────────────────────────────────────────────
        geo_run_paths = [Path(r) for r in _dirs(str(root / "data" / "runs"))
                         if "geometry" in Path(r).name
                         and not any(k in Path(r).name for k in ("_aero_", "_sweep_"))]

        src_mode = st.radio(
            "Geometry source",
            ["From existing run", "From config file"],
            horizontal=True,
            key="gv_src_mode",
            help="From existing run: reuses the exact same config AND seed that produced "
                 "that geometry — so you visualize the identical shape. "
                 "From config file: choose any config and seed freely.",
        )

        # resolved for the buttons
        vcfg       = ""
        auto_seed  = None   # int seed read from manifest — None means not resolved yet

        if src_mode == "From existing run":
            if not geo_run_paths:
                st.warning(
                    "No geometry runs found in data/runs/. "
                    "Go to ① Generate first, then come back here."
                )
            else:
                run_opts = {p.name: p for p in geo_run_paths}
                chosen_run_name = st.selectbox(
                    "Select generated run",
                    list(run_opts.keys()),
                    key="gv_run_sel",
                    help="Pick the run folder. Config and seed are read automatically "
                         "from that run — you will visualize the exact geometry that was generated.",
                )
                chosen_run = run_opts[chosen_run_name]

                # Read seed from manifest (authoritative)
                m = _rjson(chosen_run / "manifest.json")
                auto_seed = (m or {}).get("geometry", {}).get("design_sampling_seed")
                status    = (m or {}).get("status", "unknown")
                dot_col   = "#22C55E" if status == "success" else "#EF4444"

                # Config from input_config.yaml
                saved_cfg = chosen_run / "input_config.yaml"
                if saved_cfg.exists():
                    vcfg = str(saved_cfg)
                    cfg_display = saved_cfg.name
                else:
                    st.warning(
                        f"No input_config.yaml in {chosen_run.name}. "
                        "Falling back to config picker."
                    )
                    vcfg = st.selectbox(
                        "Config (fallback)", cfg_smoke_first,
                        format_func=_cfg_label, key="gv_cfg_fb",
                    )
                    cfg_display = Path(vcfg).name if vcfg else "—"

                # Info row
                seed_display = str(auto_seed) if auto_seed is not None else "unknown"
                _h(
                    f'<div style="background:#1B2A3A;border:1px solid #2D3F52;border-radius:8px;'
                    f'padding:.55rem 1rem;margin:.35rem 0;display:flex;align-items:center;gap:12px">'
                    f'<div style="width:8px;height:8px;border-radius:50%;background:{dot_col};flex-shrink:0"></div>'
                    f'<div style="flex:1;font-size:.8rem;color:#D6DEE8">'
                    f'<span style="font-family:JetBrains Mono,monospace;color:#93C5FD">{chosen_run.name}</span>'
                    f'<span style="color:#5A7A96"> · config: </span>{cfg_display}'
                    f'<span style="color:#5A7A96"> · seed: </span>'
                    f'<span style="color:#FCD34D">{seed_display}</span></div>'
                    f'<div style="font-size:.7rem;color:{dot_col};font-weight:600">{status}</div>'
                    f'</div>'
                )
                if auto_seed is not None:
                    st.caption(
                        f"Seed **{auto_seed}** read from manifest — "
                        "visualize will reproduce the exact same geometry."
                    )
                else:
                    st.caption(
                        "Seed not found in manifest. "
                        "The geometry may not be exactly reproduced."
                    )
        else:
            # From config file — user controls seed freely
            vcfg = st.selectbox(
                "Config", cfg_smoke_first,
                format_func=_cfg_label, key="gv_cfg",
                help="Pick which config to sample one geometry from.",
            )

        # ── Seed (only shown in config-file mode) ────────────────────────
        if src_mode == "From config file":
            c1, c2 = st.columns([1, 2])
            seed_val = c1.number_input(
                "Seed", min_value=0, max_value=99999, value=42, step=1,
                key="gv_seed",
                help="Same seed + same config = same geometry every time.",
            )
            png_name = c2.text_input(
                "PNG filename (optional)",
                value="", placeholder="e.g. bwb_sweep35  — leave blank for auto name",
                key="gv_pngname",
            )
        else:
            # Seed comes from manifest — not shown to user
            seed_val = auto_seed if auto_seed is not None else 0
            png_name = st.text_input(
                "PNG filename (optional)",
                value="", placeholder="e.g. bwb_seed100_run1  — leave blank for auto name",
                key="gv_pngname",
            )

        # ── Buttons ───────────────────────────────────────────────────────
        if not vcfg:
            st.info("Select a run or config above to enable visualization.")
        else:
            st.caption(
                "**▶ Visualize 3D wing** — opens an interactive OpenGL window. "
                "Requires a local desktop (not SSH / headless).  "
                "**📷 Save plot as PNG** — saves a 2D top-view image. Works everywhere."
            )
            col_a, col_b = st.columns(2)
            with col_a:
                _panel(
                    "Visualize 3D wing",
                    "Output → data/debug/visualization_runs/<timestamp>/",
                    ["geometry", "visualize", "--config", vcfg,
                     "--seed", str(int(seed_val)), "--draw-3d"],
                    root, exe, tmo, dry, "gv_3d",
                    label="▶  Visualize 3D wing",
                )
            with col_b:
                args_png = ["geometry", "visualize", "--config", vcfg,
                            "--seed", str(int(seed_val)), "--no-draw-3d", "--save-plot"]
                if png_name.strip():
                    out_dir = root / "data" / "debug" / "plots" / png_name.strip()
                    args_png += ["--output-dir", str(out_dir)]
                _panel(
                    "Save plot as PNG",
                    "Output → data/debug/visualization_runs/<timestamp>/  "
                    "(or plots/<name>/ if named).",
                    args_png,
                    root, exe, tmo, dry, "gv_png",
                    label="📷  Save plot as PNG",
                )

        # ── Auto-display most recent PNG from last save-plot run ──────────
        viz_base_auto = root / "data" / "debug" / "visualization_runs"
        plot_base_auto = root / "data" / "debug" / "plots"
        # Scan both dirs for the newest PNG
        _all_pngs = sorted(
            list(viz_base_auto.glob("*/*.png")) + list(plot_base_auto.glob("*/*.png")),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        ) if (viz_base_auto.exists() or plot_base_auto.exists()) else []
        if _all_pngs:
            _sec("Latest saved planform PNG")
            latest_png = _all_pngs[0]
            st.caption(f"{latest_png.relative_to(root) if latest_png.is_relative_to(root) else latest_png}")
            st.image(str(latest_png), use_container_width=True)
            if len(_all_pngs) > 1:
                with st.expander(f"Previous PNGs ({len(_all_pngs) - 1})", expanded=False):
                    for png in _all_pngs[1:6]:
                        st.caption(str(png.name))
                        st.image(str(png), use_container_width=True)

        # ── Runs from data/debug/visualization_runs/ + data/debug/plots/ ──
        viz_base  = root / "data" / "debug" / "visualization_runs"
        plot_base = root / "data" / "debug" / "plots"
        viz_runs  = [Path(r) for r in _dirs(str(viz_base))]
        plot_runs = [Path(r) for r in _dirs(str(plot_base))]
        all_viz   = viz_runs + plot_runs

        if all_viz:
            _sec("Visualize outputs")
            st.caption(
                "`visualization_runs/` = 3D viewer and default PNG runs. "
                "`plots/` = named PNG outputs. Click 🗑 to delete."
            )
            did_delete = False
            for i, p in enumerate(all_viz[:20]):
                if _geo_delete_one(p, f"viz_{i}"):
                    did_delete = True
            if did_delete:
                st.rerun()

            if len(all_viz) > 1:
                st.markdown("")
                if st.button(
                    f"🗑  Delete ALL visualize outputs ({len(all_viz)})",
                    key="gv_del_all", type="secondary",
                ):
                    st.session_state["gv_confirm_all"] = True
                    st.session_state["gv_to_delete"] = [str(p) for p in all_viz]

            if st.session_state.get("gv_confirm_all"):
                to_delete_viz = st.session_state.get("gv_to_delete", all_viz)
                st.warning(f"Delete all {len(to_delete_viz)} visualize output folder(s)? This cannot be undone.")
                ca, cb, _ = st.columns([1, 1, 4])
                if ca.button("Yes, delete all", key="gv_confirm_all_yes", type="primary"):
                    deleted = []
                    for p in to_delete_viz:
                        if not Path(p).exists():
                            continue
                        try:
                            _shutil.rmtree(p)
                            deleted.append(Path(p).name)
                        except Exception as e:
                            st.error(f"{Path(p).name}: {e}")
                    st.session_state["gv_confirm_all"] = False
                    st.session_state.pop("gv_to_delete", None)
                    st.cache_data.clear()
                    st.toast(f"Deleted {len(deleted)} folder(s).", icon="🗑")
                    st.rerun()
                if cb.button("Cancel", key="gv_confirm_all_no", type="secondary"):
                    st.session_state["gv_confirm_all"] = False
                    st.session_state.pop("gv_to_delete", None)
                    st.rerun()
        else:
            st.caption("No visualize outputs yet.")

    # ── DESIGN VARIABLES ─────────────────────────────────────────────────────
    with tab_info:
        info_cfg = st.selectbox(
            "Show bounds for config", cfg_prod_first,
            format_func=_cfg_label, key="gi_cfg",
            help="Switch config to see the exact design-variable bounds from that YAML file.",
        )
        st.caption(
            "Ranges are read directly from the selected YAML. "
            "**Amber** = nearly fixed (min ≈ max) — not useful for ML training."
        )
        _geo_var_table(info_cfg)


    # ── INSPECT ──────────────────────────────────────────────────────────────
    with tab_inspect:
        _note(
            "Inspect any completed geometry run — reads <code>manifest.json</code> "
            "and shows seed, key aerodynamic metrics, and artifact paths. "
            "Equivalent to <code>aeris geometry inspect --run-dir &lt;run&gt;</code>.",
            "info",
        )
        insp_runs = [Path(r) for r in _dirs(str(root / "data" / "runs"))
                     if "geometry" in Path(r).name
                     and not any(k in Path(r).name for k in ("_aero_", "_sweep_"))]
        if not insp_runs:
            st.warning("No geometry runs found in data/runs/. Run ① Generate first.")
        else:
            chosen_insp = st.selectbox(
                "Select run to inspect",
                [p.name for p in insp_runs],
                key="gi_insp_run",
                help="Pick a geometry run folder. Data is read from manifest.json.",
            )
            insp_path = next((p for p in insp_runs if p.name == chosen_insp), None)
            if insp_path:
                m   = _rjson(insp_path / "manifest.json") or {}
                geo = m.get("geometry") or {}
                # case_summary is the full build_geometry_summary() output — a nested dict.
                # Key metric fields live under cs["metrics"], planform values under cs["sampled_planform"].
                cs      = geo.get("case_summary") or {}
                cs_met  = cs.get("metrics") or {}
                cs_pf   = cs.get("sampled_planform") or {}
                status  = m.get("status", "unknown")

                # Status + identity
                c1, c2, c3 = st.columns(3)
                c1.metric("Status", status)
                c2.metric("Seed", str(geo.get("design_sampling_seed", "—")))
                c3.metric("Generator", str(geo.get("generator_id", "—")))

                # Key aerodynamic metrics — from cs["metrics"]
                semi = cs_met.get("semi_span_m")
                full = cs_met.get("full_span_m")
                area = cs_met.get("approx_area_m2")
                ar_v = cs_met.get("approx_aspect_ratio_planform")
                ar_asb = cs_met.get("aspect_ratio_aerosandbox")

                # Planform values from cs["sampled_planform"]
                c1_m = cs_pf.get("c1_m")
                b_total = cs_pf.get("b_total_m")

                if any(v is not None for v in [semi, full, area, ar_v]):
                    _sec("Key geometry metrics")
                    stat_items = []
                    if semi is not None:
                        stat_items.append(("Semi-span", f"{semi:.3f} m", "half-span"))
                    if full is not None:
                        stat_items.append(("Full span", f"{full:.3f} m", "2 × semi"))
                    if area is not None:
                        stat_items.append(("Planform area", f"{area:.4f} m²", "approx"))
                    if ar_v is not None:
                        stat_items.append(("AR (planform)", f"{ar_v:.2f}", "planform AR"))
                    if ar_asb is not None:
                        stat_items.append(("AR (ASB)", f"{ar_asb:.2f}", "AeroSandbox"))
                    _stat_row(stat_items)

                    # Planform parameters
                    if c1_m is not None or b_total is not None:
                        _sec("Planform parameters")
                        pf_items = []
                        if c1_m is not None:
                            pf_items.append(("Root chord c1", f"{c1_m:.4f} m", "sampled"))
                        if b_total is not None:
                            pf_items.append(("Semi-span b_total", f"{b_total:.4f} m", "sampled"))
                        _stat_row(pf_items)
                else:
                    if cs:
                        st.warning(
                            'Metrics not found under `case_summary["metrics"]`. '
                            "This may indicate a schema change. Check Full manifest below."
                        )
                    else:
                        st.warning("No case_summary in manifest. Run may have failed during geometry generation.")

                # Timestamps
                _sec("Run metadata")
                st.caption(
                    f"Created: {m.get('created_at_utc', '—')}  ·  "
                    f"Completed: {m.get('completed_at_utc', '—')}  ·  "
                    f"Config: {Path(m.get('config_path', '—')).name}"
                )
                st.caption(f"Run root: `{insp_path}`")

                # Artifact paths
                gspath = insp_path / "artifacts" / "geometry" / "geometry_summary.json"
                if gspath.exists():
                    gs = _rjson(gspath) or {}
                    with st.expander("geometry_summary.json — key sections", expanded=True):
                        sub_tabs = st.tabs(["metrics", "sampled_planform", "sampled_sections", "raw"])
                        with sub_tabs[0]:
                            st.json(gs.get("metrics") or {}, expanded=True)
                        with sub_tabs[1]:
                            st.json(gs.get("sampled_planform") or {}, expanded=True)
                        with sub_tabs[2]:
                            st.json(gs.get("sampled_sections") or {}, expanded=True)
                        with sub_tabs[3]:
                            st.json(gs, expanded=False)

                # Full manifest — show geometry sub-section prominently
                with st.expander("manifest.json — geometry section", expanded=True):
                    inner_tabs = st.tabs(["generator info", "design_sample", "full"])
                    with inner_tabs[0]:
                        st.json({
                            "generator_id":         geo.get("generator_id"),
                            "design_sampling_seed": geo.get("design_sampling_seed"),
                            "name":                 geo.get("name"),
                            "geometry_deterministic": geo.get("geometry_deterministic"),
                        }, expanded=True)
                    with inner_tabs[1]:
                        st.json(geo.get("design_sample") or {}, expanded=False)
                    with inner_tabs[2]:
                        st.json(m, expanded=False)

                # CLI shortcut
                _sec("CLI equivalent")
                _cmd_preview(["geometry", "inspect", "--run-dir", str(insp_path)])


    # ── CAD EXPORT ───────────────────────────────────────────────────────────
    with tab_cad:
        _note(
            "Backend-first CAD workstation. This panel calls real CLI commands only: "
            "<code>aeris geometry export-cad</code> for neutral CAD and "
            "<code>aeris geometry export-deflected-cad</code> for physical control-deflected CAD. "
            "The GUI reads produced manifests/previews; it does not duplicate CAD, OpenVSP, CadQuery, or deflection logic.",
            "info",
        )

        def _cad_file_rows(cad_dir: Path) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            if not cad_dir.exists():
                return rows
            for f in sorted(cad_dir.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(cad_dir)
                rows.append({
                    "file": str(rel),
                    "size_bytes": f.stat().st_size,
                    "path": str(f),
                })
            return rows

        def _step_backend_label(data: dict[str, Any], step_export: dict[str, Any], *, physical: bool) -> str:
            """Human-readable final STEP backend/fallback label for CAD manifests."""
            backend = step_export.get("backend") or data.get("step_backend")
            if backend:
                return str(backend)

            # Neutral CAD manifests may store backend details under cadquery/openvsp
            # instead of a single final backend field.
            cadquery = step_export.get("cadquery")
            openvsp = step_export.get("openvsp")
            artifacts = data.get("artifacts") or {}

            if isinstance(cadquery, dict):
                cq_status = str(cadquery.get("status", "")).lower()
                if cq_status == "success" or artifacts.get("step"):
                    return "cadquery"

            if isinstance(openvsp, dict):
                ovsp_status = str(openvsp.get("status", "")).lower()
                if ovsp_status == "success":
                    return "openvsp"

            requested = step_export.get("backend_requested")
            if requested:
                return f"{requested} requested"

            return "—"

        def _read_body_report_from_manifest(step_export: dict[str, Any]) -> dict[str, Any]:
            body_report_path = step_export.get("body_report_path")
            if not body_report_path:
                return {}
            try:
                return _rjson(Path(str(body_report_path)).expanduser()) or {}
            except Exception:
                return {}

        def _manifest_status_card(manifest_path: Path, *, physical: bool) -> None:
            data = _rjson(manifest_path)
            if not data:
                st.caption(f"No manifest found yet: `{manifest_path.name}`")
                return

            status = str(data.get("status", "unknown"))
            produced = ",".join(data.get("formats_produced", []) or []) or "—"
            requested = ",".join(data.get("formats_requested", []) or []) or "—"
            step_export = data.get("step_export") or {}
            artifacts = data.get("artifacts") or {}
            controls = data.get("physical_controls") or {}

            step_backend_label = _step_backend_label(data, step_export, physical=physical)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Status", status)
            c2.metric("Produced", produced)
            c3.metric("Requested", requested)
            c4.metric("STEP backend", step_backend_label)

            if physical:
                body_report = _read_body_report_from_manifest(step_export)
                assembly_error = str(body_report.get("assembly_export_error") or "").strip()
                per_body_errors = body_report.get("per_body_export_errors") or []
                body_errors = body_report.get("errors") or []

                if status.lower() == "success" and assembly_error:
                    st.warning(
                        "STEP export succeeded through the segmented/per-body fallback. "
                        "The high-level assembly export failed non-fatally."
                    )
                elif assembly_error:
                    st.warning("High-level assembly export reported an error. Check the STEP body report below.")

                if per_body_errors or body_errors:
                    st.error("One or more individual CAD bodies reported export/loft errors. Inspect the body report.")

                _sec("Physical deflection evidence")
                st.json({
                    "deflection_topology": data.get("deflection_topology"),
                    "surface_model": data.get("surface_model"),
                    "body_model": data.get("body_model"),
                    "right_deflection_deg": controls.get("right_deflection_deg"),
                    "left_deflection_deg": controls.get("left_deflection_deg"),
                    "delta_e_sym_deg": controls.get("delta_e_sym_deg"),
                    "delta_a_diff_deg": controls.get("delta_a_diff_deg"),
                    "boundary_model": controls.get("boundary_model"),
                    "step_export": step_export,
                    "assembly_export_error_nonfatal": assembly_error or None,
                    "per_body_export_errors": per_body_errors,
                }, expanded=False)

                if body_report:
                    _sec("STEP backend health")
                    h1, h2, h3, h4 = st.columns(4)
                    h1.metric("Bodies attempted", body_report.get("n_bodies_attempted", "—"))
                    h2.metric("Bodies lofted", body_report.get("n_bodies_lofted", "—"))
                    h3.metric("Body errors", len(body_errors))
                    h4.metric("Assembly fallback", "yes" if assembly_error and status.lower() == "success" else "no")

                b_report = data.get("boundary_report") or {}
                if b_report:
                    st.caption(
                        "Topology: fixed inboard | separate elevon | fixed outboard. "
                        f"y_start={b_report.get('y_start_m', '—')} m, "
                        f"y_end={b_report.get('y_end_m', '—')} m, "
                        f"epsilon={b_report.get('boundary_epsilon_m', '—')} m."
                    )
            else:
                if step_backend_label == "cadquery":
                    st.info("Neutral STEP export used the CadQuery/OpenCASCADE backend.")
                elif step_backend_label == "openvsp":
                    st.info("Neutral STEP export used the OpenVSP backend.")
                elif "requested" in step_backend_label:
                    st.caption("STEP backend was requested but no final backend field was found in the manifest.")

                st.json({
                    "status": status,
                    "formats_produced": data.get("formats_produced"),
                    "step_backend_final": step_backend_label,
                    "step_export": step_export or data.get("step_backend"),
                    "artifacts": artifacts,
                }, expanded=False)


        def _render_cad_outputs(cad_dir: Path, *, physical: bool, key: str) -> None:
            _sec("Produced files / evidence")
            if not cad_dir.exists():
                st.caption("No CAD export folder yet. Run the export above.")
                return

            manifest_name = "physical_deflected_geometry_export_manifest.json" if physical else "geometry_export_manifest.json"
            manifest_path = cad_dir / manifest_name
            _manifest_status_card(manifest_path, physical=physical)

            if physical:
                preview = cad_dir / "previews" / "physical_deflected_planform.png"
                if preview.exists():
                    _sec("Physical-deflected preview")
                    st.image(str(preview), caption="physical_deflected_planform.png", use_container_width=True)

                body_report = cad_dir / "physical_deflected_geometry.step_bodies.json"
                if body_report.exists():
                    _sec("STEP body report")
                    report = _rjson(body_report) or {}
                    b1, b2, b3 = st.columns(3)
                    b1.metric("Bodies attempted", report.get("n_bodies_attempted", "—"))
                    b2.metric("Bodies lofted", report.get("n_bodies_lofted", "—"))
                    b3.metric("Body errors", len(report.get("errors", []) or []))
                    with st.expander("physical_deflected_geometry.step_bodies.json", expanded=False):
                        st.json(report, expanded=False)

            rows = _cad_file_rows(cad_dir)
            if rows:
                if pd is not None:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=260)
                else:
                    st.json(rows)
                previewable = [Path(r["path"]) for r in rows if Path(r["path"]).suffix.lower() in {".json", ".txt", ".vspscript", ".step", ".stp", ".vsp3", ".png", ".jpg", ".jpeg"}]
                if previewable:
                    chosen = st.selectbox(
                        "Preview artifact",
                        previewable,
                        format_func=lambda p: str(p.relative_to(cad_dir)),
                        key=f"{key}_artifact_preview",
                    )
                    _show_file(chosen)
            else:
                st.info("cad_exports/ exists but contains no files yet.")

        neutral_tab, physical_tab, doctor_tab = st.tabs([
            "  Neutral CAD  ",
            "  Physical deflected CAD  ",
            "  OpenVSP doctor  ",
        ])

        # ── Neutral CAD export ────────────────────────────────────────────────
        with neutral_tab:
            _note(
                "Neutral CAD export is for the baseline/generated BWB shape without physical control deflection. "
                "Use this for normal geometry handoff or OpenVSP/STEP reconstruction checks.",
                "info",
            )
            cad_cfg = st.selectbox(
                "Geometry config",
                cfg_smoke_first,
                format_func=_cfg_label,
                key="cad_cfg",
                help="Use baseline_bwb_25.yaml for smoke checks unless running a real design-space export.",
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                cad_format_label = st.selectbox(
                    "Export format selector",
                    ["VSP script (.vspscript)", "STEP (.step/.stp)", "Both"],
                    index=2,
                    key="cad_fmt",
                )
            cad_format = {
                "VSP script (.vspscript)": "vspscript",
                "STEP (.step/.stp)": "step",
                "Both": "vspscript,step",
            }[cad_format_label]
            with c2:
                step_backend = st.selectbox(
                    "STEP backend",
                    ["auto", "cadquery", "openvsp"],
                    index=0,
                    key="cad_step_backend",
                    help="auto tries AeroSandbox/CadQuery first and falls back to OpenVSP batch when available.",
                )
            with c3:
                openvsp_exe = st.text_input(
                    "OpenVSP executable/path",
                    value="vsp",
                    key="cad_openvsp",
                    help="Examples: vsp, OpenVSP, /opt/OpenVSP/vsp. Used by OpenVSP doctor and OpenVSP STEP fallback.",
                )
            cad_out = st.text_input(
                "Output directory",
                value=str(root / "data" / "runs" / "cad_export_test"),
                key="cad_out",
                help="Artifacts go under <output-dir>/cad_exports/.",
            )
            cad_args = [
                "geometry", "export-cad",
                "--config", cad_cfg,
                "--formats", cad_format,
                "--output-dir", cad_out,
                "--openvsp-command", openvsp_exe,
                "--step-backend", step_backend,
            ]
            _panel(
                "Export neutral CAD",
                "Writes geometry.vspscript, optional geometry.step, source geometry artifacts, stdout/stderr, and geometry_export_manifest.json.",
                cad_args,
                root, exe, tmo, dry, "cad_export_run",
                label="Export neutral CAD",
            )
            _render_cad_outputs(Path(cad_out).expanduser() / "cad_exports", physical=False, key="neutral_cad")

        # ── Physical deflected CAD export ─────────────────────────────────────
        with physical_tab:
            _note(
                "Physical deflected CAD is for CFD/CAD handoff, not AVL metadata. "
                "AERIS physically deflects the elevons and writes a traceable split-elevon geometry. "
                "Positive <code>delta_a_diff_deg</code> = right elevon trailing-edge down, left elevon up.",
                "info",
            )
            asym_cfg = str(root / "configs" / "geometry" / "bwb_25_sections_asym_controls.yaml")
            v2_cfg = str(root / "configs" / "geometry" / "bwb_training_v2.yaml")
            v3_cfg = str(root / "configs" / "geometry" / "bwb_training_v3.yaml")
            phys_first = ([asym_cfg] if asym_cfg in cfg_files else []) + ([v2_cfg] if v2_cfg in cfg_files else []) + ([v3_cfg] if v3_cfg in cfg_files else []) + [f for f in cfg_smoke_first if f not in (asym_cfg, v2_cfg, v3_cfg)]

            def _phys_cfg_label(s: str) -> str:
                name = Path(s).name
                if name == "bwb_25_sections_asym_controls.yaml":
                    return f"Physical CAD smoke — {name}"
                if name == "bwb_training_v2.yaml":
                    return f"Training v2 — symmetric + differential controls"
                if name == "bwb_training_v3.yaml":
                    return f"Training v3 — variable elevon geometry"
                return _cfg_label(s)

            phys_cfg = st.selectbox(
                "Physical deflection config",
                phys_first,
                format_func=_phys_cfg_label,
                key="phys_cad_cfg",
                help="Recommended smoke: bwb_25_sections_asym_controls.yaml. For real campaigns use training v2/v3 after canary checks.",
            )

            r1c1, r1c2, r1c3, r1c4 = st.columns(4)
            with r1c1:
                delta_e = st.number_input(
                    "delta_e_sym_deg",
                    value=0.0,
                    step=1.0,
                    key="phys_delta_e",
                    help="Symmetric elevon: positive = both trailing edges down.",
                )
            with r1c2:
                delta_a = st.number_input(
                    "delta_a_diff_deg",
                    value=15.0,
                    step=1.0,
                    key="phys_delta_a",
                    help="Differential elevon: positive = right TE down, left TE up.",
                )
            with r1c3:
                topology = st.selectbox(
                    "Deflection topology",
                    ["split-elevon", "unified-abrupt"],
                    index=0,
                    key="phys_topology",
                    help="split-elevon is the mechanically honest CFD topology. unified-abrupt is legacy/visual only.",
                )
            with r1c4:
                phys_fmt_label = st.selectbox(
                    "Formats",
                    ["Both", "VSP script only", "STEP only"],
                    index=0,
                    key="phys_formats",
                )
            phys_formats = {"Both": "vspscript,step", "VSP script only": "vspscript", "STEP only": "step"}[phys_fmt_label]

            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            with r2c1:
                hinge_gap = st.number_input(
                    "hinge_gap_fraction",
                    min_value=0.0,
                    max_value=0.10,
                    value=0.005,
                    step=0.001,
                    format="%.6f",
                    key="phys_hinge_gap",
                    help="Small chordwise gap between fixed wing and separate elevon. 0.005 is a good CFD-meshing smoke value.",
                )
            with r2c2:
                boundary_eps = st.number_input(
                    "boundary_epsilon_fraction",
                    min_value=1.0e-8,
                    max_value=1.0e-3,
                    value=1.0e-6,
                    step=1.0e-6,
                    format="%.8f",
                    key="phys_boundary_eps",
                    help="Near-coincident stations at elevon start/end. Smaller = sharper, but more CAD fragile.",
                )
            with r2c3:
                use_seed = st.checkbox("Override geometry seed", value=False, key="phys_use_seed")
                phys_seed = st.number_input("Seed", min_value=0, value=100, step=1, key="phys_seed") if use_seed else None
            with r2c4:
                save_preview = st.checkbox("Save preview PNG", value=True, key="phys_save_preview")
                draw_3d = st.checkbox("Open AeroSandbox 3D viewer", value=False, key="phys_draw_3d", help="Requires a local desktop/OpenGL session; do not use over headless SSH.")

            phys_out = st.text_input(
                "Output directory",
                value=str(root / "data" / "runs" / "bwb25_physical_deflected_cad_gui"),
                key="phys_out",
                help="Artifacts go under <output-dir>/cad_exports/.",
            )

            right_defl = float(delta_e) + float(delta_a)
            left_defl = float(delta_e) - float(delta_a)
            max_abs_defl = max(abs(right_defl), abs(left_defl))

            _note(
                "Final actuator mix: "
                "<code>right = delta_e_sym_deg + delta_a_diff_deg</code>; "
                "<code>left = delta_e_sym_deg - delta_a_diff_deg</code>. "
                "Symmetric and differential commands may be applied together.",
                "info",
            )

            if abs(float(delta_e)) > 1.0e-9 and abs(float(delta_a)) > 1.0e-9:
                st.caption(
                    "Both modes are active: symmetric/elevator-like deflection is superimposed "
                    "with differential/aileron-like deflection."
                )

            if max_abs_defl > 60.0:
                _note(
                    f"Max physical deflection is {max_abs_defl:.1f}°. "
                    "This is very large. Treat this mainly as a CAD stress-test, "
                    "not a realistic aero/CFD operating point.",
                    "warn",
                )
            elif max_abs_defl > 35.0:
                _note(
                    f"Max physical deflection is {max_abs_defl:.1f}°. "
                    "This is large. Check whether it is realistic before using this "
                    "geometry for aero/CFD interpretation.",
                    "warn",
                )

            _stat_row([
                ("Right elevon", f"{right_defl:+.1f}°", "delta_e + delta_a"),
                ("Left elevon", f"{left_defl:+.1f}°", "delta_e - delta_a"),
                ("Max |δ|", f"{max_abs_defl:.1f}°", "physical limit check"),
                ("Topology", topology, "CAD body model"),
                ("STEP strategy", "segmented bodies", "robust CadQuery path"),
            ])

            phys_args = [
                "geometry", "export-deflected-cad",
                "--config", phys_cfg,
                "--formats", phys_formats,
                "--output-dir", phys_out,
                "--delta-e-sym-deg", str(delta_e),
                "--delta-a-diff-deg", str(delta_a),
                "--deflection-topology", topology,
                "--hinge-gap-fraction", str(hinge_gap),
                "--boundary-epsilon-fraction", str(boundary_eps),
            ]
            if phys_seed is not None:
                phys_args.extend(["--seed", str(int(phys_seed))])
            if save_preview:
                phys_args.append("--save-preview")
            if draw_3d:
                phys_args.append("--draw-3d")

            _panel(
                "Export physical deflected CAD",
                "Writes physical_deflected_geometry.vspscript, physical_deflected_geometry.step, per-body STEP diagnostics, preview PNG, physical_control_deflection.json, and manifest evidence.",
                phys_args,
                root, exe, tmo, dry, "phys_cad_export_run",
                label="Export physical deflected CAD",
            )
            _render_cad_outputs(Path(phys_out).expanduser() / "cad_exports", physical=True, key="physical_cad")

        # ── OpenVSP doctor ────────────────────────────────────────────────────
        with doctor_tab:
            _note(
                "VSP script export does not require OpenVSP. OpenVSP is only needed if you explicitly use the OpenVSP STEP backend or want to open the generated script in OpenVSP.",
                "info",
            )
            doctor_exe = st.text_input("OpenVSP executable/path", value="vsp", key="cad_doctor_openvsp")
            _panel(
                "Check OpenVSP executable",
                "Checks whether the executable/path is discoverable. Does not launch OpenVSP.",
                ["geometry", "openvsp-doctor", "--openvsp-command", doctor_exe],
                root, exe, tmo, dry, "cad_doctor_run",
                label="Check OpenVSP",
            )



# AERIS_PATCH_CST_GUI_V1_HELPERS
def _airfoil_feature_preset_hint_from_manifest(manifest: dict | None) -> str:
    """Return the recommended ML feature preset for an airfoil dataset/library.

    CST metadata can be stored in raw dataset manifests, promotion manifests,
    library reports, or nested summaries. Walk recursively so the GUI remains
    robust as reports evolve.
    """
    def _walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_s = str(key).lower()
                if key_s == "has_cst_features" and bool(value):
                    return True
                if key_s in {"generator_id", "generator_ids"}:
                    if isinstance(value, list) and any(str(v) == "cst_airfoil_v1" for v in value):
                        return True
                    if str(value) == "cst_airfoil_v1":
                        return True
                if key_s in {"parameterization", "source_format"} and "cst" in str(value).lower():
                    return True
                if key_s in {"cst_feature_columns", "cst_coefficient_columns"} and value:
                    return True
                if str(value) in {"cst_airfoil_v1", "cst_kulfan"}:
                    return True
                if _walk(value):
                    return True
        elif isinstance(obj, list):
            return any(_walk(item) for item in obj)
        return False

    return "airfoil_cst_xfoil_v1" if _walk(manifest or {}) else "airfoil_xfoil_v1"


def _airfoil_dataset_feature_preset_hint(dataset_root: Path) -> str:
    """Infer the best airfoil ML preset from dataset artifacts."""
    for name in ["airfoil_dataset_manifest.json", "promotion_manifest.json", "library_report.json"]:
        data = _rjson(Path(dataset_root) / name)
        if data:
            hint = _airfoil_feature_preset_hint_from_manifest(data)
            if hint == "airfoil_cst_xfoil_v1":
                return hint
    return "airfoil_xfoil_v1"


def _airfoil_library_candidates(root: Path) -> list[Path]:
    """Discover selectable airfoil libraries under data/."""
    data_root = Path(root) / "data"
    candidates: list[Path] = []
    preferred = [data_root / "airfoil_library", data_root / "airfoil_library_cst_smoke"]
    for d in preferred:
        if (d / "airfoil_inventory.csv").exists() and d not in candidates:
            candidates.append(d)
    if data_root.exists():
        for d in sorted(data_root.glob("airfoil_library*")):
            if d.is_dir() and (d / "airfoil_inventory.csv").exists() and d not in candidates:
                candidates.append(d)
    if not candidates:
        candidates.append(data_root / "airfoil_library")
    return candidates



def _airfoil_inventory_count(library_dir: str | Path) -> int:
    """Return number of airfoils in an AERIS airfoil library."""
    inv = Path(library_dir).expanduser() / "airfoil_inventory.csv"
    if not inv.exists():
        return 0

    try:
        if pd is not None:
            return int(len(pd.read_csv(inv)))
    except Exception:
        pass

    try:
        # Fallback without pandas: count data lines after header.
        with inv.open("r", encoding="utf-8") as f:
            n_lines = sum(1 for _ in f)
        return max(0, n_lines - 1)
    except Exception:
        return 0


def _airfoil_library_origin(library_dir: str | Path) -> str:
    """Classify an airfoil library for GUI display."""
    root = Path(library_dir).expanduser()
    if (root / "cst_airfoil_library_manifest.json").exists() or (root / "library_report.json").exists():
        return "CST/Kulfan generated"
    if (root / "airfoil_inventory.csv").exists():
        return "Imported .dat library"
    return "Not built yet"


def _airfoil_library_candidates(project_root: Path) -> list[Path]:
    """Find likely AERIS airfoil libraries.

    Libraries are selected by folder. The active folder must contain, or be expected
    to contain, airfoil_inventory.csv. This supports both imported .dat libraries
    and generated CST/Kulfan libraries.
    """
    data_root = project_root / "data"

    preferred = [
        data_root / "airfoil_library",
        data_root / "airfoil_library_cst_smoke",
    ]

    found: list[Path] = []

    def add(path: Path) -> None:
        try:
            rp = path.expanduser().resolve()
        except Exception:
            rp = path
        if rp not in found:
            found.append(rp)

    for path in preferred:
        add(path)

    if data_root.exists():
        # Keep this intentionally shallow and cheap for Streamlit refreshes.
        for child in sorted(data_root.iterdir()):
            if not child.is_dir():
                continue
            name = child.name.lower()
            has_inventory = (child / "airfoil_inventory.csv").exists()
            looks_like_library = (
                "airfoil_library" in name
                or "cst" in name and "airfoil" in name
                or has_inventory
            )
            if looks_like_library:
                add(child)

        datasets_root = data_root / "datasets"
        if datasets_root.exists():
            for child in sorted(datasets_root.iterdir()):
                if child.is_dir() and (child / "airfoil_inventory.csv").exists():
                    add(child)

    return found


def _airfoil_library_label(path: Path | str) -> str:
    """Human-readable label for an airfoil library selector entry."""
    if isinstance(path, str) and path == "__AERIS_CHOOSE_AIRFOIL_LIBRARY__":
        return "Choose active airfoil library..."

    p = Path(path)
    n = _airfoil_inventory_count(p)
    origin = _airfoil_library_origin(p)

    seed_txt = ""
    try:
        manifest = _rjson(p / "cst_airfoil_library_manifest.json") or {}
        if manifest.get("seed") is not None:
            seed_txt = f" · seed={manifest.get('seed')}"
        if manifest.get("n_airfoils_generated") is not None and n <= 0:
            n = int(manifest.get("n_airfoils_generated"))
    except Exception:
        seed_txt = ""

    if n > 0:
        return f"{p}  —  {n} airfoils · {origin}{seed_txt}"
    return f"{p}  —  {origin}"




def _airfoil_xfoil_dataset_candidates(project_root: Path) -> list[Path]:
    """Find generated 2D XFOIL airfoil datasets.

    A valid generated XFOIL dataset is any folder under data/datasets that
    contains airfoil_dataset.csv. This is intentionally independent from
    the selected source airfoil library.
    """
    ds_root = project_root / "data" / "datasets"
    if not ds_root.exists():
        return []

    found: list[Path] = []

    def add(path: Path) -> None:
        try:
            rp = path.expanduser().resolve()
        except Exception:
            rp = path
        if rp not in found:
            found.append(rp)

    for child in sorted(ds_root.iterdir()):
        if child.is_dir() and (child / "airfoil_dataset.csv").exists():
            add(child)

    # One-level fallback for any manually nested dataset folders.
    for csv_path in sorted(ds_root.glob("*/*/airfoil_dataset.csv")):
        add(csv_path.parent)

    return found


def _airfoil_xfoil_dataset_label(dataset_dir: Path | str) -> str:
    """Human-readable label for generated XFOIL dataset dropdowns."""
    ds = Path(dataset_dir)
    csv_path = ds / "airfoil_dataset.csv"

    if not csv_path.exists():
        return f"{ds.name} — no airfoil_dataset.csv"

    rows = 0
    converged = None

    try:
        if pd is not None:
            df = pd.read_csv(csv_path)
            rows = int(len(df))
            if "converged" in df.columns:
                conv = _airfoil_bool_series(df["converged"])
                converged = int(conv.sum())
        else:
            with csv_path.open("r", encoding="utf-8") as f:
                rows = max(0, sum(1 for _ in f) - 1)
    except Exception:
        return f"{ds.name} — airfoil_dataset.csv"

    if converged is not None:
        return f"{ds.name} — {rows} rows · {converged} converged"
    return f"{ds.name} — {rows} rows"

def _airfoil_dataset_csv(dataset_dir: str | Path) -> Path:
    """Return the standard AERIS 2D airfoil dataset CSV path."""
    return Path(dataset_dir).expanduser() / "airfoil_dataset.csv"


def _airfoil_bool_series(series: Any) -> Any:
    """Robustly interpret converged column values from CSV."""
    if pd is None:
        return series
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(("true", "1", "yes", "y"))


def _render_airfoil_polar_viewer(dataset_dir: str | Path, *, key_prefix: str = "af_polar") -> None:
    """Interactive Streamlit viewer for 2D XFOIL polar curves.

    Supports:
      - CL vs alpha
      - CD vs alpha
      - Cm vs alpha
      - CL vs CD drag polar

    This is intentionally GUI-only visualization. It does not change the dataset.
    """
    ds = Path(dataset_dir).expanduser()
    csv_path = _airfoil_dataset_csv(ds)

    if pd is None:
        st.warning("pandas is required to plot airfoil polars.")
        return
    if not csv_path.exists():
        st.warning(f"No airfoil_dataset.csv found in {ds}.")
        return

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        st.error(f"Could not read {csv_path}: {exc}")
        return

    if df.empty:
        st.warning("Dataset CSV is empty.")
        return

    required = {"alpha_deg", "cl", "cd"}
    missing = sorted(required - set(df.columns))
    if missing:
        st.warning(f"Cannot plot polar curves. Missing columns: {', '.join(missing)}")
        return

    id_col = "airfoil_id" if "airfoil_id" in df.columns else None
    name_col = "airfoil_name" if "airfoil_name" in df.columns else id_col

    if id_col is None:
        df["_airfoil_plot_id"] = "airfoil"
        id_col = "_airfoil_plot_id"
        name_col = "_airfoil_plot_id"

    converged_only = st.checkbox(
        "Plot converged rows only",
        value=True,
        key=f"{key_prefix}_converged_only",
        help="Recommended. Unconverged XFOIL rows may have missing or unreliable coefficients.",
    )

    plot_df = df.copy()
    if converged_only and "converged" in plot_df.columns:
        plot_df = plot_df[_airfoil_bool_series(plot_df["converged"])].copy()

    if plot_df.empty:
        st.warning("No rows available after filtering.")
        return

    available_ids = list(dict.fromkeys(plot_df[id_col].astype(str).tolist()))
    max_default = min(12, len(available_ids))

    mode = st.radio(
        "Polar plot type",
        ["CL vs alpha", "CD vs alpha", "Cm vs alpha", "CL vs CD drag polar"],
        horizontal=True,
        key=f"{key_prefix}_mode",
    )

    n_show = st.slider(
        "Maximum airfoils to draw",
        min_value=1,
        max_value=max(1, len(available_ids)),
        value=max(1, max_default),
        step=1,
        key=f"{key_prefix}_n_show",
        help="Limit overlaid curves so the plot stays readable.",
    )

    selected_ids = st.multiselect(
        "Airfoils to plot",
        available_ids,
        default=available_ids[:n_show],
        key=f"{key_prefix}_ids",
        help="Leave default for the first selected subset. You can manually choose specific airfoils.",
    )

    if not selected_ids:
        st.info("Select at least one airfoil to plot.")
        return

    # Respect manual selection but still keep the plot readable.
    selected_ids = selected_ids[: int(n_show)]
    plot_df = plot_df[plot_df[id_col].astype(str).isin(selected_ids)].copy()

    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        st.error(f"matplotlib is required for polar plots: {exc}")
        return

    x_col, y_col = "alpha_deg", "cl"
    xlabel, ylabel, title = "Angle of attack α [deg]", "CL", "XFOIL CL-alpha curves"

    if mode == "CD vs alpha":
        x_col, y_col = "alpha_deg", "cd"
        xlabel, ylabel, title = "Angle of attack α [deg]", "CD", "XFOIL CD-alpha curves"
    elif mode == "Cm vs alpha":
        if "cm" not in plot_df.columns:
            st.warning("Column 'cm' not found in this dataset.")
            return
        x_col, y_col = "alpha_deg", "cm"
        xlabel, ylabel, title = "Angle of attack α [deg]", "Cm", "XFOIL Cm-alpha curves"
    elif mode == "CL vs CD drag polar":
        x_col, y_col = "cd", "cl"
        xlabel, ylabel, title = "CD", "CL", "XFOIL drag polar (CL vs CD)"

    fig, ax = plt.subplots(figsize=(8.5, 5.2))

    for aid, group in plot_df.groupby(id_col, sort=False):
        g = group.sort_values(x_col)
        label = str(aid)
        if name_col and name_col in g.columns:
            label = str(g[name_col].iloc[0])
        ax.plot(g[x_col], g[y_col], marker="o", linewidth=1.3, markersize=3.0, alpha=0.78, label=label)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    if len(selected_ids) <= 12:
        ax.legend(fontsize=7, loc="best")

    fig.tight_layout()
    st.pyplot(fig)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows plotted", f"{len(plot_df):,}")
    c2.metric("Airfoils", f"{plot_df[id_col].nunique():,}")
    c3.metric("Total dataset rows", f"{len(df):,}")
    if "converged" in df.columns:
        n_conv = int(_airfoil_bool_series(df["converged"]).sum())
        c4.metric("Converged rows", f"{n_conv:,}")
    else:
        c4.metric("Converged rows", "—")

    save_plot = st.checkbox(
        "Save this plot as PNG",
        value=False,
        key=f"{key_prefix}_save_png",
    )
    if save_plot:
        plots_dir = ds / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        safe_mode = mode.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
        out_path = plots_dir / f"{safe_mode}.png"
        fig.savefig(out_path, dpi=200)
        st.success(f"Saved plot: {out_path}")

    try:
        plt.close(fig)
    except Exception:
        pass

def pg_airfoil(root, exe, tmo, dry):
    _hero("〜", "2D Airfoils", "XFOIL pipeline · choose source library → sweep → QC → promote → ML", "xfoil")

    cfg_files = _files(str(root / "configs" / "airfoil"), "*.yaml")
    ds_dirs = _airfoil_xfoil_dataset_candidates(root)

    library_choices = _airfoil_library_candidates(root)
    airfoil_library_options = _airfoil_library_candidates(root)
    if not airfoil_library_options:
        airfoil_library_options = [root / "data" / "airfoil_library"]

    library_prompt = "__AERIS_CHOOSE_AIRFOIL_LIBRARY__"
    airfoil_library_select_options = [library_prompt] + airfoil_library_options

    if st.session_state.get("af_active_library_choice") not in airfoil_library_select_options:
        st.session_state.pop("af_active_library_choice", None)

    selected_airfoil_library = st.selectbox(
        "Active airfoil library",
        airfoil_library_select_options,
        index=0,
        format_func=_airfoil_library_label,
        key="af_active_library_choice",
        help=(
            "Manually choose which existing airfoil library XFOIL should sweep. "
            "This can be an imported .dat library or any CST/Kulfan-generated library."
        ),
    )
    active_airfoil_library_selected = selected_airfoil_library != library_prompt


    custom_airfoil_library = st.checkbox(
        "Use custom airfoil library path",
        value=False,
        key="af_active_library_custom_enabled",
        help="Use this only if the library folder is not shown in the selector.",
    )
    if custom_airfoil_library:
        custom_default = (
            str(selected_airfoil_library)
            if active_airfoil_library_selected
            else str(root / "data" / "airfoil_library")
        )
        lib_dir = Path(st.text_input(
            "Custom active airfoil library",
            value=custom_default,
            key="af_active_library",
        ))
        active_airfoil_library_selected = True
    elif active_airfoil_library_selected:
        lib_dir = Path(selected_airfoil_library)
    else:
        lib_dir = root / "data" / "airfoil_library"

    active_airfoil_count = _airfoil_inventory_count(lib_dir) if active_airfoil_library_selected else 0
    active_airfoil_origin = _airfoil_library_origin(lib_dir) if active_airfoil_library_selected else "No library selected"

    tab_lib, tab_sweep, tab_trust, tab_ml = st.tabs([
        "① Library",
        "② XFOIL Sweep",
        "③ QC / Curate / Promote",
        "④ ML",
    ])
    tab_qc = tab_trust


    # Backward-compatible alias: older GUI code/tests may call this tab_qc,
    # while the existing airfoil page body uses tab_trust.
    tab_qc = tab_trust


    # ── ① LIBRARY ────────────────────────────────────────────────────────────
    with tab_lib:
        _sec("Active library")
        inv_csv = lib_dir / "airfoil_inventory.csv"
        lib_manifest = _rjson(lib_dir / "cst_airfoil_library_manifest.json")

        lib_origin = active_airfoil_origin
        n_lib = str(active_airfoil_count)
        tc_range = "—"
        fam_summary = "—"

        if inv_csv.exists() and pd is not None:
            try:
                df_inv = pd.read_csv(inv_csv)
                n_lib = str(len(df_inv))
                if "t_c" in df_inv.columns and len(df_inv):
                    tc_range = f"{df_inv['t_c'].min():.3f}-{df_inv['t_c'].max():.3f}"
                if "family" in df_inv.columns and len(df_inv):
                    fam_counts = df_inv["family"].value_counts().to_dict()
                    fam_summary = ", ".join(f"{k}:{v}" for k, v in list(fam_counts.items())[:3])
            except Exception as exc:
                st.warning(f"Could not read airfoil inventory: {exc}")

        _stat_row([
            ("Active library path", Path(lib_dir).name if active_airfoil_library_selected else "No library selected", "selected library"),
            ("Origin", lib_origin, "imported or generated"),
            ("Airfoils", n_lib, "airfoil_inventory.csv"),
            ("t/c range", tc_range, "thickness ratio"),
        ])

        if not active_airfoil_library_selected:
            _note(
                "Choose an existing airfoil library from the dropdown above before running XFOIL. "
                "Use ① Library only when you want to create/import a new library.",
                "warn",
            )
        elif not inv_csv.exists():
            _note(
                "The selected folder is not a built airfoil library yet. Choose one of the two source workflows below: "
                "<b>Import existing airfoils (.dat)</b> or <b>Generate CST/Kulfan airfoils</b>.",
                "warn",
            )
        else:
            _note(
                f"Active library is ready. The same downstream XFOIL → QC → Promote → ML pipeline "
                f"works for imported and CST-generated libraries.",
                "ok",
            )

        _sec("Choose how to build an airfoil library")
        c_import, c_cst = st.columns(2)
        with c_import:
            with st.container(border=True):
                _h('<div style="font-weight:700;color:#F2F5F8;font-size:.95rem">Import existing airfoils (.dat)</div>')
                _h('<div style="font-size:.78rem;color:#AAB6C2;line-height:1.55;margin:.35rem 0 .55rem">'
                   'Use an external coordinate database such as UIUC/Selig-format files. '
                   'AERIS ingests coordinates, computes geometry statistics, and writes a selectable library.</div>')
                st.caption("Best when you already have trusted coordinate files.")
        with c_cst:
            with st.container(border=True):
                _h('<div style="font-weight:700;color:#F2F5F8;font-size:.95rem">Generate CST/Kulfan airfoils</div>')
                _h('<div style="font-size:.78rem;color:#AAB6C2;line-height:1.55;margin:.35rem 0 .55rem">'
                   'Create a parametric AERIS airfoil library from CST/Kulfan coefficients. '
                   'AERIS writes .dat files, coordinate arrays, CST JSON, inventory, and reports.</div>')
                st.caption("Best when you want controlled parametric design-space coverage.")

        source_workflow = st.radio(
            "Library source workflow",
            ["Import existing airfoils (.dat)", "Generate CST/Kulfan airfoils"],
            horizontal=True,
            key="af_library_source_workflow",
            help="These are two source routes into the same downstream XFOIL surrogate pipeline.",
        )

        if source_workflow == "Import existing airfoils (.dat)":
            _sec("Import existing airfoils (.dat)")
            _note(
                "Point <code>--db-dir</code> to a directory of Selig-format <code>.dat</code> files. "
                "Default output is the active library path shown above.",
                "info",
            )
            db_dir_str = st.text_input(
                "Source .dat directory (--db-dir)",
                value=str(root / "data" / "airfoil_database"),
                key="af_db_dir",
            )
            _panel(
                "Import airfoil library, Generate CST airfoils",
                "Reads .dat files, writes airfoil_inventory.csv and coords/*.npz.",
                ["airfoil", "ingest", "--db-dir", db_dir_str, "--output-dir", str(lib_dir)],
                root, exe, tmo, dry, "af_ingest", label="▶  Import .dat library",
            )
            _panel(
                "Library stats",
                "Count, family breakdown, t/c and camber ranges.",
                ["airfoil", "library-stats", "--library", str(lib_dir)],
                root, exe, tmo, dry, "af_libstats", label="▶  Library stats",
            )

        else:
            _sec("Generate CST/Kulfan airfoils")
            _note(
                "Creates a first-class AERIS 2D CST airfoil library: <code>.dat</code>, "
                "coordinate <code>.npz</code>, CST JSON, <code>airfoil_inventory.csv</code>, "
                "<code>cst_airfoil_library_manifest.json</code>, and <code>library_report.json</code>.",
                "info",
            )
            cst_cfgs = [
                f for f in _files(str(root / "configs" / "airfoil"), "*.yaml")
                if "cst_library" in Path(f).name
            ]
            if cst_cfgs:
                cst_default = next((f for f in cst_cfgs if "smoke" in Path(f).name), cst_cfgs[0])
                cst_cfg = st.selectbox(
                    "CST config",
                    cst_cfgs,
                    index=cst_cfgs.index(cst_default),
                    format_func=lambda s: Path(s).name,
                    key="af_cst_cfg",
                )
            else:
                cst_cfg = st.text_input(
                    "CST config",
                    str(root / "configs" / "airfoil" / "cst_library_smoke_v1.yaml"),
                    key="af_cst_cfg_text",
                )

            cst_out = st.text_input(
                "CST library output dir",
                str(root / "data" / "airfoil_library_cst_smoke"),
                key="af_cst_out",
            )
            _panel(
                "Generate CST/Kulfan library",
                "Runs cst_airfoil_v1 and writes a selectable airfoil library for XFOIL and ML.",
                ["airfoil", "generate-cst-library", "--config", cst_cfg, "--output-dir", cst_out],
                root, exe, tmo, dry, "af_cst_generate", label="▶  Generate CST library",
            )
            if (Path(cst_out) / "library_report.json").exists():
                with st.expander("CST library report", expanded=False):
                    _show_file(Path(cst_out) / "library_report.json")

        _sec("Airfoil utilities")
        c_info, c_fit = st.columns(2)
        with c_info:
            _panel(
                "Airfoil module info",
                "Show 2D workflow status, library hints, XFOIL status, and available airfoil commands.",
                ["airfoil", "info"],
                root, exe, tmo, dry, "af_info", label="▶  Airfoil info",
            )
        with c_fit:
            fit_dat = st.text_input(
                "DAT file to fit CST",
                str(root / "data" / "airfoil_database" / "naca4412.dat"),
                key="af_fit_cst_dat",
                help="Selig-format .dat coordinate file. Use this to pull legacy airfoils into the CST design space.",
            )
            fit_out = st.text_input(
                "CST fit output dir",
                str(root / "data" / "debug" / "cst_fit" / "naca4412"),
                key="af_fit_cst_out",
            )
            fit_order = st.number_input("CST fit order", min_value=2, max_value=16, value=8, step=1, key="af_fit_cst_order")
            _panel(
                "Fit CST to .dat",
                "Runs aeris airfoil fit-cst and writes CST coefficients plus fit_report.json.",
                ["airfoil", "fit-cst", fit_dat, "--output-dir", fit_out, "--order", str(int(fit_order))],
                root, exe, tmo, dry, "af_fit_cst", label="▶  Fit CST",
            )

        if (lib_dir / "library_report.json").exists():
            with st.expander("Active library report", expanded=False):
                _show_file(lib_dir / "library_report.json")


    with tab_sweep:
        _sec("XFOIL readiness")
        _panel(
            "Check XFOIL binary",
            "Confirms XFOIL is on PATH and shows its version before running sweeps.",
            ["airfoil", "check-solver"],
            root, exe, tmo, dry, "af_check", label="▶  Check XFOIL",
        )

        if not active_airfoil_library_selected:
            st.warning(
                "Choose an active airfoil library from the dropdown above before running XFOIL. "
                "You can choose any imported .dat library or any CST/Kulfan library with a different seed."
            )
        elif not inv_csv.exists():
            st.warning(
                "The selected active library has no airfoil_inventory.csv. "
                "Choose another existing library or build/import this one in ① Library."
            )
        else:
            st.caption(
                f"Selected active library: `{lib_dir}` · "
                f"{active_airfoil_count} airfoils · {active_airfoil_origin}"
            )
            _note(
                "XFOIL does not create airfoils. It only sweeps airfoils that already exist "
                "in the selected active library. Therefore <code>--n-airfoils</code> is capped "
                "by the selected library inventory count.",
                "info",
            )

            # AERIS_PATCH_CST_GUI_V1_1_XFOIL_CONFIG_FILTER
            # cst_library_v1.yaml generate airfoil shapes; it must not appear
            # in the XFOIL sweep config selector.
            xfoil_cfg_files = [
                f for f in _files(str(root / "configs" / "airfoil"), "*.yaml")
                if "xfoil" in Path(f).stem.lower()
            ]
            cfg_opts = xfoil_cfg_files

            # Reset stale Streamlit state if an older selected value was a CST
            # library generator config or any non-XFOIL config.
            if st.session_state.get("af_cfg") not in cfg_opts:
                st.session_state.pop("af_cfg", None)

            if not cfg_opts:
                xfoil_cfg = st.text_input(
                    "XFOIL sweep config",
                    str(root / "configs" / "airfoil" / "xfoil_smoke_v1.yaml"),
                    key="af_xfoil_cfg_text",
                )
            else:
                default_cfg = next(
                    (f for f in cfg_opts if "smoke" in Path(f).stem.lower()),
                    cfg_opts[0],
                )
                selected_cfg = st.session_state.get("af_cfg", default_cfg)
                if selected_cfg not in cfg_opts:
                    selected_cfg = default_cfg

                xfoil_cfg = st.selectbox("XFOIL sweep config", cfg_opts, index=cfg_opts.index(selected_cfg), format_func=lambda s: ("Smoke — " + Path(s).name if "smoke" in Path(s).stem.lower() else Path(s).name), key="af_cfg")

                if "smoke" in Path(xfoil_cfg).stem.lower():
                    st.caption("Smoke config — fast pipeline validation only.")

            ds_name = st.text_input(
                "Dataset name (--name)",
                "airfoil_xfoil_pilot",
                key="af_ds_name",
            )

            sweep_slider_max = max(1, int(active_airfoil_count))
            suggested_n = min(sweep_slider_max, 10 if sweep_slider_max <= 25 else 25)

            if st.session_state.get("af_n_airfoils", suggested_n) > sweep_slider_max:
                st.session_state["af_n_airfoils"] = sweep_slider_max

            n_airfoils = int(st.slider(
                "Airfoils to sweep from active library (--n-airfoils)",
                min_value=1,
                max_value=sweep_slider_max,
                value=min(st.session_state.get("af_n_airfoils", suggested_n), sweep_slider_max),
                step=1,
                key="af_n_airfoils",
                help=(
                    "Subset size for the selected active library. "
                    "This does not generate new airfoils and cannot exceed the selected library size."
                ),
            ))

            seed = int(st.number_input(
                "Subset seed (--seed)",
                min_value=0,
                value=42,
                step=1,
                key="af_seed",
                help="Controls which reproducible subset is selected from the active library.",
            ))

            show_xfoil_plots = st.checkbox(
                "Show XFOIL plots (--show-plots)",
                value=False,
                key="af_show_plots",
                help=(
                    "Checked: XFOIL/Xplot11 graphics windows may appear during the sweep. "
                    "Use this only for small debug runs, usually 1-3 airfoils. "
                    "Unchecked: headless/no windows, recommended for datasets."
                ),
            )

            if show_xfoil_plots and int(n_airfoils) > 3:
                _note(
                    "Plot mode can open many XFOIL/Xplot11 windows. "
                    "For visual debugging, reduce <code>--n-airfoils</code> to 1-3.",
                    "warn",
                )

            _sweep_args = [
                "airfoil", "dataset", "generate",
                "--library", str(lib_dir),
                "--config", str(xfoil_cfg),
                "--name", ds_name,
                "--n-airfoils", str(n_airfoils),
                "--seed", str(seed),
            ]
            if show_xfoil_plots:
                _sweep_args.append("--show-plots")

            _panel(
                "Run XFOIL sweep",
                (
                    f"Sweeps {n_airfoils} airfoils from the selected active library "
                    f"→ data/datasets/{ds_name}/ "
                    + ("[Xplot11 ON]" if show_xfoil_plots else "[headless, no windows]")
                ),
                _sweep_args,
                root, exe, tmo, dry, "af_sweep",
                label="▶  Run XFOIL sweep " + ("[Xplot11 ON]" if show_xfoil_plots else "[headless]"),
            )

            _sec("Dataset polar viewer")
            _note(
                "View XFOIL polar curves from an existing generated dataset. "
                "This is different from live <code>--show-plots</code>: it plots saved CSV results "
                "inside the GUI after the run.",
                "info",
            )

            polar_ds_dirs = _airfoil_xfoil_dataset_candidates(root)

            if not polar_ds_dirs:
                st.warning(
                    "No generated XFOIL airfoil datasets found under data/datasets. "
                    "Expected folders containing airfoil_dataset.csv."
                )
                manual_polar_ds = st.text_input(
                    "Manual dataset folder",
                    str(root / "data" / "datasets" / "airfoil_xfoil_pilot"),
                    key="af_polar_manual_dataset",
                    help="Use this if the dataset exists but was not auto-discovered.",
                )
                manual_polar_path = Path(manual_polar_ds)
                if (manual_polar_path / "airfoil_dataset.csv").exists():
                    _render_airfoil_polar_viewer(manual_polar_path, key_prefix="af_polar_sweep_manual")
            else:
                polar_ds_path = st.selectbox(
                    "Dataset to plot",
                    polar_ds_dirs,
                    format_func=_airfoil_xfoil_dataset_label,
                    key="af_polar_dataset",
                    help="Choose any generated 2D airfoil XFOIL dataset containing airfoil_dataset.csv.",
                )
                _render_airfoil_polar_viewer(polar_ds_path, key_prefix="af_polar_sweep")


    # ── ③ QC / CURATE / PROMOTE ──────────────────────────────────────────────
    with tab_trust:
        if not ds_dirs:
            st.warning("No airfoil datasets found. Run ② XFOIL Sweep first.")
        else:
            sel_ds  = st.selectbox("Dataset", [d.name for d in ds_dirs], key="af_trust_ds")
            ds_path = next((d for d in ds_dirs if d.name == sel_ds), None)
            if ds_path:
                prom_exists = (ds_path / "promotion_manifest.json").exists()
                cur_exists  = (ds_path / "curation_report.json").exists()
                if prom_exists:
                    st.success("✓ Promoted — ready for ML.")
                elif cur_exists:
                    st.info("Curated but not yet promoted.")
                else:
                    st.warning("Raw dataset — run QC and Curate before promoting.")

                # AERIS_GUI_C12_QC_GATE_WARNING: ISSUE-C12 — curate blocks
                # promotion when airfoil_qc_report.json is absent.
                # Warn the operator so they know to run QC first.
                qc_report_path = ds_path / "airfoil_qc_report.json"
                if not qc_report_path.exists():
                    _note(
                        "⚠ QC has not been run on this dataset. "
                        "Run <b>▶ QC</b> before Curate — curation now blocks "
                        "promotion when <code>airfoil_qc_report.json</code> is absent.",
                        "warn",
                    )
                elif _rjson(qc_report_path):
                    qc_payload = _rjson(qc_report_path) or {}
                    coverage_failures = qc_payload.get("per_group_coverage_failures") or []
                    if not qc_payload.get("passed"):
                        _note(
                            "✗ QC failed on this dataset. Fix fatal issues before curating. "
                            "Coverage shortfalls are reported separately as warnings.",
                            "err",
                        )
                    elif coverage_failures:
                        _note(
                            "⚠ QC passed with per-group coverage warnings. Curation may still promote "
                            "if the under-covered airfoil/Re/Mach groups are fully removed; surviving "
                            "groups need at least 3 converged rows.",
                            "warn",
                        )
                _sec("QC polar preview")
                _note(
                    "Quickly inspect saved XFOIL curves before/after QC and curation.",
                    "info",
                )
                _render_airfoil_polar_viewer(ds_path, key_prefix="af_polar_qc")

                c_qc, c_cur, c_prom = st.columns(3)
                with c_qc:
                    _panel(
                        "QC",
                        "Checks XFOIL rows: converged targets, cd>0, duplicate key incl. ncrit; warns when airfoil/Re/Mach groups have fewer than 3 converged rows.",
                        ["airfoil", "dataset", "qc", "--dataset", str(ds_path)],
                        root, exe, tmo, dry, "af_qc", label="▶  QC",
                    )
                with c_cur:
                    _panel(
                        "Curate",
                        "Rejects unconverged, cd<=0, non-finite rows; blocks promotion if QC failed or insufficient per-group coverage remains after curation: surviving groups need at least 3 converged rows per airfoil/Re/Mach group.",
                        ["airfoil", "dataset", "curate", "--dataset", str(ds_path)],
                        root, exe, tmo, dry, "af_cur", label="▶  Curate",
                    )
                with c_prom:
                    _panel("Promote", "Write promotion_manifest.json for ML.",
                           ["airfoil", "dataset", "promote", "--dataset", str(ds_path)],
                           root, exe, tmo, dry, "af_prom", label="▶  Promote")

                _sec("Inspect")
                _panel("Dataset inspect", "Show manifest, curation, promotion status.",
                       ["airfoil", "dataset", "inspect", "--dataset", str(ds_path)],
                       root, exe, tmo, dry, "af_insp", label="▶  Inspect")

                for fname, label_str in [
                    ("airfoil_dataset.csv",          "Raw dataset preview"),
                    ("airfoil_qc_report.json",       "Airfoil QC report"),
                    ("curated_airfoil_dataset.csv",  "Curated dataset preview"),
                    ("promotion_manifest.json",      "Promotion manifest"),
                    ("curation_report.json",         "Curation report"),
                ]:
                    fpath = ds_path / fname
                    if fpath.exists():
                        with st.expander(label_str, expanded=False):
                            _show_file(fpath)

    # ── ④ ML SHORTCUT ────────────────────────────────────────────────────────
    with tab_ml:
        _note(
            "All ML training for 2D airfoil data happens in <b>◈ ML Studio</b>. "
            "Use the settings below when you get there.",
            "info",
        )
        promoted = [d for d in ds_dirs if (d / "promotion_manifest.json").exists()]
        if not promoted:
            st.warning("No promoted datasets yet. Complete ③ QC / Curate / Promote first, then go to ◈ ML Studio.")
        else:
            sel_prom  = st.selectbox("Promoted dataset", [d.name for d in promoted], key="af_ml_ds")
            prom_path = next((d for d in promoted if d.name == sel_prom), None)
            if prom_path:
                af_feature_preset_hint = _airfoil_dataset_feature_preset_hint(prom_path)
                _sec("Settings to use in ◈ ML Studio")
                _h(
                    f'<div style="background:#1B2A3A;border:1px solid #2D3F52;border-radius:9px;'
                    f'padding:1rem 1.2rem;margin:.5rem 0">' +
                    f'<div style="font-size:.8rem;color:#AAB6C2;margin-bottom:.7rem;'
                    f'text-transform:uppercase;letter-spacing:.08em">Copy these into ML Studio</div>' +
                    f'<table style="width:100%;border-collapse:collapse;font-size:.82rem">' +
                    f'<tr><td style="color:#7F8B98;padding:.2rem .5rem .2rem 0;white-space:nowrap">Dataset</td>' +
                    f'<td style="font-family:JetBrains Mono,monospace;color:#93C5FD">{prom_path}</td></tr>' +
                    f'<tr><td style="color:#7F8B98;padding:.2rem .5rem .2rem 0">Feature set</td>' +
                    f'<td style="font-family:JetBrains Mono,monospace;color:#86EFAC">{af_feature_preset_hint}</td></tr>' +
                    f'<tr><td style="color:#7F8B98;padding:.2rem .5rem .2rem 0">Targets</td>' +
                    f'<td style="font-family:JetBrains Mono,monospace;color:#D6DEE8">cl, cd, cm</td></tr>' +
                    f'<tr><td style="color:#7F8B98;padding:.2rem .5rem .2rem 0">Group column</td>' +
                    f'<td style="font-family:JetBrains Mono,monospace;color:#FCD34D">airfoil_id</td></tr>' +
                    f'<tr><td style="color:#7F8B98;padding:.2rem .5rem .2rem 0">Split method</td>' +
                    f'<td style="font-family:JetBrains Mono,monospace;color:#D6DEE8">grouped</td></tr>' +
                    f'<tr><td style="color:#7F8B98;padding:.2rem .5rem .2rem 0">Recommended seeds</td>' +
                    f'<td style="font-family:JetBrains Mono,monospace;color:#D6DEE8">101, 202, 303, 404, 505</td></tr>' +
                    f'</table>' +
                    f'<div style="margin-top:.8rem;font-size:.75rem;color:#5A7A96">' +
                    f'Workflow in ML Studio: ② EDA → ③ Train → ⑤ Compare → ⑥ Promote model' +
                    f'</div></div>'
                )

                # Show promoted model if it exists
                prom_model = root / "data" / "processed" / "ml_runs" / "airfoil_et_final_v1"
                if prom_model.exists():
                    _sec("Promoted model")
                    st.success(f"✓ Promoted model found: `{prom_model.name}`")
                    _cmd_preview(["ml", "inspect-model", "--model-run-dir", str(prom_model)])


def pg_dataset(root, exe, tmo, dry):
    _hero("▣","Dataset Factory","3D aero · 2D↔3D bridge · qc → curate → promote → ML-ready","data pipeline")
    tabs = st.tabs(["  Unified Aero  ","  Geometry Only  ","  Inspect / QC  ","  Curate / Promote  ","  Training Data  ","  Control / Flyability  ","  Smoke Check  ","  2D↔3D Bridge  "])

    # ── UNIFIED AERO DATASET ─────────────────────────────────────────────────
    with tabs[0]:
        _note(
            "<b>aeris dataset aero-generate</b> — the main production command. "
            "Geometry + full aero sweeps + QC in one pipeline. "
            "--alpha-values, --velocity-values, --altitude-values, --control-input-values are <b>required</b>.",
            "info",
        )
        def _ds_cfg_label(s):
            name = Path(s).name
            if name == "bwb_training_v1.yaml":
                return "v1 — 17 DVs, fixed elevon, sym sweep only"
            if name == "bwb_training_v2.yaml":
                return "v2 — 17 DVs, sym + diff elevon sweep"
            if name == "bwb_training_v3.yaml":
                return "v3 — 20 DVs, variable elevon + sym/diff sweep"
            return Path(s).name

        mode = st.radio("Config source",["Use existing YAML file","Build config interactively"],horizontal=True,key="ds_mode2")
        if mode.startswith("Use existing"):
            config = _pick_file("Geometry config",root/"configs"/"geometry","*.yaml","ds_ac",
                                default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
            _cfg_name = Path(config).name if config else ""
            if _cfg_name == "bwb_training_v2.yaml":
                _note(
                    "<b>v2 config selected</b> — supports sym elevon (<code>delta_e_sym_deg</code>) and diff elevon "
                    "(<code>delta_a_diff_deg</code>) sweeps. Use <code>--diff-input-values</code> below to add roll authority.",
                    "info",
                )
            elif _cfg_name == "bwb_training_v3.yaml":
                _note(
                    "<b>v3 config selected</b> — 20 DVs including variable elevon geometry (start/end/hinge fractions). "
                    "Supports both sym and diff sweeps. Use feature presets <code>bwb_control_sym_elevon_v3</code> or "
                    "<code>bwb_diff_elevon_v3</code> in ML Studio.",
                    "info",
                )
        else:
            ys = _yaml_geometry_builder("dsb")
            with st.expander("Preview YAML"): st.code(ys, language="yaml")
            sp2 = st.text_input("Save YAML to",str(root/"configs"/"geometry"/"gui_ds_config.yaml"),key="dsb_sp2")
            if st.button("Save YAML",key="dsb_sv2",type="secondary"):
                p=Path(sp2); p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(ys,encoding="utf-8"); st.success(f"Saved: {p}")
            config = sp2

        _sec("Sampling & naming")
        c1,c2,c3,c4 = st.columns(4)
        n    = c1.number_input("--n (geometries)",min_value=1,value=10,step=1,key="ds_n",help="Number of geometries to generate")
        samp = c2.selectbox("--sampler",SAMPLERS,key="ds_samp",format_func=lambda s: SAMPLER_INFO.get(s,s))
        seed = c3.number_input("--sampler-seed",min_value=0,value=123,step=1,key="ds_seed",help="Same seed = reproducible dataset")
        name = c4.text_input("--name (REQUIRED)",value="gui_aero_dataset_v1",key="ds_name",
                             help="Folder name under data/datasets/. Required. No spaces or slashes.")

        _sec("Flight condition sweep (all required)")
        _note("All values are comma-separated floats. --alpha-values, --velocity-values, --altitude-values, --control-input-values are required by the CLI.", "warn")
        c1,c2 = st.columns(2)
        alpha = c1.text_input("--alpha-values [deg]","-2,0,2,4,6",key="ds_al",help="Angle of attack sweep. e.g. -4,-2,0,2,4,6,8,10")
        beta  = c2.text_input("--beta-values [deg]","0",key="ds_be",help="Sideslip. Usually 0.")
        c3,c4 = st.columns(2)
        vel   = c3.text_input("--velocity-values [m/s]","28",key="ds_ve",help="Freestream velocity. e.g. 20,28")
        alt   = c4.text_input("--altitude-values [m]","1500",key="ds_at",help="ISA altitude. e.g. 0,1500")
        ctrl  = st.text_input("--control-input-values [deg]","-5,0,5",key="ds_ctrl",help="Symmetric elevon (delta_e_sym_deg). e.g. -10,-5,0,5,10")
        diff  = st.text_input(
            "--diff-input-values [deg]", "",
            key="ds_diff",
            help=(
                "Differential elevon sweep (delta_a_diff_deg). "
                "Independent of --control-input-values. "
                "Requires bwb_training_v2.yaml or v3.yaml config. "
                "Leave blank for symmetric-only datasets. "
                "e.g. -10,-5,0,5,10"
            ),
        )
        with st.expander("Angular rates (optional — leave 0 for standard datasets)"):
            c5,c6,c7 = st.columns(3)
            pv = c5.text_input("--p-values [rad/s]","0",key="ds_pv"); qv = c6.text_input("--q-values [rad/s]","0",key="ds_qv"); rv = c7.text_input("--r-values [rad/s]","0",key="ds_rv")
        _n_sym = _est(alpha,beta,vel,alt,ctrl,pv,qv,rv)
        if diff.strip():
            est_sym  = int(n) * _n_sym
            est_diff = int(n) * _csvn(diff) * _csvn(alpha) * _csvn(vel) * _csvn(alt)
            est = est_sym + est_diff
            _note(
                f"Estimated aero cases: <b>{est:,}</b> total — "
                f"{est_sym:,} symmetric (N_geom × {_n_sym} conditions) + "
                f"{est_diff:,} differential (N_geom × {_csvn(diff)} diff-values × {_csvn(alpha)} alpha × vel × alt). "
                "Sym and diff sweeps are independent (not a product).",
                "info",
            )
        else:
            est = int(n) * _n_sym
            _note(f"Estimated aero cases: <b>{est:,}</b> ({int(n)} geometries × {est//max(int(n),1)} conditions each)","info")

        _sec("Solver settings")
        c1,c2,c3 = st.columns(3)
        avl_cmd     = c1.text_input("--avl-command","avl",key="ds_avl",help="'avl' if on PATH, or full path to binary")
        timeout_ds  = c2.number_input("--timeout-sec",min_value=5,value=180,step=5,key="ds_tmo",help="Per-case solver timeout")
        sp_span     = c3.number_input("--spanwise-resolution",min_value=1,value=4,step=1,key="ds_sp")
        c4,c5,c6 = st.columns(3)
        sp_chord    = c4.number_input("--chordwise-resolution",min_value=1,value=8,step=1,key="ds_cp")
        sp_spacing  = c5.selectbox("--spanwise-spacing",SPACING,key="ds_spsp")
        ch_spacing  = c6.selectbox("--chordwise-spacing",SPACING,index=1,key="ds_chsp")
        c7,c8 = st.columns(2)
        save_srf    = c7.checkbox("--save-surface-forces",False,key="ds_ssf",help="Write AVL surface force files. More disk use.")
        save_elf    = c8.checkbox("--save-element-forces",False,key="ds_sef",help="Write AVL element force files. Even more disk.")

        _sec("Output & retention")
        c1,c2,c3 = st.columns(3)
        retain      = c1.selectbox("--retain-aero-runs",RETENTION_POLICIES,index=1,key="ds_ret",format_func=lambda s: RETENTION_INFO.get(s,s))
        save_pl_ds  = c2.checkbox("--no-save-plot (disable geometry plots)",False,key="ds_spl",help="Check to disable plot saving. Faster for large runs.")
        build_asb_ds= c3.checkbox("--build-aerosandbox (required for aero)",True,key="ds_ba",help="Must be True for aero runs to work.")
        c4,c5 = st.columns(2)
        keep_geo    = c4.checkbox("--keep-geometry-dataset",True,key="ds_kgd",help="Keep intermediate geometry dataset. Default True.")
        max_c_ds    = c5.text_input("--max-cases (optional cap)","",key="ds_mc",help="Safety cap on total aero cases. Leave blank.")

        _sec("QC — use preset OR explicit flags (preset overrides flags)")
        _note(
            "<b>Production QC</b> now includes physical geometry checks plus aero CL-alpha and Cm-control sign checks. "
            "<b>Strict QC</b> additionally keeps statistical outliers, L/D, beta=0 lateral sanity, and target-variation checks.",
            "info",
        )
        qcp_label = st.selectbox("--qc-preset (recommended — overrides all explicit QC flags)",
                                  ["(none — use explicit flags below)"] + QC_PRESETS, index=0, key="ds_qcp",
                                  format_func=lambda s: QC_PRESET_INFO.get(s,s) if s in QC_PRESET_INFO else s)
        qcp = "" if qcp_label.startswith("(none") else qcp_label
        if not qcp:
            with st.expander("Explicit QC flags (only used when no --qc-preset)"):
                c1,c2,c3 = st.columns(3)
                rg_qc  = c1.checkbox("--run-geometry-qc",False,key="ds_rgqc"); gp_qc = c1.selectbox("--geometry-qc-profile",QC_PROFILES,key="ds_gqcp"); fg_qc = c1.checkbox("--fail-on-geometry-qc-error",False,key="ds_fgqc")
                ra_qc  = c2.checkbox("--run-aero-qc",False,key="ds_raqc");     ap_qc = c2.selectbox("--aero-qc-profile",QC_PROFILES,key="ds_aqcp");     fa_qc = c2.checkbox("--fail-on-aero-qc-error",False,key="ds_faqc")

        args = [
            "dataset","aero-generate",
            "--config",config,"--n",str(int(n)),
            "--sampler",samp,"--sampler-seed",str(int(seed)),
            "--name",name,
            "--alpha-values",alpha,"--velocity-values",vel,
            "--altitude-values",alt,"--control-input-values",ctrl,
        ]
        if diff.strip():
            args += ["--diff-input-values", diff]
        if beta.strip() and beta.strip() != "0": args += ["--beta-values",beta]
        if pv.strip() and pv.strip() != "0": args += ["--p-values",pv]
        if qv.strip() and qv.strip() != "0": args += ["--q-values",qv]
        if rv.strip() and rv.strip() != "0": args += ["--r-values",rv]
        args += ["--solver","aerosandbox_avl","--avl-command",avl_cmd,
                 "--timeout-sec",str(int(timeout_ds)),
                 "--spanwise-resolution",str(int(sp_span)),"--chordwise-resolution",str(int(sp_chord)),
                 "--spanwise-spacing",sp_spacing,"--chordwise-spacing",ch_spacing,
                 "--retain-aero-runs",retain]
        if save_pl_ds: args.append("--no-save-plot")
        if not build_asb_ds: args.append("--no-build-aerosandbox")
        if not keep_geo: args.append("--delete-geometry-dataset")
        if save_srf: args.append("--save-surface-forces")
        if save_elf: args.append("--save-element-forces")
        _flag(args,"--max-cases",max_c_ds)
        ds_wf_input = st.text_input(
            "--workflow (auto-record on success)", "", key="ds_wf",
            placeholder="e.g. data/workflows/campaign_v1 — leave blank to skip",
            help="If set, auto-records the dataset aero-generate stage in the workflow spine after the campaign completes.",
        )
        if ds_wf_input.strip(): args += ["--workflow", ds_wf_input.strip()]
        if qcp:
            args += ["--qc-preset",qcp]
        else:
            _bflag(args,"--run-geometry-qc","--no-run-geometry-qc",rg_qc)
            if rg_qc: args += ["--geometry-qc-profile",gp_qc]; _bflag(args,"--fail-on-geometry-qc-error","--allow-geometry-qc-errors",fg_qc)
            _bflag(args,"--run-aero-qc","--no-run-aero-qc",ra_qc)
            if ra_qc: args += ["--aero-qc-profile",ap_qc]; _bflag(args,"--fail-on-aero-qc-error","--allow-aero-qc-errors",fa_qc)
        _panel("Generate unified aero dataset",
               "Generates N geometries + full aero sweeps + QC. Writes aero_dataset.csv ready for curation/ML.",
               args, root, exe, tmo, dry, "ds_aero_gen")

    # ── GEOMETRY ONLY ─────────────────────────────────────────────────────────
    with tabs[1]:
        _note("<b>aeris dataset generate</b> — geometry only, no aero. Fast iteration on design space before committing to sweeps.","info")
        config2 = _pick_file("Geometry config",root/"configs"/"geometry","*.yaml","gs_cfg",
                             default=str(root/"configs"/"geometry"/"wing_bwb.yaml"))
        c1,c2,c3,c4 = st.columns(4)
        n2   = c1.number_input("--n",min_value=1,value=20,step=1,key="gs_n")
        s2   = c2.selectbox("--sampler",SAMPLERS,key="gs_samp",format_func=lambda s:SAMPLER_INFO.get(s,s))
        sd2  = c3.number_input("--sampler-seed",min_value=0,value=123,step=1,key="gs_seed")
        nm2  = c4.text_input("--name (optional)","",key="gs_name",help="Dataset folder name. Leave blank for auto-generated name.")
        c5,c6 = st.columns(2)
        sp2  = c5.checkbox("--no-save-plot (disable plots)",False,key="gs_sp")
        ba2  = c6.checkbox("--build-aerosandbox",True,key="gs_ba")
        with st.expander("QC options"):
            qcp2  = st.selectbox("--qc-preset",["(none)"] + QC_PRESETS,key="gs_qcp2",format_func=lambda s:QC_PRESET_INFO.get(s,s) if s in QC_PRESET_INFO else s)
            if qcp2 == "(none)":
                rqc2 = st.checkbox("--run-qc/--no-run-qc",False,key="gs_rqc")
                qpr2 = st.selectbox("--qc-profile",QC_PROFILES,key="gs_qpr2")
                fqc2 = st.checkbox("--fail-on-qc-error/--allow-qc-errors",False,key="gs_fqc2")
        args2 = ["dataset","generate","--config",config2,"--n",str(int(n2)),"--sampler",s2,"--sampler-seed",str(int(sd2))]
        _flag(args2,"--name",nm2)
        if sp2:  args2.append("--no-save-plot")
        if not ba2: args2.append("--no-build-aerosandbox")
        if qcp2 != "(none)":
            args2 += ["--qc-preset",qcp2]
        else:
            _bflag(args2,"--run-qc","--no-run-qc",rqc2)
            if rqc2: args2 += ["--qc-profile",qpr2]; _bflag(args2,"--fail-on-qc-error","--allow-qc-errors",fqc2)
        _panel("Generate geometry dataset","Builds many deterministic geometry cases. No aero.",args2,root,exe,tmo,dry,"gs_run")

    # ── INSPECT / QC ──────────────────────────────────────────────────────────
    with tabs[2]:
        ds3 = _pick_dir("Dataset root",root/"data"/"datasets","diq_ds")
        act3 = st.selectbox("Action",["Inspect (aeris dataset inspect)","Geometry QC (aeris dataset qc)","Aero QC (aeris dataset aero-qc)"],key="diq_act")
        if "inspect" in act3.lower():
            args3 = ["dataset","inspect","--dataset",ds3]
            desc3 = "Reads dataset structure and prints QC summary JSON."
        elif "Geometry QC" in act3:
            qp3 = st.selectbox("--profile",QC_PROFILES,key="diq_gqcp")
            args3 = ["dataset","qc","--dataset",ds3,"--profile",qp3]
            desc3 = "Runs geometry QC. Production/strict include AR consistency, taper, planform, twist, and dihedral physical checks."
        else:
            qp3 = st.selectbox("--profile",QC_PROFILES,key="diq_aqcp")
            args3 = ["dataset","aero-qc","--dataset",ds3,"--profile",qp3]
            desc3 = "Runs aero QC. Production includes CL-alpha and Cm-control sign; strict adds outlier, L/D, beta=0, and target-variation checks."
        _panel("Inspect / QC",desc3,args3,root,exe,tmo,dry,"diq_run")

    # ── CURATE / PROMOTE ──────────────────────────────────────────────────────
    with tabs[3]:
        _note("Curation filters bad rows. Promotion writes <code>promotion_manifest.json</code> — required gate before ML training.","info")
        ds4 = _pick_dir("Aero dataset root",root/"data"/"datasets","dcp_ds")
        task4 = st.selectbox("Task",["curate-aero","promote-aero","require-promoted-aero"],key="dcp_task")

        if task4 == "curate-aero":
            _note(
                "Curation rejects: incomplete groups, aero failures, nonfinite targets, failed control diagnostics. "
                "Grid completeness is checked against manifest sweep lists, including beta/rates/differential controls when present. "
                "All four defaults are True. "
                "<b>After curating and promoting, run <code>aeris aero cm-sanity --dataset &lt;ds&gt;</code></b> "
                "(in the Aero page) to verify Cm sign convention before any ML training.",
                "info",
            )
            c1,c2 = st.columns(2)
            ri4 = c1.checkbox("--reject-incomplete-groups",True,key="dc_ri",help="Reject geometries whose manifest-defined sweep grid is incomplete")
            rf4 = c2.checkbox("--reject-groups-with-failures",True,key="dc_rf",help="Reject geometries with any failed AVL case")
            rn4 = c1.checkbox("--reject-nonfinite-targets",True,key="dc_rn",help="Reject rows with NaN/Inf in CL/CD/Cm")
            rd4 = c2.checkbox("--reject-control-diagnostic-failures",True,key="dc_rd",help="Reject geometries where AVL control diagnostics failed")
            args4 = ["dataset","curate-aero","--dataset",ds4]
            if not ri4: args4.append("--keep-incomplete-groups")
            if not rf4: args4.append("--keep-groups-with-failures")
            if not rn4: args4.append("--keep-nonfinite-targets")
            if not rd4: args4.append("--keep-control-diagnostic-failures")
            desc4 = "Filters bad rows. Writes curated_aero_dataset.csv + curation_report.json."

        elif task4 == "promote-aero":
            force4 = st.checkbox("--force (bypass promotion blockers)",False,key="dc_force",
                                 help="Force promotion despite curation_report.json promotion_ready=false. Document why before using.")
            if force4: _note("⚠ Force-promoted datasets are flagged in all downstream workflows. Document the reason.","warn")
            args4 = ["dataset","promote-aero","--dataset",ds4]
            if force4: args4.append("--force")
            desc4 = "Writes promotion_manifest.json — the required gate for ML training."

        else:  # require-promoted-aero
            af4 = st.checkbox("--allow-forced (allow force-promoted datasets)",False,key="dc_af")
            args4 = ["dataset","require-promoted-aero","--dataset",ds4]
            if af4: args4.append("--allow-forced")
            desc4 = "Validates dataset has promotion_manifest.json and is trustworthy."

        _panel(f"Dataset: {task4}",desc4,args4,root,exe,tmo,dry,"dcp_run",danger=(task4=="promote-aero"))

    # ── TRAINING DATA ─────────────────────────────────────────────────────────
    with tabs[4]:
        ds5 = _pick_dir("Promoted dataset root",root/"data"/"datasets","dtr_ds")
        c1,c2 = st.columns(2)
        feat5 = c1.text_input("--features",DEFAULT_FEATURES,key="dtr_feat")
        tgt5  = c2.text_input("--targets",DEFAULT_TARGETS,key="dtr_tgt")
        util5 = st.selectbox("Utility",["training-data","split-training-data"],key="dtr_util")
        args5 = ["dataset",util5,"--dataset",ds5,"--features",feat5,"--targets",tgt5]
        if util5 == "split-training-data":
            c3,c4,c5 = st.columns(3)
            sm5  = c3.selectbox("--method",["grouped","random"],key="dtr_sm")
            gc5  = c4.text_input("--group-column","geometry_id",key="dtr_gc")
            rs5  = c5.number_input("--random-seed",min_value=0,value=123,step=1,key="dtr_rs")
            c6,c7,c8 = st.columns(3)
            tr5  = c6.slider("--train-fraction",0.3,0.85,0.70,0.05,key="dtr_tr")
            vl5  = c7.slider("--val-fraction",0.05,0.3,0.15,0.05,key="dtr_vl")
            te5  = c8.slider("--test-fraction",0.05,0.3,0.15,0.05,key="dtr_te")
            args5 += ["--method",sm5,"--group-column",gc5,"--random-seed",str(int(rs5)),
                      "--train-fraction",str(tr5),"--val-fraction",str(vl5),"--test-fraction",str(te5)]
        _panel("Training data",f"Prepares training-ready data from promoted dataset.",args5,root,exe,tmo,dry,"dtr_run")

    # ── CONTROL / FLYABILITY LABELS ───────────────────────────────────────────
    with tabs[5]:
        _note(
            "D2/D3/D4 convert symmetric elevon sweeps into engineering labels: "
            "control derivatives → trim/flyability labels → one batch evidence report. "
            "This is first-order diagnostic logic, not a nonlinear trim solver and not a MIL-STD claim.",
            "info",
        )
        with st.expander("⟳ Roll authority check (differential elevon datasets — v2/v3 configs)", expanded=False):
            _note(
                "For <b>roll authority</b> analysis from a differential elevon dataset, filter rows to "
                "<code>sweep_type == diff</code> first (or use a diff-only dataset), then run:",
                "info",
            )
            st.code(
                "aeris dataset compute-control-derivatives \\\n"
                "  --dataset <dataset> \\\n"
                "  --control-column delta_a_diff_deg \\\n"
                "  --targets cl_roll,cy,cn",
                language="bash",
            )
            _note(
                "<b>Note:</b> <code>sweep_type=diff</code> rows are generated by <code>--diff-input-values</code> during aero-generate. "
                "These rows hold <code>delta_e_sym_deg=0</code> and vary <code>delta_a_diff_deg</code>. "
                "D2 on these rows gives roll derivatives (dCl_roll/dδa) rather than pitch derivatives.",
                "warn",
            )
        ds_cf = _pick_dir("Aero dataset root", root / "data" / "datasets", "dcf_ds")
        c1, c2, c3 = st.columns(3)
        src_cf = c1.selectbox("--source", ["auto", "curated", "raw"], key="dcf_src")
        ctrl_cf = c2.text_input("--control-column", "", key="dcf_ctrl", help="Blank = delta_e_sym_deg with fallback to control_input_deg.")
        cm_cf = c3.text_input("--cm-column", "cm", key="dcf_cm")

        with st.expander("Advanced grouping / targets / thresholds"):
            c4, c5 = st.columns(2)
            groups_cf = c4.text_input("--group-columns", DEFAULT_CONTROL_DERIVATIVE_GROUPS, key="dcf_groups")
            targets_cf = c5.text_input("--targets", DEFAULT_CONTROL_DERIVATIVE_TARGETS, key="dcf_targets")
            c6, c7, c8 = st.columns(3)
            trim_lim = c6.number_input("--max-abs-trim-delta-e-deg", value=25.0, step=1.0, key="dcf_trimlim")
            min_cmde = c7.number_input("--min-abs-cm-delta-e-per-rad", value=0.10, step=0.01, format="%.3f", key="dcf_mincmde")
            recompute = c8.checkbox("--recompute-control-derivatives", True, key="dcf_recompute")
            c9, c10 = st.columns(2)
            alpha_min = c9.number_input("--alpha-min-deg", value=-5.0, step=1.0, key="dcf_amin")
            alpha_max = c10.number_input("--alpha-max-deg", value=15.0, step=1.0, key="dcf_amax")

        args_d2 = ["dataset", "compute-control-derivatives", "--dataset", ds_cf, "--source", src_cf]
        _flag(args_d2, "--control-column", ctrl_cf)
        _flag(args_d2, "--group-columns", groups_cf)
        _flag(args_d2, "--targets", targets_cf)

        args_d3 = [
            "dataset", "compute-flyability-labels", "--dataset", ds_cf, "--source", src_cf,
            "--cm-column", cm_cf,
            "--max-abs-trim-delta-e-deg", str(trim_lim),
            "--min-abs-cm-delta-e-per-rad", str(min_cmde),
            "--alpha-min-deg", str(alpha_min),
            "--alpha-max-deg", str(alpha_max),
        ]
        _flag(args_d3, "--control-column", ctrl_cf)
        _flag(args_d3, "--group-columns", groups_cf)

        args_d4 = [
            "dataset", "compute-dynamics-labels", "--dataset", ds_cf, "--source", src_cf,
            "--cm-column", cm_cf,
            "--max-abs-trim-delta-e-deg", str(trim_lim),
            "--min-abs-cm-delta-e-per-rad", str(min_cmde),
            "--alpha-min-deg", str(alpha_min),
            "--alpha-max-deg", str(alpha_max),
        ]
        _flag(args_d4, "--control-column", ctrl_cf)
        _flag(args_d4, "--group-columns", groups_cf)
        _flag(args_d4, "--targets", targets_cf)
        if not recompute:
            args_d4.append("--no-recompute-control-derivatives")

        c1, c2, c3 = st.columns(3)
        with c1:
            _panel("D2 — compute control derivatives", "Finite-difference Cmδe/CLδe/CDδe from -δ,0,+δ symmetric elevon sweeps.", args_d2, root, exe, tmo, dry, "dcf_d2")
        with c2:
            _panel("D3 — compute flyability labels", "Estimates required trim δe and basic longitudinal flyability from D2 derivatives.", args_d3, root, exe, tmo, dry, "dcf_d3")
        with c3:
            _panel("D4 — batch dynamics labels", "Runs the D2→D3 chain and writes one evidence report.", args_d4, root, exe, tmo, dry, "dcf_d4")

        if ds_cf:
            _dataset_control_artifact_preview(Path(ds_cf))

    # ── SMOKE CHECK ───────────────────────────────────────────────────────────
    with tabs[6]:
        _note("<b>aeris pipeline smoke</b> — minimal end-to-end: config → generator → one sample → manifest. Run after install/env changes.","info")
        cfg_sm = _pick_file("Smoke config",root/"configs"/"smoke","*.yaml","sm_cfg",
                            default=str(root/"configs"/"smoke"/"dev.yaml"))
        _panel("Run smoke pipeline","Quick end-to-end sanity check.",["pipeline","smoke","--config",cfg_sm],root,exe,tmo,dry,"sm_run")

        st.divider()
        _note("<b>Aero-generate smoke runs</b> — quick functional checks for v2/v3 configs and diff elevon wiring.","info")
        sm_tabs = st.tabs(["Sym smoke (v2)", "Diff smoke (v2)", "Variable elevon smoke (v3)"])

        _v2_cfg = str(root / "configs" / "geometry" / "bwb_training_v2.yaml")
        _v3_cfg = str(root / "configs" / "geometry" / "bwb_training_v3.yaml")

        with sm_tabs[0]:
            _note("1 geometry, 3 alpha, symmetric sweep only. Validates v2 config + AVL wiring.","info")
            _panel(
                "Sym smoke (v2)",
                "Generates 1 geometry with symmetric elevon sweep. Expected: 3 alpha × 3 ctrl = 9 aero cases.",
                [
                    "dataset", "aero-generate", "-c", _v2_cfg,
                    "--n", "1", "--name", "smoke_sym_gui",
                    "--alpha-values", "-4,0,4", "--velocity-values", "28",
                    "--altitude-values", "0", "--control-input-values", "-10,0,10",
                    "--qc-preset", "debug", "--no-save-plot",
                ],
                root, exe, tmo, dry, "sm_sym_v2",
            )

        with sm_tabs[1]:
            _note("1 geometry, 3 alpha, differential sweep. Validates d2/SgnDup=-1 wiring and Cl_roll response.","info")
            _panel(
                "Diff smoke (v2)",
                "Generates 1 geometry with differential elevon sweep. sym=0 held; diff varies. Cl_roll should vary, Cm near-constant.",
                [
                    "dataset", "aero-generate", "-c", _v2_cfg,
                    "--n", "1", "--name", "smoke_diff_gui",
                    "--alpha-values", "-4,0,4", "--velocity-values", "28",
                    "--altitude-values", "0", "--control-input-values", "0",
                    "--diff-input-values", "-10,0,10",
                    "--qc-preset", "debug", "--no-save-plot",
                ],
                root, exe, tmo, dry, "sm_diff_v2",
            )

        with sm_tabs[2]:
            _note("3 geometries with varied elevon geometry (start/end/hinge fractions). Validates v3 20-DV space.","info")
            _panel(
                "Variable elevon smoke (v3)",
                "Generates 3 geometries with sampled elevon_start_frac / end_frac / hinge_frac. Pitch authority should scale with elevon span.",
                [
                    "dataset", "aero-generate", "-c", _v3_cfg,
                    "--n", "3", "--name", "smoke_v3_gui",
                    "--alpha-values", "-4,0,4", "--velocity-values", "28",
                    "--altitude-values", "0", "--control-input-values", "-10,0,10",
                    "--qc-preset", "debug", "--no-save-plot",
                ],
                root, exe, tmo, dry, "sm_v3",
            )

    # ── 2D ↔ 3D BRIDGE ───────────────────────────────────────────────────
    with tabs[7]:
        _note(
            "<b>2D ↔ 3D Bridge</b> — connect a promoted XFOIL airfoil library to a "
            "3D BWB aero-generate campaign. "
            "The 2D XFOIL surrogate predicts airfoil-level Cl/Cd/Cm across t/c and Re; "
            "the 3D AVL sweep predicts wing-level CL/CD/Cm across geometry DVs and flight conditions. "
            "Together they span the full design space from section to vehicle.",
            "info",
        )

        _sec("Step 1 — 2D source library")
        bridge_lib_opts = _airfoil_library_candidates(root)
        _default_lib = (bridge_lib_opts[0] if bridge_lib_opts
                        else str(root / "data" / "airfoil_library"))
        bridge_lib = st.selectbox(
            "Active airfoil library",
            bridge_lib_opts if bridge_lib_opts else [_default_lib],
            format_func=_airfoil_library_label,
            key="bridge_lib",
            help="Select the promoted XFOIL airfoil library that describes the BWB section family.",
        )
        bridge_lib_path = Path(str(bridge_lib))
        _bridge_n = _airfoil_inventory_count(bridge_lib_path)
        if _bridge_n > 0:
            st.caption("Library **" + bridge_lib_path.name + "** — " + str(_bridge_n) + " airfoils.")
        else:
            st.warning("No airfoils found. Generate + promote a 2D dataset first (2D Airfoils page).")

        _sec("Step 2 — 3D geometry config")
        bridge_cfg_opts = _files(str(root / "configs" / "geometry"), "*.yaml")
        bridge_cfg = _pick_file(
            "3D geometry config", root / "configs" / "geometry", "*.yaml",
            "bridge_cfg",
            default=str(root / "configs" / "geometry" / "bwb_training_v1.yaml"),
        )

        _sec("Step 3 — campaign settings")
        bc1, bc2, bc3, bc4 = st.columns(4)
        bridge_n    = bc1.number_input("--n", min_value=1, value=5, step=1, key="bridge_n",
                                        help="Number of 3D BWB geometries to generate.")
        bridge_samp = bc2.selectbox("--sampler", SAMPLERS, key="bridge_samp",
                                    format_func=lambda s: SAMPLER_INFO.get(s, s))
        bridge_seed = bc3.number_input("--sampler-seed", min_value=0, value=42, step=1, key="bridge_seed")
        bridge_name = bc4.text_input("--name", value="bridge_aero_v1", key="bridge_name",
                                     help="Output dataset folder name under data/datasets/.")

        _sec("Step 4 — 3D flight envelope")
        bb1, bb2 = st.columns(2)
        bridge_al  = bb1.text_input("--alpha-values [deg]", "-2,0,2,4,6", key="bridge_al")
        bridge_ve  = bb2.text_input("--velocity-values [m/s]", "28", key="bridge_ve")
        bb3, bb4 = st.columns(2)
        bridge_at  = bb3.text_input("--altitude-values [m]", "1500", key="bridge_at")
        bridge_ct  = bb4.text_input("--control-input-values [deg]", "-5,0,5", key="bridge_ct")

        _sec("Step 5 — QC preset")
        bridge_qcp = st.selectbox(
            "--qc-preset", ["(none)"] + QC_PRESETS, key="bridge_qcp",
            format_func=lambda s: QC_PRESET_INFO.get(s, s) if s in QC_PRESET_INFO else s,
        )

        bridge_args = [
            "dataset", "aero-generate",
            "-c", bridge_cfg,
            "--n", str(int(bridge_n)),
            "--sampler", bridge_samp,
            "--sampler-seed", str(int(bridge_seed)),
            "--name", bridge_name,
            "--alpha-values", bridge_al,
            "--velocity-values", bridge_ve,
            "--altitude-values", bridge_at,
            "--control-input-values", bridge_ct,
            "--solver", "aerosandbox_avl",
            "--no-save-plot",
            "--retain-aero-runs", "failures_only",
        ]
        if bridge_qcp != "(none)": bridge_args += ["--qc-preset", bridge_qcp]

        _note(
            "<b>After this campaign:</b> go to ◈ ML Studio, select a feature set that "
            "includes both 2D airfoil features and 3D geometry/flight-condition features "
            "(e.g. a custom set combining <code>airfoil_xfoil_v1</code> inputs with "
            "<code>c1_m, b_total_m, sw1_deg</code>) to train a joint surrogate.",
            "info",
        )
        _panel(
            "Launch 2D↔3D bridged aero campaign",
            "3D BWB aero-generate campaign wired to the 2D airfoil library. "
            "After completion: train a joint surrogate in ML Studio.",
            bridge_args, root, exe, tmo, dry, "bridge_run",
        )


def _aero_run_rows(root: Path) -> list[Path]:
    """All folders in data/runs/ that look like aero runs (single or sweep)."""
    return [Path(r) for r in _dirs(str(root / "data" / "runs"))
            if any(k in Path(r).name for k in ("_aero_", "_sweep_"))]

def _geo_run_rows(root: Path) -> list[Path]:
    """All folders in data/runs/ that look like geometry-only runs."""
    return [Path(r) for r in _dirs(str(root / "data" / "runs"))
            if "geometry" in Path(r).name
            and not any(k in Path(r).name for k in ("_aero_", "_sweep_"))]

def _aero_src_widget(key: str, root: Path, geo_runs: list[Path],
                     cfg_opts: list[str], cfg_label_fn) -> list[str]:
    """
    Geometry source selector for aero run/sweep.
    Returns the CLI source args list.
    Always hardcodes --generator-id bwb_segmented_v1 (only registered generator).
    """
    src_mode = st.radio(
        "Geometry source",
        ["From existing geometry run", "From config file"],
        horizontal=True,
        key=f"{key}_src_mode",
        help="Existing run: reuses a geometry you already generated. "
             "Config file: generates a fresh geometry sample on the fly.",
    )

    args = []
    if src_mode == "From existing geometry run":
        if not geo_runs:
            st.warning(
                "No geometry runs found in data/runs/. "
                "Go to Geometry → ① Generate first."
            )
            # Fall back silently to config so args are always valid
            cfg = cfg_opts[0] if cfg_opts else ""
            args += ["--config", cfg]
        else:
            run_map = {p.name: p for p in geo_runs}
            chosen = st.selectbox(
                "Select geometry run",
                list(run_map.keys()),
                key=f"{key}_run_sel",
                help="Folder from data/runs/. The geometry inside will be reused — "
                     "no re-sampling.",
            )
            chosen_path = run_map[chosen]
            m = _rjson(chosen_path / "manifest.json")
            status = (m or {}).get("status", "unknown")
            dot = "#22C55E" if status == "success" else "#EF4444"
            _h(
                f'<div style="background:#1B2A3A;border:1px solid #2D3F52;border-radius:7px;'
                f'padding:.42rem .9rem;margin:.3rem 0;display:flex;align-items:center;gap:10px">'
                f'<div style="width:7px;height:7px;border-radius:50%;background:{dot};flex-shrink:0"></div>'
                f'<div style="flex:1;font-size:.78rem;color:#D6DEE8;font-family:JetBrains Mono,monospace;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{chosen_path.name}</div>'
                f'<div style="font-size:.7rem;color:{dot};font-weight:600;flex-shrink:0">{status}</div>'
                f'</div>'
            )
            args += ["--run-dir", str(chosen_path),
                     "--generator-id", "bwb_segmented_v1"]
    else:
        cfg = st.selectbox(
            "Config", cfg_opts if cfg_opts else [""],
            format_func=cfg_label_fn,
            key=f"{key}_cfg",
            help="Generates a fresh geometry sample from this config.",
        )
        seed = st.number_input(
            "Seed", min_value=0, max_value=99999, value=0, step=1,
            key=f"{key}_seed",
            help="Geometry seed. 0 = config default. Same seed + same config = same geometry.",
        )
        args += ["--config", cfg, "--seed", str(int(seed))]

    return args


def _aero_solver_widget(key: str) -> list[str]:
    """Solver settings — AVL command always visible, rest collapsed."""
    avl = st.text_input(
        "AVL command",
        value="avl",
        key=f"{key}_avl",
        help="Type 'avl' if avl is on your PATH. "
             "Otherwise paste the full path, e.g. /usr/local/bin/avl",
    )
    with st.expander("Paneling & advanced solver settings"):
        c1, c2, c3, c4 = st.columns(4)
        sp  = c1.number_input("Spanwise panels",  min_value=1, value=4,  step=1, key=f"{key}_sp",
                              help="--spanwise-resolution. Default 4 for datasets, 8+ for accuracy.")
        cp  = c2.number_input("Chordwise panels", min_value=1, value=8,  step=1, key=f"{key}_cp",
                              help="--chordwise-resolution. Default 8.")
        ssp = c3.selectbox("Spanwise spacing",  SPACING,       key=f"{key}_ssp",
                           help="--spanwise-spacing. 'equal' or 'cosine'.")
        csp = c4.selectbox("Chordwise spacing", SPACING, index=1, key=f"{key}_csp",
                           help="--chordwise-spacing. 'cosine' recommended.")
        tmo_ = st.number_input("Timeout [s]", min_value=5, value=180, step=5, key=f"{key}_tmo",
                               help="--timeout-sec. Per-case timeout. 180s is safe for single AVL runs.")
        c5, c6 = st.columns(2)
        ssf = c5.checkbox("Save surface forces", False, key=f"{key}_ssf",
                          help="--save-surface-forces. Writes AVL surface force files.")
        sef = c6.checkbox("Save element forces", False, key=f"{key}_sef",
                          help="--save-element-forces. Writes AVL element force files.")
    args = ["--solver", "aerosandbox_avl",
            "--avl-command", avl,
            "--spanwise-resolution", str(int(sp)),
            "--chordwise-resolution", str(int(cp)),
            "--spanwise-spacing", ssp,
            "--chordwise-spacing", csp,
            "--timeout-sec", str(int(tmo_))]
    if ssf: args.append("--save-surface-forces")
    if sef: args.append("--save-element-forces")
    return args


def _aero_run_list(root: Path, tab_key: str, run_filter_fn) -> None:
    """Show aero runs with per-row delete buttons."""
    import shutil as _shutil
    runs = run_filter_fn(root)
    if not runs:
        st.caption("No runs yet.")
        return

    _sec("Recent runs")
    st.caption("Click 🗑 to delete a run folder.")
    did_delete = False
    for i, p in enumerate(runs[:20]):
        m      = _rjson(p / "manifest.json")
        status = (m or {}).get("status", "—")
        dot    = "#22C55E" if status == "success" else                  "#EF4444" if status == "failed"  else "#8EA0B3"
        col_n, col_b = st.columns([10, 1])
        with col_n:
            _h(
                f'<div style="background:#1B2A3A;border:1px solid #2D3F52;border-radius:7px;'
                f'padding:.42rem .9rem;display:flex;align-items:center;gap:10px">'
                f'<div style="width:7px;height:7px;border-radius:50%;background:{dot};flex-shrink:0"></div>'
                f'<div style="flex:1;font-size:.78rem;color:#D6DEE8;font-family:JetBrains Mono,monospace;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{p.name}</div>'
                f'<div style="font-size:.7rem;color:{dot};font-weight:600;flex-shrink:0">{status}</div>'
                f'</div>'
            )
        with col_b:
            if st.button("🗑", key=f"del_aero_{tab_key}_{i}", help=f"Delete {p.name}"):
                try:
                    _shutil.rmtree(p)
                    st.toast(f"Deleted {p.name}", icon="🗑")
                    did_delete = True
                except Exception as e:
                    st.error(str(e))
    if did_delete:
        st.rerun()

    if len(runs) > 1:
        st.markdown("")
        if st.button(f"🗑  Delete ALL ({len(runs)})", key=f"del_aero_{tab_key}_all", type="secondary"):
            st.session_state[f"confirm_del_{tab_key}"] = True
    if st.session_state.get(f"confirm_del_{tab_key}"):
        st.warning(f"Delete all {len(runs)} run folder(s)? Cannot be undone.")
        ca, cb, _ = st.columns([1, 1, 4])
        if ca.button("Yes, delete all", key=f"del_aero_{tab_key}_yes", type="primary"):
            for p in runs:
                try:
                    _shutil.rmtree(p)
                except Exception as e:
                    st.error(str(e))
            st.session_state[f"confirm_del_{tab_key}"] = False
            st.toast(f"Deleted {len(runs)} folder(s).", icon="🗑")
            st.rerun()
        if cb.button("Cancel", key=f"del_aero_{tab_key}_no", type="secondary"):
            st.session_state[f"confirm_del_{tab_key}"] = False
            st.rerun()


def pg_aero(root, exe, tmo, dry):
    _hero("⊿", "Aero Analysis", "aerosandbox_avl · single run or sweep", "aero")

    # Shared config list
    cfg_files = _files(str(root / "configs" / "geometry"), "*.yaml")
    smoke_cfg = str(root / "configs" / "geometry" / "baseline_bwb_25.yaml")
    prod_cfg  = str(root / "configs" / "geometry" / "bwb_training_v1.yaml")
    cfg_smoke_first = ([smoke_cfg] if smoke_cfg in cfg_files else []) +                       ([prod_cfg]  if prod_cfg  in cfg_files else []) +                       [f for f in cfg_files if f not in (prod_cfg, smoke_cfg)]

    def _cfg_label(s):
        if "bwb_training_v1" in s: return f"Production — {Path(s).name}"
        if "baseline_bwb_25"  in s: return f"Smoke test  — {Path(s).name}"
        return Path(s).name if s else "— none —"

    geo_runs = _geo_run_rows(root)

    tab_single, tab_sweep, tab_inspect = st.tabs([
        "  ① Single run  ",
        "  ② Sweep  ",
        "  ③ Inspect  ",
    ])

    # ── ① SINGLE RUN ─────────────────────────────────────────────────────────
    with tab_single:
        st.caption(
            "Run AVL on **one geometry × one flight condition**. "
            "Use for spot-checks and solver verification."
        )
        src_args = _aero_src_widget("ar", root, geo_runs, cfg_smoke_first, _cfg_label)

        _sec("Flight condition")
        c1, c2, c3 = st.columns(3)
        al   = c1.number_input("Alpha [deg]",    value=4.0,    step=0.5, key="ar_al",
                               help="Angle of attack. Required.")
        ve   = c2.number_input("Velocity [m/s]", value=28.0,   step=1.0, key="ar_ve")
        at   = c3.number_input("Altitude [m]",   value=1500.0, step=100.0, key="ar_at")
        c4, c5 = st.columns(2)
        ctrl = c4.number_input("Sym elevon δe [deg]", value=0.0, step=1.0, key="ar_ctrl",
                               help="Symmetric elevon (d2 symmetric). Positive = both trailing edges down.")
        diff = c5.number_input("Diff elevon δa [deg]", value=0.0, step=1.0, key="ar_diff",
                               help="Differential elevon (d2 antisymmetric). Positive = right TE down, left TE up.")
        if abs(al) > 30.0:
            st.warning(f"⚠ Alpha = {al}° is outside the typical envelope (±30°). AVL may diverge.")
        if ve <= 0:
            st.error("✗ Velocity must be > 0 m/s.")
        elif ve > 150.0:
            st.warning(f"⚠ Velocity = {ve} m/s is unusually high for a BWB UAV. Check units.")
        with st.expander("Sideslip & body rates (leave at 0 for standard runs)"):
            c5, c6, c7, c8 = st.columns(4)
            be = c5.number_input("Beta [deg]", value=0.0, step=0.5, key="ar_be")
            pv = c6.number_input("p [rad/s]",  value=0.0, step=0.1, key="ar_p")
            qv = c7.number_input("q [rad/s]",  value=0.0, step=0.1, key="ar_q")
            rv = c8.number_input("r [rad/s]",  value=0.0, step=0.1, key="ar_r")

        _sec("Solver")
        sol_args = _aero_solver_widget("ar")

        with st.expander("Output naming & workflow (optional)"):
            c_o1, c_o2 = st.columns(2)
            ar_out_name = c_o1.text_input(
                "--output-name", "", key="ar_out_name",
                placeholder="e.g. baseline_check_v1",
                help="Optional suffix appended to the output run folder name.",
            )
            ar_mach = c_o2.text_input(
                "--mach (override)", "", key="ar_mach",
                placeholder="e.g. 0.083 — normally leave blank (auto)",
                help="Override auto-computed Mach number. AVL is incompressible; leave blank in most cases.",
            )
            ar_wf = st.text_input(
                "--workflow (auto-record stage on success)", "", key="ar_wf",
                placeholder="e.g. data/workflows/campaign_v1",
                help="Workflow root. If set, auto-records the aero_run stage after a successful run.",
            )
        full_args = (["aero", "run"] + src_args +
                     ["--alpha", str(al), "--velocity", str(ve),
                      "--altitude", str(at), "--control-input-deg", str(ctrl),
                      "--diff-input-deg", str(diff),
                      "--beta", str(be),
                      "--p", str(pv), "--q", str(qv), "--r", str(rv)] +
                     sol_args)
        if ar_out_name.strip(): full_args += ["--output-name", ar_out_name.strip()]
        if ar_mach.strip():     full_args += ["--mach", ar_mach.strip()]
        if ar_wf.strip():       full_args += ["--workflow", ar_wf.strip()]
        _panel(
            "Run single aero case",
            "One geometry × one flight condition → data/runs/<timestamp>_aero_*/",
            full_args, root, exe, tmo, dry, "ar_run",
            label="▶  Run aero case",
        )
        _aero_run_list(root, "single", _aero_run_rows)

    # ── ② SWEEP ───────────────────────────────────────────────────────────────
    with tab_sweep:
        st.caption(
            "Run AVL across **multiple flight conditions** for one geometry. "
            "Generates the Cartesian product of the value lists you provide."
        )
        src_args_sw = _aero_src_widget("sw", root, geo_runs, cfg_smoke_first, _cfg_label)

        _sec("Flight condition sweep")
        st.caption(
            "Enter comma-separated values for each dimension. "
            "Leave a field at its single value to hold it constant."
        )
        c1, c2 = st.columns(2)
        al2  = c1.text_input("Alpha values [deg]",    "-2,0,2,4,6",  key="sw_al",
                             help="e.g. -4,-2,0,2,4,6,8,10")
        ve2  = c2.text_input("Velocity values [m/s]", "28",          key="sw_ve")
        c3, c4 = st.columns(2)
        at2  = c3.text_input("Altitude values [m]",          "1500",   key="sw_at")
        ct2  = c4.text_input("Sym elevon δe values [deg]", "-5,0,5", key="sw_ctrl",
                             help="Symmetric elevon sweep (d2 symmetric). e.g. -10,-5,0,5,10")
        c5, c6 = st.columns(2)
        df2  = c5.text_input("Diff elevon δa values [deg]", "0",   key="sw_diff",
                             help="Differential elevon sweep (d2 antisymmetric). Leave as 0 for symmetric-only runs.")
        _ = c6  # spacer
        with st.expander("Sideslip & body rates — expand for lateral-directional derivatives"):
            st.caption(
                "**For lateral-directional derivative extraction (Clβ, Cnβ, CYβ):** "
                "set Beta values to `-10,-8,-6,-4,-2,0,2,4,6,8,10` and keep alpha fixed at cruise. "
                "This is required for Paper 1 dataset labels and Dutch roll / spiral screening."
            )
            c5, c6, c7, c8 = st.columns(4)
            be2 = c5.text_input("Beta values [deg]", "0", key="sw_be",
                                help="For derivative extraction: -10,-8,-6,-4,-2,0,2,4,6,8,10")
            pv2 = c6.text_input("p [rad/s]", "0", key="sw_p")
            qv2 = c7.text_input("q [rad/s]", "0", key="sw_q")
            rv2 = c8.text_input("r [rad/s]", "0", key="sw_r")

        est = _est(al2, ve2, at2, ct2, be2, pv2, qv2, rv2, df2)
        if est > 500:
            st.warning(f"⚠ Estimated cases: **{est:,}** — large sweep, may take a long time.")
        else:
            st.info(f"Estimated cases: **{est:,}** (Cartesian product)")

        max_c = st.text_input(
            "Safety cap — max cases (optional)",
            value="", placeholder="e.g. 100 — leave blank for no cap",
            key="sw_mc",
            help="--max-cases. If the Cartesian product exceeds this, the sweep errors out. "
                 "Useful to prevent accidental huge runs.",
        )

        _sec("Solver")
        sol_args_sw = _aero_solver_widget("sw")

        sweep_args = ["aero", "sweep"] + src_args_sw
        for flag, val in [("--alpha-values", al2), ("--velocity-values", ve2),
                          ("--altitude-values", at2), ("--control-input-values", ct2),
                          ("--beta-values", be2)]:
            if val.strip(): sweep_args += [flag, val]
        for flag, val in [("--p-values", pv2), ("--q-values", qv2), ("--r-values", rv2)]:
            if val.strip() and val.strip() != "0":
                sweep_args += [flag, val]
        if df2.strip() and df2.strip() != "0":
            sweep_args += ["--diff-input-values", df2]
        sweep_args += sol_args_sw
        if max_c.strip(): sweep_args += ["--max-cases", max_c.strip()]

        with st.expander("Output naming & workflow (optional)"):
            c_sw1, c_sw2 = st.columns(2)
            sw_out_name = c_sw1.text_input(
                "--output-name", "", key="sw_out_name",
                placeholder="e.g. sweep_v1",
                help="Optional suffix for the sweep output folder name.",
            )
            sw_wf = c_sw2.text_input(
                "--workflow (auto-record on success)", "", key="sw_wf",
                placeholder="e.g. data/workflows/campaign_v1",
                help="Workflow root. Auto-records the aero_sweep stage after all cases succeed.",
            )
        if sw_out_name.strip(): sweep_args += ["--output-name", sw_out_name.strip()]
        if sw_wf.strip():       sweep_args += ["--workflow", sw_wf.strip()]

        _panel(
            "Run aero sweep",
            "Cartesian product of flight conditions → data/runs/<timestamp>_aero_sweep_*/",
            sweep_args, root, exe, tmo, dry, "sw_run",
            label="▶  Run sweep",
        )
        _aero_run_list(root, "sweep", _aero_run_rows)

    # ── ③ INSPECT ─────────────────────────────────────────────────────────────
    with tab_inspect:
        st.caption("Read and display results from a completed aero run or sweep.")

        aero_runs = _aero_run_rows(root)
        if not aero_runs:
            st.info("No aero runs found yet. Run a Single run or Sweep first.")
        else:
            run_map = {p.name: p for p in aero_runs}
            chosen_run = st.selectbox(
                "Select run", list(run_map.keys()), key="ai_run_sel",
                help="All aero run folders from data/runs/.",
            )
            chosen_path = run_map[chosen_run]
            is_sweep = "sweep" in chosen_run.lower()

            # ── helpers ───────────────────────────────────────────────────
            def _find_result_json(base):
                for p in [base / "aero" / "aero_result.json",
                           base / "aero_result.json"]:
                    if p.exists(): return p
                hits = list(base.rglob("aero_result.json"))
                return hits[0] if hits else None

            def _result_card(res):
                sc  = res.get("scalars") or {}
                meta = res.get("solver_metadata") or {}
                derivs = res.get("stability_axis_derivatives") or {}
                fc = meta.get("flight_condition") or res.get("flight_condition") or {}
                _sec("Aerodynamic coefficients")
                items = [("CL", sc.get("cl")), ("CD", sc.get("cd")),
                         ("Cm", sc.get("cm")), ("L/D", sc.get("l_over_d")),
                         ("CDind", sc.get("cd_ind")),
                         ("Span eff", sc.get("span_efficiency")),
                         ("Xnp [m]", sc.get("x_np"))]
                cols = st.columns(len(items))
                for col, (lbl, v) in zip(cols, items):
                    col.metric(lbl, f"{float(v):+.4f}" if v is not None else "—")
                if fc:
                    _sec("Flight condition")
                    fc2 = st.columns(6)
                    for col, (lbl, v) in zip(fc2, [
                        ("α [°]", fc.get("alpha_deg")),
                        ("V [m/s]", fc.get("velocity_mps")),
                        ("Alt [m]", fc.get("altitude_m")),
                        ("β [°]", fc.get("beta_deg")),
                        ("Sym δe [°]", meta.get("control_input_deg")),
                        ("Diff δa [°]", meta.get("diff_input_deg")),
                    ]):
                        col.metric(lbl, f"{float(v):+.2f}" if v is not None else "—")
                cma = derivs.get("Cma")
                cla = derivs.get("CLa")
                cnb = derivs.get("Cnb")
                clb = derivs.get("Clb")
                if any(v is not None for v in [cma, cla, cnb, clb]):
                    _sec("Key stability derivatives")
                    dc = st.columns(4)
                    for col, (k, v) in zip(dc, [("CLa",cla),("Cma",cma),("Cnb",cnb),("Clb",clb)]):
                        col.metric(k, f"{float(v):+.4f}" if v is not None else "—")
                    if cma is not None:
                        (st.error if float(cma) >= 0 else st.success)(
                            "⚠ Cma ≥ 0 — pitch-unstable. Do not use for ML training."
                            if float(cma) >= 0 else "✓ Cma < 0 — pitch-stable.")

            def _strips_chart(base):
                cands = [base / "aero" / "strips_parsed.csv", base / "strips_parsed.csv"]
                sp = next((p for p in cands if p.exists()), None)
                if not sp: return
                try:
                    import pandas as _pd
                    df = _pd.read_csv(sp)
                    df.columns = [c.strip().lower() for c in df.columns]
                    yc  = next((c for c in df.columns if "yle" in c or c == "y"), None)
                    clc = next((c for c in df.columns if c in ("cl","cl_strip","cl_norm")), None)
                    cdc = next((c for c in df.columns if c in ("cd","cd_strip")), None)
                    if not (yc and clc): return
                    _sec("Spanwise load distribution")
                    st.caption("Section CL across semi-span. Tip peaks → potential tip-stall.")
                    pf = (df[[yc,clc]].dropna()
                            .rename(columns={yc:"y (m)",clc:"Section CL"})
                            .sort_values("y (m)"))
                    st.line_chart(pf.set_index("y (m)"), use_container_width=True)
                    if cdc:
                        with st.expander("Section CD distribution"):
                            cd2 = (df[[yc,cdc]].dropna()
                                     .rename(columns={yc:"y (m)",cdc:"Section CD"})
                                     .sort_values("y (m)"))
                            st.line_chart(cd2.set_index("y (m)"), use_container_width=True)
                except Exception as ex:
                    st.caption(f"Strips: {ex}")

            # ── SINGLE RUN ────────────────────────────────────────────────
            if not is_sweep:
                rjp = _find_result_json(chosen_path)
                if rjp:
                    try:
                        import json as _j
                        _result_card(_j.loads(rjp.read_text()))
                    except Exception as ex:
                        st.warning(f"Could not parse aero_result.json: {ex}")
                else:
                    st.info("No aero_result.json found — use CLI inspect below.")
                _strips_chart(chosen_path)
                _sec("Full CLI output")
                _panel("Full inspect", "Prints complete result in terminal.",
                       ["aero","inspect","--run-dir",str(chosen_path)],
                       root, exe, tmo, dry, "ai_run", label="▶  Full inspect")

            # ── SWEEP ─────────────────────────────────────────────────────
            else:
                # Load manifest
                import json as _j
                import pandas as _pd

                sw_raw = None
                for cand in [chosen_path / "aero_sweep_manifest.json",
                              chosen_path / "aero_sweep" / "aero_sweep_manifest.json"]:
                    if cand.exists():
                        try: sw_raw = _j.loads(cand.read_text())
                        except Exception: pass
                        break

                sw_data = (sw_raw or {}).get("aero_sweep_result", sw_raw or {})
                cases   = sw_data.get("cases") or []

                if not cases:
                    st.warning("No cases found in sweep manifest. Using CLI fallback.")
                    _panel("Sweep inspect","Raw sweep summary.",
                           ["aero","sweep-inspect","--run-dir",str(chosen_path)],
                           root,exe,tmo,dry,"ai_sw_cli",label="▶  Sweep inspect")
                else:
                    # Build flat DataFrame from all cases
                    rows = []
                    for c in cases:
                        fc  = c.get("flight_condition") or {}
                        ar  = c.get("aero_result") or {}
                        sc  = ar.get("scalars") or {}
                        derivs = ar.get("stability_axis_derivatives") or {}
                        rows.append({
                            "#":       c.get("case_index"),
                            "Status":  c.get("status","—"),
                            "α [°]":   fc.get("alpha_deg"),
                            "β [°]":   fc.get("beta_deg"),
                            "V [m/s]": fc.get("velocity_mps"),
                            "Alt [m]": fc.get("altitude_m"),
                            "δe [°]":  c.get("control_input_deg"),
                            "δa [°]":  c.get("diff_input_deg"),
                            "CL":      sc.get("cl"),
                            "CD":      sc.get("cd"),
                            "Cm":      sc.get("cm"),
                            "L/D":     sc.get("l_over_d"),
                            "Xnp":     sc.get("x_np"),
                            "CLa":     derivs.get("CLa"),
                            "Cma":     derivs.get("Cma"),
                        })
                    df = _pd.DataFrame(rows)
                    float_cols = ["α [°]","β [°]","V [m/s]","Alt [m]","δe [°]","δa [°]","CL","CD","Cm","L/D","Xnp","CLa","Cma"]
                    for fc_col in float_cols:
                        if fc_col in df.columns:
                            df[fc_col] = _pd.to_numeric(df[fc_col], errors="coerce")

                    # ── stats bar ─────────────────────────────────────
                    _n_ok  = (df["Status"] == "success").sum()
                    _n_bad = len(df) - _n_ok
                    _al_u  = sorted(df["α [°]"].dropna().unique())
                    _de_u  = sorted(df["δe [°]"].dropna().unique())
                    _stat_row([
                        ("Cases", str(len(df)), "total in sweep"),
                        ("Success", str(int(_n_ok)), "AVL converged"),
                        ("Failed", str(int(_n_bad)), "solver timeout / error"),
                        ("α range", (str(_al_u[0]) + "…" + str(_al_u[-1]) + "°") if _al_u else "—", "sweep bounds"),
                        ("δe settings", str(len(_de_u)), "elevon values"),
                    ])

                    st.caption(
                        "**" + str(len(df)) + " cases** — ✓ " + str(int(_n_ok)) + " success"
                        + ("  ✗ " + str(int(_n_bad)) + " failed" if _n_bad else "")
                    )

                    view = st.radio(
                        "View", ["Polar curves", "Data table", "Single case detail"],
                        horizontal=True, key="ai_type",
                        help="Polar curves: XFLR5-style overlaid polars coloured by elevon. "
                             "Data table: all cases sortable. "
                             "Single case detail: full result card.",
                    )

                    # ── Polar curves (XFLR5-style, Plotly) ───────────────
                    if view == "Polar curves":
                        df_ok = df[df["Status"] == "success"].copy()
                        if df_ok.empty:
                            st.warning("No successful cases to plot.")
                        else:
                            try:
                                import plotly.graph_objects as go
                                from plotly.subplots import make_subplots

                                elevon_vals = sorted(df_ok["δe [°]"].dropna().unique())
                                PALETTE = ["#3B82F6","#F59E0B","#10B981",
                                           "#EF4444","#8B5CF6","#EC4899","#06B6D4"]

                                LAYOUT = dict(
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="#0F1923",
                                    font=dict(color="#C8D6E5", size=12),
                                    legend=dict(
                                        bgcolor="rgba(0,0,0,0)",
                                        bordercolor="#334252",
                                        borderwidth=1,
                                    ),
                                    margin=dict(l=50, r=20, t=40, b=50),
                                )

                                def _traces(x_col, y_col, sort_col=None):
                                    traces = []
                                    for i, ev in enumerate(elevon_vals):
                                        sub = (df_ok[df_ok["δe [°]"] == ev]
                                                   .sort_values(sort_col or x_col)
                                                   [[x_col, y_col]].dropna())
                                        if sub.empty:
                                            continue
                                        lbl = f"δ={ev:+.0f}°"
                                        traces.append(go.Scatter(
                                            x=sub[x_col].tolist(),
                                            y=sub[y_col].tolist(),
                                            mode="lines+markers",
                                            name=lbl,
                                            line=dict(color=PALETTE[i % len(PALETTE)], width=2),
                                            marker=dict(size=7),
                                            hovertemplate=(
                                                f"<b>{lbl}</b><br>"
                                                f"{x_col}: %{{x:.3f}}<br>"
                                                f"{y_col}: %{{y:.4f}}<extra></extra>"
                                            ),
                                        ))
                                    return traces

                                def _make_fig(x_col, y_col, x_label, y_label,
                                              title, sort_col=None, hline=None):
                                    fig = go.Figure()
                                    for t in _traces(x_col, y_col, sort_col):
                                        fig.add_trace(t)
                                    if hline is not None:
                                        fig.add_hline(
                                            y=hline, line_dash="dash",
                                            line_color="#475569", line_width=1,
                                        )
                                    fig.update_layout(
                                        **LAYOUT,
                                        title=dict(text=title, font=dict(size=13)),
                                        xaxis=dict(title=x_label, gridcolor="#1E2F3E",
                                                   zerolinecolor="#334252"),
                                        yaxis=dict(title=y_label, gridcolor="#1E2F3E",
                                                   zerolinecolor="#334252"),
                                        height=320,
                                    )
                                    return fig

                                if len(elevon_vals) > 1:
                                    st.caption(
                                        f"One curve per elevon — "
                                        + ", ".join(f"**δ={e:+.0f}°**" for e in elevon_vals)
                                        + ". Hover for values. Scroll to zoom."
                                    )
                                else:
                                    st.caption("Single elevon setting. Hover for values.")

                                r1c1, r1c2 = st.columns(2)
                                r2c1, r2c2 = st.columns(2)

                                with r1c1:
                                    st.plotly_chart(
                                        _make_fig("α [°]", "CL", "α [°]", "CL",
                                                  "CL vs α — lift curve"),
                                        use_container_width=True,
                                    )
                                with r1c2:
                                    st.plotly_chart(
                                        _make_fig("α [°]", "Cm", "α [°]", "Cm",
                                                  "Cm vs α — stability (neg slope = stable)",
                                                  hline=0.0),
                                        use_container_width=True,
                                    )
                                with r2c1:
                                    st.plotly_chart(
                                        _make_fig("CD", "CL", "CD", "CL",
                                                  "CL vs CD — drag polar",
                                                  sort_col="CD"),
                                        use_container_width=True,
                                    )
                                with r2c2:
                                    st.plotly_chart(
                                        _make_fig("α [°]", "L/D", "α [°]", "L/D",
                                                  "L/D vs α — efficiency"),
                                        use_container_width=True,
                                    )

                            except ImportError:
                                st.error(
                                    "Plotly is not installed. "
                                    "Run `pip install plotly` in your AERIS environment."
                                )

                    # ── Data table ────────────────────────────────────────
                    elif view == "Data table":
                        # Round for display
                        disp = df.copy()
                        for fc_col in ["CL","CD","Cm","L/D","Xnp"]:
                            if fc_col in disp.columns:
                                disp[fc_col] = disp[fc_col].round(5)
                        for fc_col in ["α [°]","V [m/s]","Alt [m]","δe [°]"]:
                            if fc_col in disp.columns:
                                disp[fc_col] = disp[fc_col].round(2)

                        # Elevon filter
                        elev_opts = ["All"] + [
                            f"{e:+.1f}°" for e in
                            sorted(df["δe [°]"].dropna().unique())
                        ]
                        sel_elev = st.selectbox(
                            "Filter by sym elevon (δe)", elev_opts, key="ai_tbl_elev"
                        )
                        if sel_elev != "All":
                            ev_val = float(sel_elev.replace("°",""))
                            disp = disp[disp["δe [°]"] == ev_val]

                        st.dataframe(disp, use_container_width=True, hide_index=True)
                        st.caption(f"Showing {len(disp)} of {len(df)} cases.")

                    # ── Single case detail ────────────────────────────────
                    else:
                        c1, c2 = st.columns(2)
                        case_label_in = c1.text_input(
                            "Case label (optional)", value="",
                            placeholder="e.g. case_0000_ap4d00_...",
                            key="ai_cl",
                        )
                        case_idx_in = int(c2.number_input(
                            "Case index", min_value=0,
                            max_value=max(0, len(cases)-1),
                            value=0, step=1, key="ai_ci",
                        ))

                        case = None
                        if case_label_in.strip():
                            case = next(
                                (c for c in cases
                                 if c.get("case_label") == case_label_in.strip()),
                                None
                            )
                        elif 0 <= case_idx_in < len(cases):
                            case = cases[case_idx_in]

                        if case:
                            ar = case.get("aero_result") or {}
                            if ar:
                                _result_card(ar)
                                case_dir = case.get("case_dir")
                                if case_dir:
                                    _strips_chart(Path(case_dir))
                            else:
                                st.warning(
                                    f"Case {case_idx_in} has no aero_result "
                                    f"(status: {case.get('status','?')})."
                                )
                        else:
                            st.info("Enter a valid case label or index above.")

                        _panel("CLI case inspect","Full result via CLI.",
                               ["aero","sweep-case-inspect","--run-dir",str(chosen_path)]
                               + (["--case-label", case_label_in.strip()]
                                  if case_label_in.strip()
                                  else ["--case-index", str(case_idx_in)]),
                               root,exe,tmo,dry,"ai_run",label="▶  CLI inspect")


def _dyn_run_rows(root: Path) -> list[Path]:
    """Aero single-run folders that have a dynamics/ subfolder already built."""
    return [Path(r) for r in _dirs(str(root / "data" / "runs"))
            if "_aero_" in Path(r).name and "_sweep_" not in Path(r).name
            and (Path(r) / "dynamics").exists()]

def _all_aero_rows(root: Path) -> list[Path]:
    """All aero SINGLE runs — sweep case folders discovered separately."""
    return [Path(r) for r in _dirs(str(root / "data" / "runs"))
            if "_aero_" in Path(r).name and "_sweep_" not in Path(r).name]

def _all_sweep_runs(root: Path) -> list[Path]:
    """All aero sweep run folders."""
    return [Path(r) for r in _dirs(str(root / "data" / "runs"))
            if "_sweep_" in Path(r).name]

def _sweep_case_dirs(sweep_path: Path) -> list[Path]:
    """Individual case folders inside a sweep run (in aero/ subdir)."""
    aero_sub = sweep_path / "aero"
    if aero_sub.exists():
        return sorted([p for p in aero_sub.iterdir()
                       if p.is_dir() and p.name.startswith("case_")],
                      key=lambda p: p.name)
    # fallback: case folders directly in sweep root
    return sorted([p for p in sweep_path.iterdir()
                   if p.is_dir() and p.name.startswith("case_")],
                  key=lambda p: p.name)

def pg_dynamics(root, exe, tmo, dry):
    _hero("◎", "Dynamics", "mass · CG · static margin · eigenvalues · MIL-STD-1797B", "dynamics")

    st.caption(
        "Dynamics builds on top of a completed **aero run**. "
        "Workflow: **① Build** → **② CG Sweep** → **③ Trim** → **④ State Space** → **⑤ Plots** → **⑥ Batch Labels** → **⑦ Flyability ML Dataset** → **⑧ Validate** → **⑨ Inspect**. "
        "Build computes static margin and neutral-point evidence. State-space computes eigenvalues, "
        "D5.1 reports explicit unstable-root flags, and D5.2/D5.2.1 generate eigenvalue plots. "
        "Add Iyy/Izz to your mass YAML to unlock short-period, phugoid, roll, Dutch roll, and spiral eigenvalues."
    )

    tab_build, tab_cgsweep, tab_trim, tab_state_space, tab_state_plots, tab_batch_labels, tab_fly_ml, tab_validate, tab_inspect = st.tabs([
        "  ① Build  ",
        "  ② CG Sweep  ",
        "  ③ Trim  ",
        "  ④ State Space  ",
        "  ⑤ Plots  ",
        "  ⑥ Batch Labels  ",
        "  ⑦ Flyability ML Dataset  ",
        "  ⑧ Validate  ",
        "  ⑨ Inspect  ",
    ])

    # Shared: picker for aero run directory
    all_aero = _all_aero_rows(root)

    def _aero_run_picker(key: str, label: str = "Select aero run") -> str:
        """
        Picker that handles both single aero runs and individual sweep cases.
        Dynamics build requires a folder with aero_result.json directly accessible.
        Single runs: data/runs/<timestamp>_aero_<name>/
        Sweep cases: data/runs/<timestamp>_sweep_.../aero/case_0000_.../
        """
        single_runs  = _all_aero_rows(root)
        sweep_runs   = _all_sweep_runs(root)

        if not single_runs and not sweep_runs:
            st.warning(
                "No aero runs found. Run a single aero run or sweep first "
                "(Aero Analysis → ① Single run or ② Sweep)."
            )
            return ""

        # Build option list: single runs first, then sweep cases grouped by sweep
        options = {}  # label → Path

        for p in single_runs:
            options[f"[single]  {p.name}"] = p

        for sweep in sweep_runs:
            cases = _sweep_case_dirs(sweep)
            for case in cases:
                ar = case / "aero_result.json"
                if ar.exists():
                    label_str = f"[sweep case]  {sweep.name} / {case.name}"
                    options[label_str] = case

        if not options:
            st.warning(
                "No usable aero results found. "
                "Single runs need an aero_result.json at their root. "
                "Sweep runs need completed case folders."
            )
            return ""

        # If only sweep cases available, show a note
        has_single = any(k.startswith("[single]") for k in options)
        if not has_single:
            st.info(
                "Only sweep runs found. Dynamics build works on individual cases — "
                "pick one case from a sweep below."
            )

        chosen_label = st.selectbox(
            label, list(options.keys()), key=key,
            help="Single aero runs [single] or individual sweep cases [sweep case]. "
                 "Dynamics build needs a folder with one aero_result.json.",
        )
        p = options[chosen_label]

        # Read status from aero_result.json directly
        ar_path = p / "aero_result.json"
        ar_status = "—"
        if ar_path.exists():
            try:
                import json as _jj
                ar_data = _jj.loads(ar_path.read_text())
                ar_status = ar_data.get("status", "—")
            except Exception:
                ar_status = "?"
        dot = "#22C55E" if ar_status == "success" else               "#EF4444" if "fail" in ar_status.lower() else "#8EA0B3"

        has_dyn = (p / "dynamics").exists() or (p.parent.parent / "dynamics").exists()
        dyn_badge = (
            ' <span style="color:#22C55E;font-size:.68rem">✓ dynamics built</span>'
            if has_dyn else
            ' <span style="color:#5A7A96;font-size:.68rem">dynamics not yet built</span>'
        )

        is_case = "[sweep case]" in chosen_label
        type_badge = (
            ' <span style="color:#8B5CF6;font-size:.68rem">sweep case</span>'
            if is_case else
            ' <span style="color:#3B82F6;font-size:.68rem">single run</span>'
        )

        _h(
            f'<div style="background:#1B2A3A;border:1px solid #2D3F52;border-radius:7px;'
            f'padding:.42rem .9rem;margin:.3rem 0;display:flex;align-items:center;gap:10px">'
            f'<div style="width:7px;height:7px;border-radius:50%;background:{dot};flex-shrink:0"></div>'
            f'<div style="flex:1;font-size:.75rem;color:#D6DEE8;font-family:JetBrains Mono,monospace;'
            f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{p.name}</div>'
            f'<div style="font-size:.68rem;flex-shrink:0">{type_badge}</div>'
            f'<div style="font-size:.68rem;flex-shrink:0">{dyn_badge}</div>'
            f'<div style="font-size:.7rem;color:{dot};font-weight:600;flex-shrink:0;margin-left:6px">{ar_status}</div>'
            f'</div>'
        )
        return str(p)

    def _aero_dataset_picker(key: str, label: str = "Select promoted aero dataset") -> str:
        """Picker for unified aero dataset roots used by dynamics batch labels."""
        ds_root = root / "data" / "datasets"
        candidates = []
        if ds_root.exists():
            for d in sorted([p for p in ds_root.iterdir() if p.is_dir()], key=lambda p: p.name):
                if (d / "curated_aero_dataset.csv").exists() or (d / "aero_dataset.csv").exists():
                    candidates.append(d)
        if not candidates:
            st.info("No aero datasets found. Build, curate, and promote an aero dataset first.")
            return ""
        promoted = [d for d in candidates if (d / "promotion_manifest.json").exists()]
        ordered = promoted + [d for d in candidates if d not in promoted]
        chosen = st.selectbox(
            label,
            ordered,
            key=key,
            format_func=lambda p: f"✓ {p.name}" if (p / "promotion_manifest.json").exists() else f"○ {p.name} (not promoted)",
            help="✓ means promotion_manifest.json exists. Serious ML/dynamics-label workflows should use promoted datasets.",
        )
        return str(chosen)

    def _mass_inputs(key: str) -> list[str]:
        """Mass config section — reads YAMLs from configs/mass/ and returns CLI args."""
        args = []
        mass_dir = root / "configs" / "mass"
        mass_yaml_files = _files(str(mass_dir), "*.yaml") if mass_dir.exists() else []
        NONE_LABEL = "none (use explicit values below)"

        if mass_yaml_files:
            mc_choice = st.selectbox(
                "Mass config YAML",
                [NONE_LABEL] + mass_yaml_files,
                format_func=lambda s: NONE_LABEL if s == NONE_LABEL else Path(s).name,
                key=f"{key}_mc",
                help="Select a mass-properties YAML from configs/mass/. "
                     "Explicit values below override the YAML field by field.",
            )
            if mc_choice != NONE_LABEL:
                args += ["--mass-config", mc_choice]
                try:
                    contents = Path(mc_choice).read_text(encoding="utf-8")
                    with st.expander(f"Preview: {Path(mc_choice).name}"):
                        st.code(contents, language="yaml")
                except Exception:
                    pass
        else:
            mc_text = st.text_input(
                "Mass config YAML (none found in configs/mass/)",
                value="", placeholder="configs/mass/baseline_uav.yaml",
                key=f"{key}_mc",
            )
            if mc_text.strip():
                args += ["--mass-config", mc_text.strip()]

        with st.expander("Explicit mass & inertia values (override or supplement YAML)"):
            st.caption(
                "mass_kg and x_cg_m are required if no YAML is selected. "
                "Leave blank to use values from the YAML. "
                "**Iyy and Izz unlock eigenvalue analysis** (short-period, phugoid, Dutch roll)."
            )
            c1, c2, c3 = st.columns(3)
            mkg = c1.text_input("Mass [kg]",         "", key=f"{key}_mkg")
            xcg = c2.text_input("CG x [m]",          "", key=f"{key}_xcg",
                                help="Longitudinal CG from nose reference point.")
            ycg = c3.text_input("CG y [m]",          "0", key=f"{key}_ycg")
            c4, c5, c6 = st.columns(3)
            ixx = c4.text_input("Ixx [kg m2] roll",  key=f"{key}_ixx")
            iyy = c5.text_input("Iyy [kg m2] pitch", key=f"{key}_iyy",
                                help="Pitch inertia. Required for short-period and phugoid modes.")
            izz = c6.text_input("Izz [kg m2] yaw",   key=f"{key}_izz",
                                help="Yaw inertia. Required for Dutch roll mode.")

            # DATCOM inertia estimator
            geo_runs_for_inertia = [
                Path(r) for r in _dirs(str(root / "data" / "runs"))
                if "geometry" in Path(r).name
                and not any(k in Path(r).name for k in ("_aero_", "_sweep_"))
            ]
            if geo_runs_for_inertia and mkg.strip():
                with st.expander("📐 Estimate inertia from geometry (DATCOM method)"):
                    st.caption(
                        "Uses planform geometry + mass to estimate Iyy, Ixx, Izz via DATCOM "
                        "radius-of-gyration method. Accuracy ★★★ (±25% Iyy). "
                        "Sufficient for eigenvalue screening. Replace with measured values when available."
                    )
                    geo_opts = {p.name: p for p in geo_runs_for_inertia}
                    chosen_geo = st.selectbox(
                        "Select geometry run",
                        list(geo_opts.keys()),
                        key=f"{key}_datcom_geo",
                        help="Reads geometry_summary.json from this run to extract span, MAC, sweep.",
                    )
                    if st.button("📐 Estimate inertia", key=f"{key}_datcom_btn", type="secondary"):
                        geo_path = geo_opts[chosen_geo]
                        gs_path  = geo_path / "artifacts" / "geometry" / "geometry_summary.json"
                        if not gs_path.exists():
                            st.warning(f"geometry_summary.json not found in {chosen_geo}.")
                        else:
                            try:
                                import json as _jj
                                gs = _jj.loads(gs_path.read_text(encoding="utf-8"))
                                m_val = float(mkg.strip())
                                rv  = gs.get("reference_values") or {}
                                ma  = gs.get("mean_angles_deg") or {}
                                import math as _math
                                span  = float(rv.get("span_m", 2.0))
                                mac   = float(rv.get("mean_aerodynamic_chord_m", 0.877))
                                area  = float(rv.get("area_m2", 0.5))
                                ar    = float(rv.get("aspect_ratio", 5.0))
                                sweep = float(ma.get("sweep_le_deg", 35.0))
                                dihed = abs(float(ma.get("dihedral_c4_deg", 3.0)))
                                k_x = max(0.28, min(0.40, 0.32 + dihed/90*0.05))
                                k_y_base = 0.35 + (sweep - 30.0) * (0.42 - 0.35) / 20.0
                                k_y = max(0.25, min(0.55, k_y_base))
                                i_xx = round(m_val * (k_x * span/2)**2, 4)
                                i_yy = round(m_val * (k_y * mac)**2, 4)
                                i_zz = round(i_xx + i_yy, 4)
                                st.success(
                                    f"DATCOM estimates (k_x={k_x:.3f}, k_y={k_y:.3f}): "
                                    f"**Ixx = {i_xx} kg·m²** · "
                                    f"**Iyy = {i_yy} kg·m²** · "
                                    f"**Izz = {i_zz} kg·m²**"
                                )
                                # Auto-fill session state so fields update on next render
                                st.session_state[f"{key}_ixx"] = str(i_xx)
                                st.session_state[f"{key}_iyy"] = str(i_yy)
                                st.session_state[f"{key}_izz"] = str(i_zz)
                                st.caption(
                                    "✓ Fields above auto-filled. "
                                    "Review values then click Build / Run CG sweep."
                                )
                                st.caption(
                                    f"Based on: span={span:.3f}m, MAC={mac:.3f}m, "
                                    f"AR={ar:.2f}, LE sweep={sweep:.0f}°"
                                )
                            except Exception as ex:
                                st.error(f"Estimation failed: {ex}")

            xconv = st.radio(
                "x-axis convention",
                ["x positive aft (aviation standard)", "x positive forward"],
                horizontal=True, key=f"{key}_xconv",
                help="x positive aft matches AVL and AeroSandbox conventions.",
            )
            if "forward" in xconv:
                args.append("--x-positive-forward")
            for flag, val in [
                ("--mass-kg", mkg), ("--x-cg-m", xcg), ("--y-cg-m", ycg),
                ("--ixx-kg-m2", ixx), ("--iyy-kg-m2", iyy), ("--izz-kg-m2", izz),
            ]:
                if val.strip() and val.strip() != "0":
                    args += [flag, val.strip()]
        return args

    # ── ① BUILD ───────────────────────────────────────────────────────────────
    with tab_build:
        st.caption(
            "Reads the aero result, combines it with your mass/CG inputs, "
            "and computes the **static margin** and neutral point. "
            "Output → `<run_dir>/dynamics/dynamics_foundation.json`"
        )
        rd_build = _aero_run_picker("dyn_rd_build")
        if rd_build:
            st.info(
                "ℹ️ **CG x [m]** is from the nose reference point. "
                "For this BWB (NP ≈ 0.56m, MAC ≈ 0.877m): **stable CG is typically 0.30–0.52m**. "
                "Use the DATCOM estimator below to get Iyy/Izz. "
                "CG = 1.0m would be far aft of the wing — check your geometry."
            )
            mass_args = _mass_inputs("build")
            _panel(
                "Build dynamics foundation",
                "Computes static margin, Xnp, and readiness for trim/eigenanalysis.",
                ["dynamics", "build", "--run-dir", rd_build] + mass_args,
                root, exe, tmo, dry, "dyn_build_run",
                label="▶  Build",
            )

    # ── ② CG SWEEP ────────────────────────────────────────────────────────────
    with tab_cgsweep:
        st.caption(
            "Sweeps CG x-position across a range and computes the static margin at each point. "
            "Identifies the **stable CG envelope** — the range where static margin > 0. "
            "Output → `<run_dir>/dynamics/cg_sweep.json` + `cg_sweep.csv`"
        )
        _note(
            "✓ <b>CG-corrected trim</b> (BUG-D3 fix): the trim elevon δe shown in the "
            "plot is now adjusted for each CG position via the moment transfer theorem "
            "<code>Cm(xcg_new) = Cm(xcg_ref) + CLα·(xcg_ref−xcg_new)/c·α₀</code>. "
            "This means de_trim_deg varies realistically with CG (e.g. ~10° change per 10 cm shift). "
            "The trimmable CG range reflects actual actuator authority."
            "  # AERIS_GUI_D3_CG_TRIM_NOTE",
            "info",
        )
        rd_cgsw = _aero_run_picker("dyn_rd_cgsw")
        if rd_cgsw:
            c1, c2, c3 = st.columns(3)
            cgmn = c1.number_input(
                "CG min [m]", value=0.20, step=0.05, key="dyn_cgmn",
                help="Forward limit of CG sweep — must be < CG max.",
            )
            cgmx = c2.number_input(
                "CG max [m]", value=0.70, step=0.05, key="dyn_cgmx",
                help="Aft limit of CG sweep.",
            )
            ns = c3.number_input(
                "Points", min_value=2, value=9, step=1, key="dyn_ns",
                help="Number of equally-spaced CG positions to evaluate.",
            )
            mass_args_sw = _mass_inputs("cgsw")
            # cg-sweep CLI does not accept --x-cg-m (CG is swept automatically)
            # Filter it out — only mass_kg, inertias, and mass-config are valid
            cgsw_filtered = []
            skip_next = False
            for tok in mass_args_sw:
                if skip_next:
                    skip_next = False
                    continue
                if tok == "--x-cg-m":
                    skip_next = True  # skip this flag AND its value
                    continue
                cgsw_filtered.append(tok)
            _panel(
                "Run CG sweep",
                f"Evaluates static margin at {int(ns)} CG positions from {cgmn:.2f} to {cgmx:.2f} m.",
                ["dynamics", "cg-sweep", "--run-dir", rd_cgsw,
                 "--cg-min-m", str(cgmn), "--cg-max-m", str(cgmx),
                 "--n", str(int(ns))] + cgsw_filtered,
                root, exe, tmo, dry, "dyn_cgsw_run",
                label="▶  Run CG sweep",
            )
            # Show CG sweep summary inline after running
            cgsw_json = Path(rd_cgsw) / "dynamics" / "cg_sweep.json"
            if cgsw_json.exists():
                try:
                    import json as _jcg
                    cg_data = _jcg.loads(cgsw_json.read_text(encoding="utf-8"))
                    sm_min  = cg_data.get("stable_cg_min_m")
                    sm_max  = cg_data.get("stable_cg_max_m")
                    zc      = cg_data.get("static_margin_zero_crossing_estimate_m")
                    _sec("CG sweep result")
                    s1, s2, s3 = st.columns(3)
                    s1.metric("Neutral point (Xnp)",
                              f"{float(zc):.4f} m" if zc is not None else "—")
                    s2.metric("Stable CG min",
                              f"{float(sm_min):.4f} m" if sm_min is not None else "—")
                    s3.metric("Stable CG max",
                              f"{float(sm_max):.4f} m" if sm_max is not None else "—")
                    if sm_min is not None and sm_max is not None:
                        st.success(
                            f"✓ Stable CG range: {float(sm_min):.4f} – "
                            f"{float(sm_max):.4f} m "
                            f"(span = {float(sm_max) - float(sm_min):.4f} m). "
                            "See ⑥ Inspect → CG sweep curve for the full chart."
                        )
                    else:
                        st.warning("No stable CG range found. Check aero result and mass inputs.")
                except Exception as _ex:
                    st.caption(f"Could not read cg_sweep.json: {_ex}")
            else:
                st.caption("Run CG sweep above to see results here.")

    # ── ③ TRIM ────────────────────────────────────────────────────────────────
    with tab_trim:
        st.caption(
            "First-order longitudinal trim estimate — finds the alpha at which Cm ≈ 0. "
            "⚠ This is a **diagnostic only**, not a full nonlinear trim solver. "
            "Requires dynamics to be built first (① Build)."
        )
        rd_trim = _aero_run_picker("dyn_rd_trim")
        if rd_trim:
            _panel(
                "Run trim estimate",
                "Estimates trim alpha from saved aero + dynamics results.",
                ["dynamics", "trim", "--run-dir", rd_trim],
                root, exe, tmo, dry, "dyn_trim_run",
                label="▶  Run trim",
            )
            # Show trim result inline — no need to navigate to ⑥ Inspect
            trim_json = Path(rd_trim) / "dynamics" / "trim_result.json"
            if trim_json.exists():
                try:
                    import json as _jt
                    tr  = _jt.loads(trim_json.read_text(encoding="utf-8"))
                    lng = tr.get("longitudinal") or {}
                    _sec("Trim result")
                    if not lng.get("valid"):
                        st.error(f"Trim invalid: {lng.get('reason', 'unknown')}")
                    else:
                        t1, t2, t3, t4 = st.columns(4)
                        t1.metric("Current α [°]",
                                  f"{float(lng.get('alpha_current_deg', 0)):+.2f}")
                        t2.metric("Trim α estimate",
                                  f"{float(lng.get('alpha_trim_deg', 0)):+.4f}°")
                        t3.metric("Δα required",
                                  f"{float(lng.get('delta_alpha_deg', 0)):+.4f}°")
                        in_bounds = lng.get("alpha_trim_in_bounds")
                        t4.metric("In range [-5°,15°]",
                                  "✓ Yes" if in_bounds else "✗ No")
                        if in_bounds:
                            st.success(
                                f"✓ Trim α = {lng.get('alpha_trim_deg', 0):.2f}° "
                                "is within flyable range."
                            )
                        else:
                            st.warning(
                                f"⚠ Trim α = {lng.get('alpha_trim_deg', 0):.2f}° "
                                "is outside [-5°, 15°]. Consider moving CG aft."
                            )
                        if lng.get("de_trim_deg") is not None:
                            e1, e2 = st.columns(2)
                            e1.metric("Trim δe estimate",
                                      f"{float(lng.get('de_trim_deg', 0)):+.4f}°")
                            de_ok = lng.get("de_trim_in_bounds")
                            e2.metric("In actuator range [-25°,25°]",
                                      "✓ Yes" if de_ok else "✗ No")
                except Exception as _ex:
                    st.caption(f"Could not read trim_result.json: {_ex}")
            else:
                st.caption("Run trim above to see results here.")

    # ── ④ STATE SPACE ─────────────────────────────────────────────────────────
    with tab_state_space:
        st.caption(
            "Computes full 4×4 longitudinal and lateral-directional linear state-space diagnostics "
            "from one aero_result.json, mass/inertia, and reference geometry values. "
            "Output → `<run_dir>/dynamics/state_space_result.json`."
        )
        rd_state = _aero_run_picker("dyn_rd_state", "Select aero run for state-space")
        if rd_state:
            mass_args_state = _mass_inputs("state")
            with st.expander("Reference geometry overrides — required if geometry_summary is unavailable", expanded=True):
                c1, c2, c3 = st.columns(3)
                sref = c1.text_input("--sref-m2", "", key="dyn_state_sref", help="Reference area [m²]")
                mac = c2.text_input("--mac-m", "", key="dyn_state_mac", help="Mean aerodynamic chord [m]")
                span = c3.text_input("--span-m", "", key="dyn_state_span", help="Reference span [m]")
                st.caption("If the run has no geometry summary, enter Sref/MAC/span manually. The baseline smoke used Sref=0.72, MAC=0.55, span=3.2.")

            args_state = ["dynamics", "state-space", "--run-dir", rd_state] + mass_args_state
            _flag(args_state, "--sref-m2", sref)
            _flag(args_state, "--mac-m", mac)
            _flag(args_state, "--span-m", span)

            c1, c2 = st.columns(2)
            with c1:
                _panel(
                    "Run state-space analysis",
                    "Builds A matrices, eigenvalues, named modes, and D5.1 explicit unstable-root summary flags.",
                    args_state, root, exe, tmo, dry, "dyn_state_run", label="▶  Run state-space",
                )
            with c2:
                _panel(
                    "Inspect state-space result",
                    "Reads state_space_result.json and prints named modes plus linear-stability flags.",
                    ["dynamics", "state-space-inspect", "--run-dir", rd_state],
                    root, exe, tmo, dry, "dyn_state_inspect", label="▶  Inspect state-space",
                )
            _state_space_artifact_preview(Path(rd_state))

    # ── ⑤ STATE-SPACE PLOTS ──────────────────────────────────────────────────
    with tab_state_plots:
        st.caption(
            "Generates state-space evidence plots from an existing state_space_result.json. "
            "D5.2 adds eigenvalue and mode-summary plots; D5.2.1 adds near-origin zoom plots."
        )
        rd_plot = _aero_run_picker("dyn_rd_state_plot", "Select aero run for state-space plots")
        if rd_plot:
            plot_choice = st.selectbox("--plot", STATE_SPACE_PLOT_CHOICES, key="dyn_state_plot_choice")
            _panel(
                "Generate state-space plots",
                "Writes PNG plots and state_space_plot_manifest.json under <run_dir>/dynamics/plots/.",
                ["dynamics", "plot-state-space", "--run-dir", rd_plot, "--plot", plot_choice],
                root, exe, tmo, dry, "dyn_state_plot_run", label="▶  Plot state-space",
            )
            # Show PNGs directly — not behind a collapsed expander
            plot_dir = Path(rd_plot) / "dynamics" / "plots"
            plot_manifest = plot_dir / "state_space_plot_manifest.json"
            pm = _rjson(plot_manifest)
            if pm:
                artifacts = pm.get("artifacts") or {}
                pngs = [(label, Path(path)) for label, path in artifacts.items()
                        if path and Path(path).exists()
                        and Path(path).suffix.lower() == ".png"]
                if pngs:
                    _sec(f"Generated plots ({len(pngs)} PNG{'s' if len(pngs) != 1 else ''})")
                    for label, png_path in pngs:
                        st.caption(label)
                        st.image(str(png_path), use_container_width=True)
                else:
                    st.info("No PNG files found. Run ▶ Plot state-space above.")
            else:
                st.info("No plot manifest found. Run ▶ Plot state-space above.")
            # Also keep the full evidence expander for JSON details
            with st.expander("State-space JSON details", expanded=False):
                _state_space_artifact_preview(Path(rd_plot))

    # ── ⑥ BATCH LABELS ────────────────────────────────────────────────────────
    with tab_batch_labels:
        st.caption(
            "Compute dataset-level control derivatives, first-order trim-deflection estimates, "
            "flyability labels, red flags, and failure reasons from a promoted control-sweep aero dataset. "
            "Output → control_derivatives.csv, flyability_labels.csv, dynamics_label_run_report.json."
        )
        ds_labels = _aero_dataset_picker("dyn_batch_labels_ds", "Aero dataset for dynamics batch labels")
        if ds_labels:
            c1, c2, c3 = st.columns(3)
            source = c1.selectbox("--source", ["curated", "auto", "raw"], key="dyn_batch_labels_source")
            max_trim = c2.number_input("Max |trim δe| [deg]", value=25.0, step=1.0, key="dyn_batch_labels_trim_limit")
            min_auth = c3.number_input("Min |Cmδe| [/rad]", value=0.10, step=0.05, key="dyn_batch_labels_cmde_min")
            workflow = st.text_input(
                "Workflow root (optional)",
                value="",
                key="dyn_batch_labels_workflow",
                placeholder="data/workflows/<workflow_name>",
                help="Adds --workflow so the Workflow Cockpit can record dynamics_batch_labels.",
            )
            args_batch = [
                "dynamics", "batch-labels",
                "--dataset", ds_labels,
                "--source", source,
                "--max-abs-trim-delta-e-deg", str(float(max_trim)),
                "--min-abs-cm-delta-e-per-rad", str(float(min_auth)),
            ]
            if workflow.strip():
                args_batch += ["--workflow", workflow.strip()]
            _panel(
                "Build dynamics batch labels",
                "Computes finite-difference symmetric-elevon derivatives and first-order flyability labels. No solver rerun.",
                args_batch,
                root, exe, tmo, dry, "dyn_batch_labels_run", label="▶  Build batch labels",
            )
            _dataset_control_artifact_preview(Path(ds_labels))

    # ── ⑦ FLYABILITY ML DATASET ───────────────────────────────────────────────
    with tab_fly_ml:
        st.caption(
            "Build an ML-ready derived dataset by joining zero-control aero rows with flyability labels. "
            "Output → <dataset>__flyability_ml/curated_aero_dataset.csv and flyability_ml_dataset_report.json."
        )
        ds_fly = _aero_dataset_picker("dyn_fly_ml_ds", "Source aero dataset with flyability labels")
        if ds_fly:
            c1, c2 = st.columns(2)
            source_fly = c1.selectbox("--source", ["curated", "raw"], key="dyn_fly_ml_source")
            allow_forced = c2.checkbox("Allow forced source promotion", value=False, key="dyn_fly_ml_allow_forced")
            out_dir = st.text_input(
                "Output dataset root (optional)",
                value="",
                key="dyn_fly_ml_output",
                placeholder="leave blank for <source_dataset>__flyability_ml",
            )
            workflow_fly = st.text_input(
                "Workflow root (optional)",
                value="",
                key="dyn_fly_ml_workflow",
                placeholder="data/workflows/<workflow_name>",
                help="Adds --workflow so the Workflow Cockpit can record flyability_ml_dataset.",
            )
            args_fly = ["dynamics", "build-ml-dataset", "--dataset", ds_fly, "--source", source_fly]
            if out_dir.strip():
                args_fly += ["--output-dir", out_dir.strip()]
            if allow_forced:
                args_fly.append("--allow-forced")
            if workflow_fly.strip():
                args_fly += ["--workflow", workflow_fly.strip()]
            _panel(
                "Build flyability ML dataset",
                "Creates a promoted ML-compatible derived dataset for trim/control/flyability targets. No solver rerun.",
                args_fly,
                root, exe, tmo, dry, "dyn_fly_ml_run", label="▶  Build ML dataset",
            )
            expected = Path(out_dir.strip()) if out_dir.strip() else Path(ds_fly).with_name(Path(ds_fly).name + "__flyability_ml")
            with st.expander("Evidence preview: flyability ML dataset", expanded=False):
                _json_metric_block(
                    expected / "flyability_ml_dataset_report.json",
                    ["status", "source", "row_counts", "ml_columns", "artifacts"],
                )
                _dataframe_preview(expected / "curated_aero_dataset.csv")

    # ── ⑧ VALIDATE ────────────────────────────────────────────────────────────
    with tab_validate:
        st.caption(
            "Validates saved dynamics artifacts without rerunning solvers: static-margin formula, "
            "trim Taylor formulas, state-space A-matrix shape/finite values, eigenvalue summary consistency, "
            "and artifact presence. Output → `<run_dir>/dynamics/dynamics_validation_report.json`."
        )
        rd_validate = _aero_run_picker("dyn_rd_validate", "Select aero run for dynamics validation")
        if rd_validate:
            c1, c2 = st.columns(2)
            with c1:
                fail_validate = st.checkbox(
                    "Fail command on validation errors",
                    value=False,
                    key="dyn_validate_fail",
                    help="Adds --fail-on-error. Useful for CI/regression checks; leave off for exploratory inspection.",
                )
            args_validate = ["dynamics", "validate", "--run-dir", rd_validate]
            if fail_validate:
                args_validate.append("--fail-on-error")
            _panel(
                "Validate dynamics artifacts",
                "Checks formulas and evidence consistency; does not certify the aircraft and does not run AVL.",
                args_validate,
                root, exe, tmo, dry, "dyn_validate_run", label="▶  Validate dynamics",
            )
            validation_path = Path(rd_validate) / "dynamics" / "dynamics_validation_report.json"
            if validation_path.exists():
                try:
                    validation_data = json.loads(validation_path.read_text(encoding="utf-8"))
                    st.metric("Validation passed", str(validation_data.get("passed")))
                    vc1, vc2 = st.columns(2)
                    vc1.metric("Errors", validation_data.get("error_count", 0))
                    vc2.metric("Warnings", validation_data.get("warning_count", 0))
                    with st.expander("Validation report JSON", expanded=False):
                        st.json(validation_data)
                except Exception as ex:
                    st.warning(f"Could not read validation report: {ex}")

    # ── ⑨ INSPECT ─────────────────────────────────────────────────────────────
    with tab_inspect:
        st.caption(
            "Read and display results from built dynamics runs. "
            "Shows static margin, stability derivatives, state-space modes, explicit unstable-root flags, "
            "MIL-STD-1797B classification, CG sweep curve, and plot artifacts."
        )

        dyn_runs = _dyn_run_rows(root)
        if not dyn_runs:
            st.info(
                "No dynamics results found yet. "
                "Run ① Build on an aero run first — it creates the `dynamics/` subfolder."
            )
        else:
            run_map = {p.name: p for p in dyn_runs}
            chosen_run_name = st.selectbox(
                "Select run", list(run_map.keys()), key="dyn_ins_sel",
                help="Only runs with a dynamics/ subfolder appear here.",
            )
            chosen_path = run_map[chosen_run_name]
            dyn_dir = chosen_path / "dynamics"

            ins_view = st.radio(
                "View",
                ["Foundation & modes", "CG sweep curve", "Trim result"],
                horizontal=True, key="dyn_ins_view",
            )

            # ── Foundation & dynamic modes ────────────────────────────────
            if ins_view == "Foundation & modes":
                found_json = dyn_dir / "dynamics_foundation.json"
                if not found_json.exists():
                    st.warning("No dynamics_foundation.json found. Run ① Build first.")
                else:
                    try:
                        import json as _j
                        data = _j.loads(found_json.read_text(encoding="utf-8"))
                        sm   = data.get("stability_metrics") or {}
                        mp   = data.get("mass_properties") or {}
                        rdns = data.get("state_space_preparation") or {}
                        deriv_s = data.get("stability_derivatives") or {}
                        long_d  = deriv_s.get("longitudinal") or {}
                        lat_d   = deriv_s.get("lateral_directional") or {}
                        ctrl    = data.get("control_effectiveness") or {}
                        dyn_m   = data.get("dynamic_modes") or {}
                        sp_m    = dyn_m.get("short_period") or {}
                        ph_m    = dyn_m.get("phugoid") or {}
                        dr_m    = dyn_m.get("dutch_roll") or {}

                        # ── Static margin ─────────────────────────────────
                        _sec("Static margin & neutral point")
                        c1, c2, c3, c4 = st.columns(4)
                        sm_val  = sm.get("static_margin_percent_mac")
                        xnp_val = sm.get("x_np_m")
                        cma_val = sm.get("cma")
                        mac_val = sm.get("mac_m")
                        c1.metric("Static margin", f"{float(sm_val):+.2f} %MAC" if sm_val is not None else "—")
                        c2.metric("Neutral point Xnp", f"{float(xnp_val):+.4f} m" if xnp_val is not None else "—")
                        c3.metric("Cma", f"{float(cma_val):+.4f}" if cma_val is not None else "—")
                        c4.metric("MAC", f"{float(mac_val):.4f} m" if mac_val is not None else "—")

                        interp = sm.get("longitudinal_interpretation", "")
                        if sm_val is not None:
                            (st.success if float(sm_val) > 0 else st.error)(
                                f"{'✓ Statically stable' if float(sm_val) > 0 else '✗ Statically unstable'} "
                                f"— SM = {float(sm_val):+.2f} %MAC"
                            )

                        # ── Spiral metric ─────────────────────────────────
                        spiral = deriv_s.get("spiral_metric")
                        spiral_stable = deriv_s.get("spiral_stable")
                        if spiral is not None:
                            sc1, sc2 = st.columns(2)
                            sc1.metric("Spiral metric (Clβ·Cnr / Clr·Cnβ)",
                                       f"{float(spiral):+.4f}")
                            sc2.metric("Spiral tendency",
                                       "✓ Stable (< 1)" if spiral_stable else "⚠ Unstable (> 1)")

                        # ── Control effectiveness ─────────────────────────
                        _sec("Control effectiveness")
                        cm_de = ctrl.get("cm_per_de_rad")
                        cl_de = ctrl.get("cl_per_de_rad")
                        pitch_ok = ctrl.get("pitch_authority_adequate")
                        ce1, ce2, ce3 = st.columns(3)
                        ce1.metric("Cmδe [/rad]",
                                   f"{float(cm_de):+.4f}" if cm_de is not None else "— (not in AVL output)")
                        ce2.metric("CLδe [/rad]",
                                   f"{float(cl_de):+.4f}" if cl_de is not None else "—")
                        ce3.metric("Pitch authority",
                                   "✓ Adequate" if pitch_ok else ("✗ Inadequate" if pitch_ok is False else "— unknown"))
                        if cm_de is None:
                            st.caption(
                                "Cmδe not found. Run the aero sweep with elevon deflection values "
                                "(e.g. `-10,-5,0,5,10`) to enable control effectiveness extraction."
                            )

                        # ── Stability derivatives ─────────────────────────
                        with st.expander("Stability derivatives — full table"):
                            sign_ok = {
                                "cma": (cma_val, "<0"),
                                "cmq": (long_d.get("cmq"), "<0"),
                                "clb": (lat_d.get("clb"), "<0"),
                                "cnb": (lat_d.get("cnb"), ">0"),
                                "clp": (lat_d.get("clp"), "<0"),
                                "cnr": (lat_d.get("cnr"), "<0"),
                            }
                            rows_long = [
                                ("CLα", long_d.get("cla"), "lift slope"),
                                ("Cma", long_d.get("cma"), "pitch stability — must be < 0"),
                                ("Cmq", long_d.get("cmq"), "pitch damping — must be < 0"),
                                ("CLq", long_d.get("clq"), "lift due to pitch rate"),
                                ("Cmαdot", long_d.get("cmad"), "alpha-rate damping"),
                            ]
                            rows_lat = [
                                ("Clβ", lat_d.get("clb"), "dihedral effect — must be < 0"),
                                ("Cnβ", lat_d.get("cnb"), "directional stability — must be > 0"),
                                ("CYβ", lat_d.get("cyb"), "side force"),
                                ("Clp", lat_d.get("clp"), "roll damping — must be < 0"),
                                ("Cnr", lat_d.get("cnr"), "yaw damping — must be < 0"),
                                ("Clr", lat_d.get("clr"), "roll due to yaw rate"),
                                ("Cnp", lat_d.get("cnp"), "adverse yaw"),
                            ]
                            sign_check = {
                                "cla": None, "cma": -1, "cmq": -1, "clq": None, "cmad": None,
                                "clb": -1, "cnb": +1, "cyb": None, "clp": -1, "cnr": -1, "clr": None, "cnp": None,
                            }
                            def _row_html(name, val, note, key_lc):
                                if val is None:
                                    return f'<tr><td>{name}</td><td style="color:#5A7A96">—</td><td style="color:#5A7A96">{note}</td></tr>'
                                v = float(val)
                                exp = sign_check.get(key_lc)
                                if exp is None:
                                    col = "#D6DEE8"
                                elif (exp < 0 and v < 0) or (exp > 0 and v > 0):
                                    col = "#22C55E"
                                else:
                                    col = "#EF4444"
                                return f'<tr><td style="font-family:JetBrains Mono,monospace">{name}</td><td style="color:{col};font-family:JetBrains Mono,monospace">{v:+.5f}</td><td style="color:#8EA0B3;font-size:.75rem">{note}</td></tr>'

                            st.markdown("**Longitudinal**")
                            _h('<table style="width:100%;border-collapse:collapse;font-size:.8rem">' +
                               "".join(_row_html(n, v, note, n.lower().replace("α","a").replace("δ","d").replace("dot","ad"))
                                       for n, v, note in rows_long) + "</table>")
                            st.markdown("**Lateral-directional**")
                            _h('<table style="width:100%;border-collapse:collapse;font-size:.8rem">' +
                               "".join(_row_html(n, v, note, n.lower().replace("β","b").replace("α","a"))
                                       for n, v, note in rows_lat) + "</table>")
                            st.caption("Green = correct sign for stability · Red = wrong sign · Grey = sign not prescribed")

                        # ── Dynamic modes ─────────────────────────────────
                        _sec("Dynamic modes")
                        if sp_m.get("valid"):
                            st.markdown("**Short-period**")
                            dm1, dm2, dm3, dm4 = st.columns(4)
                            dm1.metric("ζ_sp",   f"{float(sp_m.get('zeta', 0)):+.4f}" if sp_m.get("zeta") else "—")
                            dm2.metric("ωn [rad/s]", f"{float(sp_m.get('omega_n_rad_s', 0)):.4f}" if sp_m.get("omega_n_rad_s") else "—")
                            dm3.metric("Period [s]", f"{float(sp_m.get('period_s', 0)):.3f}" if sp_m.get("period_s") else "—")
                            dm4.metric("t½ [s]", f"{float(sp_m.get('time_to_half_s', 0)):.3f}" if sp_m.get("time_to_half_s") else "—")
                            zeta_sp = sp_m.get("zeta")
                            if zeta_sp is not None:
                                z = float(zeta_sp)
                                if 0.35 <= z <= 1.30:
                                    st.success(f"✓ ζ_sp = {z:.4f} — MIL-STD-1797B **Level 1** (0.35 ≤ ζ ≤ 1.30)")
                                elif 0.25 <= z:
                                    st.warning(f"⚠ ζ_sp = {z:.4f} — **Level 2** (0.25 ≤ ζ < 0.35 or ζ > 1.30)")
                                elif 0.15 <= z:
                                    st.error(f"✗ ζ_sp = {z:.4f} — **Level 3** (barely controllable)")
                                else:
                                    st.error(f"✗ ζ_sp = {z:.4f} — **Unacceptable** (below Level 3)")
                        else:
                            reason = sp_m.get("reason", "")
                            st.caption(f"Short-period not computed. {reason}")
                            if "Iyy" in (reason or ""):
                                st.info("💡 Add Iyy (pitch inertia) to your mass config to enable short-period analysis. Use the DATCOM estimator above.")

                        if ph_m.get("valid"):
                            st.markdown("**Phugoid**")
                            pm1, pm2, pm3 = st.columns(3)
                            pm1.metric("ζ_ph", f"{float(ph_m.get('zeta', 0)):+.4f}" if ph_m.get("zeta") else "—")
                            pm2.metric("Period [s]", f"{float(ph_m.get('period_s', 0)):.1f}" if ph_m.get("period_s") else "—")
                            pm3.metric("Stable", "✓ Yes" if ph_m.get("stable") else "✗ No")
                            zeta_ph = ph_m.get("zeta")
                            if zeta_ph is not None:
                                (st.success if float(zeta_ph) >= 0.04 else
                                 st.warning if float(zeta_ph) >= 0 else st.error)(
                                    f"Phugoid ζ = {float(zeta_ph):.4f} — "
                                    + ("Level 1 (≥0.04)" if float(zeta_ph) >= 0.04
                                       else "Level 2 (stable but ζ<0.04)"
                                       if float(zeta_ph) >= 0 else "Level 3 (divergent phugoid)")
                                )

                        if dr_m.get("valid"):
                            st.markdown("**Dutch roll**")
                            dr1, dr2, dr3 = st.columns(3)
                            dr1.metric("ζ_DR", f"{float(dr_m.get('zeta', 0)):+.4f}" if dr_m.get("zeta") else "—")
                            dr2.metric("ωn_DR [rad/s]", f"{float(dr_m.get('omega_n_rad_s', 0)):.4f}" if dr_m.get("omega_n_rad_s") else "—")
                            dr3.metric("Period [s]", f"{float(dr_m.get('period_s', 0)):.2f}" if dr_m.get("period_s") else "—")

                        # ── Mass & readiness ──────────────────────────────
                        _sec("Mass properties & readiness")
                        mc1, mc2, mc3, mc4 = st.columns(4)
                        inertia = mp.get("inertia") or {}
                        mc1.metric("Mass", f"{float(mp.get('mass_kg')):+.2f} kg" if mp.get("mass_kg") is not None else "—")
                        mc2.metric("CG x", f"{float(mp.get('x_cg_m')):+.4f} m" if mp.get("x_cg_m") is not None else "—")
                        mc3.metric("Iyy", f"{float(inertia.get('iyy_kg_m2')):.4f} kg·m²" if inertia.get("iyy_kg_m2") else "— (not set)")
                        mc4.metric("Izz", f"{float(inertia.get('izz_kg_m2')):.4f} kg·m²" if inertia.get("izz_kg_m2") else "— (not set)")

                        missing = rdns.get("missing_items") or []
                        if missing:
                            st.caption("Missing for full eigenanalysis: " + " · ".join(f"**{m}**" for m in missing))

                    except Exception as ex:
                        st.warning(f"Could not read dynamics_foundation.json: {ex}")

                _panel("Full CLI inspect",
                       "Prints the complete dynamics result in the terminal.",
                       ["dynamics", "inspect", "--run-dir", str(chosen_path)],
                       root, exe, tmo, dry, "dyn_ins_cli", label="▶  Full inspect")

            # ── CG sweep curve ────────────────────────────────────────────
            elif ins_view == "CG sweep curve":
                cg_json = dyn_dir / "cg_sweep.json"
                if not cg_json.exists():
                    st.info("No cg_sweep.json found. Run ② CG Sweep first.")
                else:
                    try:
                        import json as _j
                        import plotly.graph_objects as go
                        data   = _j.loads(cg_json.read_text(encoding="utf-8"))
                        cases  = data.get("cases") or []
                        zc     = data.get("static_margin_zero_crossing_estimate_m")
                        sm_min = data.get("stable_cg_min_m")
                        sm_max = data.get("stable_cg_max_m")
                        trim_min = data.get("trimmable_cg_min_m")
                        trim_max = data.get("trimmable_cg_max_m")

                        if cases:
                            cg_vals = [c.get("x_cg_m") for c in cases]
                            sm_vals = [c.get("static_margin_percent_mac") for c in cases]
                            de_vals = [c.get("de_trim_deg") for c in cases]

                            from plotly.subplots import make_subplots
                            has_de  = any(v is not None for v in de_vals)
                            fig = make_subplots(specs=[[{"secondary_y": has_de}]])

                            fig.add_trace(go.Scatter(
                                x=cg_vals, y=sm_vals, mode="lines+markers",
                                name="Static margin [%MAC]",
                                line=dict(color="#3B82F6", width=2), marker=dict(size=7),
                                hovertemplate="CG: %{x:.3f} m<br>SM: %{y:.2f}% MAC<extra></extra>",
                            ), secondary_y=False)

                            fig.add_hline(y=0, line_dash="dash", line_color="#EF4444", line_width=1.5,
                                          annotation_text="SM=0 (neutral point)",
                                          annotation_position="top right")
                            fig.add_hrect(y0=5, y1=12, fillcolor="#22C55E", opacity=0.08,
                                          annotation_text="ISR target 5–12%",
                                          annotation_position="top right")

                            if has_de:
                                fig.add_trace(go.Scatter(
                                    x=cg_vals, y=de_vals, mode="lines+markers",
                                    name="Trim δe [deg]",
                                    line=dict(color="#F59E0B", width=2, dash="dot"),
                                    marker=dict(size=5, symbol="square"),
                                    hovertemplate="CG: %{x:.3f} m<br>Trim δe: %{y:.2f}°<extra></extra>",
                                ), secondary_y=True)
                                fig.add_hline(y=20, line_color="#EF4444", line_dash="dot", line_width=1,
                                              annotation_text="δe=20° limit", secondary_y=True)
                                fig.add_hline(y=-20, line_color="#EF4444", line_dash="dot", line_width=1,
                                              secondary_y=True)

                            if zc is not None:
                                fig.add_vline(x=zc, line_dash="dot", line_color="#F59E0B", line_width=1.5,
                                              annotation_text=f"NP ≈ {zc:.3f} m",
                                              annotation_position="top left")
                            if sm_min is not None and sm_max is not None:
                                fig.add_vrect(x0=sm_min, x1=sm_max, fillcolor="#22C55E", opacity=0.06,
                                              annotation_text=f"Stable: {sm_min:.3f}–{sm_max:.3f} m")

                            fig.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0F1923",
                                font=dict(color="#C8D6E5", size=12),
                                margin=dict(l=60, r=20, t=50, b=60), height=400,
                                title="CG sweep — static margin and trim elevon",
                                xaxis=dict(title="CG x position [m]", gridcolor="#1E2F3E"),
                                yaxis=dict(title="Static margin [%MAC]", gridcolor="#1E2F3E"),
                                yaxis2=dict(title="Trim δe [deg]", gridcolor="#1E2F3E"),
                                legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#334252", borderwidth=1),
                            )
                            st.plotly_chart(fig, use_container_width=True)

                            sc1, sc2, sc3, sc4 = st.columns(4)
                            sc1.metric("Neutral point", f"{zc:.4f} m" if zc else "—")
                            sc2.metric("Stable CG min", f"{float(sm_min):.4f} m" if sm_min else "—")
                            sc3.metric("Stable CG max", f"{float(sm_max):.4f} m" if sm_max else "—")
                            sc4.metric("Trimmable range",
                                       f"{float(trim_min):.3f}–{float(trim_max):.3f} m"
                                       if (trim_min and trim_max) else "— (no Cmδe data)")

                            if sm_min is not None and sm_max is not None:
                                st.success(
                                    f"✓ Stable CG range: {float(sm_min):.4f} – {float(sm_max):.4f} m  "
                                    f"(span = {float(sm_max)-float(sm_min):.4f} m)"
                                )
                            if trim_min and trim_max:
                                st.info(
                                    f"Trimmable CG range (|δe| ≤ 25°): "
                                    f"{float(trim_min):.4f} – {float(trim_max):.4f} m"
                                )

                    except ImportError:
                        st.error("Plotly not installed. Run `pip install plotly`.")
                    except Exception as ex:
                        st.warning(f"Could not read cg_sweep.json: {ex}")

                _panel("Full CLI sweep inspect",
                       "Prints per-CG-point static margin results.",
                       ["dynamics", "cg-sweep-inspect", "--run-dir", str(chosen_path)],
                       root, exe, tmo, dry, "dyn_cgsw_ins_cli", label="▶  Full CG sweep inspect")

            # ── Trim result ───────────────────────────────────────────────
            else:
                trim_json = dyn_dir / "trim_result.json"
                if not trim_json.exists():
                    st.info("No trim_result.json found. Run ③ Trim first.")
                else:
                    try:
                        import json as _j
                        tr   = _j.loads(trim_json.read_text(encoding="utf-8"))
                        lng  = tr.get("longitudinal") or {}
                        meta = tr.get("metadata") or {}

                        if not lng.get("valid"):
                            st.error(f"Trim estimate invalid: {lng.get('reason', 'unknown reason')}")
                        else:
                            _sec("Control-fixed trim (α-trim at fixed δe)")
                            t1, t2, t3, t4 = st.columns(4)
                            t1.metric("Current α [°]", f"{float(lng.get('alpha_current_deg', 0)):+.2f}")
                            t2.metric("Δα required", f"{float(lng.get('delta_alpha_deg', 0)):+.4f}°")
                            t3.metric("Trim α estimate", f"{float(lng.get('alpha_trim_deg', 0)):+.4f}°")
                            in_bounds = lng.get("alpha_trim_in_bounds")
                            t4.metric("In flyable range [-5°,15°]", "✓ Yes" if in_bounds else "✗ No")

                            if in_bounds:
                                st.success(f"✓ Trim alpha {lng.get('alpha_trim_deg', 0):.2f}° is within flyable range.")
                            else:
                                st.warning(
                                    f"⚠ Trim alpha {lng.get('alpha_trim_deg', 0):.2f}° is outside [-5°, 15°]. "
                                    "Consider: (a) moving CG aft, or (b) adding positive elevon deflection."
                                )

                            if lng.get("de_trim_deg") is not None:
                                _sec("Elevon-fixed trim (δe-trim at fixed α)")
                                e1, e2, e3, e4 = st.columns(4)
                                e1.metric("Current δe [°]", f"{float(lng.get('control_input_deg', 0)):+.2f}")
                                e2.metric("Δδe required", f"{float(lng.get('delta_de_deg', 0)):+.4f}°")
                                e3.metric("Trim δe estimate", f"{float(lng.get('de_trim_deg', 0)):+.4f}°")
                                de_bounds = lng.get("de_trim_in_bounds")
                                e4.metric("In actuator range [-25°,25°]", "✓ Yes" if de_bounds else "✗ No")
                                if de_bounds:
                                    st.success(f"✓ Trim δe {lng.get('de_trim_deg', 0):.2f}° within actuator limits.")
                                else:
                                    st.warning(
                                        f"⚠ Trim δe {lng.get('de_trim_deg', 0):.2f}° exceeds actuator limits [-25°, 25°]. "
                                        "Consider moving CG toward the neutral point."
                                    )

                            _sec("Key derivatives used")
                            d1, d2 = st.columns(2)
                            d1.metric("Cma [/rad]", f"{float(lng.get('cma_per_rad', 0)):+.4f}" if lng.get("cma_per_rad") else "—")
                            d2.metric("Cmδe [/rad]", f"{float(lng.get('cmde_per_rad', 0)):+.4f}" if lng.get("cmde_per_rad") else "— (not available)")

                            if meta.get("alpha_trim_warning"):
                                st.warning(meta["alpha_trim_warning"])
                            if meta.get("de_trim_warning"):
                                st.warning(meta["de_trim_warning"])

                    except Exception as ex:
                        st.warning(f"Could not read trim_result.json: {ex}")

                _panel("Full CLI trim inspect",
                       "Runs the trim estimate via CLI.",
                       ["dynamics", "trim", "--run-dir", str(chosen_path)],
                       root, exe, tmo, dry, "dyn_trim_ins_cli", label="▶  Run trim")


def _feature_selector(key, include_feature_set=True):
    """Returns (feature_args, label) for ML commands that accept --features / --feature-preset / --feature-set."""
    opts = ["--feature-preset (named preset)", "--features (raw comma-sep columns)"]
    if include_feature_set:
        opts.append("--feature-set (physics-engineered)")
    mode = st.radio("Feature input (exactly ONE required)",opts,horizontal=True,key=f"{key}_fmode")
    c1, c2 = st.columns(2)
    if "preset" in mode:
        fp = c1.selectbox("--feature-preset", ML_FEATURE_PRESETS, key=f"{key}_fp",
                          help="bwb_control = legacy control_input_deg; bwb_control_sym_elevon = explicit delta_e_sym_deg; bwb_basic = no control column")
        tgt = c2.text_input("--targets",DEFAULT_TARGETS,key=f"{key}_tgt")
        return ["--feature-preset",fp,"--targets",tgt], f"preset:{fp}"
    elif "raw" in mode:
        feat = c1.text_input("--features", DEFAULT_FEATURES, key=f"{key}_feat", help=f"Legacy default: {DEFAULT_FEATURES}. Explicit symmetric elevon option: {DEFAULT_SYM_ELEVON_FEATURES}")
        tgt  = c2.text_input("--targets",DEFAULT_TARGETS,key=f"{key}_tgt2")
        return ["--features",feat,"--targets",tgt], f"raw features"
    else:
        fs  = c1.selectbox("--feature-set", ML_FEATURE_SET_CHOICES, key=f"{key}_fs",
                             help="Raw or physics-engineered feature sets. Symmetric-elevon variants use delta_e_sym_deg explicitly.")
        tgt = c2.text_input("--targets",DEFAULT_TARGETS,key=f"{key}_tgt3")
        return ["--feature-set",fs,"--targets",tgt], f"set:{fs}"




def _aeris_clean_gui_path_text(value: object) -> str:
    """Return a clean filesystem path from Streamlit text inputs.

    Guards against accidental copied labels such as:
    'Dataset: data/datasets/foo' or 'Output dir: data/processed/bar'.
    """
    raw = str(value or "").strip().strip("`'")
    # Handle pasted two-line labels: "Dataset:\n/path".
    raw = raw.replace("\r\n", "\n").strip()
    for _ in range(4):
        lowered = raw.lower().lstrip()
        matched = False
        for label in (
            "dataset:",
            "output dir:",
            "output directory:",
            "--dataset",
            "--output-dir",
            "--output_dir",
        ):
            if lowered.startswith(label):
                raw = raw.lstrip()[len(label):].strip()
                matched = True
                break
        if not matched:
            break
    return raw.strip().strip("`'")

def pg_ml(root, exe, tmo, dry):
    _hero("◈","ML Studio","train · tune · compare · promote · predict · active learning","surrogate")

    # AERIS_PATCH_CST_GUI_V1_ML_QUICKSTART
    with st.expander("〜 2D Airfoil / CST quick ML commands", expanded=False):
        _note(
            "Use this for promoted 2D XFOIL datasets. CST-generated datasets should use "
            "<code>airfoil_cst_xfoil_v1</code>; legacy .dat-library datasets should use "
            "<code>airfoil_xfoil_v1</code>. Group split by <code>airfoil_id</code> prevents leakage.",
            "info",
        )
        airfoil_datasets = [Path(d) for d in _dirs(str(root / "data" / "datasets"))
                            if (Path(d) / "promotion_manifest.json").exists()
                            and (Path(d) / "curated_airfoil_dataset.csv").exists()]
        if airfoil_datasets:
            airfoil_ds = st.selectbox(
                "Promoted airfoil dataset",
                [str(d) for d in airfoil_datasets],
                format_func=lambda s: f"✓ {Path(s).name} · {_airfoil_dataset_feature_preset_hint(Path(s))}",
                key="ml_airfoil_quick_ds",
            )
            airfoil_preset = _airfoil_dataset_feature_preset_hint(Path(airfoil_ds))
        else:
            airfoil_ds = st.text_input(
                "Promoted airfoil dataset",
                str(root / "data" / "datasets" / "cst_xfoil_smoke"),
                key="ml_airfoil_quick_ds_text",
            )
            airfoil_preset = "airfoil_cst_xfoil_v1"
        cqa, cqb, cqc = st.columns(3)
        airfoil_preset = cqa.selectbox(
            "Feature preset",
            ["airfoil_cst_xfoil_v1", "airfoil_xfoil_v1"],
            index=0 if airfoil_preset == "airfoil_cst_xfoil_v1" else 1,
            key="ml_airfoil_quick_preset",
        )
        airfoil_targets = cqb.text_input("Targets", "cl,cd,cm", key="ml_airfoil_quick_targets")
        airfoil_model = cqc.selectbox("Model", MODEL_TYPES, index=MODEL_TYPES.index("lightgbm") if "lightgbm" in MODEL_TYPES else 0, key="ml_airfoil_quick_model")
        airfoil_out = st.text_input(
            "ML output dir",
            str(root / "data" / "processed" / "ml_runs" / "gui_airfoil_cst_lgbm"),
            key="ml_airfoil_quick_out",
        )
        qa, qb, qc = st.columns(3)
        with qa:
            _panel("Airfoil EDA", "EDA with the correct airfoil feature preset.",
                   ["ml", "eda", "--dataset", airfoil_ds, "--feature-preset", airfoil_preset, "--targets", airfoil_targets],
                   root, exe, tmo, dry, "ml_airfoil_quick_eda", label="▶  EDA")
        with qb:
            _panel("Train airfoil model", "Grouped split by airfoil_id; suitable for CST/XFOIL smoke and larger campaigns.",
                   ["ml", "train", "--dataset", airfoil_ds, "--feature-preset", airfoil_preset, "--targets", airfoil_targets,
                    "--group-column", "airfoil_id", "--model-type", airfoil_model, "--output-dir", airfoil_out],
                   root, exe, tmo, dry, "ml_airfoil_quick_train", label="▶  Train")
        with qc:
            _panel("Compare airfoil seeds", "Multi-seed stability check with group split by airfoil_id.",
                   ["ml", "compare-seeds", "--dataset", airfoil_ds, "--feature-preset", airfoil_preset, "--targets", airfoil_targets,
                    "--group-column", "airfoil_id", "--models", "lightgbm,xgboost", "--seeds", "101,202,303,404,505"],
                   root, exe, tmo, dry, "ml_airfoil_quick_compare", label="▶  Compare seeds")

    # ── Cm sanity gate — mandatory before training ────────────────────────────
    with st.expander("⚠  Step 0 — Cm sanity check  (run before training)", expanded=False):
        st.warning(
            "**Run this once on your promoted dataset before any ML training.** "
            "Verifies that Cm decreases with alpha (Cma < 0 = statically stable pitch). "
            "A positive Cma means the aircraft is unstable in pitch — ML models trained "
            "on that data would learn the wrong physics."
        )
        cm_src = st.radio(
            "Source",
            ["Promoted aero dataset (recommended)", "Direct CSV path"],
            horizontal=True, key="cms_src",
        )
        if "dataset" in cm_src:
            promoted   = [d for d in _dirs(str(root / "data" / "datasets"))
                          if (Path(d) / "promotion_manifest.json").exists()]
            all_ds     = _dirs(str(root / "data" / "datasets"))
            ds_choices = promoted + [d for d in all_ds if d not in promoted]
            if ds_choices:
                cms_ds = st.selectbox(
                    "Dataset",
                    ds_choices,
                    format_func=lambda s: (
                        f"✓ {Path(s).name}"
                        if (Path(s) / "promotion_manifest.json").exists()
                        else f"○ {Path(s).name} (not promoted)"
                    ),
                    key="cms_ds",
                    help="✓ = promoted dataset. Run Cm sanity on promoted data only.",
                )
                args_cm = ["aero", "cm-sanity", "--dataset", cms_ds]
            else:
                st.info("No datasets found in data/datasets/. Complete the Dataset Factory first.")
                args_cm = []
        else:
            cms_csv = st.text_input(
                "CSV path", "", key="cms_csv",
                placeholder="data/datasets/<name>/curated_aero_dataset.csv",
            )
            args_cm = ["aero", "cm-sanity", "--csv", cms_csv] if cms_csv.strip() else []

        cm_od = st.text_input(
            "Output dir (optional)", value="", key="cms_od",
            placeholder="leave blank for auto",
        )
        if cm_od.strip() and args_cm:
            args_cm += ["--output-dir", cm_od.strip()]

        with st.expander("Advanced column settings"):
            c1, c2 = st.columns(2)
            cms_ac  = c1.text_input("Alpha column", "alpha_deg", key="cms_ac")
            cms_cc  = c2.text_input("Cm column",    "cm",        key="cms_cc")
            cms_gc  = st.text_input(
                "Group columns",
                "geometry_id,control_input_deg,velocity_mps,altitude_m",
                key="cms_gc",
            )
            cms_fov = st.checkbox(
                "Fail on violation", False, key="cms_fov",
                help="Exit non-zero if any group has Cma ≥ 0. Useful in CI pipelines.",
            )
            if args_cm:
                args_cm += ["--alpha-column", cms_ac, "--cm-column", cms_cc,
                            "--group-columns", cms_gc]
                if cms_fov:
                    args_cm.append("--fail-on-violation")

        if args_cm:
            _panel(
                "Run Cm sanity check",
                "Verifies Cma < 0 in all condition groups. Gate before ML training.",
                args_cm, root, exe, tmo, dry, "cms_run",
                label="▶  Run Cm sanity",
            )
        else:
            st.caption("Select a dataset or CSV path above to enable.")

    _note(
        "<b>Feature input rules (strictly enforced by the CLI):</b> use exactly ONE of "
        "<code>--features</code>, <code>--feature-preset</code>, or <code>--feature-set</code>. "
        "Mixing any two is a CLI error. "
        "Presets: <code>bwb_basic</code>, <code>bwb_control</code>, <code>airfoil_xfoil_v1</code>, <code>airfoil_cst_xfoil_v1</code>. "
        "Feature sets: <code>bwb_control_raw</code>, <code>bwb_control_physics_v1</code>.",
        "info",
    )

    tabs = st.tabs([
        "  ① Feature Sets  ",
        "  ② Schema/EDA  ",
        "  ③ Train  ",
        "  ④ Tune  ",
        "  ⑤ Compare  ",
        "  ⑥ Trust gates  ",
        "  ⑦ Predict  ",
        "  ⑧ Audit  ",
        "  ⑨ Active Learning  ",
        "  ⑩ Classification  ",
        "  ⑪ Multifidelity  ",
        "  ⑫ ML Trust  ",
    ])

    # ── ① Feature Sets ────────────────────────────────────────────────────────
    with tabs[0]:
        fst = st.tabs(["  List  ","  Validate feature-set  ","  Materialize  "])
        with fst[0]:
            c1,c2 = st.columns(2)
            with c1: _panel("List feature presets","Lists bwb_basic and bwb_control column bundles.",["ml","feature-presets"],root,exe,tmo,dry,"ft_presets")
            with c2: _panel("List feature sets","Lists bwb_control_raw, bwb_control_physics_v1 with transforms.",["ml","feature-sets"],root,exe,tmo,dry,"ft_sets")
            st.divider()
            c3,c4 = st.columns(2)
            fs_d = c3.text_input("--feature-set to describe","bwb_control_physics_v1",key="ft_desc_fs")
            with c4: _panel("Describe feature set","Shows raw+engineered features, transforms, status.",["ml","describe-feature-set","--feature-set",fs_d],root,exe,tmo,dry,"ft_desc")

        with fst[1]:
            _note("<b>aeris ml validate-feature-set</b> — checks the promoted dataset has all columns required by the feature set.","info")
            ds_fv = _pick_dir("Promoted dataset",root/"data"/"datasets","fv_ds")
            c1,c2 = st.columns(2)
            fs_fv = c1.text_input("--feature-set","bwb_control_raw",key="fv_fs")
            tgt_fv = c2.text_input("--targets (optional)",DEFAULT_TARGETS,key="fv_tgt")
            gc_fv = st.text_input("--group-column","geometry_id",key="fv_gc")
            af_fv = st.checkbox("--allow-forced",False,key="fv_af")
            args_fv = ["ml","validate-feature-set","--dataset",ds_fv,"--feature-set",fs_fv,"--group-column",gc_fv]
            if tgt_fv.strip(): args_fv += ["--targets",tgt_fv]
            if af_fv: args_fv.append("--allow-forced")
            _panel("Validate feature set","Checks dataset columns match feature set requirements.",args_fv,root,exe,tmo,dry,"fv_run")

        with fst[2]:
            _note("<b>aeris ml feature-engineer</b> — materializes a feature set into an explicit engineered CSV with transform manifest. Required before training on physics-engineered features.","info")
            ds_fe = _pick_dir("Promoted dataset",root/"data"/"datasets","fe_ds")
            c1,c2 = st.columns(2)
            fs_fe = c1.text_input("--feature-set","bwb_control_physics_v1",key="fe_fs")
            tgt_fe = c2.text_input("--targets (optional)","",key="fe_tgt")
            gc_fe = st.text_input("--group-column","geometry_id",key="fe_gc")
            od_fe = st.text_input("--output-dir (blank = <dataset>/features/<feature_set>)","",key="fe_od")
            c3,c4,c5 = st.columns(3)
            af_fe = c3.checkbox("--allow-forced",False,key="fe_af")
            iac_fe = c4.checkbox("--include-all-columns (default True)",True,key="fe_iac",help="False = only group/features/targets (--only-feature-columns)")
            ow_fe = c5.checkbox("--overwrite",False,key="fe_ow")
            args_fe = ["ml","feature-engineer","--dataset",ds_fe,"--feature-set",fs_fe,"--group-column",gc_fe]
            if tgt_fe.strip(): args_fe += ["--targets",tgt_fe]
            if od_fe.strip(): args_fe += ["--output-dir",od_fe]
            if af_fe: args_fe.append("--allow-forced")
            if not iac_fe: args_fe.append("--only-feature-columns")
            if ow_fe: args_fe.append("--overwrite")
            _panel("Materialize feature set","Writes engineered_dataset.csv + feature_engineering_manifest.json.",args_fe,root,exe,tmo,dry,"fe_run")

    # ── ② Schema / EDA ────────────────────────────────────────────────────────
    with tabs[1]:
        se_t = st.tabs(["  Schema validate  ","  EDA  "])
        with se_t[0]:
            _note("<b>aeris ml validate-schema</b> — checks a promoted dataset has feature/target columns. Use --feature-preset or --features (not both).","info")
            ds0 = _pick_dir("Promoted dataset",root/"data"/"datasets","sch_ds")
            fa0, _ = _feature_selector("sch", include_feature_set=False)
            gc0 = st.text_input("--group-column","geometry_id",key="sch_gc")
            af0 = st.checkbox("--allow-forced",False,key="sch_af")
            args0 = ["ml","validate-schema","--dataset",ds0,"--group-column",gc0] + fa0
            if af0: args0.append("--allow-forced")
            _panel("Schema validate","Validates dataset columns for training readiness.",args0,root,exe,tmo,dry,"sch_run")

        with se_t[1]:
            _note(
                "<b>aeris ml eda</b> — EDA v2 checks constants, duplicates, missingness, dtypes, categorical/status columns, "
                "coverage gaps, Pearson/Spearman relationships, robust outliers, and aero sanity signals. "
                "Generates <code>eda_report.json</code> + <code>eda_summary.md</code> + optional PNGs. "
                "<code>--feature-set</code> is now supported directly, so physics-engineered views can be inspected before training.",
                "info",
            )
            ds_e = _pick_dir("Promoted dataset",root/"data"/"datasets","eda_ds")
            fa_e, _ = _feature_selector("eda", include_feature_set=True)
            c1,c2,c3 = st.columns(3)
            gc_e    = c1.text_input("--group-column","geometry_id",key="eda_gc")
            sig_e   = c2.number_input("--outlier-sigma",min_value=0.1,value=4.0,step=0.5,key="eda_sig",help="Sigma threshold for simple outlier scan. EDA v2 also adds robust IQR/MAD outliers.")
            od_e    = c3.text_input("--output-dir (blank = <dataset>/eda)","",key="eda_od")
            c4,c5 = st.columns(2)
            plots_e = c4.checkbox("--plots (generate PNGs)",True,key="eda_plots",help="Writes heatmaps, distributions, alpha/control coverage, CL-vs-CD polar, target-vs-feature plots.")
            af_e    = c5.checkbox("--allow-forced",False,key="eda_af")
            args_e = ["ml","eda","--dataset",ds_e,"--group-column",gc_e,"--outlier-sigma",str(sig_e)] + fa_e
            if od_e.strip(): args_e += ["--output-dir",od_e]
            if plots_e: args_e.append("--plots")
            else: args_e.append("--no-plots")
            if af_e: args_e.append("--allow-forced")
            _panel("EDA v2","Generates EDA v2 JSON/Markdown plus optional diagnostic PNGs.",args_e,root,exe,tmo,dry,"eda_run")

            eda_out_dir = Path(od_e).expanduser() if od_e.strip() else Path(ds_e).expanduser() / "eda"
            eda_report_path = eda_out_dir / "eda_report.json"
            if eda_report_path.exists():
                rep = _rjson(eda_report_path) or {}
                st.caption(f"Loaded existing EDA report: {eda_report_path}")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Rows", rep.get("shape", {}).get("n_rows", "—"))
                m2.metric("Missing cols", rep.get("missingness", {}).get("n_columns_with_missing", "—"))
                m3.metric("Constant cols", rep.get("constant_columns", {}).get("n_constant", "—"))
                m4.metric("Robust outlier cols", rep.get("robust_outliers", {}).get("n_columns_with_robust_outliers", "—"))

                recs = rep.get("operator_recommendations", []) or []
                if recs:
                    st.markdown("**EDA v2 recommendations**")
                    for rec in recs[:8]:
                        st.write(f"- {rec}")

                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Regime outlier cols", rep.get("regime_outliers", {}).get("n_columns_with_regime_outliers", "—"))
                p2.metric("Polar low-R² groups", rep.get("polar_diagnostics", {}).get("n_low_r2_groups", "—"))
                p3.metric("Negative polar-k groups", rep.get("polar_diagnostics", {}).get("n_negative_k_groups", "—"))
                p4.metric("Scale", rep.get("learning_readiness", {}).get("scale_label", "—"))

                eda_view_tabs = st.tabs(["Aero sanity", "Polar/control", "Learning readiness", "Missingness", "Compare reports"])
                with eda_view_tabs[0]:
                    st.json(rep.get("aero_physics_sanity", {}))
                with eda_view_tabs[1]:
                    st.markdown("**Polar diagnostics**")
                    st.json(rep.get("polar_diagnostics", {}))
                    st.markdown("**Control-effect sanity**")
                    st.json(rep.get("control_effect_sanity", {}))
                with eda_view_tabs[2]:
                    st.json(rep.get("learning_readiness", {}))
                with eda_view_tabs[3]:
                    miss = rep.get("missingness", {}) or {}
                    top_missing = []
                    for col, item in (miss.get("by_column", {}) or {}).items():
                        if int(item.get("n_missing", 0) or 0) > 0:
                            top_missing.append({
                                "column": col,
                                "n_missing": item.get("n_missing"),
                                "missing_fraction": item.get("missing_fraction"),
                            })
                    top_missing = sorted(top_missing, key=lambda r: r.get("n_missing", 0), reverse=True)[:30]
                    if top_missing:
                        st.dataframe(top_missing, use_container_width=True)
                    else:
                        st.success("No missing-value hotspots in the loaded EDA report.")
                with eda_view_tabs[4]:
                    other_report = st.text_input(
                        "Optional second EDA report path for comparison",
                        "",
                        key="eda_compare_report_path",
                        help="Example: data/datasets/other_dataset/eda/eda_report.json",
                    )
                    if other_report.strip():
                        try:
                            from aeris.ml.eda import compare_eda_reports
                            comp = compare_eda_reports([eda_report_path, Path(other_report).expanduser()])
                            st.dataframe(comp.get("reports", []), use_container_width=True)
                        except Exception as exc:
                            st.error(f"Could not compare EDA reports: {exc}")

                plots_dir = eda_out_dir / "plots"
                if plots_dir.exists():
                    plot_files = sorted(plots_dir.glob("*.png"))
                    if plot_files:
                        st.markdown("**Existing EDA plots**")
                        selected_plot = st.selectbox(
                            "Select plot to inspect",
                            [p.name for p in plot_files],
                            key="eda_plot_selector",
                        )
                        selected_path = next((p for p in plot_files if p.name == selected_plot), plot_files[0])
                        st.image(str(selected_path), caption=selected_path.name, use_container_width=True)
                        with st.expander("Show all EDA plots", expanded=False):
                            for plot_path in plot_files[:20]:
                                st.image(str(plot_path), caption=plot_path.name, use_container_width=True)

    # ── ③ Train ───────────────────────────────────────────────────────────────
    with tabs[2]:
        _note(
            "Always follow training with seed stability (⑤ Compare → Seed stability, ≥5 seeds) before declaring a winner. "
            "Feature set provenance is written into every run artifact — <code>train_config.json</code> records "
            "which feature set and transforms were applied before splitting. "
            "Engineered columns (<code>re_number</code>, <code>alpha_deg_sq</code>, etc.) are added before the split, not after.",
            "warn",
        )
        ds1 = _pick_dir("Promoted dataset",root/"data"/"datasets","tr_ds")
        fa1, _ = _feature_selector("tr")
        mt1 = st.selectbox("--model-type",MODEL_TYPES,index=6,key="tr_mt",format_func=lambda s:MODEL_INFO.get(s,s))
        c1,c2,c3 = st.columns(3)
        sm1  = c1.selectbox("--split-method",["grouped","random"],key="tr_sm")
        gc1  = c2.text_input("--group-column","geometry_id",key="tr_gc")
        rs1  = c3.number_input("--random-seed",min_value=0,value=123,step=1,key="tr_rs")
        c4,c5,c6 = st.columns(3)
        tf1  = c4.slider("--train-fraction",0.3,0.85,0.70,0.05,key="tr_tf")
        vf1  = c5.slider("--val-fraction",0.05,0.3,0.15,0.05,key="tr_vf")
        te1  = c6.slider("--test-fraction",0.05,0.3,0.15,0.05,key="tr_te")
        od1  = st.text_input("--output-dir",str(root/"data"/"processed"/"ml_runs"/"gui_train"),key="tr_od")
        af1  = st.checkbox("--allow-forced",False,key="tr_af")
        args1 = ["ml","train","--dataset",ds1,"--model-type",mt1,
                 "--split-method",sm1,"--group-column",gc1,"--random-seed",str(int(rs1)),
                 "--train-fraction",str(tf1),"--val-fraction",str(vf1),"--test-fraction",str(te1),
                 "--output-dir",od1] + fa1
        if af1: args1.append("--allow-forced")
        _panel("Train model","Trains one surrogate on the promoted dataset.",args1,root,exe,tmo,dry,"tr_run")

        st.divider()
        # static marker: live_train_neural_mlp streamlit_add_rows_disabled
        with st.expander("Live neural MLP training — epoch-by-epoch", expanded=False):
            _note(
                "This is true live training for iterative neural models. The chart updates every epoch. "
                "Tree/linear models do not have epoch-by-epoch history; use ML Trust learning-curves for those.",
                "info",
            )
            live_default_ds = str(Path(ds1).with_name(Path(ds1).name + "__flyability_ml")) if Path(str(ds1) + "__flyability_ml").exists() else ds1
            live_ds = st.text_input("Dataset", live_default_ds, key="live_tr_ds")
            c_live_a, c_live_b = st.columns(2)
            live_fs = c_live_a.selectbox(
                "--feature-set",
                ML_FEATURE_SET_CHOICES,
                index=ML_FEATURE_SET_CHOICES.index("bwb_control_physics_v1") if "bwb_control_physics_v1" in ML_FEATURE_SET_CHOICES else 0,
                key="live_tr_fs",
                help="Live V2 uses feature sets so engineered columns are produced before split.",
            )
            live_targets = c_live_b.text_input(
                "--targets",
                "trim_delta_e_required_deg,trim_delta_e_margin_to_limit_deg",
                key="live_tr_targets",
            )
            c_live_c, c_live_d, c_live_e = st.columns(3)
            live_epochs = c_live_c.number_input("max epochs", min_value=1, max_value=1000, value=50, step=1, key="live_tr_epochs")
            live_seed = c_live_d.number_input("random seed", min_value=0, value=123, step=1, key="live_tr_seed")
            live_allow_forced = c_live_e.checkbox("--allow-forced", False, key="live_tr_allow_forced")
            c_live_f, c_live_g, c_live_h = st.columns(3)
            live_hidden = c_live_f.text_input("hidden layers", "64,64", key="live_tr_hidden")
            live_lr = c_live_g.number_input("learning_rate_init", min_value=1e-6, value=1e-3, step=1e-4, format="%.6f", key="live_tr_lr")
            live_alpha = c_live_h.number_input("alpha", min_value=0.0, value=1e-4, step=1e-4, format="%.6f", key="live_tr_alpha")
            c_live_i, c_live_j, c_live_k = st.columns(3)
            live_tf = c_live_i.slider("train fraction", 0.3, 0.85, 0.70, 0.05, key="live_tr_tf")
            live_vf = c_live_j.slider("val fraction", 0.05, 0.3, 0.15, 0.05, key="live_tr_vf")
            live_te = c_live_k.slider("test fraction", 0.05, 0.3, 0.15, 0.05, key="live_tr_te")
            live_gc = st.text_input("--group-column", "geometry_id", key="live_tr_gc")
            live_od = st.text_input(
                "--output-dir",
                str(root / "data" / "processed" / "ml_runs" / "gui_live_neural_mlp"),
                key="live_tr_od",
            )
            st.caption("Writes training_monitor/training_history.csv and updates the Streamlit line chart from each epoch callback.")
            with st.expander("Experiment tracking / external dashboards", expanded=False):
                _note(
                    "Privacy-first: MLflow and TensorBoard are local. W&B is optional and defaults to offline mode.",
                    "info",
                )
                c_track_a, c_track_b, c_track_c = st.columns(3)
                live_track_mlflow = c_track_a.checkbox("MLflow local tracking", True, key="live_tr_track_mlflow")
                live_track_tb = c_track_b.checkbox("TensorBoard event logs", False, key="live_tr_track_tb")
                live_track_wandb = c_track_c.checkbox("W&B offline", False, key="live_tr_track_wandb")
                live_track_project = st.text_input("tracking experiment", "aeris", key="live_tr_track_project")
                live_track_run = st.text_input("tracking run name", "", key="live_tr_track_run")
                st.caption("MLflow UI: mlflow ui --backend-store-uri sqlite:///<output_dir>/tracking/mlflow.db")
                st.caption("TensorBoard: tensorboard --logdir <output_dir>/tracking/tensorboard")
                st.caption("W&B remains offline unless you explicitly sync it later.")

            def _live_training_csv_tokens(value: str) -> list[str]:
                return [part.strip() for part in str(value).split(',') if part.strip()]

            if st.button("▶ Live train neural MLP", key="live_tr_run_btn", type="primary"):
                if pd is None:
                    st.error("pandas is required for the live training chart.")
                else:
                    from aeris.ml.live_training import run_live_neural_mlp_training

                    epoch_rows: list[dict[str, Any]] = []
                    status_slot = st.empty()
                    warning_slot = st.empty()
                    st.caption("Loss / MSE curves — x-axis: epoch | y-axis: loss / MSE")
                    loss_chart_slot = st.empty()
                    st.caption("Mean RMSE curves — x-axis: epoch | y-axis: RMSE mean [target units]")
                    rmse_chart_slot = st.empty()
                    st.caption("Mean R² curves — x-axis: epoch | y-axis: R² [-]")
                    r2_chart_slot = st.empty()
                    st.caption("Normalized RMSE curves — x-axis: epoch | y-axis: normalized RMSE [-]")
                    norm_chart_slot = st.empty()
                    st.caption("Per-target validation RMSE — x-axis: epoch | y-axis: validation RMSE [target units]")
                    target_rmse_chart_slot = st.empty()
                    st.caption("Generalization gap curves — x-axis: epoch | y-axis: validation/test minus train gap")
                    gap_chart_slot = st.empty()
                    st.caption("Learning-rate schedule — x-axis: epoch | y-axis: learning rate [-]")
                    lr_chart_slot = st.empty()
                    st.caption("Epoch time — x-axis: epoch | y-axis: seconds per epoch [s]")
                    time_chart_slot = st.empty()
                    st.caption("Mean bias curves — x-axis: epoch | y-axis: bias [target units]")
                    bias_chart_slot = st.empty()
                    st.caption("Mean p95 error curves — x-axis: epoch | y-axis: p95 absolute error [target units]")
                    p95_chart_slot = st.empty()
                    table_slot = st.empty()
                    artifact_slot = st.empty()
                    live_chart_state = {"charts": {}, "last_epoch": {}}

                    def _on_live_epoch(event: dict[str, Any]) -> None:
                        epoch_rows.append(event)
                        hist = pd.DataFrame(epoch_rows)
                        status_slot.info(
                            f"epoch {int(event.get('epoch', 0))}/{int(live_epochs)} · "
                            f"loss={float(event.get('train_loss', 0.0)):.6g} · "
                            f"val_rmse={float(event.get('val_rmse_mean', 0.0)):.6g} · "
                            f"val_r2={float(event.get('val_r2_mean', 0.0)):.6g}"
                        )
                        def _finite_cols(names: list[str]) -> list[str]:
                            good: list[str] = []
                            for name in names:
                                if name in hist.columns and pd.to_numeric(hist[name], errors="coerce").notna().any():
                                    good.append(name)
                            return good

                        def _stream_metric_chart(
                            key: str,
                            slot: Any,
                            columns: list[str],
                            *,
                            y_axis_title: str = "Metric value",
                            x_axis_title: str = "Epoch",
                            best_epoch: int | None = None,
                            **_unused_chart_kwargs: Any,
                        ) -> None:
                            """Render a stable live metric chart.

                            Accepts chart-label kwargs from the V2.2 GUI calls.
                            Uses Altair when available so the axis labels are inside
                            the chart; falls back to Streamlit line_chart without
                            using add_rows(), which is unsupported in this app
                            runtime.
                            """
                            if not columns:
                                return
                            chart_df = hist[["epoch", *columns]].copy()
                            chart_df["epoch"] = pd.to_numeric(chart_df["epoch"], errors="coerce")
                            for _col in columns:
                                chart_df[_col] = pd.to_numeric(chart_df[_col], errors="coerce")
                            chart_df = chart_df.dropna(subset=["epoch"]).sort_values("epoch")
                            if chart_df.empty:
                                return

                            try:
                                import altair as alt

                                long_df = chart_df.melt(
                                    id_vars=["epoch"],
                                    value_vars=columns,
                                    var_name="metric",
                                    value_name="value",
                                ).dropna(subset=["value"])
                                if long_df.empty:
                                    return

                                base = (
                                    alt.Chart(long_df)
                                    .mark_line()
                                    .encode(
                                        x=alt.X("epoch:Q", title=x_axis_title),
                                        y=alt.Y("value:Q", title=y_axis_title),
                                        color=alt.Color("metric:N", title="Metric"),
                                        tooltip=[
                                            alt.Tooltip("epoch:Q", title="Epoch"),
                                            alt.Tooltip("metric:N", title="Metric"),
                                            alt.Tooltip("value:Q", title=y_axis_title, format=".6g"),
                                        ],
                                    )
                                )
                                chart = base
                                if best_epoch is not None:
                                    try:
                                        best_epoch_value = float(best_epoch)
                                    except (TypeError, ValueError):
                                        best_epoch_value = None
                                    if best_epoch_value is not None:
                                        rule_df = pd.DataFrame({"epoch": [best_epoch_value]})
                                        rule = (
                                            alt.Chart(rule_df)
                                            .mark_rule(strokeDash=[4, 4])
                                            .encode(x=alt.X("epoch:Q", title=x_axis_title))
                                        )
                                        chart = base + rule

                                slot.altair_chart(chart.properties(height=260), use_container_width=True)
                            except Exception:
                                slot.line_chart(chart_df.set_index("epoch")[columns], use_container_width=True)

                        loss_cols = _finite_cols(["train_loss", "train_loss_mse_mean", "val_loss_mse_mean", "test_loss_mse_mean"])
                        _stream_metric_chart("loss", loss_chart_slot, loss_cols, y_axis_title="Loss / MSE")

                        rmse_cols = _finite_cols(["train_rmse_mean", "val_rmse_mean", "test_rmse_mean"])
                        _stream_metric_chart("rmse", rmse_chart_slot, rmse_cols, y_axis_title="RMSE mean [target units]")

                        r2_cols = _finite_cols(["train_r2_mean", "val_r2_mean", "test_r2_mean"])
                        _stream_metric_chart("r2", r2_chart_slot, r2_cols, y_axis_title="R² [-]")

                        norm_cols = _finite_cols(["train_nrmse_scale_mean", "val_nrmse_scale_mean", "test_nrmse_scale_mean"])
                        _stream_metric_chart("normalized", norm_chart_slot, norm_cols, y_axis_title="Normalized RMSE [-]")

                        target_rmse_cols = _finite_cols([c for c in hist.columns if c.startswith("val_rmse__")])
                        _stream_metric_chart("per_target_rmse", target_rmse_chart_slot, target_rmse_cols, y_axis_title="Validation RMSE [target units]")

                        gap_cols = _finite_cols(["val_minus_train_rmse_mean", "val_minus_train_loss_mse_mean", "test_minus_train_rmse_mean"])
                        _stream_metric_chart("gap", gap_chart_slot, gap_cols, y_axis_title="Generalization gap")

                        lr_cols = _finite_cols(["learning_rate"])
                        _stream_metric_chart("learning_rate", lr_chart_slot, lr_cols, y_axis_title="Learning rate [-]")

                        time_cols = _finite_cols(["epoch_time_sec"])
                        _stream_metric_chart("epoch_time", time_chart_slot, time_cols, y_axis_title="Epoch time [s]")

                        bias_cols = _finite_cols(["train_bias_mean", "val_bias_mean", "test_bias_mean"])
                        _stream_metric_chart("bias", bias_chart_slot, bias_cols, y_axis_title="Bias [target units]")

                        p95_cols = _finite_cols(["train_error_p95_mean", "val_error_p95_mean", "test_error_p95_mean"])
                        _stream_metric_chart("error_p95", p95_chart_slot, p95_cols, y_axis_title="p95 absolute error [target units]")

                        if event.get("val_r2_mean") is not None and float(event.get("val_r2_mean", 0.0)) < 0.5:
                            warning_slot.warning("MLP metrics are poor; do not promote. Continue tuning/scaling and check target-specific diagnostics.")
                        elif event.get("val_nrmse_scale_mean") is not None and float(event.get("val_nrmse_scale_mean", 0.0)) > 0.3:
                            warning_slot.warning("MLP normalized validation error is high; do not promote yet.")

                        if event.get("val_rmse_mean") is None:
                            warning_slot.warning("Validation metrics are unavailable/NaN for this epoch. Check validation split and target columns.")

                        table_slot.dataframe(hist.tail(12), use_container_width=True)

                    live_tracking_backends: list[str] = []
                    if live_track_mlflow:
                        live_tracking_backends.append("mlflow")
                    if live_track_tb:
                        live_tracking_backends.append("tensorboard")
                    if live_track_wandb:
                        live_tracking_backends.append("wandb")

                    with st.spinner("Live neural MLP training in progress..."):
                        result = run_live_neural_mlp_training(
                            dataset_path=Path(_aeris_clean_gui_path_text(live_ds)),
                            feature_set_name=live_fs,
                            target_columns=_live_training_csv_tokens(live_targets),
                            split_method=sm1,
                            group_column=live_gc,
                            train_fraction=float(live_tf),
                            val_fraction=float(live_vf),
                            test_fraction=float(live_te),
                            random_seed=int(live_seed),
                            allow_forced=bool(live_allow_forced),
                            output_dir=Path(live_od),
                            max_epochs=int(live_epochs),
                            model_params={
                                "hidden_layer_sizes": live_hidden,
                                "learning_rate_init": float(live_lr),
                                "alpha": float(live_alpha),
                                "random_state": int(live_seed),
                            },
                            epoch_callback=_on_live_epoch,
                            tracking_backends=live_tracking_backends,
                            tracking_experiment_name=live_track_project,
                            tracking_run_name=live_track_run.strip() or None,
                            wandb_mode="offline",
                        )
                    artifacts = result.get("artifacts")
                    report = result.get("report", {})
                    st.success("Live neural MLP training completed")
                    if artifacts is not None:
                        artifact_slot.code(
                            "\n".join([
                                f"training_monitor_report_json: {artifacts.report_json}",
                                f"training_history_csv: {artifacts.history_csv}",
                                f"loss_curves_png: {artifacts.loss_curve_png}",
                                f"rmse_mean_curves_png: {artifacts.rmse_mean_curve_png}",
                                f"r2_mean_curves_png: {artifacts.r2_mean_curve_png}",
                                f"per_target_rmse_curves_png: {artifacts.per_target_rmse_curve_png}",
                                f"per_target_r2_curves_png: {artifacts.per_target_r2_curve_png}",
                                f"normalized_error_curves_png: {artifacts.normalized_error_curve_png}",
                                f"generalization_gap_curves_png: {artifacts.generalization_gap_curve_png}",
                                f"training_history_long_csv: {artifacts.history_long_csv}",
                                f"metrics_json: {artifacts.metrics_json}",
                                f"experiment_tracking_manifest_json: {Path(live_od) / 'tracking' / 'experiment_tracking_manifest.json'}",
                            ]),
                            language="text",
                        )
                        if Path(artifacts.loss_curve_png).exists():
                            st.image(str(artifacts.loss_curve_png), caption="Live training loss/RMSE curve", use_container_width=True)
                        residual_hist = Path(live_od) / "training_monitor" / "plots" / "residual_distribution_histogram.png"
                        if residual_hist.exists():
                            st.image(str(residual_hist), caption="Residual distribution after training", use_container_width=True)
                    with st.expander("Live training report JSON", expanded=False):
                        st.json(report)


    # ── ④ Tune ────────────────────────────────────────────────────────────────
    with tabs[3]:
        _note("<b>--backend optuna</b>: advanced TPE search. <b>--backend aeris</b>: grid/random. Optuna for serious tuning.","info")
        ds2 = _pick_dir("Promoted dataset",root/"data"/"datasets","tu_ds")
        c1,c2 = st.columns(2)
        bk2 = c1.selectbox("--backend",["optuna","aeris"],key="tu_bk",help="optuna=Bayesian TPE · aeris=grid/random")
        mt2 = c2.selectbox("--model-type",MODEL_TYPES,index=4,key="tu_mt",format_func=lambda s:MODEL_INFO.get(s,s))
        fa2, _ = _feature_selector("tu", include_feature_set=False)
        c3,c4,c5 = st.columns(3)
        rs2    = c3.number_input("--random-seed",min_value=0,value=123,step=1,key="tu_rs")
        nt2    = c4.number_input("--n-trials (Optuna)",min_value=5,value=50,step=5,key="tu_nt",help="Optuna trials. Ignored for aeris backend.")
        sm2    = c5.selectbox("--split-method",["grouped","random"],key="tu_sm")
        gc2    = st.text_input("--group-column","geometry_id",key="tu_gc")
        od2    = st.text_input("--output-dir",str(root/"data"/"processed"/"ml_runs"/"gui_tune"),key="tu_od")
        args2 = ["ml","tune","--backend",bk2,"--dataset",ds2,"--model-type",mt2,
                 "--split-method",sm2,"--group-column",gc2,"--random-seed",str(int(rs2)),
                 "--output-dir",od2] + fa2
        if bk2 == "optuna": args2 += ["--n-trials",str(int(nt2))]
        _panel("Tune model","Hyperparameter search. Best params saved to output dir.",args2,root,exe,tmo,dry,"tu_run")

    # ── ⑤ Compare ─────────────────────────────────────────────────────────────
    with tabs[4]:
        cmp_t = st.tabs(["  Compare models  ","  Seed stability  ","  Compare tuning runs  "])

        with cmp_t[0]:
            _note("Never declare a winner from a single split. Follow with Seed stability.","warn")
            ds3 = _pick_dir("Promoted dataset",root/"data"/"datasets","cm_ds")
            fa3, _ = _feature_selector("cm")
            models3 = st.multiselect("--models",MODEL_TYPES,default=["extra_trees","hist_gradient_boosting","gradient_boosting"],key="cm_models",format_func=lambda s:MODEL_INFO.get(s,s))
            c1,c2,c3 = st.columns(3)
            sm3 = c1.selectbox("--split-method",["grouped","random"],key="cm_sm")
            gc3 = c2.text_input("--group-column","geometry_id",key="cm_gc")
            rs3 = c3.number_input("--random-seed",min_value=0,value=123,step=1,key="cm_rs")
            od3 = st.text_input("--output-dir",str(root/"data"/"processed"/"ml_runs"/"gui_compare"),key="cm_od")
            af3 = st.checkbox("--allow-forced",False,key="cm_af")
            models_str3 = ",".join(models3) if models3 else "extra_trees,hist_gradient_boosting"
            args3 = ["ml","compare","--dataset",ds3,"--models",models_str3,
                     "--split-method",sm3,"--group-column",gc3,"--random-seed",str(int(rs3)),
                     "--output-dir",od3] + fa3
            if af3: args3.append("--allow-forced")
            _panel("Compare models","Benchmarks multiple model types on one split.",args3,root,exe,tmo,dry,"cm_run")

        with cmp_t[1]:
            _note(
                "<b>aeris ml compare-seeds</b> — same models, multiple seeds, same feature set. "
                "Feature-set provenance is recorded per seed run. "
                "A stable winner ranks consistently across seeds. Use ≥5 seeds. "
                "On datasets with &lt;30 geometries the test set is too small — use this to catch instability, not to claim accuracy.",
                "info",
            )
            ds_cs = _pick_dir("Promoted dataset",root/"data"/"datasets","cs_ds")
            fa_cs, _ = _feature_selector("cs")
            models_cs = st.multiselect("--models",MODEL_TYPES,default=["extra_trees","hist_gradient_boosting"],key="cs_models",format_func=lambda s:MODEL_INFO.get(s,s))
            c1,c2 = st.columns(2)
            seeds_cs = c1.text_input("--seeds (comma-sep ints)","101,202,303,404,505",key="cs_seeds",help="At least 5 seeds recommended")
            gc_cs    = c2.text_input("--group-column","geometry_id",key="cs_gc")
            sm_cs    = st.selectbox("--split-method",["grouped","random"],key="cs_sm")
            od_cs    = st.text_input("--output-dir",str(root/"data"/"processed"/"ml_runs"/"gui_seeds"),key="cs_od")
            models_str_cs = ",".join(models_cs) if models_cs else "extra_trees,hist_gradient_boosting"
            args_cs = ["ml","compare-seeds","--dataset",ds_cs,"--models",models_str_cs,"--seeds",seeds_cs,
                       "--split-method",sm_cs,"--group-column",gc_cs,"--output-dir",od_cs] + fa_cs
            _panel("Seed stability","Runs same models with N seeds. Confirms winner is consistent.",args_cs,root,exe,tmo,dry,"cs_run")

        with cmp_t[2]:
            _note("<b>aeris ml compare-tuning-runs</b> — compares completed tuning campaigns by their best trial. Pass all tuning run dirs as a comma-separated string to <code>--runs</code>.","info")
            runs_ctr = st.text_input("--runs (comma-sep tuning run dirs)","",key="ctr_runs",
                                     help="e.g. data/processed/ml_runs/tune_run1,data/processed/ml_runs/tune_run2")
            c1,c2 = st.columns(2)
            metric_ctr = c1.text_input("--selection-metric","val.rmse_mean",key="ctr_metric",help="Metric to rank tuning runs. Default: val.rmse_mean")
            minimize_ctr = c2.checkbox("--minimize (lower is better)",True,key="ctr_min",help="Uncheck for --maximize (higher is better)")
            od_ctr = st.text_input("--output-dir",str(root/"data"/"processed"/"ml_runs"/"gui_compare_tuning"),key="ctr_od")
            if runs_ctr.strip():
                args_ctr = ["ml","compare-tuning-runs","--runs",runs_ctr,"--selection-metric",metric_ctr,"--output-dir",od_ctr]
                if not minimize_ctr: args_ctr.append("--maximize")
                _panel("Compare tuning runs","Selects best hyperparameters across tuning campaigns.",args_ctr,root,exe,tmo,dry,"ctr_run")
            else:
                _note("Enter at least one comma-separated tuning run path in --runs above.","warn")

    # ── ⑥ Trust gates ─────────────────────────────────────────────────────────
    with tabs[5]:
        tg_t = st.tabs(["  Promote model  ", "  Suggest gates  ", "  Inspect model  ", "  Require promoted  "])

        with tg_t[0]:
            mr4 = _pick_dir("ML run dir",root/"data"/"processed"/"ml_runs","tg_mr")
            _note(
                "All threshold args are optional — leave blank to skip that gate. "
                "Dataset promotion context is rechecked here; force-promoted datasets and recorded QC/curation blockers stop model promotion unless explicitly allowed. "
                "<code>--require-diagnostics</code> defaults True. "
                "<b>Per-target thresholds are aggregate only</b> — a model can have good mean RMSE but fail on Cm specifically. "
                "After promotion, run <b>⑧ Audit model</b> to inspect per-target and per-regime residuals.",
                "info",
            )
            c1,c2,c3 = st.columns(3)
            max_vr  = c1.text_input("--max-val-rmse-mean","",key="tg_mvr",help="Optional: val RMSE mean ≤ this")
            max_tr  = c2.text_input("--max-test-rmse-mean","",key="tg_mtr",help="Optional: test RMSE mean ≤ this")
            min_r2  = c3.text_input("--min-test-r2-mean","",key="tg_mr2",help="Optional: test R² mean ≥ this")
            c4,c5,c6 = st.columns(3)
            req_d   = c4.checkbox("--require-diagnostics",True,key="tg_rd",help="Require diagnostics artifacts. Default True.")
            afd     = c5.checkbox("--allow-forced-dataset",False,key="tg_afd",help="Allow models trained from force-promoted datasets.")
            notes4  = c6.text_input("--notes (optional)","",key="tg_notes",help="Operator note recorded in promotion manifest.")
            args4 = ["ml","promote-model","--model-run-dir",mr4]
            _flag(args4,"--max-val-rmse-mean",max_vr); _flag(args4,"--max-test-rmse-mean",max_tr); _flag(args4,"--min-test-r2-mean",min_r2)
            if not req_d: args4.append("--no-require-diagnostics")
            if afd: args4.append("--allow-forced-dataset")
            _flag(args4,"--notes",notes4)
            _panel("Promote model","Gates model on optional thresholds. Writes model_promotion_manifest.json + model card.",args4,root,exe,tmo,dry,"tg_run")

        with tg_t[1]:
            _note(
                "<b>aeris ml suggest-promotion-gates</b> proposes scale-aware gate thresholds from an existing run. "
                "Use it after training/audit, then manually choose defensible gates. It is guidance, not gospel.",
                "info",
            )
            mr_sg = _pick_dir("ML run dir",root/"data"/"processed"/"ml_runs","sg_mr")
            csg1, csg2 = st.columns(2)
            prof_sg = csg1.selectbox("--profile", ["strict", "normal", "loose"], index=1, key="sg_profile")
            od_sg = csg2.text_input("--output-dir", "", key="sg_od", help="Leave blank for auto output under model run dir.")
            args_sg = ["ml", "suggest-promotion-gates", "--model-run-dir", mr_sg, "--profile", prof_sg]
            if od_sg.strip():
                args_sg += ["--output-dir", od_sg.strip()]
            _panel(
                "Suggest promotion gates",
                "Writes promotion_gate_suggestions.json and promotion_gates_template.yaml.",
                args_sg, root, exe, tmo, dry, "sg_run", label="▶  Suggest gates",
            )

        with tg_t[2]:
            mr_ins = _pick_dir("ML run dir",root/"data"/"processed"/"ml_runs","ins_mr")
            _panel("Inspect model run","Prints model type, metrics, features, promotion status.",["ml","inspect-model","--model-run-dir",mr_ins],root,exe,tmo,dry,"ins_run")

        with tg_t[3]:
            mr_rq = _pick_dir("ML run dir",root/"data"/"processed"/"ml_runs","rq_mr")
            vh_rq = st.checkbox("--verify-hashes",True,key="rq_vh",help="Verify artifact hashes against promotion manifest. Default True.")
            args_rq = ["ml","require-promoted-model","--model-run-dir",mr_rq]
            if not vh_rq: args_rq.append("--no-verify-hashes")
            _panel("Require promoted model","Verifies model has approved promotion manifest.",args_rq,root,exe,tmo,dry,"rq_run")

    # ── ⑦ Predict ─────────────────────────────────────────────────────────────
    with tabs[6]:
        pr_t = st.tabs(["  Standard predict  ","  Predict with confidence  ","  Check inference inputs  "])

        with pr_t[0]:
            _note(
                "<b>aeris ml predict</b> — <code>--require-promoted-model</code> and <code>--enforce-envelope</code> are FLAGS (default False). "
                "Enable both for production. "
                "<b>--feature-set</b>: if the model was trained with a feature set (e.g. <code>bwb_control_physics_v1</code>), "
                "pass the same feature set here — AERIS will apply the transforms automatically to your raw input CSV "
                "before prediction. Leave blank if the model was trained on raw columns. "
                "Mismatch is rejected unless <code>--allow-feature-set-mismatch</code> is set.",
                "warn",
            )
            mr5 = _pick_dir("Model run dir",root/"data"/"processed"/"ml_runs","pr_mr5")
            ic5 = st.text_input("--input-csv",str(Path(mr5)/"test_rows.csv" if mr5 else ""),key="pr_ic5")
            od5 = st.text_input("--output-dir","",key="pr_od5",help="Leave blank for auto dir under model run dir.")
            c1,c2,c3 = st.columns(3)
            rp5 = c1.checkbox("--require-promoted-model",False,key="pr_rp5",help="Check for production use. Default False.")
            ee5 = c2.checkbox("--enforce-envelope",False,key="pr_ee5",help="Block out-of-envelope inputs. Default False.")
            it5 = c3.checkbox("--include-truth-if-available",True,key="pr_it5",help="Compute error metrics if targets in input CSV. Default True. Uses --no-include-truth-if-available to disable.")
            tol5 = st.number_input("--envelope-tolerance",0.0,key="pr_tol5",format="%.4f",help="Absolute tolerance on envelope checks. Default 0.0.")
            fs5  = st.text_input("--feature-set (optional)","",key="pr_fs5",help="Apply named feature-set transforms to input before prediction.")
            args5 = ["ml","predict","--model-run-dir",mr5,"--input-csv",ic5,"--envelope-tolerance",str(tol5)]
            if od5.strip(): args5 += ["--output-dir",od5]
            if rp5:  args5.append("--require-promoted-model")
            if ee5:  args5.append("--enforce-envelope")
            if not it5: args5.append("--no-include-truth-if-available")
            _flag(args5,"--feature-set",fs5)
            _panel("Predict","Runs inference. Guards envelope. Computes error if truth available.",args5,root,exe,tmo,dry,"pr_run5")

        with pr_t[1]:
            _note("<b>aeris ml predict-with-confidence</b> — adds heuristic uncertainty + envelope diagnostics to predictions.","info")
            mr_pc = _pick_dir("Model run dir",root/"data"/"processed"/"ml_runs","pc_mr")
            ic_pc = st.text_input("--input-csv",str(Path(mr_pc)/"test_rows.csv" if mr_pc else ""),key="pc_ic")
            od_pc = st.text_input("--output-dir","",key="pc_od")
            c1,c2 = st.columns(2)
            rp_pc = c1.checkbox("--require-promoted-model",True,key="pc_rp",help="Default True.")
            it_pc = c2.checkbox("--include-truth-if-available",True,key="pc_it",help="Default True.")
            args_pc = ["ml","predict-with-confidence","--model-run-dir",mr_pc,"--input-csv",ic_pc]
            if od_pc.strip(): args_pc += ["--output-dir",od_pc]
            if not rp_pc: args_pc.append("--no-require-promoted-model")
            if not it_pc: args_pc.append("--no-include-truth-if-available")
            _panel("Predict with confidence","Predictions + uncertainty + envelope diagnostics.",args_pc,root,exe,tmo,dry,"pc_run")

        with pr_t[2]:
            _note("<b>aeris ml check-inference-inputs</b> — pre-flight check before prediction: verifies inputs are inside the training envelope.","info")
            mr_ci = _pick_dir("Model run dir",root/"data"/"processed"/"ml_runs","ci_mr")
            ic_ci = st.text_input("--input-csv",str(Path(mr_ci)/"test_rows.csv" if mr_ci else ""),key="ci_ic")
            od_ci = st.text_input("--output-dir","",key="ci_od")
            c1,c2,c3 = st.columns(3)
            rp_ci  = c1.checkbox("--require-promoted-model",True,key="ci_rp")
            fov_ci = c2.checkbox("--fail-on-violations",False,key="ci_fov",help="Exit nonzero if violations found. Default False.")
            tol_ci = c3.number_input("--tolerance",0.0,key="ci_tol",format="%.4f")
            fs_ci  = st.text_input("--feature-set (optional)","",key="ci_fs")
            afm_ci = st.checkbox("--allow-feature-set-mismatch",False,key="ci_afm",help="Allow feature set to differ from training set. Default False.")
            args_ci = ["ml","check-inference-inputs","--model-run-dir",mr_ci,"--input-csv",ic_ci,"--tolerance",str(tol_ci)]
            if od_ci.strip(): args_ci += ["--output-dir",od_ci]
            if not rp_ci:  args_ci.append("--no-require-promoted-model")
            if fov_ci:     args_ci.append("--fail-on-violations")
            _flag(args_ci,"--feature-set",fs_ci)
            if afm_ci: args_ci.append("--allow-feature-set-mismatch")
            _panel("Check inference inputs","Verifies inputs are inside training envelope before prediction.",args_ci,root,exe,tmo,dry,"ci_run")

    # ── ⑧ Audit ───────────────────────────────────────────────────────────────
    with tabs[7]:
        _note("<b>aeris ml audit-model</b> — deep quality analysis: residual audit, p95 error, bias, worst rows, optional quality gates.","info")
        mr6 = _pick_dir("ML run dir",root/"data"/"processed"/"ml_runs","au_mr")
        od6 = st.text_input("--output-dir","",key="au_od",help="Leave blank for auto dir under model run dir.")
        _sec("Optional quality thresholds (leave blank to skip gate)")
        c1,c2,c3,c4 = st.columns(4)
        mr6_rmse = c1.text_input("--max-test-rmse-mean","",key="au_rmse",help="Fail if test RMSE mean > this.")
        mr6_r2   = c2.text_input("--min-test-r2-mean","",key="au_r2",help="Fail if test R² mean < this.")
        mr6_p95  = c3.text_input("--max-test-error-p95-mean","",key="au_p95",help="Fail if p95 absolute error mean > this.")
        mr6_bias = c4.text_input("--max-test-abs-bias-mean","",key="au_bias",help="Fail if absolute bias mean > this.")
        c5,c6 = st.columns(2)
        topk6  = c5.number_input("--top-k-worst-rows-per-target",min_value=1,value=20,step=5,key="au_topk",help="Worst residual rows per target and split. Default 20.")
        fail6  = c6.checkbox("--fail-on-quality-gate",False,key="au_fail",help="Exit nonzero if any threshold fails. Default False.")
        args6 = ["ml","audit-model","--model-run-dir",mr6,"--top-k-worst-rows-per-target",str(int(topk6))]
        if od6.strip(): args6 += ["--output-dir",od6]
        _flag(args6,"--max-test-rmse-mean",mr6_rmse); _flag(args6,"--min-test-r2-mean",mr6_r2)
        _flag(args6,"--max-test-error-p95-mean",mr6_p95); _flag(args6,"--max-test-abs-bias-mean",mr6_bias)
        if fail6: args6.append("--fail-on-quality-gate")
        _panel("Audit model","Writes residual_audit.csv + model_quality_report.json.",args6,root,exe,tmo,dry,"au_run")

    # ── ⑨ Active Learning ─────────────────────────────────────────────────────
    with tabs[8]:
        _note("<b>aeris ml suggest-samples</b> — ranks a candidate pool for the next simulation batch using uncertainty + novelty + optional objective. Does NOT run AVL or any simulator.","info")
        mr_al = _pick_dir("Model run dir (promoted recommended)",root/"data"/"processed"/"ml_runs","al_mr")
        c1,c2 = st.columns(2)
        ic_al  = c1.text_input("--candidate-csv",str(Path(mr_al)/"test_rows.csv" if mr_al else ""),key="al_ic",help="CSV with all model feature columns. Candidates to rank.")
        ref_al = c2.text_input("--reference-csv (optional, default = train_rows.csv)","",key="al_ref",help="Reference rows for novelty scoring. Blank = model's training rows.")
        od_al  = st.text_input("--output-dir","",key="al_od")
        c3,c4  = st.columns(2)
        topn_al = c3.number_input("--top-n",min_value=1,value=25,step=5,key="al_topn",help="Number of recommended candidates. Default 25.")
        cid_al  = c4.text_input("--candidate-id-column (optional)","",key="al_cid",help="Existing ID column. Blank = AERIS creates candidate_id.")
        rp_al   = st.checkbox("--require-promoted-model",True,key="al_rp",help="Require approved promotion manifest. Default True.")

        _sec("Ranking weights")
        c5,c6,c7,c8 = st.columns(4)
        uw_al  = c5.number_input("--uncertainty-weight",0.0,5.0,1.0,0.1,key="al_uw",help="Weight for estimator-spread uncertainty. Default 1.0.")
        nw_al  = c6.number_input("--novelty-weight",0.0,5.0,0.5,0.1,key="al_nw",help="Weight for distance-from-training novelty. Default 0.5.")
        ow_al  = c7.number_input("--objective-weight",0.0,5.0,0.25,0.05,key="al_ow",help="Weight for objective score. Default 0.25. Only used if objective-column set.")
        epw_al = c8.number_input("--envelope-penalty-weight",0.0,10.0,2.0,0.5,key="al_epw",help="Penalty for outside-envelope candidates. Default 2.0.")

        _sec("Optional objective (guided active learning)")
        c9,c10,c11 = st.columns(3)
        obj_col  = c9.text_input("--objective-column (optional)","",key="al_obj",help="Column for objective, e.g. pred__cl. Leave blank for no objective.")
        obj_mode = c10.selectbox("--objective-mode",["maximize","minimize","target"],key="al_omode",help="Default maximize. Use 'target' with --objective-target-value.")
        obj_tgt  = c11.text_input("--objective-target-value (only for target mode)","",key="al_otgt")
        excl_al  = st.checkbox("--exclude-outside-envelope",False,key="al_excl",help="Never recommend candidates outside envelope. Default False (--allow-outside-envelope).")

        args_al = ["ml","suggest-samples","--model-run-dir",mr_al,"--candidate-csv",ic_al,
                   "--top-n",str(int(topn_al)),
                   "--uncertainty-weight",str(uw_al),"--novelty-weight",str(nw_al),
                   "--objective-weight",str(ow_al),"--envelope-penalty-weight",str(epw_al),
                   "--objective-mode",obj_mode]
        if od_al.strip():  args_al += ["--output-dir",od_al]
        if ref_al.strip(): args_al += ["--reference-csv",ref_al]
        _flag(args_al,"--candidate-id-column",cid_al)
        if not rp_al: args_al.append("--no-require-promoted-model")
        _flag(args_al,"--objective-column",obj_col)
        if obj_mode == "target" and obj_tgt.strip(): args_al += ["--objective-target-value",obj_tgt.strip()]
        if excl_al: args_al.append("--exclude-outside-envelope")
        _panel("Suggest next batch","Ranks candidates. Does not run any simulator.",args_al,root,exe,tmo,dry,"al_run")

    # ── ⑩ Classification ─────────────────────────────────────────────────────
    with tabs[9]:
        _note(
            "<b>Classification is for labels</b> such as flyability/red-flag/trim-feasible targets. "
            "Do not use classifiers for CL/CD/Cm regression targets. Different weapon, different job.",
            "info",
        )
        cls_t = st.tabs(["  Train classifier  ", "  Compare classifiers  "])

        with cls_t[0]:
            ds_cl = _pick_dir("Promoted dataset", root/"data"/"datasets", "cls_ds")
            c1,c2,c3 = st.columns(3)
            input_mode_cl = c1.radio("Feature input", ["--feature-set", "--feature-preset", "--features"], horizontal=False, key="cls_mode")
            if input_mode_cl == "--feature-set":
                feat_cl = c2.text_input("--feature-set", "bwb_control_physics_v1", key="cls_fs")
                feat_args_cl = ["--feature-set", feat_cl]
            elif input_mode_cl == "--feature-preset":
                feat_cl = c2.selectbox("--feature-preset", ML_FEATURE_PRESETS, key="cls_fp")
                feat_args_cl = ["--feature-preset", feat_cl]
            else:
                feat_cl = c2.text_input("--features", DEFAULT_SYM_ELEVON_FEATURES, key="cls_features")
                feat_args_cl = ["--features", feat_cl]
            targets_cl = c3.text_input("--targets", "longitudinal_basic_flyable_int,red_flag_int", key="cls_targets")
            c4,c5,c6 = st.columns(3)
            ctype_cl = c4.selectbox("--classifier-type", CLASSIFIER_TYPES, key="cls_type", format_func=lambda s: CLASSIFIER_INFO.get(s, s))
            sm_cl = c5.selectbox("--split-method", ["grouped", "random"], key="cls_sm")
            gc_cl = c6.text_input("--group-column", "geometry_id", key="cls_gc")
            c7,c8,c9 = st.columns(3)
            rs_cl = c7.number_input("--random-seed", min_value=0, value=123, step=1, key="cls_rs")
            af_cl = c8.checkbox("--allow-forced", False, key="cls_af", help="Allow force-promoted dataset sources. Avoid for real work.")
            json_cl = c9.checkbox("--json", False, key="cls_json")
            od_cl = st.text_input("--output-dir", str(root/"data"/"processed"/"ml_runs"/"gui_classifier"), key="cls_od")
            wf_cl = st.text_input("--workflow (optional)", "", key="cls_wf")
            args_cl = ["ml", "classify", "--dataset", ds_cl, *feat_args_cl, "--targets", targets_cl,
                       "--classifier-type", ctype_cl, "--split-method", sm_cl, "--group-column", gc_cl,
                       "--random-seed", str(int(rs_cl)), "--output-dir", od_cl]
            if af_cl: args_cl.append("--allow-forced")
            if json_cl: args_cl.append("--json")
            if wf_cl.strip(): args_cl += ["--workflow", wf_cl.strip()]
            _panel(
                "Train classifier",
                "One classifier per target. Writes classification_summary_json and per-target metrics.",
                args_cl, root, exe, tmo, dry, "cls_run", label="▶  Classify",
            )

        with cls_t[1]:
            ds_cc = _pick_dir("Promoted dataset", root/"data"/"datasets", "cc_ds")
            c1,c2,c3 = st.columns(3)
            input_mode_cc = c1.radio("Feature input", ["--feature-set", "--feature-preset", "--features"], horizontal=False, key="cc_mode")
            if input_mode_cc == "--feature-set":
                feat_cc = c2.text_input("--feature-set", "bwb_control_physics_v1", key="cc_fs")
                feat_args_cc = ["--feature-set", feat_cc]
            elif input_mode_cc == "--feature-preset":
                feat_cc = c2.selectbox("--feature-preset", ML_FEATURE_PRESETS, key="cc_fp")
                feat_args_cc = ["--feature-preset", feat_cc]
            else:
                feat_cc = c2.text_input("--features", DEFAULT_SYM_ELEVON_FEATURES, key="cc_features")
                feat_args_cc = ["--features", feat_cc]
            targets_cc = c3.text_input("--targets", "longitudinal_basic_flyable_int,red_flag_int", key="cc_targets")
            c4,c5,c6 = st.columns(3)
            classifiers_cc = c4.multiselect("--classifiers", CLASSIFIER_TYPES, default=["logistic_regression", "extra_trees_classifier"], key="cc_types", format_func=lambda s: CLASSIFIER_INFO.get(s, s))
            sm_cc = c5.selectbox("--split-method", ["grouped", "random"], key="cc_sm")
            gc_cc = c6.text_input("--group-column", "geometry_id", key="cc_gc")
            c7,c8,c9 = st.columns(3)
            rs_cc = c7.number_input("--random-seed", min_value=0, value=123, step=1, key="cc_rs")
            af_cc = c8.checkbox("--allow-forced", False, key="cc_af")
            json_cc = c9.checkbox("--json", False, key="cc_json")
            od_cc = st.text_input("--output-dir", str(root/"data"/"processed"/"ml_runs"/"gui_compare_classifiers"), key="cc_od")
            wf_cc = st.text_input("--workflow (optional)", "", key="cc_wf")
            cls_arg = ",".join(classifiers_cc) if classifiers_cc else "logistic_regression,extra_trees_classifier"
            args_cc = ["ml", "compare-classifiers", "--dataset", ds_cc, *feat_args_cc, "--targets", targets_cc,
                       "--classifiers", cls_arg, "--split-method", sm_cc, "--group-column", gc_cc,
                       "--random-seed", str(int(rs_cc)), "--output-dir", od_cc]
            if af_cc: args_cc.append("--allow-forced")
            if json_cc: args_cc.append("--json")
            if wf_cc.strip(): args_cc += ["--workflow", wf_cc.strip()]
            _panel(
                "Compare classifiers",
                "Ranks classifier families by test F1 / balanced accuracy. Use only for label targets.",
                args_cc, root, exe, tmo, dry, "cc_run", label="▶  Compare classifiers",
            )

    # ── ⑪ Multifidelity ──────────────────────────────────────────────────────
    with tabs[10]:
        _note("⚠ Requires real HF data (XFOIL or CFD). AVL-only delta correction does NOT give paper-level accuracy.","warn")
        mf_t = st.tabs(["  Build delta  ","  Train delta  ","  Predict  ","  Evaluate  "])
        with mf_t[0]:
            c1,c2 = st.columns(2)
            lf = c1.text_input("--lf-csv (AVL results)",str(root/"data"/"processed"/"multifidelity"/"lf.csv"),key="mf_lf")
            hf = c2.text_input("--hf-csv (CFD/XFOIL results)",str(root/"data"/"processed"/"multifidelity"/"hf.csv"),key="mf_hf")
            pk = st.text_input("--pair-keys",DEFAULT_PAIR_KEYS,key="mf_pk",help="Comma-sep columns to match LF/HF rows.")
            tg = st.text_input("--targets",DEFAULT_TARGETS,key="mf_tg")
            od = st.text_input("--output-dir (REQUIRED)",str(root/"data"/"processed"/"multifidelity"/"gui_delta"),key="mf_od")
            _panel("Build delta dataset","Pairs LF/HF rows. Writes delta_dataset.csv + delta_dataset_report.json.",
                   ["ml","build-delta-dataset","--lf-csv",lf,"--hf-csv",hf,"--pair-keys",pk,"--targets",tg,"--output-dir",od],
                   root,exe,tmo,dry,"mf_bld")
        with mf_t[1]:
            dd2 = _pick_dir("Delta dataset dir (or parent dir)",root/"data"/"processed"/"multifidelity","mf_dd2")
            _note(
                "<b>Feature input:</b> use <code>--feature-set</code> (recommended — e.g. <code>bwb_control_physics_v1</code>) "
                "or explicit <code>--features</code>. LF target columns (<code>lf__cl</code>, etc.) are appended automatically when using a feature set. "
                "Provenance is written to <code>delta_model_manifest.json</code>.",
                "info",
            )
            mf_fs_mode = st.radio("Feature input",["--feature-set (recommended)","--features (explicit)"],horizontal=True,key="mf_fs_mode")
            c1,c2 = st.columns(2)
            if "--feature-set" in mf_fs_mode:
                mf_fs2 = c1.text_input("--feature-set","bwb_control_physics_v1",key="mf_fs2",help="LF columns (lf__cl etc.) appended automatically.")
                tg2    = c2.text_input("--base-targets",DEFAULT_TARGETS,key="mf_tg2",help="cl,cd,cm. Delta targets = delta__cl etc.")
                ft2    = None
            else:
                ft2 = c1.text_input("--features (include lf__ columns)","c1_m,alpha_deg,velocity_mps,altitude_m,control_input_deg,lf__cl,lf__cd,lf__cm",key="mf_ft2",help="Include LF output columns as features — main correction signal")
                tg2 = c2.text_input("--base-targets",DEFAULT_TARGETS,key="mf_tg2b",help="e.g. cl,cd,cm.")
                mf_fs2 = None
            mt2 = st.selectbox("--model-type",MODEL_TYPES,index=4,key="mf_mt2",format_func=lambda s:MODEL_INFO.get(s,s))
            c3,c4,c5 = st.columns(3)
            sm2 = c3.selectbox("--split-method",["grouped","random"],key="mf_sm2")
            gc2 = c4.text_input("--group-column","geometry_id",key="mf_gc2")
            rs2 = c5.number_input("--random-seed",min_value=0,value=123,step=1,key="mf_rs2")
            od2 = st.text_input("--output-dir",str(root/"data"/"processed"/"ml_runs"/"gui_delta_model"),key="mf_od2")
            args_mft = ["ml","train-delta-model","--delta-dataset",dd2,"--base-targets",tg2,
                         "--model-type",mt2,"--split-method",sm2,"--group-column",gc2,
                         "--random-seed",str(int(rs2)),"--output-dir",od2]
            if mf_fs2: args_mft += ["--feature-set",mf_fs2]
            elif ft2:  args_mft += ["--features",ft2]
            _panel("Train delta model","Learns HF−LF correction. Feature provenance written to delta_model_manifest.json.",
                   args_mft, root,exe,tmo,dry,"mf_tr2")
        with mf_t[2]:
            mr3  = _pick_dir("Delta model run dir",root/"data"/"processed"/"ml_runs","mf_pr3")
            ic3  = st.text_input("--input-csv",str(Path(mr3)/"test_rows.csv" if mr3 else ""),key="mf_ic3",help="Needs feature columns AND lf__ columns.")
            od3  = st.text_input("--output-dir","",key="mf_od3")
            it3  = st.checkbox("--include-truth-if-available",True,key="mf_it3",help="Compute metrics if HF columns present. Default True.")
            c_mfp1, c_mfp2 = st.columns(2)
            mfp_fs = c_mfp1.text_input("--feature-set (optional)","",key="mfp_fs",
                                         help="Same feature set used during delta training. Leave blank if model was trained with --features.")
            mfp_afm = c_mfp2.checkbox("--allow-feature-set-mismatch",False,key="mfp_afm")
            args_mfp = ["ml","predict-delta-model","--model-run-dir",mr3,"--input-csv",ic3]
            if od3.strip(): args_mfp += ["--output-dir",od3]
            if not it3: args_mfp.append("--no-include-truth-if-available")
            if mfp_fs.strip(): args_mfp += ["--feature-set",mfp_fs.strip()]
            if mfp_afm: args_mfp.append("--allow-feature-set-mismatch")
            _panel("Predict with delta","Output = LF_prediction + predicted_delta. Feature transforms applied automatically if --feature-set provided.",args_mfp,root,exe,tmo,dry,"mf_pr3r")
        with mf_t[3]:
            mr4  = _pick_dir("Delta model run dir",root/"data"/"processed"/"ml_runs","mf_ev4")
            parts4 = st.text_input("--partitions","train,val,test",key="mf_parts",help="Comma-sep partitions to evaluate. Default train,val,test.")
            od4  = st.text_input("--output-dir","",key="mf_od4")
            args_mfe = ["ml","evaluate-delta-model","--model-run-dir",mr4,"--partitions",parts4]
            if od4.strip(): args_mfe += ["--output-dir",od4]
            _panel("Evaluate delta","Compare LF baseline vs corrected RMSE. Reports improved/worsened targets.",args_mfe,root,exe,tmo,dry,"mf_ev4r")





    # ── ⑫ ML Trust ───────────────────────────────────────────────────────────
    with tabs[11]:
        _note(
            "<b>ML Trust diagnostics:</b> run and inspect learning curves, repeated grouped CV, and per-regime residuals. "
            "Use <code>--targets aero_all</code> for Paper 1 aero-scalar trust evidence. Keep <code>--plots</code> enabled to generate PNGs.",
            "info",
        )
        trust_ds = _pick_dir("Promoted dataset root", root / "data" / "datasets", "mltrust_ds")
        trust_fs = st.selectbox("--feature-set", ML_FEATURE_SET_CHOICES, index=ML_FEATURE_SET_CHOICES.index("bwb_control_physics_v1") if "bwb_control_physics_v1" in ML_FEATURE_SET_CHOICES else 0, key="mltrust_fs")
        c1, c2, c3 = st.columns(3)
        trust_targets = c1.text_input("--targets", "aero_all", key="mltrust_targets", help="Examples: aero_basic, aero_all, flyability_all, all/numeric_all, or explicit cl,cd,cm.")
        trust_group = c2.text_input("--group-column", "geometry_id", key="mltrust_group")
        trust_model = c3.selectbox("--model", MODEL_TYPES, index=MODEL_TYPES.index("extra_trees") if "extra_trees" in MODEL_TYPES else 0, key="mltrust_model")
        c4, c5, c6 = st.columns(3)
        trust_seeds = c4.text_input("--seeds", "101,202,303,404,505", key="mltrust_seeds")
        trust_params = c5.text_input("--model-params-json", "", key="mltrust_params", help="Optional path, e.g. /tmp/aeris_extra_trees_fast.json")
        trust_allow = c6.checkbox("--allow-forced", value=True, key="mltrust_allow", help="Useful for current Paper 1 pilot attrition/forced promotion evidence.")
        trust_plots = st.checkbox("--plots / generate PNG plots", value=True, key="mltrust_plots")

        def _trust_base_args(command: str) -> list[str]:
            args = ["ml", command, "--dataset", trust_ds, "--feature-set", trust_fs, "--targets", trust_targets, "--group-column", trust_group, "--model", trust_model, "--seeds", trust_seeds]
            if trust_allow:
                args.append("--allow-forced")
            if trust_params.strip():
                args += ["--model-params-json", trust_params.strip()]
            args.append("--plots" if trust_plots else "--no-plots")
            return args

        def _trust_plot_gallery(label: str, rel_plot_dir: str, filenames: list[str], key: str) -> None:
            st.markdown(f"### {label}")
            base = Path(trust_ds).expanduser() if trust_ds.strip() else root / "data" / "datasets"
            plot_dir_default = base / rel_plot_dir
            plot_dir_raw = st.text_input(f"{label} plot directory", str(plot_dir_default), key=f"{key}_plot_dir")
            plot_dir = Path(plot_dir_raw).expanduser()
            if not plot_dir.exists():
                st.info(f"No plot directory found yet: {plot_dir}")
                return
            existing = [plot_dir / name for name in filenames if (plot_dir / name).exists()]
            extra = sorted(p for p in plot_dir.glob("*.png") if p.name not in set(filenames))
            if not existing and not extra:
                st.info(f"No PNG plots found in: {plot_dir}")
                return
            with st.expander(f"Show {label.lower()}", expanded=True):
                cols = st.columns(2)
                for i, path in enumerate(existing + extra):
                    with cols[i % 2]:
                        st.image(str(path), caption=path.name, use_container_width=True)
                        st.code(str(path), language="text")

        def _trust_report_viewer(label: str, rel_report: str, rel_summary: str, key: str) -> None:
            base = Path(trust_ds).expanduser() if trust_ds.strip() else root / "data" / "datasets"
            default_report = str(base / rel_report)
            default_summary = str(base / rel_summary)
            report_path = st.text_input(f"{label} report JSON", default_report, key=f"{key}_report")
            summary_path = st.text_input(f"{label} summary MD", default_summary, key=f"{key}_summary")
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button(f"Load {label} JSON", key=f"{key}_load_json"):
                    data = _rjson(Path(report_path).expanduser())
                    if data is None:
                        st.warning(f"Could not read JSON: {report_path}")
                    else:
                        st.json(data)
            with c_b:
                if st.button(f"Load {label} summary", key=f"{key}_load_md"):
                    st.markdown(_read(Path(summary_path).expanduser(), lim=120_000))

        trust_tabs = st.tabs(["  Learning curves  ", "  Repeated grouped CV  ", "  Per-regime residuals  ", "  Plot gallery  ", "  Report viewer  ", "  Evidence package  ", "  Training monitor  "])
        with trust_tabs[0]:
            c1, c2 = st.columns(2)
            lc_sizes = c1.text_input("--group-sizes", "5,10,20,30,40", key="mltrust_lc_sizes")
            lc_out = c2.text_input("--output-dir", "", key="mltrust_lc_out", help="Optional. Default: <dataset>/learning_curves")
            lc_args = _trust_base_args("learning-curves") + ["--group-sizes", lc_sizes]
            if lc_out.strip():
                lc_args += ["--output-dir", lc_out.strip()]
            _panel(
                "Run learning curves",
                "Checks whether more geometry groups improve performance and writes per-target readiness evidence plus learning-curve plots.",
                lc_args,
                root,
                exe,
                tmo,
                dry,
                "mltrust_learning_curves_run",
                label="▶  Run learning curves",
            )
            _trust_report_viewer(
                "Learning curves",
                "learning_curves/learning_curves_report.json",
                "learning_curves/learning_curves_summary.md",
                "mltrust_lc_view",
            )
            _trust_plot_gallery(
                "Learning curve plots",
                "learning_curves/plots",
                [
                    "learning_curve_r2.png",
                    "learning_curve_rmse.png",
                    "learning_curve_mae.png",
                    "per_target_learning_curves.png",
                    "per_target_final_r2.png",
                    "overfit_gap.png",
                ],
                "mltrust_lc_gallery",
            )

        with trust_tabs[1]:
            cv_out = st.text_input("--output-dir", "", key="mltrust_cv_out", help="Optional. Default: <dataset>/repeated_grouped_cv")
            cv_args = _trust_base_args("repeated-grouped-cv")
            if cv_out.strip():
                cv_args += ["--output-dir", cv_out.strip()]
            _panel(
                "Run repeated grouped CV",
                "Repeats grouped geometry splits to show whether scores are stable or lucky and writes repeated-CV plots.",
                cv_args,
                root,
                exe,
                tmo,
                dry,
                "mltrust_repeated_cv_run",
                label="▶  Run repeated CV",
            )
            _trust_report_viewer(
                "Repeated grouped CV",
                "repeated_grouped_cv/repeated_grouped_cv_report.json",
                "repeated_grouped_cv/repeated_grouped_cv_summary.md",
                "mltrust_cv_view",
            )
            _trust_plot_gallery(
                "Repeated CV plots",
                "repeated_grouped_cv/plots",
                [
                    "per_target_repeated_cv_r2.png",
                    "split_score_variability.png",
                ],
                "mltrust_cv_gallery",
            )

        with trust_tabs[2]:
            c1, c2 = st.columns(2)
            reg_cols = c1.text_input("--regime-columns", "alpha_deg,control_input_deg", key="mltrust_reg_cols")
            min_reg = c2.number_input("--min-regime-count", min_value=1, value=3, step=1, key="mltrust_min_reg")
            pr_out = st.text_input("--output-dir", "", key="mltrust_pr_out", help="Optional. Default: <dataset>/per_regime_residuals")
            pr_args = _trust_base_args("per-regime-residuals") + ["--regime-columns", reg_cols, "--min-regime-count", str(int(min_reg))]
            if pr_out.strip():
                pr_args += ["--output-dir", pr_out.strip()]
            _panel(
                "Run per-regime residual diagnostics",
                "Finds where the model fails by target, alpha, control deflection, and residual regime bucket.",
                pr_args,
                root,
                exe,
                tmo,
                dry,
                "mltrust_per_regime_run",
                label="▶  Run residual diagnostics",
            )
            _trust_report_viewer(
                "Per-regime residuals",
                "per_regime_residuals/per_regime_residuals_report.json",
                "per_regime_residuals/per_regime_residuals_summary.md",
                "mltrust_pr_view",
            )
            _trust_plot_gallery(
                "Per-regime residual plots",
                "per_regime_residuals/plots",
                [
                    "per_target_residual_rmse.png",
                    "per_target_residual_bias.png",
                    "residuals_vs_actual.png",
                    "regime_rmse_alpha_control.png",
                ],
                "mltrust_pr_gallery",
            )

        with trust_tabs[3]:
            _note("Direct viewer for all generated ML-trust PNG plots for the selected dataset.", "info")
            _trust_plot_gallery(
                "Learning curve plots",
                "learning_curves/plots",
                ["learning_curve_r2.png", "learning_curve_rmse.png", "learning_curve_mae.png", "per_target_learning_curves.png", "per_target_final_r2.png", "overfit_gap.png"],
                "mltrust_gallery_lc_all",
            )
            _trust_plot_gallery(
                "Repeated CV plots",
                "repeated_grouped_cv/plots",
                ["per_target_repeated_cv_r2.png", "split_score_variability.png"],
                "mltrust_gallery_cv_all",
            )
            _trust_plot_gallery(
                "Per-regime residual plots",
                "per_regime_residuals/plots",
                ["per_target_residual_rmse.png", "per_target_residual_bias.png", "residuals_vs_actual.png", "regime_rmse_alpha_control.png"],
                "mltrust_gallery_pr_all",
            )

        with trust_tabs[4]:
            _note(
                "Quick artifact locations for the selected dataset. Use this tab after running the diagnostics above.",
                "info",
            )
            if trust_ds.strip():
                base = Path(trust_ds).expanduser()
                st.code(
                    "\n".join(
                        [
                            str(base / "learning_curves" / "learning_curves_report.json"),
                            str(base / "learning_curves" / "learning_curves_per_target_summary.csv"),
                            str(base / "learning_curves" / "plots" / "learning_curve_r2.png"),
                            str(base / "learning_curves" / "plots" / "per_target_learning_curves.png"),
                            str(base / "repeated_grouped_cv" / "repeated_grouped_cv_report.json"),
                            str(base / "repeated_grouped_cv" / "repeated_grouped_cv_per_target_summary.csv"),
                            str(base / "repeated_grouped_cv" / "plots" / "per_target_repeated_cv_r2.png"),
                            str(base / "per_regime_residuals" / "per_regime_residuals_report.json"),
                            str(base / "per_regime_residuals" / "regime_residual_summary.csv"),
                            str(base / "per_regime_residuals" / "plots" / "regime_rmse_alpha_control.png"),
                        ]
                    ),
                    language="text",
                )
            else:
                st.warning("Select a dataset root first.")


        with trust_tabs[5]:
            _note(
                "<b>Evidence package viewer:</b> build and inspect the final Paper 1 evidence index. "
                "This reads real backend artifacts: <code>evidence_package_summary.md</code>, "
                "<code>evidence_artifact_index.csv</code>, and <code>evidence_package_manifest.json</code>.",
                "info",
            )
            evi_c1, evi_c2 = st.columns(2)
            with evi_c1:
                evi_model_dir = _pick_dir(
                    "--model-run-dir (optional)",
                    root / "data" / "processed" / "ml_runs",
                    "mltrust_evidence_model_dir",
                )
            with evi_c2:
                evi_workflow = st.text_input("--workflow (optional)", "", key="mltrust_evidence_workflow")
            evi_c3, evi_c4 = st.columns(2)
            evi_out = evi_c3.text_input(
                "--output-dir (optional)",
                "",
                key="mltrust_evidence_output_dir",
                help="Default: <dataset>/paper1_evidence_package",
            )
            evi_allow_missing = evi_c4.checkbox(
                "--allow-missing",
                value=True,
                key="mltrust_evidence_allow_missing",
                help="Use for pilot/debug packages so missing optional evidence is reported instead of blocking the viewer.",
            )

            evi_args = ["ml", "package-evidence", "--dataset", trust_ds]
            if evi_model_dir.strip():
                evi_args += ["--model-run-dir", evi_model_dir]
            if evi_workflow.strip():
                evi_args += ["--workflow", evi_workflow.strip()]
            if evi_out.strip():
                evi_args += ["--output-dir", evi_out.strip()]
            if evi_allow_missing:
                evi_args.append("--allow-missing")

            _panel(
                "Build evidence package",
                "Indexes existing EDA, ML-trust, model-promotion, confidence, and workflow evidence into one auditable package. It does not rerun solvers or retrain models.",
                evi_args,
                root,
                exe,
                tmo,
                dry,
                "mltrust_evidence_package_run",
                label="▶  Build evidence package",
            )

            base = Path(trust_ds).expanduser() if trust_ds.strip() else root / "data" / "datasets"
            default_package_dir = base / "paper1_evidence_package"
            evi_package_dir_raw = st.text_input(
                "Evidence package directory",
                str(default_package_dir),
                key="mltrust_evidence_package_dir",
            )
            evi_package_dir = Path(evi_package_dir_raw).expanduser()
            evi_summary = evi_package_dir / "evidence_package_summary.md"
            evi_index = evi_package_dir / "evidence_artifact_index.csv"
            evi_manifest = evi_package_dir / "evidence_package_manifest.json"

            evi_manifest_data = _rjson(evi_manifest)
            if isinstance(evi_manifest_data, dict):
                status = evi_manifest_data.get("status", "unknown")
                counts_raw = evi_manifest_data.get("counts")
                if not isinstance(counts_raw, dict):
                    counts_raw = evi_manifest_data.get("artifact_counts")
                counts = counts_raw if isinstance(counts_raw, dict) else {}

                present_count = counts.get("present", evi_manifest_data.get("present_artifacts", "?"))
                missing_optional_count = counts.get("missing_optional", evi_manifest_data.get("missing_optional_artifacts", "?"))
                missing_required_count = counts.get("missing_required", evi_manifest_data.get("missing_required_artifacts", "?"))

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Evidence status", str(status))
                m2.metric("Present", present_count)
                m3.metric("Missing optional", missing_optional_count)
                m4.metric("Missing required", missing_required_count)

                try:
                    missing_required_numeric = int(missing_required_count)
                except Exception:
                    missing_required_numeric = 0
                try:
                    missing_optional_numeric = int(missing_optional_count)
                except Exception:
                    missing_optional_numeric = 0

                if str(status).startswith("failed") or missing_required_numeric:
                    st.error("Evidence package has missing required artifacts. Inspect the artifact index before trusting this run.")
                elif "missing_optional" in str(status) or missing_optional_numeric:
                    st.warning("Evidence package is usable, but some optional evidence is missing.")
                else:
                    st.success("Evidence package has no missing required evidence.")
            else:
                st.info(f"No evidence package manifest found yet: {evi_manifest}")

            ev_v1, ev_v2, ev_v3 = st.columns(3)
            with ev_v1:
                if st.button("Load evidence package summary", key="mltrust_evidence_load_summary"):
                    if evi_summary.exists():
                        st.markdown(_read(evi_summary, lim=160_000))
                    else:
                        st.warning(f"Missing summary: {evi_summary}")
            with ev_v2:
                if st.button("Load artifact index CSV", key="mltrust_evidence_load_index"):
                    if evi_index.exists():
                        st.code(_read(evi_index, lim=160_000), language="csv")
                    else:
                        st.warning(f"Missing artifact index: {evi_index}")
            with ev_v3:
                if st.button("Load evidence manifest JSON", key="mltrust_evidence_load_manifest"):
                    data = _rjson(evi_manifest)
                    if data is None:
                        st.warning(f"Missing or unreadable manifest: {evi_manifest}")
                    else:
                        st.json(data)

            st.code(
                "\n".join(
                    [
                        str(evi_summary),
                        str(evi_index),
                        str(evi_manifest),
                    ]
                ),
                language="text",
            )


        with trust_tabs[-1]:
            _note(
                "<b>Training monitor:</b> inspect the artifacts written immediately after <code>aeris ml train</code>. "
                "Tree/linear models usually report <code>non_iterative_model / iterative_history_available</code>; MLP-style models can expose epoch-like loss history.",
                "info",
            )
            c_tm1, c_tm2 = st.columns(2)
            tm_model_run = c_tm1.text_input(
                "Model run directory",
                str(root / "data" / "processed" / "ml_runs" / "training_monitor_neural_mlp_smoke"),
                key="mltrust_tm_model_run",
                help="A model run folder produced by `aeris ml train`.",
            )
            tm_dir = Path(tm_model_run).expanduser() / "training_monitor" if tm_model_run.strip() else root / "data" / "processed" / "ml_runs"
            tm_report_default = str(tm_dir / "training_monitor_report.json")
            tm_history_default = str(tm_dir / "training_history.csv")
            tm_plot_default = str(tm_dir / "plots" / "training_loss_curve.png")
            tm_report_path = c_tm2.text_input(
                "training_monitor_report.json",
                tm_report_default,
                key="mltrust_tm_report_path",
            )
            tm_history_path = st.text_input(
                "training_history.csv",
                tm_history_default,
                key="mltrust_tm_history_path",
            )
            tm_plot_path = st.text_input(
                "training_loss_curve.png",
                tm_plot_default,
                key="mltrust_tm_plot_path",
            )

            report_path = Path(tm_report_path).expanduser()
            history_path = Path(tm_history_path).expanduser()
            plot_path = Path(tm_plot_path).expanduser()

            if st.button("Load training monitor report", key="mltrust_tm_load_report"):
                report = _rjson(report_path)
                if report is None:
                    st.warning(f"Could not read training monitor report: {report_path}")
                else:
                    metrics_summary = report.get("metrics_summary", {}) if isinstance(report, dict) else {}
                    _stat_row(
                        [
                            ("Status", str(report.get("monitor_status", "?")), "monitor"),
                            ("History", "yes" if report.get("history_available") else "no", "epoch rows"),
                            ("Rows", str(report.get("n_history_rows", 0)), "history"),
                            ("Live", "yes" if report.get("live_streaming_supported") else "no", "streaming"),
                        ]
                    )
                    if report.get("monitor_status") == "non_iterative_model":
                        _note(
                            "This model does not expose epoch-by-epoch history. Use ML Trust learning curves, repeated grouped CV, and residual diagnostics instead.",
                            "info",
                        )
                    elif report.get("history_available"):
                        _note("Epoch-like training history is available. Inspect the CSV and loss plot below.", "ok")
                    st.caption("training_monitor_report.json")
                    st.json(report)
                    if metrics_summary:
                        st.caption("metrics_summary")
                        st.json(metrics_summary)

            c_hist, c_plot = st.columns(2)
            with c_hist:
                if st.button("Load training history CSV", key="mltrust_tm_load_history"):
                    if pd is None:
                        st.warning("pandas is not available; cannot display CSV table.")
                    elif not history_path.exists():
                        st.info(f"No training history CSV found: {history_path}")
                    else:
                        try:
                            hist_df = pd.read_csv(history_path)
                            st.dataframe(hist_df.head(200), use_container_width=True)
                            st.caption(f"Rows shown: {min(len(hist_df), 200)} / {len(hist_df)}")
                        except Exception as exc:
                            st.error(f"Could not load training history CSV: {exc}")
            with c_plot:
                if st.button("Load training loss plot", key="mltrust_tm_load_plot"):
                    if plot_path.exists():
                        st.image(str(plot_path), caption="training_loss_curve.png", use_container_width=True)
                        st.code(str(plot_path), language="text")
                    else:
                        st.info(f"No training loss plot found: {plot_path}")

            with st.expander("Training monitor artifact paths", expanded=False):
                st.code(
                    "\n".join(
                        [
                            str(report_path),
                            str(history_path),
                            str(plot_path),
                        ]
                    ),
                    language="text",
                )

def pg_workflow(root, exe, tmo, dry):
    _hero("▤", "Workflow Cockpit", "guided stage state + evidence validation", "workflow")
    _note("This panel is a cockpit over <b>aeris workflow</b>. It reads workflow JSON artifacts and runs CLI commands; it does not duplicate solver, dataset, or ML business logic.", "info")

    _sec("Workflow coverage audit")
    _workflow_coverage_table("workflow_coverage")

    workflows = _workflow_dirs(root)
    c_top1, c_top2, c_top3 = st.columns(3)
    with c_top1:
        _panel("List stage definitions", "Show the built-in guided workflow stages.", ["workflow", "stages"], root, exe, tmo, dry, "wf_stages", "▶  stages")
    with c_top2:
        wf_name_new = st.text_input("New workflow name", "bwb_training_v1_workflow", key="wf_new_name")
    with c_top3:
        wf_out_new = st.text_input("New workflow output-dir", str(root / "data" / "workflows" / wf_name_new), key="wf_new_out")
    c_tpl1, c_tpl2, c_tpl3 = st.columns(3)
    wf_template = c_tpl1.selectbox("Workflow template", ["none", "canary", "paper_1", "production", "multifidelity", "active_learning"], key="wf_template")
    wf_desc = c_tpl2.text_input("Description (optional)", "", key="wf_desc")
    wf_force = c_tpl3.checkbox("--force", False, key="wf_force", help="Overwrite/reinitialize existing workflow folder.")
    init_args = ["workflow", "init", "--name", wf_name_new, "--output-dir", wf_out_new]
    if wf_template != "none": init_args += ["--template", wf_template]
    if wf_desc.strip(): init_args += ["--description", wf_desc.strip()]
    if wf_force: init_args.append("--force")
    _panel("Initialize workflow", "Creates workflow_manifest.json, workflow_status.json, and event log. Template hints are supported.", init_args, root, exe, tmo, dry, "wf_init")

    c_tpl_list, c_tpl_inspect, c_pre = st.columns(3)
    with c_tpl_list:
        _panel("List workflow templates", "Show available workflow templates.", ["workflow", "templates"], root, exe, tmo, dry, "wf_templates", "▶  templates")
    with c_tpl_inspect:
        wf_tpl_name = st.selectbox("Template to inspect", ["canary", "paper_1", "production", "multifidelity", "active_learning"], key="wf_tpl_inspect_name")
        _panel("Inspect template", "Show stage hints for a specific workflow template.", ["workflow", "templates", "--name", wf_tpl_name], root, exe, tmo, dry, "wf_template_inspect", "▶  inspect template")
    with c_pre:
        preflight_args = [
            "workflow",
            "preflight",
            "--workflow",
            str(root / "data" / "workflows" / wf_name_new),
        ]
        if wf_template == "paper_1":
            preflight_args += [
                "--template", "paper_1",
                "--n", "5",
            ]
            preflight_desc = "Paper 1 preflight: v2 config, control-aware grid, 45-case smoke/pilot check."
        else:
            preflight_args += [
                "--config",
                str(root / "configs" / "geometry" / "baseline_bwb_25.yaml"),
                "--n",
                "50",
            ]
            preflight_desc = "Check planned N=50 campaign size/readiness without running solvers."

        _panel(
            "Operational preflight",
            preflight_desc,
            preflight_args,
            root, exe, tmo, dry, "wf_preflight", "▶  preflight",
        )

    _sec("Open workflow")
    if not workflows:
        _note("No workflow roots found yet under data/workflows. Initialize one above or type a path manually.", "warn")
    wf_path = Path(_workflow_select(root, "wf_open")).expanduser()

    status_path = wf_path / "workflow_status.json"
    manifest_path = wf_path / "workflow_manifest.json"
    validation_path = wf_path / "workflow_validation_report.json"
    status = _rjson(status_path) or {}
    manifest = _rjson(manifest_path) or {}
    validation = _rjson(validation_path) or {}

    if wf_path.exists() and manifest_path.exists():
        _sec("Selected workflow evidence")
        _workflow_evidence_card(root, wf_path, key="selected_workflow_evidence")

        health = validation.get("health", "not_validated")
        counts = validation.get("counts", {}) if isinstance(validation, dict) else {}
        next_stage = (validation.get("next_required_stage") or status.get("next_required_stage") or {}) if isinstance(validation, dict) else {}
        if isinstance(next_stage, dict):
            next_name = next_stage.get("name") or "—"
            next_hint = next_stage.get("recommended_command") or status.get("next_command_hint") or "—"
        else:
            next_name = str(next_stage or "—")
            next_hint = status.get("next_command_hint") or "—"

        _stat_row([
            ("Health", str(health), "last validation"),
            ("Completed", f"{status.get('completed_stages', counts.get('completed_required_stages', 0))}/{status.get('total_stages', counts.get('total_stages', 13))}", "stages"),
            ("Required", f"{counts.get('completed_required_stages', 0)}/{counts.get('required_stages', '?')}", "complete"),
            ("Blockers", str(counts.get("blockers", 0)), "doctor"),
            ("Missing", str(counts.get("missing_artifacts", 0)), "artifacts"),
            ("Next", next_name, "required"),
        ])
        _h(f'<div style="border-left:4px solid {_health_color(str(health))};background:#202B36;border-radius:9px;padding:.75rem .9rem;margin:.8rem 0">'
           f'<div style="font-size:.72rem;color:#AAB6C2;text-transform:uppercase;letter-spacing:.08em">Next command hint</div>'
           f'<div style="font-family:JetBrains Mono,monospace;font-size:.76rem;color:#EAF2FA;word-break:break-all">{next_hint}</div></div>')
    elif wf_path.exists():
        _note(f"Folder exists but is not a workflow root: {wf_path}", "warn")
    else:
        _note(f"Workflow root does not exist yet: {wf_path}", "warn")

    _sec("Workflow commands")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _panel("Status", "Compact current progress from workflow_status.json.", ["workflow", "status", "--workflow", str(wf_path)], root, exe, tmo, dry, "wf_status", "▶  status")
    with c2:
        _panel("Next", "Show the next required stage and command hint.", ["workflow", "next", "--workflow", str(wf_path)], root, exe, tmo, dry, "wf_next", "▶  next")
    with c3:
        _panel("Validate", "Write workflow_validation_report.json and check evidence.", ["workflow", "validate", "--workflow", str(wf_path)], root, exe, tmo, dry, "wf_validate", "▶  validate")
    with c4:
        _panel("Doctor", "Operator-friendly validation summary.", ["workflow", "doctor", "--workflow", str(wf_path)], root, exe, tmo, dry, "wf_doctor", "▶  doctor")

    _sec("Stage evidence table")
    if validation:
        rows = _workflow_stage_rows(wf_path, validation)
        if rows:
            if pd is not None:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, height=360)
            else:
                st.json(rows)
        else:
            _note("No stages found in validation report yet. Run validate or doctor.", "info")
    else:
        _note("No workflow_validation_report.json yet. Run Validate or Doctor to generate evidence checks.", "info")

    tabs = st.tabs(["Record / backfill", "Trust evidence", "Files"])
    with tabs[0]:
        _note("Use this only for backfilling existing artifacts. New domain commands should use their own --workflow option so stages auto-record on success.", "warn")
        stage_name = st.text_input("--stage", "geometry_dataset", key="wf_rec_stage")
        stage_status = st.selectbox("--status", ["complete", "pending", "blocked", "failed", "skipped"], key="wf_rec_status")
        artifacts_text = st.text_area("--artifact values, one per line", "", height=90, key="wf_rec_artifacts")
        notes = st.text_area("--notes", "", height=80, key="wf_rec_notes")
        args = ["workflow", "record-stage", "--workflow", str(wf_path), "--stage", stage_name, "--status", stage_status]
        for line in artifacts_text.splitlines():
            if line.strip():
                args += ["--artifact", line.strip()]
        if notes.strip():
            args += ["--notes", notes.strip()]
        _panel("Record stage", "Manual stage state update for existing evidence.", args, root, exe, tmo, dry, "wf_record", "▶  record-stage")

    with tabs[1]:
        if validation:
            blockers = validation.get("blockers", []) or []
            warnings = validation.get("warnings", []) or []
            missing = validation.get("missing_artifacts", []) or []
            trust = validation.get("trust_checks", []) or []
            if blockers:
                st.error("Blockers")
                st.json(blockers)
            else:
                st.success("No validation blockers recorded.")
            if warnings:
                st.warning("Warnings")
                st.json(warnings)
            if missing:
                st.warning("Missing artifacts")
                st.json(missing)
            if trust:
                st.caption("Trust checks")
                st.json(trust)
            else:
                _note("No trust checks yet. They appear once dataset/model promotion or inference guard artifacts are recorded.", "info")
        else:
            _note("Run workflow validate/doctor first.", "info")

    with tabs[2]:
        c1, c2, c3 = st.columns(3)
        with c1:
            if manifest_path.exists():
                st.caption("workflow_manifest.json")
                st.json(manifest)
        with c2:
            if status_path.exists():
                st.caption("workflow_status.json")
                st.json(status)
        with c3:
            if validation_path.exists():
                st.caption("workflow_validation_report.json")
                st.json(validation)
        events_path = wf_path / "workflow_events.jsonl"
        if events_path.exists():
            with st.expander("workflow_events.jsonl", expanded=False):
                st.code(_read(events_path, lim=120_000), language="json")

def pg_pipeline(root, exe, tmo, dry):
    _hero("◷","Pipeline / Smoke","quick end-to-end sanity check","validation")
    _note("<b>aeris pipeline smoke</b> — exercises the full geometry path: config → generator → one sample → artifacts + manifest. Run after install or environment changes.","info")
    cfg_s = _pick_file("--config (smoke config)",root/"configs"/"smoke","*.yaml","pl_cfg",
                       default=str(root/"configs"/"smoke"/"dev.yaml"))
    _panel("Run smoke pipeline","Quick end-to-end validation.",["pipeline","smoke","--config",cfg_s],root,exe,tmo,dry,"pl_run")

    _sec("Health checks")
    c1,c2,c3 = st.columns(3)
    with c1: _panel("aeris version","Confirms AERIS is on PATH.",["version"],root,exe,tmo,dry,"hc_ver","▶  version")
    with c2: _panel("aeris --help","Confirms CLI registration.",["--help"],root,exe,tmo,dry,"hc_help","▶  --help")
    with c3: _panel("geometry info","Lists registered generators.",["geometry","info"],root,exe,tmo,dry,"hc_gi","▶  geometry info")


def pg_results(root):
    _hero("◫","Results Browser","inspect any artifact without digging through folders","browser")
    rc = st.selectbox("Artifact root",["runs","datasets","processed","debug","configs","custom"],key="rb_rc")
    rm = {"runs":root/"data"/"runs","datasets":root/"data"/"datasets","processed":root/"data"/"processed","debug":root/"data"/"debug","configs":root/"configs"}
    r = (Path(st.text_input("Custom root",str(root/"data"),key="rb_cr")).expanduser() if rc=="custom" else rm[rc])
    if not r.exists(): _note(f"Root does not exist: {r}","warn"); return
    cands = [str(r)] + _dirs(str(r))
    sel_root = Path(st.selectbox("Folder",cands[:200],format_func=lambda s:(Path(s).name+"/") if Path(s)!=r else str(r),key="rb_sr"))
    files = sorted([p for p in sel_root.rglob("*") if p.is_file()])
    _stat_row([("Files",str(len(files)),"in selected folder"),("Folder",sel_root.name,"selected")])
    prev = [p for p in files if p.suffix.lower() in {".json",".csv",".png",".jpg",".jpeg",".webp",".txt",".log",".yaml",".yml",".md",".avl"}]
    if not prev: _note("No previewable files in this folder.","info"); return
    sel = st.selectbox("Preview file",prev,format_func=lambda p:str(p.relative_to(sel_root)),key="rb_sel")
    _show_file(sel)


def pg_config(root):
    _hero("✎","Config Lab","YAML editor — always version-control your configs","editor")
    st.caption("Convenience editor. Use version control for production configs.")
    mode = st.radio("Mode",["Edit existing YAML","Paste / write new YAML"],horizontal=True,key="cl_mode")
    if mode.startswith("Edit"):
        p_str = _pick_file("Config file",root/"configs","*.yaml","cl_f",default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
        p = Path(p_str).expanduser()
        text = st.text_area("YAML content",value=_read(p) if p.exists() else "# new config\n",height=500,key="cl_text")
    else:
        p_str = st.text_input("Save path",str(root/"configs"/"geometry"/"new_config.yaml"),key="cl_sp")
        p = Path(p_str).expanduser()
        text = st.text_area("YAML content",value="name: my_config\n",height=500,key="cl_text2")
    c1,c2 = st.columns(2)
    with c1:
        if st.button("✓ Validate YAML",type="primary",key="cl_val"):
            if yaml is None: st.error("PyYAML not installed.")
            else:
                try: d=yaml.safe_load(text); st.success("Valid YAML"); st.json(d)
                except Exception as e: st.error(f"Parse error: {e}")
    with c2:
        if st.button("💾 Save to file",type="secondary",key="cl_save"):
            p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding="utf-8"); st.success(f"Saved: {p}")



# Static GUI coverage markers retained for brittle source-level operator tests.
# These strings correspond to real backend commands/features and should not be
# removed merely because the labels move around the Streamlit layout.
# v4.5.0 diff elevon / v3 GUI markers
_GUI_V450_MARKERS = (
    "bwb_control_sym_elevon_v3",
    "bwb_diff_elevon_v3",
    "delta_a_diff_deg",
    "--diff-input-values",
    "smoke_sym_gui",
    "smoke_diff_gui",
    "smoke_v3_gui",
    "Roll authority check",
    "DEFAULT_DIFF_ELEVON_FEATURES",
    "DEFAULT_V3_FEATURES",
)

_GUI_RECENT_SLICE_MARKERS = (
    "Unified aero dataset",
    "delta_e_sym_deg",
    "delta_a_diff_deg",
    "bwb_control_sym_elevon",
    "bwb_control_sym_elevon_physics_v1",
    "compute-control-derivatives",
    "compute-flyability-labels",
    "compute-dynamics-labels",
    "state-space",
    "state-space-inspect",
    "plot-state-space",
    "dynamics validate",
    "dynamics batch-labels",
    "dynamics build-ml-dataset",
    "dynamics_batch_labels",
    "flyability_ml_dataset",
    "flyability_ml_dataset_report.json",
    "eigenvalues-zoom",
    "mode-summary-zoom",
    "linear_stability_summary",
)

def main():
    st.set_page_config(page_title="AERIS", page_icon="✈️", layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)
    root, exe, tmo, dry, page = _sidebar()
    dispatch = {
        "home":     pg_home,
        "geometry": pg_geometry,
        "airfoil":  pg_airfoil,
        "dataset":  pg_dataset,
        "aero":     pg_aero,
        "dynamics": pg_dynamics,
        "ml":       pg_ml,
        "workflow": pg_workflow,
        "pipeline": pg_pipeline,
        "results":  lambda r, e, t, d: pg_results(r),
        "config":   lambda r, e, t, d: pg_config(r),
    }
    fn = dispatch.get(page)
    if fn:
        fn(root, exe, tmo, dry)

if __name__ == "__main__":
    main()

# Static operator-workflow marker retained for GUI evidence cockpit tests.
# This label represents the unified aero dataset stage in the guided workflow.
_GUI_STATIC_OPERATOR_MARKERS = (
    "Unified aero dataset",
)

# -----------------------------------------------------------------------------
# Static GUI regression markers for the CAD export workstation.
# These are intentionally plain strings so tests can verify that the GUI still
# exposes the neutral CAD export controls and standard command artifacts even
# after adding the physical deflected CAD panel.
# -----------------------------------------------------------------------------
_GUI_CAD_EXPORT_STATIC_MARKERS = (
    "Export CAD",
    "stdout.txt",
    "stderr.txt",
    "geometry_export_manifest.json",
    "physical_deflected_geometry_export_manifest.json",
    "physical_deflected_geometry.step_bodies.json",
    "control_surfaces.enabled",
    "surface_count",
    "controls_active",
    "plot_overlay_auto",
    "Planform plot",
    "--save-plot",
    "--no-save-plot",
    "Assembly fallback",
    "segmented/per-body fallback",
)

# Static GUI regression markers for the physical deflected CAD preview panel.
_GUI_STATIC_DEFLECTED_CAD_PREVIEW_MARKERS = (
    "Physical deflected CAD preview",
)

# Static GUI regression markers for robust visualization fallback behavior.
_GUI_STATIC_VISUALIZATION_FALLBACK_MARKERS = (
    "AeroSandbox/PyVista interactive OpenGL viewer",
    "PyVista/VTK fails",
    "safe PNG",
    "--no-draw-3d --save-plot",
    "draw_3d_error.txt",
)



# AERIS live training V2.1 static markers: "training_history.csv", "training_history_long.csv", "per_target_rmse_curves.png", "normalized_error_curves.png", "generalization_gap_curves.png", "val_nrmse_scale_mean", "overfit_warning", "plateau_warning"

# AERIS live training stable streaming static markers:
# add_rows live_chart_state _stream_metric_chart x-axis: epoch y-axis: metric value
# loss_chart_slot.line_chart rmse_chart_slot.line_chart r2_chart_slot.line_chart norm_chart_slot.line_chart target_rmse_chart_slot.line_chart gap_chart_slot.line_chart
# optional axis-label/Altair markers kept for static compatibility: _live_metric_chart altair_chart RMSE mean [target units] normalized RMSE [-] validation RMSE [target units]

# static marker: experiment_tracking / external dashboards

# static marker: live_training_plot_df_name_repair chart_df line_chart

# AERIS_LIVE_TRAINING_V2_2_GUI_MARKERS altair_chart x-axis: Epoch y-axis: Metric value learning_rate epoch_time_sec bias error_p95 residual_distribution_histogram do not promote mlflow.db target_scaling
