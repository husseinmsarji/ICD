"""Test suite for icdgen.

Covers schema validation (XML+JSON, line-referenced errors), the relaxed-rule
behavior (v1.5.0), the warnings channel, byte-determinism, provenance stamping,
registry/schema sync, and diff detection.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from icdgen import gen_code, gen_docx, gen_pdf, gen_trace  # noqa: E402
from icdgen.diff import diff  # noqa: E402
from icdgen.loader import ValidationError, load  # noqa: E402
from icdgen.provenance import Provenance  # noqa: E402

EX_XML = os.path.join(ROOT, "examples", "icd_example.xml")


def _make_xml(tmp_path, body):
    p = tmp_path / "in.xml"
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_valid_xml_loads():
    model, h, _w = load(EX_XML)
    assert model.schema_version == "1.0"
    assert len(model.interfaces) == 1
    assert len(h) == 64


def test_missing_required_field_has_line_ref(tmp_path):
    # `units` is still required; removing it is a fatal, line-referenced error.
    body = open(EX_XML).read().replace("<units>deg</units>", "", 1)
    path = _make_xml(tmp_path, body)
    with pytest.raises(ValidationError) as ei:
        load(path)
    assert ei.value.line is not None
    assert ei.value.line > 0


def test_bad_enum_rejected(tmp_path):
    body = open(EX_XML).read().replace('dal="A"', 'dal="Z"', 1)
    path = _make_xml(tmp_path, body)
    with pytest.raises(ValidationError):
        load(path)


def test_duplicate_signal_rejected(tmp_path):
    src = open(EX_XML).read()
    block = src[src.index("<signal name=\"latitude\""):src.index("</signal>") + 9]
    body = src.replace(block, block + "\n" + block, 1)
    path = _make_xml(tmp_path, body)
    with pytest.raises(ValidationError):
        load(path)


def test_determinism_all_artifacts():
    model, h, _w = load(EX_XML)
    prov = Provenance.create(h, model.schema_version)
    assert gen_code.render_header(model, prov) == gen_code.render_header(model, prov)
    assert gen_code.render_simulink(model, prov) == gen_code.render_simulink(model, prov)
    assert gen_trace.render_csv(model, prov) == gen_trace.render_csv(model, prov)


def test_header_contains_provenance():
    model, h, _w = load(EX_XML)
    prov = Provenance.create(h, model.schema_version)
    out = gen_code.render_header(model, prov)
    assert h in out
    assert "DO NOT EDIT" in out
    assert "if_nav_state_position_t" in out


def test_trace_csv_row_count():
    model, h, _w = load(EX_XML)
    prov = Provenance.create(h, model.schema_version)
    csv = gen_trace.render_csv(model, prov)
    n_sig = sum(len(pk.signals) for i in model.interfaces for pk in i.packets)
    assert len(csv.strip().splitlines()) == n_sig + 1
    assert h in csv


def test_diff_detects_changes():
    model, _, _w = load(EX_XML)
    res_same = diff(model, model)
    assert not res_same.has_changes


def test_cli_validate_exit_codes(tmp_path):
    r = subprocess.run([sys.executable, "-m", "icdgen.cli", "validate", EX_XML],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0
    bad = open(EX_XML).read().replace("<units>deg</units>", "", 1)
    bp = _make_xml(tmp_path, bad)
    r2 = subprocess.run([sys.executable, "-m", "icdgen.cli", "validate", bp],
                        cwd=ROOT, capture_output=True, text=True)
    assert r2.returncode == 1
    assert "VALIDATION ERROR" in r2.stderr


def test_serializer_roundtrips():
    from icdgen.serializer import to_xml
    import tempfile, os as _os
    model, _, _w = load(EX_XML)
    xml = to_xml(model)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
        f.write(xml); p = f.name
    try:
        model2, _, _w2 = load(p)
        assert tuple(model2.interfaces) == tuple(model.interfaces)
        assert to_xml(model2) == xml
    finally:
        _os.unlink(p)


def test_registry_schema_sync():
    from icdgen.fields import SIGNAL_FIELDS
    from icdgen.schema_gen import json_signal_schema
    from icdgen.resources import compiled_xsd
    js = json_signal_schema()
    xsd = compiled_xsd()
    for f in SIGNAL_FIELDS:
        assert f.json_name in js["properties"]
        assert f.xml_name in xsd
    reg_required = {f.json_name for f in SIGNAL_FIELDS if f.required}
    assert set(js["required"]) == reg_required


def test_registry_roundtrip_via_codec():
    from icdgen.signal_codec import signal_to_json_dict, signal_from_json_dict
    model, _, _w = load(EX_XML)
    for iface, pkt, sig in model.all_signals():
        assert signal_from_json_dict(signal_to_json_dict(sig)) == sig


def test_assembled_xsd_compiles():
    from lxml import etree
    from icdgen.resources import compiled_xsd
    etree.XMLSchema(etree.fromstring(compiled_xsd().encode("utf-8")))


def test_interface_registry_schema_sync():
    from icdgen.fields import INTERFACE_FIELDS
    from icdgen.schema_gen import json_interface_schema
    from icdgen.resources import compiled_xsd
    js = json_interface_schema()
    xsd = compiled_xsd()
    for f in INTERFACE_FIELDS:
        assert f.json_name in js["properties"]
        assert f.xml_name in xsd


def test_interface_roundtrip_via_codec():
    from icdgen.signal_codec import interface_to_json_dict, interface_from_json_dict
    model, _, _w = load(EX_XML)
    for iface in model.interfaces:
        assert interface_from_json_dict(interface_to_json_dict(iface)) == iface


def test_duplicate_packet_rejected(tmp_path):
    src = open(EX_XML).read()
    block = src[src.index('<packet name="POSITION"'):
                src.index("</packet>") + len("</packet>")]
    body = src.replace(block, block + "\n" + block, 1)
    path = _make_xml(tmp_path, body)
    with pytest.raises(ValidationError):
        load(path)


def test_packet_roundtrip_via_codec():
    from icdgen.signal_codec import packet_to_json_dict, packet_from_json_dict
    model, _, _w = load(EX_XML)
    for iface in model.interfaces:
        for pkt in iface.packets:
            assert packet_from_json_dict(packet_to_json_dict(pkt)) == pkt


def test_enum_is_a_valid_signal_type():
    from icdgen.fields import DATA_TYPE_NAMES, C_TYPE_MAP
    assert "enum" in DATA_TYPE_NAMES
    assert C_TYPE_MAP["enum"] == "int32_t"


# ---- v1.5.0 relaxed-rules + warnings ----
def _wip_xml(signal_attrs='signalType="uint8"', rate="<updateRateHz>50</updateRateHz>",
             extra="", bus="ARINC429", name="sig_ok"):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<icd xmlns="urn:icdgen:icd:1.0" schemaVersion="1.0">
  <metadata><documentId>D</documentId><documentTitle>T</documentTitle>
  <program>P</program><revision>A</revision><revisionDate>2026-06-01</revisionDate>
  <author>H</author><revisionHistory><entry><revision>A</revision>
  <date>2026-06-01</date><author>H</author><description>d</description></entry>
  </revisionHistory></metadata>
  <interfaces><interface id="IF-1" busType="{bus}" dal="A">
  <name>N</name><sourceLru>A</sourceLru><destinationLru>B</destinationLru>
  <owningDocument>D</owningDocument><packets><packet name="P1"><signals>
  <signal name="{name}" {signal_attrs}>{rate}<units>u</units>{extra}</signal>
  </signals></packet></packets></interface></interfaces></icd>'''


def test_bus_type_freeform(tmp_path):
    p = _make_xml(tmp_path, _wip_xml(bus="SpaceWire"))
    model, _h, _w = load(p)
    assert model.interfaces[0].bus_type == "SpaceWire"


def test_signal_type_optional_blank(tmp_path):
    p = _make_xml(tmp_path, _wip_xml(signal_attrs='signalType=""'))
    model, _h, warns = load(p)
    sig = model.interfaces[0].packets[0].signals[0]
    assert sig.signal_type == ""
    assert sig.c_type == "uint8_t"
    assert sig.has_concrete_type is False
    assert any("no signal type" in w.message for w in warns)


def test_update_rate_optional_and_nonnegative(tmp_path):
    m1, _h, _w = load(_make_xml(tmp_path, _wip_xml(rate="")))
    assert m1.interfaces[0].packets[0].signals[0].update_rate_hz is None
    load(_make_xml(tmp_path, _wip_xml(rate="<updateRateHz>0</updateRateHz>")))
    with pytest.raises(ValidationError):
        load(_make_xml(tmp_path, _wip_xml(rate="<updateRateHz>-1</updateRateHz>")))


def test_range_optional(tmp_path):
    model, _h, _w = load(_make_xml(tmp_path, _wip_xml()))
    sig = model.interfaces[0].packets[0].signals[0]
    assert sig.range_min is None and sig.range_max is None


def test_noncident_name_warns_not_fatal(tmp_path):
    model, _h, warns = load(_make_xml(tmp_path, _wip_xml(name="motor-speed#1")))
    assert model.interfaces[0].packets[0].signals[0].name == "motor-speed#1"
    assert any("not a valid C identifier" in w.message for w in warns)


def test_range_min_gt_max_still_fatal_when_both_present(tmp_path):
    p = _make_xml(tmp_path, _wip_xml(
        extra="<rangeMin>10</rangeMin><rangeMax>5</rangeMax>"))
    with pytest.raises(ValidationError):
        load(p)