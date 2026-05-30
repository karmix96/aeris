#!/usr/bin/env bash
set -euo pipefail

# AERIS GUI v0.2 patch
# Run from the AERIS repository root:
#   bash aeris_gui_v0_2_patch.sh

mkdir -p src/aeris/gui src/aeris/commands tests/commands

cat > requirements-gui.txt <<'REQ'
streamlit>=1.31
pandas>=2.0
PyYAML>=6.0
REQ

cat > src/aeris/gui/__init__.py <<'PY'
"""Internal Streamlit operator GUI for AERIS."""
PY

cat > src/aeris/gui/app.py <<'PY'
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import streamlit as st

try:  # Optional, but strongly recommended for the GUI.
    import pandas as pd
except Exception:  # pragma: no cover - GUI fallback
    pd = None

try:  # Optional; config editor still degrades gracefully without it.
    import yaml
except Exception:  # pragma: no cover - GUI fallback
    yaml = None


APP_VERSION = "0.2.0"
DEFAULT_FEATURES = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg"
DEFAULT_TARGETS = "cl,cd,cm"
SUPPORTED_MODEL_TYPES = ["linear_regression", "random_forest", "gradient_boosting"]
SUPPORTED_SAMPLERS = ["lhs_v1", "random_v1"]
SUPPORTED_SPACING = ["equal", "cosine"]
SUPPORTED_QC_PRESETS = ["off", "debug", "production", "promotion_strict"]


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


# -----------------------------------------------------------------------------
# Generic helpers
# -----------------------------------------------------------------------------


def _default_project_root() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "src" / "aeris").exists():
            return candidate
    return cwd


def _repo_exists(project_root: Path) -> bool:
    return (project_root / "src" / "aeris").exists()


def _latest_dirs(root: Path, pattern: str = "*") -> list[Path]:
    if not root.exists():
        return []
    dirs = [p for p in root.glob(pattern) if p.is_dir()]
    return sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)


