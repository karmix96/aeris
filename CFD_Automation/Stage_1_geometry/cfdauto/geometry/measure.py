"""Measure the built wing.

Every value is read from points on the loft (or, without pyGeo, from the same
straight panels through the stations). Later stages use these measured values;
the design vector is only the label.
"""

from __future__ import annotations

import numpy as np

from .sections import Station

N_SPAN = 401
N_CHORD = 101


def span_table(le: np.ndarray, te_up: np.ndarray, te_lo: np.ndarray, tmax_c: np.ndarray) -> dict[str, np.ndarray]:
    """Along-span values from leading-edge and trailing-edge points (rows sorted by y)."""
    te_mid = 0.5 * (te_up + te_lo)
    d = te_mid - le
    chord = np.linalg.norm(d, axis=1)
    return {
        "y": le[:, 1],
        "x_le": le[:, 0],
        "z_le": le[:, 2],
        "chord": chord,
        "twist_deg": np.degrees(np.arctan2(-d[:, 2], d[:, 0])),
        "x_qc": le[:, 0] + 0.25 * d[:, 0],
        "te_thickness": np.linalg.norm(te_up - te_lo, axis=1),
        "tmax_c": tmax_c,
    }


def table_from_loft(loft, n: int = N_SPAN) -> dict[str, np.ndarray]:
    v = np.unique(np.concatenate([np.linspace(0.0, 1.0, n), loft.station_v]))
    u = np.linspace(0.0, 1.0, N_CHORD)
    uu, vv = np.meshgrid(u, v)
    up = loft.upper(uu, vv)
    lo = loft.lower(uu, vv)
    le, te_up, te_lo = up[:, 0], up[:, -1], lo[:, -1]
    chord = np.linalg.norm(0.5 * (te_up + te_lo) - le, axis=1)
    tmax_c = np.max(np.linalg.norm(up - lo, axis=2), axis=1) / chord
    return span_table(le, te_up, te_lo, tmax_c)


def table_from_stations(stations: list[Station], n: int = N_SPAN) -> dict[str, np.ndarray]:
    """Same table from the straight panels through the stations (no pyGeo)."""
    from .loft import section_points

    ys = np.array([s.y for s in stations])
    y = np.unique(np.concatenate([np.linspace(0.0, ys[-1], n), ys]))
    pts = [section_points(s) for s in stations]
    le_s = np.array([p[0][0] for p in pts])
    teu_s = np.array([p[0][-1] for p in pts])
    tel_s = np.array([p[1][-1] for p in pts])
    tmax_s = np.array([s.airfoil.thickness.max() for s in stations])

    def lerp(a):
        return np.column_stack([np.interp(y, ys, a[:, k]) for k in range(3)])

    return span_table(lerp(le_s), lerp(teu_s), lerp(tel_s), np.interp(y, ys, tmax_s))


def measure(table: dict[str, np.ndarray], stations: list[Station]) -> dict:
    """Measured values of one wing. Station values are read at the station y."""
    y = table["y"]
    s = float(y[-1])
    idx = [int(np.argmin(np.abs(y - st.y))) for st in stations]
    main = [i for i, st in zip(idx, stations) if st.name in ("b0", "b1", "b2", "b3")]

    def at(key, rows):
        return [float(table[key][i]) for i in rows]

    ym, xm, zm = (np.array(at(k, main)) for k in ("y", "x_le", "z_le"))
    chord = table["chord"]
    half_area = float(np.trapezoid(chord, y))
    mac = float(np.trapezoid(chord ** 2, y) / half_area)
    area = 2.0 * half_area
    return {
        "stations": {
            "y_m": ym.tolist(),
            "x_le_m": xm.tolist(),
            "z_le_m": zm.tolist(),
            "chord_m": at("chord", main),
            "twist_deg": at("twist_deg", main),
        },
        "panels": {
            "sweep_le_deg": np.degrees(np.arctan2(np.diff(xm), np.diff(ym))).tolist(),
            "dihedral_deg": np.degrees(np.arctan2(np.diff(zm), np.diff(ym))).tolist(),
        },
        "sections": [
            {"name": st.name, "y_m": float(y[i]), "chord_m": float(chord[i]),
             "te_thickness_m": float(table["te_thickness"][i])}
            for st, i in zip(stations, idx)
        ],
        "semi_span_m": s,
        "span_m": 2.0 * s,
        "area_m2": area,
        "mac_m": mac,
        "aspect_ratio": (2.0 * s) ** 2 / area,
        "max_thickness_c": float(np.max(table["tmax_c"])),
        "te_thickness_min_m": float(np.min(table["te_thickness"])),
        "te_thickness_max_m": float(np.max(table["te_thickness"])),
        "along_span": {k: np.asarray(v).tolist() for k, v in table.items()},
    }
