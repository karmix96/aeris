"""AVL output-file parsers — pure text/pandas, AeroSandbox-free.

Every AVL run writes a family of ASCII dumps (``ft``/``fn``/``fs``/``fe``/``vm``/
``fb``/``hm``/``st``/``sb``). This module owns the parsing of all of them, so the
native pyGeo→AVL path and the AeroSandbox reference path read AVL through the
*same* validated parser rather than two divergent copies.

Nothing here imports aerosandbox; the only third-party dependency is pandas (for
the strip table). ``aerosandbox_avl`` re-exports these under its historical
private names so existing imports keep working.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

__all__ = [
    "to_float_or_none",
    "parse_totals_text",
    "parse_stability_file",
    "normalize_stability_key",
    "extract_stability_axis_derivatives",
    "extract_body_axis_derivatives",
    "extract_control_derivatives",
    "compute_derived_metrics",
    "read_avl_strips",
    "parse_hinge_moments",
    "parse_surface_forces",
    "parse_strip_shear_moment",
    "STABILITY_DERIVATIVE_KEYS",
    "BODY_DERIVATIVE_KEYS",
]

# AVL prints ``key = value`` with keys such as CLa, pb/2V, Cl'tot, e, CDffd01.
_KV_PATTERN = re.compile(r"([A-Za-z][A-Za-z0-9'/_.\-]*)\s*=\s*([-+]?[0-9.]+(?:[EeDd][-+]?\d+)?)")

STABILITY_DERIVATIVE_KEYS = [
    # Stability-axis static derivatives
    "CLa", "CLb",
    "CYa", "CYb",
    "Cla", "Clb",
    "Cma", "Cmb",
    "Cna", "Cnb",
    # Stability-axis rate derivatives
    "CLp", "CLq", "CLr",
    "CYp", "CYq", "CYr",
    "Clp", "Clq", "Clr",
    "Cmp", "Cmq", "Cmr",
    "Cnp", "Cnq", "Cnr",
    # Common scalar printed in the stability file
    "Xnp",
]

BODY_DERIVATIVE_KEYS = [
    "CXu", "CXv", "CXw",
    "CYu", "CYv", "CYw",
    "CZu", "CZv", "CZw",
    "Clu", "Clv", "Clw",
    "Cmu", "Cmv", "Cmw",
    "Cnu", "Cnv", "Cnw",
]

# Force/moment prefixes AVL prints for each control derivative column.
_CONTROL_DERIV_PREFIXES = ("CL", "CY", "Cl", "Cm", "Cn", "CDff", "e")


def to_float_or_none(value: Any) -> float | None:
    try:
        val = float(value)
        if not math.isfinite(val):
            return None
        return val
    except Exception:
        return None


def parse_totals_text(text: str) -> dict[str, float]:
    """Scrape every ``key = value`` pair out of an AVL totals (``ft``) dump.

    Returns the AVL key names verbatim (``CLtot``, ``CDind``, ``e``, ``Sref``,
    ``pb/2V``, and one entry per control surface). First occurrence wins, so the
    reference block at the top of the file is not clobbered by later sections.
    """
    out: dict[str, float] = {}
    for match in _KV_PATTERN.finditer(text):
        key = match.group(1).strip()
        val = to_float_or_none(match.group(2).replace("D", "E").replace("d", "e"))
        if val is None or key in out:
            continue
        out[key] = val
    return out


def parse_stability_file(stab_path: "Path | str") -> dict[str, float]:
    """Parse an AVL ``st``/``sb`` dump into a flat {key: value} dict.

    Keeps AVL's own key spelling and additionally stores a normalised alias
    (``CL_a`` → ``CLa``) when one applies. First occurrence wins.
    """
    text = Path(stab_path).read_text()
    out: dict[str, float] = {}

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Composite metric printed as its own line; parse it explicitly so the
        # generic scrape does not mistake the trailing token for Cnb.
        if "Clb Cnr / Clr Cnb" in stripped and "=" in stripped:
            lhs, rhs = stripped.split("=", 1)
            try:
                out[lhs.strip()] = float(rhs.strip().split()[0])
            except Exception:
                pass
            continue

        for match in _KV_PATTERN.finditer(line):
            raw_key = match.group(1).strip()
            val = to_float_or_none(match.group(2))
            if val is None:
                continue
            if raw_key not in out:
                out[raw_key] = val
            normalized = normalize_stability_key(raw_key)
            if normalized is not None and normalized not in out:
                out[normalized] = val

    return out


def normalize_stability_key(key: str) -> str | None:
    k = key.strip()

    alias_map = {
        "CL_a": "CLa",
        "Cm_a": "Cma",
        "CY_b": "CYb",
        "Cl_b": "Clb",
        "Cn_b": "Cnb",
        "Cl_p": "Clp",
        "Cm_q": "Cmq",
        "Cn_r": "Cnr",
        "Cl_r": "Clr",
        "Cn_p": "Cnp",
        "CLu": "CLu",
        "Cmu": "Cmu",
        "CYp": "CYp",
        "CYr": "CYr",
    }
    if k in alias_map:
        return alias_map[k]

    compressed = re.sub(r"[^A-Za-z0-9]", "", k)

    canonical_targets = {
        "CLa", "Cma", "CYb", "Clb", "Cnb",
        "Clp", "Cmq", "Cnr", "Clr", "Cnp",
        "CLu", "Cmu", "CYp", "CYr",
    }
    if compressed in canonical_targets:
        return compressed

    return None


def extract_stability_axis_derivatives(parsed: dict[str, Any]) -> dict[str, float | None]:
    """Pull the canonical stability-axis derivative set out of a parsed ``st``."""
    parsed = parsed or {}
    return {key: to_float_or_none(parsed.get(key)) for key in STABILITY_DERIVATIVE_KEYS}


def extract_body_axis_derivatives(parsed: dict[str, Any]) -> dict[str, float | None]:
    """Pull the canonical body/geometry-axis derivative set out of a parsed ``sb``."""
    parsed = parsed or {}
    return {key: to_float_or_none(parsed.get(key)) for key in BODY_DERIVATIVE_KEYS}


def extract_control_derivatives(
    stab_text: str, parsed: dict[str, Any] | None = None
) -> dict[str, dict[str, float | None]]:
    """Map AVL's ``d01``/``d02`` control-derivative columns onto control names.

    AVL prints a header row pairing each control with its slot, e.g.::

        elevon_sym   d01     elevon_diff  d02

    and then ``CLd01``, ``Cmd01``, ``Cld02``, … Returns
    ``{control_name: {"CL": …, "CY": …, "Cl": …, "Cm": …, "Cn": …, "CDff": …,
    "e": …}}`` — the control-authority derivatives the elevon sizing needs.
    """
    parsed = parsed if parsed is not None else {}
    slots: dict[str, str] = {}
    for line in stab_text.splitlines():
        for name, slot in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s+(d\d+)\b", line):
            slots.setdefault(slot, name)

    out: dict[str, dict[str, float | None]] = {}
    for slot, name in slots.items():
        entry: dict[str, float | None] = {}
        for prefix in _CONTROL_DERIV_PREFIXES:
            entry[prefix] = to_float_or_none(parsed.get(f"{prefix}{slot}"))
        entry["avl_slot"] = slot  # type: ignore[assignment]
        out[name] = entry
    return out


def compute_derived_metrics(
    stability_axis_derivatives: dict[str, float | None],
) -> dict[str, float | None]:
    """Derived stability metrics. ``spiral_metric`` = Clb·Cnr / (Clr·Cnb) > 1 is
    the classic spiral-stability criterion."""
    clb = stability_axis_derivatives.get("Clb")
    cnr = stability_axis_derivatives.get("Cnr")
    clr = stability_axis_derivatives.get("Clr")
    cnb = stability_axis_derivatives.get("Cnb")

    spiral_metric: float | None = None
    try:
        if None not in (clb, cnr, clr, cnb) and clr != 0.0 and cnb != 0.0:
            spiral_metric = float((clb * cnr) / (clr * cnb))
    except Exception:
        spiral_metric = None

    return {"spiral_metric": spiral_metric}


def read_avl_strips(filepath: "str | Path", alpha_deg: float | None = None) -> pd.DataFrame:
    """Parse an AVL strip-forces (``fs``) dump into a tidy DataFrame."""
    lines = Path(filepath).read_text().splitlines()
    rows: list[dict[str, Any]] = []
    surface_id = None
    header_cols = None

    for line in lines:
        m = re.search(r"Surface\s*#\s*(\d+)", line, re.IGNORECASE)
        if m:
            surface_id = int(m.group(1))
            header_cols = None
            continue

        if ("Strip" in line or re.search(r"\bj\b", line)) and "Chord" in line:
            header_cols = re.findall(r"[A-Za-z0-9'_/.-]+", line)
            continue

        if header_cols and re.match(r"\s*\d+\s", line):
            tokens = re.findall(r"[A-Za-z0-9'_/.-]+", line)
            if len(tokens) >= len(header_cols):
                row = dict(zip(header_cols, tokens[:len(header_cols)]))
                row["surface"] = surface_id
                rows.append(row)

    if not rows:
        raise ValueError(f"No strip data found in {filepath}")

    df = pd.DataFrame(rows)
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    rename_map = {
        "Strip": "strip",
        "j": "strip",
        "Xle": "x_le",
        "Yle": "y_le",
        "Zle": "z_le",
        "Chord": "chord",
        "Area": "area",
        "ai": "alpha_induced",
        "cl": "cl_local",
        "cd": "cd_local",
        "cm_c/4": "cm_c4",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "strip" in df.columns:
        df["strip"] = pd.to_numeric(df["strip"], errors="coerce").astype("Int64")

    if alpha_deg is not None:
        df["alpha_deg"] = float(alpha_deg)

    return df


def parse_hinge_moments(path: "str | Path") -> dict[str, float]:
    """Parse an AVL hinge-moment (``hm``) dump: {control_name: Chinge}.

    Chinge is referred to Sref·Cref; it is the actuator-sizing quantity for the
    elevon.
    """
    out: dict[str, float] = {}
    for line in Path(path).read_text().splitlines():
        m = re.match(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+([-+]?[0-9.]+(?:[EeDd][-+]?\d+)?)\s*$", line
        )
        if not m:
            continue
        val = to_float_or_none(m.group(2).replace("D", "E").replace("d", "e"))
        if val is not None:
            out[m.group(1)] = val
    return out


def parse_surface_forces(path: "str | Path") -> dict[str, list[dict[str, Any]]]:
    """Parse an AVL surface-forces (``fn``) dump.

    Returns ``{"referred_to_sref": [...], "referred_to_ssurf": [...]}`` — one
    row per surface. The first table is normalised on Sref/Cref/Bref (so the
    rows sum to the totals); the second on each surface's own area.
    """
    sref_rows: list[dict[str, Any]] = []
    ssurf_rows: list[dict[str, Any]] = []
    mode: str | None = None

    sref_cols = ["n", "area", "cl", "cd", "cm", "cy", "cn", "cl_roll", "cdi", "cdv"]
    ssurf_cols = ["n", "ssurf", "cave", "cl", "cd", "cdv"]

    for line in Path(path).read_text().splitlines():
        if "Area" in line and "CDi" in line:
            mode = "sref"
            continue
        if "Ssurf" in line and "Cave" in line:
            mode = "ssurf"
            continue
        if not re.match(r"\s*\d+\s", line):
            continue

        tokens = line.split()
        cols = sref_cols if mode == "sref" else ssurf_cols
        if len(tokens) < len(cols):
            continue
        row: dict[str, Any] = {}
        for col, tok in zip(cols, tokens[: len(cols)]):
            row[col] = to_float_or_none(tok)
        row["name"] = " ".join(tokens[len(cols):]).strip() or None
        (sref_rows if mode == "sref" else ssurf_rows).append(row)

    return {"referred_to_sref": sref_rows, "referred_to_ssurf": ssurf_rows}


def parse_strip_shear_moment(path: "str | Path") -> pd.DataFrame:
    """Parse an AVL shear/bending (``vm``) dump — the structural loads column.

    Columns: ``surface``, ``two_y_over_bref``, ``vz_over_q_sref``,
    ``mx_over_q_bref_sref``.
    """
    rows: list[dict[str, Any]] = []
    surface_id = None
    in_table = False

    for line in Path(path).read_text().splitlines():
        m = re.search(r"Surface:\s*(\d+)", line)
        if m:
            surface_id = int(m.group(1))
            in_table = False
            continue
        if "2Y/Bref" in line:
            in_table = True
            continue
        if not in_table:
            continue
        tokens = line.split()
        if len(tokens) != 3:
            continue
        vals = [to_float_or_none(t) for t in tokens]
        if any(v is None for v in vals):
            continue
        rows.append(
            {
                "surface": surface_id,
                "two_y_over_bref": vals[0],
                "vz_over_q_sref": vals[1],
                "mx_over_q_bref_sref": vals[2],
            }
        )

    return pd.DataFrame(rows)
