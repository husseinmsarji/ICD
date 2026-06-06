"""Single source of truth for ICD signal fields.

THE ONE PLACE TO ADD A SIGNAL FIELD.
====================================
Every signal field is declared exactly once, here, as a ``FieldSpec``. The XSD
fragment, the JSON Schema fragment, the editable form column, the API options
payload, the XML serialization, and the parsing logic are all *derived* from
this registry rather than restated. Adding a field is a one-line edit to
``SIGNAL_FIELDS`` below (plus, only if it is a brand-new primitive data type,
an entry in ``DATA_TYPES``).

Why a registry instead of scattered definitions:
  * Before, a new field meant editing 7 files that could silently disagree.
  * The XSD and JSON Schema were two hand-maintained copies of the same rules —
    a latent drift bug. Now both are generated from one description, so they
    cannot diverge.

Determinism: the registry is an ordered tuple. Field order here fixes column
order in every artifact, so output stays byte-stable as long as the order is
unchanged. Appending a new field is safe (it lands last); reordering changes
output and is therefore a deliberate, reviewable act.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Data type catalog: maps each abstract ICD data type to its representations.
# Add a new primitive type here once; struct/bus generation picks it up.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DataTypeSpec:
    name: str          # abstract name used in the ICD (e.g. "float32")
    c_type: str        # C/C++ type (e.g. "float")
    simulink_type: str  # MATLAB/Simulink class (e.g. "single")


DATA_TYPES: tuple[DataTypeSpec, ...] = (
    DataTypeSpec("bool", "uint8_t", "boolean"),
    DataTypeSpec("uint8", "uint8_t", "uint8"),
    DataTypeSpec("int8", "int8_t", "int8"),
    DataTypeSpec("uint16", "uint16_t", "uint16"),
    DataTypeSpec("int16", "int16_t", "int16"),
    DataTypeSpec("uint32", "uint32_t", "uint32"),
    DataTypeSpec("int32", "int32_t", "int32"),
    DataTypeSpec("uint64", "uint64_t", "uint64"),
    DataTypeSpec("int64", "int64_t", "int64"),
    DataTypeSpec("float32", "float", "single"),
    DataTypeSpec("float64", "double", "double"),
)

DATA_TYPE_NAMES: tuple[str, ...] = tuple(d.name for d in DATA_TYPES)
C_TYPE_MAP: dict[str, str] = {d.name: d.c_type for d in DATA_TYPES}
SIMULINK_TYPE_MAP: dict[str, str] = {d.name: d.simulink_type for d in DATA_TYPES}

# Interface-level enumerations. Declared once here; consumed by the XSD
# template assembly, the JSON Schema, the API /meta/options endpoint, and UI.
BUS_TYPES: tuple[str, ...] = (
    "ARINC429", "MIL-STD-1553", "ARINC664", "CAN", "DISCRETE", "ANALOG",
)
DAL_LEVELS: tuple[str, ...] = ("A", "B", "C", "D", "E")
DIRECTIONS: tuple[str, ...] = ("TX", "RX")


# ---------------------------------------------------------------------------
# How a field is carried in XML: as an attribute on <signal> or a child element.
# (Identity-ish fields are attributes in the existing schema; physical
# properties are elements. Preserving that split keeps output byte-identical.)
# ---------------------------------------------------------------------------
XML_ATTRIBUTE = "attribute"
XML_ELEMENT = "element"


@dataclass(frozen=True)
class FieldSpec:
    """Complete description of one signal field, in one place."""
    # Identity
    name: str                       # Python/JSON key, e.g. "range_min" (snake)
    xml_name: str                   # XML name, e.g. "rangeMin" (camel)
    json_name: str                  # JSON/DTO key, e.g. "rangeMin" (camel)
    label: str                      # human label for the UI column header

    # Kind / type
    py_type: type                   # str | float | bool
    xml_location: str               # XML_ATTRIBUTE | XML_ELEMENT
    required: bool                  # required in schema?
    default: Any = None             # default when optional/absent
    enum: Optional[tuple[str, ...]] = None   # allowed values, if enumerated
    enum_source: Optional[str] = None        # name of a dynamic enum (data types)

    # Validation hints (used to build XSD/JSON Schema facets)
    positive: bool = False          # value must be > 0
    pattern: Optional[str] = None   # regex (XSD + JSON Schema)
    min_length: Optional[int] = None

    # UI hints
    ui_width: str = "auto"          # "auto" | "narrow" | "tiny"
    ui_numeric: bool = False        # render a number input

    # Serialization: only emit element when this predicate is true (keeps
    # optional elements out of XML unless they carry meaningful values, which
    # the existing serializer relied on for byte-stable output).
    emit_if: Optional[Callable[[Any], bool]] = None

    def enum_values(self) -> Optional[tuple[str, ...]]:
        if self.enum_source == "data_types":
            return DATA_TYPE_NAMES
        return self.enum


# ---------------------------------------------------------------------------
# THE REGISTRY. Order = column order in every artifact. Append to extend.
# ---------------------------------------------------------------------------
SIGNAL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="name", xml_name="name", json_name="name", label="Name",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True,
        pattern=r"[A-Za-z_][A-Za-z0-9_]*", ui_width="auto",
    ),
    FieldSpec(
        name="data_type", xml_name="dataType", json_name="dataType", label="Type",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True,
        enum_source="data_types", ui_width="narrow",
    ),
    FieldSpec(
        name="direction", xml_name="direction", json_name="direction", label="Dir",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True,
        enum=("TX", "RX"), ui_width="tiny",
    ),
    FieldSpec(
        name="optional", xml_name="optional", json_name="optional", label="Opt",
        py_type=bool, xml_location=XML_ATTRIBUTE, required=False, default=False,
        # optional attr emitted only when true (matches original serializer).
        emit_if=lambda v: v is True,
    ),
    FieldSpec(
        name="units", xml_name="units", json_name="units", label="Units",
        py_type=str, xml_location=XML_ELEMENT, required=True, default="",
        ui_width="tiny",
    ),
    FieldSpec(
        name="range_min", xml_name="rangeMin", json_name="rangeMin", label="Min",
        py_type=float, xml_location=XML_ELEMENT, required=True, default=0.0,
        ui_width="tiny", ui_numeric=True,
    ),
    FieldSpec(
        name="range_max", xml_name="rangeMax", json_name="rangeMax", label="Max",
        py_type=float, xml_location=XML_ELEMENT, required=True, default=0.0,
        ui_width="tiny", ui_numeric=True,
    ),
    FieldSpec(
        name="update_rate_hz", xml_name="updateRateHz", json_name="updateRateHz",
        label="Rate Hz", py_type=float, xml_location=XML_ELEMENT, required=True,
        default=1.0, positive=True, ui_width="tiny", ui_numeric=True,
    ),
    FieldSpec(
        name="scaling", xml_name="scaling", json_name="scaling", label="Scale",
        py_type=float, xml_location=XML_ELEMENT, required=False, default=1.0,
        ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v != 1.0,
    ),
    FieldSpec(
        name="offset", xml_name="offset", json_name="offset", label="Offset",
        py_type=float, xml_location=XML_ELEMENT, required=False, default=0.0,
        ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v != 0.0,
    ),
    FieldSpec(
        name="encoding", xml_name="encoding", json_name="encoding", label="Encoding",
        py_type=str, xml_location=XML_ELEMENT, required=False, default=None,
        ui_width="tiny",
        emit_if=lambda v: bool(v),
    ),
    FieldSpec(
        name="description", xml_name="description", json_name="description",
        label="Description", py_type=str, xml_location=XML_ELEMENT, required=False,
        default=None, ui_width="auto",
        emit_if=lambda v: bool(v),
    ),
)

# Convenience indexes.
SIGNAL_FIELDS_BY_NAME: dict[str, FieldSpec] = {f.name: f for f in SIGNAL_FIELDS}

# ---------------------------------------------------------------------------
# INTERFACE-LEVEL field registry. Mirrors SIGNAL_FIELDS for the <interface>
# element's scalar fields. The child <signals> collection is NOT a scalar field
# and is handled structurally (it is always present and required), so it is not
# listed here. Order = element order in the XSD sequence + form field order.
# ---------------------------------------------------------------------------
INTERFACE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="id", xml_name="id", json_name="id", label="Interface ID",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True,
        pattern=r"[A-Za-z0-9_\-]+", ui_width="auto",
    ),
    FieldSpec(
        name="bus_type", xml_name="busType", json_name="busType", label="Bus Type",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True,
        enum=BUS_TYPES, ui_width="narrow",
    ),
    FieldSpec(
        name="dal", xml_name="dal", json_name="dal", label="DAL",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True,
        enum=DAL_LEVELS, ui_width="tiny",
    ),
    FieldSpec(
        name="name", xml_name="name", json_name="name", label="Name",
        py_type=str, xml_location=XML_ELEMENT, required=True, min_length=1,
        ui_width="auto",
    ),
    FieldSpec(
        name="source_lru", xml_name="sourceLru", json_name="sourceLru",
        label="Source LRU", py_type=str, xml_location=XML_ELEMENT, required=True,
        min_length=1, ui_width="auto",
    ),
    FieldSpec(
        name="destination_lru", xml_name="destinationLru",
        json_name="destinationLru", label="Destination LRU", py_type=str,
        xml_location=XML_ELEMENT, required=True, min_length=1, ui_width="auto",
    ),
    FieldSpec(
        name="owning_document", xml_name="owningDocument",
        json_name="owningDocument", label="Owning Document", py_type=str,
        xml_location=XML_ELEMENT, required=True, min_length=1, ui_width="auto",
    ),
    FieldSpec(
        name="description", xml_name="description", json_name="description",
        label="Description", py_type=str, xml_location=XML_ELEMENT,
        required=False, default=None, ui_width="auto",
        emit_if=lambda v: bool(v),
    ),
)

INTERFACE_FIELDS_BY_NAME: dict[str, FieldSpec] = {f.name: f for f in INTERFACE_FIELDS}



def signal_field_order() -> tuple[str, ...]:
    """Field names in canonical order (drives column order everywhere)."""
    return tuple(f.name for f in SIGNAL_FIELDS)


# ---------------------------------------------------------------------------
# UI / API export: a JSON-serializable descriptor of the signal field set, so
# the frontend builds its editable table columns dynamically from the registry.
# Adding a field here makes a new column appear with no frontend code change.
# ---------------------------------------------------------------------------
def _fields_descriptor(fields) -> list[dict]:
    out = []
    for f in fields:
        out.append({
            "name": f.name,
            "jsonName": f.json_name,
            "label": f.label,
            "kind": "enum" if f.enum_values() is not None else (
                "bool" if f.py_type is bool else
                "number" if f.py_type is float else "text"),
            "enum": list(f.enum_values()) if f.enum_values() is not None else None,
            "required": f.required,
            "uiWidth": f.ui_width,
        })
    return out


def signal_fields_descriptor() -> list[dict]:
    return _fields_descriptor(SIGNAL_FIELDS)


def interface_fields_descriptor() -> list[dict]:
    return _fields_descriptor(INTERFACE_FIELDS)
