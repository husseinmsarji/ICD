"""Resolve bundled data files (schema, templates) at runtime.

Works both from a source checkout and from a PyInstaller onefile bundle, where
data files are unpacked under sys._MEIPASS. All access to the XSD and Jinja
templates must go through here so the standalone executable can find them.
"""
from __future__ import annotations

import os
import sys


def _base_dir() -> str:
    # PyInstaller sets _MEIPASS to the temp extraction dir.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    # Source layout: this file lives in icdgen/, project root is its parent.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _first_existing(*candidates: str) -> str:
    for c in candidates:
        if os.path.exists(c):
            return c
    # Fall back to the first candidate so the error message is meaningful.
    return candidates[0]


def xsd_template_path() -> str:
    """Path to the XSD TEMPLATE (with @SIGNAL_TYPES@/@ENUM_TYPES@ markers).

    The signal and interface-enum portions are injected from the field registry
    at load time (see schema_gen.assemble_xsd), so the schema can never drift
    from the registry.
    """
    base = _base_dir()
    here = os.path.dirname(os.path.abspath(__file__))
    return _first_existing(
        os.path.join(base, "schemas", "icd-1.0.xsd.template"),
        os.path.join(here, "schemas", "icd-1.0.xsd.template"),
    )


def compiled_xsd() -> str:
    """Return the fully assembled XSD text (template + generated fragments)."""
    from .schema_gen import assemble_xsd
    with open(xsd_template_path(), encoding="utf-8") as fh:
        return assemble_xsd(fh.read())


def template_dir() -> str:
    base = _base_dir()
    here = os.path.dirname(os.path.abspath(__file__))
    return _first_existing(
        os.path.join(base, "icdgen", "templates"),  # PyInstaller datas layout
        os.path.join(here, "templates"),             # source / installed package
    )
