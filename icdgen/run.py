"""Standalone launcher for the PyInstaller build.

Uses an absolute import so it works when PyInstaller executes it as the
top-level script (relative imports require a known parent package, which the
frozen __main__ lacks).
"""
import sys

from icdgen.cli import main

if __name__ == "__main__":
    sys.exit(main())
