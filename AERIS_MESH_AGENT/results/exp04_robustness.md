# Experiment 4 — robustness across fold partitions

20 independent grouped partitions of the 100 geometries. Every number below is a counterfactual replay of the 162-attempt production campaign.

| policy                                        |   repeats |   attempts_mean |   attempts_sd |   attempts_min |   attempts_max |   first_attempt_mean |   worst_case_mean |   quality_mean |   quality_loss_pct |
|:----------------------------------------------|----------:|----------------:|--------------:|---------------:|---------------:|---------------------:|------------------:|---------------:|-------------------:|
| ranking (design only)                         |        20 |          132.85 |         2.134 |            130 |            139 |                0.893 |             21    |          0.212 |              0     |
| ranking (design+surface)                      |        20 |          133    |         2.575 |            128 |            139 |                0.901 |             21    |          0.212 |              0     |
| ranking + accept-first-valid (design only)    |        20 |          107.35 |         1.424 |            105 |            110 |                0.946 |              3    |          0.209 |              1.281 |
| ranking + accept-first-valid (design+surface) |        20 |          105.95 |         1.701 |            103 |            109 |                0.957 |              3.05 |          0.209 |              1.222 |
| ranking + ceiling stopping (design only)      |        20 |          114.8  |         3.205 |            110 |            123 |                0.898 |              4.25 |          0.211 |              0.162 |
| ranking + ceiling stopping (design+surface)   |        20 |          112.85 |         3.376 |            107 |            119 |                0.911 |              3.85 |          0.211 |              0.43  |

Reference: atlas as run = **162** attempts (first-attempt 0.74, worst case 21); oracle lower bound = **100**.

**Reading it.** The cheapest policy that holds accepted quality within 0.5% of the incumbent (`ranking + ceiling stopping (design+surface)`) averages 112.8 +/- 3.4 attempts against the atlas's 162, recovering 79% of the 62 attempts an oracle would save. Across 20 partitions it never needed more than 119 nor fewer than 107: the spread is an order of magnitude smaller than the saving, so this is a property of the method and not of one partition.

`ranking + accept-first-valid (design+surface)` is cheaper still at 106.0 +/- 1.7, but gives up 1.22% of accepted quality. It is reported, not headlined.
