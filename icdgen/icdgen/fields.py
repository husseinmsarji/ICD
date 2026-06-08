"""Single source of truth for ICD signal fields.

THE ONE PLACE TO ADD A SIGNAL FIELD.
====================================
Every signal field is declared exactly once, here, as a ``FieldSpec``. The XSD
fragment, the JSON Schema fragment, the editable form column, the API options
payload, the XML serialization, and the parsing logic are all *derived* from
this registry rather than restated.

Why a registry instead of scattered definitions:
  * Before, a new field meant editing 7 files that could silently disagree.
  * The XSD and JSON Schema were two hand-maintained copies of the same rules —
    a latent drift bug. Now both are generated from one description.

Determinism: the registry is an ordered tuple. Field order here fixes column
order in every artifact. Appending a new field is safe (it lands last);
reordering changes output and is therefore a deliberate, reviewable act.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class DataTypeSpec:
    name: str
    c_type: str
    simulink_type: str


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
    DataTypeSpec("enum", "int32_t", "int32"),
)

DATA_TYPE_NAMES: tuple[str, ...] = tuple(d.name for d in DATA_TYPES)
C_TYPE_MAP: dict[str, str] = {d.name: d.c_type for d in DATA_TYPES}
SIMULINK_TYPE_MAP: dict[str, str] = {d.name: d.simulink_type for d in DATA_TYPES}

# Interface-level suggestion lists. BUS_TYPES is now only a *suggestion* set for
# the UI (bus type is freeform); DAL is still an enforced enum.
BUS_TYPES: tuple[str, ...] = (
    "ARINC429", "MIL-STD-1553", "ARINC664", "CAN", "DISCRETE", "ANALOG",
)
DAL_LEVELS: tuple[str, ...] = ("A", "B", "C", "D", "E")
DIRECTIONS: tuple[str, ...] = ("TX", "RX")


XML_ATTRIBUTE = "attribute"
XML_ELEMENT = "element"


@dataclass(frozen=True)
class FieldSpec:
    """Complete description of one field, in one place."""
    name: str
    xml_name: str
    json_name: str
    label: str

    py_type: type                   # str | float | int | bool
    xml_location: str               # XML_ATTRIBUTE | XML_ELEMENT
    required: bool
    default: Any = None
    enum: Optional[tuple[str, ...]] = None
    enum_source: Optional[str] = None        # "data_types" for dynamic

    # Validation hints (used to build XSD/JSON Schema facets)
    positive: bool = False                    # value must be > 0 (exclusive)
    min_inclusive: Optional[float] = None     # value must be >= this
    pattern: Optional[str] = None             # regex (XSD + JSON Schema)
    min_length: Optional[int] = None

    # UI hints
    ui_width: str = "auto"
    ui_numeric: bool = False
    suggestions: Optional[tuple[str, ...]] = None  # freeform autocomplete list

    # Serialization predicate: only emit when this returns True.
    emit_if: Optional[Callable[[Any], bool]] = None

    def enum_values(self) -> Optional[tuple[str, ...]]:
        if self.enum_source == "data_types":
            return DATA_TYPE_NAMES
        return self.enum


# ---------------------------------------------------------------------------
# THE SIGNAL REGISTRY. Order = column order in every artifact.
#
# Permissive-by-design (v1.5.0) so partially-complete ICDs can be uploaded and
# finished in the tool. Fields that are blank/absent on import produce non-fatal
# WARNINGS (see loader._semantic_checks), not errors.
# ---------------------------------------------------------------------------
SIGNAL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        # Relaxed pattern: allow hyphen, hash, dot, etc. so draft ICDs import.
        # A name that is not a valid C identifier still loads but raises a
        # non-fatal WARNING (it cannot become a C struct field / macro verbatim).
        name="name", xml_name="name", json_name="name", label="Signal Name",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True,
        pattern="[^\\s\x22\x27<>]+", ui_width="auto",
    ),
    FieldSpec(
        name="description", xml_name="description", json_name="description",
        label="Description", py_type=str, xml_location=XML_ELEMENT, required=False,
        default=None, ui_width="auto",
        emit_if=lambda v: bool(v),
    ),
    FieldSpec(
        # Optional so an in-progress signal can have a blank type. A blank type
        # cannot map to a real C/Simulink type, so it raises a non-fatal WARNING
        # and the generated header uses a placeholder.
        name="signal_type", xml_name="signalType", json_name="signalType",
        label="Signal Type", py_type=str, xml_location=XML_ATTRIBUTE,
        required=False, default="", enum_source="data_types", ui_width="narrow",
    ),
    FieldSpec(
        # Optional + non-negative (>= 0). Blank allowed for unknown rates;
        # negatives are rejected by the schema.
        name="update_rate_hz", xml_name="updateRateHz", json_name="updateRateHz",
        label="Rate (Hz)", py_type=float, xml_location=XML_ELEMENT,
        required=False, default=None, min_inclusive=0.0,
        ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v is not None,
    ),
    FieldSpec(
        name="units", xml_name="units", json_name="units", label="Units",
        py_type=str, xml_location=XML_ELEMENT, required=True, default="",
        ui_width="tiny",
    ),
    FieldSpec(
        name="data_bits", xml_name="dataBits", json_name="dataBits",
        label="Data Bits", py_type=int, xml_location=XML_ELEMENT, required=False,
        default=None, ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v is not None,
    ),
    FieldSpec(
        name="xmit_bits", xml_name="xmitBits", json_name="xmitBits",
        label="Xmit Bits", py_type=int, xml_location=XML_ELEMENT, required=False,
        default=None, ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v is not None,
    ),
    FieldSpec(
        name="xmit_bytes", xml_name="xmitBytes", json_name="xmitBytes",
        label="Xmit Bytes", py_type=int, xml_location=XML_ELEMENT, required=False,
        default=None, ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v is not None,
    ),
    FieldSpec(
        name="scaling", xml_name="scaling", json_name="scaling", label="Scale",
        py_type=float, xml_location=XML_ELEMENT, required=False, default=1.0,
        ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v != 1.0,
    ),
    FieldSpec(
        name="definition", xml_name="definition", json_name="definition",
        label="Definition", py_type=str, xml_location=XML_ELEMENT, required=False,
        default=None, ui_width="auto",
        emit_if=lambda v: bool(v),
    ),
    FieldSpec(
        name="range_min", xml_name="rangeMin", json_name="rangeMin",
        label="Range Min", py_type=float, xml_location=XML_ELEMENT,
        required=False, default=None, ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v is not None,
    ),
    FieldSpec(
        name="range_max", xml_name="rangeMax", json_name="rangeMax",
        label="Range Max", py_type=float, xml_location=XML_ELEMENT,
        required=False, default=None, ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v is not None,
    ),
    FieldSpec(
        name="offset", xml_name="offset", json_name="offset", label="Offset",
        py_type=float, xml_location=XML_ELEMENT, required=False, default=0.0,
        ui_width="tiny", ui_numeric=True,
        emit_if=lambda v: v != 0.0,
    ),
    FieldSpec(
        # Freeform change-control ticket that last touched this signal (e.g. a
        # PR/Jira id). Optional in the schema; a non-fatal WARNING is raised by
        # loader._semantic_checks when a signal has no ticket and the ICD
        # revision is not the initial "A". Emitted only when non-empty.
        name="pr_ticket", xml_name="prTicket", json_name="prTicket",
        label="PR Ticket", py_type=str, xml_location=XML_ELEMENT, required=False,
        default=None, ui_width="auto",
        emit_if=lambda v: bool(v),
    ),
)

SIGNAL_FIELDS_BY_NAME: dict[str, FieldSpec] = {f.name: f for f in SIGNAL_FIELDS}


# ---------------------------------------------------------------------------
# INTERFACE-LEVEL field registry. The child <packets> collection is NOT a
# scalar field and is handled structurally.
# ---------------------------------------------------------------------------
INTERFACE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="id", xml_name="id", json_name="id", label="Interface ID",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True,
        pattern=r"[A-Za-z0-9_\-]+", ui_width="auto",
    ),
    FieldSpec(
        # Freeform: any non-empty bus name is allowed (not restricted to the
        # BUS_TYPES suggestion list). BUS_TYPES is served to the UI as
        # autocomplete suggestions via the descriptor.
        name="bus_type", xml_name="busType", json_name="busType", label="Bus Type",
        py_type=str, xml_location=XML_ATTRIBUTE, required=True, min_length=1,
        ui_width="narrow", suggestions=BUS_TYPES,
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
    return tuple(f.name for f in SIGNAL_FIELDS)


# ---------------------------------------------------------------------------
# UI / API descriptor: JSON-serializable description of a field set, consumed
# by the React form so columns/inputs are built dynamically from the registry.
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
                "number" if f.py_type in (float, int) else "text"),
            "enum": list(f.enum_values()) if f.enum_values() is not None else None,
            "suggestions": list(f.suggestions) if f.suggestions else None,
            "required": f.required,
            "uiWidth": f.ui_width,
        })
    return out


def signal_fields_descriptor() -> list[dict]:
    return _fields_descriptor(SIGNAL_FIELDS)


def interface_fields_descriptor() -> list[dict]:
    return _fields_descriptor(INTERFACE_FIELDS)
