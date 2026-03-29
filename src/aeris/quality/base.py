from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from aeris.quality.models import QCCheckResult


class DatasetValidator(ABC):
    VALIDATOR_ID: str = ""

    @abstractmethod
    def validate(self, dataset_root: Path) -> QCCheckResult:
        raise NotImplementedError