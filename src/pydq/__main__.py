"""Allow ``python -m pydq`` to run the CLI."""

from __future__ import annotations

import sys

from pydq.cli import main

if __name__ == "__main__":
    sys.exit(main())
