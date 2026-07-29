"""Shared runner for the AVL panelling study (RUNBOOK_avl_panelling_study_v2.md).

Every stage imports this module so the stages are comparable by construction.
Nothing here decides anything the runbook fixes in Stage 0 — this file only
*executes* one AVL solve, caches it on a full-provenance hash, guards it, and
returns the frozen quantity list (§4.3) as a flat dict of scalars.

Rules enforced here (see the runbook):
  §0.4  status == "SUCCESS" is asserted before any arithmetic downstream.
  §3.3  AVL's hard limits (strips <= 500, vortices <= 6000) are asserted BEFORE
        the .avl is written; an illegal request aborts rather than letting AVL
        fail silently.
  §4.1  sections are built once per sample and reused across panellings.
  §4.2  cache hash is the full provenance pre-image; on a hit the provenance is
        re-read and asserted field-by-field.
  §4.3  the frozen quantity list, no additions, no removals.
  §5    the solver is deterministic; no run-to-run averaging anywhere.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

from aeris.aero.models import FlightCondition
from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
    build_pygeo_sections_from_config,
    run_pygeo_native_avl_case,
)
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator

# --------------------------------------------------------------------------- #
# Paths — everything under the repo, nothing in /tmp (§0.6).                   #
# --------------------------------------------------------------------------- #
REPO = Path(__file__).resolve().parents[2]
GEOM_CONFIG = REPO / "configs" / "geometry" / "bwb.yaml"
DATA_ROOT = REPO / "data" / "panelling_study"
CACHE_ROOT = DATA_ROOT / "cache"
CONFIG_ROOT = REPO / "configs" / "aero" / "panelling_study"
PLOTS_ROOT = CONFIG_ROOT / "plots"
AVL_BIN = "avl"

# --------------------------------------------------------------------------- #
# Fixed conditions (§3). These are constants of the study, not knobs.         #
# --------------------------------------------------------------------------- #
N_SECTIONS = 25
SPAN_MARGIN = 0.0
SNAP_SECTIONS_TO_CONTROL = True
VELOCITY_MPS = 28.0
ALTITUDE_M = 0.0
BETA_DEG = 0.0
VISCOUS = True
AVL_TIMEOUT_SEC = 900

# AVL hard limits (§3.3).
MAX_STRIPS = 500
MAX_VORTICES = 6000
# §3.3 CORRECTION (Stage 0 finding). The runbook assumes 48 base strips, i.e.
# 2*(25-1), which presumes the 25 configured sections survive unchanged. They do
# NOT: with snap_sections_to_control=true (frozen in §3) the adapter INSERTS
# sections at the two control-band edges and the planform kinks, so the realized
# section count is ~29 and the true strip count is 2*(N_realized-1)*spanwise,
# ~56*spanwise here. The strip/vortex counts are therefore computed per geometry
# from the built sections, never from the 48 constant. See strips_for().

# Print-noise floor (§4.5): never form a relative error against a comparator
# whose |value| is below this.
NOISE_FLOOR = 1e-4


# --------------------------------------------------------------------------- #
# Provenance of the toolchain (§4.2).                                         #
# --------------------------------------------------------------------------- #
def _sha256_file(path: Path, limit_bytes: int | None = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        data = fh.read() if limit_bytes is None else fh.read(limit_bytes)
    h.update(data)
    return h.hexdigest()


def _which(binary: str) -> Path:
    out = subprocess.run(["which", binary], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"binary not found on PATH: {binary}")
    return Path(out.stdout.strip())


def avl_version_string() -> str:
    """A stable identity for the AVL binary. AVL has no --version flag, so we
    fingerprint the binary itself; that is what actually determines the numbers."""
    p = _which(AVL_BIN)
    return f"{p}:sha256={_sha256_file(p)[:16]}"


def src_git_sha() -> str:
    """git SHA of the tree, plus a dirty flag if src/aeris/ has uncommitted work."""
    try:
        sha = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain", "src/aeris"],
            capture_output=True, text=True,
        ).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except Exception as exc:  # pragma: no cover - git optional
        return f"unknown({exc})"


_TOOLCHAIN: dict[str, str] | None = None


def toolchain() -> dict[str, str]:
    global _TOOLCHAIN
    if _TOOLCHAIN is None:
        _TOOLCHAIN = {
            "geom_config_sha256": _sha256_file(GEOM_CONFIG),
            "src_git_sha": src_git_sha(),
            "avl_version": avl_version_string(),
        }
    return _TOOLCHAIN


# --------------------------------------------------------------------------- #
# Config + sampling (§4.1, §5).                                               #
# --------------------------------------------------------------------------- #
_BASE_CONFIG: tuple[str, Any] | None = None


def load_base_config() -> tuple[str, Any]:
    """resolve_generator_and_config(load_yaml_config('configs/geometry/bwb.yaml'))."""
    global _BASE_CONFIG
    if _BASE_CONFIG is None:
        raw = load_yaml_config(GEOM_CONFIG)
        _BASE_CONFIG = resolve_generator_and_config(raw)
    return _BASE_CONFIG


def make_sample(kind: str, seed: int, *, override: dict[str, Any] | None = None) -> Any:
    """kind='normal' -> the production sampler at `seed` (§5 step 1).
       kind='extreme' -> the base sample at `seed` with `override` applied by
       dataclasses.replace (§5 step 2). The override dict is authored in Stage 0
       and recorded verbatim in the locked config."""
    gid, gcfg = load_base_config()
    gen = get_geometry_generator(gid)
    base = gen.sample_one(gcfg, seed=seed)
    if kind == "normal":
        return base
    if kind == "extreme":
        if not override:
            raise ValueError("kind='extreme' requires an override dict")
        return dataclasses.replace(base, **override)
    raise ValueError(f"unknown sample kind: {kind!r}")


def sample_id(kind: str, seed: int, label: str | None = None) -> str:
    return label if label else f"{kind}:{seed}"


# --------------------------------------------------------------------------- #
# The 36 study geometries (§5). Decided in Stage 0, shared by every stage.    #
#                                                                             #
# D5: production samples geometries with the LHS sampler (aeris.dataset.      #
# sampling.samplers.lhs_v1), a space-filling design — NOT independent seeded  #
# draws. Per §5 step 1 the 30 normal geometries are therefore an LHS design   #
# over the same bounds, so they are distributionally matched to production.   #
# The convergence subsets the runbook calls "seeds 2001..2008" / "2001..2004" #
# map to the FIRST 8 / FIRST 4 points of this design.                          #
# --------------------------------------------------------------------------- #
DESIGN_SEED = 2000
N_NORMAL = 30

# 6 extreme geometries (§5 step 2): base = normal LHS point 0, with these
# overrides applied verbatim. Bounds are from configs/geometry/bwb.yaml.
EXTREME_OVERRIDES: dict[str, dict[str, float]] = {
    "narrow_elevon": {"elevon_start_frac": 0.70, "elevon_end_frac": 0.85,
                      "elevon_hinge_frac": 0.78},
    "wide_elevon":   {"elevon_start_frac": 0.50, "elevon_end_frac": 0.98,
                      "elevon_hinge_frac": 0.70},
    "high_ar":       {"b_total_m": 1.25, "c1_m": 0.70},
    "strong_taper":  {"c2_ratio": 0.55, "c3_ratio": 0.30, "c4_ratio": 0.08},
    "min_chord":     {"c4_ratio": 0.08},
    "max_sweep":     {"sw1_deg": 40.0, "sw2_deg": 35.0, "sw3_deg": 25.0},
}

_NORMAL_SAMPLES: list[tuple[str, Any]] | None = None


def normal_samples() -> list[tuple[str, Any]]:
    """The 30 normal geometries as (sample_key, sample), from one fixed LHS
    design. Deterministic across stages."""
    global _NORMAL_SAMPLES
    if _NORMAL_SAMPLES is None:
        from aeris.dataset.sampling.samplers.lhs_v1 import generate_lhs_samples
        _gid, gcfg = load_base_config()
        xs = generate_lhs_samples(config=gcfg, n_samples=N_NORMAL,
                                  sampler_seed=DESIGN_SEED)
        _NORMAL_SAMPLES = [
            (f"lhs{N_NORMAL}s{DESIGN_SEED}:{i:02d}", x) for i, x in enumerate(xs)
        ]
    return _NORMAL_SAMPLES


def convergence_subset(k: int) -> list[tuple[str, Any]]:
    """First k normal geometries — the fixed subset the convergence stages use
    (runbook's 'seeds 2001..200k')."""
    return normal_samples()[:k]


def extreme_samples() -> list[tuple[str, Any]]:
    """The 6 extreme geometries as (sample_key, sample): normal LHS point 0 with
    each documented override applied (§5 step 2)."""
    _base_key, base = normal_samples()[0]
    out = []
    for name, override in EXTREME_OVERRIDES.items():
        out.append((f"extreme:{name}", dataclasses.replace(base, **override)))
    return out


# --------------------------------------------------------------------------- #
# Mesh-limit guard (§3.3).                                                    #
# --------------------------------------------------------------------------- #
def strips_for(n_sections_realized: int, spanwise: int) -> int:
    """True AVL strip count. Each of the (N-1) section intervals carries
    `spanwise` strips, and YDUPLICATE mirrors the half-model, hence the factor 2.
    Calibrated against AVL's own reported n_strips (span 1/2/4 -> 56/112/224 at
    N=29)."""
    return 2 * (int(n_sections_realized) - 1) * int(spanwise)


def mesh_counts(n_sections_realized: int, nchordwise: int, spanwise: int) -> tuple[int, int]:
    """Return the (strips, vortices) a request WILL produce, from the REALIZED
    section count, before any solve."""
    strips = strips_for(n_sections_realized, spanwise)
    vortices = strips * int(nchordwise)
    return strips, vortices


def assert_mesh_legal(n_sections_realized: int, nchordwise: int, spanwise: int) -> tuple[int, int]:
    strips, vortices = mesh_counts(n_sections_realized, nchordwise, spanwise)
    if strips > MAX_STRIPS:
        raise ValueError(
            f"illegal mesh: strips={strips} > {MAX_STRIPS} "
            f"(N={n_sections_realized}, spanwise={spanwise}). Aborting before AVL (§3.3)."
        )
    if vortices > MAX_VORTICES:
        raise ValueError(
            f"illegal mesh: vortices={vortices} > {MAX_VORTICES} "
            f"(N={n_sections_realized}, nchordwise={nchordwise}, spanwise={spanwise}). "
            f"Aborting before AVL (§3.3)."
        )
    return strips, vortices


# --------------------------------------------------------------------------- #
# Cache hash + provenance (§4.2).                                             #
# --------------------------------------------------------------------------- #
def _provenance(sample_key: str, *, nchordwise, spanwise, cspace, alpha_deg,
                control_input_deg, diff_input_deg) -> dict[str, Any]:
    tc = toolchain()
    return {
        "sample_id": sample_key,
        "nchordwise": int(nchordwise),
        "spanwise": int(spanwise),
        "cspace": float(cspace),
        "alpha_deg": float(alpha_deg),
        "beta_deg": float(BETA_DEG),
        "control_input_deg": float(control_input_deg),
        "diff_input_deg": float(diff_input_deg),
        "viscous": bool(VISCOUS),
        "velocity_mps": float(VELOCITY_MPS),
        "altitude_m": float(ALTITUDE_M),
        "geom_config_sha256": tc["geom_config_sha256"],
        "src_git_sha": tc["src_git_sha"],
        "avl_version": tc["avl_version"],
    }


def _hash_provenance(prov: dict[str, Any]) -> str:
    blob = json.dumps(prov, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


# --------------------------------------------------------------------------- #
# Frozen quantity extraction (§4.3). DO NOT add or remove fields.             #
# --------------------------------------------------------------------------- #
def _get(d: dict | None, *keys, default=None):
    """Fetch the first present key from a dict (case/label tolerant)."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d:
            return d[k]
    return default


def _ctl(cderivs: dict, surface_names: tuple[str, ...], field: str, default=None):
    """control_derivatives is keyed by surface; pull `field` from the first
    matching surface name."""
    if not isinstance(cderivs, dict):
        return default
    for name in surface_names:
        block = cderivs.get(name)
        if isinstance(block, dict) and field in block:
            return block[field]
    return default


# elevon surface naming can be 'elevon_sym'/'elevon_diff' or the raw AVL control
# names; try both. The exact keys are asserted against a real solve in Stage 0.
_SYM_NAMES = ("elevon_sym", "elevon_symmetric", "sym", "d1")
_DIFF_NAMES = ("elevon_diff", "elevon_differential", "diff", "d2")


def extract_quantities(res: Any) -> dict[str, Any]:
    """Flatten a NativeAvlResult into the frozen §4.3 row of scalars."""
    stab = getattr(res, "stability_axis_derivatives", {}) or {}
    cderivs = getattr(res, "control_derivatives", {}) or {}
    hinge = getattr(res, "hinge_moments", {}) or {}
    row: dict[str, Any] = {
        # drag
        "cd_ind": getattr(res, "cd_ind", None),
        "cd_total": getattr(res, "cd_total", None),
        "span_efficiency": getattr(res, "span_efficiency", None),
        "l_over_d": getattr(res, "l_over_d", None),
        # forces
        "cl": getattr(res, "cl", None),
        "cm": getattr(res, "cm", None),
        # stability
        "x_np": getattr(res, "x_np", None),
        "CLa": _get(stab, "CLa", "CL_a", "CLalpha"),
        "Cma": _get(stab, "Cma", "Cm_a", "Cmalpha"),
        "Clp": _get(stab, "Clp", "Cl_p"),
        "Cmq": _get(stab, "Cmq", "Cm_q"),
        "Cnb": _get(stab, "Cnb", "Cn_b", "Cnbeta"),
        # control
        "elevon_sym.CL": _ctl(cderivs, _SYM_NAMES, "CL"),
        "elevon_sym.Cm": _ctl(cderivs, _SYM_NAMES, "Cm"),
        "elevon_diff.Cl": _ctl(cderivs, _DIFF_NAMES, "Cl"),
        "elevon_diff.Cn": _ctl(cderivs, _DIFF_NAMES, "Cn"),
        "elevon_diff.CY": _ctl(cderivs, _DIFF_NAMES, "CY"),
        # hinge
        "hinge_moments.elevon_sym": _get(hinge, *_SYM_NAMES),
        "hinge_moments.elevon_diff": _get(hinge, *_DIFF_NAMES),
        # mesh
        "n_strips": getattr(res, "n_strips", None),
        "n_vortices": getattr(res, "n_vortices", None),
        "n_sections": getattr(res, "n_sections", None),
        # references (needed for derived quantities; frozen in Stage 0)
        "c_ref": getattr(res, "c_ref", None),
        "s_ref": getattr(res, "s_ref", None),
        "b_ref": getattr(res, "b_ref", None),
    }
    return row


# The set of physical quantities the study aggregates over (excludes mesh/meta).
QUANTITY_FIELDS = (
    "cd_ind", "cd_total", "span_efficiency", "l_over_d", "cl", "cm",
    "x_np", "CLa", "Cma", "Clp", "Cmq", "Cnb",
    "elevon_sym.CL", "elevon_sym.Cm", "elevon_diff.Cl", "elevon_diff.Cn",
    "elevon_diff.CY", "hinge_moments.elevon_sym", "hinge_moments.elevon_diff",
)


# --------------------------------------------------------------------------- #
# Section cache — build sections once per sample (§4.1).                       #
# --------------------------------------------------------------------------- #
_SECTION_CACHE: dict[str, tuple[Any, float, dict]] = {}


def build_sections(sample: Any, sample_key: str):
    """(extracted_sections, semispan_m, meta), built once per sample_key."""
    if sample_key not in _SECTION_CACHE:
        ex, semi, meta = build_pygeo_sections_from_config(
            GEOM_CONFIG,
            n_sections=N_SECTIONS,
            span_margin=SPAN_MARGIN,
            snap_sections_to_control=SNAP_SECTIONS_TO_CONTROL,
            sample=sample,
        )
        _SECTION_CACHE[sample_key] = (ex, semi, meta)
    return _SECTION_CACHE[sample_key]


def realized_n_sections(sample: Any, sample_key: str) -> int:
    """The section count AVL will actually see (base 25 + inserted control-band
    edges and kink pins). Drives the corrected §3.3 legality table in Stage 0."""
    ex, _semi, _meta = build_sections(sample, sample_key)
    return len(ex)


# --------------------------------------------------------------------------- #
# The one solve everything routes through (§4.1).                             #
# --------------------------------------------------------------------------- #
def run_case(sample, *, nchordwise, spanwise, cspace, alpha_deg,
             control_input_deg, diff_input_deg, sample_key: str,
             tag: str = "", bypass_cache: bool = False) -> dict:
    """One AVL solve. Returns a flat dict of scalars (§4.3) plus meta.

    Never raises on a physics/solver failure: returns {ok: False, reason: ...}.
    Raises only on programmer error the study must not paper over: an illegal
    mesh (§3.3), a mesh mismatch (§9) or a provenance mismatch on a cache hit
    (§9) — those are STOP conditions and must surface loudly.
    """
    prov = _provenance(
        sample_key, nchordwise=nchordwise, spanwise=spanwise, cspace=cspace,
        alpha_deg=alpha_deg, control_input_deg=control_input_deg,
        diff_input_deg=diff_input_deg,
    )
    h = _hash_provenance(prov)
    cache_dir = CACHE_ROOT / h
    result_json = cache_dir / "native_avl_result.json"
    prov_json = cache_dir / "provenance.json"

    # ---- cache hit -------------------------------------------------------- #
    if result_json.exists() and prov_json.exists() and not bypass_cache:
        cached_prov = json.loads(prov_json.read_text())
        for k, v in prov.items():
            if cached_prov.get(k) != v:
                raise RuntimeError(
                    f"§9 STOP: provenance mismatch on cache hit {h}: "
                    f"field {k!r} cached={cached_prov.get(k)!r} requested={v!r}"
                )
        row = json.loads(result_json.read_text())
        row["cache_hit"] = True
        return row

    # ---- fresh solve ------------------------------------------------------ #
    # Build sections FIRST so the mesh guard uses the REALIZED section count
    # (§3.3 correction), then assert legality before writing any .avl.
    ex, semi, meta = build_sections(sample, sample_key)
    n_sec_realized = len(ex)
    strips, vortices = assert_mesh_legal(n_sec_realized, nchordwise, spanwise)

    cache_dir.mkdir(parents=True, exist_ok=True)
    fc = FlightCondition(
        alpha_deg=float(alpha_deg), beta_deg=float(BETA_DEG),
        velocity_mps=VELOCITY_MPS, altitude_m=ALTITUDE_M,
    )

    def _one_solve() -> tuple[Any, float]:
        t0 = time.perf_counter()
        r = run_pygeo_native_avl_case(
            flight_condition=fc, output_dir=cache_dir,
            extracted_sections=ex, semispan_m=semi, control=meta.get("control"),
            control_input_deg=float(control_input_deg),
            diff_input_deg=float(diff_input_deg),
            viscous=VISCOUS, nchordwise=int(nchordwise),
            spanwise_panels_per_section=int(spanwise), cspace=float(cspace),
            timeout_sec=AVL_TIMEOUT_SEC, avl_command=AVL_BIN,
        )
        return r, time.perf_counter() - t0

    t_total0 = time.perf_counter()
    res, seconds_avl = _one_solve()
    status = getattr(res, "status", "UNKNOWN")

    # one retry on failure (§4.1); never invent a substitute (§0.3)
    if status != "SUCCESS":
        res, seconds_avl = _one_solve()
        status = getattr(res, "status", "UNKNOWN")

    seconds_total = time.perf_counter() - t_total0

    if status != "SUCCESS":
        row = {
            "ok": False, "status": status, "reason": f"status={status}",
            "cache_hit": False, "sample_id": sample_key,
            "nchordwise": int(nchordwise), "spanwise": int(spanwise),
            "cspace": float(cspace), "alpha_deg": float(alpha_deg),
            "control_input_deg": float(control_input_deg),
            "diff_input_deg": float(diff_input_deg),
            "seconds_avl": seconds_avl, "seconds_total": seconds_total,
            "tag": tag,
        }
        prov_json.write_text(json.dumps(prov, indent=2))
        result_json.write_text(json.dumps(row, indent=2))
        return row

    # §0.4 / §9: SUCCESS must carry real numbers.
    if getattr(res, "cl", None) is None:
        raise RuntimeError(
            f"§9 STOP: status==SUCCESS but cl is None ({h}); the guard is broken."
        )

    row = extract_quantities(res)

    # §9: the mesh AVL REPORTS must equal what we asked for.
    if row["n_strips"] not in (None, strips):
        raise RuntimeError(
            f"§9 STOP: requested strips={strips} but AVL reports "
            f"n_strips={row['n_strips']} ({h})."
        )
    if row["n_vortices"] not in (None, vortices):
        raise RuntimeError(
            f"§9 STOP: requested vortices={vortices} but AVL reports "
            f"n_vortices={row['n_vortices']} ({h})."
        )

    row.update({
        "ok": True, "status": status, "cache_hit": False,
        "sample_id": sample_key, "tag": tag,
        "nchordwise": int(nchordwise), "spanwise": int(spanwise),
        "cspace": float(cspace), "alpha_deg": float(alpha_deg),
        "control_input_deg": float(control_input_deg),
        "diff_input_deg": float(diff_input_deg),
        "strips_expected": strips, "vortices_expected": vortices,
        "seconds_avl": seconds_avl, "seconds_total": seconds_total,
    })

    prov_json.write_text(json.dumps(prov, indent=2))
    result_json.write_text(json.dumps(row, indent=2))
    return row


# --------------------------------------------------------------------------- #
# Error triplet (§4.5): absolute, relative (NaN under floor), normalised.     #
# --------------------------------------------------------------------------- #
def error_triplet(value: float, comparator: float, scale: float | None) -> dict:
    abs_err = abs(value - comparator)
    rel = float("nan") if abs(comparator) < NOISE_FLOOR else abs_err / abs(comparator)
    norm = float("nan") if not scale else abs_err / scale
    return {"abs": abs_err, "rel": rel, "norm": norm}


# --------------------------------------------------------------------------- #
# Parallel driver (§7 says Stage 7 must be serial; other stages may parallelise).
# AVL solves are independent and the cache is on disk, so this is embarrassingly
# parallel. We parallelise BY GEOMETRY so each worker builds its sections once
# and reuses them across that geometry's meshes/angles. Spawn context (not fork)
# avoids fork-after-torch hazards; each worker re-imports under run.sh's env.
# --------------------------------------------------------------------------- #
DEFAULT_WORKERS = 4  # 7 GB RAM box: ~1 GB per AVL+pyGeo+NeuralFoil worker


def run_geometry_cells(payload: dict) -> list[dict]:
    """Worker entry: solve every cell for ONE geometry. `payload` =
    {sample_key, sample, cells:[{nchordwise,spanwise,cspace,alpha_deg,
    control_input_deg,diff_input_deg,tag}, ...]}. Returns the rows."""
    key = payload["sample_key"]
    sample = payload["sample"]
    out = []
    for cell in payload["cells"]:
        out.append(run_case(sample, sample_key=key, **cell))
    return out


def parallel_by_geometry(geoms, cells, *, workers: int = DEFAULT_WORKERS,
                         tag: str = "run") -> dict:
    """Run `cells` (a list of cell-kwargs) on every geometry in `geoms`
    (list of (sample_key, sample)) across `workers` INDEPENDENT subprocesses,
    coordinated only through the on-disk cache. Avoids the mpi4py-in-child
    deadlock that multiprocessing/fork hits. Returns
    {(sample_key, nchordwise, spanwise, cspace, alpha_deg): row}."""
    import subprocess

    keys = [k for k, _ in geoms]
    # round-robin geometries into `workers` slices for even load
    slices = [keys[i::workers] for i in range(workers)]
    slices = [sl for sl in slices if sl]
    run_sh = str(Path(__file__).resolve().parent / "run.sh")

    procs = []
    spec_paths = []
    for wid, sl in enumerate(slices):
        spec = {"wid": wid, "sample_keys": sl, "cells": cells}
        sp = DATA_ROOT / f"_slice_{tag}_{wid}.json"
        sp.write_text(json.dumps(spec))
        spec_paths.append(sp)
        procs.append(subprocess.Popen(["bash", run_sh, "worker.py", str(sp)]))

    codes = [p.wait() for p in procs]
    for sp in spec_paths:
        try:
            sp.unlink()
        except OSError:
            pass
    bad = [i for i, c in enumerate(codes) if c != 0]
    if bad:
        raise RuntimeError(f"parallel workers {bad} exited non-zero: "
                           f"{[codes[i] for i in bad]}")

    # collect from cache (fast cache hits in THIS process)
    sample_of = {k: s for k, s in geoms}
    results: dict = {}
    for key, s in geoms:
        for cell in cells:
            r = run_case(s, sample_key=key, **cell)
            results[(r["sample_id"], r["nchordwise"], r["spanwise"],
                     r["cspace"], r["alpha_deg"])] = r
    return results


# --------------------------------------------------------------------------- #
# Convergence analysis (Stages 2 & 3). Shared so both stages are identical.    #
# Refinement ratio r=2, GCI safety factor Fs=1.25 (Roache).                    #
# --------------------------------------------------------------------------- #
GCI_FS = 1.25
R_REFINE = 2.0


def _chain_p(f_coarse, f_mid, f_fine, r=R_REFINE):
    """Observed order of convergence from a 3-mesh chain (ratio r)."""
    d_hi = f_mid - f_coarse
    d_lo = f_fine - f_mid
    if d_lo == 0:
        return float("nan")
    ratio = abs(d_hi) / abs(d_lo)
    if ratio <= 0:
        return float("nan")
    return math.log(ratio) / math.log(r)


def richardson_gci(f_coarse, f_mid, f_fine, r=R_REFINE, Fs=GCI_FS):
    """Richardson extrapolation + GCI for one 3-mesh chain. Returns a dict with
    p, extrapolated value, GCI_fine, GCI_coarse, asymptotic ratio R, and the
    monotonic/shrinking flags. Caller applies the six admissibility gates."""
    p = _chain_p(f_coarse, f_mid, f_fine, r)
    d_hi = f_mid - f_coarse
    d_lo = f_fine - f_mid
    monotonic = (d_hi > 0 and d_lo > 0) or (d_hi < 0 and d_lo < 0)
    shrinking = abs(d_lo) < abs(d_hi)
    out = {"p": p, "monotonic": monotonic, "shrinking": shrinking,
           "extrap": None, "gci_fine": None, "gci_coarse": None, "R": None}
    if not math.isnan(p) and (r ** p - 1) != 0:
        out["extrap"] = f_fine + d_lo / (r ** p - 1)
        if f_fine != 0 and f_mid != 0:
            gf = Fs * abs(d_lo / f_fine) / (r ** p - 1)
            gc = Fs * abs(d_hi / f_mid) / (r ** p - 1)
            out["gci_fine"], out["gci_coarse"] = gf, gc
            if gf != 0:
                out["R"] = gc / (r ** p * gf)
    return out


def convergence_admissible(chainA, chainB, comparator_abs, *, floor=NOISE_FLOOR):
    """The six §Stage2 admissibility gates on the finer chain (chainB), using
    chainA only to cross-check the observed order. Returns (ok, reasons, detail).
    chainA/chainB are richardson_gci() dicts; comparator_abs is |f_fine|."""
    reasons = []
    pA, pB = chainA["p"], chainB["p"]
    if not chainB["monotonic"]:
        reasons.append("non_monotonic")
    if not chainB["shrinking"]:
        reasons.append("differences_not_shrinking")
    if math.isnan(pB) or not (0.5 <= pB <= 3.0):
        reasons.append("p_out_of_range")
    if math.isnan(pA) or math.isnan(pB) or pB == 0 or abs(pA - pB) / abs(pB) > 0.30:
        reasons.append("chains_disagree_gt30pct")
    if comparator_abs < floor:
        reasons.append("below_noise_floor")
    R = chainB["R"]
    if R is None or math.isnan(R) or not (0.8 <= R <= 1.25):
        reasons.append("asymptotic_ratio_out_of_band")
    return (len(reasons) == 0, reasons, {"pA": pA, "pB": pB, "R": R})


if __name__ == "__main__":  # tiny self-check, not a stage
    print("REPO:", REPO)
    print("geom config exists:", GEOM_CONFIG.exists())
    print("toolchain:", json.dumps(toolchain(), indent=2))
    print("mesh(12,2):", mesh_counts(12, 2))
