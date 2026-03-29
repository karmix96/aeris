import pytest

from aeris.quality.base import DatasetValidator
from aeris.quality.models import QCCheckResult
from aeris.quality.registry import ValidatorRegistry


def test_registry_rejects_missing_validator_id() -> None:
    registry = ValidatorRegistry()

    class BadValidator(DatasetValidator):
        VALIDATOR_ID = ""

        def validate(self, dataset_root):
            return QCCheckResult(validator_id="bad", passed=True)

    with pytest.raises(ValueError):
        registry.register(BadValidator)


def test_registry_rejects_duplicate_validator_id() -> None:
    registry = ValidatorRegistry()

    class V1(DatasetValidator):
        VALIDATOR_ID = "dup"

        def validate(self, dataset_root):
            return QCCheckResult(validator_id="dup", passed=True)

    class V2(DatasetValidator):
        VALIDATOR_ID = "dup"

        def validate(self, dataset_root):
            return QCCheckResult(validator_id="dup", passed=True)

    registry.register(V1)

    with pytest.raises(ValueError):
        registry.register(V2)


def test_registry_create_many() -> None:
    registry = ValidatorRegistry()

    class V1(DatasetValidator):
        VALIDATOR_ID = "v1"

        def validate(self, dataset_root):
            return QCCheckResult(validator_id="v1", passed=True)

    class V2(DatasetValidator):
        VALIDATOR_ID = "v2"

        def validate(self, dataset_root):
            return QCCheckResult(validator_id="v2", passed=True)

    registry.register(V1)
    registry.register(V2)

    validators = registry.create_many(["v1", "v2"])
    assert len(validators) == 2
    assert {v.VALIDATOR_ID for v in validators} == {"v1", "v2"}