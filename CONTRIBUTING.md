# Contributing

Thanks for helping improve pydq-toolkit. The library is a small, typed Python
package: checks stay declarative, reports stay structured, and a failing check
is a result rather than an exception.

## Setup

Python 3.10, 3.11, or 3.12 is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pre-commit install
```

## Checks

```bash
ruff check .
ruff format --check .
mypy src
pytest
```

`pytest` fails if branch coverage of `pydq` drops below 90%.

## Pull requests

- Add or update tests for behavior changes.
- Keep public functions typed and documented.
- Do not add data, names, or code from private systems. Example tables stay
  synthetic.
- Update `CHANGELOG.md` under the next version when the change is user-visible.

## Reporting issues

Include the suite snippet, a tiny synthetic frame, the Python version, and the
report JSON. Please do not attach production extracts.
