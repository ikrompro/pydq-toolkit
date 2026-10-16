"""Render a suite result as Markdown."""

from __future__ import annotations

from typing import Any

from pydq.results import SuiteResult


def render_markdown(result: SuiteResult) -> str:
    """Render a human-readable report.

    Args:
        result: Suite result to render.

    Returns:
        Markdown ending with a newline. Failing checks include a sample table
        when the check recorded failing rows.
    """
    status = "PASS" if result.passed else "FAIL"
    lines = [
        f"# Data quality report: {result.suite}",
        "",
        f"**Result:** {status}",
        (
            f"**Checks:** {result.passed_count} passed, {result.failed_count} failed, "
            f"{len(result.checks)} total"
        ),
        f"**Backend:** {result.backend}",
        f"**Started:** {result.started_at.isoformat()}",
        f"**Finished:** {result.finished_at.isoformat()}",
        "",
        "| Check | Type | Status | Failing rows | Total rows | Message |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for check in result.checks:
        flag = "PASS" if check.passed else "FAIL"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(check.name),
                    _cell(check.check_type),
                    flag,
                    str(check.failing_rows),
                    str(check.total_rows),
                    _cell(check.message),
                ]
            )
            + " |"
        )
    failures = [check for check in result.checks if not check.passed]
    if not failures:
        lines.extend(["", "All checks passed.", ""])
        return "\n".join(lines)
    lines.extend(["", "## Failures", ""])
    for check in failures:
        lines.append(f"### {_heading(check.name)}")
        lines.append("")
        lines.append(check.message)
        lines.append("")
        if check.sample_failing_rows:
            lines.append("Sample failing rows:")
            lines.append("")
            lines.extend(_table(check.sample_failing_rows))
            lines.append("")
        else:
            lines.append("No failing-row sample.")
            lines.append("")
    return "\n".join(lines)


def _table(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    header = "| " + " | ".join(_cell(column) for column in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(_cell(row.get(column)) for column in columns) + " |" for row in rows]
    return [header, divider, *body]


def _cell(value: Any) -> str:
    if value is None:
        text = "null"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _heading(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")
