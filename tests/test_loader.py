"""YAML suite loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from pydq.errors import SuiteLoadError
from pydq.loader import load_suite, suite_from_dict


def _check(**fields: object) -> dict[str, object]:
    return dict(fields)


def test_suite_from_dict_accepts_aliases() -> None:
    suite = suite_from_dict(
        {
            "version": 1,
            "name": "orders",
            "sample_size": 1.0,
            "as_of": "2026-10-16T12:00:00Z",
            "checks": [
                {"type": "not_null", "column": "id", "name": "present"},
                {"type": "unique", "columns": ["id", "sku"]},
                {"type": "in_range", "column": "amount", "min": 0, "max": 10},
                {"type": "allowed_values", "column": "status", "values": ["ok", 1, None]},
                {"type": "regex_match", "column": "email", "pattern": "a+"},
                {"type": "row_count_between", "minimum": 0, "maximum": 5},
                {"type": "freshness", "column": "ts", "max_age": 24},
                {"type": "schema", "columns": {"id": "int"}, "exact": False},
                {
                    "type": "referential_integrity",
                    "column": "id",
                    "ref": "parents",
                    "ref_column": "id",
                },
            ],
        }
    )
    assert suite.name == "orders"
    assert suite.sample_size == 1
    assert [check.check_type for check in suite.checks] == [
        "not_null",
        "unique",
        "in_range",
        "allowed_values",
        "regex_match",
        "row_count_between",
        "freshness",
        "schema",
        "referential_integrity",
    ]


def test_load_suite_reads_example(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text("name: demo\nchecks:\n  - type: not_null\n    column: id\n", encoding="utf-8")
    assert load_suite(path).name == "demo"
    missing = tmp_path / "missing.yaml"
    with pytest.raises(SuiteLoadError, match="Could not read"):
        load_suite(missing)
    path.write_text(":\n  - [", encoding="utf-8")
    with pytest.raises(SuiteLoadError, match="Invalid YAML"):
        load_suite(path)
    path.write_text("- just-a-list\n", encoding="utf-8")
    with pytest.raises(SuiteLoadError, match="mapping"):
        load_suite(path)
    path.write_text("", encoding="utf-8")
    with pytest.raises(SuiteLoadError, match="mapping"):
        load_suite(path)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "ok", "checks": [], "extra": 1},
        {"name": "ok", "version": 2, "checks": [{"type": "not_null", "column": "id"}]},
        {"checks": [{"type": "not_null", "column": "id"}]},
        {"name": " ", "checks": [{"type": "not_null", "column": "id"}]},
        {"name": "ok", "checks": "nope"},
        {"name": "ok", "checks": [None]},
        {"name": "ok", "checks": [{"column": "id"}]},
        {"name": "ok", "checks": [{"type": "nope"}]},
        {"name": "ok", "checks": [{"type": "not_null", "column": "id", "nope": 1}]},
        {"name": "ok", "checks": [{"type": "not_null"}]},
        {"name": "ok", "checks": [{"type": "not_null", "column": "id", "name": " "}]},
        {"name": "ok", "checks": [{"type": "unique"}]},
        {"name": "ok", "checks": [{"type": "unique", "column": "id", "columns": ["id"]}]},
        {"name": "ok", "checks": [{"type": "unique", "columns": []}]},
        {"name": "ok", "checks": [{"type": "unique", "column": ["id"]}]},
        {"name": "ok", "checks": [{"type": "in_range", "column": "n", "min": 1, "minimum": 1}]},
        {"name": "ok", "checks": [{"type": "in_range", "column": "n", "min": "1"}]},
        {"name": "ok", "checks": [{"type": "in_range", "column": "n", "min": True}]},
        {"name": "ok", "checks": [{"type": "in_range", "column": "n"}]},
        {"name": "ok", "checks": [{"type": "allowed_values", "column": "s", "values": "ok"}]},
        {"name": "ok", "checks": [{"type": "allowed_values", "column": "s", "values": [object()]}]},
        {"name": "ok", "checks": [{"type": "regex_match", "column": "s"}]},
        {"name": "ok", "checks": [{"type": "regex_match", "column": "s", "pattern": "("}]},
        {"name": "ok", "checks": [{"type": "row_count_between"}]},
        {"name": "ok", "checks": [{"type": "row_count_between", "min": 1, "minimum": 2}]},
        {"name": "ok", "checks": [{"type": "row_count_between", "min": 1.5}]},
        {"name": "ok", "checks": [{"type": "freshness", "column": "ts"}]},
        {"name": "ok", "checks": [{"type": "freshness", "column": "ts", "max_age": True}]},
        {"name": "ok", "checks": [{"type": "freshness", "column": "ts", "max_age": "nope"}]},
        {"name": "ok", "checks": [{"type": "schema", "columns": {}}]},
        {"name": "ok", "checks": [{"type": "schema", "columns": {1: "int"}}]},
        {"name": "ok", "checks": [{"type": "schema", "columns": {"id": "nope"}}]},
        {"name": "ok", "checks": [{"type": "schema", "columns": {"id": "int"}, "exact": "yes"}]},
        {"name": "ok", "checks": [{"type": "referential_integrity", "column": "id"}]},
        {
            "name": "ok",
            "checks": [
                {"type": "referential_integrity", "column": "id", "ref": "p", "ref_column": ""}
            ],
        },
        {"name": "ok", "sample_size": -1, "checks": [{"type": "not_null", "column": "id"}]},
        {"name": "ok", "sample_size": True, "checks": [{"type": "not_null", "column": "id"}]},
        {"name": "ok", "as_of": 5, "checks": [{"type": "not_null", "column": "id"}]},
        {"name": "ok", "as_of": "yesterday", "checks": [{"type": "not_null", "column": "id"}]},
        {
            "name": "ok",
            "checks": [
                {"type": "not_null", "column": "id"},
                {"type": "not_null", "column": "id"},
            ],
        },
    ],
)
def test_suite_from_dict_rejects_bad_documents(payload: dict[str, object]) -> None:
    with pytest.raises(SuiteLoadError):
        suite_from_dict(payload)
