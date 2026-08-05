"""Default location of the reqgen config file.

The config is a version-controlled qualification artifact. It lives at
`reqgen/config/reqgen.json` (inside the reqgen project dir, alongside
pyproject.toml), not at the repo root next to icdgen/. The CLI and UI both
resolve this path here, so `-c` is only needed for non-standard layouts.

Resolution order:
  1. $REQGEN_CONFIG if set (e.g. CI or a non-standard tree).
  2. `config/reqgen.json` in the reqgen project dir, located relative to this
     file (reqgen/reqgen/paths.py -> up two levels). Works regardless of cwd.
  3. If the project dir can't be determined, `config/reqgen.json` under the
     current directory.
"""
from __future__ import annotations

import os

CONFIG_DIRNAME = "config"
CONFIG_FILENAME = "reqgen.json"
ENV_VAR = "REQGEN_CONFIG"


def _project_dir() -> str | None:
    """The reqgen/ project directory: parent of the importable package.

    This file is reqgen/reqgen/paths.py, so the parent of its dir is the
    project root (holds pyproject.toml and config/). Returns None when that
    parent isn't a real directory on disk (e.g. a zipped install).
    """
    pkg_dir = os.path.dirname(os.path.abspath(__file__))   # reqgen/reqgen
    proj = os.path.dirname(pkg_dir)                         # reqgen
    return proj if os.path.isdir(proj) else None


def default_config_path(start: str | None = None) -> str:
    """Resolve the conventional config path (see module docstring)."""
    env = os.environ.get(ENV_VAR)
    if env:
        return env
    proj = _project_dir()
    if proj is not None:
        return os.path.join(proj, CONFIG_DIRNAME, CONFIG_FILENAME)
    # Fallback: under the current (or given) directory.
    base = os.path.abspath(start or os.getcwd())
    return os.path.join(base, CONFIG_DIRNAME, CONFIG_FILENAME)
