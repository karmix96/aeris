"""
AERIS GUI v4.0.0 — Aerospace + AI Design Platform
Every CLI option verified directly against codebase.txt source. Zero invalid flags.

Run: aeris gui run  OR  streamlit run src/aeris/gui/app.py

ground-truth: geometry generate only accepts --config (no --name, no --seed, no --save-plot)
"""
from __future__ import annotations

import json, os, re, shlex, shutil, subprocess, textwrap, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

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
APP_VERSION       = "4.0.0"
DEFAULT_FEATURES  = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg"
DEFAULT_TARGETS   = "cl,cd,cm"
DEFAULT_PAIR_KEYS = "geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg"

MODEL_TYPES = [
    "linear_regression", "ridge", "elastic_net",
    "random_forest", "extra_trees", "gradient_boosting",
    "hist_gradient_boosting", "neural_mlp", "neural_mlp_ensemble",
]
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
}
SAMPLERS = ["lhs_v1", "random_v1"]
SAMPLER_INFO = {
    "lhs_v1":    "Latin Hypercube — best design-space coverage ✓ recommended",
    "random_v1": "Uniform Random — simple, may cluster",
}
QC_PRESETS = ["off", "debug", "production", "promotion_strict"]
QC_PRESET_INFO = {
    "off":              "Off — skip all QC (smoke/debug only, lets bad data pass)",
    "debug":            "Debug — run QC, don't block on failures (visibility without gate)",
    "production":       "Production — run QC + block on failures ✓ recommended",
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
QC_PROFILES  = ["basic", "strict"]

PAGES = [
    ("home",     "⌂",  "Home"),
    ("geometry", "△",  "Geometry"),
    ("dataset",  "▣",  "Dataset Factory"),
    ("aero",     "⊿",  "Aero Analysis"),
    ("dynamics", "◎",  "Dynamics"),
    ("ml",       "◈",  "ML Studio"),
    ("pipeline", "◷",  "Pipeline / Smoke"),
    ("results",  "◫",  "Results Browser"),
    ("config",   "✎",  "Config Lab"),
]

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

@st.cache_data(ttl=30)
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
            <div style="width:32px;height:32px;background:linear-gradient(135deg,#2F80ED,#3B82F6);
            border-radius:8px;display:flex;align-items:center;justify-content:center;
            font-weight:800;font-size:.95rem;color:#fff">A</div>
            <div>
              <div style="font-size:1.02rem;font-weight:700;color:#FFFFFF;letter-spacing:.01em">AERIS</div>
              <div style="font-size:.64rem;color:#B7C6D7;letter-spacing:.14em;
              font-family:JetBrains Mono,monospace">MISSION CONTROL v{APP_VERSION}</div>
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
    runs_root = root / "data" / "runs"
    ds_root   = root / "data" / "datasets"
    ml_root   = root / "data" / "processed" / "ml_runs"
    cfg_files = _files(str(root / "configs" / "geometry"), "*.yaml")
    geo_runs  = _dirs(str(runs_root))
    all_ds    = _dirs(str(ds_root))
    promoted  = [d for d in all_ds if (Path(d)/"promotion_manifest.json").exists()]
    aero_ds   = [d for d in all_ds if (Path(d)/"aero_dataset.csv").exists()]
    ml_runs   = [d for d in _dirs(str(ml_root)) if (Path(d)/"metrics.json").exists()]
    promo_mdl = [d for d in _dirs(str(ml_root)) if (Path(d)/"model_promotion_manifest.json").exists()]

    if promo_mdl:       step = 6
    elif ml_runs:       step = 5
    elif promoted:      step = 4
    elif aero_ds:       step = 3
    elif geo_runs:      step = 2
    elif cfg_files:     step = 1
    else:               step = 0

    _h("""<div style="margin-bottom:1.4rem"><div style="display:flex;align-items:center;gap:12px;margin-bottom:.2rem">
      <div style="width:40px;height:40px;background:#2F80ED12;border:1px solid #2F80ED25;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:1.2rem">⌂</div>
      <div><h1 style="margin:0!important">AERIS Mission Control</h1>
      <p style="margin:0!important;font-size:.78rem!important;color:#AAB6C2!important;font-family:JetBrains Mono,monospace">BWB aerodynamic surrogate pipeline · ground-truth CLI wiring</p></div>
    </div></div>""")

    steps_data = [
        (1,"Config",   f"{len(cfg_files)} file(s)", bool(cfg_files)),
        (2,"Geometry", f"{len(geo_runs)} run(s)",   bool(geo_runs)),
        (3,"Aero",     f"{len(aero_ds)} dataset(s)",bool(aero_ds)),
        (4,"Promoted", f"{len(promoted)} promoted",  bool(promoted)),
        (5,"ML model", f"{len(ml_runs)} run(s)",     bool(ml_runs)),
        (6,"Deployed", f"{len(promo_mdl)} model(s)", bool(promo_mdl)),
    ]
    parts = []
    for num, label, detail, done in steps_data:
        is_next = (num == step+1) and not done
        if done:      bg,bd,col,icon = "#22C55E10","#22C55E50","#22C55E","✓"
        elif is_next: bg,bd,col,icon = "#3B82F610","#3B82F650","#3B82F6","→"
        else:         bg,bd,col,icon = "#202B36","#405166","#8EA0B3",str(num)
        conn = '<div style="flex:1;height:1px;background:#2A3848;margin-top:-12px"></div>' if num < 6 else ""
        parts.append(f'''<div style="display:flex;flex-direction:column;align-items:center;flex:1">
          <div style="width:24px;height:24px;border-radius:50%;background:{bg};border:1.5px solid {bd};display:flex;align-items:center;justify-content:center;font-size:.68rem;font-weight:600;color:{col};position:relative;z-index:1;font-family:JetBrains Mono,monospace">{icon}</div>
          <div style="font-size:.66rem;color:{"#7F8B98" if not (done or is_next) else col};margin-top:4px;text-align:center">{label}</div>
          <div style="font-size:.6rem;color:#7F8B98;text-align:center;margin-top:1px">{detail if done else ""}</div>
        </div>{conn}''')
    _h(f'<div style="background:#202B36;border:1px solid #334252;border-radius:10px;padding:1rem 1.3rem;margin-bottom:1.4rem"><div style="display:flex;align-items:flex-start">{"".join(parts)}</div></div>')

    _sec("Quick actions")
    c1, c2, c3 = st.columns(3)
    with c1: _panel("aeris version","Confirms AERIS is on PATH.",["version"],root,exe,tmo,dry,"hv_ver","▶  aeris version")
    with c2: _panel("geometry info","Lists registered generators.",["geometry","info"],root,exe,tmo,dry,"hv_ginfo","▶  geometry info")
    with c3: _panel("aeris --help","Confirms CLI registration.",["--help"],root,exe,tmo,dry,"hv_help","▶  aeris --help")

    _sec("Inventory")
    # Also check for the training config (not just any config)
    has_training_cfg = (root/"configs"/"geometry"/"bwb_training_v1.yaml").exists()
    _stat_row([
        ("Config files", str(len(cfg_files)), "configs/geometry/*.yaml"),
        ("Training config", "✓" if has_training_cfg else "missing", "bwb_training_v1.yaml"),
        ("Aero datasets", str(len(aero_ds)), "data/datasets/"),
        ("ML runs", str(len(ml_runs)), "data/processed/ml_runs/"),
    ])


def pg_geometry(root, exe, tmo, dry):
    _hero("△","Geometry","bwb_segmented_v1 · 17 design variables","generator")
    tab_gen, tab_vis, tab_info = st.tabs(["  ① Generate  ","  ② Visualize  ","  ③ System info  "])

    # ── GENERATE ────────────────────────────────────────────────────────────
    with tab_gen:
        _note(
            "<b>aeris geometry generate</b> — accepts <b>only --config/-c</b>. "
            "Nothing else. Plot-saving and AeroSandbox are set in the YAML "
            "<code>geometry.outputs.save_plot</code> / <code>build_aerosandbox</code>. "
            "The run folder is always <code>data/runs/&lt;timestamp&gt;_geometry_&lt;config_stem&gt;/</code>. "
            "Custom naming requires a codebase patch (add <code>--name</code> to "
            "<code>src/aeris/pipeline/geometry_run.py</code> and "
            "<code>src/aeris/commands/geometry.py</code>).",
            "info",
        )
        _note(
            "<b>For training campaigns:</b> use <code>bwb_training_v1.yaml</code> (real design-space bounds). "
            "<code>baseline_bwb_25.yaml</code> is nearly fixed — use only for smoke tests.",
            "info",
        )
        mode = st.radio("Config source",["Use existing YAML file","Build config interactively"],horizontal=True,key="gm_mode")
        if mode.startswith("Use existing"):
            _sec("YAML file")
            config = _pick_file("Config file",root/"configs"/"geometry","*.yaml","g_cfg",
                                default=str(root/"configs"/"geometry"/"bwb_training_v1.yaml"))
        else:
            _sec("Interactive builder")
            yaml_str = _yaml_geometry_builder("gb")
            with st.expander("Preview YAML"): st.code(yaml_str, language="yaml")
            sp = st.text_input("Save YAML to path",str(root/"configs"/"geometry"/"gui_built.yaml"),key="gb_sp")
            if st.button("💾 Save YAML",key="gb_save",type="secondary"):
                p=Path(sp); p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(yaml_str,encoding="utf-8"); st.success(f"Saved: {p}")
            config = sp

        # Only valid arg: --config
        args = ["geometry","generate","--config",config]
        _panel("Generate one geometry",
               "Creates one deterministic BWB geometry. Output → data/runs/<timestamp>_geometry_<stem>/",
               args, root, exe, tmo, dry, "g_run")

        # Show recent geometry runs
        geo_runs = [r for r in _dirs(str(root/"data"/"runs")) if "geometry" in Path(r).name]
        if geo_runs:
            _sec("Recent geometry runs")
            for r in geo_runs[:5]:
                p = Path(r)
                m = _rjson(p/"manifest.json")
                status = (m or {}).get("status","?")
                col = "#22C55E" if status=="success" else "#EF4444" if status=="failed" else "#F59E0B"
                _h(f'<div style="background:#202B36;border:1px solid #334252;border-radius:8px;padding:.6rem 1rem;margin-bottom:.35rem;display:flex;align-items:center;gap:10px">'
                   f'<div style="width:8px;height:8px;border-radius:50%;background:{col}"></div>'
                   f'<div style="flex:1;font-size:.79rem;color:#D6DEE8;font-family:JetBrains Mono,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{p.name}</div>'
                   f'<div style="font-size:.7rem;color:#8EA0B3">{status}</div></div>')

    # ── VISUALIZE ────────────────────────────────────────────────────────────
    with tab_vis:
        _note(
            "<b>aeris geometry visualize --config &lt;file&gt;</b> — "
            "samples ONE geometry from the config using the seed, then visualizes it. "
            "It does NOT replay an existing run — it re-generates from config.<br>"
            "<b>2D plot</b> (<code>--save-plot</code>): saves a top-view planform PNG to the output folder. "
            "View it later in Results Browser — no display needed.<br>"
            "<b>3D viewer</b> (<code>--draw-3d</code>): opens an AeroSandbox OpenGL window on your "
            "<b>local desktop</b>. Disable on headless servers / SSH / remote environments. "
            "Requires <code>build_aerosandbox: true</code> in config outputs.<br>"
            "<b>--output-dir</b>: leave blank for auto debug folder; "
            "pick an existing run folder to co-locate visualization artifacts.",
            "info",
        )
        _sec("Config")
        vcfg = _pick_file("Geometry config",root/"configs"/"geometry","*.yaml","gv_cfg",
                          default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))

        _sec("Generation")
        c1, c2 = st.columns(2)
        seed_ov = c1.text_input("--seed (optional, int)",value="",key="gv_seed",
                                help="Seed for the geometry sampler. Leave blank = use config seed. "
                                     "Match the seed from a generate run to reproduce that exact shape.")
        build_asb = c2.selectbox("--build-aerosandbox override",
                                  ["(from config)","build (--build-aerosandbox)","skip (--no-build-aerosandbox)"],
                                  key="gv_ba",
                                  help="Override the YAML build_aerosandbox setting. "
                                       "Must be True/build to use --draw-3d.")

        _sec("Visualization")
        c3, c4, c5 = st.columns(3)
        save_pl = c3.selectbox("--save-plot override",
                                ["(from config)","save (--save-plot)","skip (--no-save-plot)"],
                                key="gv_sp",
                                help="Save the 2D planform PNG. Viewable in Results Browser later.")
        draw3d = c4.checkbox("--draw-3d (open 3D viewer)",value=False,key="gv_3d",
                             help="Opens interactive AeroSandbox OpenGL window. "
                                  "DISABLE on headless/remote servers. Needs build-aerosandbox=true.")
        show_pl = c5.checkbox("--show-plot (pop-up 2D window)",value=False,key="gv_sh",
                              help="Opens matplotlib window. Usually False on servers.")

        _sec("Output directory (--output-dir)")
        runs_dirs = _dirs(str(root/"data"/"runs"))
        od_opts = ["(auto — data/debug/visualization_runs/<timestamp>_geometry_<name>/)"] + runs_dirs
        od_sel = st.selectbox("Output dir",od_opts,index=0,key="gv_od_sel",
                              format_func=lambda s: "auto debug folder" if s.startswith("(auto") else Path(s).name,
                              help="Leave on auto for a fresh debug folder, or pick an existing run to save alongside it.")
        od = "" if od_sel.startswith("(auto") else od_sel
        od = st.text_input("Manual --output-dir override",value=od,key="gv_od_m",
                           help="Absolute path. Leave blank for automatic debug subfolder.")

        args = ["geometry","visualize","--config",vcfg]
        _flag(args,"--seed",seed_ov)
        _flag(args,"--output-dir",od)
        if "save (--save-plot)" in save_pl:   args.append("--save-plot")
        elif "skip (--no-save-plot)" in save_pl: args.append("--no-save-plot")
        if "build (" in build_asb:   args.append("--build-aerosandbox")
        elif "skip (" in build_asb:  args.append("--no-build-aerosandbox")
        _bflag(args,"--draw-3d","--no-draw-3d",draw3d)
        _bflag(args,"--show-plot","--no-show-plot",show_pl)
        _panel("Visualize geometry",
               "Generates and visualizes one geometry from config. 2D PNG saved to output dir. 3D = desktop OpenGL.",
               args, root, exe, tmo, dry, "gv_run")

    with tab_info:
        _note("<code>aeris geometry info</code> — lists registered generator IDs and current status.", "info")
        _panel("Geometry system info","Lists registered generators.",["geometry","info"],root,exe,tmo,dry,"gi_run")


