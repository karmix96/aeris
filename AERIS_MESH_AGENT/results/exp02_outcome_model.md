# Experiment 2 — predicting an attempt's outcome

247 observed (geometry, template) cells, grouped out-of-fold by target geometry (5 folds).

| feature_set    |   n_features |   n_cells |   balanced_accuracy |   macro_f1 |   pass_auc |   quality_mae |   quality_spearman |
|:---------------|-------------:|----------:|--------------------:|-----------:|-----------:|--------------:|-------------------:|
| design only    |           63 |       247 |              0.6313 |     0.6402 |     0.8914 |        0.0747 |             0.7559 |
| design+surface |           86 |       247 |              0.6008 |     0.5984 |     0.894  |        0.0622 |             0.8433 |

Reference points: always predicting the majority class gives accuracy 0.563 (balanced accuracy 0.25 for four classes); the PASS base rate is 0.563, so an uninformed ranker has AUC 0.5 and Spearman 0.

**Reading it.** For the agent, the ranking correlation matters more than the point error: the policy never needs the quality value, only the order of the candidates.
