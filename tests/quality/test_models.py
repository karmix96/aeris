from aeris.quality.models import QCCheckResult, QCMessage, QCReport


def test_qc_report_error_and_warning_counts() -> None:
    report = QCReport(
        domain="demo",
        target_path="/tmp/demo",
        passed=False,
        checks=[
            QCCheckResult(
                validator_id="v1",
                passed=False,
                messages=[
                    QCMessage("e1", "error", "boom"),
                    QCMessage("w1", "warning", "hmm"),
                ],
            ),
            QCCheckResult(
                validator_id="v2",
                passed=True,
                messages=[
                    QCMessage("i1", "info", "ok"),
                ],
            ),
        ],
    )

    assert report.error_count() == 1
    assert report.warning_count() == 1