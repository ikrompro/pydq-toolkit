"""Built-in data-quality checks.

Nulls are ignored by ``in_range`` and ``regex_match`` so those checks compose
with :func:`not_null`. ``allowed_values`` and referential integrity ignore
nulls unless ``allow_nulls`` is false. Numeric and timestamp bounds are
inclusive. ``regex_match`` uses full-string matching.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from pydq.duration import format_duration, parse_duration
from pydq.errors import PydqError
from pydq.frames import Frame
from pydq.results import CheckResult

DTYPE_ALIASES = {
    "int": "int64",
    "integer": "int64",
    "long": "int64",
    "int64": "int64",
    "int32": "int32",
    "int16": "int16",
    "int8": "int8",
    "uint64": "uint64",
    "uint32": "uint32",
    "uint16": "uint16",
    "uint8": "uint8",
    "float": "float64",
    "double": "float64",
    "float64": "float64",
    "float32": "float32",
    "str": "string",
    "string": "string",
    "text": "string",
    "object": "string",
    "bool": "bool",
    "boolean": "bool",
    "datetime": "datetime64",
    "datetime64": "datetime64",
    "timestamp": "datetime64",
    "date": "date",
    "category": "category",
    "categorical": "category",
    "timedelta": "timedelta64",
    "timedelta64": "timedelta64",
}


@dataclass(frozen=True)
class EvalContext:
    """Inputs shared by every check in one suite run.

    Attributes:
        frame: Table under test.
        refs: Named reference tables.
        sample_size: Maximum failing rows kept on each result.
        as_of: UTC instant used by freshness checks.
    """

    frame: Frame
    refs: Mapping[str, Frame]
    sample_size: int
    as_of: datetime


class Check(Protocol):
    """A data-quality check that can be evaluated against a frame."""

    @property
    def check_type(self) -> str:
        """Stable identifier such as ``not_null``."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name used in reports."""
        ...

    def parameters(self) -> dict[str, Any]:
        """Configuration values included in the result payload."""
        ...

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Run the check and return a structured result."""
        ...


@dataclass(frozen=True)
class NotNull:
    """Fail when a column contains null values."""

    column: str
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate the column and optional name."""
        _column(self.column)
        _optional_name(self.name)

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "not_null"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, self.column)

    def parameters(self) -> dict[str, Any]:
        """Return the column name."""
        return {"column": self.column}

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Count nulls in the configured column."""
        missing = _missing(self, ctx, self.column)
        if missing is not None:
            return missing
        found = ctx.frame.null_failures(self.column, ctx.sample_size)
        total = ctx.frame.nrows()
        if found.count == 0:
            message = f"All {total} values in {self.column!r} are non-null."
        else:
            message = (
                f"{found.count} of {total} values in {self.column!r} "
                f"{_agree(found.count, 'is', 'are')} null."
            )
        return _done(self, ctx, found.count == 0, found.count, message, found.sample)


@dataclass(frozen=True)
class Unique:
    """Fail when a column or column group contains duplicate keys."""

    columns: tuple[str, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate the key columns."""
        if not self.columns:
            raise PydqError("unique requires at least one column.")
        for column in self.columns:
            _column(column)
        if len(set(self.columns)) != len(self.columns):
            raise PydqError("unique columns must be distinct.")
        _optional_name(self.name)

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "unique"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, ", ".join(self.columns))

    def parameters(self) -> dict[str, Any]:
        """Return the key columns."""
        return {"columns": list(self.columns)}

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Count rows that participate in a duplicate key."""
        missing = _missing_many(self, ctx, list(self.columns))
        if missing is not None:
            return missing
        found = ctx.frame.duplicate_failures(list(self.columns), ctx.sample_size)
        total = ctx.frame.nrows()
        rendered = ", ".join(repr(column) for column in self.columns)
        if found.count == 0:
            message = f"Values in {rendered} are unique across {total} rows."
        else:
            how = _agree(found.count, "is a duplicate", "are duplicates")
            message = f"{found.count} of {total} rows {how} on {rendered}."
        return _done(self, ctx, found.count == 0, found.count, message, found.sample)


@dataclass(frozen=True)
class InRange:
    """Fail when numeric values fall outside inclusive bounds."""

    column: str
    minimum: float | None = None
    maximum: float | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate the column and bounds."""
        _column(self.column)
        _optional_name(self.name)
        minimum = _number_bound(self.minimum, field="minimum")
        maximum = _number_bound(self.maximum, field="maximum")
        if minimum is None and maximum is None:
            raise PydqError("in_range requires minimum, maximum, or both.")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise PydqError("in_range minimum cannot be greater than maximum.")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "in_range"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, self.column)

    def parameters(self) -> dict[str, Any]:
        """Return the column and bounds."""
        return {"column": self.column, "minimum": self.minimum, "maximum": self.maximum}

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Count non-null values outside the inclusive range."""
        missing = _missing(self, ctx, self.column)
        if missing is not None:
            return missing
        total = ctx.frame.nrows()
        if not ctx.frame.is_numeric(self.column):
            return _done(
                self,
                ctx,
                False,
                total,
                f"Column {self.column!r} is not numeric.",
                [],
            )
        found = ctx.frame.range_failures(self.column, self.minimum, self.maximum, ctx.sample_size)
        span = f"[{_fmt_bound(self.minimum, upper=False)}, {_fmt_bound(self.maximum, upper=True)}]"
        if found.count == 0:
            message = f"All non-null values in {self.column!r} are inside {span}."
        else:
            message = (
                f"{found.count} of {total} values in {self.column!r} "
                f"{_agree(found.count, 'is', 'are')} outside {span}."
            )
        return _done(self, ctx, found.count == 0, found.count, message, found.sample)


@dataclass(frozen=True)
class AllowedValues:
    """Fail when a value is outside an allowed set."""

    column: str
    values: tuple[Any, ...]
    allow_nulls: bool = True
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate the column and allowed scalars."""
        _column(self.column)
        _optional_name(self.name)
        if isinstance(self.allow_nulls, bool) is False:
            raise PydqError("allow_nulls must be a boolean.")
        for value in self.values:
            _scalar(value, field="allowed value")

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "allowed_values"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, self.column)

    def parameters(self) -> dict[str, Any]:
        """Return the column, allowed values, and null policy."""
        return {
            "column": self.column,
            "values": list(self.values),
            "allow_nulls": self.allow_nulls,
        }

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Count values that are not in the allowed set."""
        missing = _missing(self, ctx, self.column)
        if missing is not None:
            return missing
        found = ctx.frame.disallowed_failures(
            self.column,
            list(self.values),
            allow_nulls=self.allow_nulls,
            sample_size=ctx.sample_size,
        )
        total = ctx.frame.nrows()
        if found.count == 0:
            message = f"All accepted values in {self.column!r} are allowed."
        else:
            message = (
                f"{found.count} of {total} values in {self.column!r} "
                f"{_agree(found.count, 'is', 'are')} not allowed."
            )
        return _done(self, ctx, found.count == 0, found.count, message, found.sample)


@dataclass(frozen=True)
class RegexMatch:
    """Fail when a string does not fully match a regular expression."""

    column: str
    pattern: str
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate the column and compile the pattern."""
        _column(self.column)
        _optional_name(self.name)
        if not isinstance(self.pattern, str) or self.pattern == "":
            raise PydqError("regex_match pattern must be a non-empty string.")
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise PydqError(f"Invalid regex {self.pattern!r}: {exc}") from exc

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "regex_match"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, self.column)

    def parameters(self) -> dict[str, Any]:
        """Return the column, pattern, and match mode."""
        return {"column": self.column, "pattern": self.pattern, "match": "fullmatch"}

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Count non-null strings that do not fully match the pattern."""
        missing = _missing(self, ctx, self.column)
        if missing is not None:
            return missing
        total = ctx.frame.nrows()
        if not ctx.frame.is_string_like(self.column):
            return _done(
                self,
                ctx,
                False,
                total,
                f"Column {self.column!r} is not a string column.",
                [],
            )
        found = ctx.frame.regex_failures(self.column, self.pattern, ctx.sample_size)
        if found.count == 0:
            message = f"All non-null values in {self.column!r} match the pattern."
        else:
            message = (
                f"{found.count} of {total} values in {self.column!r} "
                f"{_agree(found.count, 'does', 'do')} not match the pattern."
            )
        return _done(self, ctx, found.count == 0, found.count, message, found.sample)


@dataclass(frozen=True)
class RowCountBetween:
    """Fail when the table row count is outside an inclusive window."""

    minimum: int | None = None
    maximum: int | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate the inclusive window."""
        _optional_name(self.name)
        _count_bound(self.minimum, field="minimum")
        _count_bound(self.maximum, field="maximum")
        if self.minimum is None and self.maximum is None:
            raise PydqError("row_count_between requires minimum, maximum, or both.")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise PydqError("row_count_between minimum cannot be greater than maximum.")

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "row_count_between"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, "rows")

    def parameters(self) -> dict[str, Any]:
        """Return the inclusive bounds."""
        return {"minimum": self.minimum, "maximum": self.maximum}

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Compare the frame row count with the configured window."""
        total = ctx.frame.nrows()
        span = f"[{_fmt_count(self.minimum, upper=False)}, {_fmt_count(self.maximum, upper=True)}]"
        distance = 0
        if self.minimum is not None and total < self.minimum:
            distance = self.minimum - total
        elif self.maximum is not None and total > self.maximum:
            distance = total - self.maximum
        if distance == 0:
            message = f"Row count {total} is inside {span}."
        else:
            message = f"Row count {total} is outside {span}."
        return _done(self, ctx, distance == 0, distance, message, [])


@dataclass(frozen=True)
class Freshness:
    """Fail when the newest timestamp is older than ``max_age`` before ``as_of``."""

    column: str
    max_age: Any
    name: str | None = None
    max_age_label: str = ""

    def __post_init__(self) -> None:
        """Validate the column and store a parsed duration."""
        _column(self.column)
        _optional_name(self.name)
        label = self.max_age.strip() if isinstance(self.max_age, str) else ""
        object.__setattr__(self, "max_age", parse_duration(self.max_age))
        object.__setattr__(self, "max_age_label", label or format_duration(self.max_age))

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "freshness"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, self.column)

    def parameters(self) -> dict[str, Any]:
        """Return the column and maximum age in seconds."""
        return {"column": self.column, "max_age_seconds": self.max_age.total_seconds()}

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Compare the column's maximum timestamp with the suite clock."""
        missing = _missing(self, ctx, self.column)
        if missing is not None:
            return missing
        total = ctx.frame.nrows()
        cutoff = ctx.as_of - self.max_age
        inspected = ctx.frame.inspect_timestamps(self.column, cutoff, ctx.sample_size)
        age = self.max_age_label
        if inspected.numeric_column:
            return _done(
                self,
                ctx,
                False,
                total,
                (
                    f"Column {self.column!r} is numeric. Cast epoch values to "
                    "datetimes before a freshness check."
                ),
                [],
            )
        non_null = total - inspected.null_count
        if non_null == 0:
            return _done(
                self,
                ctx,
                False,
                total,
                f"Column {self.column!r} has no timestamps.",
                [],
            )
        if inspected.unparsed_count:
            return _done(
                self,
                ctx,
                False,
                inspected.unparsed_count,
                (
                    f"{inspected.unparsed_count} "
                    f"{_agree(inspected.unparsed_count, 'value', 'values')} in {self.column!r} "
                    f"{_agree(inspected.unparsed_count, 'is', 'are')} not ISO-8601 timestamps."
                ),
                inspected.sample_unparsed,
            )
        assert inspected.maximum is not None
        maximum = inspected.maximum.isoformat()
        anchor = ctx.as_of.isoformat()
        if inspected.maximum < cutoff:
            return _done(
                self,
                ctx,
                False,
                inspected.stale_count,
                (
                    f"Latest timestamp in {self.column!r} is {maximum}, older than "
                    f"{age} before {anchor}."
                ),
                inspected.sample_stale,
            )
        return _done(
            self,
            ctx,
            True,
            0,
            f"Latest timestamp in {self.column!r} is {maximum}, within {age} of {anchor}.",
            [],
        )


