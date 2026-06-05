"""
AERIS Dynamics — UQ Propagation to Eigenvalue Level
=====================================================
Propagates conformal prediction intervals from the surrogate's derivative
predictions through the full eigenvalue chain, producing:
  - N samples of all dynamic mode metrics (ζ_sp, ω_sp, ζ_ph, τ_r, T₂, ζ_DR)
  - P(Mode X meets MIL-STD-1797B Level Y) for each mode and mission class

This module is the computational core of PhD Paper 2.

---
Mathematical basis
---
Split conformal prediction guarantees (Angelopoulos & Bates, 2023):
  P(y_true ∈ [ŷ - q_hat, ŷ + q_hat]) ≥ 1 - α  (marginal, per target)

Sampling strategy: for each derivative d_i with point prediction μ_i and
conformal half-width q_i, we draw samples from U[μ_i - q_i, μ_i + q_i].
This is a conservative joint coverage strategy because:
  1. The true value lies in the interval with ≥ 1-α probability per derivative.
  2. Sampling independently ignores cross-derivative correlations.
  3. The resulting joint coverage is conservative (≤ (1-α)^n_derivs).

This limitation is explicitly documented and must be stated in Paper 2:
"Intervals are marginal conformal guarantees per derivative. Joint coverage
is conservative due to independence sampling. Correlation structure will be
captured in Paper 2 via a multivariate conformal extension."

---
What this enables
---
From 1000 bootstrap samples of the derivative vector:
  - Distribution of ζ_sp, ω_sp, ζ_ph, τ_r, T₂, ζ_DR
  - P(0.35 ≤ ζ_sp ≤ 1.30) → Mission A Level 1 compliance probability
  - P(ζ_ph ≥ 0.04) → Phugoid acceptability
  - P(T₂ ≥ 20 s) → ISR spiral mode acceptability
  - P(τ_r ≤ 1.0 s) → Roll subsidence Level 1
  - Empirical confidence intervals for each mode
  - MIL-STD-1797B level probabilities for all three missions

---
References
---
[AB23] Angelopoulos & Bates, "A Gentle Introduction to Conformal Prediction",
       arXiv:2107.07511, 2023.
[ER]   Etkin & Reid, "Dynamics of Flight", 3rd ed., 1996.
[MIL]  MIL-HDBK-1797A, 1997.
PhD Roadmap, Section 8, Paper 2, "Uncertainty Propagation to Eigenvalue Level".
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ModeUQResult:
    """
    UQ result for one dynamic mode metric.
    All statistics are empirical from the N bootstrap samples.
    """
    metric_name: str                 # e.g. "zeta_sp", "omega_n_sp", "tau_r"
    n_samples: int                   # number of valid samples (< N if some failed)
    n_total: int                     # total samples requested

    # Point estimate (from nominal derivative vector, no sampling)
    point_estimate: float | None

    # Empirical statistics from bootstrap
    mean: float | None
    std: float | None
    p05: float | None                # 5th percentile
    p50: float | None                # median
    p95: float | None                # 95th percentile

    # MIL-STD-1797B compliance probabilities
    # These are the primary output for Paper 2 and Paper 4 chance constraints
    p_level1: float | None           # P(metric satisfies Level 1 boundary)
    p_level2_or_better: float | None # P(metric satisfies Level 2 or better)
    p_stable: float | None           # P(mode is stable) — relevant for spiral, phugoid

    # Convergence diagnostic
    converged: bool                  # True if std stabilised (n_samples > 100)
    note: str | None = None


@dataclass
class EigenvalueUQResult:
    """
    Complete UQ propagation result for one design point.
    Contains all mode UQ results and the derivative samples used.
    """
    # Design point identification
    geometry_id: str | None
    alpha_deg: float | None
    velocity_mps: float | None
    altitude_m: float | None
    x_cg_m: float | None

    # Sampling configuration
    n_samples: int
    alpha_conformal: float           # conformal miscoverage rate used (e.g. 0.10 = 90%)
    sampling_method: str             # "uniform_marginal" (current) | future: "multivariate"

    # Per-mode UQ results
    short_period_zeta: ModeUQResult | None = None
    short_period_omega_n: ModeUQResult | None = None
    phugoid_zeta: ModeUQResult | None = None
    phugoid_omega_n: ModeUQResult | None = None
    roll_tau: ModeUQResult | None = None
    spiral_t2: ModeUQResult | None = None
    dutch_roll_zeta: ModeUQResult | None = None
    dutch_roll_omega_n: ModeUQResult | None = None
    dutch_roll_zeta_omega: ModeUQResult | None = None  # ζ·ω product

    # Derivative intervals used (for traceability)
    derivative_point_estimates: dict[str, float] = field(default_factory=dict)
    derivative_intervals: dict[str, float] = field(default_factory=dict)

    # Fraction of samples that produced valid eigenvalues
    sample_success_rate: float = 1.0

    # Honest limitation statement (required for Paper 2 and Paper 5)
    limitation_note: str = (
        "Intervals are marginal conformal guarantees per derivative. "
        "Derivatives sampled independently — joint coverage is conservative. "
        "Correlation structure between AVL derivatives is not captured. "
        "This is a first-order UQ estimate suitable for design screening. "
        "Paper 2 should quantify the conservatism empirically."
    )

    def to_dict(self) -> dict[str, Any]:
        """Flat dict for dataset label insertion (Paper 1 labels)."""
        def _m(r: ModeUQResult | None, prefix: str) -> dict:
            if r is None:
                return {}
            return {
                f"{prefix}_mean":    r.mean,
                f"{prefix}_std":     r.std,
                f"{prefix}_p05":     r.p05,
                f"{prefix}_p50":     r.p50,
                f"{prefix}_p95":     r.p95,
                f"{prefix}_p_l1":    r.p_level1,
                f"{prefix}_p_l2":    r.p_level2_or_better,
                f"{prefix}_p_stab":  r.p_stable,
                f"{prefix}_n_samp":  r.n_samples,
            }

        d: dict[str, Any] = {
            "uq_n_samples":           self.n_samples,
            "uq_alpha":               self.alpha_conformal,
            "uq_success_rate":        self.sample_success_rate,
            "uq_sampling_method":     self.sampling_method,
        }
        d.update(_m(self.short_period_zeta,     "uq_sp_zeta"))
        d.update(_m(self.short_period_omega_n,  "uq_sp_omegan"))
        d.update(_m(self.phugoid_zeta,          "uq_ph_zeta"))
        d.update(_m(self.roll_tau,              "uq_roll_tau"))
        d.update(_m(self.spiral_t2,             "uq_spiral_t2"))
        d.update(_m(self.dutch_roll_zeta,       "uq_dr_zeta"))
        d.update(_m(self.dutch_roll_zeta_omega, "uq_dr_zeta_omega"))
        return d


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def _sample_uniform_marginal(
    point_estimates: dict[str, float],
    intervals: dict[str, float],
    rng: random.Random,
) -> dict[str, float]:
    """
    Sample one derivative vector from independent uniform marginal distributions.
    For derivative d with point estimate μ and half-width q:
      sample ~ U[μ - q, μ + q]

    This is the correct sampling distribution for split conformal prediction.
    Independence is conservative (overestimates variability) — see module docstring.
    """
    sample: dict[str, float] = {}
    for key, mu in point_estimates.items():
        q = intervals.get(key, 0.0)
        if q <= 0.0:
            sample[key] = mu
        else:
            sample[key] = mu + rng.uniform(-q, q)
    return sample


# ---------------------------------------------------------------------------
# Statistics computation
# ---------------------------------------------------------------------------

def _percentile(data: list[float], p: float) -> float | None:
    """Compute p-th percentile (0-100) of a sorted list."""
    if not data:
        return None
    n = len(data)
    idx = (p / 100.0) * (n - 1)
    lo  = int(idx)
    hi  = min(lo + 1, n - 1)
    frac = idx - lo
    return data[lo] * (1.0 - frac) + data[hi] * frac


def _mode_uq_result(
    metric_name: str,
    values: list[float],
    n_total: int,
    point_estimate: float | None,
    level1_check_fn,     # callable(float) -> bool
    level2_check_fn,     # callable(float) -> bool
    stable_check_fn,     # callable(float) -> bool | None
) -> ModeUQResult:
    """Assemble a ModeUQResult from a list of sampled metric values."""
    n = len(values)
    if n == 0:
        return ModeUQResult(
            metric_name=metric_name,
            n_samples=0, n_total=n_total,
            point_estimate=point_estimate,
            mean=None, std=None,
            p05=None, p50=None, p95=None,
            p_level1=None, p_level2_or_better=None, p_stable=None,
            converged=False,
            note="No valid samples produced.",
        )

    sorted_vals = sorted(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
    std  = math.sqrt(variance)

    p_l1  = sum(1 for v in values if level1_check_fn(v)) / n
    p_l2  = sum(1 for v in values if level2_check_fn(v)) / n
    p_stab = sum(1 for v in values if stable_check_fn(v)) / n if stable_check_fn else None

    return ModeUQResult(
        metric_name=metric_name,
        n_samples=n,
        n_total=n_total,
        point_estimate=point_estimate,
        mean=round(mean, 5),
        std=round(std, 5),
        p05=_percentile(sorted_vals, 5.0),
        p50=_percentile(sorted_vals, 50.0),
        p95=_percentile(sorted_vals, 95.0),
        p_level1=round(p_l1, 4),
        p_level2_or_better=round(p_l2, 4),
        p_stable=round(p_stab, 4) if p_stab is not None else None,
        converged=n >= 100,
    )


# ---------------------------------------------------------------------------
# Core propagation engine
# ---------------------------------------------------------------------------

def propagate_uq(
    *,
    # Surrogate point predictions for all needed derivatives
    point_estimates: dict[str, float],
    # Conformal half-widths from q_hat (one per derivative key)
    conformal_intervals: dict[str, float],
    # Fixed (non-uncertain) parameters — mass properties and reference geometry
    mass_kg: float,
    iyy_kg_m2: float | None,
    izz_kg_m2: float | None,
    ixx_kg_m2: float | None,
    velocity_mps: float,
    altitude_m: float,
    sref_m2: float,
    mac_m: float,
    span_m: float,
    x_cg_m: float,
    alpha_deg: float,
    cl0: float,
    cd0: float,
    # UQ configuration
    n_samples: int = 1000,
    alpha_conformal: float = 0.10,
    seed: int = 42,
    # Identification
    geometry_id: str | None = None,
) -> EigenvalueUQResult:
    """
    Propagate surrogate conformal intervals through the eigenvalue chain.

    Parameters
    ----------
    point_estimates : dict
        Surrogate point predictions for stability derivatives.
        Required keys: "CLa", "Cma"
        Optional keys: "Cmq", "CLq", "Clb", "Cnb", "Clp", "Cnr", "Clr",
                       "Cnp", "CYb", "CYp", "CYr", "CLu", "Cmu", "Cmad", "CDa"
        Missing keys default to DATCOM estimates (if possible) or zero.

    conformal_intervals : dict
        Per-derivative conformal half-widths from q_hat.
        Same keys as point_estimates. Derivatives not in this dict have zero
        uncertainty (treated as exact).

    n_samples : int
        Number of bootstrap derivative vectors to sample.
        1000 is sufficient for P estimates to ±0.01.
        Use 5000 for publication-grade results.

    alpha_conformal : float
        Conformal miscoverage rate used when fitting q_hat.
        Typically 0.10 (90% coverage). Used for documentation only —
        the actual intervals are already in conformal_intervals.

    Returns
    -------
    EigenvalueUQResult with per-mode distributions and P(Level X) values.
    """
    try:
        from aeris.dynamics.state_space import (
            DimDerivatives,
            build_longitudinal_a_matrix,
            build_lateral_a_matrix,
            _eigenvalues,
            decompose_longitudinal_modes,
            decompose_lateral_modes,
        )
        from aeris.dynamics.mil_std import (
            SP_ZETA_LEVEL1_MIN, SP_ZETA_LEVEL1_MAX,
            SP_ZETA_LEVEL2_MIN, SP_ZETA_LEVEL2_MAX,
            PH_ZETA_LEVEL1_MIN, PH_ZETA_LEVEL2_MIN,
            ROLL_TAU_LEVEL1_MAX, ROLL_TAU_LEVEL2_MAX,
            SPIRAL_T2_MISSION_A,
            DR_ZETA_LEVEL1_MIN, DR_ZETA_OMEGA_LEVEL1,
            DR_ZETA_LEVEL2_MIN, DR_ZETA_OMEGA_LEVEL2,
        )
    except ImportError as e:
        raise ImportError(f"AERIS dynamics modules required: {e}")

    rng = random.Random(seed)
    alpha_rad = math.radians(alpha_deg)

    # Storage for sampled mode metrics
    sp_zetas:      list[float] = []
    sp_omegas:     list[float] = []
    ph_zetas:      list[float] = []
    ph_omegas:     list[float] = []
    roll_taus:     list[float] = []
    spiral_t2s:    list[float] = []
    dr_zetas:      list[float] = []
    dr_omegas:     list[float] = []
    dr_zeta_omegas: list[float] = []

    n_success = 0

    for _ in range(n_samples):
        # ── 1. Sample one derivative vector ──────────────────────────────
        d = _sample_uniform_marginal(point_estimates, conformal_intervals, rng)

        # Extract all needed derivatives with safe defaults
        CLa  = d.get("CLa",  4.0)    # lift curve slope — critical
        Cma  = d.get("Cma", -2.5)    # pitch stiffness — critical, must be negative
        CYb  = d.get("CYb", -0.15)
        Clb  = d.get("Clb", -0.08)
        Cnb  = d.get("Cnb",  0.05)
        Clp  = d.get("Clp", -0.22)
        Cmq  = d.get("Cmq", -8.0)
        Cnr  = d.get("Cnr", -0.12)
        Clr  = d.get("Clr",  0.10)
        Cnp  = d.get("Cnp", -0.05)
        CLu  = d.get("CLu",  0.0)
        Cmu  = d.get("Cmu",  0.0)
        CLq  = d.get("CLq",  CLa * 0.5)  # DATCOM estimate if missing
        CLp  = d.get("CLp",  0.0)
        CLr  = d.get("CLr",  0.0)
        CYp  = d.get("CYp",  0.0)
        CYr  = d.get("CYr",  0.0)
        CDa  = d.get("CDa",  0.0)
        Cmad = d.get("Cmad", 0.0)

        # Physical constraint: skip samples where pitch is unstable
        # (Cma > 0 means divergent pitch — the state-space has a real
        #  positive eigenvalue for short-period, not an oscillatory pair)
        # We still keep them but they will have no oscillatory SP mode.

        # ── 2. Assemble DimDerivatives ────────────────────────────────────
        try:
            dd = DimDerivatives(
                CLa=CLa, Cma=Cma,
                CYb=CYb, Clb=Clb, Cnb=Cnb,
                Clp=Clp, Cmq=Cmq, Cnr=Cnr,
                Clr=Clr, Cnp=Cnp,
                CLu=CLu, Cmu=Cmu,
                CLq=CLq, CLp=CLp, CLr=CLr,
                CYp=CYp, CYr=CYr,
                CDa=CDa, CD0=cd0,
                Cmad=Cmad,
                CL0=cl0, CD0_trim=cd0,
                alpha0_rad=alpha_rad,
                velocity_mps=velocity_mps,
                altitude_m=altitude_m,
                sref_m2=sref_m2,
                mac_m=mac_m,
                span_m=span_m,
                mass_kg=mass_kg,
                ixx_kg_m2=ixx_kg_m2 or mass_kg * 0.01,
                iyy_kg_m2=iyy_kg_m2 or mass_kg * 0.06,
                izz_kg_m2=izz_kg_m2 or mass_kg * 0.07,
            )

            # ── 3. Longitudinal modes ─────────────────────────────────────
            long_A = build_longitudinal_a_matrix(dd)
            long_eigs = _eigenvalues(long_A)
            sp_mode, ph_mode = decompose_longitudinal_modes(long_eigs)

            if sp_mode and sp_mode.zeta is not None and sp_mode.omega_n is not None:
                sp_zetas.append(sp_mode.zeta)
                sp_omegas.append(sp_mode.omega_n)

            if ph_mode and ph_mode.zeta is not None:
                ph_zetas.append(ph_mode.zeta)
                if ph_mode.omega_n is not None:
                    ph_omegas.append(ph_mode.omega_n)

            # ── 4. Lateral-directional modes ──────────────────────────────
            lat_A = build_lateral_a_matrix(dd)
            lat_eigs = _eigenvalues(lat_A)
            roll_mode, spiral_mode, dr_mode = decompose_lateral_modes(lat_eigs)

            if roll_mode and roll_mode.time_constant_s is not None:
                roll_taus.append(roll_mode.time_constant_s)

            if spiral_mode:
                if spiral_mode.time_to_double_s is not None:
                    spiral_t2s.append(spiral_mode.time_to_double_s)
                elif spiral_mode.stable:
                    spiral_t2s.append(float("inf"))

            if dr_mode and dr_mode.zeta is not None and dr_mode.omega_n is not None:
                dr_zetas.append(dr_mode.zeta)
                dr_omegas.append(dr_mode.omega_n)
                dr_zeta_omegas.append(dr_mode.zeta * dr_mode.omega_n)

            n_success += 1

        except Exception:
            # Numerically degenerate sample — skip silently
            continue

    # ── 5. Assemble UQ results ─────────────────────────────────────────────

    # Short-period zeta
    sp_zeta_uq = _mode_uq_result(
        metric_name="zeta_sp",
        values=sp_zetas,
        n_total=n_samples,
        point_estimate=point_estimates.get("sp_zeta_nominal"),
        level1_check_fn=lambda z: SP_ZETA_LEVEL1_MIN <= z <= SP_ZETA_LEVEL1_MAX,
        level2_check_fn=lambda z: SP_ZETA_LEVEL2_MIN <= z <= SP_ZETA_LEVEL2_MAX,
        stable_check_fn=lambda z: z > 0,
    )

    # Short-period omega_n
    sp_omega_uq = _mode_uq_result(
        metric_name="omega_n_sp_rad_s",
        values=sp_omegas,
        n_total=n_samples,
        point_estimate=point_estimates.get("sp_omega_nominal"),
        level1_check_fn=lambda w: 1.0 <= w <= 10.0,
        level2_check_fn=lambda w: w > 0,
        stable_check_fn=lambda w: w > 0,
    )

    # Phugoid zeta
    ph_zeta_uq = _mode_uq_result(
        metric_name="zeta_ph",
        values=ph_zetas,
        n_total=n_samples,
        point_estimate=point_estimates.get("ph_zeta_nominal"),
        level1_check_fn=lambda z: z >= PH_ZETA_LEVEL1_MIN,
        level2_check_fn=lambda z: z >= PH_ZETA_LEVEL2_MIN,
        stable_check_fn=lambda z: z > 0,
    )

    # Roll subsidence
    # Note: tau_r = -1/sigma; Level 1 requires tau_r ≤ 1.0 s
    roll_uq = _mode_uq_result(
        metric_name="tau_r_s",
        values=roll_taus,
        n_total=n_samples,
        point_estimate=point_estimates.get("roll_tau_nominal"),
        level1_check_fn=lambda t: 0 < t <= ROLL_TAU_LEVEL1_MAX,
        level2_check_fn=lambda t: 0 < t <= ROLL_TAU_LEVEL2_MAX,
        stable_check_fn=lambda t: t > 0,
    )

    # Spiral T2 — ISR threshold (20 s)
    # For stable spiral: inf > 20 s → Level 1
    spiral_uq = _mode_uq_result(
        metric_name="spiral_t2_s",
        values=[v for v in spiral_t2s if math.isfinite(v)],
        n_total=n_samples,
        point_estimate=point_estimates.get("spiral_t2_nominal"),
        level1_check_fn=lambda t: t >= SPIRAL_T2_MISSION_A,
        level2_check_fn=lambda t: t >= 8.0,
        stable_check_fn=lambda t: math.isinf(t) or t > 0,
    )
    # Adjust P(stable) to include stable-spiral samples (infinite T2)
    n_spiral_stable = sum(1 for v in spiral_t2s if math.isinf(v))
    if len(spiral_t2s) > 0:
        p_spiral_l1 = (
            sum(1 for v in spiral_t2s if math.isinf(v) or v >= SPIRAL_T2_MISSION_A)
            / len(spiral_t2s)
        )
        p_spiral_l2 = (
            sum(1 for v in spiral_t2s if math.isinf(v) or v >= 8.0)
            / len(spiral_t2s)
        )
        spiral_uq = ModeUQResult(
            metric_name="spiral_t2_s",
            n_samples=len(spiral_t2s),
            n_total=n_samples,
            point_estimate=spiral_uq.point_estimate,
            mean=spiral_uq.mean,
            std=spiral_uq.std,
            p05=spiral_uq.p05,
            p50=spiral_uq.p50,
            p95=spiral_uq.p95,
            p_level1=round(p_spiral_l1, 4),
            p_level2_or_better=round(p_spiral_l2, 4),
            p_stable=round((len(spiral_t2s)) / n_samples, 4),
            converged=len(spiral_t2s) >= 100,
        )

    # Dutch roll zeta
    dr_zeta_uq = _mode_uq_result(
        metric_name="zeta_dr",
        values=dr_zetas,
        n_total=n_samples,
        point_estimate=point_estimates.get("dr_zeta_nominal"),
        level1_check_fn=lambda z: z >= DR_ZETA_LEVEL1_MIN,
        level2_check_fn=lambda z: z >= DR_ZETA_LEVEL2_MIN,
        stable_check_fn=lambda z: z > 0,
    )

    # Dutch roll zeta*omega product
    dr_zo_uq = _mode_uq_result(
        metric_name="zeta_dr_omega_dr",
        values=dr_zeta_omegas,
        n_total=n_samples,
        point_estimate=None,
        level1_check_fn=lambda zo: zo >= DR_ZETA_OMEGA_LEVEL1,
        level2_check_fn=lambda zo: zo >= DR_ZETA_OMEGA_LEVEL2,
        stable_check_fn=lambda zo: zo > 0,
    )

    return EigenvalueUQResult(
        geometry_id=geometry_id,
        alpha_deg=alpha_deg,
        velocity_mps=velocity_mps,
        altitude_m=altitude_m,
        x_cg_m=x_cg_m,
        n_samples=n_samples,
        alpha_conformal=alpha_conformal,
        sampling_method="uniform_marginal_independent",
        short_period_zeta=sp_zeta_uq,
        short_period_omega_n=sp_omega_uq,
        phugoid_zeta=ph_zeta_uq,
        roll_tau=roll_uq,
        spiral_t2=spiral_uq,
        dutch_roll_zeta=dr_zeta_uq,
        dutch_roll_zeta_omega=dr_zo_uq,
        derivative_point_estimates=dict(point_estimates),
        derivative_intervals=dict(conformal_intervals),
        sample_success_rate=round(n_success / max(n_samples, 1), 4),
    )


# ---------------------------------------------------------------------------
# Convenience: build from AERIS aero_result dict + conformal calibration
# ---------------------------------------------------------------------------

def propagate_from_aero_result(
    *,
    aero_result: dict[str, Any],
    conformal_calibration: dict[str, float],
    mass_kg: float,
    iyy_kg_m2: float | None = None,
    izz_kg_m2: float | None = None,
    ixx_kg_m2: float | None = None,
    sref_m2: float | None = None,
    span_m: float | None = None,
    n_samples: int = 1000,
    alpha_conformal: float = 0.10,
    seed: int = 42,
    geometry_id: str | None = None,
) -> EigenvalueUQResult:
    """
    High-level entry point: extract derivatives from an aero_result dict,
    pair with conformal calibration, and run propagation.

    conformal_calibration: dict mapping derivative name → q_hat value.
    Typically loaded from conformal_calibration.json produced by
    aeris.ml.conformal.fit_conformal().
    """
    sad  = aero_result.get("stability_axis_derivatives") or {}
    sc   = aero_result.get("scalars") or {}
    meta = aero_result.get("solver_metadata") or {}
    fc   = meta.get("flight_condition") or {}

    def _f(d, *keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return None

    # Point estimates from aero result
    pe: dict[str, float] = {}
    for k, keys in [
        ("CLa",  ["CLa"]),
        ("Cma",  ["Cma"]),
        ("Cmq",  ["Cmq"]),
        ("CLq",  ["CLq"]),
        ("Clb",  ["Clb"]),
        ("Cnb",  ["Cnb"]),
        ("Clp",  ["Clp"]),
        ("Cnr",  ["Cnr"]),
        ("Clr",  ["Clr"]),
        ("Cnp",  ["Cnp"]),
        ("CYb",  ["CYb"]),
        ("CYp",  ["CYp"]),
        ("CYr",  ["CYr"]),
        ("CLu",  ["CLu"]),
        ("Cmu",  ["Cmu"]),
        ("CDa",  ["CDa"]),
    ]:
        v = _f(sad, *keys)
        if v is not None:
            pe[k] = v

    # Flight condition
    alpha_deg    = _f(fc, "alpha_deg") or 4.0
    velocity_mps = _f(fc, "velocity_mps") or 28.0
    altitude_m   = _f(fc, "altitude_m") or 1500.0
    cl0          = _f(sc, "cl", "CL") or 0.3
    cd0          = _f(sc, "cd", "CD") or 0.03

    # Reference geometry — try to infer from aero result, fallback to crude estimate
    if sref_m2 is None:
        # Cannot infer Sref from aero result reliably; caller should provide it
        # Fallback: for a 12.5 kg UAV at 28 m/s cruise CL~0.35
        from aeris.dynamics.analysis import dynamic_pressure
        q_inf = dynamic_pressure(velocity_mps, altitude_m)
        sref_m2 = max(mass_kg * 9.81 / (max(q_inf, 1.0) * max(cl0, 0.1)), 0.05)

    if span_m is None:
        # AR ~ 5 is typical for BWB; S = b²/AR
        span_m = math.sqrt(sref_m2 * 5.0)

    mac_m = _f(aero_result, "mac_m", "mean_aerodynamic_chord_m") or math.sqrt(sref_m2 / 5.0)
    x_cg_m = meta.get("x_cg_m") or 0.4

    return propagate_uq(
        point_estimates=pe,
        conformal_intervals=conformal_calibration,
        mass_kg=mass_kg,
        iyy_kg_m2=iyy_kg_m2,
        izz_kg_m2=izz_kg_m2,
        ixx_kg_m2=ixx_kg_m2,
        velocity_mps=velocity_mps,
        altitude_m=altitude_m,
        sref_m2=sref_m2,
        mac_m=mac_m,
        span_m=span_m,
        x_cg_m=x_cg_m,
        alpha_deg=alpha_deg,
        cl0=cl0,
        cd0=cd0,
        n_samples=n_samples,
        alpha_conformal=alpha_conformal,
        seed=seed,
        geometry_id=geometry_id,
    )


# ---------------------------------------------------------------------------
# UQ plot data: P(Level X) vs. conformal interval width
# ---------------------------------------------------------------------------

def sensitivity_to_interval_width(
    *,
    point_estimates: dict[str, float],
    base_intervals: dict[str, float],
    scale_factors: list[float] | None = None,
    n_samples: int = 500,
    seed: int = 42,
    **propagate_kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Sweep conformal interval widths by a scaling factor and show how
    P(Level 1 short-period) degrades as uncertainty grows.

    This produces the "cost of uncertainty" figure for Paper 2:
    x-axis: interval scale factor (1.0 = nominal, 2.0 = double width)
    y-axis: P(Level 1 ζ_sp)

    Used to demonstrate that tighter UQ directly improves design confidence —
    the core argument for investing in HF data to narrow conformal intervals.
    """
    if scale_factors is None:
        scale_factors = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]

    results: list[dict[str, Any]] = []
    for sf in scale_factors:
        scaled = {k: v * sf for k, v in base_intervals.items()}
        uq = propagate_uq(
            point_estimates=point_estimates,
            conformal_intervals=scaled,
            n_samples=n_samples,
            seed=seed,
            **propagate_kwargs,
        )
        sp = uq.short_period_zeta
        ph = uq.phugoid_zeta
        results.append({
            "scale_factor":    sf,
            "p_l1_sp_zeta":    sp.p_level1 if sp else None,
            "p_l1_ph_zeta":    ph.p_level1 if ph else None,
            "sp_zeta_p50":     sp.p50 if sp else None,
            "sp_zeta_std":     sp.std if sp else None,
            "success_rate":    uq.sample_success_rate,
        })

    return results
