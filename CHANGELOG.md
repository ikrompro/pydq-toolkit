# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-16

### Added

- Declarative checks for pandas DataFrames, with polars DataFrames accepted at
  the boundary: `not_null`, `unique`, `in_range`, `allowed_values`,
  `regex_match`, `row_count_between`, `freshness`, `schema`, and
  `referential_integrity`.
- Suites defined in Python or YAML version 1.
- JSON and Markdown reports with failing-row counts and samples.
- `pydq run` CLI for CSV and Parquet, with exit code 1 when a check fails.
- Example suite and synthetic orders dataset.
- pytest, ruff, mypy, pre-commit, and a GitHub Actions matrix for Python
  3.10–3.12.

[0.1.0]: https://github.com/ikrompro/pydq-toolkit/releases/tag/v0.1.0
