"""Command-line interface.

``pydq run`` exits 0 when every check passes, 1 when a check fails, and 2 when
the suite or the input tables cannot be loaded.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from pydq._version import __version__
from pydq.errors import PydqError
from pydq.io import load_table
from pydq.loader import load_suite

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser used by the ``pydq`` console script.

    Returns:
        A parser with the ``run`` subcommand.
    """
    parser = argparse.ArgumentParser(
        prog="pydq",
        description="Run declarative data-quality checks on CSV and Parquet tables.",
    )
    parser.add_argument("--version", action="version", version=f"pydq {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run a YAML suite against a table.")
    run.add_argument("suite", type=Path, help="Path to a YAML suite.")
    run.add_argument("--data", type=Path, required=True, help="CSV or Parquet file to test.")
    run.add_argument(
        "--ref",
        action="append",
        default=None,
        metavar="NAME=PATH",
        help="Reference table used by referential_integrity. Repeat for more than one.",
    )
    run.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format written to stdout and --output. Default: markdown.",
    )
    run.add_argument("--output", type=Path, help="Optional file to write the report to.")
    run.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Override the suite sample size.",
    )
    run.add_argument(
        "--as-of",
        dest="as_of",
        default=None,
        help="ISO-8601 clock for freshness checks. Overrides as_of in the suite file.",
    )
    run.add_argument(
        "--engine",
        choices=("pandas", "polars"),
        default="pandas",
        help="Reader used for --data and --ref. Default: pandas.",
    )
    run.add_argument("--quiet", action="store_true", help="Do not write the report to stdout.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the CLI and return a process exit code.

    Args:
        argv: Arguments, excluding the program name. Defaults to ``sys.argv``.
        stdout: Stream for the report. Defaults to ``sys.stdout``.
        stderr: Stream for errors. Defaults to ``sys.stderr``.

    Returns:
        ``0`` when all checks pass, ``1`` when any check fails, ``2`` when the
        invocation or inputs are invalid.
    """
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
    try:
        return _run(args, out)
    except PydqError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_USAGE
    except OSError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_USAGE


def _run(args: argparse.Namespace, stdout: TextIO) -> int:
    suite = load_suite(args.suite)
    data = load_table(args.data, engine=args.engine)
    refs = {
        name: load_table(path, engine=args.engine) for name, path in _parse_refs(args.ref or [])
    }
    result = suite.run(data, refs, sample_size=args.sample_size, as_of=args.as_of)
    text = result.to_json() if args.format == "json" else result.to_markdown()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    if not args.quiet:
        stdout.write(text)
    return EXIT_OK if result.passed else EXIT_FAIL


def _parse_refs(values: Sequence[str]) -> list[tuple[str, Path]]:
    parsed: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for value in values:
        name, separator, raw_path = value.partition("=")
        if separator != "=" or name == "" or raw_path == "":
            raise PydqError(f"Invalid --ref {value!r}. Expected NAME=PATH.")
        if name in seen:
            raise PydqError(f"Reference {name!r} was passed more than once.")
        seen.add(name)
        parsed.append((name, Path(raw_path)))
    return parsed
