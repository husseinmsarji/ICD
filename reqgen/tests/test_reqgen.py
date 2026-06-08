"""Tests for reqgen: config-file driving, determinism, generation, precedence,
reconciliation, and the dual-hash provenance anchor."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from reqgen.config_io import (ConfigError, config_hash, ensure_config,
                              load_config, save_config)
from reqgen.config_schema import default_config, ASPECTS_BY_KEY
from reqgen.generate import generate_requirements
from reqgen.export import to_csv, EXPORTERS
from reqgen.reconcile import reconcile
from reqgen.provenance import ReqProvenance

from icdgen.loader import load

# Resolve the demo ICD relative to the installed icdgen examples.
import icdgen
_ICDGEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(icdgen.__file__)))
DEMO = os.path.join(_ICDGEN_DIR, "examples", "icd_evtol_revC.xml")
REVB = os.path.join(_ICDGEN_DIR, "examples", "icd_evtol_revB.xml")


def _prov():
    return ReqProvenance.create("a" * 64, "b" * 64)


# ---- the config file is DRIVEN by code, not hand-edited ----
def test_ensure_config_creates_file(tmp_path):
    p = str(tmp_path / "reqgen.json")
    assert not os.path.exists(p)
    cfg = ensure_config(p)               # reqgen writes a populated default
    assert os.path.isfile(p)
    assert cfg.l3_aspects and cfg.l4_aspects


def test_config_roundtrips_deterministically(tmp_path):
    p = str(tmp_path / "reqgen.json")
    c1 = ensure_config(p)
    c2 = load_config(p)
    assert config_hash(c1) == config_hash(c2)


def test_save_changes_hash_and_output(tmp_path):
    p = str(tmp_path / "reqgen.json")
    cfg = ensure_config(p)
    h_before = config_hash(cfg)
    cfg.l4_aspects = cfg.l4_aspects + ["UNITS"]   # programmatic edit (UI later)
    save_config(p, cfg)
    cfg2 = load_config(p)
    assert config_hash(cfg2) != h_before
    assert "UNITS" in cfg2.l4_aspects


def test_invalid_aspect_rejected(tmp_path):
    p = str(tmp_path / "reqgen.json")
    cfg = ensure_config(p)
    cfg.l4_aspects = ["NOPE"]
    with pytest.raises(ConfigError):
        save_config(p, cfg)


# ---- generation ----
def test_generate_default_counts():
    model, _h, _w = load(DEMO)
    reqs = generate_requirements(model, default_config())
    # Derive expected counts from the model so the test tracks the example:
    # 2 default L3 aspects (EXISTS, DAL) per packet; 2 default L4 (TYPE, RANGE)
    # per signal.
    n_pkt = sum(len(p.signals) and 1 or 1 for i in model.interfaces for p in i.packets)
    n_pkt = sum(1 for i in model.interfaces for p in i.packets)
    n_sig = sum(1 for _ in model.all_signals())
    n_l3 = sum(1 for r in reqs if r.level == "L3")
    n_l4 = sum(1 for r in reqs if r.level == "L4")
    assert n_l3 == n_pkt * 2
    assert n_l4 == n_sig * 2


def test_ids_are_stable_across_runs():
    model, _h, _w = load(DEMO)
    a = [r.req_id for r in generate_requirements(model, default_config())]
    b = [r.req_id for r in generate_requirements(model, default_config())]
    assert a == b


def test_csv_is_deterministic():
    model, _h, _w = load(DEMO)
    reqs = generate_requirements(model, default_config())
    assert to_csv(reqs, _prov()) == to_csv(reqs, _prov())


def test_port_granularity_collapses_l3(tmp_path):
    model, _h, _w = load(DEMO)
    cfg = default_config()
    cfg.l3_granularity = "port"
    reqs = generate_requirements(model, cfg)
    # one L3 unit per interface * 2 default L3 aspects (not per packet)
    n_if = len(model.interfaces)
    assert sum(1 for r in reqs if r.level == "L3") == n_if * 2


# ---- precedence ----
def test_signal_template_override_wins():
    model, _h, _w = load(DEMO)
    cfg = default_config()
    from reqgen.config_schema import SignalOverride
    key = "IF-NAV-STATE/POSITION/latitude"
    cfg.signals[key] = SignalOverride(
        templates={"TYPE": "Custom: {signal} is {signal_type}."})
    reqs = generate_requirements(model, cfg)
    hit = [r for r in reqs if r.req_id.endswith("latitude-TYPE")][0]
    assert hit.text == "Custom: latitude is float64."


def test_signal_suppress_drops_requirement():
    model, _h, _w = load(DEMO)
    cfg = default_config()
    from reqgen.config_schema import SignalOverride
    key = "IF-NAV-STATE/POSITION/latitude"
    cfg.signals[key] = SignalOverride(suppress=["RANGE"])
    reqs = generate_requirements(model, cfg)
    assert not any(r.req_id.endswith("latitude-RANGE") for r in reqs)


# ---- reconciliation ----
def test_reconcile_four_states():
    mc, _h, _w = load(DEMO)
    mb, _h2, _w2 = load(REVB)
    cfg = default_config()
    current = generate_requirements(mc, cfg)
    prior_csv = to_csv(generate_requirements(mb, cfg), _prov())
    rec = reconcile(current, prior_csv)
    # revC adds a VELOCITY packet (vel_north etc.) and other signals not in B.
    assert rec.has_changes
    # vel_north exists in C, not B -> added
    assert any("vel_north" in i for i in rec.added)


def test_reconcile_identical_is_clean():
    model, _h, _w = load(DEMO)
    cfg = default_config()
    reqs = generate_requirements(model, cfg)
    rec = reconcile(reqs, to_csv(reqs, _prov()))
    assert not rec.has_changes
    assert len(rec.unchanged) == len(reqs)


# ---- provenance ----
def test_provenance_has_both_hashes():
    p = ReqProvenance.create("i" * 64, "c" * 64)
    banner = "\n".join(p.banner_lines())
    assert "i" * 64 in banner
    assert "c" * 64 in banner


# ---- config-location convention (baked into code) ----
def test_default_config_path_is_inside_reqgen_project(monkeypatch):
    """The default config lives at reqgen/config/reqgen.json — inside the reqgen
    project dir (parent of the package), not at the repo root."""
    from reqgen.paths import default_config_path, ENV_VAR
    import reqgen.paths as _paths
    monkeypatch.delenv(ENV_VAR, raising=False)
    got = default_config_path()
    pkg_dir = os.path.dirname(os.path.abspath(_paths.__file__))   # reqgen/reqgen
    proj = os.path.dirname(pkg_dir)                               # reqgen
    assert got == os.path.join(proj, "config", "reqgen.json")
    # It is under the reqgen project, and ends with config/reqgen.json.
    assert got.endswith(os.path.join("config", "reqgen.json"))


def test_default_config_path_env_override(tmp_path, monkeypatch):
    from reqgen.paths import default_config_path, ENV_VAR
    monkeypatch.setenv(ENV_VAR, "/custom/reqgen.json")
    assert default_config_path(str(tmp_path)) == "/custom/reqgen.json"


def test_package_is_properly_nested():
    """Guard the double-nesting: reqgen.cli must import as an installed package
    (i.e. the modules live in reqgen/reqgen/, not flattened into reqgen/)."""
    import importlib
    assert importlib.import_module("reqgen.cli")
    assert importlib.import_module("reqgen.paths")
