"""Suites group checks and run them against a table."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from pydq.checks import Check, EvalContext
from pydq.duration import parse_as_of
from pydq.errors import PydqError
from pydq.frames import Frame, as_frame
from pydq.results import SuiteResult


class Suite:
    """A named list of checks plus run defaults.

    Args:
        name: Suite name recorded on the result.
        checks: Checks evaluated in order.
        sample_size: Default number of failing rows kept for each check.
        as_of: Optional fixed clock for freshness checks. Naive datetimes are
            treated as UTC. When omitted, :meth:`run` uses the current time
            unless the caller passes ``as_of``.
    """

    def __init__(
        self,
        name: str,
        checks: Sequence[Check],
        *,
        sample_size: int = 5,
        as_of: datetime | str | None = None,
    ) -> None:
        """Store a validated suite."""
        if not isinstance(name, str) or name.strip() == "":
            raise PydqError("suite name must be a non-empty string.")
        if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size < 0:
            raise PydqError("sample_size must be an integer >= 0.")
        if not checks:
            raise PydqError("suite must contain at least one check.")
        stored: list[Check] = []
        for check in checks:
            if not callable(getattr(check, "evaluate", None)):
                raise PydqError("checks must be pydq check objects.")
            stored.append(check)
        labels = [check.display_name for check in stored]
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            rendered = ", ".join(duplicates)
            raise PydqError(f"Duplicate check names: {rendered}.")
        self.name = name
        self.checks = tuple(stored)
        self.sample_size = sample_size
        self.as_of = None if as_of is None else parse_as_of(as_of)

    def run(
        self,
        data: Any,
        refs: Mapping[str, Any] | None = None,
        *,
        sample_size: int | None = None,
        as_of: datetime | str | None = None,
    ) -> SuiteResult:
        """Evaluate every check and return a structured result.

        Args:
            data: pandas or polars DataFrame to test.
            refs: Reference frames keyed by the name used in
                ``referential_integrity``.
            sample_size: Overrides the suite default when not ``None``.
            as_of: Overrides the suite clock when not ``None``.

        Returns:
            Pass/fail details for each check. A failing check does not raise.

        Raises:
            PydqError: The frame, references, or overrides cannot be used.
        """
        frame = as_frame(data)
        ref_frames = _reference_frames(refs)
        size = self.sample_size if sample_size is None else _sample_size(sample_size)
        if as_of is not None:
            moment = parse_as_of(as_of)
        elif self.as_of is not None:
            moment = self.as_of
        else:
            moment = datetime.now(timezone.utc)
        ctx = EvalContext(frame=frame, refs=ref_frames, sample_size=size, as_of=moment)
        started = datetime.now(timezone.utc)
        results = [check.evaluate(ctx) for check in self.checks]
        finished = datetime.now(timezone.utc)
        return SuiteResult(
            suite=self.name,
            passed=all(item.passed for item in results),
            checks=results,
            started_at=started,
            finished_at=finished,
            backend=frame.backend,
        )


def _reference_frames(refs: Mapping[str, Any] | None) -> dict[str, Frame]:
    frames: dict[str, Frame] = {}
    if refs is None:
        return frames
    for key, value in refs.items():
        if not isinstance(key, str) or key == "":
            raise PydqError("Reference names must be non-empty strings.")
        frames[key] = as_frame(value)
    return frames


def _sample_size(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PydqError("sample_size must be an integer >= 0.")
    return value
