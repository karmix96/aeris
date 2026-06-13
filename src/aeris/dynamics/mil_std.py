"""
AERIS Dynamics — MIL-STD-1797B Handling Quality Classifier
===========================================================
Classifies dynamic modes into Level 1 / Level 2 / Level 3 / Unacceptable
per MIL-STD-1797B, and maps them to the three AERIS military mission classes.

Design rules:
- Boundaries are named constants, never magic numbers.
- Every classification returns a probability stub (1.0 for deterministic
  input; fills with conformal UQ samples in Paper 2 probabilistic mode).
- Mission classes map to different threshold sets exactly per PhD roadmap.
- No side effects — all functions are pure.

Reference:
  [MIL] MIL-HDBK-1797A, "Flying Qualities of Piloted Aircraft", 1997.
  [MIL2] MIL-STD-1797B, 2012 (boundary tables).
  PhD Roadmap, Section 3.1 — Screening Policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class HQLevel(Enum):
    LEVEL_1      = 1   # Adequate — satisfactory without improvement
    LEVEL_2      = 2   # Acceptable — adequate, some crew workload
    LEVEL_3      = 3   # Controllable — but crew workload excessive
    UNACCEPTABLE = 4   # Below Level 3 — not controllable


class MissionClass(Enum):
    ISR       = "A"   # Mission A — ISR/Loiter, Level 1 required
    ATTRITABLE = "B"  # Mission B — Attritable, Level 2 minimum
    STRIKE    = "C"   # Mission C — Strike/Payload delivery


# ---------------------------------------------------------------------------
# MIL-STD-1797B boundaries (per PhD Roadmap, Section 3.1)
# ---------------------------------------------------------------------------

# Short-period damping ratio ζ_sp
SP_ZETA_LEVEL1_MIN   = 0.35
SP_ZETA_LEVEL1_MAX   = 1.30
SP_ZETA_LEVEL2_MIN   = 0.25
SP_ZETA_LEVEL2_MAX   = 2.00
SP_ZETA_LEVEL3_MIN   = 0.15

# Short-period natural frequency ω_sp [rad/s]
# Category B flight phase (cruise): 0.085·n/α ≤ ω²_sp ≤ 3.6·n/α
# Simplified bounds for UAV screening (Class II, Phase B):
SP_OMEGA_N_LEVEL1_MIN = 1.0   # [rad/s]
SP_OMEGA_N_LEVEL1_MAX = 10.0  # [rad/s]  — generous for small UAVs

# Phugoid damping ratio ζ_ph
PH_ZETA_LEVEL1_MIN   = 0.04
PH_ZETA_LEVEL2_MIN   = 0.0    # underdamped but stable
# Level 3: divergent (ζ < 0) allowed if T₂ ≥ 55 s

# Dutch roll ζ_DR and ζ_DR·ω_DR product
DR_ZETA_LEVEL1_MIN   = 0.08
DR_ZETA_OMEGA_LEVEL1 = 0.15   # ζ_DR·ω_DR ≥ 0.15 [rad/s]
DR_ZETA_LEVEL2_MIN   = 0.02
DR_ZETA_OMEGA_LEVEL2 = 0.05
DR_ZETA_LEVEL3_MIN   = 0.0    # just needs ζ > 0

# Roll subsidence time constant τ_r [s]
ROLL_TAU_LEVEL1_MAX  = 1.0    # s  (Class IV Phase A — small UAV proxy)
ROLL_TAU_LEVEL2_MAX  = 1.4    # s
ROLL_TAU_LEVEL3_MAX  = 10.0   # s

# Spiral divergence T₂ [s] — minimum acceptable doubling time
# Mission-dependent (per PhD roadmap):
SPIRAL_T2_MISSION_A  = 20.0   # ISR — hands-off loiter, T₂ ≥ 20 s
SPIRAL_T2_MISSION_B  = 8.0    # Attritable
SPIRAL_T2_MISSION_C  = 8.0    # Strike

# Static margin % MAC targets per mission
SM_LEVEL1_MISSION_A  = 5.0    # % MAC
SM_LEVEL1_MISSION_B  = 3.0
SM_LEVEL1_MISSION_C  = 0.0    # must remain positive at payload-release CG


# ---------------------------------------------------------------------------
# Classification result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ModeClassification:
    """Classification result for one dynamic mode."""
    mode_name: str                    # "short_period", "phugoid", etc.
    level: HQLevel
    value: float | None               # primary metric value (ζ, τ, T₂, etc.)
    metric_name: str                  # human-readable metric name
    boundary_used: dict               # which boundaries were applied
    p_level1: float | None = None     # P(Level 1) — from UQ sampling; 1.0 for deterministic
    p_level2: float | None = None     # P(Level 2 or better)
    escalate: bool = False            # True if Level 3 or Unacceptable
    note: str | None = None


@dataclass
class HandlingQualityReport:
    """Complete MIL-STD-1797B handling quality report for one design point."""
    mission: MissionClass
    static_margin: ModeClassification | None = None
    short_period_damping: ModeClassification | None = None
    short_period_frequency: ModeClassification | None = None
    phugoid: ModeClassification | None = None
    roll_subsidence: ModeClassification | None = None
    dutch_roll: ModeClassification | None = None
    spiral: ModeClassification | None = None

    # Composite result
    overall_level: HQLevel = HQLevel.UNACCEPTABLE
    overall_escalate: bool = False
    flyable: bool = False             # True if overall Level 1 or 2
    mission_compliant: bool = False   # True if meets mission target level
    missing_modes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        def _mode(m: ModeClassification | None) -> dict | None:
            if m is None:
                return None
            return {
                "mode": m.mode_name,
                "level": m.level.value,
                "level_name": m.level.name,
                "value": m.value,
                "metric": m.metric_name,
                "p_level1": m.p_level1,
                "escalate": m.escalate,
                "note": m.note,
            }
        return {
            "mission": self.mission.value,
            "overall_level": self.overall_level.value,
            "flyable": self.flyable,
            "mission_compliant": self.mission_compliant,
            "escalate": self.overall_escalate,
            "static_margin": _mode(self.static_margin),
            "short_period_damping": _mode(self.short_period_damping),
            "short_period_frequency": _mode(self.short_period_frequency),
            "phugoid": _mode(self.phugoid),
            "roll_subsidence": _mode(self.roll_subsidence),
            "dutch_roll": _mode(self.dutch_roll),
            "spiral": _mode(self.spiral),
            "missing_modes": self.missing_modes,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Individual mode classifiers
# ---------------------------------------------------------------------------

def classify_static_margin(
    sm_percent_mac: float,
    mission: MissionClass,
) -> ModeClassification:
    """Classify static margin against mission-specific threshold."""
    thresholds = {
        MissionClass.ISR:        SM_LEVEL1_MISSION_A,
        MissionClass.ATTRITABLE: SM_LEVEL1_MISSION_B,
        MissionClass.STRIKE:     SM_LEVEL1_MISSION_C,
    }
    threshold = thresholds[mission]
    bounds = {"threshold_percent_mac": threshold, "mission": mission.value}

    if sm_percent_mac >= threshold:
        level = HQLevel.LEVEL_1
        note = f"SM = {sm_percent_mac:.2f}% MAC ≥ {threshold}% MAC threshold."
    elif sm_percent_mac > 0:
        level = HQLevel.LEVEL_2
        note = f"SM = {sm_percent_mac:.2f}% MAC > 0 but below {threshold}% MAC target."
    elif sm_percent_mac > -5.0:
        level = HQLevel.LEVEL_3
        note = f"SM = {sm_percent_mac:.2f}% MAC — marginally unstable. Active control required."
    else:
        level = HQLevel.UNACCEPTABLE
        note = f"SM = {sm_percent_mac:.2f}% MAC — strongly unstable. Escalate."

    return ModeClassification(
        mode_name="static_margin",
        level=level,
        value=sm_percent_mac,
        metric_name="static margin [%MAC]",
        boundary_used=bounds,
        p_level1=1.0 if level == HQLevel.LEVEL_1 else 0.0,
        p_level2=1.0 if level.value <= 2 else 0.0,
        escalate=level.value >= 3,
        note=note,
    )


def classify_short_period_damping(zeta: float) -> ModeClassification:
    """Classify short-period damping ratio per MIL-STD-1797B."""
    bounds = {
        "L1": f"[{SP_ZETA_LEVEL1_MIN}, {SP_ZETA_LEVEL1_MAX}]",
        "L2": f"[{SP_ZETA_LEVEL2_MIN}, {SP_ZETA_LEVEL2_MAX}]",
        "L3": f"[{SP_ZETA_LEVEL3_MIN}, ∞)",
    }
    if SP_ZETA_LEVEL1_MIN <= zeta <= SP_ZETA_LEVEL1_MAX:
        level = HQLevel.LEVEL_1
        note = f"ζ_sp = {zeta:.3f} ∈ [{SP_ZETA_LEVEL1_MIN}, {SP_ZETA_LEVEL1_MAX}]"
    elif SP_ZETA_LEVEL2_MIN <= zeta <= SP_ZETA_LEVEL2_MAX:
        level = HQLevel.LEVEL_2
        note = f"ζ_sp = {zeta:.3f} — Level 2 (outside Level 1 band)"
    elif zeta >= SP_ZETA_LEVEL3_MIN:
        level = HQLevel.LEVEL_3
        note = f"ζ_sp = {zeta:.3f} — Level 3 (barely controllable)"
    else:
        level = HQLevel.UNACCEPTABLE
        note = f"ζ_sp = {zeta:.3f} — below Level 3 minimum. Escalate."

    return ModeClassification(
        mode_name="short_period_damping",
        level=level,
        value=zeta,
        metric_name="short-period ζ_sp [-]",
        boundary_used=bounds,
        p_level1=1.0 if level == HQLevel.LEVEL_1 else 0.0,
        p_level2=1.0 if level.value <= 2 else 0.0,
        escalate=level.value >= 3,
        note=note,
    )


def classify_short_period_frequency(omega_n: float) -> ModeClassification:
    """Classify short-period natural frequency (simplified bounds for UAV screening)."""
    bounds = {"L1_min_rad_s": SP_OMEGA_N_LEVEL1_MIN, "L1_max_rad_s": SP_OMEGA_N_LEVEL1_MAX}
    if SP_OMEGA_N_LEVEL1_MIN <= omega_n <= SP_OMEGA_N_LEVEL1_MAX:
        level = HQLevel.LEVEL_1
        note = f"ω_sp = {omega_n:.3f} rad/s within acceptable band."
    elif omega_n > 0:
        level = HQLevel.LEVEL_2
        note = f"ω_sp = {omega_n:.3f} rad/s outside preferred band."
    else:
        level = HQLevel.UNACCEPTABLE
        note = f"ω_sp = {omega_n:.3f} rad/s — non-physical."

    return ModeClassification(
        mode_name="short_period_frequency",
        level=level,
        value=omega_n,
        metric_name="ω_sp [rad/s]",
        boundary_used=bounds,
        p_level1=1.0 if level == HQLevel.LEVEL_1 else 0.0,
        p_level2=1.0 if level.value <= 2 else 0.0,
        escalate=level.value >= 3,
        note=note,
    )


def classify_phugoid(
    zeta: float | None,
    t2_s: float | None = None,
) -> ModeClassification:
    """Classify phugoid mode. Level 3 allows divergent if T₂ ≥ 55 s."""
    if zeta is None:
        return ModeClassification(
            mode_name="phugoid",
            level=HQLevel.LEVEL_2,
            value=None,
            metric_name="phugoid ζ_ph [-]",
            boundary_used={},
            p_level1=None, p_level2=None,
            note="Phugoid damping not computed — phugoid mode data unavailable.",
        )

    bounds = {"L1_min": PH_ZETA_LEVEL1_MIN, "L2_min": PH_ZETA_LEVEL2_MIN}
    if zeta >= PH_ZETA_LEVEL1_MIN:
        level = HQLevel.LEVEL_1
        note = f"ζ_ph = {zeta:.4f} ≥ {PH_ZETA_LEVEL1_MIN} — Level 1."
    elif zeta >= PH_ZETA_LEVEL2_MIN:
        level = HQLevel.LEVEL_2
        note = f"ζ_ph = {zeta:.4f} — underdamped but stable. Level 2."
    elif t2_s is not None and t2_s >= 55.0:
        # Level 3: divergent but slow enough to be acceptable
        level = HQLevel.LEVEL_3
        note = f"ζ_ph = {zeta:.4f} < 0 but T₂ = {t2_s:.1f} s ≥ 55 s — Level 3 acceptable."
    else:
        level = HQLevel.UNACCEPTABLE
        note = (
            f"ζ_ph = {zeta:.4f} < 0 and T₂ = {t2_s:.1f} s < 55 s — "
            "divergent phugoid. Escalate."
        )

    return ModeClassification(
        mode_name="phugoid",
        level=level,
        value=zeta,
        metric_name="phugoid ζ_ph [-]",
        boundary_used=bounds,
        p_level1=1.0 if level == HQLevel.LEVEL_1 else 0.0,
        p_level2=1.0 if level.value <= 2 else 0.0,
        escalate=level.value >= 3,
        note=note,
    )


def classify_roll_subsidence(tau_r_s: float) -> ModeClassification:
    """Classify roll subsidence time constant."""
    bounds = {
        "L1_max_s": ROLL_TAU_LEVEL1_MAX,
        "L2_max_s": ROLL_TAU_LEVEL2_MAX,
        "L3_max_s": ROLL_TAU_LEVEL3_MAX,
    }
    if tau_r_s <= ROLL_TAU_LEVEL1_MAX:
        level = HQLevel.LEVEL_1
        note = f"τ_r = {tau_r_s:.3f} s ≤ {ROLL_TAU_LEVEL1_MAX} s — Level 1."
    elif tau_r_s <= ROLL_TAU_LEVEL2_MAX:
        level = HQLevel.LEVEL_2
        note = f"τ_r = {tau_r_s:.3f} s — Level 2."
    elif tau_r_s <= ROLL_TAU_LEVEL3_MAX:
        level = HQLevel.LEVEL_3
        note = f"τ_r = {tau_r_s:.3f} s — Level 3 (sluggish roll response)."
    else:
        level = HQLevel.UNACCEPTABLE
        note = f"τ_r = {tau_r_s:.3f} s > {ROLL_TAU_LEVEL3_MAX} s — unacceptable."

    return ModeClassification(
        mode_name="roll_subsidence",
        level=level,
        value=tau_r_s,
        metric_name="τ_r [s]",
        boundary_used=bounds,
        p_level1=1.0 if level == HQLevel.LEVEL_1 else 0.0,
        p_level2=1.0 if level.value <= 2 else 0.0,
        escalate=level.value >= 3,
        note=note,
    )


def classify_dutch_roll(
    zeta_dr: float | None,
    omega_n_dr: float | None,
) -> ModeClassification:
    """Classify Dutch roll per ζ_DR and ζ_DR·ω_DR product bounds."""
    if zeta_dr is None or omega_n_dr is None:
        return ModeClassification(
            mode_name="dutch_roll",
            level=HQLevel.LEVEL_2,
            value=None,
            metric_name="ζ_DR [-]",
            boundary_used={},
            p_level1=None, p_level2=None,
            note="Dutch roll data unavailable.",
        )

    product = zeta_dr * omega_n_dr
    bounds = {
        "L1_zeta_min": DR_ZETA_LEVEL1_MIN,
        "L1_zeta_omega_min": DR_ZETA_OMEGA_LEVEL1,
        "L2_zeta_min": DR_ZETA_LEVEL2_MIN,
        "L2_zeta_omega_min": DR_ZETA_OMEGA_LEVEL2,
    }

    if zeta_dr >= DR_ZETA_LEVEL1_MIN and product >= DR_ZETA_OMEGA_LEVEL1:
        level = HQLevel.LEVEL_1
        note = f"ζ_DR = {zeta_dr:.4f}, ζ_DR·ω_DR = {product:.4f} — Level 1."
    elif zeta_dr >= DR_ZETA_LEVEL2_MIN and product >= DR_ZETA_OMEGA_LEVEL2:
        level = HQLevel.LEVEL_2
        note = f"ζ_DR = {zeta_dr:.4f}, ζ_DR·ω_DR = {product:.4f} — Level 2."
    elif zeta_dr > DR_ZETA_LEVEL3_MIN:
        level = HQLevel.LEVEL_3
        note = f"ζ_DR = {zeta_dr:.4f} > 0 — Level 3 (oscillatory but divergent damping)."
    else:
        level = HQLevel.UNACCEPTABLE
        note = f"ζ_DR = {zeta_dr:.4f} ≤ 0 — divergent Dutch roll. Escalate."

    return ModeClassification(
        mode_name="dutch_roll",
        level=level,
        value=zeta_dr,
        metric_name="ζ_DR [-]",
        boundary_used=bounds,
        p_level1=1.0 if level == HQLevel.LEVEL_1 else 0.0,
        p_level2=1.0 if level.value <= 2 else 0.0,
        escalate=level.value >= 3,
        note=note,
    )


def classify_spiral(
    t2_s: float | None,
    stable: bool,
    mission: MissionClass,
) -> ModeClassification:
    """Classify spiral mode by time-to-double (divergent) or stability."""
    thresholds = {
        MissionClass.ISR:        SPIRAL_T2_MISSION_A,
        MissionClass.ATTRITABLE: SPIRAL_T2_MISSION_B,
        MissionClass.STRIKE:     SPIRAL_T2_MISSION_C,
    }
    t2_min = thresholds[mission]
    bounds = {"T2_min_s": t2_min, "mission": mission.value}

    if stable:
        level = HQLevel.LEVEL_1
        note = "Spiral mode stable — T₂ = ∞ (no divergence)."
        value = float("inf")
    elif t2_s is not None and t2_s >= t2_min:
        level = HQLevel.LEVEL_1 if t2_s >= SPIRAL_T2_MISSION_A else HQLevel.LEVEL_2
        note = f"Spiral: T₂ = {t2_s:.1f} s ≥ {t2_min:.0f} s — acceptable for autopilot."
        value = t2_s
    elif t2_s is not None and t2_s >= 4.0:
        level = HQLevel.LEVEL_3
        note = f"Spiral: T₂ = {t2_s:.1f} s — slow divergence. Level 3."
        value = t2_s
    elif t2_s is not None:
        level = HQLevel.UNACCEPTABLE
        note = f"Spiral: T₂ = {t2_s:.1f} s < 4 s — fast divergence. Escalate."
        value = t2_s
    else:
        # AERIS_PATCH_D11_APPLIED: divergent spiral with unknown T₂ → LEVEL_3.
        # Cannot claim LEVEL_2 (acceptable) when spiral is divergent but rate unknown.
        # LEVEL_3 = controllable with pilot compensation; honest for unknown instability.
        level = HQLevel.LEVEL_3 if not stable else HQLevel.LEVEL_2
        note = (
            "Spiral mode divergent (stable=False) but T₂ not computed — classified LEVEL_3 "
            "(requires pilot/autopilot compensation). Run state-space analysis to compute T₂."
            if not stable else
            "Spiral mode data unavailable; classified LEVEL_2 (conservative default for stable/unknown)."
        )
        value = None

    return ModeClassification(
        mode_name="spiral",
        level=level,
        value=value,
        metric_name="T₂ [s]",
        boundary_used=bounds,
        p_level1=1.0 if level == HQLevel.LEVEL_1 else 0.0,
        p_level2=1.0 if level.value <= 2 else 0.0,
        escalate=level.value >= 3,
        note=note,
    )


# ---------------------------------------------------------------------------
# Top-level classifier
# ---------------------------------------------------------------------------

def classify_handling_qualities(
    *,
    mission: MissionClass,
    static_margin_pct_mac: float | None = None,
    sp_zeta: float | None = None,
    sp_omega_n: float | None = None,
    ph_zeta: float | None = None,
    ph_t2_s: float | None = None,
    roll_tau_s: float | None = None,
    dutch_zeta: float | None = None,
    dutch_omega_n: float | None = None,
    spiral_t2_s: float | None = None,
    spiral_stable: bool | None = None,
) -> HandlingQualityReport:
    """
    Classify all available modes for a given mission.
    Returns a HandlingQualityReport with per-mode and overall classification.
    """
    report = HandlingQualityReport(mission=mission)
    classifications: list[ModeClassification] = []
    missing: list[str] = []

    # Static margin
    if static_margin_pct_mac is not None:
        c = classify_static_margin(static_margin_pct_mac, mission)
        report.static_margin = c
        classifications.append(c)
    else:
        missing.append("static_margin")

    # Short-period damping
    if sp_zeta is not None:
        c = classify_short_period_damping(sp_zeta)
        report.short_period_damping = c
        classifications.append(c)
    else:
        missing.append("short_period_damping")

    # Short-period frequency
    if sp_omega_n is not None:
        c = classify_short_period_frequency(sp_omega_n)
        report.short_period_frequency = c
        classifications.append(c)
    else:
        missing.append("short_period_frequency")

    # Phugoid
    ph = classify_phugoid(ph_zeta, ph_t2_s)
    report.phugoid = ph
    classifications.append(ph)

    # Lateral-directional (optional)
    if roll_tau_s is not None:
        c = classify_roll_subsidence(roll_tau_s)
        report.roll_subsidence = c
        classifications.append(c)
    else:
        missing.append("roll_subsidence")

    if dutch_zeta is not None or dutch_omega_n is not None:
        c = classify_dutch_roll(dutch_zeta, dutch_omega_n)
        report.dutch_roll = c
        classifications.append(c)
    else:
        missing.append("dutch_roll")

    if spiral_t2_s is not None or spiral_stable is not None:
        c = classify_spiral(spiral_t2_s, spiral_stable or False, mission)
        report.spiral = c
        classifications.append(c)
    else:
        missing.append("spiral")

    # Overall: worst of all classified modes
    if classifications:
        worst = max(classifications, key=lambda c: c.level.value)
        report.overall_level = worst.level
        report.overall_escalate = any(c.escalate for c in classifications)
    else:
        report.overall_level = HQLevel.UNACCEPTABLE
        report.overall_escalate = True

    report.flyable = report.overall_level.value <= 2
    report.missing_modes = missing

    # Mission compliance
    required_level = {
        MissionClass.ISR:        HQLevel.LEVEL_1,
        MissionClass.ATTRITABLE: HQLevel.LEVEL_2,
        MissionClass.STRIKE:     HQLevel.LEVEL_1,  # longitudinal Level 1 required
    }
    report.mission_compliant = (
        report.overall_level.value <= required_level[mission].value
    )

    return report
