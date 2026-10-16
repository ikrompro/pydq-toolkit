"""Behavior of the built-in checks and suite runner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from pydq import (
    Suite,
    allowed_values,
    freshness,
    in_range,
    not_null,
    referential_integrity,
    regex_match,
    row_count_between,
    schema,
    unique,
)
from pydq.checks import AllowedValues, Schema, Unique
from pydq.errors import PydqError

AS_OF = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


def _run(frame: pd.DataFrame, check: object, **kwargs: object) -> object:
    suite = Suite("demo", [check], as_of=AS_OF)  # type: ignore[list-item]
    return suite.run(frame, **kwargs)  # type: ignore[arg-type]


def _only(frame: pd.DataFrame, check: object, **kwargs: object) -> object:
    result = _run(frame, check, **kwargs)
    assert len(result.checks) == 1  # type: ignore[attr-defined]
    return result.checks[0]  # type: ignore[attr-defined]


def test_not_null_unique_and_duplicates_keep_every_copy() -> None:
    frame = pd.DataFrame({"id": [1, 1, None, None], "note": ["a", "b", "c", "d"]})
    nulls = _only(frame, not_null("id"))
    dupes = _only(frame, unique("id"))
    assert nulls.passed is False
    assert nulls.failing_rows == 2
    assert dupes.passed is False
    assert dupes.failing_rows == 4
    assert [row["note"] for row in dupes.sample_failing_rows] == ["a", "b", "c", "d"]
    assert _only(frame, unique(["note"])).passed is True


def test_unique_composite_key_and_missing_columns() -> None:
    frame = pd.DataFrame({"a": [1, 1], "b": [1, 2]})
    assert _only(frame, unique(columns=["a", "b"])).passed is True
    assert _only(frame, unique(columns=["a"])).passed is False
    missing = _only(frame, unique(columns=["a", "missing"]))
    assert missing.passed is False
    assert "missing" in missing.message
    both = _only(frame, unique(columns=["nope", "also"]))
    assert both.message.startswith("Columns")


def test_in_range_is_inclusive_and_ignores_nulls() -> None:
    frame = pd.DataFrame({"n": [0, 10, None, 11]})
    failed = _only(frame, in_range("n", minimum=0, maximum=10))
    assert failed.passed is False
    assert failed.failing_rows == 1
    assert failed.sample_failing_rows[0]["n"] == 11
    below = pd.DataFrame({"n": [0, 10, None, -1]})
    assert _only(below, in_range("n", minimum=0)).failing_rows == 1
    assert _only(frame, in_range("n", maximum=11)).passed is True
    labeled = pd.DataFrame({"label": ["a"], "flag": [True]})
    assert "not numeric" in _only(labeled, in_range("label", minimum=0)).message
    assert "not numeric" in _only(labeled, in_range("flag", minimum=0)).message


def test_allowed_values_and_regex() -> None:
    frame = pd.DataFrame({"status": ["ok", "no", None], "email": ["a@b.co", "nope", None]})
    allowed = _only(frame, allowed_values("status", ["ok"]))
    assert allowed.failing_rows == 1
    strict = _only(frame, allowed_values("status", ["ok"], allow_nulls=False))
    assert strict.failing_rows == 2
    assert _only(frame, allowed_values("status", [])).failing_rows == 2
    assert _only(frame, allowed_values("code", [1])).passed is False
    numbers = pd.DataFrame({"code": [1, "1"]})
    assert _only(numbers, allowed_values("code", [1])).failing_rows == 1
    matched = _only(frame, regex_match("email", r"^[^@\s]+@[^@\s]+\.[^@\s]+$"))
    assert matched.failing_rows == 1
    assert _only(frame, regex_match("email", "a@b.co")).passed is False
    assert _only(frame, regex_match("email", r".*@.*")).failing_rows == 1
    assert "not a string" in _only(pd.DataFrame({"n": [1]}), regex_match("n", "1")).message


def test_row_count_window() -> None:
    frame = pd.DataFrame({"a": [1, 2]})
    assert _only(frame, row_count_between(minimum=1, maximum=2)).passed is True
    low = _only(frame, row_count_between(minimum=5))
    assert low.passed is False
    assert low.failing_rows == 3
    assert low.sample_failing_rows == []
    high = _only(frame, row_count_between(maximum=1))
    assert high.failing_rows == 1
    assert _only(pd.DataFrame({"a": []}), row_count_between(maximum=0)).passed is True


def test_freshness_modes() -> None:
    fresh = pd.DataFrame(
        {
            "ordered_at": [
                "2026-10-16T11:00:00Z",
                "2026-10-14T12:00:00Z",
                "2026-10-16T08:00:00-04:00",
            ]
        }
    )
    passed = _only(fresh, freshness("ordered_at", "48h"))
    assert passed.passed is True
    assert passed.failing_rows == 0
    boundary = pd.DataFrame({"ordered_at": ["2026-10-16T11:00:00Z"]})
    assert _only(boundary, freshness("ordered_at", "1h")).passed is True
    stale = pd.DataFrame({"ordered_at": ["2020-01-02T00:00:00Z", "2020-01-01T00:00:00Z"]})
    failed = _only(stale, freshness("ordered_at", "1h"))
    assert failed.passed is False
    assert failed.failing_rows == 2
    assert failed.sample_failing_rows[0]["ordered_at"] == "2020-01-01T00:00:00Z"
    unparsed = pd.DataFrame({"ordered_at": ["2026-10-16T11:00:00Z", "yesterday"]})
    bad = _only(unparsed, freshness("ordered_at", "24h"))
    assert "ISO-8601" in bad.message
    assert bad.failing_rows == 1
    empty = _only(
        pd.DataFrame({"ordered_at": [None, None]}),
        freshness("ordered_at", timedelta(hours=1)),
    )
    assert "no timestamps" in empty.message
    numeric = _only(pd.DataFrame({"ordered_at": [1, 2]}), freshness("ordered_at", 3600))
    assert "numeric" in numeric.message
    typed = pd.DataFrame({"ordered_at": pd.to_datetime(["2026-10-16 11:30:00"])})
    assert _only(typed, freshness("ordered_at", "2h")).passed is True
    assert "does not exist" in _only(fresh, freshness("missing", "1h")).message


def test_schema_and_referential_integrity() -> None:
    frame = pd.DataFrame({"id": [1, 2], "amount": [1.5, 2.5], "extra": ["a", "b"]})
    assert _only(frame, schema({"id": "integer", "amount": "float"})).passed is True
    mismatch = _only(frame, schema({"id": "string", "missing": "int64"}))
    assert mismatch.passed is False
    assert "missing" in mismatch.message
    assert "mismatched" in mismatch.message
    exact = _only(frame, schema({"id": "int64", "amount": "float64"}, exact=True))
    assert "unexpected" in exact.message
    assert exact.failing_rows == 1
    ref = pd.DataFrame({"id": [1, None]})
    parent = pd.DataFrame({"id": [1, 2]})
    ok = _only(
        ref,
        referential_integrity("id", ref="parent", ref_column="id"),
        refs={"parent": parent},
    )
    assert ok.passed is True
    strict = _only(
        ref,
        referential_integrity("id", ref="parent", ref_column="id", allow_nulls=False),
        refs={"parent": parent},
    )
    assert strict.failing_rows == 1
    orphan = _only(
        pd.DataFrame({"id": ["1"]}),
        referential_integrity("id", ref="parent", ref_column="id"),
        refs={"parent": parent},
    )
    assert orphan.passed is False
    absent = _only(
        ref,
        referential_integrity("id", ref="parent", ref_column="missing"),
        refs={"parent": parent},
    )
    assert "no column" in absent.message
    with pytest.raises(PydqError, match="was not provided"):
        _run(ref, referential_integrity("id", ref="parent", ref_column="id"))


def test_suite_defaults_overrides_and_validation() -> None:
    frame = pd.DataFrame({"id": [1, None]})
    suite = Suite("orders", [not_null("id", name="id required")], sample_size=0)
    hidden = suite.run(frame)
    assert hidden.checks[0].sample_failing_rows == []
    assert hidden.checks[0].failing_rows == 1
    shown = suite.run(frame, sample_size=1)
    assert len(shown.checks[0].sample_failing_rows) == 1
    assert hidden.backend == "pandas"
    assert hidden.passed is False
    payload = hidden.to_dict()
    assert payload["summary"] == {"total": 1, "passed": 0, "failed": 1}
    clocked = Suite("fresh", [freshness("ts", "1h")], as_of="2020-01-01T00:30:00Z")
    data = pd.DataFrame({"ts": ["2020-01-01T00:00:00Z"]})
    assert clocked.run(data).passed is True
    assert clocked.run(data, as_of="2024-01-01T00:00:00Z").passed is False
    original = frame.copy()
    suite.run(frame)
    pd.testing.assert_frame_equal(frame, original)
    with pytest.raises(PydqError, match="Duplicate"):
        Suite("dup", [not_null("id"), not_null("id")])
    with pytest.raises(PydqError, match="at least one"):
        Suite("empty", [])
    with pytest.raises(PydqError, match="check objects"):
        Suite("bad", [object()])  # type: ignore[list-item]
    with pytest.raises(PydqError, match="sample_size"):
        suite.run(frame, sample_size=-1)
    with pytest.raises(PydqError, match="Reference names"):
        suite.run(frame, {"": frame})
    with pytest.raises(PydqError, match="suite name"):
        Suite("  ", [not_null("id")])
    with pytest.raises(PydqError, match="sample_size"):
        Suite("bad-size", [not_null("id")], sample_size=True)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "builder",
    [
        lambda: not_null(""),
        lambda: not_null("a", name=" "),
        lambda: unique(),
        lambda: unique("a", columns=["b"]),
        lambda: unique(columns=["a", "a"]),
        lambda: in_range("a"),
        lambda: in_range("a", minimum=2, maximum=1),
        lambda: in_range("a", minimum=True),  # type: ignore[arg-type]
        lambda: allowed_values("a", [object()]),
        lambda: allowed_values("a", [1], allow_nulls="yes"),  # type: ignore[arg-type]
        lambda: regex_match("a", "("),
        lambda: regex_match("a", ""),
        lambda: row_count_between(),
        lambda: row_count_between(minimum=3, maximum=1),
        lambda: row_count_between(minimum=-1),
        lambda: freshness("", "1h"),
        lambda: freshness("a", "-1s"),
        lambda: schema({}),
        lambda: schema({"a": "varchar"}),
        lambda: Schema(columns=(("a", "int64"), ("a", "int64"))),
        lambda: referential_integrity("a", ref="bad=name", ref_column="id"),
        lambda: referential_integrity("a", ref="", ref_column="id"),
        lambda: AllowedValues(column="a", values=(1,), allow_nulls="no"),  # type: ignore[arg-type]
        lambda: Unique(columns=()),
    ],
)
def test_check_constructors_reject_bad_config(builder: object) -> None:
    with pytest.raises(PydqError):
        builder()  # type: ignore[operator]


def test_schema_object_alias_matches_strings() -> None:
    frame = pd.DataFrame({"label": ["a", "b"]})
    assert _only(frame, schema({"label": "object"})).passed is True
    assert _only(frame, schema({"label": "timestamp"})).passed is False
