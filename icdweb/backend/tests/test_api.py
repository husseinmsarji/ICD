"""Backend API tests (in-process via FastAPI TestClient).

Run from icdweb/backend with: ICDGEN_DATA_DIR=/tmp/t python -m pytest
"""
import os
import tempfile

os.environ.setdefault("ICDGEN_DATA_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
EX = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                  "icdgen", "examples", "icd_example.xml")
EX = os.path.abspath(EX)


def _import_example():
    with open(EX, "rb") as f:
        r = c.post("/api/import", files={"file": ("icd.xml", f, "application/xml")})
    return r.json()


def test_health():
    assert c.get("/api/health").json()["status"] == "ok"


def test_options_lists_formats():
    o = c.get("/api/meta/options").json()
    assert "header" in o["artifactFormats"]
    assert "ARINC664" in o["busTypes"]


def test_import_valid_file():
    r = _import_example()
    assert r["ok"] is True
    assert len(r["definition"]["interfaces"]) == 1


def test_create_validate_generate_download():
    imp = _import_example()
    pid = c.post("/api/projects", json={"name": "T", "definition": imp["definition"]}).json()["id"]

    v = c.post(f"/api/projects/{pid}/validate").json()
    assert v["ok"] is True

    g = c.post(f"/api/projects/{pid}/generate", json={"formats": ["header", "trace-csv"]}).json()
    assert g["ok"] is True
    assert len(g["artifacts"]) == 2
    assert len(g["inputHash"]) == 64

    fname = [a["filename"] for a in g["artifacts"] if a["filename"].endswith(".h")][0]
    d = c.get(f"/api/projects/{pid}/artifacts/{fname}")
    assert d.status_code == 200
    assert b"#define" in d.content


def test_validation_failure_has_line():
    imp = _import_example()
    bad = imp["definition"]
    bad["metadata"]["documentId"] = ""
    pid = c.post("/api/projects", json={"name": "T2", "definition": imp["definition"]}).json()["id"]
    v = c.post(f"/api/projects/{pid}/validate", json={"definition": bad}).json()
    assert v["ok"] is False
    assert v["issues"][0]["line"] is not None


def test_diff_endpoint():
    import copy
    imp = _import_example()
    old = copy.deepcopy(imp["definition"])
    new = copy.deepcopy(imp["definition"])
    new["interfaces"][0]["packets"][0]["signals"][0]["rangeMax"] = 999
    r = c.post("/api/diff", json={"old": old, "new": new}).json()
    assert r["hasChanges"] is True
    assert r["modifiedSignals"][0]["changes"][0]["field"] == "range_max"


def test_path_traversal_blocked():
    imp = _import_example()
    pid = c.post("/api/projects", json={"name": "T3", "definition": imp["definition"]}).json()["id"]
    r = c.get(f"/api/projects/{pid}/artifacts/..%2F..%2Fproject.json")
    assert r.status_code == 404
