"""CLI exit codes and report output."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from pydq.cli import main

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "examples" / "suite.yaml"
ORDERS = ROOT / "examples" / "orders.csv"
INVALID = ROOT / "examples" / "orders_invalid.csv"
CUSTOMERS = ROOT / "examples" / "customers.csv"


def _run(argv: list[str]) -> tuple[int, str, str]:
    stdout = pytest.importorskip("io").StringIO()
    stderr = pytest.importorskip("io").StringIO()
    code = main(argv, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_cli_pass_and_fail(tmp_path: Path) -> None:
    code, out, err = _run(
        [
            "run",
            str(SUITE),
            "--data",
            str(ORDERS),
            "--ref",
            f"customers={CUSTOMERS}",
            "--output",
            str(tmp_path / "nested" / "report.md"),
        ]
    )
    assert code == 0
    assert err == ""
    assert "All checks passed." in out
    assert (tmp_path / "nested" / "report.md").read_text(encoding="utf-8") == out

    code, out, err = _run(
        [
            "run",
            str(SUITE),
            "--data",
            str(INVALID),
            "--ref",
            f"customers={CUSTOMERS}",
            "--format",
            "json",
            "--quiet",
            "--output",
            str(tmp_path / "fail.json"),
            "--sample-size",
            "1",
        ]
    )
    assert code == 1
    assert out == ""
    payload = json.loads((tmp_path / "fail.json").read_text(encoding="utf-8"))
    assert payload["passed"] is False
    failed = [item for item in payload["checks"] if not item["passed"]]
    assert failed
    assert all(len(item["sample_failing_rows"]) <= 1 for item in failed)


def test_cli_usage_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, _out, err = _run(["run", str(SUITE), "--data", str(tmp_path / "missing.csv")])
    assert code == 2
    assert "error:" in err
    code, _out, err = _run(["run", str(SUITE), "--data", str(ORDERS), "--ref", "customers"])
    assert code == 2
    assert "NAME=PATH" in err
    code, _out, err = _run(
        [
            "run",
            str(SUITE),
            "--data",
            str(ORDERS),
            "--ref",
            f"customers={CUSTOMERS}",
            "--ref",
            f"customers={CUSTOMERS}",
        ]
    )
    assert code == 2
    assert "more than once" in err
    code, _out, _err = _run(["--help"])
    assert code == 0
    code, _out, _err = _run(["--version"])
    assert code == 0
    code, _out, _err = _run([])
    assert code == 2
    assert main(["--not-a-flag"]) == 2
    monkeypatch.setattr(sys, "argv", ["pydq", "--version"])
    assert main(None) == 0
    code, _out, err = _run(
        [
            "run",
            str(SUITE),
            "--data",
            str(ORDERS),
            "--ref",
            f"customers={CUSTOMERS}",
            "--output",
            str(tmp_path),
        ]
    )
    assert code == 2
    assert "error:" in err

    def explode(*_args: object, **_kwargs: object) -> object:
        raise SystemExit("boom")

    parser = type("P", (), {"parse_args": staticmethod(explode)})()
    monkeypatch.setattr("pydq.cli.build_parser", lambda: parser)
    assert main(["run"]) == 2


def test_module_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["pydq", "--version"])
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("pydq", run_name="__main__")
    assert caught.value.code == 0
    assert "pydq" in capsys.readouterr().out
