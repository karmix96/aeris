"""
AERIS — Aerospace + AI Design Platform  v2.1
Ground-up GUI. Mild dark theme. All options. Inline YAML builder. No CLI commands exposed. Fast.

Run:  aeris gui run   OR   python -m streamlit run src/aeris/gui/app.py
"""
from __future__ import annotations

import json, os, shlex, shutil, subprocess, time, textwrap
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

# ── constants ─────────────────────────────────────────────────────────────────
APP_VERSION      = "2.3.0"
DEFAULT_FEATURES = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg"
DEFAULT_TARGETS  = "cl,cd,cm"
DEFAULT_PAIR_KEYS= "geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg"
MODEL_TYPES      = ["linear_regression","ridge","elastic_net","random_forest",
                    "extra_trees","gradient_boosting","hist_gradient_boosting",
                    "neural_mlp","neural_mlp_ensemble"]
MODEL_LABELS     = {
    "linear_regression": "Linear Regression — fast baseline, interpretable coefficients",
    "ridge": "Ridge — L2 regularized linear, good for correlated features",
    "elastic_net": "Elastic Net — L1+L2 regularized, feature selection",
    "random_forest": "Random Forest — robust ensemble, low tuning burden",
    "extra_trees": "Extra Trees — faster than RF, similar accuracy",
    "gradient_boosting": "Gradient Boosting — powerful, needs tuning",
    "hist_gradient_boosting": "Hist Gradient Boosting — fastest tree method, best accuracy",
    "neural_mlp": "Neural MLP — scaled tabular neural surrogate",
    "neural_mlp_ensemble": "Neural MLP Ensemble — neural surrogate with spread/confidence",
}
SAMPLERS         = ["lhs_v1","random_v1"]
SAMPLER_LABELS   = {"lhs_v1":"Latin Hypercube (LHS) — best coverage, recommended",
                    "random_v1":"Random — simple, may cluster"}
QC_PRESETS       = ["off","debug","production","promotion_strict"]
QC_PRESET_LABELS = {
    "off":              "Off — skip all QC (smoke/debug only)",
    "debug":            "Debug — run QC but don't block on failures",
    "production":       "Production — run QC and block on failures ✓ recommended",
    "promotion_strict": "Promotion strict — strict profile, blocks on any failure",
}
RETENTION        = ["all","failures_only","none"]
RETENTION_LABELS = {"all":"Keep all run folders (large disk use)",
                    "failures_only":"Keep only failed cases for debugging ✓ recommended",
                    "none":"Delete all run folders after dataset creation"}
SPACING          = ["equal","cosine"]
SPLIT_METHODS    = ["grouped","random"]
QC_PROFILES      = ["basic","strict"]

PAGES = [
    ("home",      "⌂",  "Home"),
    ("examples",  "★",  "Example Workflows"),
    ("geometry",  "△",  "Geometry"),
    ("dataset",   "▣",  "Dataset Factory"),
    ("aero",      "⊿",  "Aero Analysis"),
    ("dynamics",  "◎",  "Dynamics"),
    ("ml",        "◈",  "ML Studio"),
    ("multifid",  "⊞",  "Multifidelity"),
    ("results",   "◫",  "Results Browser"),
    ("config",    "✎",  "Config Lab"),
]

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
<style>
/* Mild dark AERIS theme:
   soft slate background, readable cards, restrained blue/teal accents.
   Keep the GUI comfortable for long engineering sessions. */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@300;400;500&display=swap');

