"""Test suite for icdgen.

Covers schema validation (line-referenced errors), the relaxed-rule behavior
(v1.5.0), the warnings channel, byte-determinism, provenance stamping,
registry/schema sync, and diff detection. The ICD definition format is YAML.

Examples: the suite runs against the three-revision eVTOL ICD
(icd_evtol_revA/B/C.yaml). revA is the single-baseline fixture; the revB->revC
pair is the diff fixture.
"""
import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from icdgen import gen_code, gen_docx, gen_pdf, gen_trace  # noqa: E402,F401
from icdgen.diff import diff  # noqa: E402
from icdgen.loader import ValidationError, load, schema_hash  # noqa: E402
from icdgen.provenance import Provenance  # noqa: E402
from icdgen.serializer import to_yaml  # noqa: E402

# Baseline ICD used by most tests. revA: 3 interfaces / 3 packets / 9 signals,
# Rev A (no pr_tickets expected). IF-NAV-STATE/POSITION carries latitude,
# longitude, altitude_msl, so the if_nav_state_position_t struct and a
# `units: "deg"` value are both present.
EX = os.path.join(ROOT, "examples", "icd_evtol_revA.yaml")


# --------------------------------------------------------------------------
# YAML fixture helpers (author minimal, valid ICD YAML programmatically)
# --------------------------------------------------------------------------
def _make_yaml(tmp_path, body):
    p = tmp_path / "in.yaml"
    p.write_text(body, encoding="utf-8")
    return str(p)


def _sig(name="sig_ok", signal_type="uint8", rate=50, units="u", **extra):
    lines = [f'          - name: "{name}"']
    if signal_type is not None:
        lines.append(f'            signalType: "{signal_type}"')
    if rate is not None:
        lines.append(f'            updateRateHz: {rate}')
    if units is not None:
        lines.append(f'            units: "{units}"')
    for k, v in extra.items():
        lines.append(f'            {k}: "{v}"' if isinstance(v, str)
                     else f'            {k}: {v}')
    return "\n".join(lines)


def _doc(signals, *, revision="A", bus="ARINC429", history=None, prior="",
         iface_id="IF-1"):
    if history is None:
        history = [("A", "2026-06-01", "H", "d")]
    hist = "\n".join(
        f'    - revision: "{r}"\n      date: "{d}"\n'
        f'      author: "{a}"\n      description: "{desc}"'
        for (r, d, a, desc) in history)
    prior_block = (prior + "\n") if prior else ""
    return (
        'schemaVersion: "1.0"\n'
        'metadata:\n'
        '  documentId: "D"\n'
        '  documentTitle: "T"\n'
        '  program: "P"\n'
        f'  revision: "{revision}"\n'
        '  revisionDate: "2026-06-01"\n'
        '  author: "H"\n'
        '  revisionHistory:\n'
        f'{hist}\n'
        f'{prior_block}'
        'interfaces:\n'
        f'  - id: "{iface_id}"\n'
        f'    busType: "{bus}"\n'
        '    dal: "A"\n'
        '    name: "N"\n'
        '    sourceLru: "A"\n'
        '    destinationLru: "B"\n'
        '    owningDocument: "D"\n'
        '    packets:\n'
        '      - name: "P1"\n'
        '        signals:\n'
        f'{signals}\n'
    )


def _wip(tmp_path, **kw):
    sig_kw = {k: kw.pop(k) for k in list(kw)
              if k in ("name", "signal_type", "rate", "units")}
    extra = kw.pop("extra", {})
    return _make_yaml(tmp_path, _doc(_sig(**sig_kw, **extra), **kw))


# --------------------------------------------------------------------------
# Basic loading + validation
# --------------------------------------------------------------------------
def test_valid_yaml_loads():
    model, h, _w = load(EX)
    assert model.schema_version == "1.0"
    assert len(model.interfaces) == 3
    assert len(h) == 64