@dataclass(frozen=True)
class Schema:
    """Fail when columns are missing, unexpected, or the wrong dtype."""

    columns: tuple[tuple[str, str], ...]
    exact: bool = False
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate column names and dtype aliases."""
        _optional_name(self.name)
        if isinstance(self.exact, bool) is False:
            raise PydqError("schema exact must be a boolean.")
        if not self.columns:
            raise PydqError("schema requires at least one column.")
        seen: set[str] = set()
        normalized: list[tuple[str, str]] = []
        for column, dtype in self.columns:
            _column(column)
            if column in seen:
                raise PydqError(f"schema column {column!r} is listed more than once.")
            seen.add(column)
            normalized.append((column, canonical_dtype(dtype)))
        object.__setattr__(self, "columns", tuple(normalized))

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "schema"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, "columns")

    def parameters(self) -> dict[str, Any]:
        """Return the expected canonical dtypes."""
        return {"columns": dict(self.columns), "exact": self.exact}

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Compare actual canonical dtypes with the expected mapping."""
        actual = ctx.frame.dtypes()
        expected = dict(self.columns)
        missing = [column for column in expected if column not in actual]
        mismatched = [
            f"{column}: expected {dtype}, found {actual[column]}"
            for column, dtype in expected.items()
            if column in actual and actual[column] != dtype
        ]
        unexpected = [column for column in actual if column not in expected] if self.exact else []
        problems = len(missing) + len(mismatched) + len(unexpected)
        if problems == 0:
            message = "Columns match the expected schema."
            return _done(self, ctx, True, 0, message, [])
        parts: list[str] = []
        if missing:
            parts.append("missing [" + ", ".join(missing) + "]")
        if mismatched:
            parts.append("mismatched [" + "; ".join(mismatched) + "]")
        if unexpected:
            parts.append("unexpected [" + ", ".join(unexpected) + "]")
        message = "Schema mismatch: " + "; ".join(parts) + "."
        return _done(self, ctx, False, problems, message, [])


