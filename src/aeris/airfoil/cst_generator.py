"""CST airfoil generator integration for AERIS 2D workflows.

This module turns robust CST/Kulfan airfoil generation into a first-class AERIS
library source.  It intentionally writes the same library contract used by
``aeris airfoil ingest``:

    airfoil_inventory.csv
    coords/<airfoil_id>.npz

so downstream XFOIL dataset generation, QC, curation, promotion, EDA, and ML
work without a separate special-case pipeline.

Generator ID: ``cst_airfoil_v1``
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import yaml

from aeris.airfoil.models import compute_airfoil_id, compute_geometry_stats
from aeris.airfoil.cst_reporting import polish_cst_library_outputs

ArrayLike = Union[Sequence[float], np.ndarray]
CST_GENERATOR_ID = "cst_airfoil_v1"


# ---------------------------------------------------------------------------
# Core CST math
# ---------------------------------------------------------------------------
def cosine_spacing(n: int = 201) -> np.ndarray:
    """Cosine-clustered x/c distribution in [0, 1]."""
    if n < 3:
        raise ValueError("n must be >= 3")
    beta = np.linspace(0.0, np.pi, int(n))
    return 0.5 * (1.0 - np.cos(beta))


def class_function(x: np.ndarray, n1: float, n2: float) -> np.ndarray:
    """Kulfan class function C(x)=x^N1(1-x)^N2, safe at endpoints."""
    x = np.asarray(x, dtype=float)
    xc = np.clip(x, 0.0, 1.0)
    with np.errstate(invalid="ignore"):
        c = np.power(xc, n1) * np.power(1.0 - xc, n2)
    return np.nan_to_num(c, nan=0.0)


def bernstein_matrix(x: np.ndarray, order: int) -> np.ndarray:
    """Matrix B[i,j] = comb(order,j) x_i^j (1-x_i)^(order-j)."""
    x = np.asarray(x, dtype=float)
    order = int(order)
    j = np.arange(order + 1)
    k = np.array([math.comb(order, int(v)) for v in j], dtype=float)
    xx = x[:, None]
    return k[None, :] * np.power(xx, j[None, :]) * np.power(1.0 - xx, order - j[None, :])


@dataclass(frozen=True)
class ValidationLimits:
    """Hard geometry limits used by ``CSTAirfoil.validate``."""

    min_thickness: float = 0.005
    max_thickness: float = 0.50
    min_local_gap: float = 0.0
    interior_eps: float = 1e-4
    max_le_radius: float = 0.30
    min_le_radius: float = 1e-6
    max_curvature_reversals: int = 6
    n_check: int = 401
    min_area: float = 1e-4


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.valid)

    def __str__(self) -> str:
        if self.valid:
            return "VALID  " + ", ".join(f"{k}={v:.5g}" for k, v in self.metrics.items())
        return "INVALID [" + "; ".join(self.failures) + "]"


class CSTAirfoil:
    """Kulfan/CST airfoil with independent upper/lower Bernstein vectors."""

    DEFAULT_ORDER = 8
    DEFAULT_N1 = 0.5
    DEFAULT_N2 = 1.0

    def __init__(
        self,
        au: ArrayLike,
        al: ArrayLike,
        *,
        n1: float = DEFAULT_N1,
        n2: float = DEFAULT_N2,
        dz_te: float = 0.0,
        order: int | None = None,
        limits: ValidationLimits | None = None,
        name: str = "CST",
    ) -> None:
        self.au = np.atleast_1d(np.asarray(au, dtype=float)).copy()
        self.al = np.atleast_1d(np.asarray(al, dtype=float)).copy()
        if order is None:
            order = len(self.au) - 1
        if len(self.au) != order + 1 or len(self.al) != order + 1:
            raise ValueError(
                f"Coefficient vectors must have length order+1={order + 1}; "
                f"got au={len(self.au)}, al={len(self.al)}"
            )
        if n1 <= 0 or n2 <= 0:
            raise ValueError("n1 and n2 must be positive")
        if dz_te < 0:
            raise ValueError("dz_te must be >= 0")
        self.order = int(order)
        self.n1 = float(n1)
        self.n2 = float(n2)
        self.dz_te = float(dz_te)
        self.limits = limits or ValidationLimits()
        self.name = str(name)

    def _surface(self, x: np.ndarray, coeffs: np.ndarray, te_sign: float) -> np.ndarray:
        x_in = np.asarray(x, dtype=float)
        scalar = x_in.ndim == 0
        xv = np.atleast_1d(x_in)
        z = class_function(xv, self.n1, self.n2) * (bernstein_matrix(xv, self.order) @ coeffs)
        z = z + te_sign * 0.5 * self.dz_te * xv
        return float(z[0]) if scalar else z

    def upper(self, x: ArrayLike) -> np.ndarray:
        return self._surface(np.asarray(x, dtype=float), self.au, +1.0)

    def lower(self, x: ArrayLike) -> np.ndarray:
        return self._surface(np.asarray(x, dtype=float), self.al, -1.0)

    def thickness(self, x: ArrayLike) -> np.ndarray:
        return self.upper(x) - self.lower(x)

    def camber(self, x: ArrayLike) -> np.ndarray:
        return 0.5 * (self.upper(x) + self.lower(x))

    def coordinates(self, n_per_surface: int = 161) -> np.ndarray:
        """Selig-ordered loop: TE -> upper -> LE -> lower -> TE."""
        x = cosine_spacing(n_per_surface)
        zu = self.upper(x)
        zl = self.lower(x)
        xy_u = np.column_stack([x[::-1], zu[::-1]])
        xy_l = np.column_stack([x[1:], zl[1:]])
        return np.vstack([xy_u, xy_l])

    def le_radius(self) -> float:
        if abs(self.n1 - 0.5) < 1e-12:
            r_u = 0.5 * self.au[0] ** 2
            r_l = 0.5 * self.al[0] ** 2
            return float(0.5 * (r_u + r_l))
        xs = np.array([1e-6, 4e-6, 9e-6])
        return float(_circumradius(np.column_stack([xs, self.upper(xs)])))

    def max_thickness(self) -> tuple[float, float]:
        x = cosine_spacing(801)
        t = self.thickness(x)
        idx = int(np.argmax(t))
        return float(t[idx]), float(x[idx])

    def area(self) -> float:
        xy = self.coordinates(401)
        x, z = xy[:, 0], xy[:, 1]
        return float(abs(0.5 * np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z)))

    def validate(self, limits: ValidationLimits | None = None) -> ValidationReport:
        limits = limits or self.limits
        failures: list[str] = []
        metrics: dict[str, Any] = {}
        x = cosine_spacing(limits.n_check)
        interior = (x > limits.interior_eps) & (x < 1.0 - limits.interior_eps)
        xi = x[interior]
        zu = self.upper(x)
        zl = self.lower(x)

        if not (np.all(np.isfinite(zu)) and np.all(np.isfinite(zl))):
            return ValidationReport(False, ["non_finite_coordinates"], metrics)

        gap = zu[interior] - zl[interior]
        min_gap = float(np.min(gap)) if gap.size else 0.0
        metrics["min_gap"] = min_gap
        if min_gap <= limits.min_local_gap:
            xworst = float(xi[int(np.argmin(gap))]) if xi.size else float("nan")
            failures.append(f"surface_crossover(min_gap={min_gap:.3e} at x={xworst:.3f})")

        tmax, xt = self.max_thickness()
        metrics["t_max"] = tmax
        metrics["x_tmax"] = xt
        if tmax < limits.min_thickness:
            failures.append(f"too_thin(t_max={tmax:.4f} < {limits.min_thickness})")
        if tmax > limits.max_thickness:
            failures.append(f"too_thick(t_max={tmax:.4f} > {limits.max_thickness})")

        xy = self.coordinates(201)
        n_intersections = _count_self_intersections(xy, closed=True)
        metrics["self_intersections"] = n_intersections
        if n_intersections > 0:
            failures.append(f"self_intersection(count={n_intersections})")

        area = self.area()
        metrics["area"] = area
        if area < limits.min_area:
            failures.append(f"area_too_small({area:.2e} < {limits.min_area})")

        try:
            rle = self.le_radius()
        except Exception:
            rle = float("nan")
        metrics["r_le"] = rle
        if not np.isfinite(rle) or rle < limits.min_le_radius:
            failures.append(f"bad_le_radius({rle:.3e})")
        elif rle > limits.max_le_radius:
            failures.append(f"le_radius_too_large({rle:.3f} > {limits.max_le_radius})")

        for label, z in (("upper", zu), ("lower", zl)):
            rev = _curvature_reversals(x[interior], z[interior])
            metrics[f"curv_rev_{label}"] = rev
            if rev > limits.max_curvature_reversals:
                failures.append(f"wiggly_{label}(reversals={rev} > {limits.max_curvature_reversals})")

        te_gap = float(zu[-1] - zl[-1])
        metrics["te_gap"] = te_gap
        if abs(te_gap - self.dz_te) > 1e-9:
            failures.append(f"te_gap_inconsistent({te_gap:.3e} vs dz_te={self.dz_te:.3e})")

        return ValidationReport(len(failures) == 0, failures, metrics)

    @classmethod
    def generate_random(
        cls,
        *,
        order: int = DEFAULT_ORDER,
        n1: float = DEFAULT_N1,
        n2: float = DEFAULT_N2,
        dz_te: float = 0.0,
        au_bounds: tuple[float, float] = (0.05, 0.35),
        al_bounds: tuple[float, float] = (-0.35, 0.05),
        limits: ValidationLimits | None = None,
        rng: np.random.Generator | None = None,
        max_attempts: int = 500,
        name: str = "CST-random",
    ) -> "CSTAirfoil":
        rng = rng or np.random.default_rng()
        limits = limits or ValidationLimits()
        for attempt in range(1, max_attempts + 1):
            au = rng.uniform(float(au_bounds[0]), float(au_bounds[1]), int(order) + 1)
            al = rng.uniform(float(al_bounds[0]), float(al_bounds[1]), int(order) + 1)
            if au[0] - al[0] < 0.02:
                continue
            foil = cls(
                au,
                al,
                n1=n1,
                n2=n2,
                dz_te=dz_te,
                order=order,
                limits=limits,
                name=f"{name}-{attempt}",
            )
            if foil.validate(limits):
                return foil
        raise RuntimeError(
            f"generate_random: no valid airfoil in {max_attempts} attempts; "
            f"check coefficient bounds and validation limits."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "order": self.order,
            "n1": self.n1,
            "n2": self.n2,
            "dz_te": self.dz_te,
            "au": self.au.tolist(),
            "al": self.al.tolist(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CSTAirfoil":
        return cls(
            payload["au"],
            payload["al"],
            n1=payload.get("n1", cls.DEFAULT_N1),
            n2=payload.get("n2", cls.DEFAULT_N2),
            dz_te=payload.get("dz_te", 0.0),
            order=payload.get("order"),
            name=payload.get("name", "CST"),
        )

    # ---------------- batch generation ----------------
    @classmethod
    def generate_batch(
        cls,
        n: int,
        *,
        seed: int | None = None,
        **kwargs,
    ) -> "list[CSTAirfoil]":
        """Generate *n* guaranteed-valid random airfoils, reproducible via *seed*."""
        rng = np.random.default_rng(seed)
        return [
            cls.generate_random(rng=rng, name=f"CST-batch-{i:04d}", **kwargs)
            for i in range(n)
        ]

    # ---------------- LSQ fitting ----------------
    @classmethod
    def fit(
        cls,
        x_upper: "ArrayLike",
        z_upper: "ArrayLike",
        x_lower: "ArrayLike",
        z_lower: "ArrayLike",
        *,
        order: int = DEFAULT_ORDER,
        n1: float = DEFAULT_N1,
        n2: float = DEFAULT_N2,
        dz_te: float | None = None,
        name: str = "CST-fit",
    ) -> "tuple[CSTAirfoil, float]":
        """Least-squares fit of upper/lower coordinate arrays to a CST representation.

        Coordinates must be normalised to unit chord (LE at x=0, TE at x=1).
        Returns (airfoil, rms_error).  rms is the RMS coordinate residual
        over both surfaces in chord units.
        """
        xu = np.asarray(x_upper, dtype=float)
        zu = np.asarray(z_upper, dtype=float)
        xl = np.asarray(x_lower, dtype=float)
        zl = np.asarray(z_lower, dtype=float)
        if dz_te is None:
            dz_te = max(0.0, float(zu[int(np.argmax(xu))] - zl[int(np.argmax(xl))]))

        def _solve(xs, zs, te_sign):
            C = class_function(xs, n1, n2)
            B = bernstein_matrix(xs, order)
            rhs = zs - te_sign * 0.5 * dz_te * xs
            A = C[:, None] * B
            a, *_ = np.linalg.lstsq(A, rhs, rcond=None)
            return a

        au = _solve(xu, zu, +1.0)
        al = _solve(xl, zl, -1.0)
        foil = cls(au, al, n1=n1, n2=n2, dz_te=dz_te, order=order, name=name)
        err = np.concatenate([foil.upper(xu) - zu, foil.lower(xl) - zl])
        return foil, float(np.sqrt(np.mean(err ** 2)))

    @classmethod
    def fit_dat(
        cls,
        path: "str | Path",
        **kwargs,
    ) -> "tuple[CSTAirfoil, float]":
        """Fit CST coefficients directly from a Selig-format ``.dat`` file."""
        pts = _read_selig(str(path))
        i_le = int(np.argmin(pts[:, 0]))
        upper = pts[: i_le + 1][::-1]   # LE→TE
        lower = pts[i_le:]               # LE→TE
        return cls.fit(
            upper[:, 0], upper[:, 1],
            lower[:, 0], lower[:, 1],
            **kwargs,
        )

    # ---------------- I/O methods ----------------
    def to_dat(
        self,
        path: "str | Path",
        n_per_surface: int = 161,
        header: str | None = None,
    ) -> None:
        """Write Selig-format ``.dat`` file (XFOIL/XFLR5/SU2 compatible)."""
        xy = self.coordinates(n_per_surface)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write((header or self.name) + "\n")
            for px, pz in xy:
                fh.write(f"  {float(px): .8f}  {float(pz): .8f}\n")

    def to_json(self, path: "str | Path") -> None:
        """Serialize the airfoil to a JSON file at *path* (atomic write)."""
        import json as _json
        import os as _os
        import tempfile as _tf
        payload = _json.dumps(self.to_dict(), indent=2)
        _path = Path(path)
        _path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = _tf.mkstemp(dir=_path.parent, prefix=".tmp_cst_", suffix=".json")
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            _os.replace(tmp, _path)
        except Exception:
            try: _os.unlink(tmp)
            except OSError: pass
            raise

    @classmethod
    def from_json(cls, path: "str | Path") -> "CSTAirfoil":
        """Deserialize a ``CSTAirfoil`` from a JSON file written by :meth:`to_json`."""
        import json as _json
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(_json.load(fh))

    # ---------------- visualisation ----------------
    def plot(self, ax=None, show_camber: bool = True, **plot_kw):
        """Plot the airfoil cross-section (requires matplotlib)."""
        import matplotlib.pyplot as _plt
        if ax is None:
            _, ax = _plt.subplots(figsize=(9, 3))
        x = cosine_spacing(401)
        ax.plot(x, self.upper(x), lw=1.6, **plot_kw)
        ax.plot(x, self.lower(x), lw=1.6, **plot_kw)
        if show_camber:
            ax.plot(x, self.camber(x), "--", lw=0.9, alpha=0.7)
        ax.set_aspect("equal")
        ax.grid(alpha=0.3)
        ax.set_xlabel("x/c")
        ax.set_ylabel("z/c")
        ax.set_title(self.name)
        return ax

    # ---------------- repr ----------------
    def __repr__(self) -> str:
        t, xt = self.max_thickness()
        return (
            f"CSTAirfoil(name={self.name!r}, order={self.order}, "
            f"N1={self.n1}, N2={self.n2}, dz_te={self.dz_te}, "
            f"t/c={t:.4f}@{xt:.2f})"
        )


# ---------------------------------------------------------------------------
# AERIS library generation
# ---------------------------------------------------------------------------
def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _as_pair(value: Any, *, name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be a two-element [min, max] list")
    lo, hi = float(value[0]), float(value[1])
    if not math.isfinite(lo) or not math.isfinite(hi) or hi < lo:
        raise ValueError(f"{name} bounds invalid: {value}")
    return lo, hi


def _limits_from_config(cfg: dict[str, Any]) -> ValidationLimits:
    allowed = set(ValidationLimits.__dataclass_fields__)
    values = {k: v for k, v in (cfg or {}).items() if k in allowed}
    return ValidationLimits(**values)


def _load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("CST generator config must be a YAML mapping")
    return data


def _config_block(data: dict[str, Any]) -> dict[str, Any]:
    # Preferred structure: airfoil.generator: {...}
    if isinstance(data.get("airfoil"), dict) and isinstance(data["airfoil"].get("generator"), dict):
        return data["airfoil"]["generator"]
    # Backward-friendly structure: cst_airfoil: {...}
    if isinstance(data.get("cst_airfoil"), dict):
        return data["cst_airfoil"]
    # Minimal: top-level is the block
    return data


def _write_dat(path: Path, name: str, xy: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"{name}\n")
        for x, z in xy:
            fh.write(f"  {float(x): .8f}  {float(z): .8f}\n")


def generate_cst_airfoil_library(
    *,
    config_path: Path,
    output_dir: Path,
    n_airfoils: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a CST airfoil library compatible with AERIS XFOIL workflows."""
    config_path = Path(config_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    data = _load_config(config_path)
    block = _config_block(data)

    generator_id = str(block.get("id", CST_GENERATOR_ID)).strip()
    if generator_id != CST_GENERATOR_ID:
        raise ValueError(f"Unsupported airfoil generator id {generator_id!r}; expected {CST_GENERATOR_ID!r}")

    n = int(n_airfoils if n_airfoils is not None else block.get("n_airfoils", 25))
    if n < 1:
        raise ValueError("n_airfoils must be >= 1")

    resolved_seed = seed if seed is not None else block.get("seed", 123)
    resolved_seed = None if resolved_seed is None else int(resolved_seed)
    rng = np.random.default_rng(resolved_seed)

    order = int(block.get("order", CSTAirfoil.DEFAULT_ORDER))
    if order < 1:
        raise ValueError("CST order must be >= 1")
    n1 = float(block.get("n1", CSTAirfoil.DEFAULT_N1))
    n2 = float(block.get("n2", CSTAirfoil.DEFAULT_N2))
    dz_te = float(block.get("dz_te", 0.0))
    n_per_surface = int(block.get("n_per_surface", 161))
    max_attempts = int(block.get("max_attempts", 500))

    bounds = block.get("coefficient_bounds", {}) or {}
    au_bounds = _as_pair(bounds.get("au", [0.05, 0.35]), name="coefficient_bounds.au")
    al_bounds = _as_pair(bounds.get("al", [-0.35, 0.05]), name="coefficient_bounds.al")
    limits = _limits_from_config(block.get("validation_limits", {}) or {})

    coords_dir = output_dir / "coords"
    dat_dir = output_dir / "dat"
    json_dir = output_dir / "cst_json"
    coords_dir.mkdir(parents=True, exist_ok=True)
    dat_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    attempts_total = 0
    i = 0
    while i < n:
        name = f"cst_airfoil_{i + 1:05d}"
        try:
            foil = CSTAirfoil.generate_random(
                order=order,
                n1=n1,
                n2=n2,
                dz_te=dz_te,
                au_bounds=au_bounds,
                al_bounds=al_bounds,
                limits=limits,
                rng=rng,
                max_attempts=max_attempts,
                name=name,
            )
            # The returned name carries the rejection-sampling attempt suffix.
            attempts_total += int(str(foil.name).rsplit("-", 1)[-1]) if "-" in foil.name else 1
            report = foil.validate(limits)
            xy = foil.coordinates(n_per_surface=n_per_surface)
            x = xy[:, 0].astype(float)
            y = xy[:, 1].astype(float)
            aid = compute_airfoil_id(x, y)
            if aid in seen_ids:
                failures.append({"index": i, "reason": f"duplicate_geometry({aid})"})
                continue
            seen_ids.add(aid)
            stats = compute_geometry_stats(x, y)
            t_max, x_tmax = foil.max_thickness()

            np.savez_compressed(coords_dir / f"{aid}.npz", x=x, y=y)
            dat_name = f"{name}.dat"
            _write_dat(dat_dir / dat_name, name, xy)
            (json_dir / f"{aid}.json").write_text(json.dumps(foil.to_dict(), indent=2), encoding="utf-8")

            row: dict[str, Any] = {
                "airfoil_id": aid,
                "name": name,
                "family": "cst",
                "source_file": dat_name,
                "n_coords": int(len(x)),
                "t_c": round(float(stats.t_c), 6),
                "t_c_x": round(float(stats.t_c_x), 6),
                "camber_max": round(float(stats.camber_max), 6),
                "camber_max_x": round(float(stats.camber_max_x), 6),
                "le_radius": round(float(stats.le_radius), 6),
                "te_angle_deg": round(float(stats.te_angle_deg), 4),
                "generator_id": CST_GENERATOR_ID,
                "parameterization": "cst_kulfan",
                "cst_order": int(foil.order),
                "cst_n1": float(foil.n1),
                "cst_n2": float(foil.n2),
                "cst_dz_te": float(foil.dz_te),
                "cst_t_max": float(t_max),
                "cst_x_tmax": float(x_tmax),
                "cst_area": float(foil.area()),
                "cst_r_le": float(foil.le_radius()),
                "cst_validation_valid": bool(report.valid),
                "cst_validation_failures": "|".join(report.failures),
                "cst_json": str(json_dir / f"{aid}.json"),
                "dat_path": str(dat_dir / dat_name),
            }
            for j, value in enumerate(foil.au):
                row[f"cst_u{j}"] = float(value)
            for j, value in enumerate(foil.al):
                row[f"cst_l{j}"] = float(value)
            rows.append(row)
            i += 1
        except Exception as exc:
            failures.append({"index": i, "reason": f"{type(exc).__name__}: {exc}"})
            if len(failures) > max(10, 5 * n):
                raise RuntimeError("Too many CST generation failures; aborting") from exc

    inventory_df = pd.DataFrame(rows)
    inventory_csv = output_dir / "airfoil_inventory.csv"
    inventory_df.to_csv(inventory_csv, index=False)

    report: dict[str, Any] = {
        "schema_version": "airfoil_cst_library_v1",
        "source_format": "generated_cst",
        "generator_id": CST_GENERATOR_ID,
        "generated_at_utc": _utc_now(),
        "config_path": str(config_path),
        "output_dir": str(output_dir),
        "n_airfoils_requested": n,
        "n_airfoils_generated": int(len(rows)),
        "seed": resolved_seed,
        "order": order,
        "n1": n1,
        "n2": n2,
        "dz_te": dz_te,
        "n_per_surface": n_per_surface,
        "coefficient_bounds": {"au": list(au_bounds), "al": list(al_bounds)},
        "validation_limits": asdict(limits),
        "failures": len(failures),
        "failure_details": failures,
        "inventory_csv": str(inventory_csv),
        "coords_dir": str(coords_dir),
        "dat_dir": str(dat_dir),
        "cst_json_dir": str(json_dir),
        "stats_summary": {
            "t_c_mean": round(float(inventory_df["t_c"].mean()), 4),
            "t_c_min": round(float(inventory_df["t_c"].min()), 4),
            "t_c_max": round(float(inventory_df["t_c"].max()), 4),
            "families": inventory_df["family"].value_counts().to_dict(),
        },
    }
    (output_dir / "cst_airfoil_library_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Compatibility name for existing operator expectations.
    (output_dir / "ingest_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # AERIS_PATCH_CST_POLISH_V1: normalize aliases and quick-inspection report.
    return polish_cst_library_outputs(output_dir)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _circumradius(points: np.ndarray) -> float:
    a = np.linalg.norm(points[1] - points[0])
    b = np.linalg.norm(points[2] - points[1])
    c = np.linalg.norm(points[2] - points[0])
    s = 0.5 * (a + b + c)
    area2 = max(s * (s - a) * (s - b) * (s - c), 0.0)
    if area2 == 0.0:
        return float("inf")
    return float(a * b * c / (4.0 * math.sqrt(area2)))


def _curvature_reversals(x: np.ndarray, z: np.ndarray) -> int:
    if len(x) < 5:
        return 0
    d2 = np.gradient(np.gradient(z, x), x)
    threshold = 1e-3 * max(float(np.max(np.abs(d2))), 1e-12)
    signs = np.sign(np.where(np.abs(d2) < threshold, 0.0, d2))
    signs = signs[signs != 0]
    if signs.size < 2:
        return 0
    return int(np.count_nonzero(np.diff(signs) != 0))


def _count_self_intersections(xy: np.ndarray, *, closed: bool = True) -> int:
    points = np.vstack([xy, xy[0]]) if closed else xy
    p = points[:-1]
    q = points[1:]
    m = len(p)
    d = q - p
    pi = p[:, None, :]
    di = d[:, None, :]
    pj = p[None, :, :]
    dj = d[None, :, :]
    denom = di[..., 0] * dj[..., 1] - di[..., 1] * dj[..., 0]
    rp = pj - pi
    t_num = rp[..., 0] * dj[..., 1] - rp[..., 1] * dj[..., 0]
    u_num = rp[..., 0] * di[..., 1] - rp[..., 1] * di[..., 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = t_num / denom
        u = u_num / denom
    eps = 1e-12
    proper = (np.abs(denom) > eps) & (t > eps) & (t < 1.0 - eps) & (u > eps) & (u < 1.0 - eps)
    idx = np.arange(m)
    adjacent = np.abs(idx[:, None] - idx[None, :]) <= 1
    if closed:
        adjacent |= np.abs(idx[:, None] - idx[None, :]) == m - 1
    proper &= ~adjacent
    return int(np.count_nonzero(proper) // 2)


def _read_selig(path: str) -> "np.ndarray":
    """Parse a Selig-format .dat coordinate file into shape (N, 2).

    Handles: name header on line 1, files starting with coordinates,
    comment lines (#/!), and blank separator lines between surfaces.

    Raises ValueError if fewer than 10 valid coordinate pairs are found.
    """
    rows: list = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        first_coord_seen = False
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("!"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                a, b = float(parts[0]), float(parts[1])
            except ValueError:
                # Non-numeric → airfoil name header or section label — skip
                continue
            first_coord_seen = True
            if -0.2 <= a <= 1.2 and -1.0 <= b <= 1.0:
                rows.append((a, b))
    if len(rows) < 10:
        raise ValueError(
            f"_read_selig: only {len(rows)} valid coordinate pairs in {path!r} "
            f"(minimum 10 required)"
        )
    return np.asarray(rows, dtype=float)
