"""Compatibility entry point for ``python -m app.server``."""

from .presentation.server import main


if __name__ == "__main__":
    main()
