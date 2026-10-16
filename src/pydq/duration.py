"""Parse and format durations used by freshness checks."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from pydq.errors import PydqError

_DURATION = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|w|d|h|m|s)$", re.IGNORECASE)
_SECONDS = {
    "w": 7 * 24 * 3600.0,
    "d": 24 * 3600.0,
    "h": 3600.0,
    "m": 60.0,
    "s": 1.0,
    "ms": 0.001,
}
_FORMAT_UNITS = (
    ("w", 7 * 24 * 3600.0),
    ("d", 24 * 3600.0),
    ("h", 3600.0),
    ("m", 60.0),
    ("s", 1.0),
)


def parse_duration(value: timedelta | str | int | float) -> timedelta:
    """Return a non-negative duration.

    Args:
        value: A ``timedelta``, a number of seconds, or a compact string such
            as ``30m``, ``24h``, ``2d``, ``1w``, or ``500ms``.

    Returns:
        The duration as a ``timedelta``.

    Raises:
        PydqError: The value is negative or not a recognized duration.
    """
    if isinstance(value, timedelta):
        parsed = value
    elif isinstance(value, bool):
        raise PydqError("Duration must be a non-negative number of seconds, not a boolean.")
    elif isinstance(value, (int, float)):
        if value < 0:
            raise PydqError("Duration must be a non-negative number of seconds.")
        parsed = timedelta(seconds=float(value))
    elif isinstance(value, str):
        match = _DURATION.fullmatch(value.strip())
        if match is None:
            raise PydqError(
                f"Invalid duration {value!r}. Use seconds or a suffix of "
                "ms, s, m, h, d, or w, for example 24h or 30m."
            )
        amount = float(match.group("value"))
        unit = match.group("unit").lower()
        parsed = timedelta(seconds=amount * _SECONDS[unit])
    else:
        raise PydqError("Duration must be a timedelta, number of seconds, or compact string.")
    if parsed.total_seconds() < 0:
        raise PydqError("Duration must be non-negative.")
    return parsed


def format_duration(value: timedelta) -> str:
    """Format a duration as a compact string such as ``24h`` or ``30m``.

    Args:
        value: Duration to format.

    Returns:
        A short unit suffix when the length is an exact multiple, otherwise
        a seconds value.
    """
    seconds = value.total_seconds()
    if seconds == 0:
        return "0s"
    for unit, size in _FORMAT_UNITS:
        if seconds >= size and seconds % size == 0:
            return f"{int(seconds // size)}{unit}"
    if abs(seconds) < 1:
        return f"{seconds * 1000:g}ms"
    return f"{seconds:g}s"


def parse_as_of(value: datetime | str) -> datetime:
    """Parse a timezone-aware UTC timestamp.

    Naive datetimes are treated as UTC. A trailing ``Z`` is accepted so the
    same strings work on Python 3.10 and newer.

    Args:
        value: A datetime or ISO-8601 string.

    Returns:
        An aware datetime in UTC.

    Raises:
        PydqError: The value is not a valid timestamp.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise PydqError(f"Invalid as_of timestamp {value!r}.") from exc
    else:
        raise PydqError("as_of must be a datetime or ISO-8601 string.")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
