"""Console entry point."""

from __future__ import annotations

import sys

from lpbf_serializer.ui.app import run


def main() -> int:
    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
