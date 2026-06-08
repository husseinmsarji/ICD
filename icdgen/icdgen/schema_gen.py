"""Derive schema fragments from the field registries.

Both the XSD complexTypes and the JSON Schema objects for *signals* and
*interfaces* are GENERATED here from the same ``FieldSpec`` registries, so they
can never drift apart. Generation helpers are generic over a registry plus a
short ``prefix`` used to name supporting simpleTypes (``Sig`` vs ``If``).
"""
from __future__ import annotations

from xml.sax.saxutils import quoteattr

from .fields import (
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


# ---- supporting simpleType names (parameterized by prefix) ----
def _enum_type_name(prefix: str, f: FieldSpec) -> str:
    return f"{prefix}Enum_{f.xml_name}"


def _pattern_type_name(prefix: str, f: FieldSpec) -> str:
    return f"{prefix}Pat_{f.xml_name}"


def _positive_type_name(prefix: str, f: FieldSpec) -> str:
    return f"{prefix}Pos_{f.xml_name}"


def _mininc_type_name(prefix: str, f: FieldSpec) -> str:
    return f"{prefix}Inc_{f.xml_name}"


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
    if f.min_inclusive is not None:
        return f'type="{_mininc_type_name(prefix, f)}"'
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
    """Named simpleTypes (enum/pattern/positive/min_inclusive/min_length)."""
    lines: list[str] = []
    for f in fields:
        enum = f.enum_values()
        if enum is not None:
            vals = list(enum)
            if not f.required and "" not in vals:
                vals = vals + [""]  # allow blank for in-progress optional enums
            lines.append(f'  <xs:simpleType name="{_enum_type_name(prefix, f)}">')
            lines.append('    <xs:restriction base="xs:string">')
            for v in vals:
                lines.append(f'      <xs:enumeration value="{v}"/>')
            lines.append('    </xs:restriction>')
            lines.append('  </xs:simpleType>')
        elif f.pattern is not None:
            pat_attr = quoteattr(f.pattern)  # safely quotes + escapes
            lines.append(f'  <xs:simpleType name="{_pattern_type_name(prefix, f)}">')
            lines.append('    <xs:restriction base="xs:string">')
            lines.append(f'      <xs:pattern value={pat_attr}/>')
            lines.append('    </xs:restriction>')
            lines.append('  </xs:simpleType>')
        elif f.positive:
            lines.append(f'  <xs:simpleType name="{_positive_type_name(prefix, f)}">')
            lines.append('    <xs:restriction base="xs:double">')
            lines.append('      <xs:minExclusive value="0"/>')
            lines.append('    </xs:restriction>')
            lines.append('  </xs:simpleType>')
        elif f.min_inclusive is not None:
            lines.append(f'  <xs:simpleType name="{_mininc_type_name(prefix, f)}">')
            lines.append('    <xs:restriction base="xs:double">')
            lines.append(f'      <xs:minInclusive value="{f.min_inclusive}"/>')
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
    return "\n".join(_complex_type("Sig", "SignalType", SIGNAL_FIELDS))


def xsd_interface_block() -> str:
    extra = ['      <xs:element name="packets" type="PacketsType"/>']
    return "\n".join(_complex_type("If", "InterfaceType", INTERFACE_FIELDS, extra))


def _json_object(fields) -> dict:
    props: dict = {}
    required: list[str] = []
    for f in fields:
        spec: dict = {}
        if f.enum_values() is not None:
            vals = list(f.enum_values())
            if not f.required and "" not in vals:
                vals = vals + [""]  # allow blank for in-progress optional enums
            spec["enum"] = vals
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
            if f.min_inclusive is not None:
                spec["minimum"] = f.min_inclusive
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
    return _json_object(SIGNAL_FIELDS)


def json_interface_schema() -> dict:
    return _json_object(INTERFACE_FIELDS)


def _enum_simple_type(name: str, values) -> str:
    lines = [f'  <xs:simpleType name="{name}">',
             '    <xs:restriction base="xs:string">']
    lines += [f'      <xs:enumeration value="{v}"/>' for v in values]
    lines += ['    </xs:restriction>', '  </xs:simpleType>']
    return "\n".join(lines)


def xsd_enum_types() -> str:
    """DirectionType kept for namespace stability."""
    return _enum_simple_type("DirectionType", DIRECTIONS)


def assemble_xsd(template_text: str) -> str:
    out = template_text.replace("  <!-- @SIGNAL_TYPES@ -->", xsd_signal_block())
    out = out.replace("  <!-- @INTERFACE_TYPE@ -->", xsd_interface_block())
    out = out.replace("  <!-- @ENUM_TYPES@ -->", xsd_enum_types())
    return out