def _latest_files(root: Path, pattern: str = "*") -> list[Path]:
    if not root.exists():
        return []
    files = [p for p in root.glob(pattern) if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _resolve_default_path(path: Path, fallback: str) -> str:
    return str(path if path.exists() else path.parent / fallback)


def _read_text(path: Path, limit: int = 120_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception as exc:
        return f"<could not read {path}: {exc}>"


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_yaml(path: Path) -> Any | None:
    if yaml is None:
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_yaml(path: Path, payload: Any) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install PyYAML")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _csv_count(text: str) -> int:
    if not text.strip():
        return 1
    return len([x for x in text.split(",") if x.strip()])


def _split_csv(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def _estimate_sweep_cases(*values: str) -> int:
    n = 1
    for text in values:
        n *= _csv_count(text)
    return n


def _quote_command(command: list[str]) -> str:
    try:
        return shlex.join([str(x) for x in command])
    except Exception:
        return " ".join([str(x) for x in command])


def _append_history(result: CommandResult) -> None:
    history = st.session_state.setdefault("command_history", [])
    history.insert(0, result)
    del history[50:]


def _run_command(
    *,
    project_root: Path,
    aeris_executable: str,
    args: Iterable[str],
    timeout_sec: int,
) -> CommandResult:
    command = [aeris_executable, "--no-check-writable", *[str(a) for a in args]]
    env = os.environ.copy()
    src_path = str(project_root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        return CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except FileNotFoundError as exc:
        return CommandResult(command=command, returncode=127, stdout="", stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nCommand timed out after {timeout_sec} s.",
        )


def _show_result(result: CommandResult, expanded: bool = True) -> None:
    with st.expander("Command", expanded=True):
        st.code(_quote_command(result.command), language="bash")

    if result.returncode == 0:
        st.success(f"Command finished successfully: exit code {result.returncode}")
    else:
        st.error(f"Command failed: exit code {result.returncode}")

    if result.stdout.strip():
        with st.expander("stdout", expanded=expanded):
            st.code(result.stdout[-80_000:], language="text")
    if result.stderr.strip():
        with st.expander("stderr", expanded=True):
            st.code(result.stderr[-80_000:], language="text")


def _run_button(
    label: str,
    args: list[str],
    project_root: Path,
    aeris_executable: str,
    timeout_sec: int,
    *,
    dry_run: bool = False,
    danger: bool = False,
    key: str | None = None,
) -> None:
    preview = [aeris_executable, "--no-check-writable", *[str(a) for a in args]]
    st.code(_quote_command(preview), language="bash")

    if dry_run:
        st.info("Dry-run mode is enabled. Command preview only; nothing will execute.")
        return

    button_type = "primary" if not danger else "secondary"
    if st.button(label, type=button_type, key=key):
        if not _repo_exists(project_root):
            st.error("Project root does not look like an AERIS repository: missing src/aeris")
            return
        with st.spinner("Running AERIS command..."):
            result = _run_command(
                project_root=project_root,
                aeris_executable=aeris_executable,
                args=args,
                timeout_sec=timeout_sec,
            )
        st.session_state["last_result"] = result
        _append_history(result)
        _show_result(result)


def _select_latest_dir(label: str, root: Path, *, pattern: str = "*", key: str) -> str:
    dirs = _latest_dirs(root, pattern)
    options = [""] + [str(p) for p in dirs[:50]]
    default = 1 if len(options) > 1 else 0
    return st.selectbox(label, options, index=default, key=key)


def _display_dataframe(path: Path) -> None:
    if pd is None:
        st.code(_read_text(path), language="text")
        return
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        st.code(_read_text(path), language="text")
        return

    st.caption(f"Rows: {len(df):,} | Columns: {len(df.columns):,}")
    st.dataframe(df, use_container_width=True, height=420)

    numeric_cols = list(df.select_dtypes(include="number").columns)
    if numeric_cols:
        with st.expander("Quick numeric plot", expanded=False):
            x_col = st.selectbox("X column", ["<index>"] + numeric_cols, key=f"x_{path}")
            y_cols = st.multiselect("Y columns", numeric_cols, default=numeric_cols[: min(3, len(numeric_cols))], key=f"y_{path}")
            if y_cols:
                plot_df = df[y_cols].copy()
                if x_col != "<index>":
                    plot_df.index = df[x_col]
                st.line_chart(plot_df)


def _display_file(path: Path) -> None:
    if not path.exists():
        st.warning(f"Missing file: {path}")
        return

    st.caption(str(path))
    suffix = path.suffix.lower()

    if suffix == ".json":
        payload = _read_json(path)
        if payload is None:
            st.code(_read_text(path), language="text")
        else:
            st.json(payload)
        return

    if suffix == ".csv":
        _display_dataframe(path)
        return

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        st.image(str(path), use_container_width=True)
        return

    if suffix in {".txt", ".log", ".yaml", ".yml", ".avl", ".md"}:
        st.code(_read_text(path), language="yaml" if suffix in {".yaml", ".yml"} else "text")
        return

    st.info("Preview not supported for this file type.")


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------


def sidebar_settings() -> tuple[Path, str, int, bool]:
    st.sidebar.title(f"AERIS GUI v{APP_VERSION}")
    project_root = Path(
        st.sidebar.text_input("Project root", value=str(_default_project_root()))
    ).expanduser().resolve()

    default_aeris = shutil.which("aeris") or "aeris"
    aeris_executable = st.sidebar.text_input("AERIS executable", value=default_aeris)
    timeout_sec = int(st.sidebar.number_input("Command timeout [s]", min_value=5, max_value=86400, value=900, step=5))
    dry_run = st.sidebar.toggle("Dry-run mode", value=False, help="Preview commands without executing them.")

    st.sidebar.divider()
    if _repo_exists(project_root):
        st.sidebar.success("AERIS repo detected")
    else:
        st.sidebar.error("src/aeris not found")

    st.sidebar.caption("This GUI calls the existing AERIS CLI. It is a cockpit, not a duplicate backend.")
    return project_root, aeris_executable, timeout_sec, dry_run


# -----------------------------------------------------------------------------
# Tabs
# -----------------------------------------------------------------------------


def tab_overview(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool) -> None:
    st.header("AERIS production cockpit")
    st.write(
        "Run, inspect, and replay AERIS workflows from a single local dashboard. "
        "The backend remains your CLI/pipeline architecture."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Run folders", len(_latest_dirs(project_root / "data" / "runs")))
    with col2:
        st.metric("Dataset folders", len(_latest_dirs(project_root / "data" / "datasets")))
    with col3:
        st.metric("Geometry configs", len(_latest_files(project_root / "configs" / "geometry", "*.yaml")))
    with col4:
        st.metric("Mass configs", len(_latest_files(project_root / "configs" / "mass", "*.yaml")))

    st.subheader("Health checks")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _run_button("Version", ["version"], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="health_version")
    with c2:
        _run_button("Top help", ["--help"], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="health_help")
    with c3:
        _run_button("Aero help", ["aero", "--help"], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="health_aero_help")
    with c4:
        _run_button("ML help", ["ml", "--help"], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="health_ml_help")

    st.subheader("Latest artifacts")
    latest_runs = _latest_dirs(project_root / "data" / "runs")[:8]
    latest_datasets = _latest_dirs(project_root / "data" / "datasets")[:8]
    col1, col2 = st.columns(2)
    with col1:
        st.write("Latest runs")
        for p in latest_runs:
            st.caption(str(p.relative_to(project_root) if p.is_relative_to(project_root) else p))
    with col2:
        st.write("Latest datasets")
        for p in latest_datasets:
            st.caption(str(p.relative_to(project_root) if p.is_relative_to(project_root) else p))


def tab_config_lab(project_root: Path) -> None:
    st.header("Config Lab")
    st.write("Inspect, edit, and create safe GUI-side config copies. This is where symmetry/control-surface setup belongs.")

    config_root = project_root / "configs"
    candidates = sorted(config_root.rglob("*.yaml")) if config_root.exists() else []
    choices = [str(p) for p in candidates]
    selected = st.selectbox("Config file", choices, index=0 if choices else None)

    if not selected:
        st.warning("No YAML configs found.")
        return

    path = Path(selected)
    raw_text = _read_text(path, limit=500_000)
    edited = st.text_area("YAML editor", raw_text, height=420)

    col1, col2 = st.columns(2)
    with col1:
        save_name = st.text_input("Save edited copy as", value=f"configs/gui/{path.stem}_gui.yaml")
    with col2:
        if st.button("Save edited config copy", type="primary"):
            out = (project_root / save_name).resolve() if not Path(save_name).is_absolute() else Path(save_name)
            if yaml is not None:
                try:
                    yaml.safe_load(edited)
                except Exception as exc:
                    st.error(f"YAML is invalid: {exc}")
                    return
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(edited, encoding="utf-8")
            st.success(f"Saved: {out}")

    payload = _read_yaml(path)
    if isinstance(payload, dict):
        st.subheader("Control surfaces / symmetry")
        cs = (((payload.get("geometry") or {}).get("control_surfaces")) or {})
        surfaces = cs.get("surfaces", []) if isinstance(cs, dict) else []
        st.write(f"Enabled: `{cs.get('enabled', False) if isinstance(cs, dict) else False}`")
        if surfaces and pd is not None:
            rows = []
            for s in surfaces:
                rows.append({
                    "name": s.get("name"),
                    "family": s.get("family"),
                    "symmetric": s.get("symmetric", True),
                    "side": s.get("side"),
                    "hinge_point": s.get("hinge_point"),
                    "span_start": (s.get("spanwise") or {}).get("start_frac"),
                    "span_end": (s.get("spanwise") or {}).get("end_frac"),
                    "required": s.get("required", False),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No control-surface definitions found in this config.")

        with st.expander("Create/replace a simple trailing-edge control-surface block", expanded=False):
            enabled = st.checkbox("Enable control surfaces", value=True)
            name = st.text_input("Surface name", value="elevon")
            symmetric = st.checkbox("Symmetric surface", value=True)
            side = st.selectbox("Side if asymmetric", ["left", "right"], disabled=symmetric)
            hinge = st.number_input("Hinge point", min_value=0.01, max_value=0.99, value=0.75, step=0.01)
            s0 = st.number_input("Span start fraction", min_value=0.0, max_value=1.0, value=0.60, step=0.01)
            s1 = st.number_input("Span end fraction", min_value=0.0, max_value=1.0, value=0.95, step=0.01)
            required = st.checkbox("Required by validation", value=False)
            out_name = st.text_input("Save control-surface config as", value=f"configs/gui/{path.stem}_controls.yaml")
            if st.button("Write control-surface config copy"):
                if s0 >= s1:
                    st.error("Span start must be lower than span end.")
                    return
                new_payload = dict(payload)
                geometry = dict(new_payload.get("geometry") or {})
                surface = {
                    "name": name,
                    "family": "trailing_edge",
                    "hinge_point": float(hinge),
                    "symmetric": bool(symmetric),
                    "spanwise": {"start_frac": float(s0), "end_frac": float(s1)},
                    "required": bool(required),
                }
                if not symmetric:
                    surface["side"] = side
                geometry["control_surfaces"] = {"enabled": bool(enabled), "surfaces": [surface] if enabled else []}
                new_payload["geometry"] = geometry
                out = (project_root / out_name).resolve() if not Path(out_name).is_absolute() else Path(out_name)
                try:
                    _write_yaml(out, new_payload)
                except Exception as exc:
                    st.error(str(exc))
                    return
                st.success(f"Saved: {out}")
                st.code(str(out), language="text")


def tab_geometry(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool) -> None:
    st.header("Geometry")
    default_cfg = project_root / "configs" / "geometry" / "baseline_bwb.yaml"
    config = st.text_input("Geometry config", value=str(default_cfg), key="geom_config")

    col1, col2, col3 = st.columns(3)
    with col1:
        _run_button("Generate geometry", ["geometry", "generate", "-c", config], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="geom_generate")
    with col2:
        seed = st.text_input("Visualization seed override", value="")
        save_plot = st.checkbox("Save plot", value=True, key="geom_save_plot")
        build_asb = st.checkbox("Build AeroSandbox", value=True, key="geom_build_asb")
    with col3:
        show_plot = st.checkbox("Show plot interactively", value=False, key="geom_show_plot")
        draw_3d = st.checkbox("Open AeroSandbox 3D viewer", value=False, key="geom_draw_3d")

    viz_args = ["geometry", "visualize", "-c", config]
    if seed.strip():
        viz_args += ["--seed", seed.strip()]
    viz_args += ["--save-plot" if save_plot else "--no-save-plot"]
    viz_args += ["--build-aerosandbox" if build_asb else "--no-build-aerosandbox"]
    viz_args += ["--show-plot" if show_plot else "--no-show-plot"]
    viz_args += ["--draw-3d" if draw_3d else "--no-draw-3d"]
    _run_button("Visualize geometry", viz_args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="geom_visualize")

    st.info("For production batches, keep plots off. Visualization is inspection, not a hot path.")


def tab_dataset(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool) -> None:
    st.header("Dataset")
    mode = st.radio("Dataset workflow", ["Geometry dataset", "Unified aero dataset", "QC / curate / promote"], horizontal=True)

    if mode == "Geometry dataset":
        default_cfg = project_root / "configs" / "geometry" / "wing_bwb.yaml"
        config = st.text_input("Geometry config", value=str(default_cfg), key="dataset_geom_cfg")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            n = int(st.number_input("N geometries", min_value=1, max_value=1_000_000, value=20, step=1, key="dataset_n"))
            sampler = st.selectbox("Sampler", SUPPORTED_SAMPLERS, index=0, key="dataset_sampler")
        with c2:
            sampler_seed = int(st.number_input("Sampler seed", min_value=0, max_value=2_147_483_647, value=123, step=1, key="dataset_seed"))
            name = st.text_input("Dataset name override", value="", key="dataset_name")
        with c3:
            save_plot = st.checkbox("Save plots", value=False, key="dataset_save_plot")
            build_asb = st.checkbox("Build AeroSandbox", value=False, key="dataset_asb")
        with c4:
            st.caption("Rule of thumb")
            st.write("Use `--no-save-plot` for real batches.")

        args = ["dataset", "generate", "-c", config, "--n", str(n), "--sampler", sampler, "--sampler-seed", str(sampler_seed)]
        args += ["--save-plot" if save_plot else "--no-save-plot"]
        args += ["--build-aerosandbox" if build_asb else "--no-build-aerosandbox"]
        if name.strip():
            args += ["--name", name.strip()]
        _run_button("Generate geometry dataset", args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dataset_generate")

    elif mode == "Unified aero dataset":
        default_cfg = project_root / "configs" / "geometry" / "wing_bwb.yaml"
        config = st.text_input("Geometry config", value=str(default_cfg), key="aero_dataset_cfg")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            n = int(st.number_input("N geometries", min_value=1, max_value=100_000, value=5, step=1, key="aero_dataset_n"))
            sampler = st.selectbox("Sampler", SUPPORTED_SAMPLERS, index=0, key="aero_dataset_sampler")
            sampler_seed = int(st.number_input("Sampler seed", min_value=0, value=123, step=1, key="aero_dataset_seed"))
        with c2:
            name = st.text_input("Aero dataset name", value="gui_aero_dataset_v1", key="aero_dataset_name")
            qc_preset = st.selectbox("QC preset", SUPPORTED_QC_PRESETS, index=2, key="aero_dataset_qc")
            retain = st.selectbox("Retain aero runs", ["all", "failures_only", "none"], index=1, key="aero_dataset_retain")
        with c3:
            alpha_values = st.text_input("alpha values", value="0,2,4", key="aero_dataset_alpha")
            beta_values = st.text_input("beta values", value="0", key="aero_dataset_beta")
            control_values = st.text_input("control input values [deg]", value="-5,0,5", key="aero_dataset_control")
        with c4:
            velocity_values = st.text_input("velocity values [m/s]", value="28", key="aero_dataset_velocity")
            altitude_values = st.text_input("altitude values [m]", value="1500", key="aero_dataset_altitude")
            max_cases = st.text_input("max cases per geometry", value="", key="aero_dataset_max_cases")

        with st.expander("Advanced sweep dimensions", expanded=False):
            p_values = st.text_input("p values [rad/s]", value="", key="aero_dataset_p")
            q_values = st.text_input("q values [rad/s]", value="", key="aero_dataset_q")
            r_values = st.text_input("r values [rad/s]", value="", key="aero_dataset_r")
            avl_command = st.text_input("AVL command", value="avl", key="aero_dataset_avl")
            spanwise = int(st.number_input("Spanwise panels", min_value=1, value=4, step=1, key="aero_dataset_span"))
            chordwise = int(st.number_input("Chordwise panels", min_value=1, value=8, step=1, key="aero_dataset_chord"))
            span_spacing = st.selectbox("Spanwise spacing", SUPPORTED_SPACING, index=0, key="aero_dataset_span_spacing")
            chord_spacing = st.selectbox("Chordwise spacing", SUPPORTED_SPACING, index=1, key="aero_dataset_chord_spacing")
            timeout = int(st.number_input("Solver timeout [s]", min_value=5, value=180, step=5, key="aero_dataset_timeout"))
            keep_geometry = st.checkbox("Keep intermediate geometry dataset", value=True, key="aero_dataset_keep_geom")
            save_plot = st.checkbox("Save geometry plots", value=False, key="aero_dataset_save_plot")
            build_asb = st.checkbox("Build AeroSandbox", value=True, key="aero_dataset_build_asb")

        per_geom = _estimate_sweep_cases(alpha_values, beta_values, velocity_values, altitude_values, p_values, q_values, r_values, control_values)
        total_cases = per_geom * n
        st.metric("Estimated aero cases", f"{total_cases:,}", help="N geometries × Cartesian sweep size")
        if total_cases > 1000:
            st.warning("This is a serious run. Check AVL availability, paneling, retention, and timeout before pressing the button.")

        args = [
            "dataset", "aero-generate", "-c", config, "--n", str(n), "--name", name,
            "--sampler", sampler, "--sampler-seed", str(sampler_seed),
            "--alpha-values", alpha_values, "--beta-values", beta_values,
            "--velocity-values", velocity_values, "--altitude-values", altitude_values,
            "--control-input-values", control_values,
            "--solver", "aerosandbox_avl", "--avl-command", avl_command,
            "--timeout-sec", str(timeout), "--spanwise-resolution", str(spanwise),
            "--chordwise-resolution", str(chordwise), "--spanwise-spacing", span_spacing,
            "--chordwise-spacing", chord_spacing, "--retain-aero-runs", retain,
            "--qc-preset", qc_preset,
            "--save-plot" if save_plot else "--no-save-plot",
            "--build-aerosandbox" if build_asb else "--no-build-aerosandbox",
            "--keep-geometry-dataset" if keep_geometry else "--delete-geometry-dataset",
        ]
        if p_values.strip():
            args += ["--p-values", p_values]
        if q_values.strip():
            args += ["--q-values", q_values]
        if r_values.strip():
            args += ["--r-values", r_values]
        if max_cases.strip():
            args += ["--max-cases", max_cases.strip()]
        _run_button("Generate unified aero dataset", args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="aero_dataset_generate")

    else:
        dataset = _select_latest_dir("Dataset root", project_root / "data" / "datasets", key="qc_dataset")
        if not dataset:
            st.warning("No dataset selected.")
            return
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _run_button("Inspect", ["dataset", "inspect", "--dataset", dataset], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dataset_inspect")
        with col2:
            _run_button("Aero QC", ["dataset", "aero-qc", "--dataset", dataset, "--profile", "basic"], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dataset_aero_qc")
        with col3:
            _run_button("Curate aero", ["dataset", "curate-aero", "--dataset", dataset], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dataset_curate")
        with col4:
            force = st.checkbox("Force promotion", value=False)
            promote_args = ["dataset", "promote-aero", "--dataset", dataset]
            if force:
                promote_args += ["--force"]
            _run_button("Promote aero", promote_args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dataset_promote", danger=force)
        _run_button("Require promoted gate", ["dataset", "require-promoted-aero", "--dataset", dataset], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dataset_require_promoted")


def _geometry_source_args(project_root: Path, prefix: str) -> list[str]:
    source_mode = st.radio("Geometry source", ["config", "run-dir", "dataset case"], horizontal=True, key=f"{prefix}_source_mode")
    generator_id = st.text_input("Generator ID for stored geometry", value="bwb_segmented_v1", key=f"{prefix}_generator")
    args: list[str] = []
    if source_mode == "config":
        cfg = st.text_input("Geometry config", value=str(project_root / "configs" / "geometry" / "baseline_bwb_25.yaml"), key=f"{prefix}_cfg")
        args += ["--config", cfg, "--geometry-source", "native"]
    elif source_mode == "run-dir":
        run_dir = _select_latest_dir("Geometry/aero run dir", project_root / "data" / "runs", key=f"{prefix}_run")
        args += ["--run-dir", run_dir, "--geometry-source", "reconstruct", "--generator-id", generator_id]
    else:
        dataset = _select_latest_dir("Dataset root", project_root / "data" / "datasets", key=f"{prefix}_dataset")
        geometry_id = st.text_input("Geometry ID", value="geom_00001", key=f"{prefix}_geometry_id")
        args += ["--dataset", dataset, "--geometry-id", geometry_id, "--geometry-source", "reconstruct", "--generator-id", generator_id]
    return args


def _solver_options(prefix: str) -> list[str]:
    with st.expander("Solver / paneling", expanded=False):
        avl_command = st.text_input("AVL command", value="avl", key=f"{prefix}_avl")
        timeout = int(st.number_input("Solver timeout [s]", min_value=5, value=180, step=5, key=f"{prefix}_timeout"))
        spanwise = int(st.number_input("Spanwise panels", min_value=1, value=4, step=1, key=f"{prefix}_span"))
        chordwise = int(st.number_input("Chordwise panels", min_value=1, value=8, step=1, key=f"{prefix}_chord"))
        span_spacing = st.selectbox("Spanwise spacing", SUPPORTED_SPACING, index=0, key=f"{prefix}_span_spacing")
        chord_spacing = st.selectbox("Chordwise spacing", SUPPORTED_SPACING, index=1, key=f"{prefix}_chord_spacing")
        save_surface = st.checkbox("Save surface forces", value=False, key=f"{prefix}_save_surface")
        save_element = st.checkbox("Save element forces", value=False, key=f"{prefix}_save_element")
        output_name = st.text_input("Output name suffix", value="", key=f"{prefix}_output_name")

    args = [
        "--solver", "aerosandbox_avl", "--avl-command", avl_command,
        "--timeout-sec", str(timeout), "--spanwise-resolution", str(spanwise),
        "--chordwise-resolution", str(chordwise), "--spanwise-spacing", span_spacing,
        "--chordwise-spacing", chord_spacing,
    ]
    if save_surface:
        args += ["--save-surface-forces"]
    if save_element:
        args += ["--save-element-forces"]
    if output_name.strip():
        args += ["--output-name", output_name.strip()]
    return args


def tab_aero(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool) -> None:
    st.header("Aero")
    mode = st.radio("Aero workflow", ["Single run", "Sweep", "Inspect / replay"], horizontal=True)

    if mode == "Single run":
        args = ["aero", "run"] + _geometry_source_args(project_root, "aero_single")
        st.subheader("Flight condition")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            alpha = st.number_input("alpha [deg]", value=4.0, key="single_alpha")
            beta = st.number_input("beta [deg]", value=0.0, key="single_beta")
        with c2:
            velocity = st.number_input("velocity [m/s]", value=28.0, key="single_velocity")
            altitude = st.number_input("altitude [m]", value=1500.0, key="single_altitude")
        with c3:
            p_rate = st.number_input("p [rad/s]", value=0.0, format="%.5f", key="single_p")
            q_rate = st.number_input("q [rad/s]", value=0.0, format="%.5f", key="single_q")
        with c4:
            r_rate = st.number_input("r [rad/s]", value=0.0, format="%.5f", key="single_r")
            use_control = st.checkbox("Control input", value=False, key="single_use_control")
            control = st.number_input("control [deg]", value=0.0, disabled=not use_control, key="single_control")
        args += ["--alpha", str(alpha), "--beta", str(beta), "--velocity", str(velocity), "--altitude", str(altitude), "--p", str(p_rate), "--q", str(q_rate), "--r", str(r_rate)]
        if use_control:
            args += ["--control-input-deg", str(control)]
        args += _solver_options("aero_single")
        _run_button("Run aero case", args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="aero_single_run")

    elif mode == "Sweep":
        args = ["aero", "sweep"] + _geometry_source_args(project_root, "aero_sweep")
        st.subheader("Sweep values")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            alpha_values = st.text_input("alpha values [deg]", value="0,2,4", key="sweep_alpha")
            beta_values = st.text_input("beta values [deg]", value="0", key="sweep_beta")
        with c2:
            control_values = st.text_input("control input values [deg]", value="-5,0,5", key="sweep_control")
            velocity_values = st.text_input("velocity values [m/s]", value="28", key="sweep_velocity")
        with c3:
            altitude_values = st.text_input("altitude values [m]", value="1500", key="sweep_altitude")
            q_values = st.text_input("q values [rad/s]", value="", key="sweep_q")
        with c4:
            p_values = st.text_input("p values [rad/s]", value="", key="sweep_p")
            r_values = st.text_input("r values [rad/s]", value="", key="sweep_r")

        max_cases = st.text_input("Max cases safety cap", value="", key="sweep_max_cases")
        ncases = _estimate_sweep_cases(alpha_values, beta_values, velocity_values, altitude_values, p_values, q_values, r_values, control_values)
        st.metric("Estimated sweep cases", f"{ncases:,}")
        if ncases > 200:
            st.warning("Large sweep. Use --max-cases or reduce dimensions unless this is intentional.")

        for flag, value in [
            ("--alpha-values", alpha_values), ("--beta-values", beta_values),
            ("--velocity-values", velocity_values), ("--altitude-values", altitude_values),
            ("--control-input-values", control_values),
            ("--p-values", p_values), ("--q-values", q_values), ("--r-values", r_values),
        ]:
            if value.strip():
                args += [flag, value]
        if max_cases.strip():
            args += ["--max-cases", max_cases.strip()]
        args += _solver_options("aero_sweep")
        _run_button("Run aero sweep", args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="aero_sweep_run")

    else:
        latest_aero = _select_latest_dir("Aero run", project_root / "data" / "runs", pattern="*_aero_*", key="aero_inspect_run")
        col1, col2 = st.columns(2)
        with col1:
            if latest_aero:
                _run_button("Inspect aero run", ["aero", "inspect", "--run-dir", latest_aero], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="aero_inspect")
        with col2:
            latest_sweep = _select_latest_dir("Aero sweep", project_root / "data" / "runs", pattern="*_aero_sweep_*", key="aero_inspect_sweep")
            if latest_sweep:
                _run_button("Inspect sweep", ["aero", "sweep-inspect", "--run-dir", latest_sweep], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="aero_sweep_inspect")
                case_index = int(st.number_input("Sweep case index", min_value=0, value=0, step=1))
                _run_button("Inspect sweep case", ["aero", "sweep-case-inspect", "--run-dir", latest_sweep, "--case-index", str(case_index)], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="aero_sweep_case_inspect")


def tab_dynamics(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool) -> None:
    st.header("Dynamics foundation")
    run_dir = _select_latest_dir("Aero run dir", project_root / "data" / "runs", pattern="*_aero_*", key="dyn_run")
    if not run_dir:
        st.warning("No aero run selected.")
        return

    mode = st.radio("Mass input", ["mass config", "manual"], horizontal=True)
    build_args = ["dynamics", "build", "--run-dir", run_dir]
    sweep_base_args: list[str] = []

    if mode == "mass config":
        mass_config = st.text_input("Mass config", value=str(project_root / "configs" / "mass" / "baseline_uav.yaml"), key="dyn_mass_config")
        build_args += ["--mass-config", mass_config]
        sweep_base_args += ["--mass-config", mass_config]
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            mass_kg = st.number_input("mass [kg]", value=8.0, key="dyn_mass")
        with c2:
            x_cg_m = st.number_input("x CG [m]", value=0.45, key="dyn_xcg")
        with c3:
            y_cg_m = st.number_input("y CG [m]", value=0.0, key="dyn_ycg")
        with c4:
            z_cg_m = st.number_input("z CG [m]", value=0.0, key="dyn_zcg")
        build_args += ["--mass-kg", str(mass_kg), "--x-cg-m", str(x_cg_m), "--y-cg-m", str(y_cg_m), "--z-cg-m", str(z_cg_m)]
        sweep_base_args += ["--mass-kg", str(mass_kg), "--y-cg-m", str(y_cg_m), "--z-cg-m", str(z_cg_m)]

    col1, col2, col3 = st.columns(3)
    with col1:
        _run_button("Build dynamics", build_args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dyn_build")
    with col2:
        _run_button("Inspect dynamics", ["dynamics", "inspect", "--run-dir", run_dir], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dyn_inspect")
    with col3:
        _run_button("Trim diagnostic", ["dynamics", "trim", "--run-dir", run_dir], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dyn_trim")

    st.subheader("CG sweep")
    c1, c2, c3 = st.columns(3)
    with c1:
        cg_min = st.number_input("CG min [m]", value=0.30, key="dyn_cg_min")
    with c2:
        cg_max = st.number_input("CG max [m]", value=0.70, key="dyn_cg_max")
    with c3:
        n = int(st.number_input("N CG points", min_value=2, value=9, step=1, key="dyn_cg_n"))

    sweep_args = ["dynamics", "cg-sweep", "--run-dir", run_dir, "--cg-min-m", str(cg_min), "--cg-max-m", str(cg_max), "--n", str(n)] + sweep_base_args
    col1, col2 = st.columns(2)
    with col1:
        _run_button("Run CG sweep", sweep_args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dyn_cg_sweep")
    with col2:
        _run_button("Inspect CG sweep", ["dynamics", "cg-sweep-inspect", "--run-dir", run_dir], project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="dyn_cg_inspect")


def tab_ml(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool) -> None:
    st.header("ML")
    st.warning("ML commands require promoted aero datasets. The GUI exposes the gate; it does not bypass it.")
    mode = st.radio("ML workflow", ["Training data / split", "Train", "Compare", "Predict"], horizontal=True)

    if mode in {"Training data / split", "Train", "Compare"}:
        dataset = _select_latest_dir("Promoted aero dataset root", project_root / "data" / "datasets", key=f"ml_dataset_{mode}")
        features = st.text_input("Feature columns", value=DEFAULT_FEATURES, key=f"ml_features_{mode}")
        targets = st.text_input("Target columns", value=DEFAULT_TARGETS, key=f"ml_targets_{mode}")
        allow_forced = st.checkbox("Allow forced promotion", value=False, key=f"ml_allow_forced_{mode}")
        forced_args = ["--allow-forced"] if allow_forced else []

    if mode == "Training data / split":
        col1, col2 = st.columns(2)
        with col1:
            _run_button("Check training data", ["dataset", "training-data", "--dataset", dataset, "--features", features, "--targets", targets] + forced_args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="ml_training_data")
        with col2:
            split_method = st.selectbox("Split method", ["grouped", "random"], index=0, key="ml_split_method")
            random_seed = int(st.number_input("Random seed", value=123, step=1, key="ml_split_seed"))
            _run_button("Split training data", ["dataset", "split-training-data", "--dataset", dataset, "--features", features, "--targets", targets, "--method", split_method, "--random-seed", str(random_seed)] + forced_args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="ml_split")

    elif mode == "Train":
        c1, c2, c3 = st.columns(3)
        with c1:
            model_type = st.selectbox("Model", SUPPORTED_MODEL_TYPES, index=2)
            split_method = st.selectbox("Split method", ["grouped", "random"], index=0, key="ml_train_split_method")
        with c2:
            random_seed = int(st.number_input("Random seed", value=123, step=1, key="ml_train_seed"))
            output_dir = st.text_input("Output dir", value=str(project_root / "data" / "processed" / "ml_runs" / "gui_train"), key="ml_train_out")
        with c3:
            train_fraction = st.number_input("Train fraction", value=0.70, min_value=0.01, max_value=0.98, step=0.01)
            val_fraction = st.number_input("Val fraction", value=0.15, min_value=0.01, max_value=0.98, step=0.01)
            test_fraction = st.number_input("Test fraction", value=0.15, min_value=0.01, max_value=0.98, step=0.01)
        args = ["ml", "train", "--dataset", dataset, "--features", features, "--targets", targets, "--model-type", model_type, "--split-method", split_method, "--random-seed", str(random_seed), "--train-fraction", str(train_fraction), "--val-fraction", str(val_fraction), "--test-fraction", str(test_fraction), "--output-dir", output_dir] + forced_args
        _run_button("Train ML model", args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="ml_train")

    elif mode == "Compare":
        models = st.multiselect("Models", SUPPORTED_MODEL_TYPES, default=SUPPORTED_MODEL_TYPES)
        split_method = st.selectbox("Split method", ["grouped", "random"], index=0, key="ml_compare_split_method")
        random_seed = int(st.number_input("Random seed", value=123, step=1, key="ml_compare_seed"))
        output_dir = st.text_input("Output dir", value=str(project_root / "data" / "processed" / "ml_runs" / "gui_compare"), key="ml_compare_out")
        args = ["ml", "compare", "--dataset", dataset, "--features", features, "--targets", targets, "--models", ",".join(models), "--split-method", split_method, "--random-seed", str(random_seed), "--output-dir", output_dir] + forced_args
        _run_button("Compare ML models", args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="ml_compare")

    else:
        model_run = st.text_input("Model run directory", value=str(project_root / "data" / "processed" / "ml_runs" / "<run>"), key="ml_predict_run")
        input_csv = st.text_input("Input CSV", value=str(project_root / "data" / "datasets" / "<dataset>" / "curated_aero_dataset.csv"), key="ml_predict_csv")
        output_dir = st.text_input("Output dir", value=str(project_root / "data" / "processed" / "ml_predictions" / "gui_predict"), key="ml_predict_out")
        include_truth = st.checkbox("Include truth if available", value=True, key="ml_predict_truth")
        args = ["ml", "predict", "--model-run-dir", model_run, "--input-csv", input_csv, "--output-dir", output_dir]
        args += ["--include-truth-if-available" if include_truth else "--no-include-truth-if-available"]
        _run_button("Run prediction", args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="ml_predict")


def tab_artifacts(project_root: Path) -> None:
    st.header("Runs / artifacts")
    root_choice = st.radio("Root", ["runs", "datasets", "processed", "debug", "custom"], horizontal=True)
    if root_choice == "runs":
        root = project_root / "data" / "runs"
    elif root_choice == "datasets":
        root = project_root / "data" / "datasets"
    elif root_choice == "processed":
        root = project_root / "data" / "processed"
    elif root_choice == "debug":
        root = project_root / "data" / "debug"
    else:
        root = Path(st.text_input("Custom root", value=str(project_root / "data"))).expanduser().resolve()

    dirs = _latest_dirs(root)
    if not dirs:
        st.warning(f"No directories found under {root}")
        return

    selected = st.selectbox("Select run/dataset", dirs[:200], format_func=lambda p: p.name)
    st.write(f"Selected: `{selected}`")

    files = sorted([p for p in selected.rglob("*") if p.is_file()])
    st.metric("Files", len(files))
    preview_candidates = [
        p for p in files
        if p.suffix.lower() in {".json", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".log", ".yaml", ".yml", ".avl", ".md"}
    ]
    if not preview_candidates:
        st.info("No previewable files found.")
        return

    selected_file = st.selectbox("Preview file", preview_candidates, format_func=lambda p: str(p.relative_to(selected)))
    _display_file(selected_file)


def tab_cli_console(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool) -> None:
    st.header("CLI console")
    st.write("Run arbitrary AERIS CLI arguments. No shell is used; arguments are split safely.")
    raw_args = st.text_input("AERIS args", value="version", help="Example: aero inspect --run-dir data/runs/<run>")
    try:
        args = shlex.split(raw_args)
    except Exception as exc:
        st.error(f"Could not parse args: {exc}")
        return
    _run_button("Run CLI command", args, project_root, aeris_executable, timeout_sec, dry_run=dry_run, key="cli_console_run")

    st.subheader("Command history")
    history = st.session_state.get("command_history", [])
    if not history:
        st.info("No commands run yet in this GUI session.")
        return
    for i, result in enumerate(history[:10]):
        with st.expander(f"#{i + 1} exit={result.returncode}: {_quote_command(result.command[:6])} ...", expanded=False):
            _show_result(result, expanded=False)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="AERIS GUI", layout="wide")
    project_root, aeris_executable, timeout_sec, dry_run = sidebar_settings()

    tabs = st.tabs([
        "Overview",
        "Config Lab",
        "Geometry",
        "Dataset",
        "Aero",
        "Dynamics",
        "ML",
        "Artifacts",
        "CLI Console",
    ])
    with tabs[0]:
        tab_overview(project_root, aeris_executable, timeout_sec, dry_run)
    with tabs[1]:
        tab_config_lab(project_root)
    with tabs[2]:
        tab_geometry(project_root, aeris_executable, timeout_sec, dry_run)
    with tabs[3]:
        tab_dataset(project_root, aeris_executable, timeout_sec, dry_run)
    with tabs[4]:
        tab_aero(project_root, aeris_executable, timeout_sec, dry_run)
    with tabs[5]:
        tab_dynamics(project_root, aeris_executable, timeout_sec, dry_run)
    with tabs[6]:
        tab_ml(project_root, aeris_executable, timeout_sec, dry_run)
    with tabs[7]:
        tab_artifacts(project_root)
    with tabs[8]:
        tab_cli_console(project_root, aeris_executable, timeout_sec, dry_run)

    if "last_result" in st.session_state:
        with st.sidebar.expander("Last command", expanded=False):
            st.code(_quote_command(st.session_state["last_result"].command), language="bash")
            st.write(f"Exit code: `{st.session_state['last_result'].returncode}`")


if __name__ == "__main__":
    main()
PY

cat > src/aeris/commands/gui.py <<'PY'
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

import aeris.gui


gui_app = typer.Typer(help="Launch the internal AERIS Streamlit GUI.")


@gui_app.callback()
def gui_callback() -> None:
    """GUI command group."""
    pass


@gui_app.command("run")
def gui_run(
    host: str = typer.Option("localhost", "--host", help="Streamlit server host."),
    port: int = typer.Option(8501, "--port", help="Streamlit server port."),
    headless: bool = typer.Option(True, "--headless/--browser", help="Run Streamlit without opening a browser automatically."),
) -> None:
    """
    Launch the AERIS internal operator GUI.

    Install GUI dependencies first:
        pip install -r requirements-gui.txt
    """
    gui_pkg_dir = Path(aeris.gui.__file__).resolve().parent
    app_path = gui_pkg_dir / "app.py"

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--server.headless",
        "true" if headless else "false",
    ]
    try:
        raise typer.Exit(code=subprocess.call(command))
    except FileNotFoundError:
        typer.secho(
            "[AERIS] Streamlit is not installed. Run: pip install -r requirements-gui.txt",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
PY

python - <<'PY'
from pathlib import Path
path = Path('src/aeris/cli.py')
if not path.exists():
    raise SystemExit('src/aeris/cli.py not found. Run this patch from the AERIS repo root.')
text = path.read_text(encoding='utf-8')

if 'from aeris.commands.gui import gui_app' not in text:
    # Prefer placing GUI import near the other command imports.
    anchors = [
        'from aeris.commands.geometry import geometry_app\n',
        'from aeris.commands.ml import ml_app\n',
    ]
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + 'from aeris.commands.gui import gui_app\n')
            break
    else:
        text = text.replace('import typer\n', 'import typer\n\nfrom aeris.commands.gui import gui_app\n')

if 'app.add_typer(gui_app, name="gui")' not in text:
    anchors = [
        'app.add_typer(geometry_app, name="geometry")\n',
        'app.add_typer(dataset_app, name="dataset")\n',
    ]
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + 'app.add_typer(gui_app, name="gui")\n')
            break
    else:
        text += '\napp.add_typer(gui_app, name="gui")\n'

if '- gui = launch local Streamlit operator cockpit' not in text:
    text = text.replace(
        '        "- geometry = generate or visualize one geometry\\n"\n',
        '        "- geometry = generate or visualize one geometry\\n"\n'
        '        "- gui = launch local Streamlit operator cockpit\\n"\n',
    )

path.write_text(text, encoding='utf-8')
PY

cat > tests/commands/test_gui_cli.py <<'PY'
from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app


def test_gui_help_is_registered_without_streamlit_import_requirement():
    runner = CliRunner()
    result = runner.invoke(app, ["--no-check-writable", "gui", "--help"])
    assert result.exit_code == 0
    assert "run" in result.output


def test_gui_run_help_is_registered():
    runner = CliRunner()
    result = runner.invoke(app, ["--no-check-writable", "gui", "run", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output


def test_gui_app_source_contains_core_operator_tabs():
    source = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")
    assert "Config Lab" in source
    assert "Unified aero dataset" in source
    assert "control-input" in source or "control input" in source
    assert "ML" in source
PY

python -m py_compile src/aeris/gui/app.py src/aeris/commands/gui.py

cat <<'TXT'

AERIS GUI v0.2 patch installed.

Next commands:
  pip install -r requirements-gui.txt
  pytest tests/commands/test_gui_cli.py
  aeris --no-check-writable gui --help
  aeris --no-check-writable gui run --host localhost --port 8501

Open:
  http://localhost:8501

TXT
