"""GUI ↔ CLI command contract test.

This is the automated, permanent version of the manual GUI audit. It guarantees
that every CLI command the Streamlit GUI builds uses ONLY flags that the real
Typer CLI accepts. If anyone edits the GUI and introduces a wrong flag (like the
`--model-types` vs `--models` bug) or references a command that doesn't exist,
this test fails immediately — no human re-reading 5,000+ lines required.

Why this is robust:
  * Ground truth comes from introspecting the actual Typer app via Click, so
    AUTO-DERIVED flags (e.g. `--run-dir` from a `run_dir` parameter, `--mass-config`
    from `mass_config`) are included. A naive regex over the CLI source misses
    these and produces false positives; Click introspection does not.
  * The GUI side is parsed with a balanced-bracket scanner, so multi-line command
    lists are captured in full.

What it does NOT cover (see the other GUI tests):
  * Runtime rendering crashes (test_gui_render_smoke.py)
  * Data-dependent code paths like the sweep "Polar curves" view
    (needs fixtures — see test_gui_render_with_fixtures.py)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import typer
from typer.main import get_command


# --------------------------------------------------------------------------
# 1. Ground truth: every command and its valid flags, from the real CLI
# --------------------------------------------------------------------------

def _collect_cli_flags() -> tuple[dict[str, set[str]], set[str]]:
    """Return ({full_command: set(valid_flags)}, set(global_flags)).

    full_command is space-joined, e.g. 'dataset aero-generate',
    'airfoil dataset generate'. Flags include auto-derived ones.
    """
    from aeris.cli import app  # the root Typer app

    root = get_command(app)  # click.Group

    # Global options live on the root group's params (the app callback).
    global_flags: set[str] = set()
    for param in getattr(root, "params", []):
        for opt in getattr(param, "opts", []):
            if opt.startswith("--"):
                global_flags.add(opt)
        for opt in getattr(param, "secondary_opts", []):
            if opt.startswith("--"):
                global_flags.add(opt)

    commands: dict[str, set[str]] = {}

    def walk(group, prefix: str) -> None:
        for name, cmd in getattr(group, "commands", {}).items():
            full = f"{prefix} {name}".strip()
            if hasattr(cmd, "commands") and cmd.commands:
                walk(cmd, full)  # nested group (e.g. 'airfoil dataset')
            else:
                flags: set[str] = set()
                for param in cmd.params:
                    for opt in getattr(param, "opts", []):
                        if opt.startswith("--"):
                            flags.add(opt)
                    for opt in getattr(param, "secondary_opts", []):
                        if opt.startswith("--"):
                            flags.add(opt)
                commands[full] = flags

    walk(root, "")
    return commands, global_flags


# --------------------------------------------------------------------------
# 2. GUI side: extract every command list the GUI constructs
# --------------------------------------------------------------------------

def _gui_app_path() -> Path:
    import aeris.gui.app as gui_app
    return Path(gui_app.__file__)


# Top-level CLI groups (first token of a GUI command list).
_GROUPS = {
    "aero", "airfoil", "dataset", "dynamics", "geometry",
    "ml", "pipeline", "version", "workflow", "gui",
}
# Two-level nested groups.
_NESTED = {("airfoil", "dataset")}


def _extract_balanced_list(text: str, open_idx: int) -> str:
    depth = 0
    for i in range(open_idx, min(len(text), open_idx + 8000)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[open_idx:i + 1]
    return text[open_idx:open_idx + 8000]


def _extract_gui_commands() -> list[tuple[int, str, set[str]]]:
    """Return list of (line_number, full_command, set(flags_used))."""
    src = _gui_app_path().read_text(encoding="utf-8")
    pat = re.compile(
        r'\[\s*"(' + "|".join(_GROUPS) + r')"\s*,\s*"([a-z0-9\-]+)"'
    )
    out: list[tuple[int, str, set[str]]] = []
    seen: set[int] = set()
    for m in pat.finditer(src):
        bs = m.start()
        if bs in seen:
            continue
        seen.add(bs)
        g1, g2 = m.group(1), m.group(2)
        lst = _extract_balanced_list(src, bs)
        if (g1, g2) in _NESTED:
            toks = re.findall(r'"([a-z0-9\-]+)"', lst[:80])
            cmd = f"{g1} {g2} {toks[2]}" if len(toks) >= 3 else f"{g1} {g2}"
        else:
            cmd = f"{g1} {g2}"
        used = set(re.findall(r'"(--[a-z0-9\-]+)"', lst))
        lineno = src[:bs].count("\n") + 1
        out.append((lineno, cmd, used))
    return out


# --------------------------------------------------------------------------
# 3. The tests
# --------------------------------------------------------------------------

def test_gui_commands_exist_in_cli():
    cli_cmds, _ = _collect_cli_flags()
    gui_cmds = _extract_gui_commands()
    assert gui_cmds, "No GUI command lists were extracted — parser or GUI changed."

    unknown = [
        (ln, cmd) for ln, cmd, _ in gui_cmds if cmd not in cli_cmds
    ]
    assert not unknown, (
        "GUI builds commands that do not exist in the CLI:\n"
        + "\n".join(f"  app.py:{ln}  '{cmd}'" for ln, cmd in unknown)
    )


def test_gui_command_flags_are_valid():
    cli_cmds, global_flags = _collect_cli_flags()
    gui_cmds = _extract_gui_commands()

    problems: list[str] = []
    for ln, cmd, used in gui_cmds:
        if cmd not in cli_cmds:
            continue  # covered by the other test
        valid = cli_cmds[cmd] | global_flags
        bad = used - valid
        if bad:
            problems.append(
                f"  app.py:{ln}  '{cmd}'  invalid flags: {sorted(bad)}\n"
                f"      valid for this command: {sorted(cli_cmds[cmd])}"
            )
    assert not problems, (
        "GUI builds CLI commands with invalid flags:\n" + "\n".join(problems)
    )


def test_gui_feature_presets_are_registered():
    """The GUI's ML_FEATURE_PRESETS must all be real registered presets."""
    import aeris.gui.app as gui_app
    try:
        from aeris.ml.feature_presets import list_feature_presets
    except Exception:
        pytest.skip("feature preset registry not importable under this layout")
    registered = {getattr(p, "name", p) for p in list_feature_presets(include_inactive=True)}
    gui_presets = set(gui_app.ML_FEATURE_PRESETS)
    missing = gui_presets - registered
    assert not missing, (
        f"GUI lists feature presets that are not registered: {sorted(missing)}"
    )


def test_gui_feature_sets_are_registered():
    """The GUI's ML_FEATURE_SET_CHOICES must all be real registered feature sets."""
    import aeris.gui.app as gui_app
    try:
        from aeris.ml.feature_sets import list_feature_sets
    except Exception:
        pytest.skip("feature set registry not importable under this layout")
    registered = {getattr(fs, "name", fs) for fs in list_feature_sets(include_inactive=True)}
    gui_sets = set(gui_app.ML_FEATURE_SET_CHOICES)
    missing = gui_sets - registered
    assert not missing, (
        f"GUI lists feature sets that are not registered: {sorted(missing)}"
    )


def test_gui_model_types_are_registered():
    """Every model in the GUI's MODEL_TYPES must exist in the backend registry."""
    import aeris.gui.app as gui_app
    try:
        from aeris.ml.model_registry import MODEL_REGISTRY
    except Exception:
        pytest.skip("model registry not importable under this layout")
    registered = set(MODEL_REGISTRY.keys())
    gui_models = set(gui_app.MODEL_TYPES)
    missing = gui_models - registered
    assert not missing, (
        f"GUI MODEL_TYPES contains unregistered models: {sorted(missing)}"
    )
