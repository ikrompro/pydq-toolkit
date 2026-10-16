"""Load a suite from a YAML document or a plain dictionary."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from pydq.checks import (
    allowed_values,
    canonical_dtype,
    freshness,
    in_range,
    not_null,
    referential_integrity,
    regex_match,
    row_count_between,
    schema,
    unique,
)
from pydq.errors import PydqError, SuiteLoadError
from pydq.suite import Suite

_SUITE_FIELDS = {"version", "name", "checks", "sample_size", "as_of"}
_CHECK_TYPES = (
    "not_null",
    "unique",
    "in_range",
    "allowed_values",
    "regex_match",
    "row_count_between",
    "freshness",
    "schema",
    "referential_integrity",
)


def load_suite(path: str | Path) -> Suite:
    """Read a YAML suite from disk.

    Args:
        path: Path to a UTF-8 YAML file.

    Returns:
        A validated suite.

    Raises:
        SuiteLoadError: The file cannot be read or does not match the schema.
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SuiteLoadError(f"Could not read suite {file_path}: {exc}") from exc
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SuiteLoadError(f"Invalid YAML in {file_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SuiteLoadError(f"Suite file {file_path} must contain a mapping.")
    return suite_from_dict(payload)


def suite_from_dict(payload: Mapping[str, Any]) -> Suite:
    """Build a suite from a dictionary in the YAML schema.

    Args:
        payload: Suite document. ``version`` must be ``1`` when present.

    Returns:
        A validated suite.

    Raises:
        SuiteLoadError: The document has unknown fields or invalid checks.
    """
    unknown = sorted(set(payload) - _SUITE_FIELDS)
    if unknown:
        raise SuiteLoadError(f"Unknown suite fields: {', '.join(unknown)}.")
    if "version" in payload and payload["version"] != 1:
        raise SuiteLoadError("Unsupported suite version. Expected version: 1.")
    if "name" not in payload:
        raise SuiteLoadError("Suite requires 'name'.")
    name = payload["name"]
    if not isinstance(name, str) or name.strip() == "":
        raise SuiteLoadError("Suite name must be a non-empty string.")
    raw_checks = payload.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise SuiteLoadError("Suite requires a non-empty 'checks' list.")
    checks = [_build_check(item, index) for index, item in enumerate(raw_checks, start=1)]
    sample_size = 5
    if "sample_size" in payload:
        sample_size = _as_int(payload["sample_size"], field="sample_size")
        if sample_size < 0:
            raise SuiteLoadError("sample_size must be >= 0.")
    as_of = payload.get("as_of")
    if as_of is not None and not isinstance(as_of, str):
        raise SuiteLoadError("as_of must be an ISO-8601 string.")
    try:
        return Suite(name, checks, sample_size=sample_size, as_of=as_of)
    except PydqError as exc:
        raise SuiteLoadError(str(exc)) from exc


def _build_check(item: Any, index: int) -> Any:
    if not isinstance(item, dict):
        raise SuiteLoadError(f"Check {index} must be a mapping.")
    raw = dict(item)
    check_type = raw.pop("type", None)
    if not isinstance(check_type, str):
        raise SuiteLoadError(f"Check {index} requires a string 'type'.")
    builders = {
        "not_null": _build_not_null,
        "unique": _build_unique,
        "in_range": _build_in_range,
        "allowed_values": _build_allowed_values,
        "regex_match": _build_regex,
        "row_count_between": _build_row_count,
        "freshness": _build_freshness,
        "schema": _build_schema,
        "referential_integrity": _build_referential,
    }
    builder = builders.get(check_type)
    if builder is None:
        known = ", ".join(_CHECK_TYPES)
        raise SuiteLoadError(
            f"Check {index} has unknown type {check_type!r}. Expected one of: {known}."
        )
    try:
        return builder(raw, index)
    except SuiteLoadError:
        raise
    except PydqError as exc:
        raise SuiteLoadError(f"Check {index} ({check_type}) is invalid: {exc}") from exc


def _build_not_null(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(raw, {"column", "name"}, index, "not_null")
    return not_null(_require_str(raw, "column", index), name=_optional_name(raw, index))


def _build_unique(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(raw, {"column", "columns", "name"}, index, "unique")
    column = raw.get("column")
    columns = raw.get("columns")
    if column is not None and columns is not None:
        raise SuiteLoadError(f"Check {index} (unique) accepts column or columns, not both.")
    if columns is not None:
        return unique(
            columns=_str_list(columns, field="columns", index=index),
            name=_optional_name(raw, index),
        )
    if isinstance(column, str):
        return unique(column, name=_optional_name(raw, index))
    raise SuiteLoadError(f"Check {index} (unique) requires 'column' or 'columns'.")


def _build_in_range(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(raw, {"column", "min", "max", "minimum", "maximum", "name"}, index, "in_range")
    return in_range(
        _require_str(raw, "column", index),
        minimum=_optional_number(raw, ("minimum", "min"), index),
        maximum=_optional_number(raw, ("maximum", "max"), index),
        name=_optional_name(raw, index),
    )


def _build_allowed_values(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(raw, {"column", "values", "allow_nulls", "name"}, index, "allowed_values")
    if "values" not in raw or not isinstance(raw["values"], list):
        raise SuiteLoadError(f"Check {index} (allowed_values) requires a list 'values'.")
    return allowed_values(
        _require_str(raw, "column", index),
        raw["values"],
        allow_nulls=_optional_bool(raw, "allow_nulls", index, default=True),
        name=_optional_name(raw, index),
    )


def _build_regex(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(raw, {"column", "pattern", "name"}, index, "regex_match")
    pattern = raw.get("pattern")
    if not isinstance(pattern, str) or pattern == "":
        raise SuiteLoadError(f"Check {index} (regex_match) requires a string 'pattern'.")
    return regex_match(_require_str(raw, "column", index), pattern, name=_optional_name(raw, index))


def _build_row_count(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(raw, {"min", "max", "minimum", "maximum", "name"}, index, "row_count_between")
    return row_count_between(
        minimum=_optional_count(raw, ("minimum", "min"), index),
        maximum=_optional_count(raw, ("maximum", "max"), index),
        name=_optional_name(raw, index),
    )


def _build_freshness(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(raw, {"column", "max_age", "name"}, index, "freshness")
    if "max_age" not in raw:
        raise SuiteLoadError(f"Check {index} (freshness) requires 'max_age'.")
    max_age = raw["max_age"]
    if not isinstance(max_age, (str, int, float)) or isinstance(max_age, bool):
        raise SuiteLoadError(f"Check {index} (freshness) max_age must be a string or number.")
    return freshness(_require_str(raw, "column", index), max_age, name=_optional_name(raw, index))


def _build_schema(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(raw, {"columns", "exact", "name"}, index, "schema")
    columns = raw.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise SuiteLoadError(f"Check {index} (schema) requires a non-empty mapping 'columns'.")
    normalized: dict[str, str] = {}
    for key, value in columns.items():
        if not isinstance(key, str) or key == "" or not isinstance(value, str):
            raise SuiteLoadError(
                f"Check {index} (schema) columns must map non-empty names to dtype strings."
            )
        canonical_dtype(value)
        normalized[key] = value
    return schema(
        normalized,
        exact=_optional_bool(raw, "exact", index, default=False),
        name=_optional_name(raw, index),
    )


def _build_referential(raw: dict[str, Any], index: int) -> Any:
    _reject_unknown(
        raw,
        {"column", "ref", "ref_column", "allow_nulls", "name"},
        index,
        "referential_integrity",
    )
    ref = raw.get("ref")
    ref_column = raw.get("ref_column")
    if not isinstance(ref, str) or ref == "":
        raise SuiteLoadError(f"Check {index} (referential_integrity) requires string 'ref'.")
    if not isinstance(ref_column, str) or ref_column == "":
        raise SuiteLoadError(f"Check {index} (referential_integrity) requires string 'ref_column'.")
    return referential_integrity(
        _require_str(raw, "column", index),
        ref=ref,
        ref_column=ref_column,
        allow_nulls=_optional_bool(raw, "allow_nulls", index, default=True),
        name=_optional_name(raw, index),
    )


def _reject_unknown(raw: dict[str, Any], allowed: set[str], index: int, check_type: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise SuiteLoadError(
            f"Check {index} ({check_type}) has unknown fields: {', '.join(unknown)}."
        )


def _require_str(raw: Mapping[str, Any], field: str, index: int) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or value == "":
        raise SuiteLoadError(f"Check {index} requires a non-empty string '{field}'.")
    return value


def _optional_name(raw: Mapping[str, Any], index: int) -> str | None:
    if "name" not in raw:
        return None
    value = raw["name"]
    if not isinstance(value, str) or value.strip() == "":
        raise SuiteLoadError(f"Check {index} name must be a non-empty string.")
    return value


def _optional_bool(raw: Mapping[str, Any], field: str, index: int, *, default: bool) -> bool:
    if field not in raw:
        return default
    value = raw[field]
    if not isinstance(value, bool):
        raise SuiteLoadError(f"Check {index} field '{field}' must be a boolean.")
    return value


def _optional_number(
    raw: Mapping[str, Any],
    fields: tuple[str, ...],
    index: int,
) -> float | None:
    present = [field for field in fields if field in raw]
    if len(present) > 1:
        joined = " and ".join(present)
        raise SuiteLoadError(f"Check {index} uses both {joined}. Pick one.")
    if not present:
        return None
    value = raw[present[0]]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SuiteLoadError(f"Check {index} field '{present[0]}' must be a number.")
    return float(value)


def _optional_count(
    raw: Mapping[str, Any],
    fields: tuple[str, ...],
    index: int,
) -> int | None:
    present = [field for field in fields if field in raw]
    if len(present) > 1:
        joined = " and ".join(present)
        raise SuiteLoadError(f"Check {index} uses both {joined}. Pick one.")
    if not present:
        return None
    return _as_int(raw[present[0]], field=present[0], index=index)


def _str_list(value: Any, *, field: str, index: int) -> list[str]:
    items_are_strings = isinstance(value, list) and all(
        isinstance(item, str) and item for item in value
    )
    if not items_are_strings or not value:
        raise SuiteLoadError(f"Check {index} field '{field}' must be a non-empty list of strings.")
    return list(value)


def _as_int(value: Any, *, field: str, index: int | None = None) -> int:
    prefix = f"Check {index} field" if index is not None else "Field"
    if isinstance(value, bool):
        raise SuiteLoadError(f"{prefix} '{field}' must be an integer.")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise SuiteLoadError(f"{prefix} '{field}' must be an integer.")
