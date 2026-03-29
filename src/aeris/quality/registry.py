from __future__ import annotations

from collections.abc import Iterable

from aeris.quality.base import DatasetValidator


class ValidatorRegistry:
    def __init__(self) -> None:
        self._validators: dict[str, type[DatasetValidator]] = {}

    def register(self, cls: type[DatasetValidator]) -> type[DatasetValidator]:
        validator_id = getattr(cls, "VALIDATOR_ID", "").strip()
        if not validator_id:
            raise ValueError("Validator must define non-empty VALIDATOR_ID.")
        if validator_id in self._validators:
            raise ValueError(f"Duplicate validator id: {validator_id}")
        self._validators[validator_id] = cls
        return cls

    def create(self, validator_id: str) -> DatasetValidator:
        if validator_id not in self._validators:
            raise KeyError(f"Unknown validator id: {validator_id}")
        return self._validators[validator_id]()

    def create_many(self, validator_ids: Iterable[str]) -> list[DatasetValidator]:
        return [self.create(validator_id) for validator_id in validator_ids]

    def list_ids(self) -> list[str]:
        return sorted(self._validators.keys())


GEOMETRY_VALIDATOR_REGISTRY = ValidatorRegistry()
AERO_VALIDATOR_REGISTRY = ValidatorRegistry()