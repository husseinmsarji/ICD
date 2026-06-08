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


# ---- pr_ticket field + change-control warning ----
def test_pr_ticket_in_registry_and_optional():
    from icdgen.fields import SIGNAL_FIELDS, SIGNAL_FIELDS_BY_NAME
    assert "pr_ticket" in SIGNAL_FIELDS_BY_NAME
    f = SIGNAL_FIELDS_BY_NAME["pr_ticket"]
    assert f.required is False and f.xml_name == "prTicket"


def test_pr_ticket_warns_after_rev_a(tmp_path):
    # rev "C" signal with no prTicket -> warning; rev "A" -> no ticket warning.
    revc = _wip_xml().replace("<revision>A</revision>", "<revision>C</revision>")
    m, _h, warns = load(_make_xml(tmp_path, revc))
    assert any("no PR ticket" in w.message for w in warns)
    # baseline rev A: no ticket warning
    m2, _h2, warns2 = load(_make_xml(tmp_path, _wip_xml()))
    assert not any("no PR ticket" in w.message for w in warns2)


def test_pr_ticket_present_suppresses_warning(tmp_path):
    revc = _wip_xml(extra="<prTicket>PR-7</prTicket>").replace(
        "<revision>A</revision>", "<revision>C</revision>")
    m, _h, warns = load(_make_xml(tmp_path, revc))
    assert m.interfaces[0].packets[0].signals[0].pr_ticket == "PR-7"
    assert not any("no PR ticket" in w.message for w in warns)


def test_pr_ticket_in_traceability():
    model, h, _w = load(EX_XML)
    prov = Provenance.create(h, model.schema_version)
    csv = gen_trace.render_csv(model, prov)
    assert "PR Ticket" in csv.splitlines()[0]


# ---- prior-revision auto-diff summaries ----
def test_prior_revisions_parse_and_serialize(tmp_path):
    from icdgen.serializer import to_xml
    body = _wip_xml().replace(
        "<interfaces>",
        '<priorRevisions><priorRevision revision="A" source="old.xml"/>'
        '</priorRevisions><interfaces>', 1)
    m, _h, _w = load(_make_xml(tmp_path, body))
    assert len(m.prior_revisions) == 1
    assert m.prior_revisions[0].revision == "A"
    assert m.prior_revisions[0].source == "old.xml"
    # round-trips through the serializer
    assert "priorRevision" in to_xml(m)


def test_revision_summary_computes_against_prior(tmp_path):
    from icdgen.rev_summary import compute_revision_summaries
    # Write an "old" file (1 signal) and a "new" file (2 signals) that links it.
    old = _wip_xml(name="sig_a")
    old_path = tmp_path / "old.xml"; old_path.write_text(old, encoding="utf-8")
    new = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<icd xmlns="urn:icdgen:icd:1.0" schemaVersion="1.0">'
        '<metadata><documentId>D</documentId><documentTitle>T</documentTitle>'
        '<program>P</program><revision>B</revision>'
        '<revisionDate>2026-06-02</revisionDate><author>H</author>'
        '<revisionHistory>'
        '<entry><revision>A</revision><date>2026-06-01</date><author>H</author>'
        '<description>init</description></entry>'
        '<entry><revision>B</revision><date>2026-06-02</date><author>H</author>'
        '<description>add</description></entry>'
        '</revisionHistory></metadata>'
        '<priorRevisions><priorRevision revision="A" source="old.xml"/></priorRevisions>'
        '<interfaces><interface id="IF-1" busType="ARINC429" dal="A">'
        '<name>N</name><sourceLru>A</sourceLru><destinationLru>B</destinationLru>'
        '<owningDocument>D</owningDocument><packets><packet name="P1"><signals>'
        '<signal name="sig_a" signalType="uint8"><updateRateHz>50</updateRateHz><units>u</units></signal>'
        '<signal name="sig_b" signalType="uint8"><updateRateHz>50</updateRateHz><units>u</units></signal>'
        '</signals></packet></packets></interface></interfaces></icd>'
    )
    new_path = tmp_path / "new.xml"; new_path.write_text(new, encoding="utf-8")
    m, _h, _w = load(str(new_path))
    sums = {s.revision: s.text for s in compute_revision_summaries(m, str(tmp_path))}
    assert sums["A"] == "Initial release."
    # Default mode is PR-grouped; sig_b is untagged so it lands under "(no ticket)".
    assert "+sig_b" in sums["B"]
    assert "(no ticket)" in sums["B"]


