"""HTTP API + static UI hosting."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from . import config, db, documents, llm, messaging, repository
from .models import ReviewAction, VendorSubmission
from .pipeline import STAGES, run_pipeline
from .validators import india

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vendor_onboarding.api")

executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pipeline")


def _ensure_samples() -> None:
    if (config.SAMPLE_DIR / "scenarios.json").exists():
        return
    try:
        import sys
        sys.path.insert(0, str(config.BACKEND_DIR))
        from scripts.generate_samples import main as generate
        generate()
    except Exception:
        log.exception("Could not generate sample data")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    repository.seed_vendor_master()
    stale = repository.mark_stale_runs_failed()
    if stale:
        log.warning("Marked %d interrupted run(s) as failed and routed to review", stale)
    _ensure_samples()
    log.info("LLM layer: %s", llm.describe())
    yield
    executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Vendor Onboarding Automation", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ helpers
async def _parse_submission_form(request: Request) -> Tuple[Dict[str, Any], List[Tuple[str, str, bytes]], Optional[str]]:
    form = await request.form()
    raw = form.get("data")
    if not isinstance(raw, str):
        raise HTTPException(400, "Missing 'data' field with the submission JSON")
    try:
        data = VendorSubmission.model_validate(json.loads(raw)).model_dump()
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(422, f"Submission JSON is malformed: {exc}")
    files: List[Tuple[str, str, bytes]] = []
    for slot in documents.DOCUMENT_SLOTS:
        upload = form.get(slot)
        if not isinstance(upload, UploadFile) or not upload.filename:
            continue
        content = await upload.read()
        if not content:
            continue
        if len(content) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{documents.DOCUMENT_SLOTS[slot]} is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        if not content.startswith(b"%PDF"):
            raise HTTPException(415, f"{documents.DOCUMENT_SLOTS[slot]} must be a PDF file ('{upload.filename}' is not)")
        files.append((slot, upload.filename, content))
    scenario = form.get("scenario_id")
    return data, files, scenario if isinstance(scenario, str) and scenario else None


def _safe_filename(name: str) -> str:
    base = Path(name).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120] or "document.pdf"


def _store_files(sid: str, version: int, files: List[Tuple[str, str, bytes]]) -> None:
    folder = config.UPLOAD_DIR / sid / f"v{version}"
    folder.mkdir(parents=True, exist_ok=True)
    for slot, filename, content in files:
        path = folder / f"{slot}__{_safe_filename(filename)}"
        path.write_bytes(content)
        repository.add_document(sid, version, slot, filename, str(path), hashlib.sha256(content).hexdigest(), len(content))


def _start_run(sid: str, version: int) -> str:
    run_id = repository.create_run(sid, version)
    executor.submit(run_pipeline, sid, version, run_id)
    return run_id


def _scenario_manifest() -> Dict[str, Any]:
    path = config.SAMPLE_DIR / "scenarios.json"
    if not path.exists():
        return {"scenarios": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _vendor_items(run: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not run:
        return []
    return [f for f in (run.get("findings") or [])
            if f.get("resolution") == "vendor" and f.get("severity") == "fail" and f.get("vendor_action")]


def _doc_view(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k != "path"}


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/api/config")
def get_config() -> Dict[str, Any]:
    return {
        "llm": llm.describe(),
        "stage_delay_seconds": config.STAGE_DELAY_SECONDS,
        "stages": [{"key": k, "label": l, "description": d} for k, l, d in STAGES],
        "document_slots": documents.DOCUMENT_SLOTS,
        "business_types": india.BUSINESS_TYPES,
        "states": india.INDIAN_STATES,
        "thresholds": {
            "review_risk": config.REVIEW_RISK_THRESHOLD,
            "bank_letter_max_age_days": config.BANK_LETTER_MAX_AGE_DAYS,
            "sanctions_review_score": config.SANCTIONS_REVIEW_SCORE,
            "sanctions_block_score": config.SANCTIONS_BLOCK_SCORE,
        },
        "buyer": config.BUYER_COMPANY,
    }


@app.get("/api/stats")
def get_stats() -> Dict[str, Any]:
    return repository.stats()


# ------------------------------------------------------------------ scenarios
@app.get("/api/scenarios")
def list_scenarios() -> Dict[str, Any]:
    manifest = _scenario_manifest()
    for sc in manifest.get("scenarios", []):
        sc["document_urls"] = {slot: f"/api/scenarios/{sc['id']}/files/{name}" for slot, name in sc["documents"].items()}
        if sc.get("fix"):
            sc["fix"]["document_urls"] = {slot: f"/api/scenarios/{sc['id']}/files/{name}"
                                          for slot, name in sc["fix"]["documents"].items()}
    return manifest


@app.get("/api/scenarios/{scenario_id}/files/{filename}")
def scenario_file(scenario_id: str, filename: str) -> FileResponse:
    for sc in _scenario_manifest().get("scenarios", []):
        if sc["id"] != scenario_id:
            continue
        allowed = set(sc["documents"].values()) | set((sc.get("fix") or {}).get("documents", {}).values())
        if filename in allowed:
            return FileResponse(config.SAMPLE_DIR / scenario_id / filename, media_type="application/pdf", filename=filename)
    raise HTTPException(404, "File not found")


# ------------------------------------------------------------------ submissions
@app.post("/api/submissions", status_code=201)
async def create_submission(request: Request) -> Dict[str, Any]:
    data, files, scenario = await _parse_submission_form(request)
    sid = await run_in_threadpool(repository.create_submission, data, scenario)
    await run_in_threadpool(_store_files, sid, 1, files)
    repository.audit(sid, "vendor", "submitted", {"documents": [f[0] for f in files], "scenario": scenario})
    run_id = _start_run(sid, 1)
    return {"submission_id": sid, "run_id": run_id}


@app.get("/api/submissions")
def list_submissions(status: Optional[str] = None, q: Optional[str] = Query(None, max_length=100)) -> List[Dict[str, Any]]:
    return repository.list_submissions(status, q)


@app.get("/api/submissions/{sid}")
def submission_detail(sid: str) -> Dict[str, Any]:
    sub = repository.get_submission(sid)
    if not sub:
        raise HTTPException(404, "Submission not found")
    runs = repository.runs_for(sid)
    latest = runs[0] if runs else None
    vendor_items = _vendor_items(latest)
    return {
        "submission": sub,
        "versions": repository.list_versions(sid),
        "runs": [{k: v for k, v in r.items() if k != "findings"} for r in runs],
        "latest_run": latest,
        "documents": [_doc_view(d) for d in repository.documents_for(sid, sub["current_version"])],
        "messages": repository.list_messages(sid),
        "audit": repository.audit_for(sid),
        "review": {
            "open_vendor_items": len(vendor_items),
            "can_approve": sub["status"] == "PENDING_REVIEW" and not vendor_items,
        },
        "portal_url": messaging.portal_url(sub),
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    run = repository.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.get("/api/runs/{run_id}/events")
async def stream_run_events(run_id: str, request: Request, after: int = 0) -> StreamingResponse:
    if not await run_in_threadpool(repository.get_run, run_id):
        raise HTTPException(404, "Run not found")
    header = request.headers.get("last-event-id")
    cursor = max(after, int(header) if header and header.isdigit() else 0)

    async def gen():
        nonlocal cursor
        idle = 0
        yield "retry: 1500\n\n"
        while True:
            if await request.is_disconnected():
                return
            events = await run_in_threadpool(repository.events_since, run_id, cursor)
            for e in events:
                cursor = e["seq"]
                yield f"id: {e['seq']}\ndata: {json.dumps(e, default=str)}\n\n"
                if e["type"] == "run_completed":
                    yield "event: end\ndata: {}\n\n"
                    return
            if not events:
                run = await run_in_threadpool(repository.get_run, run_id)
                if not run or run["status"] != "running":
                    await asyncio.sleep(0.3)
                    if not await run_in_threadpool(repository.events_since, run_id, cursor):
                        yield "event: end\ndata: {}\n\n"
                        return
                idle += 1
                if idle % 40 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/submissions/{sid}/rerun", status_code=202)
def rerun(sid: str) -> Dict[str, Any]:
    sub = repository.get_submission(sid)
    if not sub:
        raise HTTPException(404, "Submission not found")
    if sub["status"] == "PROCESSING":
        raise HTTPException(409, "A run is already in progress")
    if sub["status"] == "APPROVED":
        raise HTTPException(409, "Approved vendors are changed through change control, not re-runs")
    repository.update_submission(sid, status="PROCESSING")
    repository.audit(sid, "operator", "rerun_requested", {"version": sub["current_version"]})
    return {"submission_id": sid, "run_id": _start_run(sid, sub["current_version"])}


@app.get("/api/documents/{doc_id}/file")
def document_file(doc_id: int) -> FileResponse:
    doc = repository.get_document(doc_id)
    if not doc or not Path(doc["path"]).exists():
        raise HTTPException(404, "Document not found")
    return FileResponse(doc["path"], media_type="application/pdf", filename=doc["filename"],
                        content_disposition_type="inline")


# ------------------------------------------------------------------ review
@app.get("/api/review-queue")
def review_queue() -> List[Dict[str, Any]]:
    items = repository.list_submissions("PENDING_REVIEW")
    for item in items:
        run = repository.latest_run(item["id"])
        flags = [f for f in (run or {}).get("findings") or []
                 if f.get("resolution") in ("review", "reject") and f.get("severity") in ("warn", "fail")]
        item["flags"] = [{"title": f["title"], "stage": f["stage"], "code": f["code"]} for f in flags]
        item["open_vendor_items"] = len(_vendor_items(run))
    return items


@app.post("/api/submissions/{sid}/review")
def review(sid: str, body: ReviewAction) -> Dict[str, Any]:
    sub = repository.get_submission(sid)
    if not sub:
        raise HTTPException(404, "Submission not found")
    if sub["status"] != "PENDING_REVIEW":
        raise HTTPException(409, f"Only submissions pending internal review can be actioned (status is {sub['status']})")
    run = repository.latest_run(sid)
    data = repository.get_version_data(sid, sub["current_version"]) or {}
    vendor_items = _vendor_items(run)
    actor = f"reviewer:{body.reviewer.strip()}"

    if body.action == "approve":
        if vendor_items:
            raise HTTPException(409, f"Cannot approve: {len(vendor_items)} vendor-fixable issue(s) are still open. "
                                     "Use 'Request info' so the vendor fixes them first.")
        tax, bank, company = data.get("tax") or {}, data.get("bank") or {}, data.get("company") or {}
        code = repository.create_vendor(sid, company.get("legal_name") or "", india.clean_id(tax.get("pan")),
                                        india.clean_id(tax.get("gstin")) or None,
                                        india.clean_id(bank.get("account_number")) or None,
                                        india.clean_id(bank.get("ifsc")) or None)
        reason = f"Approved by {body.reviewer} after review — {body.note}"
        repository.update_submission(sid, status="APPROVED", decided_by=actor, vendor_code=code, decision_reason=reason)
        draft = messaging.approval({**sub, "vendor_code": code}, data, code)
    elif body.action == "reject":
        reason = f"Rejected by {body.reviewer} after review — {body.note}"
        repository.update_submission(sid, status="REJECTED", decided_by=actor, decision_reason=reason)
        draft = messaging.rejection(sub, data, [], body.vendor_note)
    else:
        if not vendor_items and not (body.vendor_note or "").strip():
            raise HTTPException(422, "Nothing to request: there are no vendor-fixable findings, so add a note to the vendor.")
        reason = f"Information requested by {body.reviewer} — {body.note}"
        repository.update_submission(sid, status="PENDING_VENDOR", decided_by=actor, decision_reason=reason)
        draft = messaging.info_request(sub, data, vendor_items, body.vendor_note)

    repository.add_message(sid, run["id"] if run else None, draft["audience"], draft["kind"], draft["to"],
                           draft["subject"], draft["body"], draft.get("action_url"), draft["engine"])
    repository.audit(sid, actor, f"review_{body.action}", {"note": body.note, "vendor_note": body.vendor_note,
                                                           "run_id": run["id"] if run else None})
    return {"ok": True, "submission": repository.get_submission(sid)}


# ------------------------------------------------------------------ outbox / vendors
@app.get("/api/outbox")
def outbox() -> List[Dict[str, Any]]:
    return repository.list_messages()


@app.get("/api/vendors")
def vendors() -> List[Dict[str, Any]]:
    return repository.list_vendors()


# ------------------------------------------------------------------ vendor portal
PORTAL_STATUS_TEXT = {
    "PROCESSING": "We're checking your submission now. This usually takes under a minute.",
    "PENDING_VENDOR": "We need a few updates from you before we can complete your registration.",
    "PENDING_REVIEW": "Your registration is with our team for a final verification step. No action is needed from you.",
    "APPROVED": "Your registration is approved.",
    "REJECTED": "We're unable to approve this registration. Please check your email for details.",
}


@app.get("/api/portal/{token}")
def portal_view(token: str) -> Dict[str, Any]:
    sub = repository.get_submission_by_token(token)
    if not sub:
        raise HTTPException(404, "This link is invalid or has expired")
    can_resubmit = sub["status"] == "PENDING_VENDOR"
    items = _vendor_items(repository.latest_run(sub["id"])) if can_resubmit else []
    return {
        "submission_id": sub["id"],
        "legal_name": sub["legal_name"],
        "status": sub["status"],
        "status_text": PORTAL_STATUS_TEXT.get(sub["status"], ""),
        "vendor_code": sub["vendor_code"] if sub["status"] == "APPROVED" else None,
        "can_resubmit": can_resubmit,
        "requested": [{"field": f.get("field"), "title": f["title"], "action": f["vendor_action"], "hint": f.get("hint")}
                      for f in items],
        "form": repository.get_version_data(sub["id"], sub["current_version"]) if can_resubmit else None,
        "documents": [{"slot": d["slot"], "filename": d["filename"]}
                      for d in repository.documents_for(sub["id"], sub["current_version"])] if can_resubmit else [],
        "scenario_id": sub["scenario_id"],
    }


@app.post("/api/portal/{token}/resubmit", status_code=201)
async def portal_resubmit(token: str, request: Request) -> Dict[str, Any]:
    sub = await run_in_threadpool(repository.get_submission_by_token, token)
    if not sub:
        raise HTTPException(404, "This link is invalid or has expired")
    if sub["status"] != "PENDING_VENDOR":
        raise HTTPException(409, "This submission isn't waiting for updates")
    data, files, _ = await _parse_submission_form(request)
    sid = sub["id"]
    previous = sub["current_version"]
    version = await run_in_threadpool(repository.add_version, sid, data, "vendor_portal")
    await run_in_threadpool(_store_files, sid, version, files)
    await run_in_threadpool(repository.carry_over_documents, sid, previous, version, [f[0] for f in files])
    repository.audit(sid, "vendor", "resubmitted", {"version": version, "replaced_documents": [f[0] for f in files]})
    run_id = _start_run(sid, version)
    return {"submission_id": sid, "run_id": run_id, "version": version}


# ------------------------------------------------------------------ admin
@app.post("/api/admin/reset")
def reset() -> Dict[str, Any]:
    if repository.list_submissions("PROCESSING"):
        raise HTTPException(409, "Wait for running pipelines to finish before resetting")
    repository.reset_all()
    return {"ok": True}


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


# ------------------------------------------------------------------ UI
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (config.FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and config.FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        # index.html references content-hashed bundles, so it must never be served stale after a rebuild.
        return FileResponse(config.FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
