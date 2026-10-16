"""Read CSV and Parquet tables for the CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from pydq.errors import DataLoadError

_CSV = {".csv"}
_PARQUET = {".parquet", ".pq"}


def load_table(path: str | Path, *, engine: str = "pandas") -> Any:
    """Load a CSV or Parquet file.

    Args:
        path: File path. The suffix selects the format.
        engine: ``pandas`` or ``polars``. Polars CSV reading does not parse
            dates, so string timestamps stay strings and match the pandas path.

    Returns:
        A pandas or polars DataFrame.

    Raises:
        DataLoadError: The file is missing, the suffix is unsupported, or an
            optional reader dependency is not installed.
    """
    if engine not in {"pandas", "polars"}:
        raise DataLoadError("engine must be 'pandas' or 'polars'.")
    file_path = Path(path)
    if not file_path.is_file():
        raise DataLoadError(f"Data file not found: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix in _CSV:
        return _read_csv(file_path, engine)
    if suffix in _PARQUET:
        return _read_parquet(file_path, engine)
    raise DataLoadError(f"Unsupported file type {suffix!r}. Use .csv, .parquet, or .pq.")


def _read_csv(path: Path, engine: str) -> Any:
    if engine == "polars":
        polars = _import_polars()
        try:
            return polars.read_csv(path, try_parse_dates=False)
        except Exception as exc:
            raise DataLoadError(f"Could not read {path}: {exc}") from exc
    try:
        return pd.read_csv(path, encoding="utf-8")
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataLoadError(f"Could not read {path}: {exc}") from exc


def _read_parquet(path: Path, engine: str) -> Any:
    if engine == "polars":
        polars = _import_polars()
        try:
            return polars.read_parquet(path)
        except Exception as exc:
            raise DataLoadError(f"Could not read {path}: {exc}") from exc
    try:
        return pd.read_parquet(path)
    except ImportError as exc:
        raise _parquet_extra() from exc
    except (OSError, ValueError) as exc:
        if "engine" in str(exc).lower() or "pyarrow" in str(exc).lower():
            raise _parquet_extra() from exc
        raise DataLoadError(f"Could not read {path}: {exc}") from exc


def _import_polars() -> Any:
    try:
        import polars as pl
    except ImportError as exc:
        raise DataLoadError(
            "engine 'polars' requires polars. Install it with: pip install 'pydq-toolkit[polars]'"
        ) from exc
    return pl


def _parquet_extra() -> DataLoadError:
    return DataLoadError(
        "Reading parquet requires pyarrow. Install it with: pip install 'pydq-toolkit[parquet]'"
    )
