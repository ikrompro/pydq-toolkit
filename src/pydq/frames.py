"""Adapt pandas and polars tables to one check engine.

Polars frames are converted with ``DataFrame.to_pandas()`` at this boundary.
Checks then share a single set of semantics. A native polars engine is a
later milestone; accepting polars inputs now keeps suite code backend-agnostic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, cast

import pandas as pd

from pydq.errors import PydqError

_CANONICAL_FROM_NAME = {
    "int64": "int64",
    "int32": "int32",
    "int16": "int16",
    "int8": "int8",
    "uint64": "uint64",
    "uint32": "uint32",
    "uint16": "uint16",
    "uint8": "uint8",
    "float64": "float64",
    "float32": "float32",
    "bool": "bool",
    "boolean": "bool",
    "string": "string",
    "object": "object",
    "category": "category",
}


def _import_polars() -> Any:
    """Return the polars module, or ``None`` when it is not installed."""
    try:
        import polars as pl
    except ImportError:
        return None
    return pl


def jsonable(value: Any) -> Any:
    """Convert a cell value into something ``json.dumps`` can encode.

    Args:
        value: A scalar cell value from a DataFrame.

    Returns:
        A JSON-compatible value. Missing values become ``None``.
    """
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            converted = item()
        except (ValueError, TypeError):
            converted = None
        else:
            if converted is not value:
                return jsonable(converted)
    return str(value)


@dataclass
class FailureSample:
    """Rows that failed a column check.

    Attributes:
        count: Number of failing rows.
        sample: Up to ``sample_size`` failing rows in encounter order.
    """

    count: int
    sample: list[dict[str, Any]]


@dataclass
class TimestampInspection:
    """Facts a freshness check needs from one column.

    Attributes:
        maximum: Latest parsed timestamp in UTC, if any value parsed.
        null_count: Null cells.
        unparsed_count: Non-null cells that are not ISO-8601 timestamps.
        stale_count: Parsed timestamps strictly older than the cutoff.
        numeric_column: True when the column is numeric and was not parsed.
        sample_unparsed: Sample of non-null values that did not parse.
        sample_stale: Oldest stale rows, up to the requested sample size.
    """

    maximum: datetime | None
    null_count: int
    unparsed_count: int
    stale_count: int
    numeric_column: bool
    sample_unparsed: list[dict[str, Any]]
    sample_stale: list[dict[str, Any]]


class Frame:
    """Read-only view of a table used by checks.

    The original index is dropped. Samples follow physical row order, which is
    the order of the file or the frame the caller passed in.
    """

    def __init__(self, df: pd.DataFrame, *, backend: str) -> None:
        """Wrap a pandas DataFrame.

        Args:
            df: Table to evaluate. It is not modified.
            backend: ``pandas`` or ``polars``, recorded on the suite result.

        Raises:
            PydqError: Column names are missing, duplicated, or not strings.
        """
        columns = list(df.columns)
        if any(not isinstance(column, str) or column == "" for column in columns):
            raise PydqError("Column names must be non-empty strings.")
        if len(columns) != len(set(columns)):
            raise PydqError("DataFrame has duplicate column names, which pydq does not support.")
        self._df = df.reset_index(drop=True)
        self.backend = backend

    def columns(self) -> list[str]:
        """Return column names in table order."""
        return list(self._df.columns)

    def nrows(self) -> int:
        """Return the number of rows."""
        return len(self._df)

    def has_column(self, column: str) -> bool:
        """Return whether ``column`` is present."""
        return column in self._df.columns

    def dtypes(self) -> dict[str, str]:
        """Return canonical dtype names keyed by column."""
        return {column: self._canonical_dtype(column) for column in self.columns()}

    def is_numeric(self, column: str) -> bool:
        """Return whether ``column`` is numeric and not boolean."""
        series = self._df[column]
        if pd.api.types.is_bool_dtype(series):
            return False
        return bool(pd.api.types.is_numeric_dtype(series))

    def is_string_like(self, column: str) -> bool:
        """Return whether non-null values are strings or the dtype is string."""
        kind = self._canonical_dtype(column)
        if kind == "string":
            return True
        if kind not in {"object", "category"}:
            return False
        values = self._df[column].dropna()
        if values.empty:
            return True
        return all(isinstance(item, str) for item in values.head(20).tolist())

    def null_failures(self, column: str, sample_size: int) -> FailureSample:
        """Return null rows for ``column``."""
        mask = self._df[column].isna()
        return self._failure(mask, sample_size)

    def duplicate_failures(self, columns: list[str], sample_size: int) -> FailureSample:
        """Return rows whose key appears more than once.

        Nulls compare equal, so repeated missing keys are duplicates.
        """
        mask = self._df.duplicated(subset=columns, keep=False)
        return self._failure(mask, sample_size)

    def range_failures(
        self,
        column: str,
        minimum: float | None,
        maximum: float | None,
        sample_size: int,
    ) -> FailureSample:
        """Return non-null numeric values outside the inclusive bounds."""
        series = self._df[column]
        mask = pd.Series(False, index=self._df.index)
        if minimum is not None:
            mask = mask | (series < minimum)
        if maximum is not None:
            mask = mask | (series > maximum)
        mask = mask.fillna(False) & series.notna()
        return self._failure(mask, sample_size)

    def disallowed_failures(
        self,
        column: str,
        values: list[Any],
        *,
        allow_nulls: bool,
        sample_size: int,
    ) -> FailureSample:
        """Return values outside ``values``.

        Args:
            column: Column to test.
            values: Allowed scalars.
            allow_nulls: When true, nulls pass. When false, nulls fail.
            sample_size: Maximum sample length.
        """
        series = self._df[column]
        allowed = series.isin(values)
        mask = ~allowed & series.notna() if allow_nulls else ~allowed | series.isna()
        return self._failure(mask, sample_size)

    def regex_failures(self, column: str, pattern: str, sample_size: int) -> FailureSample:
        """Return non-null strings that do not fully match ``pattern``."""
        series = self._df[column].astype("string")
        matched = series.str.fullmatch(pattern, na=False)
        mask = ~matched & self._df[column].notna()
        return self._failure(mask, sample_size)

    def reference_failures(
        self,
        column: str,
        reference: Frame,
        ref_column: str,
        *,
        allow_nulls: bool,
        sample_size: int,
    ) -> FailureSample:
        """Return keys in ``column`` that are absent from the reference column."""
        series = self._df[column]
        lookup = reference._df[ref_column].dropna()
        present = series.isin(lookup)
        mask = ~present & series.notna() if allow_nulls else ~present | series.isna()
        return self._failure(mask, sample_size)

    def inspect_timestamps(
        self,
        column: str,
        cutoff: datetime,
        sample_size: int,
    ) -> TimestampInspection:
        """Parse ISO-8601 or datetime values and compare them with ``cutoff``.

        Numeric columns are not treated as epoch times. String values must
        start with ``YYYY-MM-DD``. Naive timestamps are read as UTC.

        Args:
            column: Timestamp column.
            cutoff: Aware UTC instant. Parsed values older than this are stale.
            sample_size: Maximum number of sample rows for each failure mode.

        Returns:
            Counts and samples for the freshness check.
        """
        series = self._df[column]
        null_count = int(series.isna().sum())
        if self.is_numeric(column):
            return TimestampInspection(
                maximum=None,
                null_count=null_count,
                unparsed_count=0,
                stale_count=0,
                numeric_column=True,
                sample_unparsed=[],
                sample_stale=[],
            )
        parsed = self._parse_timestamps(series)
        unparsed_mask = parsed.isna() & series.notna()
        cutoff_ts = pd.Timestamp(cutoff)
        if cutoff_ts.tzinfo is None:
            cutoff_ts = cutoff_ts.tz_localize("UTC")
        else:
            cutoff_ts = cutoff_ts.tz_convert("UTC")
        stale_mask = parsed.notna() & (parsed < cutoff_ts)
        maximum = self._maximum(parsed)
        stale_index = parsed[stale_mask].sort_values().index
        return TimestampInspection(
            maximum=maximum,
            null_count=null_count,
            unparsed_count=int(unparsed_mask.sum()),
            stale_count=int(stale_mask.sum()),
            numeric_column=False,
            sample_unparsed=self._sample(unparsed_mask, sample_size),
            sample_stale=self._sample_index(stale_index, sample_size),
        )

    def _parse_timestamps(self, series: pd.Series) -> pd.Series:
        if pd.api.types.is_datetime64_any_dtype(series):
            return pd.to_datetime(series, utc=True)
        text = series.astype("string")
        candidates = text.str.contains(r"^\d{4}-\d{2}-\d{2}", na=False)
        gated = text.where(candidates)
        parsed = pd.to_datetime(gated, utc=True, errors="coerce")
        return cast(pd.Series, parsed)

    def _maximum(self, parsed: pd.Series) -> datetime | None:
        if parsed.notna().sum() == 0:
            return None
        stamp = pd.Timestamp(cast(Any, parsed.max()))
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        aware = cast(datetime, stamp.to_pydatetime())
        return aware.astimezone(timezone.utc)

    def _canonical_dtype(self, column: str) -> str:
        series = self._df[column]
        dtype = series.dtype
        name = str(dtype)
        lowered = name.lower()
        if lowered.startswith("datetime64"):
            return "datetime64"
        if lowered.startswith("timedelta64"):
            return "timedelta64"
        if lowered == "str" or lowered.startswith("string"):
            return "string"
        if name in {"Int64", "Int32", "Int16", "Int8", "UInt64", "UInt32", "UInt16", "UInt8"}:
            return name.lower()
        if name in {"Float64", "Float32"}:
            return name.lower()
        mapped = _CANONICAL_FROM_NAME.get(lowered)
        if mapped == "object":
            return _object_kind(series)
        if mapped is not None:
            return mapped
        return "unknown"

    def _failure(self, mask: pd.Series, sample_size: int) -> FailureSample:
        clean = mask.fillna(False).astype(bool)
        return FailureSample(count=int(clean.sum()), sample=self._sample(clean, sample_size))

    def _sample(self, mask: pd.Series, sample_size: int) -> list[dict[str, Any]]:
        if sample_size <= 0:
            return []
        subset = self._df.loc[mask].head(sample_size)
        return _records(subset)

    def _sample_index(self, index: pd.Index, sample_size: int) -> list[dict[str, Any]]:
        if sample_size <= 0 or len(index) == 0:
            return []
        subset = self._df.loc[index[:sample_size]]
        return _records(subset)


def as_frame(data: Any) -> Frame:
    """Wrap a pandas or polars DataFrame.

    Args:
        data: A ``pandas.DataFrame``, a ``polars.DataFrame``, or an existing
            :class:`Frame`.

    Returns:
        A frame view. An existing :class:`Frame` is returned unchanged.

    Raises:
        PydqError: A polars frame was passed but polars is not installed, or
            the table has unsupported column names.
        TypeError: The object is not a supported frame.
    """
    if isinstance(data, Frame):
        return data
    if isinstance(data, pd.DataFrame):
        return Frame(data, backend="pandas")
    module = type(data).__module__
    if module == "polars" or module.startswith("polars."):
        polars = _import_polars()
        if polars is None:
            raise PydqError(
                "Received a polars DataFrame but polars is not installed. "
                "Install it with: pip install 'pydq-toolkit[polars]'"
            )
        if not isinstance(data, polars.DataFrame):
            raise TypeError(
                f"Expected a pandas.DataFrame or polars.DataFrame, got {type(data).__name__}."
            )
        pdf = cast(pd.DataFrame, data.to_pandas())
        return Frame(pdf, backend="polars")
    raise TypeError(f"Expected a pandas.DataFrame or polars.DataFrame, got {type(data).__name__}.")


def _is_missing(value: Any) -> bool:
    """Return whether a scalar cell is a pandas or Python missing value."""
    if value is None:
        return True
    if isinstance(value, (str, bytes, list, tuple, dict, set)):
        return False
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(missing, bool):
        return missing
    if getattr(missing, "ndim", None) == 0:
        return bool(missing)
    return False


def _object_kind(series: pd.Series) -> str:
    values = series.dropna()
    if values.empty:
        return "string"
    kinds: set[str] = set()
    for item in values.head(20):
        kinds.add(_python_kind(item))
        if len(kinds) > 1:
            return "object"
    return kinds.pop()


def _python_kind(item: Any) -> str:
    if isinstance(item, bool):
        return "bool"
    if isinstance(item, int):
        return "int64"
    if isinstance(item, float):
        return "float64"
    if isinstance(item, str):
        return "string"
    if isinstance(item, datetime):
        return "datetime64"
    if isinstance(item, date):
        return "date"
    return "object"


def _records(subset: pd.DataFrame) -> list[dict[str, Any]]:
    raw = subset.to_dict(orient="records")
    return [{str(key): jsonable(value) for key, value in row.items()} for row in raw]
