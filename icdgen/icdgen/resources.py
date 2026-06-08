"""Resolve bundled data files (schema, templates) at runtime.

Works both from a source checkout and from a PyInstaller onefile bundle, where
data files are unpacked under sys._MEIPASS. All access to the XSD and Jinja
templates must go through here so the standalone executable can find them.

The XSD template is package data: it lives at icdgen/schemas/icd-1.0.xsd.template
(inside the importable package), so a single copy serves source checkouts, pip
wheels, and PyInstaller bundles alike — it cannot drift.
"""
from __future__ import annotations

import os
import sys


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

    The template is package data shipped at icdgen/schemas/icd-1.0.xsd.template.
    One physical copy serves every layout: a source checkout and a pip-installed
    wheel both resolve it next to this module; a PyInstaller bundle unpacks it
    under sys._MEIPASS/icdgen/schemas/ (see icdgen.spec datas).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, "schemas", "icd-1.0.xsd.template")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(
            os.path.join(meipass, "icdgen", "schemas", "icd-1.0.xsd.template"))
    return _first_existing(*candidates)


def compiled_xsd() -> str:
    """Return the fully assembled XSD text (template + generated fragments)."""
    from .schema_gen import assemble_xsd
    with open(xsd_template_path(), encoding="utf-8") as fh:
        return assemble_xsd(fh.read())


def template_dir() -> str:
    """Directory holding the Jinja2 templates (header.h.j2, simulink_bus.m.j2).

    Resolves next to this module for source/wheel installs, and under the
    PyInstaller datas layout (sys._MEIPASS/icdgen/templates) when frozen.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, "templates")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "icdgen", "templates"))
    return _first_existing(*candidates)