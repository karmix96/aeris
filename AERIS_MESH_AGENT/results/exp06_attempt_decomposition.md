# Experiment 6 — where the 162 attempts go

Campaign `development_atlas_qualified21_production_written_v3`: 162 attempts over 100 geometries. Preferred threshold 0.15.

## The three-way split

| class                                                  |   attempts | recoverable_by              |
|:-------------------------------------------------------|-----------:|:----------------------------|
| irreducible (one successful extrusion per geometry)    |        100 | nothing                     |
| routing (spent before any mesh passed)                 |         27 | better routing only         |
| quality search (spent after a mesh had already passed) |         35 | better routing, or stopping |

## Was the quality search rational?

- geometries that continued after a PASS: **11**
- of those, the first PASS was already at or above 0.15: **0**
- searches that improved the accepted mesh: **10 of 11**
- searches that lifted a fallback-grade mesh to preferred grade: **10**
- attempts spent on searches that paid off: **15**
- attempts spent on searches that returned nothing: **20**

| geometry_id       |   attempts |   post_pass_attempts |   first_pass_quality |   best_pass_quality |   accepted_quality | search_was_justified   | search_paid_off   | reached_preferred   |
|:------------------|-----------:|---------------------:|---------------------:|--------------------:|-------------------:|:-----------------------|:------------------|:--------------------|
| lhs100_seed42_095 |         21 |                   20 |             0.146811 |            0.146811 |           0.146811 | True                   | False             | False               |
| lhs100_seed42_007 |          6 |                    4 |             0.115122 |            0.153736 |           0.153736 | True                   | True              | True                |
| lhs100_seed42_068 |          3 |                    2 |             0.121582 |            0.191409 |           0.191409 | True                   | True              | True                |
| lhs100_seed42_089 |          3 |                    2 |             0.129962 |            0.174184 |           0.174184 | True                   | True              | True                |
| lhs100_seed42_002 |          2 |                    1 |             0.104218 |            0.17668  |           0.17668  | True                   | True              | True                |
| lhs100_seed42_012 |          4 |                    1 |             0.137967 |            0.162402 |           0.162402 | True                   | True              | True                |
| lhs100_seed42_054 |          2 |                    1 |             0.13859  |            0.178352 |           0.178352 | True                   | True              | True                |
| lhs100_seed42_064 |          2 |                    1 |             0.130293 |            0.237156 |           0.237156 | True                   | True              | True                |
| lhs100_seed42_057 |          2 |                    1 |             0.118929 |            0.174524 |           0.174524 | True                   | True              | True                |
| lhs100_seed42_076 |          2 |                    1 |             0.120841 |            0.230667 |           0.230667 | True                   | True              | True                |
| lhs100_seed42_072 |          2 |                    1 |             0.125669 |            0.155376 |           0.155376 | True                   | True              | True                |

## Reading it

Every one of the 11 searches was permitted by the incumbent's own acceptance rule — in each case the mesh already in hand was below 0.15 and the rule says keep looking. 10 of them found a better mesh, and every one of those crossed the preferred threshold. The incumbent's stopping behaviour is therefore not a defect in general: it is profitable in 10 of 11 cases.

The unprofitable search costs 20 attempts and belongs to 1 geometry. That is the entire quality-preserving prize available to a stopping rule, and capturing it means predicting that *no* template in the atlas can reach 0.15 for that geometry — a ceiling prediction, not a stopping heuristic.

A policy that stops at the first valid mesh instead saves all 35 search attempts by destroying the 10 profitable upgrades. That is the mechanism behind the preferred-threshold rate falling from 0.99 to 0.89 in experiment 3; it is not an untuned baseline, it is a baseline paying a known price.
