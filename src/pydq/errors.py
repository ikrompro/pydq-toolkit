"""Errors raised for configuration and input problems.

Check failures are results, not exceptions. These errors mean the run could
not be evaluated: a broken suite file, an unreadable table, or an API misuse.
"""


class PydqError(Exception):
    """Base class for pydq configuration and usage errors."""


class SuiteLoadError(PydqError):
    """A suite document could not be parsed or validated."""


class DataLoadError(PydqError):
    """A CSV or Parquet table could not be read."""
