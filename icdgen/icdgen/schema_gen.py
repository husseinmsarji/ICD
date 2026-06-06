"""Derive schema fragments from the field registries.

This module is the bridge from ``fields.py`` to the two validation schemas.
Both the XSD complexTypes and the JSON Schema objects for *signals* and
*interfaces* are GENERATED here from the same ``FieldSpec`` registries, so they
can never drift apart — the historical bug where the XSD and a hand-written
jsonschema disagreed is structurally impossible.

The generation helpers are generic over a registry plus a short ``prefix`` used
to name supporting simpleTypes (e.g. ``Sig`` vs ``If``), so the same code
serves both signal and interface fields. The XSD top-level structure (root,
metadata, revision history, the <signals> child collection, <extensions>) still
lives in schemas/icd-1.0.xsd.template; only the field-driven complexTypes and
enum types are injected at marked insertion points.
"""
from __future__ import annotations

from .fields import (
    BUS_TYPES,
    DAL_LEVELS,
    DIRECTIONS,
    INTERFACE_FIELDS,
    SIGNAL_FIELDS,
    XML_ATTRIBUTE,
    XML_ELEMENT,
    FieldSpec,
)

_XSD_BASE = {
    str: "xs:string",
    float: "xs:double",
    bool: "xs:boolean",
    int: "xs:integer",
}


# ---------------------------------------------------------------------------
# Supporting simpleType names (parameterized by prefix to avoid collisions).
# ---------------------------------------------------------------------------
def _enum_type_name(prefix: str, f: FieldSpec) -> str:
    return f"{prefix}Enum_{f.xml_name}"


def _pattern_type_name(prefix: str, f: FieldSpec) -> str:
    return f"{prefix}Pat_{f.xml_name}"


def _positive_type_name(prefix: str, f: FieldSpec) -> str:
    return f"{prefix}Pos_{f.xml_name}"


def _minlen_type_name(prefix: str, f: FieldSpec) -> str:
    return f"{prefix}Len_{f.xml_name}"


def _xsd_default(f: FieldSpec) -> str:
    if isinstance(f.default, bool):
        return "true" if f.default else "false"
    return str(f.default)


def _xsd_inline_type(prefix: str, f: FieldSpec) -> str:
    """Return a type="..." reference, using a named simpleType when restricted."""
    if f.enum_values() is not None:
        return f'type="{_enum_type_name(prefix, f)}"'
    if f.pattern is not None:
        return f'type="{_pattern_type_name(prefix, f)}"'
    if f.positive:
        return f'type="{_positive_type_name(prefix, f)}"'
    if f.min_length:
        return f'type="{_minlen_type_name(prefix, f)}"'
    return f'type="{_XSD_BASE[f.py_type]}"'


def _xsd_attribute(prefix: str, f: FieldSpec) -> str:
    use = 'use="required"' if f.required else 'use="optional"'
    default = "" if f.default is None else f' default="{_xsd_default(f)}"'
    return (f'      <xs:attribute name="{f.xml_name}" '
            f'{_xsd_inline_type(prefix, f)} {use}{default}/>')


def _xsd_element(prefix: str, f: FieldSpec) -> str:
    min_occurs = "" if f.required else ' minOccurs="0"'
    default = "" if f.default is None else f' default="{_xsd_default(f)}"'
    return (f'      <xs:element name="{f.xml_name}" '
            f'{_xsd_inline_type(prefix, f)}{min_occurs}{default}/>')


def _supporting_simple_types(prefix: str, fields) -> list[str]:
    """Named simpleTypes (enum/pattern/positive/minLength) for a registry."""
    lines: list[str] = []
    for f in fields:
        enum = f.enum_values()
        if enum is not None:
            lines.append(f'  <xs:simpleType name="{_enum_type_name(prefix, f)}">')
            lines.append('    <xs:restriction base="xs:string">')
            for v in enum:
                lines.append(f'      <xs:enumeration value="{v}"/>')
            lines.append('    </xs:restriction>')
            lines.append('  </xs:simpleType>')
        elif f.pattern is not None:
            lines.append(f'  <xs:simpleType name="{_pattern_type_name(prefix, f)}">')
            lines.append('    <xs:restriction base="xs:string">')
            lines.append(f'      <xs:pattern value="{f.pattern}"/>')
            lines.append('    </xs:restriction>')
            lines.append('  </xs:simpleType>')
        elif f.positive:
            lines.append(f'  <xs:simpleType name="{_positive_type_name(prefix, f)}">')
            lines.append('    <xs:restriction base="xs:double">')
            lines.append('      <xs:minExclusive value="0"/>')
            lines.append('    </xs:restriction>')
            lines.append('  </xs:simpleType>')
        elif f.min_length:
            lines.append(f'  <xs:simpleType name="{_minlen_type_name(prefix, f)}">')
            lines.append('    <xs:restriction base="xs:string">')
            lines.append(f'      <xs:minLength value="{f.min_length}"/>')
            lines.append('    </xs:restriction>')
            lines.append('  </xs:simpleType>')
    return lines


