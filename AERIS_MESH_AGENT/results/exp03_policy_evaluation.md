# Experiment 3 — counterfactual policy replay

Campaign `development_atlas_qualified21_production_written_v3`: 162 recorded attempts over 100 geometries. Learned policies are restricted to the templates the atlas actually tried, and use predictions made out-of-fold with the target geometry held out.

## All 100 geometries

| policy                                                |   geometries |   total_attempts |   total_seconds |   mean_attempts |   max_attempts |   success_rate |   first_attempt_success |   mean_accepted_quality |   reached_preferred_rate |
|:------------------------------------------------------|-------------:|-----------------:|----------------:|----------------:|---------------:|---------------:|------------------------:|------------------------:|-------------------------:|
| atlas (as run)                                        |          100 |              162 |         2859.51 |            1.62 |             21 |              1 |                    0.74 |                  0.2118 |                     0.99 |
| atlas ordering + accept-first-valid                   |          100 |              127 |         2356.53 |            1.27 |              5 |              1 |                    0.83 |                  0.2059 |                     0.89 |
| learned ranking (design only)                         |          100 |              133 |         2508.05 |            1.33 |             21 |              1 |                    0.89 |                  0.2118 |                     0.99 |
| learned ranking + accept-first-valid (design only)    |          100 |              109 |         2198.52 |            1.09 |              3 |              1 |                    0.93 |                  0.2101 |                     0.96 |
| learned ranking + ceiling stopping (design only)      |          100 |              114 |         2262.67 |            1.14 |              4 |              1 |                    0.9  |                  0.2112 |                     0.97 |
| learned ranking (design+surface)                      |          100 |              137 |         2575.03 |            1.37 |             21 |              1 |                    0.88 |                  0.2118 |                     0.99 |
| learned ranking + accept-first-valid (design+surface) |          100 |              109 |         2203.21 |            1.09 |              3 |              1 |                    0.94 |                  0.209  |                     0.94 |
| learned ranking + ceiling stopping (design+surface)   |          100 |              117 |         2339.24 |            1.17 |              5 |              1 |                    0.89 |                  0.2112 |                     0.97 |
| oracle (upper bound)                                  |          100 |              100 |         2150.52 |            1    |              1 |              1 |                    1    |                  0.2118 |                     0.99 |

## The 26 geometries the atlas could not do in one attempt

The other 74 cost exactly one attempt for every policy, so they dilute the comparison without informing it.

| policy                                                |   geometries |   total_attempts |   mean_attempts |   max_attempts |   mean_quality |
|:------------------------------------------------------|-------------:|-----------------:|----------------:|---------------:|---------------:|
| atlas (as run)                                        |           26 |               88 |          3.3846 |             21 |         0.1996 |
| atlas ordering + accept-first-valid                   |           26 |               53 |          2.0385 |              5 |         0.1769 |
| learned ranking (design only)                         |           26 |               59 |          2.2692 |             21 |         0.1996 |
| learned ranking (design+surface)                      |           26 |               63 |          2.4231 |             21 |         0.1996 |
| learned ranking + accept-first-valid (design only)    |           26 |               35 |          1.3462 |              3 |         0.193  |
| learned ranking + accept-first-valid (design+surface) |           26 |               35 |          1.3462 |              3 |         0.1888 |
| learned ranking + ceiling stopping (design only)      |           26 |               40 |          1.5385 |              4 |         0.1971 |
| learned ranking + ceiling stopping (design+surface)   |           26 |               43 |          1.6538 |              5 |         0.1972 |
| oracle (upper bound)                                  |           26 |               26 |          1      |              1 |         0.1996 |

## The trade the stopping rule makes

