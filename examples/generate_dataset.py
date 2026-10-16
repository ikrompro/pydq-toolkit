"""Write the synthetic CSV files used by the examples and tests.

The rows are fictional retail orders. Nothing here is a real customer, and the
script does not download data. Run it from the repository root:

    python examples/generate_dataset.py
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CUSTOMERS = [
    ("customer_id", "name", "email", "country", "created_at"),
    (1, "Ava Quinn", "ava.quinn@example.com", "US", "2024-01-15T10:00:00Z"),
    (2, "Noah Patel", "noah.patel@example.com", "CA", "2024-03-02T15:30:00Z"),
    (3, "Mia Chen", "mia.chen@example.com", "GB", "2024-06-21T08:05:00Z"),
    (4, "Leo Alvarez", "leo.alvarez@example.com", "MX", "2024-11-09T19:45:00Z"),
    (5, "Sofia Rossi", "sofia.rossi@example.com", "IT", "2025-02-14T12:20:00Z"),
    (6, "Jonah Berg", "jonah.berg@example.com", "SE", "2025-08-30T07:10:00Z"),
]

ORDERS = [
    ("order_id", "customer_id", "amount", "status", "email", "ordered_at"),
    (1001, 1, "42.50", "shipped", "buyer1@example.com", "2026-10-15T18:00:00Z"),
    (1002, 2, "15.00", "pending", "buyer2@example.com", "2026-10-16T09:30:00Z"),
    (1003, 3, "128.75", "delivered", "buyer3@example.com", "2026-10-15T12:15:00Z"),
    (1004, 4, "9.99", "shipped", "buyer4@example.com", "2026-10-16T01:05:00Z"),
    (1005, 5, "640.00", "pending", "buyer5@example.com", "2026-10-16T11:45:00Z"),
    (1006, 6, "88.20", "delivered", "buyer6@example.com", "2026-10-14T13:00:00Z"),
    (1007, 1, "250.00", "shipped", "ava.quinn@example.com", "2026-10-16T08:20:00Z"),
    (1008, 2, "33.33", "pending", "noah.patel@example.com", "2026-10-15T22:40:00Z"),
    (1009, 3, "17.10", "delivered", "mia.chen@example.com", "2026-10-16T06:00:00Z"),
    (1010, 4, "499.95", "shipped", "leo.alvarez@example.com", "2026-10-15T16:16:00Z"),
    (1011, 5, "72.00", "pending", "sofia.rossi@example.com", "2026-10-16T10:10:00Z"),
    (1012, 6, "5.50", "delivered", "jonah.berg@example.com", "2026-10-14T20:30:00Z"),
]

ORDERS_INVALID = [
    ("order_id", "customer_id", "amount", "status", "email", "ordered_at"),
    (2001, 1, "10.00", "shipped", "ok@example.com", "2020-06-01T09:00:00Z"),
    (2001, 2, "11.00", "pending", "ok2@example.com", "2020-06-01T09:05:00Z"),
    (2003, 999, "12.50", "delivered", "ok3@example.com", "2020-06-01T09:10:00Z"),
    (2004, 3, "-5.00", "shipped", "ok4@example.com", "2020-06-01T09:15:00Z"),
    (2005, 4, "20.00", "refunded", "ok5@example.com", "2020-06-01T09:20:00Z"),
    (2006, 5, "30.00", "pending", "not-an-email", "2020-06-01T09:25:00Z"),
    (2007, 6, "40.00", "pending", "", "2020-06-01T09:30:00Z"),
    (2008, 1, "50.00", "delivered", "ok8@example.com", "2020-01-01T00:00:00Z"),
    (2009, 2, "18.00", "shipped", "clean@example.com", "2020-06-02T11:00:00Z"),
]


def write_csv(path: Path, rows: list[tuple[object, ...]]) -> None:
    """Write ``rows`` as UTF-8 CSV with a trailing newline."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)


def generate(directory: Path) -> None:
    """Write ``customers.csv``, ``orders.csv``, and ``orders_invalid.csv``."""
    directory.mkdir(parents=True, exist_ok=True)
    write_csv(directory / "customers.csv", CUSTOMERS)
    write_csv(directory / "orders.csv", ORDERS)
    write_csv(directory / "orders_invalid.csv", ORDERS_INVALID)


def main() -> None:
    """Generate the example files next to this script."""
    generate(ROOT)


if __name__ == "__main__":
    main()
