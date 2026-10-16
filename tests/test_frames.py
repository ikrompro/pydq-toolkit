"""Frame adapter, dtype names, and JSON cell conversion."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from pydq.errors import PydqError
from pydq.frames import as_frame, jsonable


def test_canonical_dtypes_cover_pandas_aliases() -> None:
    frame = as_frame(
        pd.DataFrame(
            {
                "i64": pd.Series([1], dtype="int64"),
                "i32": pd.Series([1], dtype="int32"),
                "f32": pd.Series([1.5], dtype="float32"),
                "nullable": pd.Series([1], dtype="Int64"),
                "flag": pd.Series([True], dtype="bool"),
                "flag2": pd.Series([True], dtype="boolean"),
                "text": pd.Series(["a"], dtype="string"),
                "when": pd.to_datetime(["2026-10-16T00:00:00Z"]),
                "span": pd.to_timedelta(["1 day"]),
                "group": pd.Series(["a"], dtype="category"),
                "empty_object": pd.Series([None], dtype="object"),
                "dates": pd.Series([date(2026, 10, 16)], dtype="object"),
                "clocks": pd.Series([datetime(2026, 10, 16, tzinfo=timezone.utc)], dtype="object"),
                "whole": pd.Series([3], dtype="object"),
                "ratio": pd.Series([1.5], dtype="object"),
                "bits": pd.Series([True], dtype="object"),
                "other": pd.Series([Decimal("1.5")], dtype="object"),
                "period": pd.period_range("2026-01", periods=1, freq="M"),
            }
        )
    )
    dtypes = frame.dtypes()
    assert dtypes["i64"] == "int64"
    assert dtypes["i32"] == "int32"
    assert dtypes["f32"] == "float32"
    assert dtypes["nullable"] == "int64"
    assert dtypes["flag"] == "bool"
    assert dtypes["flag2"] == "bool"
    assert dtypes["text"] == "string"
    assert dtypes["when"] == "datetime64"
    assert dtypes["span"] == "timedelta64"
    assert dtypes["group"] == "category"
    assert dtypes["empty_object"] == "string"
    assert dtypes["dates"] == "date"
    assert dtypes["clocks"] == "datetime64"
    mixed = as_frame(pd.DataFrame({"mixed": pd.Series(["a", 1], dtype="object")}))
    assert mixed.dtypes()["mixed"] == "object"
    assert dtypes["whole"] == "int64"
    assert dtypes["ratio"] == "float64"
    assert dtypes["bits"] == "bool"
    assert dtypes["other"] == "object"
    assert dtypes["period"] == "unknown"
    assert frame.is_string_like("text") is True
    assert frame.is_string_like("group") is True
    empty_category = as_frame(pd.DataFrame({"group": pd.Series([None], dtype="category")}))
    assert empty_category.is_string_like("group") is True
    assert frame.is_string_like("i64") is False
    assert frame.is_numeric("flag") is False
    assert frame.is_numeric("i64") is True


def test_as_frame_rejects_bad_tables_and_reuses_wrappers() -> None:
    wrapped = as_frame(pd.DataFrame({"a": [1]}))
    assert as_frame(wrapped) is wrapped
    with pytest.raises(TypeError, match="Expected"):
        as_frame([1, 2, 3])
    with pytest.raises(PydqError, match="duplicate"):
        as_frame(pd.DataFrame([[1, 2]], columns=["a", "a"]))
    with pytest.raises(PydqError, match="non-empty"):
        as_frame(pd.DataFrame([[1]], columns=[""]))
    with pytest.raises(PydqError, match="non-empty"):
        as_frame(pd.DataFrame([[1]], columns=[1]))


def test_polars_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class Dummy:
        """Stand-in object that only looks like a polars frame."""

    Dummy.__module__ = "polars.dataframe.frame"
    monkeypatch.setattr("pydq.frames._import_polars", lambda: None)
    with pytest.raises(PydqError, match="not installed"):
        as_frame(Dummy())

    class FakePolars:
        class DataFrame:
            """Unrelated DataFrame type."""

    monkeypatch.setattr("pydq.frames._import_polars", lambda: FakePolars)
    with pytest.raises(TypeError, match="Expected"):
        as_frame(Dummy())


def test_timestamp_helpers_cover_naive_and_empty_samples() -> None:
    frame = as_frame(pd.DataFrame({"event": ["2026-10-16T00:00:00Z"]}))
    naive = pd.Series(pd.to_datetime(["2026-01-01"]))
    aware = pd.Series(pd.to_datetime(["2026-01-01T00:00:00Z"]))
    assert frame._maximum(naive) == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert frame._maximum(aware) == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert frame._maximum(pd.Series([pd.NaT])) is None
    cutoff = datetime(2026, 10, 16, 12)
    inspected = frame.inspect_timestamps("event", cutoff, sample_size=0)
    assert inspected.maximum is not None
    assert inspected.sample_stale == []
    assert inspected.sample_unparsed == []


def test_jsonable_scalars() -> None:
    assert jsonable(None) is None
    assert jsonable(True) is True
    assert jsonable(False) is False
    assert jsonable(3) == 3
    assert jsonable(1.5) == 1.5
    assert jsonable(float("nan")) is None
    assert jsonable(float("inf")) == "Infinity"
    assert jsonable(float("-inf")) == "-Infinity"
    assert jsonable("ok") == "ok"
    assert jsonable(datetime(2026, 10, 16, tzinfo=timezone.utc)).startswith("2026-10-16")
    assert jsonable(date(2026, 10, 16)) == "2026-10-16"
    assert jsonable(Decimal("2.50")) == "2.50"
    assert jsonable(pd.NaT) is None
    assert jsonable(pd.NA) is None

    class Same:
        def item(self) -> Same:
            return self

    class Broken:
        def item(self) -> object:
            raise ValueError("no")

    assert isinstance(jsonable(Same()), str)
    assert isinstance(jsonable(Broken()), str)
    assert jsonable(pd.Timestamp("2026-01-01T00:00:00Z")).startswith("2026-01-01")
    number = pd.Series([7], dtype="int64").iloc[0]
    assert jsonable(number) == 7