| policy                                                |   total_attempts |   attempts_saved_pct |   hours |   mean_accepted_quality |   quality_loss_pct |   reached_preferred_rate |
|:------------------------------------------------------|-----------------:|---------------------:|--------:|------------------------:|-------------------:|-------------------------:|
| atlas (as run)                                        |              162 |                0     |   0.794 |                   0.212 |              0     |                     0.99 |
| atlas ordering + accept-first-valid                   |              127 |               21.605 |   0.655 |                   0.206 |              2.791 |                     0.89 |
| learned ranking (design only)                         |              133 |               17.901 |   0.697 |                   0.212 |              0     |                     0.99 |
| learned ranking + accept-first-valid (design only)    |              109 |               32.716 |   0.611 |                   0.21  |              0.808 |                     0.96 |
| learned ranking + ceiling stopping (design only)      |              114 |               29.63  |   0.629 |                   0.211 |              0.303 |                     0.97 |
| learned ranking (design+surface)                      |              137 |               15.432 |   0.715 |                   0.212 |              0     |                     0.99 |
| learned ranking + accept-first-valid (design+surface) |              109 |               32.716 |   0.612 |                   0.209 |              1.332 |                     0.94 |
| learned ranking + ceiling stopping (design+surface)   |              117 |               27.778 |   0.65  |                   0.211 |              0.298 |                     0.97 |
| oracle (upper bound)                                  |              100 |               38.272 |   0.597 |                   0.212 |              0     |                     0.99 |

**Headline (quality-preserving).** Atlas 162 attempts -> **114** with `learned ranking + ceiling stopping (design only)`, a 29.6% reduction for a 0.30% change in accepted quality. An oracle would need 100, so this recovers 77% of the attainable saving.

**The cheaper, lossier option.** `learned ranking + accept-first-valid (design only)` reaches 109 attempts (32.7%) but gives up 0.81% of accepted quality and drops the preferred-threshold rate to 0.96. Speed bought with quality is not the same result, and the paper reports both rather than picking the flattering one.

**Attempts are not minutes.** The incumbent spends 48 min, of which 36 min is irreducible: every geometry needs one successful extrusion, and a successful attempt is the expensive kind (20.0 s, against 11.2 s for a folded march, 9.4 s for an under-quality mesh and about 0 s for a surface-build error). Only 12 min is addressable overhead, and the headline policy removes 84% of it (48 -> 38 min). So a 30% cut in attempts is a 21% cut in time; quoting the attempt figure alone would overstate the gain.

## Attribution: which half does the work?

| policy                                         |   total_attempts |   attempts_saved |   pct_of_available |   quality_loss_pct |   reached_preferred_rate |
|:-----------------------------------------------|-----------------:|-----------------:|-------------------:|-------------------:|-------------------------:|
| atlas (as run)                                 |              162 |                0 |               0    |               0    |                     0.99 |
| atlas ordering + accept-first-valid (no model) |              127 |               35 |              56.45 |               2.79 |                     0.89 |
| atlas ordering + learned stopping              |              147 |               15 |              24.19 |               0.3  |                     0.97 |
| learned ordering only                          |              133 |               29 |              46.77 |               0    |                     0.99 |
| learned ordering + learned stopping            |              114 |               48 |              77.42 |               0.3  |                     0.97 |
| oracle (upper bound)                           |              100 |               62 |             100    |               0    |                     0.99 |

Ordering and stopping are separable and they compose: alone they save 29 and 15 of the 62 attempts an oracle would save, together 48. The line that matters is the model-free one — stopping at the first valid mesh needs no machine learning and saves 35, but it pays **2.79 %** of accepted quality and drops the preferred-threshold rate from 0.99 to 0.89. The learned policy saves more (48) for **0.30 %**, roughly a ninth of that cost. So the defensible claim is not that learning beats a heuristic on attempts; it is that **the cheap fix cannot reach this operating point at all** — at matched quality, no model-free policy in this comparison gets past 29.

**How much of this is machine learning?** Adding *only* a stopping rule to the incumbent ordering — no model at all — already reaches 127 attempts (21.6%), at a 2.79% quality cost. The learned ranking's contribution is what it adds beyond that line, and the honest reading is that the missing stopping rule, not the routing, is the incumbent's larger defect.
