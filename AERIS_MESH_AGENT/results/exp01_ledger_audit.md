# Experiment 1 — atlas ledger audit

## Campaign inventory

| campaign                                            | config_key                                |   attempts |   geometries |   templates |
|:----------------------------------------------------|:------------------------------------------|-----------:|-------------:|------------:|
| development_atlas_maximin16_production_written_v2   | 1.5|3.5999999999999994e-06|257|production |        220 |          100 |          16 |
| development_atlas_maximin16_smoke                   | None|None|None|None                       |        131 |          100 |          16 |
| development_atlas_production_written_canary_v2      | 1.5|3.5999999999999994e-06|257|production |          2 |            2 |           2 |
| development_atlas_qualified21_production_written_v3 | 1.5|3.5999999999999994e-06|257|production |        162 |          100 |          21 |
| development_atlas_smoke_all100                      | None|None|None|None                       |        184 |          100 |          10 |
| production_seed_failure_canary                      | None|3e-06|257|production                 |         28 |            2 |          14 |

## Pooled production configuration

- config key (eps_e | first cell | N | level): `1.5|3.5999999999999994e-06|257|production`
- attempts: **384** over 100 geometries and 21 templates
- unique (geometry, template) cells observed: **247** of 2100 (11.8%)
- **cells measured twice that disagree: 0** — the pipeline reproduces itself exactly across independent campaigns

## Outcome classes (unique cells)

| outcome             |   cells |   share |
|:--------------------|--------:|--------:|
| PASS                |     139 |   0.563 |
| FAIL_FOLDED         |      49 |   0.198 |
| FAIL_LOW_QUALITY    |      38 |   0.154 |
| SURFACE_BUILD_ERROR |      21 |   0.085 |

## Headline campaign — `development_atlas_qualified21_production_written_v3`

- attempts: **162** for 100 geometries (1.62 per geometry)
- first-attempt completion: **74/100**
- worst case: **21** attempts
- attempts made **after a PASS already existed** (quality search, not failure recovery): **35**
- acceptance rule recovered from the records: accept at quality >= 0.15, fall back to best >= 0.1

### Attempts per geometry

|   attempts |   geometries |
|-----------:|-------------:|
|          1 |           74 |
|          2 |           15 |
|          3 |            6 |
|          4 |            2 |
|          5 |            1 |
|          6 |            1 |
|         21 |            1 |

### The decisive case — geometry 95 (`lhs100_seed42_095`)

|   attempt_ordinal |   template_index | outcome             |   min_scaled_quality |
|------------------:|-----------------:|:--------------------|---------------------:|
|                 1 |               95 | PASS                |            0.146811  |
|                 2 |               94 | FAIL_LOW_QUALITY    |            0.08005   |
|                 3 |               92 | FAIL_FOLDED         |           -0.110052  |
|                 4 |               70 | FAIL_FOLDED         |           -0.197302  |
|                 5 |               47 | SURFACE_BUILD_ERROR |          nan         |
|                 6 |               16 | SURFACE_BUILD_ERROR |          nan         |
|                 7 |               42 | FAIL_LOW_QUALITY    |            0.0899779 |
|                 8 |               85 | PASS                |            0.108762  |
|                 9 |               90 | FAIL_LOW_QUALITY    |            0.0438732 |
|                10 |               65 | SURFACE_BUILD_ERROR |          nan         |
|                11 |               88 | PASS                |            0.113433  |
|                12 |               41 | PASS                |            0.103776  |
|                13 |               81 | PASS                |            0.124157  |
|                14 |                8 | PASS                |            0.121227  |
|                15 |               56 | FAIL_FOLDED         |           -0.143508  |
|                16 |               29 | SURFACE_BUILD_ERROR |          nan         |
|                17 |               68 | FAIL_LOW_QUALITY    |            0.025984  |
|                18 |                2 | FAIL_LOW_QUALITY    |            0.0477105 |
|                19 |               43 | PASS                |            0.118619  |
|                20 |               89 | SURFACE_BUILD_ERROR |          nan         |
|                21 |               24 | FAIL_FOLDED         |           -0.235447  |

Best quality of all 21 attempts occurred at attempt **1**; the campaign accepted 0.1468 after exhausting the atlas.
