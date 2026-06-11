"""Resolve bundled data files (schema, templates) at runtime.

Works both from a source checkout and from a PyInstaller onefile bundle, where
data files are unpacked under sys._MEIPASS. All access to the XSD and Jinja
templates must go through here so the standalone executable can find them.

The XSD template is package data: it lives at icdgen/schemas/icd-1.0.xsd.template
(inside the importable package), so a single copy serves source checkouts, pip
wheels, and PyInstaller bundles alike. It cannot drift.

TEMPLATE OVERRIDE (modularity): a program may supply its own Jinja templates
(e.g. a house-style header.h.j2) by setting $ICDGEN_TEMPLATE_DIR. Because an
overridden template is a real tool input that changes artifact bytes, the
template set is hashable via template_manifest(); the CLI records those hashes
(plus the compiled-XSD hash) in run.log so every invocation's full input set is
auditable. Identical ICD + identical templates => identical artifacts; a
template swap is visible in the provenance record instead of silent.
"""
from __future__ import annotations

import hashlib
import os
import sys

ENV_TEMPLATE_DIR = "ICDGEN_TEMPLATE_DIR"


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


def compiled_xsd_hash() -> str:
    """SHA-256 of the fully assembled XSD text. Provenance anchor for the
    schema the input was validated against."""
    return hashlib.sha256(compiled_xsd().encode("utf-8")).hexdigest()


def template_dir() -> str:
    """Directory holding the Jinja2 templates (header.h.j2, simulink_bus.m.j2).

    Resolution order:
      1. $ICDGEN_TEMPLATE_DIR if set and existing (program-supplied templates;
         their hashes are recorded in run.log via template_manifest()).
      2. Next to this module (source checkout / pip wheel).
      3. The PyInstaller datas layout (sys._MEIPASS/icdgen/templates) when
         frozen.
    """
    env = os.environ.get(ENV_TEMPLATE_DIR)
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, "templates")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "icdgen", "templates"))
    return _first_existing(*candidates)


def template_manifest() -> dict[str, str]:
    """{template filename: SHA-256} for every *.j2 in the resolved template
    dir, sorted by name. Recorded in run.log so an overridden template set is
    a traceable, auditable input rather than a silent substitution."""
    d = template_dir()
    out: dict[str, str] = {}
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".j2"):
            continue
        h = hashlib.sha256()
        with open(os.path.join(d, name), "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        out[name] = h.hexdigest()
    return out