"""Duration and clock parsing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pydq.duration import format_duration, parse_as_of, parse_duration
from pydq.errors import PydqError


def test_parse_duration_accepts_timedelta_seconds_and_units() -> None:
    assert parse_duration(timedelta(hours=2)) == timedelta(hours=2)
    assert parse_duration(90) == timedelta(seconds=90)
    assert parse_duration(1.5) == timedelta(seconds=1.5)
    assert parse_duration("  24h ") == timedelta(hours=24)
    assert parse_duration("30m") == timedelta(minutes=30)
    assert parse_duration("2d") == timedelta(days=2)
    assert parse_duration("1w") == timedelta(weeks=1)
    assert parse_duration("45s") == timedelta(seconds=45)
    assert parse_duration("500ms") == timedelta(milliseconds=500)
    assert parse_duration("1.5h") == timedelta(hours=1.5)
    assert parse_duration("0s") == timedelta(0)


@pytest.mark.parametrize(
    "value",
    ["", "24", "hour", "1 hour", "-1s", "1x", True, None, object(), -1, -0.5],
)
def test_parse_duration_rejects_bad_values(value: object) -> None:
    with pytest.raises(PydqError):
        parse_duration(value)  # type: ignore[arg-type]


def test_parse_duration_rejects_negative_timedelta() -> None:
    with pytest.raises(PydqError, match="non-negative"):
        parse_duration(timedelta(seconds=-1))


def test_format_duration_uses_the_largest_exact_unit() -> None:
    assert format_duration(timedelta(0)) == "0s"
    assert format_duration(timedelta(weeks=2)) == "2w"
    assert format_duration(timedelta(days=3)) == "3d"
    assert format_duration(timedelta(hours=48)) == "2d"
    assert format_duration(timedelta(hours=47)) == "47h"
    assert format_duration(timedelta(minutes=90)) == "90m"
    assert format_duration(timedelta(seconds=15)) == "15s"
    assert format_duration(timedelta(seconds=1.5)) == "1.5s"
    assert format_duration(timedelta(milliseconds=250)) == "250ms"


def test_parse_as_of_normalizes_to_utc() -> None:
    aware = parse_as_of("2026-10-16T08:00:00-04:00")
    assert aware == datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    zulu = parse_as_of("2026-10-16T12:00:00z")
    assert zulu == datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    naive = parse_as_of(datetime(2026, 10, 16, 12))
    assert naive.tzinfo == timezone.utc
    passed = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    assert parse_as_of(passed) == passed


@pytest.mark.parametrize("value", ["yesterday", "", 5, None])
def test_parse_as_of_rejects_bad_values(value: object) -> None:
    with pytest.raises(PydqError):
        parse_as_of(value)  # type: ignore[arg-type]