@dataclass(frozen=True)
class ReferentialIntegrity:
    """Fail when a key is absent from a reference column."""

    column: str
    ref: str
    ref_column: str
    allow_nulls: bool = True
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate column names and the reference label."""
        _column(self.column)
        _column(self.ref_column, field="ref_column")
        _optional_name(self.name)
        if not isinstance(self.ref, str) or self.ref == "" or "=" in self.ref:
            raise PydqError("ref must be a non-empty name without '='.")
        if isinstance(self.allow_nulls, bool) is False:
            raise PydqError("allow_nulls must be a boolean.")

    @property
    def check_type(self) -> str:
        """Return the check identifier."""
        return "referential_integrity"

    @property
    def display_name(self) -> str:
        """Return the report label."""
        return _label(self.name, self.check_type, f"{self.column} -> {self.ref}.{self.ref_column}")

    def parameters(self) -> dict[str, Any]:
        """Return the foreign key and reference column."""
        return {
            "column": self.column,
            "ref": self.ref,
            "ref_column": self.ref_column,
            "allow_nulls": self.allow_nulls,
        }

    def evaluate(self, ctx: EvalContext) -> CheckResult:
        """Count keys that are missing from the reference frame."""
        if self.ref not in ctx.refs:
            known = ", ".join(sorted(ctx.refs)) or "(none)"
            raise PydqError(
                f"Reference {self.ref!r} was not provided. Pass it in refs or --ref. "
                f"Known references: {known}."
            )
        reference = ctx.refs[self.ref]
        missing = _missing(self, ctx, self.column)
        if missing is not None:
            return missing
        if not reference.has_column(self.ref_column):
            return _done(
                self,
                ctx,
                False,
                ctx.frame.nrows(),
                f"Reference {self.ref!r} has no column {self.ref_column!r}.",
                [],
            )
        found = ctx.frame.reference_failures(
            self.column,
            reference,
            self.ref_column,
            allow_nulls=self.allow_nulls,
            sample_size=ctx.sample_size,
        )
        total = ctx.frame.nrows()
        target = f"{self.ref}.{self.ref_column}"
        if found.count == 0:
            message = f"All accepted values in {self.column!r} exist in {target}."
        else:
            message = (
                f"{found.count} of {total} values in {self.column!r} "
                f"{_agree(found.count, 'is', 'are')} missing from {target}."
            )
        return _done(self, ctx, found.count == 0, found.count, message, found.sample)


def not_null(column: str, *, name: str | None = None) -> NotNull:
    """Build a check that fails when ``column`` contains nulls.

    Args:
        column: Column to test.
        name: Optional report label.

    Returns:
        A not-null check.
    """
    return NotNull(column=column, name=name)


def unique(
    column: str | Sequence[str] | None = None,
    columns: Sequence[str] | None = None,
    *,
    name: str | None = None,
) -> Unique:
    """Build a uniqueness check.

    Args:
        column: One column, or a sequence of columns when ``columns`` is omitted.
        columns: Columns that form a composite key.
        name: Optional report label.

    Returns:
        A uniqueness check.

    Raises:
        PydqError: Both forms are passed, or no columns are passed.
    """
    chosen = _select_columns(column, columns)
    return Unique(columns=chosen, name=name)


def in_range(
    column: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    name: str | None = None,
) -> InRange:
    """Build an inclusive numeric range check.

    Args:
        column: Numeric column to test. Nulls are ignored.
        minimum: Inclusive lower bound. Omit for no lower bound.
        maximum: Inclusive upper bound. Omit for no upper bound.
        name: Optional report label.

    Returns:
        A range check.
    """
    return InRange(column=column, minimum=minimum, maximum=maximum, name=name)


def allowed_values(
    column: str,
    values: Sequence[Any],
    *,
    allow_nulls: bool = True,
    name: str | None = None,
) -> AllowedValues:
    """Build a membership check.

    Args:
        column: Column to test.
        values: Allowed scalars. Comparison is exact, with no type coercion.
        allow_nulls: When true, nulls pass.
        name: Optional report label.

    Returns:
        A membership check.
    """
    return AllowedValues(
        column=column,
        values=tuple(values),
        allow_nulls=allow_nulls,
        name=name,
    )


def regex_match(column: str, pattern: str, *, name: str | None = None) -> RegexMatch:
    """Build a full-match regular expression check.

    Args:
        column: String column to test. Nulls are ignored.
        pattern: Regular expression matched against the entire value.
        name: Optional report label.

    Returns:
        A regex check.
    """
    return RegexMatch(column=column, pattern=pattern, name=name)


def row_count_between(
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    name: str | None = None,
) -> RowCountBetween:
    """Build an inclusive row-count check.

    Args:
        minimum: Inclusive lower bound.
        maximum: Inclusive upper bound.
        name: Optional report label.

    Returns:
        A row-count check.
    """
    return RowCountBetween(minimum=minimum, maximum=maximum, name=name)


def freshness(column: str, max_age: Any, *, name: str | None = None) -> Freshness:
    """Build a freshness check on the newest timestamp in ``column``.

    Args:
        column: Datetime column, or a string column of ISO-8601 timestamps.
            Numeric epoch columns are rejected.
        max_age: Maximum age of the newest value, as a ``timedelta``, a number
            of seconds, or a compact string such as ``24h``.
        name: Optional report label.

    Returns:
        A freshness check.
    """
    return Freshness(column=column, max_age=max_age, name=name)


def schema(
    columns: Mapping[str, str],
    *,
    exact: bool = False,
    name: str | None = None,
) -> Schema:
    """Build a dtype check.

    Args:
        columns: Mapping of column name to dtype alias. Aliases such as
            ``int``, ``string``, and ``timestamp`` are normalized before
            comparison. Extra columns are allowed unless ``exact`` is true.
        exact: When true, columns that were not listed fail the check.
        name: Optional report label.

    Returns:
        A schema check.
    """
    pairs = tuple((str(key), str(value)) for key, value in columns.items())
    return Schema(columns=pairs, exact=exact, name=name)


def referential_integrity(
    column: str,
    *,
    ref: str,
    ref_column: str,
    allow_nulls: bool = True,
    name: str | None = None,
) -> ReferentialIntegrity:
    """Build a foreign-key check against another frame.

    Args:
        column: Column on the frame under test.
        ref: Name of the reference frame supplied to :meth:`Suite.run`.
        ref_column: Column on the reference frame.
        allow_nulls: When true, null foreign keys pass.
        name: Optional report label.

    Returns:
        A referential-integrity check.
    """
    return ReferentialIntegrity(
        column=column,
        ref=ref,
        ref_column=ref_column,
        allow_nulls=allow_nulls,
        name=name,
    )


def canonical_dtype(label: str) -> str:
    """Map a user-facing dtype label to the canonical name.

    Args:
        label: Dtype alias such as ``int``, ``string``, or ``timestamp``.

    Returns:
        The canonical dtype name.

    Raises:
        PydqError: The label is not a known alias.
    """
    if not isinstance(label, str):
        raise PydqError(f"Unknown dtype {label!r}.")
    key = label.strip().lower()
    if key not in DTYPE_ALIASES:
        known = ", ".join(sorted(set(DTYPE_ALIASES)))
        raise PydqError(f"Unknown dtype {label!r}. Expected one of: {known}.")
    return DTYPE_ALIASES[key]


def _done(
    check: Check,
    ctx: EvalContext,
    passed: bool,
    failing_rows: int,
    message: str,
    sample: list[dict[str, Any]],
) -> CheckResult:
    return CheckResult(
        name=check.display_name,
        check_type=check.check_type,
        passed=passed,
        failing_rows=failing_rows,
        total_rows=ctx.frame.nrows(),
        message=message,
        sample_failing_rows=sample,
        parameters=check.parameters(),
    )


def _missing(check: Check, ctx: EvalContext, column: str) -> CheckResult | None:
    if ctx.frame.has_column(column):
        return None
    return _done(
        check,
        ctx,
        False,
        ctx.frame.nrows(),
        f"Column {column!r} does not exist.",
        [],
    )


def _missing_many(check: Check, ctx: EvalContext, columns: list[str]) -> CheckResult | None:
    absent = [column for column in columns if not ctx.frame.has_column(column)]
    if not absent:
        return None
    rendered = ", ".join(repr(column) for column in absent)
    return _done(
        check,
        ctx,
        False,
        ctx.frame.nrows(),
        (
            f"Column {rendered} does not exist."
            if len(absent) == 1
            else f"Columns {rendered} do not exist."
        ),
        [],
    )


def _agree(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _label(name: str | None, check_type: str, detail: str) -> str:
    if name is not None:
        return name
    return f"{check_type}({detail})"


def _optional_name(name: str | None) -> None:
    if name is None:
        return
    if not isinstance(name, str) or name.strip() == "":
        raise PydqError("check name must be a non-empty string.")


def _column(value: str, *, field: str = "column") -> None:
    if not isinstance(value, str) or value == "":
        raise PydqError(f"{field} must be a non-empty string.")


def _scalar(value: Any, *, field: str) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise PydqError(f"{field} must be a string, number, boolean, or null.")


def _number_bound(value: float | None, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PydqError(f"in_range {field} must be a number.")
    return float(value)


def _count_bound(value: int | None, *, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise PydqError(f"{field} must be an integer.")
    if value < 0:
        raise PydqError(f"{field} must be >= 0.")


def _select_columns(
    column: str | Sequence[str] | None,
    columns: Sequence[str] | None,
) -> tuple[str, ...]:
    if column is not None and columns is not None:
        raise PydqError("Pass unique column or columns, not both.")
    selected: Sequence[str]
    if columns is not None:
        selected = columns
    elif isinstance(column, str):
        selected = (column,)
    elif column is not None:
        selected = column
    else:
        raise PydqError("unique requires at least one column.")
    return tuple(selected)


def _fmt_bound(value: float | None, *, upper: bool) -> str:
    if value is None:
        return "+inf" if upper else "-inf"
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _fmt_count(value: int | None, *, upper: bool) -> str:
    if value is None:
        return "+inf" if upper else "0"
    return str(value)