html, body, .stApp { background:#17212B !important; color:#E6ECF2 !important; font-family:'Inter',sans-serif !important; }
#MainMenu,footer,.stDeployButton{visibility:hidden;display:none}

/* sidebar */
section[data-testid="stSidebar"]{background:#111A23!important;border-right:1px solid #334252!important;}
section[data-testid="stSidebar"]>div:first-child{padding-top:0!important}

/* main */
.main .block-container{padding:1.6rem 2.0rem 3rem!important;max-width:1280px!important}

/* headings */
h1{font-size:1.65rem!important;font-weight:600!important;color:#F8FAFC!important;letter-spacing:-.01em!important;margin-bottom:.2rem!important}
h2{font-size:1.1rem!important;font-weight:600!important;color:#d8dce8!important}
h3{font-size:.95rem!important;font-weight:500!important;color:#D6DEE8!important}

/* labels */
label,.stMarkdown p{color:#C0CAD6!important;font-size:.8rem!important}
div[data-testid="stRadio"] label{color:#D6DEE8!important;font-size:.84rem!important}
div[data-testid="stCheckbox"] label{color:#D6DEE8!important;font-size:.84rem!important}
div[data-testid="stSelectbox"] label{color:#C0CAD6!important;font-size:.78rem!important;text-transform:uppercase;letter-spacing:.06em}
div[data-testid="stTextInput"] label,div[data-testid="stNumberInput"] label{color:#C0CAD6!important;font-size:.78rem!important;text-transform:uppercase;letter-spacing:.06em}

/* inputs */
div[data-testid="stTextInput"] input,div[data-testid="stNumberInput"] input{
  background:#263545!important;border:1px solid #405166!important;border-radius:7px!important;
  color:#F2F5F8!important;font-family:'JetBrains Mono',monospace!important;font-size:.82rem!important;padding:8px 11px!important}
div[data-testid="stTextInput"] input:focus,div[data-testid="stNumberInput"] input:focus{border-color:#3b82f6!important}
div[data-testid="stSelectbox"]>div>div{background:#263545!important;border:1px solid #405166!important;border-radius:7px!important;color:#F2F5F8!important;font-size:.83rem!important}
div[data-testid="stTextArea"] textarea{background:#111A23!important;border:1px solid #405166!important;border-radius:7px!important;color:#F2F5F8!important;font-family:'JetBrains Mono',monospace!important;font-size:.79rem!important}
div[data-testid="stSlider"] p{font-size:.78rem!important}

/* buttons */
div[data-testid="stButton"] button{border-radius:7px!important;font-family:'Inter',sans-serif!important;font-weight:500!important;font-size:.85rem!important;transition:all .15s!important}
div[data-testid="stButton"] button[kind="primary"]{background:#3B82F6!important;color:#fff!important;border:none!important;padding:.5rem 1.4rem!important}
div[data-testid="stButton"] button[kind="primary"]:hover{background:#2F80ED!important;transform:translateY(-1px)!important}
div[data-testid="stButton"] button[kind="secondary"]{background:#263545!important;color:#D6DEE8!important;border:1px solid #405166!important;padding:.45rem 1.1rem!important}
div[data-testid="stButton"] button[kind="secondary"]:hover{background:#161c2a!important;color:#F2F5F8!important}

/* containers */
div[data-testid="stExpander"]{background:#202B36!important;border:1px solid #334252!important;border-radius:9px!important}
div[data-testid="stExpander"] summary{color:#C0CAD6!important;font-size:.8rem!important}
[data-testid="stVerticalBlock"]>div[style*="border"]{background:#202B36!important;border-color:#334252!important;border-radius:9px!important}

/* metrics */
div[data-testid="metric-container"]{background:#202B36!important;border:1px solid #334252!important;border-radius:9px!important;padding:.9rem 1rem!important}
div[data-testid="metric-container"] label{color:#AAB6C2!important;font-size:.7rem!important;text-transform:uppercase;letter-spacing:.1em!important}
div[data-testid="metric-container"] [data-testid="stMetricValue"]{color:#F2F5F8!important;font-family:'JetBrains Mono',monospace!important;font-size:1.5rem!important;font-weight:500!important}

/* tabs */
button[data-baseweb="tab"]{font-family:'Inter',sans-serif!important;font-size:.83rem!important;color:#C0CAD6!important}
button[data-baseweb="tab"][aria-selected="true"]{color:#F2F5F8!important;border-bottom-color:#3B82F6!important}
div[data-baseweb="tab-list"]{border-bottom:1px solid #334252!important;background:transparent!important}
div[data-baseweb="tab-panel"]{padding-top:1.2rem!important}

/* code */
div[data-testid="stCodeBlock"]{background:#17212B!important;border:1px solid #334252!important;border-radius:7px!important}
div[data-testid="stCodeBlock"] pre{font-family:'JetBrains Mono',monospace!important;font-size:.77rem!important;color:#7ab3f0!important}

/* alerts */
div[data-testid="stAlert"]{border-radius:7px!important;border-width:1px!important}

/* dataframe */
div[data-testid="stDataFrame"]{border:1px solid #334252!important;border-radius:9px!important;overflow:hidden!important}

/* sidebar specific — deliberately high contrast */
section[data-testid="stSidebar"]{background:#162232!important;border-right:1px solid #405166!important;}
section[data-testid="stSidebar"] *{visibility:visible!important;}
section[data-testid="stSidebar"] label{color:#DCE6F1!important;font-size:.82rem!important}
section[data-testid="stSidebar"] input{background:#223142!important;border-color:#4B5F75!important;color:#F4F8FB!important;font-size:.82rem!important}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div{color:inherit;}
section[data-testid="stSidebar"] div[role="radiogroup"]{padding:.15rem .55rem .7rem!important;}
section[data-testid="stSidebar"] div[role="radiogroup"] label{
  background:#202E3C!important;
  border:1px solid #34485C!important;
  border-radius:10px!important;
  padding:.55rem .7rem!important;
  margin:.20rem 0!important;
  color:#F2F6FA!important;
  font-size:.88rem!important;
  font-weight:500!important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover{
  background:#26384A!important;
  border-color:#4E657C!important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){
  background:#2F80ED22!important;
  border-color:#3B82F6!important;
  color:#FFFFFF!important;
  box-shadow:inset 3px 0 0 #3B82F6!important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label p{
  color:#F2F6FA!important;
  font-size:.88rem!important;
  font-weight:500!important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"]{
  background:#1B2A3A!important;
  border:1px solid #405166!important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p{color:#F2F6FA!important;}

/* spinner */
.stSpinner>div{border-top-color:#3B82F6!important}

/* number input buttons */
div[data-testid="stNumberInput"] button{background:#161c2a!important;border-color:#405166!important;color:#C0CAD6!important}

/* multiselect */
div[data-testid="stMultiSelect"]>div{background:#263545!important;border-color:#405166!important}
span[data-baseweb="tag"]{background:#405166!important}

/* divider */
hr{border-color:#334252!important}

/* =======================================================================
   AERIS SIDEBAR VISIBILITY HOTFIX
   Uses high-contrast button navigation instead of fragile radio labels.
   ======================================================================= */
section[data-testid="stSidebar"],
aside[data-testid="stSidebar"]{
  background:#162232!important;
  border-right:1px solid #4B6075!important;
  min-width:285px!important;
}

section[data-testid="stSidebar"] *,
aside[data-testid="stSidebar"] *{
  visibility:visible!important;
}

section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div,
aside[data-testid="stSidebar"] p,
aside[data-testid="stSidebar"] span,
aside[data-testid="stSidebar"] label,
aside[data-testid="stSidebar"] div{
  color:#EAF2FA!important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"],
aside[data-testid="stSidebar"] div[data-testid="stButton"]{
  margin:.20rem .75rem!important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] button,
aside[data-testid="stSidebar"] div[data-testid="stButton"] button{
  width:100%!important;
  min-height:42px!important;
  justify-content:flex-start!important;
  text-align:left!important;
  background:#223142!important;
  color:#F4F8FC!important;
  border:1px solid #42566A!important;
  border-radius:10px!important;
  padding:.58rem .78rem!important;
  font-size:.88rem!important;
  font-weight:600!important;
  letter-spacing:.01em!important;
  box-shadow:none!important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover,
aside[data-testid="stSidebar"] div[data-testid="stButton"] button:hover{
  background:#2A3B4D!important;
  border-color:#5B748C!important;
  color:#FFFFFF!important;
  transform:none!important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"],
aside[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"],
section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="baseButton-primary"],
aside[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="baseButton-primary"]{
  background:#2F80ED!important;
  border-color:#60A5FA!important;
  color:#FFFFFF!important;
  box-shadow:inset 4px 0 0 #A7F3D0!important;
}

section[data-testid="stSidebar"] input,
aside[data-testid="stSidebar"] input{
  background:#263545!important;
  border-color:#5B748C!important;
  color:#FFFFFF!important;
}

section[data-testid="stSidebar"] [data-testid="stExpander"],
aside[data-testid="stSidebar"] [data-testid="stExpander"]{
  background:#1B2A3A!important;
  border:1px solid #4B6075!important;
  border-radius:10px!important;
}


/* =======================================================================
   AERIS STREAMLIT SIDEBAR RESTORE FIX
   Do NOT hide Streamlit's header. The collapsed-sidebar restore control lives
   there in many Streamlit versions. Keep it visible and readable.
   ======================================================================= */
header[data-testid="stHeader"],
div[data-testid="stHeader"],
.stApp > header{
  display:block!important;
  visibility:visible!important;
  opacity:1!important;
  background:#172432CC!important;
  border-bottom:1px solid #33465A!important;
  height:2.75rem!important;
  z-index:999999!important;
}

header[data-testid="stHeader"] *,
div[data-testid="stHeader"] *,
.stApp > header *{
  visibility:visible!important;
  opacity:1!important;
}

button[kind="header"],
button[data-testid="baseButton-header"],
button[title*="sidebar" i],
button[aria-label*="sidebar" i],
button[title*="Sidebar" i],
button[aria-label*="Sidebar" i]{
  display:flex!important;
  visibility:visible!important;
  opacity:1!important;
  color:#FFFFFF!important;
  background:#223142!important;
  border:1px solid #5B748C!important;
  border-radius:8px!important;
}

.main .block-container{
  padding-top:2.3rem!important;
}

</style>
"""

# ── HTML helpers ──────────────────────────────────────────────────────────────
def _h(html: str) -> None: st.markdown(html, unsafe_allow_html=True)

def _hero(icon: str, title: str, sub: str, badge: str = "", bcolor: str = "#3B82F6") -> None:
    b = f'<span style="margin-left:10px;padding:2px 10px;background:{bcolor}18;color:{bcolor};border:1px solid {bcolor}35;border-radius:20px;font-size:.7rem;font-weight:600;letter-spacing:.07em;font-family:JetBrains Mono,monospace;vertical-align:middle">{badge}</span>' if badge else ""
    _h(f'<div style="margin-bottom:1.6rem"><div style="display:flex;align-items:center;gap:12px;margin-bottom:.25rem"><div style="width:38px;height:38px;background:{bcolor}12;border:1px solid {bcolor}25;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:1.15rem">{icon}</div><div><h1 style="margin:0!important">{title}{b}</h1><p style="margin:0!important;font-size:.78rem!important;color:#AAB6C2!important;font-family:JetBrains Mono,monospace">{sub}</p></div></div></div>')

def _sec(label: str) -> None:
    _h(f'<div style="display:flex;align-items:center;gap:8px;margin:1.4rem 0 .7rem"><span style="font-size:.68rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:#7F8B98;white-space:nowrap">{label}</span><div style="flex:1;height:1px;background:#2A3848"></div></div>')

def _note(text: str, kind: str = "info") -> None:
    c = {"info":"#3B82F6","warn":"#F59E0B","ok":"#22C55E","err":"#EF4444"}.get(kind,"#3B82F6")
    _h(f'<div style="background:{c}0d;border-left:3px solid {c}60;border-radius:0 6px 6px 0;padding:9px 13px;margin:.6rem 0;font-size:.81rem;color:{c};line-height:1.65">{text}</div>')

def _badge(text: str, color: str = "#3B82F6") -> str:
    return f'<span style="display:inline-block;padding:1px 8px;background:{color}15;color:{color};border:1px solid {color}30;border-radius:20px;font-size:.69rem;font-weight:600;letter-spacing:.06em;font-family:JetBrains Mono,monospace">{text}</span>'

def _stat_row(stats: list[tuple]) -> None:
    cols = st.columns(len(stats))
    for col,(label,val,sub) in zip(cols,stats):
        with col: _h(f'<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:.9rem 1rem"><div style="font-size:.68rem;color:#7F8B98;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:5px">{label}</div><div style="font-size:1.45rem;font-weight:500;color:#F2F5F8;font-family:JetBrains Mono,monospace;line-height:1">{val}</div><div style="font-size:.7rem;color:#8EA0B3;margin-top:3px">{sub}</div></div>')

def _pipeline(steps: list[tuple]) -> None:
    parts=[]
    for i,(name,st_) in enumerate(steps):
        bg,bd,col,icon=("#22C55E10","#22C55E40","#22C55E","✓") if st_=="done" else (("#3B82F610","#3B82F640","#3B82F6","→") if st_=="active" else ("#2A3848","#405166","#8EA0B3",str(i+1)))
        conn='<div style="flex:1;height:1px;background:#2A3848;margin-top:-14px"></div>' if i<len(steps)-1 else ""
        parts.append(f'<div style="display:flex;flex-direction:column;align-items:center;flex:1"><div style="width:26px;height:26px;border-radius:50%;background:{bg};border:1.5px solid {bd};display:flex;align-items:center;justify-content:center;font-size:.68rem;font-weight:600;color:{col};position:relative;z-index:1;font-family:JetBrains Mono,monospace">{icon}</div><div style="font-size:.66rem;color:{col if st_!="pending" else "#7F8B98"};margin-top:4px;text-align:center">{name}</div></div>{conn}')
    _h(f'<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:1rem 1.2rem;margin-bottom:1rem"><div style="display:flex;align-items:flex-start">{"".join(parts)}</div></div>')

def _card(fn) -> None:
    _h('<div style="background:#202B36;border:1px solid #334252;border-radius:10px;padding:1.2rem 1.3rem;margin-bottom:1rem">')
    fn()
    _h('</div>')

# ── data helpers ──────────────────────────────────────────────────────────────
@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

def _default_root() -> Path:
    cwd = Path.cwd().resolve()
    for c in [cwd,*cwd.parents]:
        if (c/"src"/"aeris").exists(): return c
    return cwd

def _repo_ok(p: Path) -> bool: return (p/"src"/"aeris").exists()

@st.cache_data(ttl=30)
def _dirs(root_str: str, pattern: str = "*") -> list[str]:
    root = Path(root_str)
    if not root.exists(): return []
    return [str(p) for p in sorted([p for p in root.glob(pattern) if p.is_dir()], key=lambda x:x.stat().st_mtime, reverse=True)[:300]]

@st.cache_data(ttl=30)
def _files(root_str: str, pattern: str = "*") -> list[str]:
    root = Path(root_str)
    if not root.exists(): return []
    return [str(p) for p in sorted([p for p in root.glob(pattern) if p.is_file()], key=lambda x:x.stat().st_mtime, reverse=True)[:300]]

def _read(p: Path, lim: int = 250_000) -> str:
    try: return p.read_text(encoding="utf-8",errors="replace")[:lim]
    except Exception as e: return f"<error: {e}>"

def _rjson(p: Path) -> Any | None:
    try: return json.loads(p.read_text(encoding="utf-8"))
    except: return None

def _quote(cmd: Iterable[str]) -> str:
    try: return shlex.join([str(x) for x in cmd])
    except: return " ".join([str(x) for x in cmd])

def _xargs(text: str) -> list[str]:
    if not text.strip(): return []
    try: return shlex.split(text)
    except Exception as e: st.error(f"Parse error: {e}"); return []

def _flag(args: list, flag: str, val: Any) -> None:
    if val is None: return
    s = str(val).strip()
    if s: args.extend([flag,s])

def _bflag(args: list, t: str, f: str|None, val: bool|None) -> None:
    if val is None: return
    args.append(t if val else (f or ""))

def _csvn(text: str) -> int:
    return max(1,len([x for x in text.split(",") if x.strip()]))

def _est(*fields: str) -> int:
    n=1
    for f in fields: n*=_csvn(f)
    return n

def _run(root: Path, exe: str, args: Iterable[str], timeout: int) -> CommandResult:
    cmd=[exe,"--no-check-writable",*[str(a) for a in args]]
    env=os.environ.copy()
    env["PYTHONPATH"]=str(root/"src")+os.pathsep+env.get("PYTHONPATH","")
    try:
        r=subprocess.run(cmd,cwd=root,env=env,text=True,capture_output=True,timeout=timeout)
        return CommandResult(cmd,r.returncode,r.stdout,r.stderr)
    except FileNotFoundError as e: return CommandResult(cmd,127,"",str(e))
    except subprocess.TimeoutExpired as e: return CommandResult(cmd,124,e.stdout or"",(e.stderr or"")+f"\nTimeout after {timeout}s.")

def _save(r: CommandResult) -> None:
    st.session_state["last"]=r
    h=st.session_state.setdefault("history",[])
    h.insert(0,r); del h[50:]

def _show(r: CommandResult) -> None:
    if r.returncode==0: st.success("Completed successfully")
    else: st.error(f"Failed — exit code {r.returncode}")
    if r.stdout.strip():
        with st.expander("Output",expanded=(r.returncode!=0)): st.code(r.stdout.strip()[-80_000:],language="text")
    if r.stderr.strip():
        with st.expander("Errors / warnings",expanded=True): st.code(r.stderr.strip()[-80_000:],language="text")

def _panel(title: str, desc: str, args: list, root: Path, exe: str, tmo: int,
           dry: bool, key: str, label: str="▶  Run", danger: bool=False) -> None:
    with st.container(border=True):
        _h(f'<div style="font-weight:600;color:#F2F5F8;font-size:.9rem;margin-bottom:3px">{title}</div>')
        _h(f'<div style="font-size:.78rem;color:#AAB6C2;margin-bottom:.7rem">{desc}</div>')
        if dry: _note("Dry-run is ON — task will not execute.","warn"); return
        if st.button(label,key=key,type="secondary" if danger else "primary"):
            if not _repo_ok(root): st.error("AERIS repo not found. Check project root in sidebar."); return
            with st.spinner("Running…"):
                r=_run(root,exe,args,tmo)
            _save(r); _show(r)

def _pick_dir(label: str, root: Path, key: str, help_: str="") -> str:
    dirs=_dirs(str(root))
    opts=[""]+dirs
    sel=st.selectbox(label,opts,index=1 if len(opts)>1 else 0,key=f"{key}_s",help=help_)
    return st.text_input("Manual path override",value=sel,key=f"{key}_m")

def _pick_file(label: str, root: Path, pat: str, key: str, default: str="") -> str:
    files=_files(str(root),pat)
    opts=[default]+files
    sel=st.selectbox(label,opts,index=0,key=f"{key}_s")
    return st.text_input("Manual path override",value=sel,key=f"{key}_m")

def _show_file(p: Path) -> None:
    if not p.exists(): _note(f"File not found: {p}","warn"); return
    st.caption(str(p))
    suf=p.suffix.lower()
    if suf==".json":
        d=_rjson(p); st.json(d or {"error":"unreadable"})
    elif suf==".csv":
        if pd is None: st.code(_read(p))
        else:
            try:
                df=pd.read_csv(p)
                st.caption(f"{len(df):,} rows · {len(df.columns):,} columns")
                st.dataframe(df,use_container_width=True,height=360)
                num=list(df.select_dtypes("number").columns)
                if num:
                    with st.expander("Quick plot"):
                        cols=st.multiselect("Columns",num,default=num[:3],key=f"plt_{p}")
                        if cols: st.line_chart(df[cols])
            except Exception as e: st.error(str(e)); st.code(_read(p))
    elif suf in {".png",".jpg",".jpeg",".webp"}: st.image(str(p),use_container_width=True)
    else: st.code(_read(p),language="yaml" if suf in {".yaml",".yml"} else "text")

# ── YAML builder ──────────────────────────────────────────────────────────────
def _yaml_geometry_builder(key_pfx: str) -> str:
    """Returns a YAML string built from sliders/inputs. No file needed."""
    _sec("Generator")
    c1,c2=st.columns(2)
    gen_id=c1.selectbox("Generator ID",["bwb_segmented_v1"],key=f"{key_pfx}_gid")
    seed=c2.number_input("Seed",min_value=0,value=100,step=1,key=f"{key_pfx}_seed",help="Same seed = same geometry. Change to explore design space.")
    name=st.text_input("Config name",value="aeris_design_space",key=f"{key_pfx}_name")

    _sec("Mesh control")
    c1,c2,c3=st.columns(3)
    n_pts=c1.number_input("n_points",min_value=3,value=10,step=1,key=f"{key_pfx}_npts",help="Control polygon points")
    n_in=c2.number_input("n_spline_inboard",min_value=4,value=20,step=1,key=f"{key_pfx}_nin",help="20 for datasets, 150 for visualization only")
    n_out=c3.number_input("n_spline_outboard",min_value=2,value=10,step=1,key=f"{key_pfx}_nout")
    c4,c5=st.columns(2)
    curv=c4.slider("Curvature strength",0.0,2.0,1.0,0.05,key=f"{key_pfx}_curv",help="1.0 = default BWB curvature")
    spl_ratio=c5.slider("Spline split ratio",0.3,0.8,0.55,0.05,key=f"{key_pfx}_spr")

    _sec("Planform bounds — chord")
    _note("YAML sweep values are <b>positive magnitudes</b>. The sampler negates them internally. Never negate twice.","info")
    c1,c2,c3,c4=st.columns(4)
    c1m_min=c1.number_input("c1_m min",0.1,2.0,0.35,0.05,key=f"{key_pfx}_c1mn",help="Root chord [m]")
    c1m_max=c1.number_input("c1_m max",0.1,2.0,0.65,0.05,key=f"{key_pfx}_c1mx")
    c2r_min=c2.number_input("c2_ratio min",0.1,1.0,0.45,0.05,key=f"{key_pfx}_c2mn",help="Chord ratio at break 2")
    c2r_max=c2.number_input("c2_ratio max",0.1,1.0,0.75,0.05,key=f"{key_pfx}_c2mx")
    c3r_min=c3.number_input("c3_ratio min",0.05,1.0,0.25,0.05,key=f"{key_pfx}_c3mn")
    c3r_max=c3.number_input("c3_ratio max",0.05,1.0,0.55,0.05,key=f"{key_pfx}_c3mx")
    c4r_min=c4.number_input("c4_ratio min",0.02,0.5,0.08,0.01,key=f"{key_pfx}_c4mn",help="Tip chord ratio")
    c4r_max=c4.number_input("c4_ratio max",0.02,0.5,0.20,0.01,key=f"{key_pfx}_c4mx")

    _sec("Planform bounds — span")
    c1,c2,c3=st.columns(3)
    b_min=c1.number_input("b_total_m min [semi-span]",0.3,3.0,0.70,0.05,key=f"{key_pfx}_bmn",help="Semi-span [m]. Full span = 2×")
    b_max=c1.number_input("b_total_m max",0.3,3.0,1.10,0.05,key=f"{key_pfx}_bmx")
    b3_min=c2.number_input("b3_ratio min",0.1,0.9,0.40,0.05,key=f"{key_pfx}_b3mn",help="Outboard segment fraction")
    b3_max=c2.number_input("b3_ratio max",0.1,0.9,0.60,0.05,key=f"{key_pfx}_b3mx")
    sp_min=c3.number_input("split_ratio min",0.1,0.9,0.35,0.05,key=f"{key_pfx}_spmn",help="Inboard/mid split fraction")
    sp_max=c3.number_input("split_ratio max",0.1,0.9,0.55,0.05,key=f"{key_pfx}_spmx")

    _sec("Planform bounds — sweep [positive magnitudes in YAML]")
    c1,c2,c3=st.columns(3)
    sw1_min=c1.number_input("sw1_deg min",0.0,80.0,30.0,1.0,key=f"{key_pfx}_sw1mn",help="Inner LE sweep magnitude")
    sw1_max=c1.number_input("sw1_deg max",0.0,80.0,50.0,1.0,key=f"{key_pfx}_sw1mx")
    sw2_min=c2.number_input("sw2_deg min",0.0,60.0,15.0,1.0,key=f"{key_pfx}_sw2mn",help="Mid LE sweep magnitude")
    sw2_max=c2.number_input("sw2_deg max",0.0,60.0,30.0,1.0,key=f"{key_pfx}_sw2mx")
    sw3_min=c3.number_input("sw3_deg min",0.0,40.0,5.0,1.0,key=f"{key_pfx}_sw3mn",help="Outer LE sweep magnitude")
    sw3_max=c3.number_input("sw3_deg max",0.0,40.0,15.0,1.0,key=f"{key_pfx}_sw3mx")

    _sec("Section bounds — twist")
    _note("Twist positive = leading edge up (washout). Root dihedral is always 0° — fixed, not sampled.","info")
    c1,c2,c3,c4=st.columns(4)
    tw0m=c1.number_input("twist_b0 min",-10.0,10.0,-1.0,0.5,key=f"{key_pfx}_tw0mn"); tw0x=c1.number_input("max",-10.0,10.0,1.0,0.5,key=f"{key_pfx}_tw0mx")
    tw1m=c2.number_input("twist_b1 min",-10.0,10.0,-2.0,0.5,key=f"{key_pfx}_tw1mn"); tw1x=c2.number_input("max",-10.0,10.0,2.0,0.5,key=f"{key_pfx}_tw1mx")
    tw2m=c3.number_input("twist_b2 min",-10.0,10.0,-3.0,0.5,key=f"{key_pfx}_tw2mn"); tw2x=c3.number_input("max",-10.0,10.0,3.0,0.5,key=f"{key_pfx}_tw2mx")
    tw3m=c4.number_input("twist_b3 min",-10.0,10.0,-4.0,0.5,key=f"{key_pfx}_tw3mn"); tw3x=c4.number_input("max",-10.0,10.0,4.0,0.5,key=f"{key_pfx}_tw3mx")

    _sec("Section bounds — dihedral")
    c1,c2,c3=st.columns(3)
    dh1m=c1.number_input("dihedral_b1 min",0.0,15.0,0.0,0.5,key=f"{key_pfx}_dh1mn",help="Dihedral positive = tip above root"); dh1x=c1.number_input("max",0.0,15.0,3.0,0.5,key=f"{key_pfx}_dh1mx")
    dh2m=c2.number_input("dihedral_b2 min",0.0,15.0,0.0,0.5,key=f"{key_pfx}_dh2mn"); dh2x=c2.number_input("max",0.0,15.0,5.0,0.5,key=f"{key_pfx}_dh2mx")
    dh3m=c3.number_input("dihedral_b3 min",0.0,15.0,0.0,0.5,key=f"{key_pfx}_dh3mn"); dh3x=c3.number_input("max",0.0,15.0,7.0,0.5,key=f"{key_pfx}_dh3mx")

    _sec("Airfoil & control surfaces")
    c1,c2=st.columns(2)
    airfoil=c1.text_input("Airfoil name",value="naca4412",key=f"{key_pfx}_af",help="NACA 4-digit or profile name")
    ctrl_en=c2.checkbox("Enable control surfaces",value=True,key=f"{key_pfx}_csen")

    ctrl_block=""
    if ctrl_en:
        c3,c4,c5=st.columns(3)
        hinge=c3.slider("Hinge point (chord fraction)",0.5,0.95,0.75,0.01,key=f"{key_pfx}_hp")
        sp_start=c4.slider("Span start fraction",0.3,0.9,0.60,0.01,key=f"{key_pfx}_css")
        sp_end=c5.slider("Span end fraction",0.5,1.0,0.95,0.01,key=f"{key_pfx}_cse")
        ctrl_block=f"""  control_surfaces:
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
        ctrl_block="  control_surfaces:\n    enabled: false\n    surfaces: []"

    _sec("Output options")
    c1,c2,c3=st.columns(3)
    save_plot=c1.checkbox("Save planform plot",value=False,key=f"{key_pfx}_sp")
    build_asb=c2.checkbox("Build AeroSandbox object (required for aero)",value=True,key=f"{key_pfx}_ba")

    yaml_str=textwrap.dedent(f"""\
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
    spline_split_ratio: {spl_ratio}
  planform_bounds:
    c1_m:        {{min: {c1m_min}, max: {c1m_max}}}
    c2_ratio:    {{min: {c2r_min}, max: {c2r_max}}}
    c3_ratio:    {{min: {c3r_min}, max: {c3r_max}}}
    c4_ratio:    {{min: {c4r_min}, max: {c4r_max}}}
    b_total_m:   {{min: {b_min}, max: {b_max}}}
    b3_ratio:    {{min: {b3_min}, max: {b3_max}}}
    split_ratio: {{min: {sp_min}, max: {sp_max}}}
    sw1_deg:     {{min: {sw1_min}, max: {sw1_max}}}
    sw2_deg:     {{min: {sw2_min}, max: {sw2_max}}}
    sw3_deg:     {{min: {sw3_min}, max: {sw3_max}}}
  section_bounds:
    airfoil_name: {airfoil}
    dihedral_root_deg: 0.0
    twist_b0_deg:    {{min: {tw0m}, max: {tw0x}}}
    twist_b1_deg:    {{min: {tw1m}, max: {tw1x}}}
    twist_b2_deg:    {{min: {tw2m}, max: {tw2x}}}
    twist_b3_deg:    {{min: {tw3m}, max: {tw3x}}}
    dihedral_b1_deg: {{min: {dh1m}, max: {dh1x}}}
    dihedral_b2_deg: {{min: {dh2m}, max: {dh2x}}}
    dihedral_b3_deg: {{min: {dh3m}, max: {dh3x}}}
{ctrl_block}
  outputs:
    save_plot: {str(save_plot).lower()}
    build_aerosandbox: {str(build_asb).lower()}
dataset:
  sampling:
    method: lhs_v1
    seed: {seed}
""")
    return yaml_str

# ── sidebar ───────────────────────────────────────────────────────────────────
def _sidebar() -> tuple:
    """High-contrast, button-based sidebar.

    The older GUI used Streamlit radio navigation. On some Streamlit/theme
    combinations, radio labels can become invisible after heavy custom CSS.
    This version uses buttons because they are easier to see and much harder
    for Streamlit CSS internals to hide.
    """
    st.sidebar.markdown(
        f"""
        <div style="padding:1.15rem 1rem .9rem;border-bottom:1px solid #4B6075;margin-bottom:.65rem;background:#1B2A3A;border-radius:0 0 12px 12px">
          <div style="display:flex;align-items:center;gap:10px">
            <div style="width:32px;height:32px;background:linear-gradient(135deg,#2F80ED,#3B82F6);border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.95rem;color:#fff">A</div>
            <div>
              <div style="font-size:1.02rem;font-weight:700;color:#FFFFFF;letter-spacing:.01em">AERIS</div>
              <div style="font-size:.64rem;color:#B7C6D7;letter-spacing:.14em;font-family:JetBrains Mono,monospace">MILD DARK v{APP_VERSION}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar.expander("⚙  Settings", expanded=False):
        root_str = st.text_input(
            "Project root",
            value=str(_default_root()),
            key="sb_root",
            help="Absolute path to the AERIS repo root (the folder containing src/aeris/). "
                 "Auto-detected by walking up from the current directory. Change only if auto-detection fails.",
        )
        exe = st.text_input(
            "AERIS executable",
            value=shutil.which("aeris") or "aeris",
            key="sb_exe",
            help="The aeris command on your PATH, or an absolute path to it. "
                 "Auto-detected with shutil.which. Usually leave as-is.",
        )
        tmo = int(st.number_input(
            "Timeout [s]",
            min_value=30, max_value=86400, value=1800, step=30,
            key="sb_tmo",
            help="Max seconds the GUI waits for any single aeris command. "
                 "Increase for large dataset runs (e.g. 3600). Default 1800 = 30 min.",
        ))
        dry = st.toggle(
            "Dry-run (preview only)",
            False,
            key="sb_dry",
            help="When ON: shows the exact command that would run, but does NOT execute it. "
                 "Use to verify arguments before a long run.",
        )

    root = Path(st.session_state.get("sb_root", str(_default_root()))).expanduser().resolve()
    exe  = st.session_state.get("sb_exe", shutil.which("aeris") or "aeris")
    tmo  = int(st.session_state.get("sb_tmo", 1800))
    dry  = bool(st.session_state.get("sb_dry", False))

    ok = _repo_ok(root)
    dot = "#22C55E" if ok else "#EF4444"
    msg = "connected" if ok else "repo not found"
    st.sidebar.markdown(
        f"""
        <div style="padding:.15rem 1rem .8rem;display:flex;align-items:center;gap:8px;font-size:.78rem;color:#DCE8F4">
          <div style="width:8px;height:8px;border-radius:50%;background:{dot}"></div>
          <span style="color:#DCE8F4;font-weight:600">{msg}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown(
        """
        <div style="padding:.2rem .95rem .35rem">
          <div style="font-size:.70rem;color:#B7C6D7;letter-spacing:.14em;font-weight:800">WORKSPACE</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "home"

    for pid, icon, name in PAGES:
        selected = st.session_state["active_page"] == pid
        prefix = "●" if selected else "○"
        label = f"{prefix}  {icon}  {name}"
        if st.sidebar.button(
            label,
            key=f"nav_btn_{pid}",
            use_container_width=True,
            type="primary" if selected else "secondary",
        ):
            st.session_state["active_page"] = pid

    page_id = st.session_state.get("active_page", "home")

    if "last" in st.session_state:
        r = st.session_state["last"]
        c = "#22C55E" if r.returncode == 0 else "#EF4444"
        st.sidebar.markdown(
            f"""
            <div style="margin:1rem .85rem .7rem;padding:.6rem .75rem;border:1px solid #4B6075;border-radius:10px;background:#1B2A3A">
              <div style="font-size:.75rem;color:{c};font-family:JetBrains Mono,monospace;font-weight:700">{"✓" if r.returncode==0 else "✗"} last: exit {r.returncode}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return root, exe, tmo, dry, page_id


# ── pages ─────────────────────────────────────────────────────────────────────

def pg_home(root,exe,tmo,dry):
    # ── detect pipeline state from filesystem ──────────────────────────────
    datasets_root   = root / "data" / "datasets"
    runs_root       = root / "data" / "runs"
    ml_root         = root / "data" / "processed" / "ml_runs"

    geo_configs     = _files(str(root / "configs" / "geometry"), "*.yaml")
    geo_runs        = _dirs(str(runs_root))
    all_datasets    = _dirs(str(datasets_root))

    # promoted datasets: have promotion_manifest.json
    promoted = [d for d in all_datasets if (Path(d) / "promotion_manifest.json").exists()]
    # aero datasets: have aero_dataset.csv
    aero_ds  = [d for d in all_datasets if (Path(d) / "aero_dataset.csv").exists()]
    # ml runs: have metrics.json
    ml_runs  = [d for d in _dirs(str(ml_root)) if (Path(d) / "metrics.json").exists()]
    # promoted models: have model_promotion_manifest.json
    promoted_models = [d for d in _dirs(str(ml_root)) if (Path(d) / "model_promotion_manifest.json").exists()]

    has_config     = len(geo_configs) > 0
    has_geo_run    = len(geo_runs) > 0
    has_aero_ds    = len(aero_ds) > 0
    has_promoted   = len(promoted) > 0
    has_ml         = len(ml_runs) > 0
    has_promo_model= len(promoted_models) > 0

    # ── determine current step (1-6) ──────────────────────────────────────
    if has_promo_model:   current_step = 6
    elif has_ml:          current_step = 5
    elif has_promoted:    current_step = 4
    elif has_aero_ds:     current_step = 3
    elif has_geo_run:     current_step = 2
    elif has_config:      current_step = 1
    else:                 current_step = 0

    # ── header ─────────────────────────────────────────────────────────────
    _h("""<div style="margin-bottom:1.4rem">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:.2rem">
        <div style="width:40px;height:40px;background:#2F80ED12;border:1px solid #2F80ED25;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:1.2rem">⌂</div>
        <div>
          <h1 style="margin:0!important">AERIS Mission Control</h1>
          <p style="margin:0!important;font-size:.78rem!important;color:#AAB6C2!important;font-family:JetBrains Mono,monospace">BWB aerodynamic surrogate pipeline · mild dark workspace</p>
        </div>
      </div>
    </div>""")

    # ── pipeline progress visual ───────────────────────────────────────────
    steps_info = [
        (1, "Config",   "YAML design space file exists", has_config),
        (2, "Geometry", f"{len(geo_runs)} run{'s' if len(geo_runs)!=1 else ''}", has_geo_run),
        (3, "Aero data",f"{len(aero_ds)} dataset{'s' if len(aero_ds)!=1 else ''}", has_aero_ds),
        (4, "Promoted", f"{len(promoted)} promoted", has_promoted),
        (5, "ML model", f"{len(ml_runs)} run{'s' if len(ml_runs)!=1 else ''}", has_ml),
        (6, "Deployed", f"{len(promoted_models)} model{'s' if len(promoted_models)!=1 else ''}", has_promo_model),
    ]

    step_divs = []
    for num, label, detail, done in steps_info:
        is_next = (num == current_step + 1) and not done
        if done:
            bg,bd,col,icon = "#22C55E10","#22C55E50","#22C55E","✓"
        elif is_next:
            bg,bd,col,icon = "#3B82F610","#3B82F650","#3B82F6","→"
        else:
            bg,bd,col,icon = "#202B36","#405166","#8EA0B3",str(num)
        conn = '<div style="flex:1;height:1px;background:#2A3848;margin-top:-12px"></div>' if num < 6 else ""
        step_divs.append(f"""
        <div style="display:flex;flex-direction:column;align-items:center;flex:1">
          <div style="width:24px;height:24px;border-radius:50%;background:{bg};border:1.5px solid {bd};display:flex;align-items:center;justify-content:center;font-size:.68rem;font-weight:600;color:{col};position:relative;z-index:1;font-family:JetBrains Mono,monospace">{icon}</div>
          <div style="font-size:.66rem;color:{col if (done or is_next) else "#8EA0B3"};margin-top:4px;text-align:center;font-weight:{"600" if is_next else "400"}">{label}</div>
          <div style="font-size:.6rem;color:#7F8B98;text-align:center;margin-top:1px">{detail if done else ""}</div>
        </div>{conn}""")

    _h(f'''<div style="background:#202B36;border:1px solid #334252;border-radius:10px;padding:1rem 1.3rem;margin-bottom:1.4rem">
      <div style="display:flex;align-items:flex-start">{"".join(step_divs)}</div>
    </div>''')

    # ── next action card ───────────────────────────────────────────────────
    NEXT_ACTIONS = {
        0: ("No config found", "Create a geometry config YAML to define your design space.", "Go to Config Lab →", "config",  "#EF4444"),
        1: ("Ready to generate geometry", "You have a config. Generate one baseline geometry to verify your setup is working before running a full dataset.", "Generate geometry →", "geometry", "#3B82F6"),
        2: ("Ready to run aero analysis", "You have geometry runs. Run a single aero case or sweep to verify AVL is working on your geometry.", "Run aero analysis →", "aero", "#3B82F6"),
        3: ("Ready to curate and promote", f"You have {len(aero_ds)} aero dataset(s). Curate and promote the best one to make it available for ML training.", "Curate & promote →", "dataset", "#F59E0B"),
        4: ("Ready to train a surrogate", f"You have {len(promoted)} promoted dataset(s). Train an ML model on the promoted dataset.", "Train ML model →", "ml", "#22C55E"),
        5: ("Ready to promote your model", f"You have {len(ml_runs)} trained model(s). Promote the best one and use it for fast predictions.", "Promote & predict →", "ml", "#22C55E"),
        6: ("Pipeline complete", f"You have {len(promoted_models)} promoted model(s) ready for inference.", "Run predictions →", "ml", "#22C55E"),
    }

    title, desc, btn_label, btn_page, btn_color = NEXT_ACTIONS[current_step]

    _h(f'''<div style="background:{btn_color}08;border:1px solid {btn_color}25;border-radius:10px;padding:1.1rem 1.3rem;margin-bottom:1.4rem;display:flex;align-items:center;justify-content:space-between;gap:1rem">
      <div>
        <div style="font-size:.7rem;font-weight:600;color:{btn_color};letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px">Next step</div>
        <div style="font-size:.95rem;font-weight:600;color:#F2F5F8;margin-bottom:4px">{title}</div>
        <div style="font-size:.78rem;color:#4a5568;line-height:1.6">{desc}</div>
      </div>
    </div>''')

    _h(f'''<div style="margin-top:.8rem;font-size:.75rem;color:#AAB6C2">
      ↑ Click <strong style="color:#C0CAD6">{btn_label.replace("→","").strip()}</strong> in the left sidebar to continue.
    </div>''')

    # ── status grid ────────────────────────────────────────────────────────
    _sec("Current inventory")
    col1, col2, col3, col4 = st.columns(4)
    with col1: _h(f'''<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:.85rem 1rem"><div style="font-size:.68rem;color:#7F8B98;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:4px">Configs</div><div style="font-size:1.4rem;font-weight:500;color:#F2F5F8;font-family:JetBrains Mono,monospace">{len(geo_configs)}</div><div style="font-size:.69rem;color:#8EA0B3;margin-top:2px">configs/geometry/</div></div>''')
    with col2: _h(f'''<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:.85rem 1rem"><div style="font-size:.68rem;color:#7F8B98;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:4px">Geo runs</div><div style="font-size:1.4rem;font-weight:500;color:#F2F5F8;font-family:JetBrains Mono,monospace">{len(geo_runs)}</div><div style="font-size:.69rem;color:#8EA0B3;margin-top:2px">data/runs/</div></div>''')
    with col3: _h(f'''<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:.85rem 1rem"><div style="font-size:.68rem;color:#7F8B98;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:4px">Datasets</div><div style="font-size:1.4rem;font-weight:500;color:{"#22C55E" if has_promoted else "#F2F5F8"};font-family:JetBrains Mono,monospace">{len(promoted)}<span style="font-size:.75rem;color:#8EA0B3"> / {len(all_datasets)}</span></div><div style="font-size:.69rem;color:#8EA0B3;margin-top:2px">promoted / total</div></div>''')
    with col4: _h(f'''<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:.85rem 1rem"><div style="font-size:.68rem;color:#7F8B98;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin-bottom:4px">ML models</div><div style="font-size:1.4rem;font-weight:500;color:{"#22C55E" if has_promo_model else "#F2F5F8"};font-family:JetBrains Mono,monospace">{len(promoted_models)}<span style="font-size:.75rem;color:#8EA0B3"> / {len(ml_runs)}</span></div><div style="font-size:.69rem;color:#8EA0B3;margin-top:2px">promoted / trained</div></div>''')

    # ── recent activity ─────────────────────────────────────────────────────
    if geo_runs or all_datasets or ml_runs:
        _sec("Recent activity")
        items = []
        for d in geo_runs[:2]:
            p = Path(d)
            mf = p / "manifest.json"
            status = "success"
            if mf.exists():
                try:
                    status = json.loads(mf.read_text()).get("status","unknown")
                except: pass
            col = "#22C55E" if status=="success" else "#EF4444"
            items.append((p.name, "geometry run", status, col))
        for d in all_datasets[:2]:
            p = Path(d)
            kind = "promoted" if (p/"promotion_manifest.json").exists() else ("aero dataset" if (p/"aero_dataset.csv").exists() else "geometry dataset")
            col = "#22C55E" if kind=="promoted" else "#3B82F6"
            items.append((p.name, kind, kind, col))
        for d in ml_runs[:2]:
            p = Path(d)
            kind = "promoted model" if (p/"model_promotion_manifest.json").exists() else "ml run"
            col = "#22C55E" if kind=="promoted model" else "#F59E0B"
            items.append((p.name, kind, kind, col))

        rows_html = ""
        for name, kind, status, col in items[:6]:
            rows_html += f'''<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid #253240">
              <div style="width:6px;height:6px;border-radius:50%;background:{col};flex-shrink:0"></div>
              <div style="flex:1;font-size:.79rem;color:#D6DEE8;font-family:JetBrains Mono,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>
              <div style="font-size:.69rem;color:#8EA0B3;white-space:nowrap">{kind}</div>
            </div>'''
        _h(f'<div style="background:#202B36;border:1px solid #334252;border-radius:9px;overflow:hidden">{rows_html}</div>')

    # ── health check (minimal, no repeated warnings) ───────────────────────
    _sec("System check")
    _panel("Verify AERIS installation", "Confirm the AERIS engine is reachable and the environment is configured correctly.",
           ["version"], root, exe, tmo, dry, "home_ver", "▶  Run health check")


def pg_examples(root,exe,tmo,dry):
    _hero("★","Example Workflows","step-by-step guides for common AERIS tasks","guide")
    ex=st.selectbox("Select workflow",[
        "1 — Validate baseline geometry (single run)",
        "2 — Generate a small training dataset (50 geometries)",
        "3 — Run aero sweep on one existing geometry",
        "4 — Full campaign: dataset → QC → promote → train",
        "5 — Compare ML models on an existing dataset",
        "6 — Promote and predict with a trained model",
    ])
    if "1" in ex:
        _note("Goal: confirm the baseline geometry generates correctly and AVL runs on it.","info")
        _sec("Step 1 — Generate geometry")
        _h('<p>Go to <b>Geometry → Generate</b>, select <code>baseline_bwb_25.yaml</code>, click Run.</p>')
        _sec("Step 2 — Single aero case")
        _h('<p>Go to <b>Aero Analysis → Single run</b>, set alpha=4°, velocity=28 m/s, altitude=1500 m, click Run. Expected: CL≈0.42, CD≈0.034.</p>')
        _sec("Step 3 — Aero sweep")
        _h('<p>Go to <b>Aero Analysis → Sweep</b>, set alpha=-4,-2,0,2,4,6,8,10 and control=-10,-5,0,5,10. Click Run. Expected: 80 cases, 9 of 9 success.</p>')
        _note("Expected output path: <code>data/runs/&lt;sweep_run_id&gt;/aero_sweep_manifest.json</code>","ok")
    elif "2" in ex:
        _note("Goal: generate a 50-geometry LHS dataset with AVL sweeps, curate, and promote it.","info")
        steps=[("Dataset Factory → Aero dataset tab","Set N=50, sampler=lhs_v1, seed=123, alpha=-4,-2,0,2,4,6,8,10, control=-10,-5,0,5,10, QC preset=production"),("Dataset Factory → Curate/Promote → curate-aero","Curation filters incomplete groups, nonfinite CL/CD, failed diagnostics"),("Dataset Factory → Curate/Promote → promote-aero","Writes promotion_manifest.json — required before ML training"),("ML Studio → Schema tab","Verify bwb_control preset columns exist in the promoted dataset")]
        for i,(action,detail) in enumerate(steps,1):
            _h(f'<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:.9rem 1.1rem;margin-bottom:.6rem"><div style="font-size:.78rem;font-weight:600;color:#F2F5F8;margin-bottom:3px">Step {i} — {action}</div><div style="font-size:.76rem;color:#AAB6C2;line-height:1.6">{detail}</div></div>')
    elif "3" in ex:
        _note("Goal: run a parametric sweep on geometry geom_00001 from an existing dataset.","info")
        _h('<p>1. Go to <b>Aero Analysis → Sweep</b>.<br>2. Set source = Dataset, pick your dataset, geometry ID = <code>geom_00001</code>.<br>3. Set alpha=-2,0,2,4,6, control=-5,0,5, velocity=28, altitude=1500.<br>4. Click Run. Saves to <code>data/runs/&lt;sweep_dir&gt;/</code>.</p>')
    elif "4" in ex:
        _note("Full campaign: ~30 minutes for 50 geometries on a modern laptop.","info")
        steps=[("Dataset Factory → Unified aero dataset","N=50, lhs_v1, seed=123, name=my_dataset_v1, alpha=-4,-2,0,2,4,6,8,10, beta=0, velocity=28, altitude=0,1500, control=-10,-5,0,5,10, QC preset=production"),("Dataset Factory → Inspect/QC → aero QC strict","Verify no critical failures after generation"),("Dataset Factory → Curate/Promote → curate-aero","Review curation_report.json output — check rejection rate"),("Dataset Factory → Curate/Promote → promote-aero","Promote only if rejection rate < 5%"),("ML Studio → Train","Model type=hist_gradient_boosting, feature preset=bwb_control, targets=cl,cd,cm"),("ML Studio → Compare → seed stability","Seeds=101,202,303,404,505 — verify winner is consistent before claiming R²")]
        for i,(action,detail) in enumerate(steps,1):
            _h(f'<div style="background:#202B36;border:1px solid #334252;border-radius:9px;padding:.9rem 1.1rem;margin-bottom:.6rem"><div style="font-size:.78rem;font-weight:600;color:#F2F5F8;margin-bottom:3px">Step {i} — {action}</div><div style="font-size:.76rem;color:#AAB6C2;line-height:1.6">{detail}</div></div>')
    elif "5" in ex:
        _note("Goal: compare all tree and linear models on the same split to find the best surrogate.","info")
        _h('<p>1. ML Studio → Compare tab<br>2. Select your promoted dataset<br>3. Select all models: <code>linear_regression, ridge, random_forest, extra_trees, gradient_boosting, hist_gradient_boosting</code><br>4. Split method = grouped, group column = geometry_id<br>5. Click Run — comparison_summary.csv ranks by test RMSE<br><br><b>Rule:</b> never call a model "winner" from a single split. Always follow with seed stability (seeds=101,202,303,404,505).</p>')
    else:
        _note("Goal: promote the best model and use it for fast prediction.","info")
        _h('<p>1. ML Studio → Trust gates → promote-model<br>2. Set max-test-rmse-mean and min-test-r2-mean thresholds<br>3. ML Studio → Trust gates → require-promoted-model (verify)<br>4. ML Studio → Predict tab<br>5. Upload input CSV with feature columns, click Run<br>6. Output: <code>predictions.csv</code> with predicted CL, CD, Cm</p>')


def pg_geometry(root,exe,tmo,dry):
    _hero("△","Geometry","bwb_segmented_v1 · 17 design variables")
    tab1,tab2,tab3=st.tabs(["  Generate  ","  Visualize  ","  System info  "])

    with tab1:
        # ── aeris geometry generate only accepts: --config / -c ──────────────
        # Options --output-name, --save-plot, --build-aerosandbox do NOT exist
        # on geometry generate. They exist only on dataset generate and
        # geometry visualize. Do NOT add them here.
        _note(
            "Runs <code>aeris geometry generate --config &lt;file&gt;</code>. "
            "Plot-saving and AeroSandbox behavior are controlled by the YAML config "
            "<code>outputs:</code> section — edit there if needed. "
            "After generation the run folder appears under <code>data/runs/</code>.",
            "info",
        )
        mode=st.radio("Config source",["Use existing YAML file","Build config interactively (no file needed)"],horizontal=True,key="gm_mode")
        if mode.startswith("Use existing"):
            _sec("YAML file selection")
            config=_pick_file("Config file",root/"configs"/"geometry","*.yaml","g_cfg",default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
        else:
            _sec("Interactive YAML builder")
            yaml_str=_yaml_geometry_builder("gb")
            with st.expander("Preview generated YAML",expanded=False): st.code(yaml_str,language="yaml")
            save_path=st.text_input("Save YAML to path",value=str(root/"configs"/"geometry"/"gui_built.yaml"),key="gb_savepath")
            if st.button("Save YAML file",key="gb_save",type="secondary"):
                p=Path(save_path); p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(yaml_str,encoding="utf-8"); st.success(f"Saved: {p}")
            config=save_path
        extra=st.text_input("Extra CLI arguments","",key="g_ex",help="Passed verbatim after --config. Leave blank for a standard run.")
        # Build correct args — only --config is valid here
        args=["geometry","generate","--config",config]
        args+=_xargs(extra)
        _panel("Generate one geometry","Runs aeris geometry generate. Output lands in data/runs/<timestamp>_geometry_<name>/",args,root,exe,tmo,dry,"g_run")

    with tab2:
        # ── aeris geometry visualize accepts: --config/-c (required),
        #    --seed, --save-plot/--no-save-plot, --build-aerosandbox/--no-build-aerosandbox,
        #    --output-dir, --show-plot/--no-show-plot, --draw-3d/--no-draw-3d
        # It does NOT accept --run-dir, --dataset, --geometry-id, --case-dir.
        _note(
            "Runs <code>aeris geometry visualize --config &lt;file&gt;</code>. "
            "The command samples <b>one geometry from the config</b> (use Seed to reproduce a specific design). "
            "To inspect an already-generated run, pick <b>Output directory</b> below — "
            "this maps to <code>--output-dir</code> and saves the visualization there. "
            "The 3D viewer opens in a separate window via AeroSandbox; "
            "disable it for headless / server environments.",
            "info",
        )
        _sec("Config file")
        vcfg=_pick_file("Geometry config",root/"configs"/"geometry","*.yaml","gv_cfg",default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))

        _sec("Options")
        c1,c2=st.columns(2)
        seed_ov=c1.text_input("Seed override","",key="gv_seed",help="Integer seed. Leave blank to use config default. Use the same seed as a generate run to reproduce that exact geometry.")
        # Output dir: let user optionally pick a recent run folder
        runs_dirs=_dirs(str(root/"data"/"runs"))
        out_dir_opts=["(auto — timestamped debug folder)"]+runs_dirs
        out_dir_sel=c2.selectbox("Output directory (optional)",out_dir_opts,index=0,key="gv_od_sel",help="Leave on auto or select an existing run folder to save the plot there.")
        out_dir="" if out_dir_sel.startswith("(auto") else out_dir_sel
        out_dir=st.text_input("Manual output-dir override",value=out_dir,key="gv_od_m",help="Maps to --output-dir. Leave blank for automatic debug subfolder.")

        c3,c4,c5=st.columns(3)
        draw3d=c3.checkbox("Open 3D viewer (AeroSandbox)",True,key="gv_3d",help="Calls airplane.draw(). Needs a display — disable on headless servers.")
        show_pl=c4.checkbox("Show 2D plot window",False,key="gv_sh",help="Pops up the matplotlib window. Usually False on servers.")
        save_pl=c5.checkbox("Save planform plot",True,key="gv_spl",help="Maps to --save-plot / --no-save-plot")

        args=["geometry","visualize","--config",vcfg]
        _flag(args,"--seed",seed_ov)
        _flag(args,"--output-dir",out_dir)
        _bflag(args,"--save-plot","--no-save-plot",save_pl)
        _bflag(args,"--draw-3d","--no-draw-3d",draw3d)
        _bflag(args,"--show-plot","--no-show-plot",show_pl)
        _panel("Visualize geometry","Generates and visualizes one geometry from config. Saves plot to output-dir.",args,root,exe,tmo,dry,"gv_run")

    with tab3:
        _panel("Geometry system info","Lists registered generators, their IDs, and current status.",["geometry","info"],root,exe,tmo,dry,"gi_run")


def pg_dataset(root,exe,tmo,dry):
    _hero("▣","Dataset Factory","geometry → sweeps → qc → curate → promote","data pipeline")
    _pipeline([("geometry gen","done"),("aero sweeps","done"),("qc","done"),("curate","done"),("promote","active")])
    tab1,tab2,tab3,tab4,tab5,tab6=st.tabs(["  Aero Dataset  ","  Geometry Only  ","  Inspect / QC  ","  Curate / Promote  ","  Training Data  ","  Smoke Check  "])

    with tab1:
        mode2=st.radio("Config source",["Use existing YAML file","Build config interactively"],horizontal=True,key="ds_mode2")
        if mode2.startswith("Use existing"):
            _sec("Config file")
            config=_pick_file("Geometry config",root/"configs"/"geometry","*.yaml","ds_ac",default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
        else:
            _sec("Interactive YAML builder")
            yaml_str2=_yaml_geometry_builder("dsb")
            with st.expander("Preview YAML",expanded=False): st.code(yaml_str2,language="yaml")
            sp2=st.text_input("Save YAML to",str(root/"configs"/"geometry"/"gui_ds_config.yaml"),key="dsb_sp")
            if st.button("Save YAML",key="dsb_sv",type="secondary"):
                p=Path(sp2); p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(yaml_str2,encoding="utf-8"); st.success(f"Saved: {p}")
            config=sp2

        _sec("Sampling")
        c1,c2,c3,c4=st.columns(4)
        n=c1.number_input("N geometries",min_value=1,value=10,step=1,key="ds_n",help="Total geometries to generate")
        samp=c2.selectbox("Sampler",[f"{s} — {SAMPLER_LABELS[s].split(' — ')[0]}" for s in SAMPLERS],key="ds_samp")
        samp_id=samp.split(" — ")[0]
        seed=c3.number_input("Sampler seed",min_value=0,value=123,step=1,key="ds_seed",help="Same seed = reproducible dataset")
        name=c4.text_input("Dataset name","gui_aero_dataset",key="ds_name",help="Folder name under data/datasets/")

        _sec("Flight condition sweep")
        _note("All values are comma-separated. Control input = control-surface deflection [deg]. b_total_m is semi-span — full span = 2×.","info")
        c1,c2=st.columns(2)
        alpha=c1.text_input("Alpha values [deg]","-2,0,2,4,6",key="ds_al",help="Angle of attack sweep. e.g. -4,-2,0,2,4,6,8,10")
        beta=c2.text_input("Beta values [deg]","0",key="ds_be",help="Sideslip angle. Usually 0 for symmetric BWB.")
        c3,c4=st.columns(2)
        vel=c3.text_input("Velocity values [m/s]","28",key="ds_ve",help="Freestream velocity. Determines dynamic pressure.")
        alt=c4.text_input("Altitude values [m]","1500",key="ds_at",help="ISA altitude for density calculation.")
        ctrl=st.text_input("Control input values [deg]","-5,0,5",key="ds_ctrl",help="Elevon deflection. Positive = trailing edge down.")
        with st.expander("Angular rates (advanced — leave 0 for standard datasets)"):
            c5,c6,c7=st.columns(3)
            pv=c5.text_input("p values [rad/s]","0",key="ds_p",help="Body roll rate"); qv=c6.text_input("q values [rad/s]","0",key="ds_q",help="Body pitch rate"); rv=c7.text_input("r values [rad/s]","0",key="ds_r",help="Body yaw rate")
        est=int(n)*_est(alpha,beta,vel,alt,ctrl,pv,qv,rv)
        _note(f"Estimated aero cases: <b>{est:,}</b> ({int(n)} geometries × {est//max(int(n),1)} conditions each)","info")

        _sec("Solver & quality control")
        avl_cmd=st.text_input("AVL executable path","avl",key="ds_avlcmd",help="Path to AVL binary. 'avl' if on PATH.")
        c1,c2,c3=st.columns(3)
        qcp_label=c1.selectbox("QC preset",[f"{p} — {QC_PRESET_LABELS[p].split(' — ')[0]}" for p in QC_PRESETS],index=2,key="ds_qcp")
        qcp=qcp_label.split(" — ")[0]
        ret_label=c2.selectbox("Retain aero runs",[f"{r} — {RETENTION_LABELS[r].split(' — ')[0]}" for r in RETENTION],index=1,key="ds_ret")
        ret=ret_label.split(" — ")[0]
        tmo2=c3.number_input("Per-case timeout [s]",min_value=5,value=180,step=5,key="ds_tmo2",help="AVL timeout per flight condition case.")

        with st.expander("AVL paneling settings"):
            c4,c5,c6,c7=st.columns(4)
            sp=c4.number_input("Spanwise panels",min_value=1,value=4,step=1,key="ds_sp",help="4 is fast; 8 for production accuracy")
            cp=c5.number_input("Chordwise panels",min_value=1,value=8,step=1,key="ds_cp",help="8 is standard")
            sp_sp=c6.selectbox("Spanwise spacing",SPACING,key="ds_spsp",help="equal = uniform; cosine = denser near root")
            ch_sp=c7.selectbox("Chordwise spacing",["cosine","equal"],key="ds_chsp",help="cosine = denser at LE/TE")
            c8,c9=st.columns(2)
            save_sf=c8.checkbox("Save surface forces",False,key="ds_ssf",help="AVL surface force output files")
            save_ef=c9.checkbox("Save element forces",False,key="ds_sef",help="AVL element force output files")

        with st.expander("Dataset options"):
            c10,c11=st.columns(2)
            keep_geo=c10.checkbox("Keep geometry dataset after aero run",True,key="ds_kg",help="Uncheck to save disk space after large campaigns")
            max_cases=c11.text_input("Max cases per geometry (safety cap)","",key="ds_mc",help="Leave blank for no cap. Use e.g. 100 to prevent runaway sweeps.")

        args=["dataset","aero-generate","--config",config,"--n",str(int(n)),"--sampler",samp_id,"--sampler-seed",str(int(seed)),"--name",name,"--alpha-values",alpha,"--beta-values",beta,"--velocity-values",vel,"--altitude-values",alt,"--control-input-values",ctrl,"--p-values",pv,"--q-values",qv,"--r-values",rv,"--solver","aerosandbox_avl","--avl-command",avl_cmd,"--timeout-sec",str(int(tmo2)),"--spanwise-resolution",str(int(sp)),"--chordwise-resolution",str(int(cp)),"--spanwise-spacing",sp_sp,"--chordwise-spacing",ch_sp,"--retain-aero-runs",ret,"--qc-preset",qcp]
        _bflag(args,"--save-surface-forces",None,save_sf or None)
        _bflag(args,"--save-element-forces",None,save_ef or None)
        _bflag(args,"--keep-geometry-dataset","--delete-geometry-dataset",keep_geo)
        _flag(args,"--max-cases",max_cases if max_cases.strip() else None)
        _bflag(args,"--no-save-plot",None,True)
        _bflag(args,"--build-aerosandbox",None,True)
        _panel("Generate unified aero dataset","One command: geometry sampling → AVL sweeps → QC → manifest. The full data generation pipeline.",args,root,exe,tmo,dry,"ds_agen")

    with tab2:
        _sec("Config")
        config2=_pick_file("Geometry config",root/"configs"/"geometry","*.yaml","ds_gc2",default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
        c1,c2,c3=st.columns(3)
        n2=c1.number_input("N geometries",min_value=1,value=20,step=1,key="ds_gn2")
        smp2=c2.selectbox("Sampler",SAMPLERS,key="ds_gsmp2"); sd2=c3.number_input("Seed",min_value=0,value=123,step=1,key="ds_gsd2")
        nm2=st.text_input("Dataset name","gui_geometry_dataset",key="ds_gnm2")
        c4,c5=st.columns(2); sp2=c4.checkbox("Save plots",False,key="ds_gsp2"); ba2=c5.checkbox("Build AeroSandbox",True,key="ds_gba2")
        with st.expander("QC on geometry dataset"):
            run_qc=st.checkbox("Run QC after generation",False,key="ds_grqc"); qcp2=st.selectbox("QC preset",QC_PRESETS,key="ds_gqcp2"); fail_qc=st.checkbox("Fail on QC error",False,key="ds_gfqc")
        args2=["dataset","generate","--config",config2,"--n",str(int(n2)),"--sampler",smp2,"--sampler-seed",str(int(sd2)),"--name",nm2]
        _bflag(args2,"--save-plot","--no-save-plot",sp2); _bflag(args2,"--build-aerosandbox","--no-build-aerosandbox",ba2)
        if run_qc: args2+=["--run-qc","--qc-preset",qcp2]; _bflag(args2,"--fail-on-qc-error","--allow-qc-errors",fail_qc)
        _panel("Generate geometry dataset","Many deterministic geometry cases with metadata rows.",args2,root,exe,tmo,dry,"ds_ggen2")

    with tab3:
        ds3=_pick_dir("Dataset root",root/"data"/"datasets","ds_qc3")
        act3=st.selectbox("Action",["inspect","geometry QC","aero QC"],key="ds_act3")
        if act3=="inspect": args3=["dataset","inspect","--dataset",ds3]
        elif act3=="geometry QC":
            prf3=st.selectbox("Profile",QC_PROFILES,key="ds_prf3"); args3=["dataset","qc","--dataset",ds3,"--profile",prf3]
        else:
            prf4=st.selectbox("Profile",QC_PROFILES,key="ds_prf4"); args3=["dataset","aero-qc","--dataset",ds3,"--profile",prf4]
        _panel("Inspect / QC dataset","Read artifacts and run quality checks without reprocessing data.",args3,root,exe,tmo,dry,"ds_iqc3")

    with tab4:
        _note("Promotion is a permanent trust stamp. Only promote datasets that passed QC and have a low rejection rate.","warn")
        ds4=_pick_dir("Aero dataset root",root/"data"/"datasets","ds_prm4")
        task4=st.selectbox("Task",["curate-aero","promote-aero","require-promoted-aero"],key="ds_task4")
        args4=["dataset",task4,"--dataset",ds4]
        if task4=="curate-aero":
            with st.expander("Curation options"):
                c1,c2=st.columns(2); c3,c4=st.columns(2)
                rej_inc=c1.checkbox("Reject incomplete groups",True,key="ds_ri",help="Geometries with fewer than expected cases")
                rej_fail=c2.checkbox("Reject groups with failures",True,key="ds_rf",help="Geometries that have any failed AVL case")
                rej_nf=c3.checkbox("Reject nonfinite targets",True,key="ds_rnf",help="Rows with NaN or Inf in CL/CD/Cm")
                rej_cd=c4.checkbox("Reject control diagnostic failures",True,key="ds_rcd",help="Geometries where AVL control surface diagnostics failed")
                _bflag(args4,"--reject-incomplete-groups","--keep-incomplete-groups",rej_inc)
                _bflag(args4,"--reject-groups-with-failures","--keep-groups-with-failures",rej_fail)
                _bflag(args4,"--reject-nonfinite-targets","--keep-nonfinite-targets",rej_nf)
                _bflag(args4,"--reject-control-diagnostic-failures","--keep-control-diagnostic-failures",rej_cd)
        if task4=="promote-aero":
            force4=st.checkbox("Force promotion (bypasses QC blockers)",False,key="ds_f4",help="Use only when deliberately accepting known issues. Document why.")
            if force4: _note("Force promotion bypasses all QC blockers. This is for smoke testing only — not for trusted ML.","warn")
            _bflag(args4,"--force",None,force4)
        if task4=="require-promoted-aero":
            af4=st.checkbox("Allow force-promoted datasets",False,key="ds_af4",help="Allow datasets that were force-promoted. Off = strict trust check.")
            _bflag(args4,"--allow-forced",None,af4)
        _panel(f"Trust chain: {task4}","Curate and promote only data suitable for downstream ML training.",args4,root,exe,tmo,dry,"ds_trust4",danger=(task4=="promote-aero"))

    with tab5:
        ds5=_pick_dir("Promoted dataset root",root/"data"/"datasets","ds_td5")
        c1,c2=st.columns(2); feat5=c1.text_input("Feature columns",DEFAULT_FEATURES,key="ds_feat5"); tgt5=c2.text_input("Target columns",DEFAULT_TARGETS,key="ds_tgt5")
        util5=st.selectbox("Utility",["training-data","split-training-data"],key="ds_util5")
        args5=["dataset",util5,"--dataset",ds5,"--features",feat5,"--targets",tgt5]
        if util5=="split-training-data":
            c3,c4,c5=st.columns(3); sm5=c3.selectbox("Split method",SPLIT_METHODS,key="ds_sm5"); gc5=c4.text_input("Group column","geometry_id",key="ds_gc5"); sd5=c5.number_input("Seed",min_value=0,value=123,step=1,key="ds_sd5")
            c6,c7,c8=st.columns(3); tr5=c6.slider("Train fraction",0.3,0.85,0.70,0.05,key="ds_tr5"); vl5=c7.slider("Val fraction",0.05,0.3,0.15,0.05,key="ds_vl5"); te5=c8.slider("Test fraction",0.05,0.3,0.15,0.05,key="ds_te5")
            args5+=["--method",sm5,"--group-column",gc5,"--random-seed",str(int(sd5)),"--train-fraction",str(tr5),"--val-fraction",str(vl5),"--test-fraction",str(te5)]
        _panel("Training data utility","Load or split training-ready data from a promoted dataset.",args5,root,exe,tmo,dry,"ds_td5r")

    with tab6:
        config6=_pick_file("Smoke config",root/"configs"/"geometry","*.yaml","ds_sm6",default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
        _panel("Run smoke pipeline","Minimal end-to-end sanity check: config → geometry → manifest. Use before any long campaign.",["pipeline","smoke","--config",config6],root,exe,tmo,dry,"ds_sm6r")


def pg_aero(root,exe,tmo,dry):
    _hero("⊿","Aero Analysis","aerosandbox_avl · AVL vortex-lattice","solver")
    tab1,tab2,tab3=st.tabs(["  Single run  ","  Sweep  ","  Inspect  "])

    def _aero_source(key):
        src=st.selectbox("Geometry source",["Config file","Latest run directory","Dataset geometry"],key=f"{key}_src")
        args=[]
        if src.startswith("Config"):
            cfg=_pick_file("Config",root/"configs"/"geometry","*.yaml",f"{key}_cfg",default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
            args+=["--config",cfg]
        elif src.startswith("Latest"):
            rd=_pick_dir("Run directory",root/"data"/"runs",f"{key}_rd"); args+=["--run-dir",rd]
        else:
            ds=_pick_dir("Dataset root",root/"data"/"datasets",f"{key}_ds"); gid=st.text_input("Geometry ID","geom_00000",key=f"{key}_gid",help="e.g. geom_00001 — from dataset metadata.csv")
            gen_id=st.text_input("Generator ID","bwb_segmented_v1",key=f"{key}_genid",help="Required for dataset/run-dir source modes. Default: bwb_segmented_v1")
            args+=["--dataset",ds,"--geometry-id",gid,"--generator-id",gen_id]
        return args

    def _avl_opts(key):
        avl=st.text_input("AVL executable","avl",key=f"{key}_avl",help="Path to AVL binary or 'avl' if on PATH")
        c1,c2,c3,c4=st.columns(4)
        sp=c1.number_input("Spanwise panels",1,value=4,step=1,key=f"{key}_sp"); cp=c2.number_input("Chordwise panels",1,value=8,step=1,key=f"{key}_cp")
        sp_sp=c3.selectbox("Spanwise spacing",SPACING,key=f"{key}_spsp"); ch_sp=c4.selectbox("Chordwise spacing",["cosine","equal"],key=f"{key}_chsp")
        t_=st.number_input("Solver timeout [s]",min_value=5,value=180,step=5,key=f"{key}_tmo")
        with st.expander("Advanced output options"):
            c5,c6=st.columns(2); ssf=c5.checkbox("Save surface forces",False,key=f"{key}_ssf"); sef=c6.checkbox("Save element forces",False,key=f"{key}_sef")
        extra_args=["--solver","aerosandbox_avl","--avl-command",avl,"--spanwise-resolution",str(int(sp)),"--chordwise-resolution",str(int(cp)),"--spanwise-spacing",sp_sp,"--chordwise-spacing",ch_sp,"--timeout-sec",str(int(t_))]
        _bflag(extra_args,"--save-surface-forces",None,ssf or None); _bflag(extra_args,"--save-element-forces",None,sef or None)
        return extra_args

    with tab1:
        src_args=_aero_source("ar")
        _sec("Flight condition")
        c1,c2,c3,c4=st.columns(4)
        al=c1.number_input("Alpha [deg]",value=4.0,step=0.5,key="ar_al",help="Angle of attack")
        be=c2.number_input("Beta [deg]",value=0.0,step=0.5,key="ar_be",help="Sideslip angle")
        ve=c3.number_input("Velocity [m/s]",value=28.0,step=1.0,key="ar_ve")
        at=c4.number_input("Altitude [m]",value=1500.0,step=100.0,key="ar_at")
        ctrl=st.slider("Control input [deg] (elevon deflection)",-15.0,15.0,0.0,0.5,key="ar_ctrl",help="Positive = trailing edge down (pitch-down tendency on BWB)")
        with st.expander("Angular rates (leave 0 for standard cases)"):
            c5,c6,c7=st.columns(3)
            pv=c5.number_input("p [rad/s]",value=0.0,key="ar_p"); qv=c6.number_input("q [rad/s]",value=0.0,key="ar_q"); rv=c7.number_input("r [rad/s]",value=0.0,key="ar_r")
        out_n=st.text_input("Output name (optional)","",key="ar_on",help="Suffix for the run folder name")
        avl_args=_avl_opts("ar")
        args=["aero","run"]+src_args+["--alpha",str(al),"--beta",str(be),"--velocity",str(ve),"--altitude",str(at),"--control-input-deg",str(ctrl),"--p",str(pv),"--q",str(qv),"--r",str(rv)]+avl_args
        _flag(args,"--output-name",out_n)
        _panel("Run single aero case","One geometry, one flight condition. Full AVL evaluation with result artifacts.",args,root,exe,tmo,dry,"ar_run")

    with tab2:
        src_args2=_aero_source("sw")
        _sec("Sweep definition")
        c1,c2=st.columns(2); al2=c1.text_input("Alpha values [deg]","-2,0,2,4,6",key="sw_al",help="e.g. -4,-2,0,2,4,6,8,10"); be2=c2.text_input("Beta values [deg]","0",key="sw_be")
        c3,c4=st.columns(2); ve2=c3.text_input("Velocity values [m/s]","28",key="sw_ve"); at2=c4.text_input("Altitude values [m]","1500",key="sw_at")
        ctrl2=st.text_input("Control input values [deg]","-5,0,5",key="sw_ctrl",help="Comma-separated elevon deflection values")
        with st.expander("Angular rate sweeps (leave 0 for standard)"):
            c5,c6,c7=st.columns(3); pv2=c5.text_input("p [rad/s]","0",key="sw_p"); qv2=c6.text_input("q [rad/s]","0",key="sw_q"); rv2=c7.text_input("r [rad/s]","0",key="sw_r")
        est2=_est(al2,be2,ve2,at2,ctrl2,pv2,qv2,rv2)
        _note(f"Estimated cases for this geometry: <b>{est2:,}</b>","info")
        max_c2=st.text_input("Max cases cap","",key="sw_mc",help="Safety limit on total expanded cases. Leave blank for no cap.")
        avl_args2=_avl_opts("sw")
        out_n2=st.text_input("Output name (optional)","",key="sw_on")
        args2=["aero","sweep"]+src_args2+["--alpha-values",al2,"--beta-values",be2,"--velocity-values",ve2,"--altitude-values",at2,"--control-input-values",ctrl2,"--p-values",pv2,"--q-values",qv2,"--r-values",rv2]+avl_args2
        _flag(args2,"--output-name",out_n2); _flag(args2,"--max-cases",max_c2 if max_c2.strip() else None)
        _panel("Run aero sweep","Multiple flight conditions on one geometry. Writes per-case result files and a sweep manifest.",args2,root,exe,tmo,dry,"sw_run")

    with tab3:
        rd3=_pick_dir("Aero run or sweep directory",root/"data"/"runs","ai_rd")
        it3=st.selectbox("Inspect type",["Single aero run","Sweep summary","Specific sweep case"],key="ai_it")
        if it3.startswith("Single"): args3=["aero","inspect","--run-dir",rd3]
        elif it3.startswith("Sweep s"): args3=["aero","sweep-inspect","--run-dir",rd3]
        else:
            c1,c2=st.columns(2); cl3=c1.text_input("Case label (exact)","",key="ai_cl"); ci3=c2.text_input("Case index","",key="ai_ci",help="Zero-based index. Use label OR index, not both.")
            args3=["aero","sweep-case-inspect","--run-dir",rd3]
            _flag(args3,"--case-label",cl3 if cl3.strip() else None); _flag(args3,"--case-index",ci3 if ci3.strip() else None)
        _panel("Inspect aero result","Read saved result artifacts without re-running the solver.",args3,root,exe,tmo,dry,"ai_run")


def pg_dynamics(root,exe,tmo,dry):
    _hero("◎","Dynamics","mass · CG · trim · static margin","diagnostic")
    _note("Current trim is first-order diagnostic only — not full nonlinear control-surface trim. Use for CG placement and static margin estimates.","info")
    act=st.radio("Workflow",["Build","Inspect","CG sweep","Trim"],horizontal=True,key="dyn_act")
    rd=_pick_dir("Aero run directory",root/"data"/"runs",f"dyn_{act}_rd")
    if act=="Build":
        mc=_pick_file("Mass config",root/"configs"/"mass","*.yaml","dyn_mc",default=str(root/"configs"/"mass"/"baseline_uav.yaml"))
        args=["dynamics","build","--run-dir",rd,"--mass-config",mc]
    elif act=="Inspect": args=["dynamics","inspect","--run-dir",rd]
    elif act=="Trim": args=["dynamics","trim","--run-dir",rd]
    else:
        c1,c2,c3=st.columns(3); cgmn=c1.number_input("CG min x [m]",value=0.30,step=0.01); cgmx=c2.number_input("CG max x [m]",value=0.70,step=0.01); ns=c3.number_input("Samples",min_value=2,value=21,step=1)
        args=["dynamics","cg-sweep","--run-dir",rd,"--cg-min-m",str(cgmn),"--cg-max-m",str(cgmx),"--n",str(int(ns))]
    _panel(f"Dynamics: {act}","Creates or inspects dynamics foundation artifacts linked to aero outputs.",args,root,exe,tmo,dry,f"dyn_{act}")


def pg_ml(root,exe,tmo,dry):
    _hero("◈","ML Studio","tabular surrogate · grouped split · trust gates","benchmark_aero_v1")
    # R² note shown only in Compare tab where it's relevant
    tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs(["  Schema  ","  Train  ","  Tune  ","  Compare  ","  Trust gates  ","  Predict  ","  EDA  "])

    def _ds_feat(key):
        ds=_pick_dir("Promoted dataset",root/"data"/"datasets",f"{key}_ds")
        use_preset=st.checkbox("Use named feature preset",True,key=f"{key}_up",help="bwb_control includes control_input_deg; bwb_basic does not")
        if use_preset:
            preset=st.selectbox("Feature preset",["bwb_control","bwb_basic"],key=f"{key}_fp"); fa=["--feature-preset",preset]
        else:
            feats=st.text_input("Feature columns",DEFAULT_FEATURES,key=f"{key}_ff",help="Comma-separated column names from the promoted CSV"); fa=["--features",feats]
        c1,c2=st.columns(2); tgt=c1.text_input("Target columns",DEFAULT_TARGETS,key=f"{key}_tgt",help="cl,cd,cm are the standard aero targets")
        allow_forced=c2.checkbox("Allow force-promoted dataset",False,key=f"{key}_af",help="Only for smoke testing — not for trusted ML results")
        return ds,fa,tgt,allow_forced

    def _split_opts(key):
        c1,c2,c3=st.columns(3)
        sm=c1.selectbox("Split method",SPLIT_METHODS,key=f"{key}_sm",help="grouped = no geometry leakage between train/val/test. ALWAYS use grouped.")
        gc=c2.text_input("Group column","geometry_id",key=f"{key}_gc")
        sd=c3.number_input("Seed",min_value=0,value=123,step=1,key=f"{key}_sd")
        c4,c5,c6=st.columns(3)
        tr=c4.slider("Train fraction",0.3,0.85,0.70,0.05,key=f"{key}_tr"); vl=c5.slider("Val fraction",0.05,0.3,0.15,0.05,key=f"{key}_vl"); te=c6.slider("Test fraction",0.05,0.3,0.15,0.05,key=f"{key}_te")
        return sm,gc,int(sd),tr,vl,te

    with tab1:
        ds,fa,tgt,af=_ds_feat("sc")
        gc_sc=st.text_input("Group column","geometry_id",key="sc_gc"); args=["ml","validate-schema","--dataset",ds,*fa,"--targets",tgt,"--group-column",gc_sc]
        _bflag(args,"--allow-forced",None,af)
        _panel("Validate ML schema","Checks columns, dtypes, group structure, and promotion status.",args,root,exe,tmo,dry,"sc_run")

    with tab2:
        ds,fa,tgt,af=_ds_feat("tr")
        sm,gc,sd,tr,vl,te=_split_opts("tr")
        c1,c2=st.columns(2)
        mt=c1.selectbox("Model type",[f"{m} — {MODEL_LABELS[m].split(' — ')[0]}" for m in MODEL_TYPES],index=6,key="tr_mt"); mt_id=mt.split(" — ")[0]
        od=c2.text_input("Output directory",str(root/"data"/"processed"/"ml_runs"/"gui_train"),key="tr_od")
        with st.expander("Model hyperparameters (JSON, optional)"):
            _note("Override default model parameters. Leave empty for defaults. Example: {\"n_estimators\": 500, \"max_depth\": 5}","info")
            mp_json=st.text_area("Model params JSON","",key="tr_mpj",height=80)
        mp_path=""
        if mp_json.strip():
            mp_path=str(root/"configs"/"ml"/"gui_model_params.json")
            p=Path(mp_path); p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(mp_json,encoding="utf-8")
        args=["ml","train","--dataset",ds,*fa,"--targets",tgt,"--model-type",mt_id,"--split-method",sm,"--group-column",gc,"--random-seed",str(sd),"--train-fraction",str(tr),"--val-fraction",str(vl),"--test-fraction",str(te),"--output-dir",od]
        _flag(args,"--model-params-json",mp_path if mp_path else None)
        _bflag(args,"--allow-forced",None,af)
        _panel("Train scalar ML model","Trains a tabular surrogate from the promoted dataset.",args,root,exe,tmo,dry,"tr_run")

    with tab3:
        ds,fa,tgt,af=_ds_feat("tu")
        sm,gc,sd,tr,vl,te=_split_opts("tu")
        c1,c2=st.columns(2)
        bk=c1.selectbox("Tuning backend",["aeris — deterministic grid/random search","optuna — Bayesian optimization (TPE)"],key="tu_bk"); bk_id="aeris" if bk.startswith("aeris") else "optuna"
        mt2=c2.selectbox("Model type",[f"{m} — {MODEL_LABELS[m].split(' — ')[0]}" for m in MODEL_TYPES],index=4,key="tu_mt"); mt2_id=mt2.split(" — ")[0]
        _sec("Parameter space JSON")
        _note("Define the hyperparameter search space. Each key maps to a list of values (grid) or a dict with type/low/high for Optuna.","info")
        default_ps='{\n  "n_estimators": [100, 300, 500],\n  "max_depth": [3, 5, 8]\n}' if bk_id=="aeris" else '{\n  "n_estimators": {"type": "int", "low": 100, "high": 600},\n  "max_depth": {"type": "int", "low": 3, "high": 10}\n}'
        ps_json=st.text_area("Parameter space JSON",default_ps,key="tu_psj",height=120)
        ps_path=str(root/"configs"/"ml"/"gui_tune_space.json")
        if ps_json.strip():
            p=Path(ps_path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(ps_json,encoding="utf-8")
        c3,c4=st.columns(2)
        n_tri=c3.number_input("Max trials / n_trials",min_value=1,value=20,step=1,key="tu_nt"); od2=c4.text_input("Output dir",str(root/"data"/"processed"/"ml_runs"/"gui_tune"),key="tu_od")
        with st.expander("Advanced tuning options"):
            c5,c6,c7=st.columns(3)
            strat=c5.selectbox("Strategy (aeris backend)",["grid","random"],key="tu_str"); met=c6.text_input("Selection metric","val.rmse_mean",key="tu_met",help="val.rmse_mean or val.r2_mean"); od_optuna=c7.text_input("Optuna storage URL","",key="tu_stor",help="e.g. sqlite:///data/optuna.db for persistent study")
        args=["ml","tune","--backend",bk_id,"--dataset",ds,*fa,"--targets",tgt,"--model-type",mt2_id,"--param-space-json",ps_path,"--n-trials",str(int(n_tri)),"--split-method",sm,"--group-column",gc,"--random-seed",str(sd),"--train-fraction",str(tr),"--val-fraction",str(vl),"--test-fraction",str(te),"--selection-metric",met,"--output-dir",od2]
        if bk_id=="aeris": args+=["--strategy",strat]
        _flag(args,"--storage",od_optuna if od_optuna.strip() else None)
        _bflag(args,"--allow-forced",None,af)
        _panel("Tune ML model","Hyperparameter search. Saves all trials for comparison.",args,root,exe,tmo,dry,"tu_run")

    with tab4:
        ds,fa,tgt,af=_ds_feat("cm")
        sm,gc,sd,tr,vl,te=_split_opts("cm")
        models=st.multiselect("Models to compare",MODEL_TYPES,default=["linear_regression","ridge","random_forest","gradient_boosting","extra_trees","hist_gradient_boosting"],key="cm_mods",help="All selected models run on the same identical split for fair comparison")
        ct=st.radio("Comparison type",["Single split","Seed stability (≥5 seeds — required before claiming winner)"],horizontal=True,key="cm_ct")
        if ct.startswith("Single"):
            _note("Single split results can be misleading. Always follow up with seed stability before claiming a winner.","warn")
        od3=st.text_input("Output directory",str(root/"data"/"processed"/"ml_runs"/"gui_compare"),key="cm_od")
        with st.expander("Per-model hyperparameter overrides (optional)"):
            _note("JSON mapping of model_type → constructor parameters. e.g. {\"random_forest\": {\"n_estimators\": 500}}","info")
            mp2_json=st.text_area("Model params by type JSON","",key="cm_mp2j",height=80)
        mp2_path=""
        if mp2_json.strip():
            mp2_path=str(root/"configs"/"ml"/"gui_compare_params.json")
            p=Path(mp2_path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(mp2_json,encoding="utf-8")
        if ct.startswith("Single"):
            args=["ml","compare","--dataset",ds,*fa,"--targets",tgt,"--models",",".join(models),"--split-method",sm,"--group-column",gc,"--random-seed",str(sd),"--train-fraction",str(tr),"--val-fraction",str(vl),"--test-fraction",str(te),"--output-dir",od3]
        else:
            seeds_str=st.text_input("Seeds (comma-separated)","101,202,303,404,505",key="cm_seeds",help="Use ≥5 seeds. The winner must be consistent across all seeds.")
            args=["ml","compare-seeds","--dataset",ds,*fa,"--targets",tgt,"--models",",".join(models),"--seeds",seeds_str,"--split-method",sm,"--group-column",gc,"--train-fraction",str(tr),"--val-fraction",str(vl),"--test-fraction",str(te),"--output-dir",od3]
        _flag(args,"--model-params-json",mp2_path if mp2_path else None)
        _bflag(args,"--allow-forced",None,af)
        _panel("Compare ML models","All models run on identical splits. Seed stability reveals true consistent winners.",args,root,exe,tmo,dry,"cm_run")

    with tab5:
        mr=_pick_dir("Model run directory",root/"data"/"processed"/"ml_runs","mt_mr")
        tt=st.selectbox("Task",["inspect-model","promote-model","require-promoted-model","check-inference-inputs","audit-model"],key="mt_task")
        args=["ml",tt,"--model-run-dir",mr]
        if tt=="promote-model":
            _note("Set thresholds appropriate for your use case. A surrogate for preliminary design can tolerate higher RMSE than one for certification.","info")
            c1,c2=st.columns(2); rmse=c1.number_input("Max test RMSE mean",value=0.05,format="%.6f",key="mt_rmse",help="Test set RMSE must be below this"); r2=c2.number_input("Min test R² mean",value=0.95,format="%.4f",key="mt_r2",help="Test set R² must be above this")
            notes=st.text_input("Promotion notes","",key="mt_notes",help="Recorded in the promotion manifest for audit trail")
            c3,c4=st.columns(2); req_diag=c3.checkbox("Require diagnostics artifacts",True,key="mt_rd"); af_ds=c4.checkbox("Allow force-promoted dataset",False,key="mt_afds")
            args+=["--max-test-rmse-mean",str(rmse),"--min-test-r2-mean",str(r2)]
            _flag(args,"--notes",notes if notes.strip() else None)
            _bflag(args,"--require-diagnostics","--no-require-diagnostics",req_diag)
            _bflag(args,"--allow-forced-dataset",None,af_ds)
        if tt=="require-promoted-model":
            vh=st.checkbox("Verify artifact hashes",True,key="mt_vh",help="Checks that model files haven't changed since promotion"); _bflag(args,"--verify-hashes","--no-verify-hashes",vh)
        if tt=="check-inference-inputs":
            ic=st.text_input("Input CSV",str(Path(mr)/"train_rows.csv" if mr else ""),key="mt_ic"); od4=st.text_input("Output dir","",key="mt_od4")
            c1,c2,c3=st.columns(3); rp=c1.checkbox("Require promoted model",True,key="mt_rp"); fv=c2.checkbox("Fail on violations",False,key="mt_fv"); tol=c3.number_input("Envelope tolerance",0.0,key="mt_tol",format="%.4f",help="Absolute tolerance applied to min/max envelope checks")
            args+=["--input-csv",ic]; _flag(args,"--output-dir",od4 if od4.strip() else None)
            _bflag(args,"--require-promoted-model","--no-require-promoted-model",rp); _bflag(args,"--fail-on-violations","--no-fail-on-violations",fv); args+=["--tolerance",str(tol)]
        if tt=="audit-model":
            c1,c2=st.columns(2); max_rmse2=c1.number_input("Max test RMSE (optional)",value=0.0,format="%.6f",key="mt_ar"); min_r22=c2.number_input("Min test R² (optional)",value=0.0,format="%.4f",key="mt_ar2"); fail_gate=st.checkbox("Fail on quality gate",False,key="mt_fg")
            if max_rmse2>0: args+=["--max-test-rmse-mean",str(max_rmse2)]
            if min_r22>0: args+=["--min-test-r2-mean",str(min_r22)]
            _bflag(args,"--fail-on-quality-gate","--no-fail-on-quality-gate",fail_gate)
        _panel(f"Model trust gate: {tt}","Inspect, promote, verify, or audit a trained model.",args,root,exe,tmo,dry,"mt_run",danger=(tt=="promote-model"))

    with tab6:
        mr2=_pick_dir("Model run directory",root/"data"/"processed"/"ml_runs","pr_mr"); ic2=st.text_input("Input CSV",str(Path(mr2)/"train_rows.csv" if mr2 else ""),key="pr_ic")
        od5=st.text_input("Output directory",str(Path(mr2)/"inference"/"gui_predict" if mr2 else ""),key="pr_od")
        c1,c2,c3=st.columns(3); rp2=c1.checkbox("Require promoted model",True,key="pr_rp"); ee=c2.checkbox("Enforce training envelope",True,key="pr_ee"); it=c3.checkbox("Include truth if available",True,key="pr_it",help="If target columns exist in input CSV, compute error metrics")
        tol2=st.number_input("Envelope tolerance",0.0,key="pr_tol",format="%.4f",help="Rows outside envelope±tolerance are flagged")
        _note("Prediction is guarded: envelope violations are flagged and optionally blocked. This prevents silent extrapolation.","info")
        args=["ml","predict","--model-run-dir",mr2,"--input-csv",ic2,"--output-dir",od5,"--envelope-tolerance",str(tol2)]
        _bflag(args,"--require-promoted-model",None,rp2); _bflag(args,"--enforce-envelope",None,ee); _bflag(args,"--include-truth-if-available","--no-include-truth-if-available",it)
        _panel("Guarded prediction","Predicts CL/CD/Cm. Flags out-of-envelope inputs. Computes error if truth available.",args,root,exe,tmo,dry,"pr_run")

    with tab7:
        _sec("EDA — run before training on any new dataset")
        _note("EDA checks for constant columns, outliers, coverage gaps, collinearity, and nonlinearity. Run it every time before a new training cycle.","info")
        ds_eda=_pick_dir("Promoted dataset",root/"data"/"datasets","eda_ds")
        c1,c2=st.columns(2); feat_eda=c1.text_input("Feature columns",DEFAULT_FEATURES,key="eda_feat"); tgt_eda=c2.text_input("Target columns",DEFAULT_TARGETS,key="eda_tgt")
        _note("EDA is available via Python API: <code>from aeris.ml.eda import run_eda</code>. CLI command coming in a future release.","info")
        with st.expander("Python snippet"):
            st.code(f"""from pathlib import Path
import pandas as pd
from aeris.ml.eda import run_eda

df = pd.read_csv("{ds_eda}/curated_aero_dataset.csv")
report = run_eda(
    df,
    feature_columns=[{', '.join(repr(c) for c in feat_eda.split(','))}],
    target_columns=[{', '.join(repr(c) for c in tgt_eda.split(','))}],
    output_path=Path("{ds_eda}/eda_report.json"),
)
print("Constant columns:", report["constant_columns"]["constant_columns"])
print("Outlier columns:", report["outliers"]["columns_with_outliers"])
print("Geometry coverage uniform:", report["per_geometry_coverage"]["uniform_coverage"])
""",language="python")


def pg_multifid(root,exe,tmo,dry):
    _hero("⊞","Multifidelity","LF → delta correction → HF-like output","AVL+XFOIL/CFD")
    _note("⚠ Requires real HF data (XFOIL or CFD). Missing currently: Reynolds number features, convergence flags, Co-Kriging baseline. Do not claim paper-level results from AVL-only delta.","warn")
    tab1,tab2,tab3,tab4=st.tabs(["  Build delta  ","  Train delta  ","  Predict  ","  Evaluate  "])
    with tab1:
        c1,c2=st.columns(2); lf=c1.text_input("Low-fidelity CSV (AVL)",str(root/"data"/"processed"/"multifidelity"/"lf.csv"),key="mf_lf"); hf=c2.text_input("High-fidelity CSV",str(root/"data"/"processed"/"multifidelity"/"hf.csv"),key="mf_hf")
        pk=st.text_input("Pair keys",DEFAULT_PAIR_KEYS,key="mf_pk",help="Columns used to match LF and HF rows. Must be unique identifiers.")
        tg=st.text_input("Base targets",DEFAULT_TARGETS,key="mf_tg",help="delta__cl = hf__cl - lf__cl will be computed for each target")
        od=st.text_input("Output dir",str(root/"data"/"processed"/"multifidelity"/"gui_delta"),key="mf_od")
        _note("delta__target = hf__target − lf__target. Unmatched rows are reported in the delta report but excluded from training.","info")
        _panel("Build delta dataset","Pairs LF/HF rows strictly by pair_keys. Writes delta_dataset.csv + traceability report.",["ml","build-delta-dataset","--lf-csv",lf,"--hf-csv",hf,"--pair-keys",pk,"--targets",tg,"--output-dir",od],root,exe,tmo,dry,"mf_bld")
    with tab2:
        dd=_pick_dir("Delta dataset dir",root/"data"/"processed"/"multifidelity","mf_dd")
        ft=st.text_input("Features (include lf__ output columns)","c1_m,alpha_deg,velocity_mps,altitude_m,control_input_deg,lf__cl,lf__cd,lf__cm",key="mf_ft",help="Include LF outputs as features — they are the main correction signal")
        c1,c2=st.columns(2); tg2=c1.text_input("Base targets",DEFAULT_TARGETS,key="mf_tg2"); mt=c2.selectbox("Model type",MODEL_TYPES,index=4,key="mf_mt")
        sm = "grouped"
        gc = "geometry_id"
        sd,tr,vl,te = 123,0.7,0.15,0.15
        od2=st.text_input("Output dir",str(root/"data"/"processed"/"ml_runs"/"gui_delta_model"),key="mf_od2")
        _panel("Train delta model","Learns the HF−LF correction from design and LF-output features.",["ml","train-delta-model","--delta-dataset",dd,"--features",ft,"--base-targets",tg2,"--model-type",mt,"--split-method","grouped","--group-column","geometry_id","--output-dir",od2],root,exe,tmo,dry,"mf_tr")
    with tab3:
        mr=_pick_dir("Delta model run",root/"data"/"processed"/"ml_runs","mf_pr"); ic=st.text_input("Input CSV",str(Path(mr)/"test_rows.csv" if mr else ""),key="mf_ic"); od3=st.text_input("Output dir",str(Path(mr)/"delta_inference" if mr else ""),key="mf_od3")
        _panel("Predict with delta model","Output = LF_prediction + predicted_delta. Corrected HF-like scalars.",["ml","predict-delta-model","--model-run-dir",mr,"--input-csv",ic,"--output-dir",od3],root,exe,tmo,dry,"mf_pr")
    with tab4:
        mr2=_pick_dir("Delta model run",root/"data"/"processed"/"ml_runs","mf_ev"); od4=st.text_input("Output dir",str(Path(mr2)/"mf_eval" if mr2 else ""),key="mf_od4")
        _note("Evaluation compares LF baseline error against corrected error. A good delta model improves RMSE across all targets.","info")
        _panel("Evaluate delta model","Compare LF baseline vs corrected prediction error. Reports improved/worsened targets.",["ml","evaluate-delta-model","--model-run-dir",mr2,"--output-dir",od4],root,exe,tmo,dry,"mf_ev")


def pg_results(root):
    _hero("◫","Results Browser","inspect any artifact without digging through folders","browser")
    rc=st.selectbox("Artifact root",["runs","datasets","processed","debug","documents","custom"],key="rb_rc")
    rm={"runs":root/"data"/"runs","datasets":root/"data"/"datasets","processed":root/"data"/"processed","debug":root/"data"/"debug","documents":root/"documents"}
    r=Path(st.text_input("Custom root",str(root/"data"),key="rb_cr")).expanduser() if rc=="custom" else rm[rc]
    if not r.exists(): _note(f"Root does not exist: {r}","warn"); return
    cands=[str(r)]+_dirs(str(r))
    sel_root=Path(st.selectbox("Folder",cands[:200],format_func=lambda s: Path(s).name+("/" if Path(s)==r else ""),key="rb_sr"))
    files=sorted([p for p in sel_root.rglob("*") if p.is_file()])
    _stat_row([("Files",str(len(files)),"in selected folder"),("Folder",sel_root.name,"selected")])
    prev=[p for p in files if p.suffix.lower() in {".json",".csv",".png",".jpg",".jpeg",".webp",".txt",".log",".yaml",".yml",".md",".avl"}]
    if not prev: _note("No previewable files found in this folder.","info"); return
    sel=st.selectbox("Preview file",prev,format_func=lambda p:str(p.relative_to(sel_root)),key="rb_sel")
    _show_file(sel)


def pg_config(root):
    _hero("✎","Config Lab","YAML editor — always version-control your configs","editor")
    st.caption("Convenience editor. For production configs, use version control.")
    mode=st.radio("Mode",["Edit existing YAML file","Paste / write new YAML"],horizontal=True,key="cl_mode")
    if mode.startswith("Edit"):
        p_str=_pick_file("Config file",root/"configs","*.yaml","cl_f",default=str(root/"configs"/"geometry"/"baseline_bwb_25.yaml"))
        p=Path(p_str).expanduser()
        text=st.text_area("YAML content",value=_read(p) if p.exists() else "# new config\n",height=500,key="cl_text")
    else:
        p_str=st.text_input("Save path",str(root/"configs"/"geometry"/"new_config.yaml"),key="cl_sp")
        p=Path(p_str).expanduser()
        text=st.text_area("YAML content",value="name: my_config\n",height=500,key="cl_text2")
    c1,c2=st.columns(2)
    with c1:
        if st.button("✓ Validate YAML",type="primary",key="cl_val"):
            if yaml is None: st.error("PyYAML not installed.")
            else:
                try: d=yaml.safe_load(text); st.success("Valid YAML"); st.json(d)
                except Exception as e: st.error(f"Parse error: {e}")
    with c2:
        if st.button("Save to file",type="secondary",key="cl_save"):
            p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding="utf-8"); st.success(f"Saved: {p}")

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="AERIS", page_icon="✈️", layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS,unsafe_allow_html=True)
    root,exe,tmo,dry,page=_sidebar()
    dispatch={
        "home": pg_home,"examples": pg_examples,"geometry": pg_geometry,
        "dataset": pg_dataset,"aero": pg_aero,"dynamics": pg_dynamics,
        "ml": pg_ml,"multifid": pg_multifid,
        "results": lambda r,e,t,d: pg_results(r),
        "config":  lambda r,e,t,d: pg_config(r),
    }
    fn=dispatch.get(page)
    if fn: fn(root,exe,tmo,dry)

if __name__=="__main__":
    main()