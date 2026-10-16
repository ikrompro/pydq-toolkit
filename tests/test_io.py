"""CSV and Parquet readers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pydq.errors import DataLoadError
from pydq.io import load_table


def test_load_csv_and_parquet_roundtrip(tmp_path: Path) -> None:
    frame = pd.DataFrame({"id": [1], "amount": [1.5]})
    csv_path = tmp_path / "data.csv"
    frame.to_csv(csv_path, index=False)
    loaded = load_table(csv_path)
    assert list(loaded["id"]) == [1]
    parquet_path = tmp_path / "data.pq"
    frame.to_parquet(parquet_path, index=False)
    assert load_table(parquet_path)["amount"].iloc[0] == 1.5
    upper = tmp_path / "DATA.PARQUET"
    frame.to_parquet(upper, index=False)
    assert len(load_table(upper)) == 1


def test_load_table_rejects_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(DataLoadError, match="engine"):
        load_table(tmp_path / "data.csv", engine="spark")
    with pytest.raises(DataLoadError, match="not found"):
        load_table(tmp_path / "missing.csv")
    other = tmp_path / "notes.txt"
    other.write_text("hello", encoding="utf-8")
    with pytest.raises(DataLoadError, match="Unsupported"):
        load_table(other)
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(DataLoadError, match="Could not read"):
        load_table(empty)


def test_parquet_and_polars_reader_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "data.parquet"
    path.write_bytes(b"not-a-parquet-file")

    def missing_engine(*_args: object, **_kwargs: object) -> object:
        raise ImportError("pyarrow is not installed")

    monkeypatch.setattr("pydq.io.pd.read_parquet", missing_engine)
    with pytest.raises(DataLoadError, match="pyarrow"):
        load_table(path)

    def unusable(*_args: object, **_kwargs: object) -> object:
        raise ValueError("Unable to find a usable engine")

    monkeypatch.setattr("pydq.io.pd.read_parquet", unusable)
    with pytest.raises(DataLoadError, match="pyarrow"):
        load_table(path)

    def corrupt(*_args: object, **_kwargs: object) -> object:
        raise ValueError("corrupt footer")

    monkeypatch.setattr("pydq.io.pd.read_parquet", corrupt)
    with pytest.raises(DataLoadError, match="Could not read"):
        load_table(path)

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id\n1\n", encoding="utf-8")

    def denied(*_args: object, **_kwargs: object) -> object:
        raise OSError("denied")

    monkeypatch.setattr("pydq.io.pd.read_csv", denied)
    with pytest.raises(DataLoadError, match="Could not read"):
        load_table(csv_path)

    monkeypatch.setitem(__import__("sys").modules, "polars", None)
    with pytest.raises(DataLoadError, match="polars"):
        load_table(csv_path, engine="polars")

    class Boom:
        @staticmethod
        def read_csv(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("bad csv")

        @staticmethod
        def read_parquet(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("bad parquet")

    monkeypatch.setattr("pydq.io._import_polars", lambda: Boom)
    with pytest.raises(DataLoadError, match="Could not read"):
        load_table(csv_path, engine="polars")
    with pytest.raises(DataLoadError, match="Could not read"):
        load_table(path, engine="polars")