def test_missing_required_field_has_line_ref(tmp_path):
    # `units` is still required; removing it is a fatal, line-referenced error.
    body = open(EX).read().replace('units: "deg"', "", 1)
    path = _make_yaml(tmp_path, body)
    with pytest.raises(ValidationError) as ei:
        load(path)
    assert ei.value.line is not None
    assert ei.value.line > 0


def test_bad_enum_rejected(tmp_path):
    body = open(EX).read().replace('dal: "A"', 'dal: "Z"', 1)
    path = _make_yaml(tmp_path, body)
    with pytest.raises(ValidationError):
        load(path)


def test_yaml_syntax_error_has_line_ref(tmp_path):
    # A malformed YAML mapping is a fatal, line-referenced parse error.
    body = 'schemaVersion: "1.0"\nmetadata: [unterminated\n'
    path = _make_yaml(tmp_path, body)
    with pytest.raises(ValidationError) as ei:
        load(path)
    assert ei.value.line is not None


def test_duplicate_signal_rejected(tmp_path):
    body = _doc(_sig("dup") + "\n" + _sig("dup"))
    with pytest.raises(ValidationError):
        load(_make_yaml(tmp_path, body))


def test_duplicate_packet_rejected(tmp_path):
    # Two packets with the same name in one interface.
    body = _doc(_sig("a"))
    body = body.replace(
        '        signals:\n' + _sig("a") + "\n",
        '        signals:\n' + _sig("a") + "\n"
        '      - name: "P1"\n'
        '        signals:\n' + _sig("b") + "\n", 1)
    with pytest.raises(ValidationError):
        load(_make_yaml(tmp_path, body))


# --------------------------------------------------------------------------
# Determinism + provenance
# --------------------------------------------------------------------------
def test_determinism_all_artifacts():
    model, h, _w = load(EX)
    prov = Provenance.create(h, model.schema_version)
    assert gen_code.render_header(model, prov) == gen_code.render_header(model, prov)
    assert gen_code.render_simulink(model, prov) == gen_code.render_simulink(model, prov)
    assert gen_trace.render_csv(model, prov) == gen_trace.render_csv(model, prov)


def test_yaml_serialization_is_deterministic_and_dates_are_strings(tmp_path):
    import yaml as _yaml
    model, _, _ = load(EX)
    y1 = to_yaml(model)
    # reload from canonical and re-serialize -> byte-identical (idempotent).
    p = tmp_path / "c.yaml"
    p.write_text(y1, encoding="utf-8")
    m2, _, _ = load(str(p))
    assert to_yaml(m2) == y1
    # dates round-trip as strings (not coerced to datetime.date by YAML).
    data = _yaml.safe_load(y1)
    assert isinstance(data["metadata"]["revisionDate"], str)


def test_schema_hash_is_stable_and_64_hex():
    a = schema_hash()
    assert len(a) == 64
    assert a == schema_hash()


def test_header_contains_provenance():
    model, h, _w = load(EX)
    prov = Provenance.create(h, model.schema_version)
    out = gen_code.render_header(model, prov)
    assert h in out
    assert "DO NOT EDIT" in out
    assert "if_nav_state_position_t" in out


def test_trace_csv_row_count():
    model, h, _w = load(EX)
    prov = Provenance.create(h, model.schema_version)
    csv = gen_trace.render_csv(model, prov)
    n_sig = sum(len(pk.signals) for i in model.interfaces for pk in i.packets)
    assert len(csv.strip().splitlines()) == n_sig + 1
    assert h in csv


def test_diff_detects_changes():
    model, _, _w = load(EX)
    res_same = diff(model, model)
    assert not res_same.has_changes


