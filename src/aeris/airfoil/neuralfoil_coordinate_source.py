"""AeroSandbox-free NeuralFoil polar source.

`NeuralFoilPolarSource` is correct but uses AeroSandbox in one place: it converts
section coordinates to Kulfan weights via ``asb.Airfoil(...).to_kulfan_airfoil()``
in ``register_shape`` and evaluates ``get_aero_from_kulfan_parameters``.

This subclass removes that dependency by overriding exactly two methods:

* ``register_shape`` — store the Selig coordinates only (no Kulfan conversion).
* ``_evaluate_alpha_sweep`` — evaluate ``neuralfoil.get_aero_from_coordinates``
  directly on the stored coordinates.

Everything else (CDCL fitting, Re-grid warming, cl-bounds, query_cd/_batch, the
CdclParams contract consumed by inject_polar_cdcl and the strip profile-drag
integration) is inherited unchanged, so this drops into
``solver_options["polar_store"]`` exactly like the parent.

NeuralFoil's coordinate core is incompressible (no Mach input), identical to the
Kulfan core in that respect; ``mach`` stays a documented interface no-op.
"""

from __future__ import annotations

import numpy as np

from aeris.airfoil.neuralfoil_polar_source import (
    _DEFAULT_ALPHA_SWEEP_DEG,
    _MIN_POLAR_POINTS,
    NeuralFoilPolarSource,
    _RegisteredShape,
    log,
    shape_id_from_coordinates,
)

_ZERO8 = np.zeros(8, dtype=float)


class NeuralFoilCoordinateSource(NeuralFoilPolarSource):
    """NeuralFoil polar source that never imports AeroSandbox."""

    def register_shape(self, coordinates: "np.ndarray", airfoil_id: str | None = None) -> str:
        coords = np.asarray(coordinates, dtype=float)
        aid = airfoil_id or shape_id_from_coordinates(coords)
        if aid in self._shapes:
            return aid
        # ASB-free: store coordinates only. The Kulfan fields on _RegisteredShape
        # are required by the dataclass but never read on this path (our
        # _evaluate_alpha_sweep uses the coordinates directly).
        self._shapes[aid] = _RegisteredShape(
            coordinates=coords,
            kulfan_lower_weights=_ZERO8,
            kulfan_upper_weights=_ZERO8,
            kulfan_leading_edge_weight=0.0,
            kulfan_TE_thickness=0.0,
        )
        return aid

    def _evaluate_alpha_sweep(
        self, shape: "_RegisteredShape", *, re: float, mach: float
    ) -> "tuple[np.ndarray | None, np.ndarray | None]":
        try:
            import neuralfoil as nf
        except ImportError as exc:
            raise RuntimeError(
                "NeuralFoilCoordinateSource requires the 'neuralfoil' package. "
                "Install with: pip install neuralfoil --break-system-packages"
            ) from exc

        n_alpha = len(_DEFAULT_ALPHA_SWEEP_DEG)
        _ = mach  # incompressible core; documented no-op (mirrors the parent)
        try:
            aero = nf.get_aero_from_coordinates(
                coordinates=np.asarray(shape.coordinates, dtype=float),
                alpha=_DEFAULT_ALPHA_SWEEP_DEG,
                Re=np.full(n_alpha, max(float(re), 1.0)),
                n_crit=self.n_crit,
                model_size=self.model_size,
            )
        except Exception as exc:  # pragma: no cover - network/runtime guard
            log.debug("NeuralFoilCoordinateSource: evaluation failed: %s", exc)
            return None, None

        cl = np.asarray(aero["CL"], dtype=float)
        cd = np.asarray(aero["CD"], dtype=float)
        valid = np.isfinite(cl) & np.isfinite(cd) & (cd > 0)
        if valid.sum() < _MIN_POLAR_POINTS:
            return None, None
        return cl[valid], cd[valid]