def test_revision_summary_missing_source_is_graceful(tmp_path):
    from icdgen.rev_summary import compute_revision_summaries
    body = _wip_xml().replace("<revision>A</revision>", "<revision>B</revision>")
    # add a second history entry so idx>0 path runs, but no priorRevisions link
    body = body.replace(
        "<description>d</description></entry>",
        "<description>d</description></entry>"
        "<entry><revision>B</revision><date>2026-06-02</date><author>H</author>"
        "<description>x</description></entry>", 1)
    m, _h, _w = load(_make_xml(tmp_path, body))
    sums = compute_revision_summaries(m, str(tmp_path))  # must not raise
    assert sums[-1].text  # has some note text


# ---- standalone diff PDF report (Flow B) ----
def test_diff_pdf_report_builds_and_is_deterministic(tmp_path):
    from icdgen.gen_diff_pdf import build_diff_pdf
    import hashlib
    demo = os.path.join(ROOT, "examples", "icd_demo.xml")
    revd = os.path.join(ROOT, "examples", "icd_demo_revD.xml")
    o, oh, _ = load(demo)
    n, nh, _ = load(revd)
    res = diff(o, n)
    p1 = str(tmp_path / "d1.pdf")
    p2 = str(tmp_path / "d2.pdf")
    build_diff_pdf(res, oh, nh, p1, "Rev C", "Rev D")
    build_diff_pdf(res, oh, nh, p2, "Rev C", "Rev D")
    b1 = open(p1, "rb").read()
    assert b1[:5] == b"%PDF-"
    assert b1 == open(p2, "rb").read()  # deterministic


def test_diff_pdf_report_no_changes(tmp_path):
    from icdgen.gen_diff_pdf import build_diff_pdf
    model, h, _ = load(EX_XML)
    res = diff(model, model)               # identical -> no changes
    p = str(tmp_path / "same.pdf")
    build_diff_pdf(res, h, h, p)
    assert open(p, "rb").read()[:5] == b"%PDF-"


# ---- PR-grouped change summary (1.6.x) ----
def test_revision_summary_groups_by_pr_ticket(tmp_path):
    from icdgen.rev_summary import compute_revision_summaries

    def doc(rev, signals_xml, prior=""):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<icd xmlns="urn:icdgen:icd:1.0" schemaVersion="1.0">'
            '<metadata><documentId>D</documentId><documentTitle>T</documentTitle>'
            '<program>P</program><revision>' + rev + '</revision>'
            '<revisionDate>2026-06-02</revisionDate><author>H</author>'
            '<revisionHistory>'
            '<entry><revision>A</revision><date>2026-06-01</date><author>H</author>'
            '<description>init</description></entry>'
            '<entry><revision>B</revision><date>2026-06-02</date><author>H</author>'
            '<description>chg</description></entry>'
            '</revisionHistory></metadata>' + prior +
            '<interfaces><interface id="IF-1" busType="CAN" dal="A">'
            '<name>N</name><sourceLru>A</sourceLru><destinationLru>B</destinationLru>'
            '<owningDocument>D</owningDocument><packets><packet name="P1"><signals>'
            + signals_xml +
            '</signals></packet></packets></interface></interfaces></icd>')

    def sig(name, extra="", ticket=None):
        t = f"<prTicket>{ticket}</prTicket>" if ticket else ""
        return (f'<signal name="{name}" signalType="uint8">'
                f'<updateRateHz>10</updateRateHz><units>u</units>'
                f'<rangeMin>0</rangeMin><rangeMax>1</rangeMax>{extra}{t}</signal>')

    # OLD (rev A state): keeper + to-be-removed; both untagged.
    old = doc("A", sig("keeper") + sig("gone"))
    (tmp_path / "old.xml").write_text(old, encoding="utf-8")

    # NEW (rev B): keeper modified (range, PR-2000), 'gone' removed, 'fresh' added
    # (PR-1042). 'keeper' rangeMax 1->5.
    new = doc(
        "B",
        sig("keeper", extra="", ticket="PR-2000").replace(
            "<rangeMax>1</rangeMax>", "<rangeMax>5</rangeMax>")
        + sig("fresh", ticket="PR-1042"),
        prior='<priorRevisions><priorRevision revision="A" source="old.xml"/>'
              '</priorRevisions>')
    (tmp_path / "new.xml").write_text(new, encoding="utf-8")

    m, _h, _w = load(str(tmp_path / "new.xml"))
    text = {s.revision: s.text for s in compute_revision_summaries(m, str(tmp_path))}["B"]
    # added attributed to its ticket
    assert "PR-1042: +fresh" in text
    # modified attributed to the new signal's ticket; pr_ticket field suppressed
    assert "PR-2000: ~keeper (range_max)" in text
    assert "pr_ticket" not in text
    # removed (untagged in old) under "(no ticket)"
    assert "(no ticket): -gone" in text


