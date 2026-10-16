"""Declarative data-quality checks for pandas and polars DataFrames.

Define checks in Python or YAML, run them against a table, and render a JSON
or Markdown report. The CLI uses a non-zero exit code when a check fails so a
pipeline can treat the run as a gate.
"""

from pydq._version import __version__
from pydq.checks import (
    allowed_values,
    freshness,
    in_range,
    not_null,
    referential_integrity,
    regex_match,
    row_count_between,
    schema,
    unique,
)
from pydq.errors import DataLoadError, PydqError, SuiteLoadError
from pydq.loader import load_suite, suite_from_dict
from pydq.results import CheckResult, SuiteResult
from pydq.suite import Suite

__all__ = [
    "CheckResult",
    "DataLoadError",
    "PydqError",
    "Suite",
    "SuiteLoadError",
    "SuiteResult",
    "__version__",
    "allowed_values",
    "freshness",
    "in_range",
    "load_suite",
    "not_null",
    "referential_integrity",
    "regex_match",
    "row_count_between",
    "schema",
    "suite_from_dict",
    "unique",
]