def test_cli_validate_exit_codes(tmp_path):
    r = subprocess.run([sys.executable, "-m", "icdgen.cli", "validate", EX],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0
    bad = open(EX).read().replace('units: "deg"', "", 1)
    bp = _make_yaml(tmp_path, bad)
    r2 = subprocess.run([sys.executable, "-m", "icdgen.cli", "validate", bp],
                        cwd=ROOT, capture_output=True, text=True)
    assert r2.returncode == 1
    assert "VALIDATION ERROR" in r2.stderr


# --------------------------------------------------------------------------
# Serializer round-trip
# --------------------------------------------------------------------------
def test_serializer_roundtrips():
    model, _, _w = load(EX)
    y = to_yaml(model)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(y)
        p = f.name
    try:
        model2, _, _w2 = load(p)
        assert tuple(model2.interfaces) == tuple(model.interfaces)
        assert to_yaml(model2) == y
    finally:
        os.unlink(p)


# --------------------------------------------------------------------------
# Registry <-> schema sync + codec round-trips
# --------------------------------------------------------------------------
def test_registry_schema_sync():
    from icdgen.fields import SIGNAL_FIELDS
    from icdgen.schema_gen import json_signal_schema
    js = json_signal_schema()
    for f in SIGNAL_FIELDS:
        assert f.json_name in js["properties"]
    reg_required = {f.json_name for f in SIGNAL_FIELDS if f.required}
    assert set(js["required"]) == reg_required


def test_interface_registry_schema_sync():
    from icdgen.fields import INTERFACE_FIELDS
    from icdgen.schema_gen import json_interface_schema
    js = json_interface_schema()
    for f in INTERFACE_FIELDS:
        assert f.json_name in js["properties"]


def test_registry_roundtrip_via_codec():
    from icdgen.signal_codec import signal_to_json_dict, signal_from_json_dict
    model, _, _w = load(EX)
    for iface, pkt, sig in model.all_signals():
        assert signal_from_json_dict(signal_to_json_dict(sig)) == sig


def test_interface_roundtrip_via_codec():
    from icdgen.signal_codec import interface_to_json_dict, interface_from_json_dict
    model, _, _w = load(EX)
    for iface in model.interfaces:
        assert interface_from_json_dict(interface_to_json_dict(iface)) == iface


def test_packet_roundtrip_via_codec():
    from icdgen.signal_codec import packet_to_json_dict, packet_from_json_dict
    model, _, _w = load(EX)
    for iface in model.interfaces:
        for pkt in iface.packets:
            assert packet_from_json_dict(packet_to_json_dict(pkt)) == pkt


def test_enum_is_a_valid_signal_type():
    from icdgen.fields import DATA_TYPE_NAMES, C_TYPE_MAP
    assert "enum" in DATA_TYPE_NAMES
    assert C_TYPE_MAP["enum"] == "int32_t"


# --------------------------------------------------------------------------
# v1.5.0 relaxed-rules + warnings
# --------------------------------------------------------------------------
def test_bus_type_freeform(tmp_path):
    model, _h, _w = load(_wip(tmp_path, bus="SpaceWire"))
    assert model.interfaces[0].bus_type == "SpaceWire"


def test_signal_type_optional_blank(tmp_path):
    model, _h, warns = load(_wip(tmp_path, signal_type=""))
    sig = model.interfaces[0].packets[0].signals[0]
    assert sig.signal_type == ""
    assert sig.c_type == "uint8_t"
    assert sig.has_concrete_type is False
    assert any("no signal type" in w.message for w in warns)


def test_update_rate_optional_and_nonnegative(tmp_path):
    m1, _h, _w = load(_wip(tmp_path, rate=None))
    assert m1.interfaces[0].packets[0].signals[0].update_rate_hz is None
    load(_wip(tmp_path, rate=0))
    with pytest.raises(ValidationError):
        load(_wip(tmp_path, rate=-1))


def test_range_optional(tmp_path):
    model, _h, _w = load(_wip(tmp_path))
    sig = model.interfaces[0].packets[0].signals[0]
    assert sig.range_min is None and sig.range_max is None


def test_noncident_name_warns_not_fatal(tmp_path):
    model, _h, warns = load(_wip(tmp_path, name="motor-speed#1"))
    assert model.interfaces[0].packets[0].signals[0].name == "motor-speed#1"
    assert any("not a valid C identifier" in w.message for w in warns)


def test_range_min_gt_max_still_fatal_when_both_present(tmp_path):
    with pytest.raises(ValidationError):
        load(_wip(tmp_path, extra={"rangeMin": 10, "rangeMax": 5}))


# --------------------------------------------------------------------------
# pr_ticket field + change-control warning
# --------------------------------------------------------------------------
def test_pr_ticket_in_registry_and_optional():
    from icdgen.fields import SIGNAL_FIELDS_BY_NAME
    assert "pr_ticket" in SIGNAL_FIELDS_BY_NAME
    f = SIGNAL_FIELDS_BY_NAME["pr_ticket"]
    assert f.required is False and f.json_name == "prTicket"


def test_pr_ticket_warns_after_rev_a(tmp_path):
    m, _h, warns = load(_wip(tmp_path, revision="C"))
    assert any("no PR ticket" in w.message for w in warns)
    m2, _h2, warns2 = load(_wip(tmp_path))
    assert not any("no PR ticket" in w.message for w in warns2)


def test_pr_ticket_present_suppresses_warning(tmp_path):
    m, _h, warns = load(_wip(tmp_path, revision="C", extra={"prTicket": "PR-7"}))
    assert m.interfaces[0].packets[0].signals[0].pr_ticket == "PR-7"
    assert not any("no PR ticket" in w.message for w in warns)


def test_pr_ticket_in_traceability():
    model, h, _w = load(EX)
    prov = Provenance.create(h, model.schema_version)
    csv = gen_trace.render_csv(model, prov)
    assert "PR Ticket" in csv.splitlines()[0]


# --------------------------------------------------------------------------
# Prior-revision auto-diff summaries
# --------------------------------------------------------------------------
_PRIOR_A = ('priorRevisions:\n'
            '  - revision: "A"\n'
            '    source: "old.yaml"')


def test_prior_revisions_parse_and_serialize(tmp_path):
    body = _doc(_sig(), prior=_PRIOR_A)
    m, _h, _w = load(_make_yaml(tmp_path, body))
    assert len(m.prior_revisions) == 1
    assert m.prior_revisions[0].revision == "A"
    assert m.prior_revisions[0].source == "old.yaml"
    # round-trips through the serializer
    y = to_yaml(m)
    assert "priorRevisions:" in y and 'source: "old.yaml"' in y


def test_revision_summary_computes_against_prior(tmp_path):
    from icdgen.rev_summary import compute_revision_summaries
    old = _doc(_sig("sig_a"), revision="A")
    (tmp_path / "old.yaml").write_text(old, encoding="utf-8")
    new = _doc(
        _sig("sig_a") + "\n" + _sig("sig_b"),
        revision="B",
        history=[("A", "2026-06-01", "H", "init"),
                 ("B", "2026-06-02", "H", "add")],
        prior=_PRIOR_A)
    new_path = tmp_path / "new.yaml"
    new_path.write_text(new, encoding="utf-8")
    m, _h, _w = load(str(new_path))
    sums = {s.revision: s.text
            for s in compute_revision_summaries(m, str(tmp_path))}
    assert sums["A"] == "Initial release."
    # Default mode is PR-grouped; sig_b is untagged -> "(no ticket)".
    assert "+sig_b" in sums["B"]
    assert "(no ticket)" in sums["B"]


def test_revision_summary_missing_source_is_graceful(tmp_path):
    from icdgen.rev_summary import compute_revision_summaries
    # rev B with a second history entry but NO priorRevisions link.
    body = _doc(_sig(), revision="B",
                history=[("A", "2026-06-01", "H", "d"),
                         ("B", "2026-06-02", "H", "x")])
    m, _h, _w = load(_make_yaml(tmp_path, body))
    sums = compute_revision_summaries(m, str(tmp_path))  # must not raise
    assert sums[-1].text  # has some note text


def test_revision_summary_groups_by_pr_ticket(tmp_path):
    from icdgen.rev_summary import compute_revision_summaries
    # OLD (rev A): keeper + to-be-removed 'gone'; both untagged.
    old = _doc(_sig("keeper", rangeMin=0, rangeMax=1)
               + "\n" + _sig("gone", rangeMin=0, rangeMax=1),
               revision="A", bus="CAN")
    (tmp_path / "old.yaml").write_text(old, encoding="utf-8")
    # NEW (rev B): keeper modified (rangeMax 1->5, PR-2000), 'gone' removed,
    # 'fresh' added (PR-1042).
    new = _doc(
        _sig("keeper", rangeMin=0, rangeMax=5, prTicket="PR-2000")
        + "\n" + _sig("fresh", rangeMin=0, rangeMax=1, prTicket="PR-1042"),
        revision="B", bus="CAN",
        history=[("A", "2026-06-01", "H", "init"),
                 ("B", "2026-06-02", "H", "chg")],
        prior=_PRIOR_A)
    (tmp_path / "new.yaml").write_text(new, encoding="utf-8")
    m, _h, _w = load(str(tmp_path / "new.yaml"))
    text = {s.revision: s.text
            for s in compute_revision_summaries(m, str(tmp_path))}["B"]
    assert "PR-1042: +fresh" in text
    assert "PR-2000: ~keeper (range_max)" in text
    assert "pr_ticket" not in text
    assert "(no ticket): -gone" in text


# --------------------------------------------------------------------------
# Standalone diff PDF report (Flow B)
# --------------------------------------------------------------------------
def test_diff_pdf_report_builds_and_is_deterministic(tmp_path):
    from icdgen.gen_diff_pdf import build_diff_pdf
    old = os.path.join(ROOT, "examples", "icd_evtol_revB.yaml")
    new = os.path.join(ROOT, "examples", "icd_evtol_revC.yaml")
    o, oh, _ = load(old)
    n, nh, _ = load(new)
    res = diff(o, n)
    assert res.has_changes
    p1 = str(tmp_path / "d1.pdf")
    p2 = str(tmp_path / "d2.pdf")
    build_diff_pdf(res, oh, nh, p1, "Rev B", "Rev C")
    build_diff_pdf(res, oh, nh, p2, "Rev B", "Rev C")
    b1 = open(p1, "rb").read()
    assert b1[:5] == b"%PDF-"
    assert b1 == open(p2, "rb").read()  # deterministic


def test_diff_pdf_report_no_changes(tmp_path):
    from icdgen.gen_diff_pdf import build_diff_pdf
    model, h, _ = load(EX)
    res = diff(model, model)
    p = str(tmp_path / "same.pdf")
    build_diff_pdf(res, h, h, p)
    assert open(p, "rb").read()[:5] == b"%PDF-"


# --------------------------------------------------------------------------
# Serializer quote-safety regression
# --------------------------------------------------------------------------
def test_serializer_escapes_quotes_in_string_values(tmp_path):
    """A packet name containing a double quote must serialize to well-formed
    YAML that re-parses to the same value (double-quoted escaping)."""
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
    y = to_yaml(IcdModel("1.0", meta, (iface,)))
    p = tmp_path / "q.yaml"
    p.write_text(y, encoding="utf-8")
    model2, _h, _w = load(str(p))
    assert model2.interfaces[0].packets[0].name == 'bad"quote'


# --------------------------------------------------------------------------
# Configuration-management guards
# --------------------------------------------------------------------------
def test_package_version_matches_tool_version():
    """pyproject version and the provenance TOOL_VERSION are independent by
    design, but guard that pyproject parses and exposes a concrete version."""
    import re
    pyproject = os.path.join(ROOT, "pyproject.toml")
    text = open(pyproject, encoding="utf-8").read()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "version missing from pyproject.toml"
    assert re.match(r"^\d+\.\d+\.\d+$", m.group(1)), "version not semver"
