"""Markdown and JSON reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pydq.results import CheckResult, SuiteResult


def _result(passed: bool, sample: list[dict[str, object]] | None = None) -> SuiteResult:
    check = CheckResult(
        name="status|has\nlines",
        check_type="allowed_values",
        passed=passed,
        failing_rows=0 if passed else 1,
        total_rows=2,
        message="value | broke\nthe cell",
        sample_failing_rows=list(sample or []),
        parameters={"values": ["ok"]},
    )
    moment = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    return SuiteResult(
        suite="orders",
        passed=passed,
        checks=[check],
        started_at=moment,
        finished_at=moment,
        backend="pandas",
    )


def test_markdown_pass_and_fail_escape_tables() -> None:
    passed = _result(True).to_markdown()
    assert "All checks passed." in passed
    assert "**Result:** PASS" in passed
    failed = _result(
        False,
        [
            {"status": "bad|value", "flag": False, "note": None},
            {"status": "x", "extra": True},
        ],
    ).to_markdown()
    assert "bad\\|value" in failed
    assert "false" in failed
    assert "true" in failed
    assert "| null |" in failed or "| null" in failed
    assert "Sample failing rows:" in failed
    assert "extra" in failed
    assert "\n" in failed.split("###", 1)[1]
    bare = _result(False).to_markdown()
    assert "No failing-row sample." in bare


def test_json_report_is_strict() -> None:
    payload = json.loads(_result(False, [{"n": 1}]).to_json())
    assert payload["passed"] is False
    assert payload["checks"][0]["sample_failing_rows"] == [{"n": 1}]
    assert payload["duration_ms"] == 0