def _complex_type(prefix: str, type_name: str, fields,
                  extra_sequence: list[str] | None = None) -> list[str]:
    """Generate a complexType from a field registry.

    ``extra_sequence`` lets a caller append non-field child elements (e.g. the
    <signals> collection on an interface) after the field-derived elements.
    """
    elements = [f for f in fields if f.xml_location == XML_ELEMENT]
    attributes = [f for f in fields if f.xml_location == XML_ATTRIBUTE]
    lines = _supporting_simple_types(prefix, fields)
    lines.append(f'  <xs:complexType name="{type_name}">')
    lines.append('    <xs:sequence>')
    for f in elements:
        lines.append(_xsd_element(prefix, f))
    if extra_sequence:
        lines.extend(extra_sequence)
    lines.append('    </xs:sequence>')
    for f in attributes:
        lines.append(_xsd_attribute(prefix, f))
    lines.append('  </xs:complexType>')
    return lines


def xsd_signal_block() -> str:
    """Generate <signal> complexType + supporting simpleTypes."""
    return "\n".join(_complex_type("Sig", "SignalType", SIGNAL_FIELDS))


def xsd_interface_block() -> str:
    """Generate <interface> complexType + supporting simpleTypes.

    The <signals> child collection is appended structurally (it is not a scalar
    field in the registry).
    """
    extra = ['      <xs:element name="packets" type="PacketsType"/>']
    return "\n".join(_complex_type("If", "InterfaceType", INTERFACE_FIELDS, extra))


def _json_object(fields) -> dict:
    """Generic JSON Schema object generator for a field registry."""
    props: dict = {}
    required: list[str] = []
    for f in fields:
        spec: dict = {}
        if f.enum_values() is not None:
            spec["enum"] = list(f.enum_values())
        elif f.py_type is str:
            spec["type"] = "string"
            if f.pattern:
                spec["pattern"] = f"^{f.pattern}$"
            if f.min_length:
                spec["minLength"] = f.min_length
        elif f.py_type is float:
            spec["type"] = "number"
            if f.positive:
                spec["exclusiveMinimum"] = 0
        elif f.py_type is int:
            spec["type"] = "integer"
            if f.positive:
                spec["exclusiveMinimum"] = 0
        elif f.py_type is bool:
            spec["type"] = "boolean"
        props[f.json_name] = spec
        if f.required:
            required.append(f.json_name)
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": props,
    }


def json_signal_schema() -> dict:
    """JSON Schema object for a signal, generated from the registry."""
    return _json_object(SIGNAL_FIELDS)


def json_interface_schema() -> dict:
    """JSON Schema object for an interface (without the signals array, which the
    caller injects so it can reference the signal schema)."""
    return _json_object(INTERFACE_FIELDS)


# ---------------------------------------------------------------------------
# Interface-level enum simpleTypes + full XSD assembly.
# ---------------------------------------------------------------------------
def _enum_simple_type(name: str, values) -> str:
    lines = [f'  <xs:simpleType name="{name}">',
             '    <xs:restriction base="xs:string">']
    lines += [f'      <xs:enumeration value="{v}"/>' for v in values]
    lines += ['    </xs:restriction>', '  </xs:simpleType>']
    return "\n".join(lines)


def xsd_enum_types() -> str:
    """DirectionType kept for namespace stability (Bus/DAL are now generated
    inline by the interface block as IfEnum_* types)."""
    return _enum_simple_type("DirectionType", DIRECTIONS)


def assemble_xsd(template_text: str) -> str:
    """Inject generated signal + interface + enum blocks into the template."""
    out = template_text.replace("  <!-- @SIGNAL_TYPES@ -->", xsd_signal_block())
    out = out.replace("  <!-- @INTERFACE_TYPE@ -->", xsd_interface_block())
    out = out.replace("  <!-- @ENUM_TYPES@ -->", xsd_enum_types())
    return out
