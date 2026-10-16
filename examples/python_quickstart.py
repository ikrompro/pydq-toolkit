"""In-memory quickstart used by the README.

Run from the repository root after installing the package:

    python examples/python_quickstart.py
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from pydq import Suite, in_range, not_null, referential_integrity, unique


def main() -> int:
    """Run a tiny suite and print a Markdown report."""
    orders = pd.DataFrame(
        {
            "order_id": [1, 2],
            "customer_id": [10, 10],
            "amount": [25.0, 40.0],
        }
    )
    customers = pd.DataFrame({"customer_id": [10, 11]})
    suite = Suite(
        "quickstart",
        [
            not_null("order_id"),
            unique("order_id"),
            in_range("amount", minimum=0, maximum=1000),
            referential_integrity("customer_id", ref="customers", ref_column="customer_id"),
        ],
    )
    result = suite.run(
        orders,
        {"customers": customers},
        as_of=datetime(2026, 10, 16, tzinfo=timezone.utc),
    )
    print(result.to_markdown(), end="")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
