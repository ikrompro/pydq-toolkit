"""Structured results returned by a suite run."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CheckResult:
    """Outcome of one check.

    Attributes:
        name: Label shown in reports.
        check_type: Stable check identifier, such as ``not_null``.
        passed: Whether the check succeeded.
        failing_rows: Rows that violated the check, or a table-level distance
            for checks that do not mark individual rows.
        total_rows: Rows in the frame that was evaluated.
        message: One-line explanation.
        sample_failing_rows: JSON-ready sample of failing rows.
        parameters: Check configuration included in the report.
    """

    name: str
    check_type: str
    passed: bool
    failing_rows: int
    total_rows: int
    message: str
    sample_failing_rows: list[dict[str, Any]] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dictionary."""
        return {
            "name": self.name,
            "type": self.check_type,
            "passed": self.passed,
            "failing_rows": self.failing_rows,
            "total_rows": self.total_rows,
            "message": self.message,
            "sample_failing_rows": self.sample_failing_rows,
            "parameters": self.parameters,
        }


@dataclass
class SuiteResult:
    """Outcome of every check in a suite.

    Attributes:
        suite: Suite name.
        passed: True when every check passed.
        checks: Per-check results in declaration order.
        started_at: UTC start time.
        finished_at: UTC finish time.
        backend: Frame backend that supplied the table, ``pandas`` or ``polars``.
    """

    suite: str
    passed: bool
    checks: list[CheckResult]
    started_at: datetime
    finished_at: datetime
    backend: str

    @property
    def passed_count(self) -> int:
        """Number of checks that passed."""
        return sum(1 for item in self.checks if item.passed)

    @property
    def failed_count(self) -> int:
        """Number of checks that failed."""
        return sum(1 for item in self.checks if not item.passed)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dictionary."""
        duration_ms = (self.finished_at - self.started_at).total_seconds() * 1000.0
        return {
            "suite": self.suite,
            "passed": self.passed,
            "backend": self.backend,
            "summary": {
                "total": len(self.checks),
                "passed": self.passed_count,
                "failed": self.failed_count,
            },
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_ms": round(duration_ms, 3),
            "checks": [item.to_dict() for item in self.checks],
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the result as JSON text.

        Args:
            indent: Indentation passed to ``json.dumps``.

        Returns:
            JSON text ending with a newline.
        """
        return json.dumps(self.to_dict(), indent=indent) + "\n"

    def to_markdown(self) -> str:
        """Render a Markdown report.

        Returns:
            A Markdown document ending with a newline.
        """
        from pydq.report import render_markdown

        return render_markdown(self)
