"""CFD_Automation: load or create a wing, build its meshes, look at them.

    pip install streamlit plotly          # once, in the AERIS .venv (cfdauto installed: pip install -e CFD_Automation)
    streamlit run CFD_Automation/app/app.py

The builds are the stage code itself (Stage 1 geometry, Stage 2 surface mesh, Stage 3 volume mesh, rule set 2) with
their own checks. The hold-out sets are sealed and not offered.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core      # noqa: E402
import figures   # noqa: E402

st.set_page_config(page_title="CFD_Automation: wings and meshes", page_icon="✈", layout="wide")
PLOT = {"displaylogo": False, "scrollZoom": True}


def chart(fig):
    st.plotly_chart(fig, width="stretch", config=PLOT)


def table(rows, tall: bool = False):
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True, height=(35 * (len(df) + 1) + 3) if tall else "auto")


def tname(t: str) -> str:
    return core.TYPE_NAME[t]


# --- 1. the wing ------------------------------------------------------------------------------------------------

st.sidebar.title("Wings and meshes")
st.sidebar.header("1 · The wing")
mode = st.sidebar.radio("Start from", ["A set wing", "Create one", "A file"], key="mode")

wing = None
if mode == "A set wing":
    t = st.sidebar.selectbox("Wing type", core.TYPES, format_func=tname, key="set_type")
    s = st.sidebar.selectbox("Set", core.SETS, key="set_name",
                             help="reference: 5 per type; training_focus: realistic ranges; training_full: the whole "
                                  "space; corner1/corner2: the corners. The hold-out sets are sealed.")
    n = core.set_size(t, s)
    i = st.sidebar.number_input(f"Wing number (0 to {n - 1})", 0, n - 1, 0, key="set_index")
    wing = core.from_set(t, s, int(i))

elif mode == "Create one":
    t = st.sidebar.selectbox("Wing type", core.TYPES, format_func=tname, key="new_type")
    space = st.sidebar.radio("Ranges", ["focus", "full"], horizontal=True, key="new_space",
                             help="focus: where real UAV wings are; full: everything the generator supports")
    sp = core.spec(t, space)
    st.sidebar.caption(core.CHORD_LAW[sp.chord_law] + ". Lengths in mean chords.")

    def load_into_sliders(w: core.WingInput) -> None:
        for v in sp.free_variables:
            lo, hi = sp.ranges[v]
            st.session_state[f"{t}:{v}"] = float(min(max(w.vector[v], lo), hi))
        for k, name in enumerate(w.vector["airfoils"]):
            st.session_state[f"{t}:af{k}"] = name

    if st.sidebar.button("Middle of the ranges", width="stretch"):
        load_into_sliders(core.middle(t, space))
    with st.sidebar.expander("Start from a set wing"):
        fs = st.selectbox("Set", core.SETS, key="from_set")
        fi = st.number_input("Wing number", 0, core.set_size(t, fs) - 1, 0, key="from_index")
        if st.button("Copy it into the sliders", width="stretch"):
            w0 = core.from_set(t, fs, int(fi))
            out = core.in_space(w0, space)
            load_into_sliders(w0)
            if out:
                st.warning(f"Outside the {space} ranges, set to the nearest end: {', '.join(out)}")
    values = {}
    mid = core.middle(t, space).vector
    for v in sp.free_variables:
        lo, hi = sp.ranges[v]
        key = f"{t}:{v}"
        if key not in st.session_state:
            st.session_state[key] = float(mid[v])
        st.session_state[key] = float(min(max(st.session_state[key], lo), hi))
        values[v] = st.sidebar.slider(core.LABEL[v], float(lo), float(hi), key=key, step=(hi - lo) / 200 or 0.01,
                                      format="%.3f")
    st.sidebar.markdown("**Sections**")
    airfoils = []
    for k, sname in enumerate(core.station_names()):
        key = f"{t}:af{k}"
        if key not in st.session_state:
            st.session_state[key] = sp.choices[k][0]
        airfoils.append(st.sidebar.text_input(f"{sname} (suggested: {', '.join(sp.choices[k])})", key=key,
                                              help="any project section, AERIS database name or NACA 4/5-digit "
                                                   "(e.g. naca2412)"))
    try:
        wing = core.from_values(t, values, airfoils)
    except ValueError as e:
        st.error(str(e))
        st.stop()

else:
    t = st.sidebar.selectbox("Wing type (if the file does not say)", core.TYPES, format_func=tname, key="file_type")
    up = st.sidebar.file_uploader("A wing file (.json)", type=["json"],
                                  help="this app's own file (Files tab) or a Stage 1 vector.json")
    if up is None:
        st.title("Wings and meshes")
        st.info("Load a wing file in the sidebar, or start from a set wing.")
        st.stop()
    try:
        wing = core.from_json(up.getvalue().decode(), t, up.name)
    except ValueError as e:
        st.error(str(e))
        st.stop()

# --- 2. the mesh ------------------------------------------------------------------------------------------------

st.sidebar.header("2 · The mesh")
level = st.sidebar.radio("Level", core.LEVELS, horizontal=True, key="level",
                         help="VC: desktop; C: 2.2 × VC; M: about 10 M cells; F: about 21 M cells (rule set 2)")
re_pick = st.sidebar.selectbox("Re on the mean chord", list(core.RES) + ["other"], index=1, key="re_pick",
                               format_func=lambda r: r if r == "other" else f"{r:.0e}")
re = st.sidebar.number_input("Re", 1e4, 1e8, 3e5, format="%.3e", key="re_other") if re_pick == "other" else float(re_pick)
if level in ("M", "F"):
    st.sidebar.warning("M and F take minutes and several GB of RAM to build; VC takes seconds.")
b1, b2 = st.sidebar.columns(2)
want_surface = b1.button("Build surface", width="stretch", type="secondary")
want_volume = b2.button("Build volume", width="stretch", type="primary")


@st.cache_resource(max_entries=6, show_spinner=False)
def geometry(key: str, _w: core.WingInput):
    return core.build_geometry(_w)


@st.cache_resource(max_entries=4, show_spinner=False)
def surface(key: str, level: str, re: float, _g):
    return core.build_surface_mesh(_g, level, re)


@st.cache_resource(max_entries=2, show_spinner=False)
def volume(key: str, level: str, re: float, _sm):
    return core.build_volume_mesh(_sm)


with st.spinner("Building the wing (Stage 1)…"):
    g = geometry(wing.key(), wing)
mesh_key = (wing.key(), level, float(re))
if want_surface or want_volume:
    if not g.passed:
        st.sidebar.error("The wing was refused by Stage 1: no mesh.")
    else:
        with st.spinner(f"Building the surface mesh {level} (Stage 2)…"):
            st.session_state["sm"] = (mesh_key, surface(*mesh_key, g))
        if want_volume:
            sm = st.session_state["sm"][1]
            if sm.passed:
                with st.spinner(f"Building the volume mesh {level} (Stage 3)…"):
                    st.session_state["vm"] = (mesh_key, volume(*mesh_key, sm))
            else:
                st.sidebar.error("The surface mesh was refused: no volume mesh.")
sm = st.session_state["sm"][1] if st.session_state.get("sm", (None,))[0] == mesh_key else None
vm = st.session_state["vm"][1] if st.session_state.get("vm", (None,))[0] == mesh_key else None

# --- the page ---------------------------------------------------------------------------------------------------

st.title("Wings and meshes")
S = g.summary
st.caption(f"{wing.source} · {tname(wing.wing_type)} · wing hash {S.get('input_hash', '')[:8]} · lengths in mean chords (c̄)")
if g.passed:
    m = st.columns(5)
    m[0].metric("Stage 1 gates", "passed")
    m[1].metric("Aspect ratio", f"{S['aspect_ratio']:.2f}")
    m[2].metric("Full span", f"{S['span_m']:.2f} c̄")
    m[3].metric("Area, full wing", f"{S['area_m2']:.2f} c̄²")
    m[4].metric("Mean aerodynamic chord", f"{S['mac_m']:.3f} c̄")
    if S.get("labels"):
        lab = S["labels"]
        st.caption("Stage 1 labels: " + ", ".join(lab if isinstance(lab, (list, tuple)) else (f"{k}: {v}" for k, v in lab.items())))
else:
    st.error(f"Refused by Stage 1, gate {S.get('gate')}: {S.get('reason')}")

tab_g, tab_s, tab_v, tab_f = st.tabs(["Geometry", "Surface mesh", "Volume mesh", "Files"])

with tab_g:
    if g.stations:
        c1, c2 = st.columns(2)
        with c1:
            chart(figures.planform(g.stations))
        with c2:
            chart(figures.sections(g.stations))
        chart(figures.wing_3d(g.stations))
    rows = []
    for v in core.VARIABLES:
        f, F = core.spec(wing.wing_type, "focus"), core.spec(wing.wing_type, "full")
        how = "derived" if v in f.derived else ("pinned" if v in f.pinned else "")
        rng = lambda sp: "—" if how else f"{sp.ranges[v][0]:g} to {sp.ranges[v][1]:g}"
        rows.append({"variable": v, "in words": core.LABEL[v], "value": round(wing.vector[v], 5),
                     "how": how or "sampled", "focus range": rng(f), "full range": rng(F)})
    st.markdown("**The 17 numbers**")
    table(rows, tall=True)
    st.caption(f"Sections b0–b3: {', '.join(wing.vector['airfoils'])}. Built in {g.seconds:.1f} s.")

with tab_s:
    if sm is None:
        st.info(f"Press **Build surface** (or **Build volume**) in the sidebar for level {level}, Re {re:.0e}.")
    else:
        ok = sum(c.passed for c in sm.checks)
        m = st.columns(4)
        m[0].metric("Outcome", "passed" if sm.passed else "REFUSED")
        m[1].metric("Ring nodes × stations", f"{sm.wing.shape[0]} × {sm.wing.shape[1]}")
        m[2].metric("Tip cap", f"{sm.cap.shape[0]} × {sm.cap.shape[1]}")
        m[3].metric("Checks passed", f"{ok} of {len(sm.checks)}")
        skin = st.checkbox("Show the wing skin under the lines", True)
        chart(figures.surface_mesh_3d(sm, skin))
        k = st.slider("Station (root 0)", 0, sm.wing.shape[1] - 1, 0, key="ring_k")
        chart(figures.surface_ring(sm, k))
        st.markdown("**Checks (Stage 2)**")
        table(core.check_rows(sm.checks), tall=True)

with tab_v:
    if sm is not None and vm is None and sm.passed:
        cnt = core.count_cells(sm)
        r = core.ram_gib(cnt["cells"])
        st.info(f"Counted, not built: **{cnt['cells'] / 1e6:.2f} M cells** at {level}; ADflow RAM by S8's laws "
                f"{r['ANK only']:.0f} GiB (ANK only) to {r['ANK then NK']:.0f} GiB (ANK then NK). "
                "Press **Build volume** to build it.")
    elif vm is None:
        st.info(f"Press **Build volume** in the sidebar for level {level}, Re {re:.0e}.")
    if vm is not None:
        r = core.ram_gib(vm.cells)
        ok = sum(c.passed for c in vm.checks)
        m = st.columns(5)
        m[0].metric("Outcome", vm.outcome)
        m[1].metric("Cells", f"{vm.cells / 1e6:.2f} M")
        m[2].metric("Checks passed", f"{ok} of {len(vm.checks)}")
        m[3].metric("ADflow RAM, S8 laws", f"{r['ANK only']:.0f}–{r['ANK then NK']:.0f} GiB")
        m[4].metric("Built in", f"{vm.info.get('seconds_total', vm.info.get('seconds_build', 0)):.0f} s")
        pl = core.planes(vm)
        n_in = sum(p["side"] == "in" for p in pl)
        c1, c2, c3 = st.columns([3, 2, 2])
        j = c1.slider(f"Station plane (0 = root, the symmetry plane; {n_in - 1} = tip; then past the tip)",
                      0, len(pl) - 1, 0, key="plane_j")
        view = c2.radio("View", ["close", "wake", "all"], horizontal=True, key="view",
                        help="close: the section; wake: to 2.6 chords behind; all: the whole plane (80 c̄)")
        fan = c3.checkbox("Wake fan", True, key="fan")
        names = c3.checkbox("Block names", True, key="names")
        chart(figures.volume_plane(vm, sm, pl[j], view, fan, names))
        st.caption("Blocks in one plane: WU upper wake, CU upper side, CN nose arc, CL lower side, WL lower wake, "
                   "B base; past the tip, the tip cap CAP. Scroll to zoom, double-click to reset.")
        picks = sorted({0, n_in // 2, n_in - 1, min(n_in + 2, len(pl) - 1), j})
        chart(figures.volume_3d(vm, sm, [pl[q] for q in picks]))
        st.caption(f"Planes {', '.join(str(q) for q in picks)}: the root, the middle, the tip, one past the tip and the "
                   "one picked above; cut 1 c̄ ahead of the wing, 2.5 c̄ behind it and 1.2 c̄ above and below (the far "
                   "field is 80 c̄ away). Fine levels show every n-th line: zoom in the plane view for all.")
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("**Checks (Stage 3)**")
            table(core.check_rows(vm.checks, vm.review), tall=True)
        with c2:
            st.markdown("**Blocks**")
            table(core.block_table(vm), tall=True)

with tab_f:
    st.markdown("**The wing as a file** (load it again with *A file*)")
    st.download_button("Download the wing (.json)", wing.to_json(), file_name=f"wing_{S.get('input_hash', 'x')[:8]}.json",
                       mime="application/json")
    st.markdown(f"**Write folders** into `{core.OUT.relative_to(core.ROOT.parent)}/` (not in git)")
    c1, c2, c3 = st.columns(3)
    if c1.button("Wing folder (Stage 1)", disabled=not g.passed, width="stretch"):
        p = core.write_wing(g)
        st.success(f"{p}")
        table(core.folder_files(p))
    if c2.button("Surface mesh folder", disabled=sm is None, width="stretch"):
        p = core.write_surface_mesh(g, sm)
        st.success(f"{p}")
        table(core.folder_files(p))
    if c3.button("Volume mesh + CGNS + .su2", disabled=vm is None, width="stretch"):
        with st.spinner("Writing the solver files (check 15 reads them back)…"):
            p = core.write_volume_mesh(g, vm)
        st.success(f"{p}")
        table(core.folder_files(p))
