# Tip-Corner Origin Probe - lhs7_00

Surface-only. No pyHyp march, no solver. Decides whether the Stage 01 blocker is
a cap4 blocking artefact (H1) or a shared geometry defect that every strategy
would inherit (H2).

## Result: H1 confirmed, H2 rejected

### The tip-station geometry is clean

| check | value |
| --- | ---: |
| section points | 61 |
| collapsed segments (< 1e-9) | **0** |
| min segment length | 3.728e-03 |
| median segment length | 3.852e-02 |
| max turning angle | **41.96 deg** (at the leading edge) |
| 99th-percentile turning angle | 40.67 deg |

No cusp, no collapsed segment, no near-zero-length edge. The pyGeo tip section
handed to the mesher is a smooth airfoil. **S1-S5 do not inherit a broken OML.**

### The bad corner is invariant to where cap4 splits the contour

| variant | split_x_fore / aft | min shape | max skew | worst tip corner |
| --- | --- | ---: | ---: | ---: |
| cap4_split_0.10 | 0.10 / 0.90 | 3.7160e-04 | 0.9971 | **179.737 deg** |
| cap4_split_0.20 | 0.20 / 0.80 | 3.7160e-04 | 0.9971 | **179.737 deg** |
| cap4_split_0.35 | 0.35 / 0.65 | 3.7160e-04 | 0.9971 | **179.737 deg** |

The split really moved (confirmed in each `surface_report.json`), yet the worst
corner angle and shape metric are unchanged. That is the signature of the actual
mechanism: the airfoil-face cap takes its corners from the cap4 OML block
splits, and **any** split lands on a smooth part of the contour, where the two
edges meeting at the corner are collinear. A ~180 degree corner is produced by
construction, wherever the split is placed. Moving it cannot help.

### Every existing OML tip closure is affected, and cap4 is the least bad

| variant | outcome |
| --- | --- |
| cap4 | accepted; scaled Jacobian +4.584e-03, but a 179.737 deg corner |
| mid4 | **REJECTED** - `positive_scaled_jacobian` in `tip_ring_2` (-6.898e-02), `quad_triangle_normal_alignment` -1.0 |
| split8 | **REJECTED** - `positive_scaled_jacobian` in `tip_ring_5` (-2.838e-01), `quad_triangle_normal_alignment` -1.0, plus `open_boundary_off_root_plane` |

mid4 and split8 produce outright folded tip cells. Both were caught immediately
by the `positive_scaled_jacobian` gate added after the Variant B finding; before
that fix they would have been accepted silently.

## Conclusion

The defect belongs to AERIS's existing tip-closure implementations, not to the
geometry and not uniquely to cap4. The three legacy OML topologies all fail at
the tip; cap4 merely fails less obviously.

This is a legitimate tournament outcome for S0, not a prerequisite to repair.
S1-S5 construct their own tip treatment and start from a clean OML, so the
blocker does not propagate. Recommendation: record S0 as failing the volume
gate, re-base `epsE_common_start` on the first strategy that yields a clean
surface, and proceed to Stage 02.
