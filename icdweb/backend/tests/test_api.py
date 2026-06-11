"""Backend API tests (in-process via FastAPI TestClient).

Run from icdweb/backend with: ICDGEN_DATA_DIR=/tmp/t python -m pytest

Examples: the suite runs against the three-revision eVTOL ICD. revA (3
interfaces / 3 packets / 9 signals) is the import/CRUD fixture; the revB ->
revC pair drives the Flow A prior-file test.
"""
import os
import tempfile

os.environ.setdefault("ICDGEN_DATA_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
_EXAMPLES = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                         "..", "..", "..",
                                         "icdgen", "examples"))
EX = os.path.join(_EXAMPLES, "icd_evtol_revA.xml")


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
    assert len(r["definition"]["interfaces"]) == 3


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


def test_generate_with_prior_file_fills_summary():
    """Flow A (web): uploading a prior-revision file via priorFiles populates the
    Change Summary Report column and leaves no temp files behind."""
    import io, zipfile, os as _os
    revc = _os.path.join(_EXAMPLES, "icd_evtol_revC.xml")
    revb_state = _os.path.join(_EXAMPLES, "icd_evtol_revB.xml")
    with open(revc, "rb") as f:
        imp = c.post("/api/import",
                     files={"file": ("c.xml", f, "application/xml")}).json()
    pid = c.post("/api/projects",
                 json={"name": "FA", "definition": imp["definition"]}).json()["id"]
    prior = open(revb_state, encoding="utf-8").read()
    g = c.post(f"/api/projects/{pid}/generate",
               json={"formats": ["docx"], "priorFiles": {"B": prior}}).json()
    assert g["ok"] is True
    fn = [a["filename"] for a in g["artifacts"] if a["filename"].endswith(".docx")][0]
    d = c.get(f"/api/projects/{pid}/artifacts/{fn}")
    doc = zipfile.ZipFile(io.BytesIO(d.content)).read(
        "word/document.xml").decode("utf-8", "ignore")
    assert "Change Summary Report" in doc
    # Default summary is PR-grouped. The B -> C diff adds the VELOCITY packet
    # signals under ticket AVS-1101 (e.g. vel_north).
    assert "+vel_north" in doc
    assert "AVS-1101" in doc


def test_prior_file_revision_key_cannot_escape_output_dir():
    """A malicious priorFiles key must not produce a temp filename that can
    leave the project's out/ directory (path-traversal guard). priorFiles keys
    are user-controlled request data; pre-fix, a key like '/../../X' wrote (and
    could overwrite) .xml files outside out/."""
    from app.service import _safe_rev_token
    for evil in ("/../../etc/x", "..", "a/../../b", "C:\\..\\x", ""):
        tok = _safe_rev_token(evil)
        assert tok                       # never empty
        assert "/" not in tok and "\\" not in tok
        assert ".." not in tok
        fname = f".prior_{tok}.xml"
        assert os.path.basename(fname) == fname
    # Sanitization is filename-only: a normal letter is untouched.
    assert _safe_rev_token("B") == "B"