from aeris.ml.model_registry import build_model, get_model_spec, list_model_types


def test_registry_lists_expected_models():
    expected_core = {
        "elastic_net",
        "extra_trees",
        "gradient_boosting",
        "hist_gradient_boosting",
        "linear_regression",
        "neural_mlp",
        "neural_mlp_ensemble",
        "random_forest",
        "ridge",
    }
    expected_optional = {
        "lightgbm",
        "lightgbm_dart",
        "xgboost",
        "catboost",
        "tabpfn",
    }

    model_types = set(list_model_types())

    assert expected_core.issubset(model_types)
    assert expected_optional.issubset(model_types)


def test_build_linear_regression():
    model = build_model("linear_regression", random_seed=123)
    # Linear models are now Pipeline(StandardScaler + estimator) for proper scaling.
    assert model.__class__.__name__ == "Pipeline"
    assert model.named_steps["model"].__class__.__name__ == "LinearRegression"


def test_build_ridge():
    model = build_model("ridge", random_seed=123)
    assert model.__class__.__name__ == "Pipeline"
    assert model.named_steps["model"].__class__.__name__ == "Ridge"


def test_build_elastic_net():
    model = build_model("elastic_net", random_seed=123)
    assert model.__class__.__name__ == "Pipeline"
    # ElasticNet is single-target; inner model is MultiOutputRegressor(ElasticNet)
    assert model.named_steps["model"].__class__.__name__ == "MultiOutputRegressor"


def test_build_random_forest():
    model = build_model("random_forest", random_seed=123)
    assert model.__class__.__name__ == "RandomForestRegressor"


def test_build_extra_trees():
    model = build_model("extra_trees", random_seed=123)
    assert model.__class__.__name__ == "ExtraTreesRegressor"


def test_build_gradient_boosting():
    model = build_model("gradient_boosting", random_seed=123)
    assert model.__class__.__name__ == "MultiOutputRegressor"


def test_build_hist_gradient_boosting():
    model = build_model("hist_gradient_boosting", random_seed=123)
    assert model.__class__.__name__ == "MultiOutputRegressor"


def test_registry_metadata_for_gradient_boosting():
    spec = get_model_spec("gradient_boosting")
    assert spec.family_name == "tree_boosting"
    assert spec.explainability_artifact_type == "feature_importances"
    assert spec.wrapped_per_target is True


def test_registry_metadata_for_linear_regression():
    spec = get_model_spec("linear_regression")
    assert spec.family_name == "linear_model"
    assert spec.explainability_artifact_type == "coefficients"
    assert spec.wrapped_per_target is False


def test_registry_metadata_for_hist_gradient_boosting():
    spec = get_model_spec("hist_gradient_boosting")
    assert spec.family_name == "tree_boosting"
    assert spec.explainability_artifact_type == "none"
    assert spec.wrapped_per_target is True