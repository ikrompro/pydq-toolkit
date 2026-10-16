# Examples

`customers.csv`, `orders.csv`, and `orders_invalid.csv` are synthetic tables
written by `generate_dataset.py`. The people, emails, and order ids are made
up. `example.com` addresses are documentation addresses, not real inboxes.

`suite.yaml` is a fixed-clock quality gate (`as_of: 2026-10-16T12:00:00Z`).
It passes for `orders.csv` and fails for `orders_invalid.csv`.

```bash
pydq run examples/suite.yaml \
  --data examples/orders.csv \
  --ref customers=examples/customers.csv

pydq run examples/suite.yaml \
  --data examples/orders_invalid.csv \
  --ref customers=examples/customers.csv
```

Regenerate the CSV files from the repository root:

```bash
python examples/generate_dataset.py
```
