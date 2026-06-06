"""Entry point: enables `python -m icdgen` and serves as the PyInstaller target."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
