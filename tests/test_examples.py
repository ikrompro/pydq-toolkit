"""The published examples stay runnable."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from examples.generate_dataset import generate

from pydq.cli import main
from pydq.loader import load_suite

ROOT = Path(__file__).resolve().parents[1]


def test_generator_matches_committed_files(tmp_path: Path) -> None:
    generate(tmp_path)
    for name in ("customers.csv", "orders.csv", "orders_invalid.csv"):
        generated = (tmp_path / name).read_text(encoding="utf-8")
        committed = (ROOT / "examples" / name).read_text(encoding="utf-8")
        assert generated == committed


def test_example_suite_pass_and_fail() -> None:
    suite = load_suite(ROOT / "examples" / "suite.yaml")
    customers = pd.read_csv(ROOT / "examples" / "customers.csv")
    passed = suite.run(pd.read_csv(ROOT / "examples" / "orders.csv"), {"customers": customers})
    assert passed.passed is True
    assert passed.passed_count == 10
    failed = suite.run(
        pd.read_csv(ROOT / "examples" / "orders_invalid.csv"),
        {"customers": customers},
    )
    assert failed.passed is False
    outcomes = {check.name: check.passed for check in failed.checks}
    assert outcomes["order_id is present"] is True
    assert outcomes["email is present"] is False
    assert outcomes["unique(order_id)"] is False
    assert outcomes["in_range(amount)"] is False
    assert outcomes["allowed_values(status)"] is False
    assert outcomes["regex_match(email)"] is False
    assert outcomes["row_count_between(rows)"] is True
    assert outcomes["freshness(ordered_at)"] is False
    assert outcomes["schema(columns)"] is True
    assert outcomes["referential_integrity(customer_id -> customers.customer_id)"] is False


def test_python_quickstart_and_console_script() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "python_quickstart.py")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "All checks passed." in completed.stdout
    code = main(
        [
            "run",
            str(ROOT / "examples" / "suite.yaml"),
            "--data",
            str(ROOT / "examples" / "orders.csv"),
            "--ref",
            f"customers={ROOT / 'examples' / 'customers.csv'}",
            "--as-of",
            "2026-10-16T12:00:00Z",
        ]
    )
    assert code == 0


def test_polars_engine_matches_pandas_results() -> None:
    polars = pytest.importorskip("polars")
    suite = load_suite(ROOT / "examples" / "suite.yaml")
    orders = polars.read_csv(ROOT / "examples" / "orders_invalid.csv", try_parse_dates=False)
    customers = polars.read_csv(ROOT / "examples" / "customers.csv", try_parse_dates=False)
    pandas_orders = pd.read_csv(ROOT / "examples" / "orders_invalid.csv")
    pandas_customers = pd.read_csv(ROOT / "examples" / "customers.csv")
    left = suite.run(orders, {"customers": customers})
    right = suite.run(pandas_orders, {"customers": pandas_customers})
    assert left.backend == "polars"
    assert right.backend == "pandas"
    assert [(item.check_type, item.passed, item.failing_rows) for item in left.checks] == [
        (item.check_type, item.passed, item.failing_rows) for item in right.checks
    ]
    assert (
        main(
            [
                "run",
                str(ROOT / "examples" / "suite.yaml"),
                "--data",
                str(ROOT / "examples" / "orders.csv"),
                "--ref",
                f"customers={ROOT / 'examples' / 'customers.csv'}",
                "--engine",
                "polars",
                "--quiet",
            ]
        )
        == 0
    )
