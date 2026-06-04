"""Module entry point for ``python -m zsper``."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate module execution to the public CLI."""
    try:
        from zsper.cli import app
    except ModuleNotFoundError as exc:
        if exc.name == "zsper.cli":
            print(
                "zsper CLI is not implemented yet; run the console script after FND-004.",
                file=sys.stderr,
            )
            return 1
        raise

    return app(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
