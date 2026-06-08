"""Where the reqgen config of record lives.

The config is a version-controlled qualification artifact. By project convention
it lives at `reqgen/config/reqgen.json` — i.e. a `config/` folder inside the
reqgen project directory (the first layer of reqgen/, alongside pyproject.toml),
NOT at the repo root next to icdgen/. Baking the convention here means no one has
to remember to type `-c`: the CLI defaults to it, and the (future) UI reads and
writes the same resolved path.

Resolution order for the default config path:
  1. $REQGEN_CONFIG if set (explicit override, e.g. CI or a non-standard tree).
  2. The reqgen project's own `config/reqgen.json`, located relative to this
     file (reqgen/reqgen/paths.py -> up two levels is the reqgen/ project dir).
     This is the canonical home and works regardless of the current directory.
  3. If that project dir can't be determined, fall back to `config/reqgen.json`
     under the current directory.
"""
from __future__ import annotations

import os

CONFIG_DIRNAME = "config"
CONFIG_FILENAME = "reqgen.json"
ENV_VAR = "REQGEN_CONFIG"


def _project_dir() -> str | None:
    """The reqgen/ project directory: parent of the importable package.

    This file is reqgen/reqgen/paths.py; its dir is reqgen/reqgen/ and the
    parent is the reqgen/ project root (which holds pyproject.toml and config/).
    Returns None for an unusual install layout (e.g. a zipped package) where the
    parent isn't a real directory on disk.
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
