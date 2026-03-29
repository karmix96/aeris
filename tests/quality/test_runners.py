from pathlib import Path

from aeris.quality.base import DatasetValidator
from aeris.quality.models import QCCheckResult
from aeris.quality.runners import run_validators


class PassingValidator(DatasetValidator):
    VALIDATOR_ID = "passing"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        return QCCheckResult(validator_id=self.VALIDATOR_ID, passed=True)


class FailingValidator(DatasetValidator):
    VALIDATOR_ID = "failing"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        return QCCheckResult(validator_id=self.VALIDATOR_ID, passed=False)


def test_run_validators_all_pass(tmp_path: Path) -> None:
    report = run_validators(
        domain="demo",
        dataset_root=tmp_path,
        validators=[PassingValidator(), PassingValidator()],
    )
    assert report.passed is True
    assert len(report.checks) == 2


def test_run_validators_any_fail(tmp_path: Path) -> None:
    report = run_validators(
        domain="demo",
        dataset_root=tmp_path,
        validators=[PassingValidator(), FailingValidator()],
    )
    assert report.passed is False
    assert len(report.checks) == 2