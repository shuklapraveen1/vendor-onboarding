"""Runs every demo scenario through the real HTTP API and pipeline."""
import json
import time
from typing import Any, Dict, Optional

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/api/admin/reset")
        yield c


def _scenarios(client) -> Dict[str, Any]:
    return {s["id"]: s for s in client.get("/api/scenarios").json()["scenarios"]}


def _files(scenario_id: str, docs: Dict[str, str]):
    return {slot: (name, (config.SAMPLE_DIR / scenario_id / name).read_bytes(), "application/pdf") for slot, name in docs.items()}


def _wait(client, run_id: str, timeout: float = 30) -> Dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def _submit(client, sc: Dict[str, Any], form: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    resp = client.post("/api/submissions", data={"data": json.dumps(form or sc["form"]), "scenario_id": sc["id"]},
                       files=_files(sc["id"], sc["documents"]))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    run = _wait(client, body["run_id"])
    return {**body, "run": run}


def _codes(run, severity=("fail", "warn")):
    return {f["code"] for f in run["findings"] if f["severity"] in severity}


def test_happy_path_approved(client):
    sc = _scenarios(client)["01-happy-path"]
    out = _submit(client, sc)
    run = out["run"]
    assert run["decision"] == "APPROVED", run["decision_reason"]
    assert _codes(run) == set()
    detail = client.get(f"/api/submissions/{out['submission_id']}").json()
    assert detail["submission"]["vendor_code"].startswith("VEND-")
    assert any(m["kind"] == "approval" for m in detail["messages"])
    stages = [s["stage"] for s in run["summary"]["stages"]]
    assert stages[0] == "intake" and stages[-1] == "notify" and len(stages) == 11


def test_resubmitting_happy_path_is_duplicate(client):
    sc = _scenarios(client)["01-happy-path"]
    run = _submit(client, sc)["run"]
    assert run["decision"] == "REJECTED"
    assert "DUPLICATE_VENDOR" in _codes(run)


def test_incomplete_then_fixed_via_portal(client):
    sc = _scenarios(client)["02-incomplete-then-fixed"]
    out = _submit(client, sc)
    run = out["run"]
    assert run["decision"] == "PENDING_VENDOR"
    codes = _codes(run)
    assert {"INVALID_GSTIN", "MISSING_FIELD", "MISSING_DOCUMENT"} <= codes
    gst = next(f for f in run["findings"] if f["code"] == "INVALID_GSTIN")
    assert "27AAKCS7731Q1ZH" in (gst["hint"] or "")

    detail = client.get(f"/api/submissions/{out['submission_id']}").json()
    request_msg = next(m for m in detail["messages"] if m["kind"] == "info_request")
    token = request_msg["action_url"].rsplit("/", 1)[1]
    assert "27AAKCS7731Q1ZH" in request_msg["body"]

    portal = client.get(f"/api/portal/{token}").json()
    assert portal["can_resubmit"] and len(portal["requested"]) >= 3

    fix = sc["fix"]
    resp = client.post(f"/api/portal/{token}/resubmit", data={"data": json.dumps(fix["form"])},
                       files=_files(sc["id"], fix["documents"]))
    assert resp.status_code == 201, resp.text
    run2 = _wait(client, resp.json()["run_id"])
    assert run2["decision"] == "APPROVED", run2["decision_reason"]
    assert run2["version"] == 2
    docs = client.get(f"/api/submissions/{out['submission_id']}").json()["documents"]
    assert {d["slot"] for d in docs} == {"gst_certificate", "pan_card", "incorporation_certificate", "bank_proof"}
    assert sum(d["carried_over"] for d in docs) == 3

    assert client.get(f"/api/portal/{token}").json()["can_resubmit"] is False


def test_wrong_and_stale_documents(client):
    run = _submit(client, _scenarios(client)["03-wrong-and-stale-documents"])["run"]
    assert run["decision"] == "PENDING_VENDOR"
    assert {"DOC_WRONG_TYPE", "BANK_LETTER_STALE", "DUPLICATE_FILE"} <= _codes(run)


def test_tax_state_cross_field(client):
    run = _submit(client, _scenarios(client)["04-tax-state-cross-field"])["run"]
    assert run["decision"] == "PENDING_VENDOR"
    codes = _codes(run)
    assert {"GST_STATE_MISMATCH", "CIN_YEAR_MISMATCH"} <= codes
    assert not any(c.startswith("INVALID_") for c in codes)


def test_bank_account_belongs_to_someone_else(client):
    out = _submit(client, _scenarios(client)["05-bank-account-not-vendor"])
    run = out["run"]
    assert run["decision"] == "PENDING_REVIEW"
    assert "PENNY_DROP_MISMATCH" in _codes(run)
    msgs = client.get(f"/api/submissions/{out['submission_id']}").json()["messages"]
    vendor_msg = next(m for m in msgs if m["audience"] == "vendor")
    body = vendor_msg["body"].lower()
    assert "enterprises" not in body and "fraud" not in body and "bank" not in body
    assert vendor_msg["kind"] == "under_review"
    assert any(m["audience"] == "internal" and "RAVI KUMAR" in m["body"] for m in msgs)


def test_existing_vendor_new_bank(client):
    run = _submit(client, _scenarios(client)["06-existing-vendor-new-bank"])["run"]
    assert run["decision"] == "PENDING_REVIEW"
    assert {"TAX_ID_REUSED", "GST_NAME_MISMATCH"} <= _codes(run)


def test_sanctions_near_match_then_reviewer_clears(client):
    out = _submit(client, _scenarios(client)["07-sanctions-near-match"])
    run = out["run"]
    assert run["decision"] == "PENDING_REVIEW"
    assert "SANCTIONS_POTENTIAL" in _codes(run) and "SANCTIONS_MATCH" not in _codes(run)
    sid = out["submission_id"]
    bad = client.post(f"/api/submissions/{sid}/review", json={"action": "approve", "reviewer": "Priya", "note": "short"})
    assert bad.status_code == 422
    ok = client.post(f"/api/submissions/{sid}/review", json={
        "action": "approve", "reviewer": "Priya (Compliance)",
        "note": "False positive: listed entity is a UAE FZE, vendor is an Indian Pvt Ltd with different PAN and directors."})
    assert ok.status_code == 200, ok.text
    sub = ok.json()["submission"]
    assert sub["status"] == "APPROVED" and sub["decided_by"].startswith("reviewer:")
    audit = client.get(f"/api/submissions/{sid}").json()["audit"]
    assert any(a["action"] == "review_approve" for a in audit)


def test_exact_duplicate_rejected(client):
    run = _submit(client, _scenarios(client)["08-exact-duplicate"])["run"]
    assert run["decision"] == "REJECTED"
    assert "DUPLICATE_VENDOR" in _codes(run)


def test_cancelled_gst_rejected_with_disclosed_reason(client):
    out = _submit(client, _scenarios(client)["09-cancelled-gst-struck-off"])
    assert out["run"]["decision"] == "REJECTED"
    assert {"GST_NOT_ACTIVE", "MCA_NOT_ACTIVE"} <= _codes(out["run"])
    msgs = client.get(f"/api/submissions/{out['submission_id']}").json()["messages"]
    assert "Cancelled" in next(m for m in msgs if m["kind"] == "rejection")["body"]


def test_reviewer_cannot_approve_with_open_vendor_items(client):
    sc = _scenarios(client)["05-bank-account-not-vendor"]
    form = json.loads(json.dumps(sc["form"]))
    form["contact"]["email"] = "not-an-email"
    form["tax"]["pan"] = "AAFCT5567R "
    run = _submit(client, sc, form)["run"]
    sid = run["submission_id"]
    assert run["decision"] == "PENDING_REVIEW"
    resp = client.post(f"/api/submissions/{sid}/review", json={
        "action": "approve", "reviewer": "Priya", "note": "Looks fine to me honestly"})
    assert resp.status_code == 409
    resp = client.post(f"/api/submissions/{sid}/review", json={
        "action": "request_info", "reviewer": "Priya", "note": "Need corrected email before anything else"})
    assert resp.status_code == 200
    assert resp.json()["submission"]["status"] == "PENDING_VENDOR"


def test_empty_submission_is_accepted_and_explained(client):
    resp = client.post("/api/submissions", data={"data": json.dumps({})})
    assert resp.status_code == 201
    run = _wait(client, resp.json()["run_id"])
    assert run["decision"] == "PENDING_VENDOR"
    assert len([f for f in run["findings"] if f["code"] == "MISSING_FIELD"]) >= 10


def test_non_pdf_upload_rejected(client):
    resp = client.post("/api/submissions", data={"data": "{}"},
                       files={"pan_card": ("pan.jpg", b"\xff\xd8\xff\xe0 not a pdf", "image/jpeg")})
    assert resp.status_code == 415


def test_sse_stream_replays_events(client):
    sc = _scenarios(client)["03-wrong-and-stale-documents"]
    out = _submit(client, sc)
    with client.stream("GET", f"/api/runs/{out['run_id']}/events") as resp:
        body = "".join(chunk for chunk in resp.iter_text())
    assert '"type": "run_started"' in body and '"type": "run_completed"' in body and "event: end" in body


def test_stats(client):
    stats = client.get("/api/stats").json()
    assert stats["total"] >= 9
    assert stats["top_issues"]
