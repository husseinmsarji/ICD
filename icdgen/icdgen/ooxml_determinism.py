"""Make OOXML (.docx/.xlsx) archives byte-deterministic.

OOXML files are ZIP archives. python-docx and openpyxl stamp each ZIP entry
with the current wall-clock time, may vary entry ordering, and (openpyxl)
overwrite the core-properties <dcterms:modified> with the save time even when
it was pinned beforehand. This utility rewrites an archive with a fixed entry
timestamp, stable entry order, and a normalized core.xml modified date so two
runs over identical input are byte-identical.
"""
from __future__ import annotations

import re
import zipfile

# Fixed DOS timestamp (1980-01-01 00:00:00, the ZIP epoch).
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)
_FIXED_W3CDTF = "2000-01-01T00:00:00Z"

_MODIFIED_RE = re.compile(
    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")
_CREATED_RE = re.compile(
    rb"(<dcterms:created[^>]*>)[^<]*(</dcterms:created>)")


def _normalize_core_xml(data: bytes) -> bytes:
    repl = _FIXED_W3CDTF.encode("ascii")
    data = _MODIFIED_RE.sub(rb"\g<1>" + repl + rb"\g<2>", data)
    data = _CREATED_RE.sub(rb"\g<1>" + repl + rb"\g<2>", data)
    return data


def normalize(path: str) -> None:
    with zipfile.ZipFile(path, "r") as zin:
        infos = zin.infolist()
        items = []
        for i in infos:
            data = zin.read(i.filename)
            if i.filename == "docProps/core.xml":
                data = _normalize_core_xml(data)
            items.append((i.filename, data))
    # Stable, content-independent ordering by archive name.
    items.sort(key=lambda kv: kv[0])
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in items:
            zi = zipfile.ZipInfo(filename=name, date_time=_FIXED_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zout.writestr(zi, data)