# ---- serializer attribute escaping (quote-safety regression) ----
def test_serializer_escapes_quotes_in_attributes(tmp_path):
    """A packet name (an XSD xs:string attribute with no pattern) containing a
    double quote must serialize to well-formed XML that re-parses to the same
    value. Regression: escape() does not escape quotes by default, which
    corrupted the attribute and broke round-trip."""
    from icdgen.serializer import to_xml
    from icdgen.model import (Packet, Signal, Interface, Metadata,
                              RevisionEntry, IcdModel)
    sig = Signal(name="s", signal_type="uint8", update_rate_hz=1.0, units="u",
                 range_min=0.0, range_max=1.0)
    pkt = Packet(name='bad"quote', signals=(sig,))
    iface = Interface(id="IF-1", name="N", bus_type="CAN", dal="A",
                      source_lru="A", destination_lru="B", owning_document="D",
                      packets=(pkt,))
    meta = Metadata("D", "T", "P", "A", "2026-06-01", "H",
                    (RevisionEntry("A", "2026-06-01", "H", "d"),))
    xml = to_xml(IcdModel("1.0", meta, (iface,)))
    p = tmp_path / "q.xml"
    p.write_text(xml, encoding="utf-8")
    model2, _h, _w = load(str(p))
    assert model2.interfaces[0].packets[0].name == 'bad"quote'


# ---- configuration-management guards ----
def test_schema_template_copies_in_sync():
    """The XSD template is shipped in two locations (repo-root schemas/ for
    source/PyInstaller, and inside the package for wheel installs). They are
    kept in sync by hand, so guard that they are byte-identical: a drift here
    would mean a wheel-installed tool validates against a different schema than
    a source checkout, which is a qualification hazard."""
    root_copy = os.path.join(ROOT, "schemas", "icd-1.0.xsd.template")
    pkg_copy = os.path.join(ROOT, "icdgen", "schemas", "icd-1.0.xsd.template")
    if not (os.path.isfile(root_copy) and os.path.isfile(pkg_copy)):
        import pytest as _pt
        _pt.skip("only one template copy present in this layout")
    with open(root_copy, "rb") as a, open(pkg_copy, "rb") as b:
        assert a.read() == b.read(), "XSD template copies have drifted"


def test_package_version_matches_tool_version():
    """pyproject version and the provenance TOOL_VERSION are independent by
    design, but the packaging version must not silently lag the project; guard
    that pyproject parses and exposes a concrete version string."""
    import re
    pyproject = os.path.join(ROOT, "pyproject.toml")
    text = open(pyproject, encoding="utf-8").read()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "version missing from pyproject.toml"
    assert re.match(r"^\d+\.\d+\.\d+$", m.group(1)), "version not semver"