def pg_dataset(root, exe, tmo, dry):
    _hero("▣","Dataset Factory","geometry → sweeps → qc → curate → promote","data pipeline")
    tabs = st.tabs(["  Unified Aero  ","  Geometry Only  ","  Inspect / QC  ","  Curate / Promote  ","  Training Data  ","  Smoke Check  "])

    # ── UNIFIED AERO DATASET ─────────────────────────────────────────────────
    with tabs[0]:
        _note(
            "<b>aeris dataset aero-generate</b> — the main production command. "
            "Geometry + full aero sweeps + QC in one pipeline. "
            "--alpha-values, --velocity-values, --altitude-values, --control-input-values are <b>required</b>.",
            "info",
        )
        mode = st.radio("Config source",["Use existing YAML file","Build config interactively"],horizontal=True,key="ds_mode2")
        if mode.startswith("Use existing"):
            config = _pick_file("Geometry config",root/"configs"/"geometry","*.yaml","ds_ac",
                                default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
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
        ctrl  = st.text_input("--control-input-values [deg]","-5,0,5",key="ds_ctrl",help="Elevon deflection. e.g. -10,-5,0,5,10")
        with st.expander("Angular rates (optional — leave 0 for standard datasets)"):
            c5,c6,c7 = st.columns(3)
            pv = c5.text_input("--p-values [rad/s]","0",key="ds_pv"); qv = c6.text_input("--q-values [rad/s]","0",key="ds_qv"); rv = c7.text_input("--r-values [rad/s]","0",key="ds_rv")
        est = int(n) * _est(alpha,beta,vel,alt,ctrl,pv,qv,rv)
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
            desc3 = "Runs geometry quality checks on all cases in the dataset."
        else:
            qp3 = st.selectbox("--profile",QC_PROFILES,key="diq_aqcp")
            args3 = ["dataset","aero-qc","--dataset",ds3,"--profile",qp3]
            desc3 = "Runs aero quality checks on aero_dataset.csv."
        _panel("Inspect / QC",desc3,args3,root,exe,tmo,dry,"diq_run")

    # ── CURATE / PROMOTE ──────────────────────────────────────────────────────
    with tabs[3]:
        _note("Curation filters bad rows. Promotion writes <code>promotion_manifest.json</code> — required gate before ML training.","info")
        ds4 = _pick_dir("Aero dataset root",root/"data"/"datasets","dcp_ds")
        task4 = st.selectbox("Task",["curate-aero","promote-aero","require-promoted-aero"],key="dcp_task")

        if task4 == "curate-aero":
            _note(
                "Curation rejects: incomplete groups, aero failures, nonfinite targets, failed control diagnostics. "
                "All four defaults are True. "
                "<b>After curating and promoting, run <code>aeris aero cm-sanity --dataset &lt;ds&gt;</code></b> "
                "(in the Aero page) to verify Cm sign convention before any ML training.",
                "info",
            )
            c1,c2 = st.columns(2)
            ri4 = c1.checkbox("--reject-incomplete-groups",True,key="dc_ri",help="Reject geometries whose sweep grid is incomplete")
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

    # ── SMOKE CHECK ───────────────────────────────────────────────────────────
    with tabs[5]:
        _note("<b>aeris pipeline smoke</b> — minimal end-to-end: config → generator → one sample → manifest. Run after install/env changes.","info")
        cfg_sm = _pick_file("Smoke config",root/"configs"/"smoke","*.yaml","sm_cfg",
                            default=str(root/"configs"/"smoke"/"dev.yaml"))
        _panel("Run smoke pipeline","Quick end-to-end sanity check.",["pipeline","smoke","--config",cfg_sm],root,exe,tmo,dry,"sm_run")


def pg_aero(root, exe, tmo, dry):
    _hero("⊿","Aero Analysis","aerosandbox_avl · single run or parametric sweep","aero")

    def _src_args(key):
        """Returns source args. Exactly one of --config, --run-dir, --dataset must be provided."""
        src = st.selectbox("Geometry source",
                           ["Fresh config (--config)","Existing run (--run-dir)","Dataset geometry (--dataset)"],
                           key=f"{key}_src")
        args = []
        if "config" in src:
            cfg = _pick_file("Config",root/"configs"/"geometry","*.yaml",f"{key}_cfg",
                             default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
            args += ["--config",cfg]
        elif "run" in src:
            rd = _pick_dir("Geometry run dir",root/"data"/"runs",f"{key}_rd")
            gid = st.text_input("--generator-id","bwb_segmented_v1",key=f"{key}_gid",
                                help="Required for --run-dir mode. Must match the generator used.")
            args += ["--run-dir",rd,"--generator-id",gid]
        else:
            ds = _pick_dir("Dataset root",root/"data"/"datasets",f"{key}_ds")
            geom = st.text_input("--geometry-id","geom_00001",key=f"{key}_geomid")
            gid  = st.text_input("--generator-id","bwb_segmented_v1",key=f"{key}_gid2")
            args += ["--dataset",ds,"--geometry-id",geom,"--generator-id",gid]
        return args

    def _solver_args(key):
        avl  = st.text_input("--avl-command","avl",key=f"{key}_avl",help="'avl' if on PATH, or full path")
        c1,c2,c3,c4 = st.columns(4)
        sp   = c1.number_input("--spanwise-resolution",1,value=4,step=1,key=f"{key}_sp")
        cp   = c2.number_input("--chordwise-resolution",1,value=8,step=1,key=f"{key}_cp")
        ssp  = c3.selectbox("--spanwise-spacing",SPACING,key=f"{key}_ssp")
        csp  = c4.selectbox("--chordwise-spacing",SPACING,index=1,key=f"{key}_csp")
        tmo_ = st.number_input("--timeout-sec",min_value=5,value=180,step=5,key=f"{key}_tmo")
        with st.expander("Advanced output options"):
            c5,c6 = st.columns(2)
            ssf = c5.checkbox("--save-surface-forces",False,key=f"{key}_ssf",help="Write AVL surface force files")
            sef = c6.checkbox("--save-element-forces",False,key=f"{key}_sef",help="Write AVL element force files")
        out_n = st.text_input("--output-name (optional folder suffix)","",key=f"{key}_on",
                              help="Appended to run folder name for easy identification")
        args = ["--solver","aerosandbox_avl","--avl-command",avl,
                "--spanwise-resolution",str(int(sp)),"--chordwise-resolution",str(int(cp)),
                "--spanwise-spacing",ssp,"--chordwise-spacing",csp,
                "--timeout-sec",str(int(tmo_))]
        if ssf: args.append("--save-surface-forces")
        if sef: args.append("--save-element-forces")
        _flag(args,"--output-name",out_n)
        return args

    tab_single, tab_sweep, tab_inspect = st.tabs(["  Single run  ","  Sweep  ","  Inspect  "])

    with tab_single:
        src_a = _src_args("ar")
        _sec("Flight condition (--alpha is REQUIRED)")
        c1,c2,c3,c4 = st.columns(4)
        al = c1.number_input("--alpha [deg]",value=4.0,step=0.5,key="ar_al")
        be = c2.number_input("--beta [deg]",value=0.0,step=0.5,key="ar_be",help="Sideslip. Default 0.")
        ve = c3.number_input("--velocity [m/s]",value=28.0,step=1.0,key="ar_ve",help="Default 28 m/s")
        at = c4.number_input("--altitude [m]",value=1500.0,step=100.0,key="ar_at",help="Default 0 m")
        ctrl = st.slider("--control-input-deg [deg] (elevon)",-15.0,15.0,0.0,0.5,key="ar_ctrl",
                         help="Control-surface deflection. Positive = trailing edge down.")
        with st.expander("Angular rates & misc (optional)"):
            c5,c6,c7 = st.columns(3)
            pv = c5.number_input("--p [rad/s]",0.0,key="ar_p",help="Body roll rate. Default 0.")
            qv = c6.number_input("--q [rad/s]",0.0,key="ar_q",help="Body pitch rate. Default 0.")
            rv = c7.number_input("--r [rad/s]",0.0,key="ar_r",help="Body yaw rate. Default 0.")
            mach = st.text_input("--mach (optional Mach metadata)","",key="ar_mach",help="QC metadata only. Velocity+altitude remain authoritative.")
            seed_ar = st.number_input("--seed",min_value=0,value=0,step=1,key="ar_seed",help="Geometry seed for config mode. Default 0.")
        _sec("Solver settings")
        sol_a = _solver_args("ar")
        args_ar = ["aero","run"] + src_a + ["--alpha",str(al),"--beta",str(be),"--velocity",str(ve),"--altitude",str(at),"--control-input-deg",str(ctrl),"--p",str(pv),"--q",str(qv),"--r",str(rv),"--seed",str(int(seed_ar))] + sol_a
        _flag(args_ar,"--mach",mach)
        _panel("Single aero run","One geometry, one flight condition. Full AVL evaluation.",args_ar,root,exe,tmo,dry,"ar_run")

    with tab_sweep:
        src_s = _src_args("sw")
        _sec("Sweep definition (comma-separated values)")
        c1,c2 = st.columns(2)
        al2 = c1.text_input("--alpha-values [deg]","-2,0,2,4,6",key="sw_al",help="Comma-sep. If empty, uses base --alpha value.")
        be2 = c2.text_input("--beta-values [deg]","0",key="sw_be",help="Comma-sep. If empty, uses base --beta.")
        c3,c4 = st.columns(2)
        ve2 = c3.text_input("--velocity-values [m/s]","28",key="sw_ve",help="Comma-sep. If empty, uses base --velocity.")
        at2 = c4.text_input("--altitude-values [m]","1500",key="sw_at",help="Comma-sep. If empty, uses base --altitude.")
        ct2 = st.text_input("--control-input-values [deg]","-5,0,5",key="sw_ctrl",help="Comma-sep elevon sweep. Generates Cartesian product with other sweep values.")
        with st.expander("Angular rate sweeps (optional)"):
            c5,c6,c7 = st.columns(3)
            pv2=c5.text_input("--p-values [rad/s]","0",key="sw_p"); qv2=c6.text_input("--q-values [rad/s]","0",key="sw_q"); rv2=c7.text_input("--r-values [rad/s]","0",key="sw_r")
        est2 = _est(al2,be2,ve2,at2,ct2,pv2,qv2,rv2)
        _note(f"Estimated cases (Cartesian product): <b>{est2:,}</b>","info")
        max_c2 = st.text_input("--max-cases (optional safety cap)","",key="sw_mc",help="Leave blank for no cap.")
        seed_sw = st.number_input("--seed",min_value=0,value=0,step=1,key="sw_seed",help="Geometry seed for config mode.")
        _sec("Solver settings")
        sol_s = _solver_args("sw")
        args_sw = ["aero","sweep"] + src_s + ["--seed",str(int(seed_sw))]
        if al2.strip():  args_sw += ["--alpha-values",al2]
        if be2.strip():  args_sw += ["--beta-values",be2]
        if ve2.strip():  args_sw += ["--velocity-values",ve2]
        if at2.strip():  args_sw += ["--altitude-values",at2]
        if ct2.strip():  args_sw += ["--control-input-values",ct2]
        if pv2.strip() and pv2.strip()!="0": args_sw += ["--p-values",pv2]
        if qv2.strip() and qv2.strip()!="0": args_sw += ["--q-values",qv2]
        if rv2.strip() and rv2.strip()!="0": args_sw += ["--r-values",rv2]
        args_sw += sol_s
        _flag(args_sw,"--max-cases",max_c2)
        _panel("Aero sweep","Runs Cartesian product of flight conditions for one geometry.",args_sw,root,exe,tmo,dry,"sw_run")

    with tab_inspect:
        rd3 = _pick_dir("Run directory",root/"data"/"runs","ai_rd")
        it3 = st.selectbox("Inspect type",["Single aero run (aero inspect)","Sweep summary (aero sweep-inspect)","Sweep case (aero sweep-case-inspect)"],key="ai_it")
        if "Single" in it3:
            args3 = ["aero","inspect","--run-dir",rd3]
            desc3 = "Reads and prints a single aero run result."
        elif "summary" in it3:
            args3 = ["aero","sweep-inspect","--run-dir",rd3]
            desc3 = "Reads sweep summary manifest and prints all case results."
        else:
            c1,c2 = st.columns(2)
            cl3  = c1.text_input("--case-label (exact label)","",key="ai_cl",help="Exact sweep case label. Leave blank to use index.")
            ci3  = c2.number_input("--case-index",min_value=0,value=0,step=1,key="ai_ci",help="Used when --case-label is blank.")
            args3 = ["aero","sweep-case-inspect","--run-dir",rd3]
            if cl3.strip(): args3 += ["--case-label",cl3.strip()]
            else: args3 += ["--case-index",str(int(ci3))]
            desc3 = "Reads one specific case from a saved sweep."
        _panel("Inspect aero",desc3,args3,root,exe,tmo,dry,"ai_run")

    # ── Cm sanity ─────────────────────────────────────────────────────────────
    with st.expander("⚠ Cm sign sanity check — run before any ML training"):
        _note(
            "<b>aeris aero cm-sanity</b> — verifies that Cm decreases with alpha (Cma &lt; 0 = stable) "
            "within fixed-condition groups. Run on your promoted dataset before training any surrogate. "
            "A positive Cma means the aircraft is statically unstable in pitch — "
            "every ML model trained on Cm would be learning the wrong physics.",
            "warn",
        )
        cm_src = st.radio("Source",["--dataset (promoted aero dataset)","--csv (direct CSV path)"],
                          horizontal=True, key="cms_src")
        if "--dataset" in cm_src:
            cms_ds = _pick_dir("Promoted dataset",root/"data"/"datasets","cms_ds")
            args_cms = ["aero","cm-sanity","--dataset",cms_ds]
        else:
            cms_csv = st.text_input("--csv path","",key="cms_csv")
            args_cms = ["aero","cm-sanity","--csv",cms_csv]
        c1,c2 = st.columns(2)
        cms_od  = c1.text_input("--output-dir (optional)","",key="cms_od")
        cms_fov = c2.checkbox("--fail-on-violation",False,key="cms_fov")
        with st.expander("Advanced"):
            cms_ac  = st.text_input("--alpha-column","alpha_deg",key="cms_ac")
            cms_cc  = st.text_input("--cm-column","cm",key="cms_cc")
            cms_gc  = st.text_input("--group-columns","geometry_id,control_input_deg,velocity_mps,altitude_m",key="cms_gc")
            cms_mabs= st.number_input("--min-abs-cma-per-rad",value=1e-8,format="%.2e",key="cms_mabs")
        if cms_od.strip(): args_cms += ["--output-dir",cms_od]
        if cms_fov:        args_cms += ["--fail-on-violation"]
        args_cms += ["--alpha-column",cms_ac,"--cm-column",cms_cc,"--group-columns",cms_gc,"--min-abs-cma-per-rad",str(cms_mabs)]
        _panel("Cm sign sanity","Confirms Cma < 0 (stable). Run before ML training.",args_cms,root,exe,tmo,dry,"cms_run")


def pg_dynamics(root, exe, tmo, dry):
    _hero("◎","Dynamics","mass · CG · static margin · trim","dynamics")
    _note("Builds mass/CG/static-margin artifacts from an existing aero run. Current trim is first-order diagnostic only — not a full nonlinear trim solver.","info")
    act = st.radio("Workflow",["Build","CG sweep","Trim","Inspect","CG sweep inspect"],horizontal=True,key="dyn_act")
    rd = _pick_dir("Aero run directory",root/"data"/"runs","dyn_rd",
                   help_="Must contain an aero result. For Build/Trim/Inspect, must have a completed aero run.")

    if act == "Build":
        _note("--mass-config loads from YAML. CLI values override config values.","info")
        c1,c2 = st.columns(2)
        mc = c1.text_input("--mass-config (optional YAML path)","",key="dyn_mc",
                           help="Path to mass-properties YAML. Leave blank to use explicit CLI values only.")
        xp = c2.selectbox("Axis convention",["--x-positive-aft (default)","--x-positive-forward"],key="dyn_xp",
                          help="x positive aft = standard aviation convention.")
        with st.expander("Explicit mass values (override or supplement --mass-config)"):
            c3,c4 = st.columns(2)
            mkg  = c3.text_input("--mass-kg","",key="dyn_mkg",help="Aircraft mass [kg]")
            xcg  = c4.text_input("--x-cg-m","",key="dyn_xcg",help="CG x position [m]")
            c5,c6,c7 = st.columns(3)
            ycg  = c5.text_input("--y-cg-m","",key="dyn_ycg",help="CG y [m]. Default 0.")
            zcg  = c6.text_input("--z-cg-m","",key="dyn_zcg",help="CG z [m]. Default 0.")
            ixx  = c7.text_input("--ixx-kg-m2","",key="dyn_ixx",help="Roll inertia [kg·m²]")
            iyy  = c5.text_input("--iyy-kg-m2","",key="dyn_iyy",help="Pitch inertia [kg·m²]")
            izz  = c6.text_input("--izz-kg-m2","",key="dyn_izz",help="Yaw inertia [kg·m²]")
        args = ["dynamics","build","--run-dir",rd]
        if mc.strip(): args += ["--mass-config",mc.strip()]
        if "forward" in xp: args.append("--x-positive-forward")
        _flag(args,"--mass-kg",mkg); _flag(args,"--x-cg-m",xcg); _flag(args,"--y-cg-m",ycg); _flag(args,"--z-cg-m",zcg)
        _flag(args,"--ixx-kg-m2",ixx); _flag(args,"--iyy-kg-m2",iyy); _flag(args,"--izz-kg-m2",izz)
        desc = "Builds mass/CG/inertia/static-margin artifacts."

    elif act == "CG sweep":
        _note("Sweeps CG x-position and computes static margin at each point. Identifies stable CG range.","info")
        c1,c2 = st.columns(2)
        mc2  = c1.text_input("--mass-config (optional)","",key="dyn_mc2")
        mkg2 = c2.text_input("--mass-kg","",key="dyn_mkg2")
        c3,c4,c5 = st.columns(3)
        cgmn = c3.number_input("--cg-min-m (REQUIRED)",value=0.20,step=0.05,key="dyn_cgmn")
        cgmx = c4.number_input("--cg-max-m (REQUIRED)",value=0.70,step=0.05,key="dyn_cgmx")
        ns   = c5.number_input("--n (sweep points)",min_value=2,value=9,step=1,key="dyn_ns",help="Default 9")
        xp2  = st.selectbox("Axis convention",["--x-positive-aft","--x-positive-forward"],key="dyn_xp2")
        args = ["dynamics","cg-sweep","--run-dir",rd,"--cg-min-m",str(cgmn),"--cg-max-m",str(cgmx),"--n",str(int(ns))]
        if mc2.strip(): args += ["--mass-config",mc2.strip()]
        if mkg2.strip(): args += ["--mass-kg",mkg2.strip()]
        if "forward" in xp2: args.append("--x-positive-forward")
        desc = "Sweeps CG and computes static margin. Writes cg_sweep.json + cg_sweep.csv."

    elif act == "Trim":
        _note("First-order longitudinal trim estimate. Not a full nonlinear solver.","info")
        args = ["dynamics","trim","--run-dir",rd]
        desc = "Estimates trim alpha and Cm from saved aero result."

    elif act == "Inspect":
        args = ["dynamics","inspect","--run-dir",rd]
        desc = "Reads dynamics_foundation.json and prints mass/CG/static-margin results."

    else:  # CG sweep inspect
        args = ["dynamics","cg-sweep-inspect","--run-dir",rd]
        desc = "Reads cg_sweep.json and prints per-CG-point static margin results."

    _panel(f"Dynamics: {act}",desc,args,root,exe,tmo,dry,f"dyn_{act.replace(' ','_')}_task")


def _feature_selector(key, include_feature_set=True):
    """Returns (feature_args, label) for ML commands that accept --features / --feature-preset / --feature-set."""
    opts = ["--feature-preset (named preset)", "--features (raw comma-sep columns)"]
    if include_feature_set:
        opts.append("--feature-set (physics-engineered)")
    mode = st.radio("Feature input (exactly ONE required)",opts,horizontal=True,key=f"{key}_fmode")
    c1, c2 = st.columns(2)
    if "preset" in mode:
        fp = c1.selectbox("--feature-preset",["bwb_control","bwb_basic"],key=f"{key}_fp",
                          help="bwb_control: c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg | bwb_basic: same minus control_input_deg")
        tgt = c2.text_input("--targets",DEFAULT_TARGETS,key=f"{key}_tgt")
        return ["--feature-preset",fp,"--targets",tgt], f"preset:{fp}"
    elif "raw" in mode:
        feat = c1.text_input("--features",DEFAULT_FEATURES,key=f"{key}_feat")
        tgt  = c2.text_input("--targets",DEFAULT_TARGETS,key=f"{key}_tgt2")
        return ["--features",feat,"--targets",tgt], f"raw features"
    else:
        fs  = c1.text_input("--feature-set","bwb_control_raw",key=f"{key}_fs",
                             help="e.g. bwb_control_raw or bwb_control_physics_v1")
        tgt = c2.text_input("--targets",DEFAULT_TARGETS,key=f"{key}_tgt3")
        return ["--feature-set",fs,"--targets",tgt], f"set:{fs}"


def pg_ml(root, exe, tmo, dry):
    _hero("◈","ML Studio","train · tune · compare · promote · predict · active learning","surrogate")
    _note(
        "<b>Feature input rules (strictly enforced by the CLI):</b> use exactly ONE of "
        "<code>--features</code>, <code>--feature-preset</code>, or <code>--feature-set</code>. "
        "Mixing any two is a CLI error. "
        "Presets: <code>bwb_basic</code>, <code>bwb_control</code>. "
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
        "  ⑩ Multifidelity  ",
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
                "<b>aeris ml eda</b> — checks constant columns, outliers, coverage gaps. "
                "Generates <code>eda_report.json</code> + <code>eda_summary.md</code> + optional PNGs. "
                "<code>--plots</code> generates correlation heatmap, distributions, alpha/control coverage.<br>"
                "<b>Known gap:</b> <code>--feature-set</code> is not yet supported by EDA — use <code>--features</code> or <code>--feature-preset</code> here. "
                "Run <code>aeris ml feature-engineer</code> first to materialise physics features, then EDA the engineered CSV directly.",
                "warn",
            )
            ds_e = _pick_dir("Promoted dataset",root/"data"/"datasets","eda_ds")
            fa_e, _ = _feature_selector("eda", include_feature_set=False)
            c1,c2,c3 = st.columns(3)
            gc_e    = c1.text_input("--group-column","geometry_id",key="eda_gc")
            sig_e   = c2.number_input("--outlier-sigma",min_value=0.1,value=4.0,step=0.5,key="eda_sig",help="Sigma threshold for outlier scan. Default 4.0")
            od_e    = c3.text_input("--output-dir (blank = <dataset>/eda)","",key="eda_od")
            c4,c5 = st.columns(2)
            plots_e = c4.checkbox("--plots (generate PNGs)",False,key="eda_plots",help="Writes correlation_heatmap.png, feature_distributions.png, etc.")
            af_e    = c5.checkbox("--allow-forced",False,key="eda_af")
            args_e = ["ml","eda","--dataset",ds_e,"--group-column",gc_e,"--outlier-sigma",str(sig_e)] + fa_e
            if od_e.strip(): args_e += ["--output-dir",od_e]
            if plots_e: args_e.append("--plots")
            if af_e: args_e.append("--allow-forced")
            _panel("EDA","Generates eda_report.json + eda_summary.md + optional PNGs.",args_e,root,exe,tmo,dry,"eda_run")

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
        tg_t = st.tabs(["  Promote model  ","  Inspect model  ","  Require promoted  "])

        with tg_t[0]:
            mr4 = _pick_dir("ML run dir",root/"data"/"processed"/"ml_runs","tg_mr")
            _note(
                "All threshold args are optional — leave blank to skip that gate. "
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
            mr_ins = _pick_dir("ML run dir",root/"data"/"processed"/"ml_runs","ins_mr")
            _panel("Inspect model run","Prints model type, metrics, features, promotion status.",["ml","inspect-model","--model-run-dir",mr_ins],root,exe,tmo,dry,"ins_run")

        with tg_t[2]:
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

    # ── ⑩ Multifidelity ──────────────────────────────────────────────────────
    with tabs[9]:
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


def main():
    st.set_page_config(page_title="AERIS", page_icon="✈️", layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)
    root, exe, tmo, dry, page = _sidebar()
    dispatch = {
        "home":     pg_home,
        "geometry": pg_geometry,
        "dataset":  pg_dataset,
        "aero":     pg_aero,
        "dynamics": pg_dynamics,
        "ml":       pg_ml,
        "pipeline": pg_pipeline,
        "results":  lambda r, e, t, d: pg_results(r),
        "config":   lambda r, e, t, d: pg_config(r),
    }
    fn = dispatch.get(page)
    if fn:
        fn(root, exe, tmo, dry)

if __name__ == "__main__":
    main()