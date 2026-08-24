"""Section-positioning study — shared runner (RUNBOOK_section_positioning_study_v1).

Reuses the panelling study's samples, solver, quantity extraction and error
machinery (imported as ``pc``) and adds the one axis this study moves: the
spanwise SECTION PLACEMENT. The panel mesh is FROZEN at the panelling selection
c16s2u (chord 16, spanwise-panels-per-section 2, cspace uniform=0.0).

The loft is built once per design; sections are then extracted at any placement
(uniform / adaptive / clustered / custom) and any count N. The provenance hash
includes the FULL section-fraction vector + policy + N, so two placements at the
same N never collide in cache (§9 of the runbook — the analogue of the panelling
study's control-input hash bug).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np

import common as pc  # panelling study/common.py (added to sys.path by run.sh)

from aeris.aero.models import FlightCondition
from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
    build_pygeo, extract_sections, stations_from_records,
)
from aeris.generators.bwb_segmented_v1.pygeo_backend import _resolve_airfoil_database
from aeris.generators.bwb_segmented_v1.services import (
    build_section_geometry_from_sample, generate_bwb_planform_from_sample,
)
from aeris.geometry.geometric_information import (
    adaptive_span_fractions, ramp_fraction, spanwise_information_profile,
)

# --------------------------------------------------------------------------- #
# Paths + frozen mesh (§1).                                                   #
# --------------------------------------------------------------------------- #
REPO = pc.REPO
DATA_ROOT = REPO / "data" / "section_study"
CACHE_ROOT = DATA_ROOT / "cache"
CONFIG_ROOT = REPO / "configs" / "aero" / "section_study"
PLOTS_ROOT = CONFIG_ROOT / "plots"
for _d in (CACHE_ROOT, CONFIG_ROOT, PLOTS_ROOT):
    _d.mkdir(parents=True, exist_ok=True)

NCHORD = 16          # c16s2u (panelling study selection)
SPANW = 2
CSPACE = 0.0         # 0.0 = uniform chordwise (the c16s2u 'u')
MIN_SPACING = 1e-3
MAX_STRIPS = pc.MAX_STRIPS
MAX_VORTICES = pc.MAX_VORTICES

# convenient re-exports so stage scripts read cleanly
normal_samples = pc.normal_samples
extreme_samples = pc.extreme_samples
convergence_subset = pc.convergence_subset
extract_quantities = pc.extract_quantities
QUANTITY_FIELDS = pc.QUANTITY_FIELDS
NOISE_FLOOR = pc.NOISE_FLOOR


# --------------------------------------------------------------------------- #
# Sample resolution by key (so workers can rebuild designs from a slice).      #
# --------------------------------------------------------------------------- #
_BY_KEY: dict[str, Any] | None = None


def sample_by_key(key: str) -> Any:
    global _BY_KEY
    if _BY_KEY is None:
        _BY_KEY = {k: s for k, s in (list(normal_samples()) + list(extreme_samples()))}
    return _BY_KEY[key]


# --------------------------------------------------------------------------- #
# Loft context — built once per design, reused for every placement.           #
# --------------------------------------------------------------------------- #
_CTX: dict[str, dict] = {}


def build_context(sample: Any, sample_key: str) -> dict:
    """Loft the design and return everything placement needs.

    Mirrors build_pygeo_sections_from_config's load->planform->stations->loft
    pipeline, but STOPS before extraction so we own the section fractions.
    """
    if sample_key in _CTX:
        return _CTX[sample_key]
    gid, gcfg = pc.load_base_config()
    planform = generate_bwb_planform_from_sample(sample, gcfg)
    section_geometry = build_section_geometry_from_sample(planform, sample, gcfg)
    stations = tuple(stations_from_records(
        section_geometry.sections, _resolve_airfoil_database(gcfg)))
    frame_mode = ("asb_frame" if gcfg.pygeo.frame_mode == "aeris_frame"
                  else gcfg.pygeo.frame_mode)
    build = build_pygeo(
        stations, k_span=gcfg.pygeo.k_span, frame_mode=frame_mode,
        n_ctl=gcfg.pygeo.n_ctl, tip=gcfg.pygeo.tip, tip_scale=gcfg.pygeo.tip_scale)

    # control band from the SAMPLE (the elevon DVs are sampled per design)
    control = None
    band = None
    surfaces = getattr(gcfg.control_surfaces, "surfaces", None)
    if surfaces:
        cs = surfaces[0]
        hinge = float(cs.hinge_point) if hasattr(cs, "hinge_point") else 0.7
        start, end = float(cs.spanwise.start_frac), float(cs.spanwise.end_frac)
        if getattr(gcfg, "elevon_bounds", None) is not None:
            hinge = float(getattr(sample, "elevon_hinge_frac", hinge))
            start = float(getattr(sample, "elevon_start_frac", start))
            end = float(getattr(sample, "elevon_end_frac", end))
        control = {"name": cs.name, "hinge_point": hinge, "symmetric": cs.symmetric,
                   "start_frac": start, "end_frac": end}
        band = (start, end)

    # mandatory nodes (§1): span ends, planform breaks, control-band edges
    pins: list[float] = [0.0, 1.0]
    try:
        b3r = float(getattr(sample, "b3_ratio"))
        split = float(getattr(sample, "split_ratio", getattr(sample, "b2_ratio", 0.5)))
        pins += [(1.0 - b3r) * split, 1.0 - b3r]
    except (AttributeError, TypeError, ValueError):
        pass
    if band is not None:
        pins += list(band)
    pins = sorted({round(v, 9) for v in pins if 0.0 <= v <= 1.0})

    ctx = {"build": build, "gcfg": gcfg, "gid": gid, "control": control,
           "band": band, "pins": pins,
           "cst_order": gcfg.pygeo.extraction.cst_order,
           "chordwise_points": gcfg.pygeo.extraction.chordwise_points}
    _CTX[sample_key] = ctx
    return ctx


# --------------------------------------------------------------------------- #
# Placement policies -> a span-fraction vector.                               #
# --------------------------------------------------------------------------- #
def _finalise(fractions: np.ndarray, pins: Sequence[float]) -> np.ndarray:
    """Insert pins (never drop them), clip, enforce strict monotone spacing.
    Same rule as adaptive_span_fractions so all policies are comparable."""
    fr = np.asarray(fractions, dtype=float)
    pins_in = [float(p) for p in pins if 0.0 <= float(p) <= 1.0]
    if pins_in:
        fr = np.concatenate([fr, np.asarray(pins_in)])
    fr = np.unique(np.clip(fr, 0.0, 1.0))
    keep = [fr[0]]
    for f in fr[1:]:
        if f - keep[-1] >= MIN_SPACING:
            keep.append(f)
        elif f == fr[-1]:
            keep[-1] = f
    return np.asarray(keep, dtype=float)


def fractions_for(ctx: dict, n_sections: int, policy: str) -> np.ndarray:
    """Span fractions for a placement policy. Pins are always honoured."""
    pins = ctx["pins"]
    n = int(n_sections)
    if policy == "uniform":
        return _finalise(np.linspace(0.0, 1.0, n), pins)
    if policy == "uniform_nopin":
        # uniform with NO mandatory nodes (only span ends) — isolates the value
        # of the hard-point / control-edge pins from the density rule.
        fr = np.linspace(0.0, 1.0, n)
        fr = np.unique(np.clip(fr, 0.0, 1.0))
        return fr
    if policy == "clustered":
        # deliberately the OPPOSITE of adaptive: inboard-heavy (root-clustered),
        # so the dense reference is proven family-independent, not co-biased.
        t = np.linspace(0.0, 1.0, n)
        return _finalise(t ** 2, pins)
    if policy in ("adaptive", "M2"):
        prof = spanwise_information_profile(
            ctx["build"], n_probe=301, chordwise_probe=21, control_band=ctx["band"])
        return adaptive_span_fractions(prof, n, must_include=pins)
    raise ValueError(f"unknown placement policy {policy!r}")


# --------------------------------------------------------------------------- #
# Provenance + cache (§9): hash includes the full fraction vector + policy.   #
# --------------------------------------------------------------------------- #
def _provenance(sample_key, *, fractions, policy, n_req, alpha_deg,
                control_input_deg, diff_input_deg, nchord=NCHORD, spanw=SPANW) -> dict:
    return {
        "study": "section_positioning_v1",
        "sample_id": sample_key,
        "policy": policy,
        "n_requested": int(n_req),
        "section_fractions": [round(float(f), 6) for f in fractions],
        "n_realized": int(len(fractions)),
        "nchordwise": int(nchord), "spanwise": int(spanw), "cspace": CSPACE,
        "alpha_deg": float(alpha_deg), "beta_deg": float(pc.BETA_DEG),
        "control_input_deg": float(control_input_deg),
        "diff_input_deg": float(diff_input_deg),
        "viscous": bool(pc.VISCOUS), "velocity_mps": pc.VELOCITY_MPS,
        "altitude_m": pc.ALTITUDE_M,
        "geom_config_sha256": pc._sha256_file(pc.GEOM_CONFIG),
    }


def _hash(prov: dict) -> str:
    return hashlib.sha256(
        json.dumps(prov, sort_keys=True).encode()).hexdigest()[:24]


def hash_for(ctx, sample_key, *, n_sections, policy, alpha_deg,
             control_input_deg=4.0, diff_input_deg=4.0):
    fr = fractions_for(ctx, n_sections, policy)
    prov = _provenance(sample_key, fractions=fr, policy=policy, n_req=n_sections,
                       alpha_deg=alpha_deg, control_input_deg=control_input_deg,
                       diff_input_deg=diff_input_deg)
    return _hash(prov), fr


# --------------------------------------------------------------------------- #
# Solve one case.                                                             #
# --------------------------------------------------------------------------- #
def run_section_case(sample, *, sample_key, n_sections, policy, alpha_deg,
                     control_input_deg=4.0, diff_input_deg=4.0,
                     tag="", bypass_cache=False, nchord=NCHORD, spanw=SPANW) -> dict:
    ctx = build_context(sample, sample_key)
    fr = fractions_for(ctx, n_sections, policy)
    n_real = len(fr)
    strips, vortices = pc.assert_mesh_legal(n_real, int(nchord), int(spanw))

    prov = _provenance(sample_key, fractions=fr, policy=policy, n_req=n_sections,
                       alpha_deg=alpha_deg, control_input_deg=control_input_deg,
                       diff_input_deg=diff_input_deg, nchord=nchord, spanw=spanw)
    h = _hash(prov)
    cache_dir = CACHE_ROOT / h
    result_json = cache_dir / "native_avl_result.json"
    prov_json = cache_dir / "provenance.json"

    if result_json.exists() and not bypass_cache:
        row = json.loads(result_json.read_text())
        row["cache_hit"] = True
        return row

    ex = extract_sections(ctx["build"], fr, cst_order=ctx["cst_order"],
                          chordwise_points=ctx["chordwise_points"])
    semi = max(float(s.y_m) for s in ex)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fc = FlightCondition(alpha_deg=float(alpha_deg), beta_deg=float(pc.BETA_DEG),
                         velocity_mps=pc.VELOCITY_MPS, altitude_m=pc.ALTITUDE_M)

    def _solve():
        t0 = time.perf_counter()
        r = pc.run_pygeo_native_avl_case(
            flight_condition=fc, output_dir=cache_dir,
            extracted_sections=ex, semispan_m=semi, control=ctx["control"],
            control_input_deg=float(control_input_deg),
            diff_input_deg=float(diff_input_deg),
            viscous=pc.VISCOUS, nchordwise=int(nchord),
            spanwise_panels_per_section=int(spanw), cspace=CSPACE,
            timeout_sec=pc.AVL_TIMEOUT_SEC, avl_command=pc.AVL_BIN)
        return r, time.perf_counter() - t0

    t0 = time.perf_counter()
    res, sec = _solve()
    status = getattr(res, "status", "UNKNOWN")
    if status != "SUCCESS":
        res, sec = _solve()
        status = getattr(res, "status", "UNKNOWN")
    sec_total = time.perf_counter() - t0

    base = {"ok": status == "SUCCESS", "status": status, "cache_hit": False,
            "sample_id": sample_key, "policy": policy, "tag": tag,
            "n_requested": int(n_sections), "n_realized": int(n_real),
            "nchordwise": int(nchord), "spanwise": int(spanw), "cspace": CSPACE,
            "alpha_deg": float(alpha_deg),
            "control_input_deg": float(control_input_deg),
            "diff_input_deg": float(diff_input_deg),
            "ramp_fraction": (float(ramp_fraction(fr, ctx["band"]))
                              if ctx["band"] else None),
            "section_fractions": [round(float(f), 6) for f in fr],
            "seconds_avl": sec, "seconds_total": sec_total}

    if status != "SUCCESS":
        prov_json.write_text(json.dumps(prov, indent=2))
        result_json.write_text(json.dumps(base, indent=2))
        return base

    if getattr(res, "cl", None) is None:
        raise RuntimeError(f"§STOP: SUCCESS but cl is None ({h})")
    row = extract_quantities(res)
    if row.get("n_strips") not in (None, strips):
        raise RuntimeError(f"§STOP: asked strips={strips} got {row.get('n_strips')} ({h})")
    row.update(base)
    prov_json.write_text(json.dumps(prov, indent=2))
    result_json.write_text(json.dumps(row, indent=2))
    return row


# --------------------------------------------------------------------------- #
# Case running + parallel-by-design driver.                                   #
# --------------------------------------------------------------------------- #
def run_cases_serial(cases, *, verbose=True):
    """Run a list of case dicts serially; cache makes it resumable."""
    out = []
    for i, c in enumerate(cases):
        s = sample_by_key(c["sample_key"])
        r = run_section_case(
            s, sample_key=c["sample_key"], n_sections=c["n_sections"],
            policy=c["policy"], alpha_deg=c["alpha_deg"],
            control_input_deg=c.get("control_input_deg", 4.0),
            diff_input_deg=c.get("diff_input_deg", 4.0),
            tag=c.get("tag", ""),
            nchord=c.get("nchord", NCHORD), spanw=c.get("spanw", SPANW))
        out.append(r)
        if verbose:
            print(f"[{i+1}/{len(cases)}] {c['sample_key']} {c['policy']} "
                  f"N{c['n_sections']} a{c['alpha_deg']:+.0f} "
                  f"ok={r['ok']} hit={r.get('cache_hit')} "
                  f"cl={r.get('cl')}", flush=True)
    return out


def _collect_one(sample_key, policy, n_sections, alpha_deg, nchord, spanw,
                 control_input_deg=4.0, diff_input_deg=4.0):
    """Read one cached result by recomputing its provenance hash."""
    s = sample_by_key(sample_key)
    ctx = build_context(s, sample_key)
    prov = _provenance(sample_key,
                       fractions=fractions_for(ctx, n_sections, policy),
                       policy=policy, n_req=n_sections, alpha_deg=alpha_deg,
                       control_input_deg=control_input_deg,
                       diff_input_deg=diff_input_deg, nchord=nchord, spanw=spanw)
    rj = CACHE_ROOT / _hash(prov) / "native_avl_result.json"
    return json.loads(rj.read_text()) if rj.exists() else None


def collect(cases) -> dict:
    """Read results for cases from cache (all should be present). Keyed by
    (sample_key, policy, n_sections, alpha, sym, diff)."""
    res = {}
    for c in cases:
        s = sample_by_key(c["sample_key"])
        ctx = build_context(s, c["sample_key"])
        prov = _provenance(
            c["sample_key"],
            fractions=fractions_for(ctx, c["n_sections"], c["policy"]),
            policy=c["policy"], n_req=c["n_sections"], alpha_deg=c["alpha_deg"],
            control_input_deg=c.get("control_input_deg", 4.0),
            diff_input_deg=c.get("diff_input_deg", 4.0),
            nchord=c.get("nchord", NCHORD), spanw=c.get("spanw", SPANW))
        h = _hash(prov)
        rj = CACHE_ROOT / h / "native_avl_result.json"
        row = json.loads(rj.read_text()) if rj.exists() else {"ok": False, "missing": True}
        k = (c["sample_key"], c["policy"], c["n_sections"], c["alpha_deg"],
             c.get("control_input_deg", 4.0), c.get("diff_input_deg", 4.0))
        res[k] = row
    return res


def parallel_by_design(cases, *, workers=4, tag="run"):
    """Split cases across W subprocess workers by design key (context reuse),
    wait, then collect from cache. Avoids mpi4py-in-child deadlocks by using
    independent subprocess slices (panelling study pattern)."""
    import subprocess
    keys = sorted({c["sample_key"] for c in cases})
    buckets: list[list[str]] = [[] for _ in range(min(workers, len(keys)) or 1)]
    for i, k in enumerate(keys):
        buckets[i % len(buckets)].append(k)
    run_sh = str(Path(__file__).resolve().parent / "run.sh")
    procs = []
    for wid, bucket in enumerate(buckets):
        sub = [c for c in cases if c["sample_key"] in set(bucket)]
        slc = DATA_ROOT / f"_slice_{tag}_{wid}.json"
        slc.write_text(json.dumps(sub))
        procs.append(subprocess.Popen(["bash", run_sh, "worker_sec.py", str(slc)]))
    rc = [p.wait() for p in procs]
    if any(x != 0 for x in rc):
        raise RuntimeError(f"worker(s) failed: rc={rc}")
    return collect(cases)
