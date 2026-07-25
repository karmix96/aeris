# Evidence — native pyGeo→AVL output capture, geometry fidelity, ASB equivalence

Backs `decision/0005-native-avl-output-and-geometry-fidelity.md` and
`studies/native_avl_output_and_fidelity.md`. Rescued out of `data/` (gitignored,
regenerable) per the findings-live-in-configs rule.

All runs: `configs/geometry/bwb.yaml` at its default seed, 28 m/s, sea level,
25 extraction sections, 8 chordwise × 4 spanwise panels per section interval.

| file | what it is |
|---|---|
| `span_margin_probe.txt` / `.json` | Span-margin sensitivity sweep (0.02 → 0.0). Shows the old 2 % inset understated CL by 54.9 % and CLα by 26.2 % via the YDUPLICATE centreline gap. Regenerate: `python standalone/lowfi_avl_study/probe_span_margin.py` |
| `verification_report.txt` / `.json` | Field-by-field native vs AeroSandbox comparison over three cases (clean symmetric / pitch control / lateral). Fields missing in native: NONE. Case A agrees to ≤0.6 %. Regenerate: `python standalone/lowfi_avl_study/verify_native_vs_asb.py` |
| `native_avl_result_example.json` | A complete `NativeAvlResult` dump — the reference for what the hardened runner now captures (e, Xnp, 25 stability + 18 body derivatives, per-control authority, hinge moments, surface forces, discretisation counts). |
| `example_avl_stability_dump.txt` | The raw AVL `st` dump the parsers are tested against, including the `d01`/`d02` control-derivative columns. |

## Headline numbers

- Span margin 0.02 → 0.0: CL ×2.22, CLα 2.741 → 3.715 /rad, L/D 3.39 → 7.25.
- Elevon extent fix: CL_δe 0.00810 → 0.00945 /deg (+16.7 %).
- Native vs ASB, clean symmetric: CLα 8e-7, Xnp 1e-5, CD 5e-4, CL 5.2e-3.
- ASB reference path has **zero** differential (roll) elevon authority — its AVL
  exporter emits a single `all_deflections` control variable.
