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

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional GUI dependency
    pd = None

try:
    import yaml
except Exception:  # pragma: no cover - optional GUI dependency
    yaml = None


APP_VERSION = "0.5.0"
DEFAULT_FEATURES = "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg"
DEFAULT_TARGETS = "cl,cd,cm"
DEFAULT_PAIR_KEYS = "geometry_id,alpha_deg,velocity_mps,altitude_m,control_input_deg"
MODEL_TYPES = ["linear_regression", "ridge", "random_forest", "gradient_boosting", "extra_trees", "hist_gradient_boosting"]
SAMPLERS = ["lhs_v1", "random_v1"]
QC_PRESETS = ["off", "debug", "production", "promotion_strict"]
QC_PROFILES = ["basic", "strict"]
RETENTION_POLICIES = ["all", "failures_only", "none"]
SPACING = ["equal", "cosine"]
SOURCE_POLICIES = ["auto", "native", "reconstruct"]


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


# -----------------------------------------------------------------------------
# Paths, files, and execution helpers
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
    return sorted([p for p in root.glob(pattern) if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)


def _latest_files(root: Path, pattern: str = "*") -> list[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.glob(pattern) if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)


def _path_text(path: Path | str | None) -> str:
    if path is None:
        return ""
    return str(path)


def _read_text(path: Path, limit: int = 250_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception as exc:
        return f"<could not read {path}: {exc}>"


def _read_json(path: Path) -> Any | None:
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


def _write_yaml(path: Path, data: Any) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install PyYAML")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _quote_command(command: Iterable[str]) -> str:
    try:
        return shlex.join([str(x) for x in command])
    except Exception:
        return " ".join([str(x) for x in command])


def _parse_extra_args(text: str) -> list[str]:
    if not text.strip():
        return []
    try:
        return shlex.split(text)
    except Exception as exc:
        st.error(f"Could not parse advanced arguments: {exc}")
        return []


def _append_flag(args: list[str], flag: str, value: Any | None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        args.extend([flag, text])


def _append_bool(args: list[str], truthy_flag: str, falsey_flag: str | None, value: bool | None) -> None:
    if value is None:
        return
    if value:
        args.append(truthy_flag)
    elif falsey_flag:
        args.append(falsey_flag)


def _csv_count(text: str) -> int:
    return max(1, len([x for x in text.split(",") if x.strip()]))


def _estimate_cases(*fields: str) -> int:
    n = 1
    for field in fields:
        n *= _csv_count(field)
    return n


def _run_command(*, project_root: Path, aeris_executable: str, args: Iterable[str], timeout_sec: int) -> CommandResult:
    command = [aeris_executable, "--no-check-writable", *[str(a) for a in args]]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        return CommandResult(command, completed.returncode, completed.stdout, completed.stderr)
    except FileNotFoundError as exc:
        return CommandResult(command, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command,
            124,
            exc.stdout or "",
            (exc.stderr or "") + f"\nCommand timed out after {timeout_sec} s.",
        )


def _remember_result(result: CommandResult) -> None:
    st.session_state["last_result"] = result
    history = st.session_state.setdefault("command_history", [])
    history.insert(0, result)
    del history[50:]


def _show_result(result: CommandResult, *, advanced: bool = False) -> None:
    if result.returncode == 0:
        st.success("Task completed successfully.")
    else:
        st.error(f"Task failed. Exit code: {result.returncode}")

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if stdout:
        with st.expander("Result details", expanded=result.returncode != 0):
            st.code(stdout[-120_000:], language="text")
    if stderr:
        with st.expander("Errors / warnings", expanded=True):
            st.code(stderr[-120_000:], language="text")
    if advanced:
        with st.expander("Advanced: executed command", expanded=False):
            st.code(_quote_command(result.command), language="bash")


def _task_panel(
    *,
    title: str,
    purpose: str,
    args: list[str],
    project_root: Path,
    aeris_executable: str,
    timeout_sec: int,
    dry_run: bool,
    advanced: bool,
    button_label: str = "Run task",
    key: str,
    danger: bool = False,
) -> None:
    with st.container(border=True):
        st.subheader(title)
        st.write(purpose)
        if advanced:
            with st.expander("Advanced: command that will be executed", expanded=False):
                st.code(_quote_command([aeris_executable, "--no-check-writable", *args]), language="bash")
        if dry_run:
            st.info("Dry-run is enabled. This task will not execute until you turn dry-run off in the sidebar.")
            return
        if st.button(button_label, key=key, type="primary" if not danger else "secondary"):
            if not _repo_exists(project_root):
                st.error("This does not look like an AERIS repo. Missing src/aeris under the selected project root.")
                return
            with st.spinner("Running AERIS task..."):
                result = _run_command(project_root=project_root, aeris_executable=aeris_executable, args=args, timeout_sec=timeout_sec)
            _remember_result(result)
            _show_result(result, advanced=advanced)


def _select_dir(label: str, root: Path, *, key: str, help_text: str = "", allow_manual: bool = True) -> str:
    dirs = _latest_dirs(root)
    options = [""] + [str(p) for p in dirs[:200]]
    selected = st.selectbox(label, options, index=1 if len(options) > 1 else 0, key=f"{key}_select", help=help_text)
    if allow_manual:
        return st.text_input("Path override", value=selected, key=f"{key}_manual")
    return selected


def _select_file(label: str, root: Path, pattern: str, *, key: str, default: str = "") -> str:
    files = _latest_files(root, pattern)
    options = [default] + [str(p) for p in files[:200]]
    selected = st.selectbox(label, options, index=0, key=f"{key}_select")
    return st.text_input("File override", value=selected, key=f"{key}_manual")


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
        with st.expander("Quick plot", expanded=False):
            y_cols = st.multiselect("Numeric columns", numeric_cols, default=numeric_cols[: min(3, len(numeric_cols))], key=f"plot_{path}")
            if y_cols:
                st.line_chart(df[y_cols])


def _display_file(path: Path) -> None:
    if not path.exists():
        st.warning(f"File does not exist: {path}")
        return
    suffix = path.suffix.lower()
    st.caption(str(path))
    if suffix == ".json":
        payload = _read_json(path)
        st.json(payload if payload is not None else {"error": "could not read JSON"})
    elif suffix == ".csv":
        _display_dataframe(path)
    elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        st.image(str(path), use_container_width=True)
    elif suffix in {".txt", ".log", ".yaml", ".yml", ".md", ".avl"}:
        st.code(_read_text(path), language="yaml" if suffix in {".yaml", ".yml"} else "text")
    else:
        st.info("Preview not supported for this file type.")


# -----------------------------------------------------------------------------
# Sidebar and small UI helpers
# -----------------------------------------------------------------------------


def _sidebar() -> tuple[Path, str, int, bool, bool, str]:
    st.sidebar.title("AERIS")
    st.sidebar.caption(f"GUI v{APP_VERSION} — workflow cockpit")
    project_root = Path(st.sidebar.text_input("Project root", value=str(_default_project_root()))).expanduser().resolve()
    aeris_executable = st.sidebar.text_input("AERIS executable", value=shutil.which("aeris") or "aeris")
    timeout_sec = int(st.sidebar.number_input("Task timeout [s]", min_value=5, max_value=86400, value=1800, step=5))
    dry_run = st.sidebar.toggle("Dry-run", value=False, help="Prepare tasks without executing them.")
    advanced = st.sidebar.toggle("Show advanced CLI details", value=False, help="The GUI uses the AERIS CLI internally. Keep this off for normal use.")

    if _repo_exists(project_root):
        st.sidebar.success("AERIS repository detected")
    else:
        st.sidebar.error("src/aeris not found under project root")

    page_options = [
        "Home",
        "Setup & health",
        "Geometry",
        "Dataset factory",
        "Aero analysis",
        "Dynamics",
        "ML studio",
        "Multifidelity",
        "Results browser",
    ]
    if advanced:
        page_options.append("Advanced command runner")
    page = st.sidebar.radio("Workspace", page_options)
    st.sidebar.caption("Normal users should not need to copy terminal commands. Advanced details are hidden by default.")
    return project_root, aeris_executable, timeout_sec, dry_run, advanced, page


def _section_help(title: str, body: str) -> None:
    with st.expander(title, expanded=False):
        st.write(body)


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------


def page_home(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("AERIS Workflow Cockpit")
    st.write(
        "A user-friendly front end for AERIS workflows: geometry, datasets, aero, dynamics, ML trust gates, and multifidelity. "
        "It runs the existing AERIS engine underneath, but it hides terminal commands unless advanced details are enabled."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Repo", "OK" if _repo_exists(project_root) else "Missing")
    c2.metric("Datasets", len(_latest_dirs(project_root / "data" / "datasets")))
    c3.metric("Runs", len(_latest_dirs(project_root / "data" / "runs")))
    c4.metric("ML runs", len(_latest_dirs(project_root / "data" / "processed" / "ml_runs")))

    st.subheader("Common workflows")
    w1, w2, w3 = st.columns(3)
    with w1.container(border=True):
        st.markdown("**1. Generate trusted aero data**")
        st.write("Create geometry samples, run aero sweeps, QC, curate, and promote the dataset.")
    with w2.container(border=True):
        st.markdown("**2. Train and promote ML models**")
        st.write("Validate schema, train/tune/compare, promote a model, and guard inference inputs.")
    with w3.container(border=True):
        st.markdown("**3. Multifidelity correction**")
        st.write("Pair LF/HF data, train delta models, predict corrected outputs, and evaluate improvement.")

    st.subheader("Quick health check")
    _task_panel(
        title="Check installed AERIS version",
        purpose="Confirms that the selected executable can start and that the repo environment is wired correctly.",
        args=["version"],
        project_root=project_root,
        aeris_executable=aeris_executable,
        timeout_sec=timeout_sec,
        dry_run=dry_run,
        advanced=advanced,
        button_label="Check AERIS",
        key="home_version",
    )


def page_health(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("Setup & health")
    st.write("Use this page before long runs. It catches boring environment problems early, which is better than discovering them after 900 cases.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Repository")
        st.write(f"Project root: `{project_root}`")
        st.write(f"Source tree exists: `{_repo_exists(project_root)}`")
        st.write(f"Data folder: `{project_root / 'data'}`")
    with c2:
        st.subheader("Documentation")
        for rel in ["README.md", "documents/AERIS_USER_GUIDE.md", "documents/AERIS_CLI_QUICK_REFERENCE.md"]:
            p = project_root / rel
            st.write(("✅" if p.exists() else "❌") + f" `{rel}`")

    col1, col2, col3 = st.columns(3)
    with col1:
        _task_panel(title="AERIS version", purpose="Basic package/CLI check.", args=["version"], project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="health_version")
    with col2:
        _task_panel(title="Top-level help", purpose="Checks that Typer command registration works.", args=["--help"], project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="health_help")
    with col3:
        _task_panel(title="GUI help", purpose="Checks that the GUI launcher command is registered.", args=["gui", "run", "--help"], project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="health_gui_help")


def page_geometry(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("Geometry")
    st.write("Generate or inspect BWB geometries. The active production generator is `bwb_segmented_v1`.")
    action = st.radio("What do you want to do?", ["Generate geometry", "Visualize geometry", "Geometry info"], horizontal=True)

    if action == "Geometry info":
        _task_panel(title="Geometry system info", purpose="Shows registered geometry command information.", args=["geometry", "info"], project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="geom_info")
        return

    if action == "Generate geometry":
        config = _select_file("Geometry config", project_root / "configs" / "geometry", "*.yaml", key="geom_config", default=str(project_root / "configs" / "geometry" / "baseline_bwb.yaml"))
        output_name = st.text_input("Optional output name", value="", help="Leave empty for automatic timestamped run folder.")
        save_plot = st.checkbox("Save planform plot", value=True)
        build_asb = st.checkbox("Build AeroSandbox geometry", value=True)
        extra = st.text_input("Advanced extra options", value="", help="Optional additional geometry command options.")
        args = ["geometry", "generate", "--config", config]
        _append_flag(args, "--output-name", output_name)
        _append_bool(args, "--save-plot", "--no-save-plot", save_plot)
        _append_bool(args, "--build-aerosandbox", "--no-build-aerosandbox", build_asb)
        args += _parse_extra_args(extra)
        _task_panel(title="Generate one geometry", purpose="Creates a single deterministic geometry run with artifacts and manifest.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="geom_generate")
        return

    source_mode = st.selectbox("Geometry source", ["latest run", "dataset geometry", "manual path"])
    if source_mode == "latest run":
        run_dir = _select_dir("Run directory", project_root / "data" / "runs", key="geom_vis_run")
        args = ["geometry", "visualize", "--run-dir", run_dir]
    elif source_mode == "dataset geometry":
        dataset = _select_dir("Dataset root", project_root / "data" / "datasets", key="geom_vis_dataset")
        geometry_id = st.text_input("Geometry ID", value="geom_00000")
        args = ["geometry", "visualize", "--dataset", dataset, "--geometry-id", geometry_id]
    else:
        case_dir = st.text_input("Geometry/case directory", value=str(project_root / "data" / "runs"))
        args = ["geometry", "visualize", "--case-dir", case_dir]
    save_path = st.text_input("Optional image output path", value="")
    draw_3d = st.checkbox("Draw 3D geometry", value=True)
    show_plot = st.checkbox("Show plot window", value=False)
    _append_flag(args, "--save-path", save_path)
    _append_bool(args, "--draw-3d", "--no-draw-3d", draw_3d)
    _append_bool(args, "--show-plot", "--no-show-plot", show_plot)
    _task_panel(title="Visualize geometry", purpose="Replays an existing geometry artifact for inspection.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="geom_visualize")


def page_dataset(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("Dataset factory")
    st.write("Create geometry datasets, unified aero datasets, run QC, curate, and promote. This is the data trust chain.")
    action = st.radio("Workflow", ["Geometry dataset", "Unified aero dataset", "Inspect / QC", "Curate / promote", "Training data utilities"], horizontal=False)

    if action == "Geometry dataset":
        config = _select_file("Geometry config", project_root / "configs" / "geometry", "*.yaml", key="ds_geo_config", default=str(project_root / "configs" / "geometry" / "wing_bwb.yaml"))
        c1, c2, c3 = st.columns(3)
        n = c1.number_input("Number of geometries", min_value=1, value=20, step=1)
        sampler = c2.selectbox("Sampler", SAMPLERS)
        seed = c3.number_input("Sampler seed", min_value=0, value=123, step=1)
        name = st.text_input("Dataset name", value="gui_geometry_dataset")
        save_plot = st.checkbox("Save plots", value=False)
        build_asb = st.checkbox("Build AeroSandbox geometry", value=True)
        extra = st.text_input("Advanced extra options", value="")
        args = ["dataset", "generate", "--config", config, "--n", str(int(n)), "--sampler", sampler, "--sampler-seed", str(int(seed)), "--name", name]
        _append_bool(args, "--save-plot", "--no-save-plot", save_plot)
        _append_bool(args, "--build-aerosandbox", "--no-build-aerosandbox", build_asb)
        args += _parse_extra_args(extra)
        _task_panel(title="Generate geometry dataset", purpose="Builds many deterministic geometry cases and metadata rows.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ds_generate")
        return

    if action == "Unified aero dataset":
        config = _select_file("Geometry config", project_root / "configs" / "geometry", "*.yaml", key="ds_aero_config", default=str(project_root / "configs" / "geometry" / "wing_bwb.yaml"))
        st.caption("control input means control-surface deflection in degrees when supported by the aero solver.")
        c1, c2, c3, c4 = st.columns(4)
        n = c1.number_input("Geometries", min_value=1, value=10, step=1)
        sampler = c2.selectbox("Sampler", SAMPLERS, key="aero_ds_sampler")
        seed = c3.number_input("Sampler seed", min_value=0, value=123, step=1, key="aero_ds_seed")
        name = c4.text_input("Dataset name", value="gui_aero_dataset")
        alpha = st.text_input("AoA values [deg]", value="-2,0,2,4,6")
        beta = st.text_input("Sideslip values beta [deg]", value="0")
        velocity = st.text_input("Velocity values [m/s]", value="28")
        altitude = st.text_input("Altitude values [m]", value="1500")
        control = st.text_input("Control input values [deg]", value="-5,0,5")
        p, q, r = st.columns(3)
        p_values = p.text_input("p values [rad/s]", value="0")
        q_values = q.text_input("q values [rad/s]", value="0")
        r_values = r.text_input("r values [rad/s]", value="0")
        estimated = int(n) * _estimate_cases(alpha, beta, velocity, altitude, control, p_values, q_values, r_values)
        st.info(f"Estimated aero cases: {estimated:,}")
        c5, c6, c7 = st.columns(3)
        qc_preset = c5.selectbox("QC preset", QC_PRESETS, index=2)
        retention = c6.selectbox("Retain aero run folders", RETENTION_POLICIES, index=1)
        timeout_case = c7.number_input("Per-case timeout [s]", min_value=5, value=180, step=5)
        panel_span = st.number_input("Spanwise panel resolution", min_value=1, value=4, step=1)
        panel_chord = st.number_input("Chordwise panel resolution", min_value=1, value=8, step=1)
        extra = st.text_input("Advanced extra options", value="", key="aero_ds_extra")
        args = [
            "dataset", "aero-generate", "--config", config, "--n", str(int(n)), "--sampler", sampler, "--sampler-seed", str(int(seed)), "--name", name,
            "--alpha-values", alpha, "--beta-values", beta, "--velocity-values", velocity, "--altitude-values", altitude,
            "--control-input-values", control, "--p-values", p_values, "--q-values", q_values, "--r-values", r_values,
            "--solver", "aerosandbox_avl", "--timeout-sec", str(int(timeout_case)), "--spanwise-resolution", str(int(panel_span)), "--chordwise-resolution", str(int(panel_chord)),
            "--retain-aero-runs", retention, "--qc-preset", qc_preset,
        ]
        args += _parse_extra_args(extra)
        _task_panel(title="Generate unified aero dataset", purpose="Generates geometries, runs aero sweeps, records successes/failures, and writes a dataset ready for QC/curation.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ds_aero_generate")
        return

    if action == "Inspect / QC":
        dataset = _select_dir("Dataset root", project_root / "data" / "datasets", key="ds_qc_dataset")
        qc_kind = st.selectbox("Action", ["inspect", "geometry QC", "aero QC"])
        if qc_kind == "inspect":
            args = ["dataset", "inspect", "--dataset", dataset]
        elif qc_kind == "geometry QC":
            profile = st.selectbox("Geometry QC profile", QC_PROFILES)
            args = ["dataset", "qc", "--dataset", dataset, "--profile", profile]
        else:
            profile = st.selectbox("Aero QC profile", QC_PROFILES)
            args = ["dataset", "aero-qc", "--dataset", dataset, "--profile", profile]
        _task_panel(title="Inspect or QC dataset", purpose="Reads dataset artifacts and/or runs quality checks.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ds_inspect_qc")
        return

    if action == "Curate / promote":
        dataset = _select_dir("Aero dataset root", project_root / "data" / "datasets", key="ds_promote_dataset")
        task = st.selectbox("Trust-chain task", ["curate-aero", "promote-aero", "require-promoted-aero"])
        args = ["dataset", task, "--dataset", dataset]
        if task == "promote-aero":
            force = st.checkbox("Force promotion", value=False, help="Use only when you deliberately accept blockers. Not for normal trusted work.")
            _append_bool(args, "--force", None, force)
        _task_panel(title="Dataset trust-chain task", purpose="Curate and promote only data that is suitable for downstream ML.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ds_trust_task", danger=task == "promote-aero")
        return

    dataset = _select_dir("Promoted dataset root", project_root / "data" / "datasets", key="ds_training_dataset")
    features = st.text_input("Feature columns", value=DEFAULT_FEATURES)
    targets = st.text_input("Target columns", value=DEFAULT_TARGETS)
    utility = st.selectbox("Utility", ["training-data", "split-training-data"])
    args = ["dataset", utility, "--dataset", dataset, "--features", features, "--targets", targets]
    if utility == "split-training-data":
        split_method = st.selectbox("Split method", ["grouped", "random"])
        group_column = st.text_input("Group column", value="geometry_id")
        seed = st.number_input("Random seed", min_value=0, value=123, step=1)
        args += ["--method", split_method, "--group-column", group_column, "--random-seed", str(int(seed))]
    _task_panel(title="Training-data utility", purpose="Builds or splits training-ready data from a promoted dataset.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ds_training_util")


def page_aero(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("Aero analysis")
    st.write("Run AVL/AeroSandbox scalar aero cases and sweeps from a config, run directory, or dataset geometry.")
    action = st.radio("Workflow", ["Single run", "Sweep", "Inspect"], horizontal=True)

    if action == "Inspect":
        run_dir = _select_dir("Aero run or sweep directory", project_root / "data" / "runs", key="aero_inspect_run")
        inspect_type = st.selectbox("Inspect type", ["single aero run", "sweep", "sweep case"])
        if inspect_type == "single aero run":
            args = ["aero", "inspect", "--run-dir", run_dir]
        elif inspect_type == "sweep":
            args = ["aero", "sweep-inspect", "--run-dir", run_dir]
        else:
            case_id = st.text_input("Case ID or case folder", value="case_0000")
            args = ["aero", "sweep-case-inspect", "--run-dir", run_dir, "--case-id", case_id]
        _task_panel(title="Inspect aero result", purpose="Reads saved aero result artifacts without rerunning the solver.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="aero_inspect")
        return

    source = st.selectbox("Geometry source", ["config", "run-dir", "dataset"])
    args = ["aero", "run" if action == "Single run" else "sweep"]
    if source == "config":
        config = _select_file("Geometry config", project_root / "configs" / "geometry", "*.yaml", key=f"aero_{action}_config", default=str(project_root / "configs" / "geometry" / "baseline_bwb.yaml"))
        args += ["--config", config]
    elif source == "run-dir":
        run_dir = _select_dir("Geometry run directory", project_root / "data" / "runs", key=f"aero_{action}_run")
        args += ["--run-dir", run_dir]
    else:
        dataset = _select_dir("Geometry dataset root", project_root / "data" / "datasets", key=f"aero_{action}_dataset")
        geometry_id = st.text_input("Geometry ID", value="geom_00000", key=f"aero_{action}_geom")
        args += ["--dataset", dataset, "--geometry-id", geometry_id]

    if action == "Single run":
        c1, c2, c3, c4 = st.columns(4)
        alpha = c1.number_input("AoA alpha [deg]", value=4.0)
        beta = c2.number_input("Sideslip beta [deg]", value=0.0)
        velocity = c3.number_input("Velocity [m/s]", value=28.0)
        altitude = c4.number_input("Altitude [m]", value=1500.0)
        control = st.number_input("Control input [deg]", value=0.0)
        p, q, r = st.columns(3)
        p_val = p.number_input("p [rad/s]", value=0.0)
        q_val = q.number_input("q [rad/s]", value=0.0)
        r_val = r.number_input("r [rad/s]", value=0.0)
        args += ["--alpha", str(alpha), "--beta", str(beta), "--velocity", str(velocity), "--altitude", str(altitude), "--control-input-deg", str(control), "--p", str(p_val), "--q", str(q_val), "--r", str(r_val)]
    else:
        alpha = st.text_input("AoA alpha values [deg]", value="-2,0,2,4,6")
        beta = st.text_input("Sideslip beta values [deg]", value="0")
        velocity = st.text_input("Velocity values [m/s]", value="28")
        altitude = st.text_input("Altitude values [m]", value="1500")
        control = st.text_input("Control input values [deg]", value="-5,0,5")
        estimated = _estimate_cases(alpha, beta, velocity, altitude, control)
        st.info(f"Estimated cases for this single geometry: {estimated:,}")
        args += ["--alpha-values", alpha, "--beta-values", beta, "--velocity-values", velocity, "--altitude-values", altitude, "--control-input-values", control]

    c5, c6, c7 = st.columns(3)
    panel_span = c5.number_input("Spanwise panels", min_value=1, value=4, step=1, key=f"aero_{action}_span")
    panel_chord = c6.number_input("Chordwise panels", min_value=1, value=8, step=1, key=f"aero_{action}_chord")
    case_timeout = c7.number_input("Solver timeout [s]", min_value=5, value=180, step=5, key=f"aero_{action}_timeout")
    output_name = st.text_input("Optional output name", value="", key=f"aero_{action}_outname")
    args += ["--solver", "aerosandbox_avl", "--timeout-sec", str(int(case_timeout)), "--spanwise-resolution", str(int(panel_span)), "--chordwise-resolution", str(int(panel_chord))]
    _append_flag(args, "--output-name", output_name)
    _task_panel(title=f"Aero {action.lower()}", purpose="Runs the aero solver and writes structured result artifacts.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key=f"aero_{action}_run_task")


def page_dynamics(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("Dynamics")
    st.write("Build mass/CG/dynamics foundation artifacts, inspect them, estimate trim, or sweep CG. This is not a full flight simulator.")
    action = st.radio("Workflow", ["Build", "Inspect", "Trim", "CG sweep"], horizontal=True)
    run_dir = _select_dir("Aero run directory", project_root / "data" / "runs", key=f"dyn_{action}_run")

    if action == "Inspect":
        args = ["dynamics", "inspect", "--run-dir", run_dir]
    elif action == "Trim":
        args = ["dynamics", "trim", "--run-dir", run_dir]
    elif action == "CG sweep":
        c1, c2, c3 = st.columns(3)
        cg_min = c1.number_input("CG min x [m]", value=0.30)
        cg_max = c2.number_input("CG max x [m]", value=0.70)
        n = c3.number_input("Samples", min_value=2, value=21, step=1)
        args = ["dynamics", "cg-sweep", "--run-dir", run_dir, "--cg-min-m", str(cg_min), "--cg-max-m", str(cg_max), "--n", str(int(n))]
    else:
        mass_config = _select_file("Mass config", project_root / "configs" / "mass", "*.yaml", key="dyn_mass_config", default=str(project_root / "configs" / "mass" / "baseline_uav.yaml"))
        args = ["dynamics", "build", "--run-dir", run_dir, "--mass-config", mass_config]
    _task_panel(title=f"Dynamics: {action}", purpose="Creates or inspects dynamics foundation artifacts linked to aero outputs.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key=f"dyn_{action}_task")


def page_ml(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("ML studio")
    st.write("Train, tune, compare, promote, and safely use scalar surrogate models. Raw datasets are not trusted inputs.")
    action = st.radio("Workflow", ["Schema", "Train", "Tune", "Compare", "Model trust", "Predict"], horizontal=False)

    if action == "Schema":
        dataset = _select_dir("Promoted aero dataset", project_root / "data" / "datasets", key="ml_schema_dataset")
        preset = st.text_input("Feature preset", value="bwb_control")
        targets = st.text_input("Targets", value=DEFAULT_TARGETS)
        group_column = st.text_input("Group column", value="geometry_id")
        args = ["ml", "validate-schema", "--dataset", dataset, "--feature-preset", preset, "--targets", targets, "--group-column", group_column]
        _task_panel(title="Validate ML schema", purpose="Checks that a promoted dataset has the columns needed for ML.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ml_schema")
        return

    if action in {"Train", "Tune", "Compare"}:
        dataset = _select_dir("Promoted aero dataset", project_root / "data" / "datasets", key=f"ml_{action}_dataset")
        use_preset = st.checkbox("Use feature preset", value=True, key=f"ml_{action}_use_preset")
        if use_preset:
            feature_args = ["--feature-preset", st.text_input("Feature preset", value="bwb_control", key=f"ml_{action}_preset")]
        else:
            feature_args = ["--features", st.text_input("Feature columns", value=DEFAULT_FEATURES, key=f"ml_{action}_features")]
        targets = st.text_input("Targets", value=DEFAULT_TARGETS, key=f"ml_{action}_targets")
        split_method = st.selectbox("Split method", ["grouped", "random"], key=f"ml_{action}_split")
        group_column = st.text_input("Group column", value="geometry_id", key=f"ml_{action}_group")
        seed = st.number_input("Random seed", min_value=0, value=123, step=1, key=f"ml_{action}_seed")

    if action == "Train":
        model_type = st.selectbox("Model type", MODEL_TYPES, index=4)
        output_dir = st.text_input("Output directory", value=str(project_root / "data" / "processed" / "ml_runs" / "gui_train"))
        args = ["ml", "train", "--dataset", dataset, *feature_args, "--targets", targets, "--model-type", model_type, "--split-method", split_method, "--group-column", group_column, "--random-seed", str(int(seed)), "--output-dir", output_dir]
        _task_panel(title="Train scalar ML model", purpose="Trains a tabular surrogate from a promoted dataset.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ml_train")
        return

    if action == "Tune":
        backend = st.selectbox("Tuning backend", ["aeris", "optuna"], index=1)
        model_type = st.selectbox("Model type", MODEL_TYPES, index=4, key="ml_tune_model")
        n_trials = st.number_input("Trials", min_value=1, value=25, step=1)
        param_space = st.text_input("Parameter-space JSON", value=str(project_root / "configs" / "ml" / "tune_extra_trees_optuna_space.json"))
        output_dir = st.text_input("Output directory", value=str(project_root / "data" / "processed" / "ml_runs" / "gui_tune"))
        args = ["ml", "tune", "--backend", backend, "--dataset", dataset, *feature_args, "--targets", targets, "--model-type", model_type, "--param-space-json", param_space, "--n-trials", str(int(n_trials)), "--split-method", split_method, "--group-column", group_column, "--random-seed", str(int(seed)), "--output-dir", output_dir]
        _task_panel(title="Tune scalar ML model", purpose="Runs deterministic or Optuna-based hyperparameter tuning.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ml_tune")
        return

    if action == "Compare":
        models = st.multiselect("Models", MODEL_TYPES, default=["linear_regression", "ridge", "random_forest", "gradient_boosting", "extra_trees"])
        compare_type = st.selectbox("Comparison type", ["single split", "seed stability"])
        output_dir = st.text_input("Output directory", value=str(project_root / "data" / "processed" / "ml_runs" / "gui_compare"))
        if compare_type == "single split":
            args = ["ml", "compare", "--dataset", dataset, *feature_args, "--targets", targets, "--models", ",".join(models), "--split-method", split_method, "--group-column", group_column, "--random-seed", str(int(seed)), "--output-dir", output_dir]
        else:
            seeds = st.text_input("Seeds", value="101,202,303,404,505")
            args = ["ml", "compare-seeds", "--dataset", dataset, *feature_args, "--targets", targets, "--models", ",".join(models), "--seeds", seeds, "--split-method", split_method, "--group-column", group_column, "--output-dir", output_dir]
        _task_panel(title="Compare scalar ML models", purpose="Compares models and, if requested, checks whether the winner is stable across seeds.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ml_compare")
        return

    if action == "Model trust":
        model_run = _select_dir("Model run directory", project_root / "data" / "processed" / "ml_runs", key="ml_trust_model")
        trust_task = st.selectbox("Trust task", ["inspect-model", "promote-model", "require-promoted-model", "check-inference-inputs"])
        args = ["ml", trust_task, "--model-run-dir", model_run]
        if trust_task == "promote-model":
            max_rmse = st.number_input("Max test RMSE mean", value=0.001, format="%.8f")
            min_r2 = st.number_input("Min test R² mean", value=0.99, format="%.6f")
            args += ["--max-test-rmse-mean", str(max_rmse), "--min-test-r2-mean", str(min_r2)]
        if trust_task == "check-inference-inputs":
            input_csv = st.text_input("Input CSV", value=str(Path(model_run) / "train_rows.csv" if model_run else ""))
            enforce = st.checkbox("Fail on violations", value=False)
            args += ["--input-csv", input_csv]
            _append_bool(args, "--fail-on-violations", "--no-fail-on-violations", enforce)
        _task_panel(title="Model trust gate", purpose="Promotes or verifies a trained model before downstream use.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ml_trust")
        return

    model_run = _select_dir("Model run directory", project_root / "data" / "processed" / "ml_runs", key="ml_predict_model")
    input_csv = st.text_input("Input CSV", value=str(Path(model_run) / "train_rows.csv" if model_run else ""))
    output_dir = st.text_input("Output directory", value=str(Path(model_run) / "inference" / "gui_predict" if model_run else project_root / "data" / "processed" / "ml_predictions" / "gui_predict"))
    require_promoted = st.checkbox("Require promoted model", value=True)
    enforce_envelope = st.checkbox("Enforce training envelope", value=True)
    args = ["ml", "predict", "--model-run-dir", model_run, "--input-csv", input_csv, "--output-dir", output_dir]
    _append_bool(args, "--require-promoted-model", None, require_promoted)
    _append_bool(args, "--enforce-envelope", None, enforce_envelope)
    _task_panel(title="Guarded prediction", purpose="Predicts only after the selected trust gates pass.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key="ml_predict")


def page_multifidelity(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("Multifidelity")
    st.write("Build LF/HF delta datasets, train correction models, predict corrected outputs, and evaluate whether correction actually helped.")
    action = st.radio("Workflow", ["Build delta dataset", "Train delta model", "Predict delta model", "Evaluate delta model"], horizontal=False)

    if action == "Build delta dataset":
        lf_csv = st.text_input("Low-fidelity CSV", value=str(project_root / "data" / "processed" / "multifidelity" / "lf.csv"))
        hf_csv = st.text_input("High-fidelity CSV", value=str(project_root / "data" / "processed" / "multifidelity" / "hf.csv"))
        pair_keys = st.text_input("Pair keys", value=DEFAULT_PAIR_KEYS)
        targets = st.text_input("Base targets", value=DEFAULT_TARGETS)
        output_dir = st.text_input("Output directory", value=str(project_root / "data" / "processed" / "multifidelity" / "gui_delta_dataset"))
        args = ["ml", "build-delta-dataset", "--lf-csv", lf_csv, "--hf-csv", hf_csv, "--pair-keys", pair_keys, "--targets", targets, "--output-dir", output_dir]
        purpose = "Pairs LF/HF scalar rows and writes delta_dataset.csv plus a traceability report."
    elif action == "Train delta model":
        delta_dataset = _select_dir("Delta dataset directory", project_root / "data" / "processed" / "multifidelity", key="mf_delta_dataset")
        features = st.text_input("Features", value="c1_m,alpha_deg,velocity_mps,altitude_m,control_input_deg,lf__cl,lf__cd,lf__cm")
        targets = st.text_input("Base targets", value=DEFAULT_TARGETS)
        model_type = st.selectbox("Model type", MODEL_TYPES, index=4)
        output_dir = st.text_input("Output directory", value=str(project_root / "data" / "processed" / "ml_runs" / "gui_delta_model"))
        args = ["ml", "train-delta-model", "--delta-dataset", delta_dataset, "--features", features, "--base-targets", targets, "--model-type", model_type, "--split-method", "grouped", "--group-column", "geometry_id", "--output-dir", output_dir]
        purpose = "Trains a model that predicts HF-LF correction deltas."
    elif action == "Predict delta model":
        model_run = _select_dir("Delta model run", project_root / "data" / "processed" / "ml_runs", key="mf_delta_model_pred")
        input_csv = st.text_input("Input CSV", value=str(Path(model_run) / "test_rows.csv" if model_run else ""))
        output_dir = st.text_input("Output directory", value=str(Path(model_run) / "delta_inference" / "gui_predict" if model_run else ""))
        args = ["ml", "predict-delta-model", "--model-run-dir", model_run, "--input-csv", input_csv, "--output-dir", output_dir]
        purpose = "Predicts deltas and writes corrected outputs: LF + predicted delta."
    else:
        model_run = _select_dir("Delta model run", project_root / "data" / "processed" / "ml_runs", key="mf_delta_model_eval")
        output_dir = st.text_input("Output directory", value=str(Path(model_run) / "multifidelity_evaluation" if model_run else ""))
        args = ["ml", "evaluate-delta-model", "--model-run-dir", model_run, "--output-dir", output_dir]
        purpose = "Compares LF baseline error against corrected prediction error. No sugarcoating."

    _task_panel(title=action, purpose=purpose, args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=advanced, key=f"mf_{action}")


def page_results(project_root: Path) -> None:
    st.title("Results browser")
    st.write("Inspect generated artifacts without digging through folders manually.")
    root_choice = st.selectbox("Artifact root", ["runs", "datasets", "processed", "debug", "documents", "custom"])
    if root_choice == "runs":
        root = project_root / "data" / "runs"
    elif root_choice == "datasets":
        root = project_root / "data" / "datasets"
    elif root_choice == "processed":
        root = project_root / "data" / "processed"
    elif root_choice == "debug":
        root = project_root / "data" / "debug"
    elif root_choice == "documents":
        root = project_root / "documents"
    else:
        root = Path(st.text_input("Custom root", value=str(project_root / "data"))).expanduser()

    if not root.exists():
        st.warning(f"Root does not exist: {root}")
        return

    candidates = [root] + _latest_dirs(root)
    selected_root = st.selectbox("Folder", candidates[:200], format_func=lambda p: p.name if p != root else f"{p.name}/")
    files = sorted([p for p in selected_root.rglob("*") if p.is_file()])
    st.metric("Files", len(files))
    previewable = [p for p in files if p.suffix.lower() in {".json", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".log", ".yaml", ".yml", ".md", ".avl"}]
    if not previewable:
        st.info("No previewable files found.")
        return
    selected_file = st.selectbox("Preview file", previewable, format_func=lambda p: str(p.relative_to(selected_root)))
    _display_file(selected_file)


def page_config_lab(project_root: Path) -> None:
    st.title("Config Lab")
    st.write("Inspect and lightly edit YAML configs. This is for convenience, not a replacement for version-controlled config files.")
    config_path = _select_file("Config file", project_root / "configs", "*.yaml", key="config_lab", default=str(project_root / "configs" / "geometry" / "baseline_bwb.yaml"))
    path = Path(config_path).expanduser()
    if not path.exists():
        st.warning("Selected config file does not exist yet.")
    text = st.text_area("YAML content", value=_read_text(path) if path.exists() else "", height=520)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Validate YAML", type="primary"):
            if yaml is None:
                st.error("PyYAML is not installed.")
            else:
                try:
                    data = yaml.safe_load(text)
                    st.success("YAML parsed successfully.")
                    st.json(data)
                except Exception as exc:
                    st.error(f"YAML parse failed: {exc}")
    with c2:
        if st.button("Save YAML file"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            st.success(f"Saved: {path}")


def page_advanced_console(project_root: Path, aeris_executable: str, timeout_sec: int, dry_run: bool, advanced: bool) -> None:
    st.title("Advanced command runner")
    st.warning("This is for expert/debug use. Normal workflows should use the pages above.")
    raw = st.text_input("AERIS arguments", value="version", help="Example: ml inspect-model --model-run-dir data/processed/ml_runs/example")
    args = _parse_extra_args(raw)
    _task_panel(title="Run advanced AERIS task", purpose="Runs exactly the arguments above through the AERIS CLI wrapper.", args=args, project_root=project_root, aeris_executable=aeris_executable, timeout_sec=timeout_sec, dry_run=dry_run, advanced=True, key="advanced_runner")

    st.subheader("Session history")
    history = st.session_state.get("command_history", [])
    if not history:
        st.info("No tasks have been run in this session.")
        return
    for i, result in enumerate(history[:10], start=1):
        label = f"#{i} exit={result.returncode} — {_quote_command(result.command[:5])}"
        with st.expander(label, expanded=False):
            _show_result(result, advanced=True)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="AERIS", layout="wide", page_icon="✈️")
    project_root, aeris_executable, timeout_sec, dry_run, advanced, page = _sidebar()

    if page == "Home":
        page_home(project_root, aeris_executable, timeout_sec, dry_run, advanced)
    elif page == "Setup & health":
        page_health(project_root, aeris_executable, timeout_sec, dry_run, advanced)
    elif page == "Geometry":
        page_geometry(project_root, aeris_executable, timeout_sec, dry_run, advanced)
    elif page == "Dataset factory":
        page_dataset(project_root, aeris_executable, timeout_sec, dry_run, advanced)
    elif page == "Aero analysis":
        page_aero(project_root, aeris_executable, timeout_sec, dry_run, advanced)
    elif page == "Dynamics":
        page_dynamics(project_root, aeris_executable, timeout_sec, dry_run, advanced)
    elif page == "ML studio":
        page_ml(project_root, aeris_executable, timeout_sec, dry_run, advanced)
    elif page == "Multifidelity":
        page_multifidelity(project_root, aeris_executable, timeout_sec, dry_run, advanced)
    elif page == "Results browser":
        page_results(project_root)
    elif page == "Advanced command runner":
        page_advanced_console(project_root, aeris_executable, timeout_sec, dry_run, advanced)

    if "last_result" in st.session_state:
        result = st.session_state["last_result"]
        with st.sidebar.expander("Last task", expanded=False):
            st.write("✅ Success" if result.returncode == 0 else f"❌ Failed: {result.returncode}")
            if advanced:
                st.code(_quote_command(result.command), language="bash")


if __name__ == "__main__":
    main()
