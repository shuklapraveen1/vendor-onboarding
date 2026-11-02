"""Data-access functions. All SQL lives here."""
from __future__ import annotations

import secrets
import shutil
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import config
from .db import connection, dumps, row_to_dict, rows_to_dicts, utcnow
from .mock_services import seeded_vendor_master

OPEN_STATUSES = ("PROCESSING", "PENDING_VENDOR", "PENDING_REVIEW")


# ---------------------------------------------------------------- submissions
def _next_submission_id(conn) -> str:
    year = datetime.now().year
    row = conn.execute(
        "SELECT id FROM submissions WHERE id LIKE ? ORDER BY id DESC LIMIT 1", (f"VND-{year}-%",)
    ).fetchone()
    seq = int(row["id"].rsplit("-", 1)[1]) + 1 if row else 1
    return f"VND-{year}-{seq:04d}"


def _identity(data: Dict[str, Any]) -> Dict[str, Optional[str]]:
    company, tax, contact = data.get("company") or {}, data.get("tax") or {}, data.get("contact") or {}
    clean = lambda v: "".join(str(v).split()).upper() if v else None  # noqa: E731
    return {
        "legal_name": (company.get("legal_name") or "").strip() or None,
        "pan": clean(tax.get("pan")),
        "gstin": clean(tax.get("gstin")),
        "contact_email": (contact.get("email") or "").strip() or None,
    }


def create_submission(data: Dict[str, Any], scenario_id: Optional[str]) -> str:
    now = utcnow()
    ident = _identity(data)
    with connection() as conn:
        sid = _next_submission_id(conn)
        conn.execute(
            """INSERT INTO submissions (id, created_at, updated_at, status, legal_name, pan, gstin,
                   contact_email, current_version, portal_token, scenario_id)
               VALUES (?, ?, ?, 'PROCESSING', ?, ?, ?, ?, 1, ?, ?)""",
            (sid, now, now, ident["legal_name"], ident["pan"], ident["gstin"], ident["contact_email"],
             secrets.token_urlsafe(24), scenario_id),
        )
        conn.execute(
            "INSERT INTO submission_versions (submission_id, version, source, data_json, created_at) VALUES (?, 1, 'vendor_form', ?, ?)",
            (sid, dumps(data), now),
        )
    return sid


def add_version(sid: str, data: Dict[str, Any], source: str) -> int:
    now = utcnow()
    ident = _identity(data)
    with connection() as conn:
        row = conn.execute("SELECT current_version FROM submissions WHERE id = ?", (sid,)).fetchone()
        version = int(row["current_version"]) + 1
        conn.execute(
            "INSERT INTO submission_versions (submission_id, version, source, data_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (sid, version, source, dumps(data), now),
        )
        conn.execute(
            """UPDATE submissions SET current_version = ?, status = 'PROCESSING', updated_at = ?,
                   legal_name = ?, pan = ?, gstin = ?, contact_email = ? WHERE id = ?""",
            (version, now, ident["legal_name"], ident["pan"], ident["gstin"], ident["contact_email"], sid),
        )
    return version


def get_version_data(sid: str, version: int) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute(
            "SELECT data_json FROM submission_versions WHERE submission_id = ? AND version = ?", (sid, version)
        ).fetchone()
    return row_to_dict(row)["data"] if row else None  # type: ignore[index]


def list_versions(sid: str) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT version, source, data_json, created_at FROM submission_versions WHERE submission_id = ? ORDER BY version",
            (sid,),
        ).fetchall()
    return rows_to_dicts(rows)


def get_submission(sid: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM submissions WHERE id = ?", (sid,)).fetchone())


def get_submission_by_token(token: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM submissions WHERE portal_token = ?", (token,)).fetchone())


def update_submission(sid: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connection() as conn:
        conn.execute(f"UPDATE submissions SET {cols} WHERE id = ?", (*fields.values(), sid))


def list_submissions(status: Optional[str] = None, q: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = """SELECT s.*, (SELECT id FROM runs r WHERE r.submission_id = s.id ORDER BY started_at DESC LIMIT 1) AS latest_run_id,
                    (SELECT COUNT(*) FROM runs r WHERE r.submission_id = s.id) AS run_count
             FROM submissions s WHERE 1 = 1"""
    params: List[Any] = []
    if status:
        statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
        sql += f" AND s.status IN ({','.join('?' * len(statuses))})"
        params.extend(statuses)
    if q:
        like = f"%{q.strip()}%"
        sql += " AND (s.id LIKE ? OR s.legal_name LIKE ? OR s.pan LIKE ? OR s.gstin LIKE ? OR s.contact_email LIKE ?)"
        params.extend([like] * 5)
    sql += " ORDER BY s.created_at DESC"
    with connection() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def open_submissions_matching(pan: Optional[str], account: Optional[str], ifsc: Optional[str], exclude_sid: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    with connection() as conn:
        rows = conn.execute(
            f"""SELECT s.id, s.legal_name, s.pan, s.status, v.data_json FROM submissions s
                JOIN submission_versions v ON v.submission_id = s.id AND v.version = s.current_version
                WHERE s.id != ? AND s.status IN ({','.join('?' * len(OPEN_STATUSES))})""",
            (exclude_sid, *OPEN_STATUSES),
        ).fetchall()
    for row in rows_to_dicts(rows):
        bank = (row.get("data") or {}).get("bank") or {}
        other_acct = "".join(str(bank.get("account_number") or "").split())
        other_ifsc = "".join(str(bank.get("ifsc") or "").split()).upper()
        reasons = []
        if pan and row.get("pan") == pan:
            reasons.append("same PAN")
        if account and ifsc and other_acct == account and other_ifsc == ifsc:
            reasons.append("same bank account")
        if reasons:
            results.append({"id": row["id"], "legal_name": row["legal_name"], "status": row["status"], "reasons": reasons})
    return results


# ---------------------------------------------------------------- documents
def add_document(sid: str, version: int, slot: str, filename: str, path: str, sha256: str,
                 size: int, carried_over: bool = False, extraction: Optional[Dict[str, Any]] = None) -> int:
    with connection() as conn:
        cur = conn.execute(
            """INSERT INTO documents (submission_id, version, slot, filename, path, sha256, size_bytes,
                   carried_over, extraction_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sid, version, slot, filename, path, sha256, size, int(carried_over),
             dumps(extraction) if extraction else None, utcnow()),
        )
        return int(cur.lastrowid)


def documents_for(sid: str, version: int) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE submission_id = ? AND version = ? ORDER BY id", (sid, version)
        ).fetchall()
    return rows_to_dicts(rows)


def get_document(doc_id: int) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone())


def set_document_extraction(doc_id: int, extraction: Dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute("UPDATE documents SET extraction_json = ? WHERE id = ?", (dumps(extraction), doc_id))


def carry_over_documents(sid: str, from_version: int, to_version: int, replaced_slots: List[str]) -> None:
    for doc in documents_for(sid, from_version):
        if doc["slot"] in replaced_slots:
            continue
        add_document(sid, to_version, doc["slot"], doc["filename"], doc["path"], doc["sha256"],
                     doc["size_bytes"], carried_over=True)


# ---------------------------------------------------------------- runs/events
def create_run(sid: str, version: int) -> str:
    run_id = f"RUN-{uuid.uuid4().hex[:10].upper()}"
    with connection() as conn:
        conn.execute(
            "INSERT INTO runs (id, submission_id, version, status, started_at) VALUES (?, ?, ?, 'running', ?)",
            (run_id, sid, version, utcnow()),
        )
    return run_id


def append_event(run_id: str, seq: int, stage: Optional[str], type_: str, payload: Dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO run_events (run_id, seq, ts, stage, type, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, seq, utcnow(), stage, type_, dumps(payload)),
        )


def events_since(run_id: str, after_seq: int) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT seq, ts, stage, type, payload_json FROM run_events WHERE run_id = ? AND seq > ? ORDER BY seq",
            (run_id, after_seq),
        ).fetchall()
    return rows_to_dicts(rows)


def finish_run(run_id: str, *, status: str, decision: Optional[str], reason: Optional[str], risk: Optional[int],
               findings: List[Dict[str, Any]], summary: Dict[str, Any], engine: Dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(
            """UPDATE runs SET status = ?, finished_at = ?, decision = ?, decision_reason = ?, risk_score = ?,
                   findings_json = ?, summary_json = ?, engine_json = ? WHERE id = ?""",
            (status, utcnow(), decision, reason, risk, dumps(findings), dumps(summary), dumps(engine), run_id),
        )


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())


def runs_for(sid: str) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE submission_id = ? ORDER BY started_at DESC", (sid,)
        ).fetchall()
    return rows_to_dicts(rows)


def latest_run(sid: str) -> Optional[Dict[str, Any]]:
    runs = runs_for(sid)
    return runs[0] if runs else None


def mark_stale_runs_failed() -> int:
    """Runs left 'running' by a crashed/restarted server can never finish."""
    with connection() as conn:
        rows = conn.execute("SELECT id, submission_id FROM runs WHERE status = 'running'").fetchall()
        for row in rows:
            conn.execute(
                "UPDATE runs SET status = 'failed', finished_at = ?, decision = 'PENDING_REVIEW', "
                "decision_reason = 'Run interrupted by server restart; routed to manual review' WHERE id = ?",
                (utcnow(), row["id"]),
            )
            conn.execute(
                "UPDATE submissions SET status = 'PENDING_REVIEW', decision_reason = ?, updated_at = ? WHERE id = ? AND status = 'PROCESSING'",
                ("Run interrupted by server restart; routed to manual review", utcnow(), row["submission_id"]),
            )
    return len(rows)


# ---------------------------------------------------------------- messages
def add_message(sid: str, run_id: Optional[str], audience: str, kind: str, to_address: str,
                subject: str, body: str, action_url: Optional[str], engine: str) -> int:
    with connection() as conn:
        cur = conn.execute(
            """INSERT INTO messages (submission_id, run_id, created_at, audience, kind, to_address, subject,
                   body, action_url, engine) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sid, run_id, utcnow(), audience, kind, to_address, subject, body, action_url, engine),
        )
        return int(cur.lastrowid)


def list_messages(sid: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = "SELECT m.*, s.legal_name FROM messages m JOIN submissions s ON s.id = m.submission_id"
    params: List[Any] = []
    if sid:
        sql += " WHERE m.submission_id = ?"
        params.append(sid)
    sql += " ORDER BY m.id DESC"
    with connection() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())


# ---------------------------------------------------------------- audit
def audit(sid: Optional[str], actor: str, action: str, details: Optional[Dict[str, Any]] = None) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO audit_log (submission_id, ts, actor, action, details_json) VALUES (?, ?, ?, ?, ?)",
            (sid, utcnow(), actor, action, dumps(details or {})),
        )


def audit_for(sid: str) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM audit_log WHERE submission_id = ? ORDER BY id", (sid,)).fetchall()
    return rows_to_dicts(rows)


# ---------------------------------------------------------------- vendor master
def seed_vendor_master() -> None:
    with connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM vendor_master").fetchone()["n"]
        if count:
            return
        for v in seeded_vendor_master():
            conn.execute(
                """INSERT INTO vendor_master (vendor_code, legal_name, pan, gstin, account_number, ifsc, status,
                       source, submission_id, created_at) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', 'erp_seed', NULL, ?)""",
                (v["vendor_code"], v["legal_name"], v["pan"], v["gstin"], v["account_number"], v["ifsc"], utcnow()),
            )


def vendor_master_matches(pan: Optional[str], gstin: Optional[str], account: Optional[str],
                          ifsc: Optional[str], exclude_sid: str) -> List[Dict[str, Any]]:
    clauses, params = [], []
    if pan:
        clauses.append("pan = ?")
        params.append(pan)
    if gstin:
        clauses.append("gstin = ?")
        params.append(gstin)
    if account and ifsc:
        clauses.append("(account_number = ? AND ifsc = ?)")
        params.extend([account, ifsc])
    if not clauses:
        return []
    sql = f"SELECT * FROM vendor_master WHERE ({' OR '.join(clauses)}) AND (submission_id IS NULL OR submission_id != ?)"
    with connection() as conn:
        return rows_to_dicts(conn.execute(sql, (*params, exclude_sid)).fetchall())


def create_vendor(sid: str, legal_name: str, pan: str, gstin: Optional[str], account: Optional[str],
                  ifsc: Optional[str]) -> str:
    with connection() as conn:
        existing = conn.execute("SELECT vendor_code FROM vendor_master WHERE submission_id = ?", (sid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE vendor_master SET legal_name = ?, pan = ?, gstin = ?, account_number = ?, ifsc = ? WHERE vendor_code = ?",
                (legal_name, pan, gstin, account, ifsc, existing["vendor_code"]),
            )
            return existing["vendor_code"]
        row = conn.execute("SELECT vendor_code FROM vendor_master ORDER BY vendor_code DESC LIMIT 1").fetchone()
        seq = int(row["vendor_code"].split("-")[1]) + 1 if row else 1
        code = f"VEND-{seq:04d}"
        conn.execute(
            """INSERT INTO vendor_master (vendor_code, legal_name, pan, gstin, account_number, ifsc, status, source,
                   submission_id, created_at) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', 'onboarding', ?, ?)""",
            (code, legal_name, pan, gstin, account, ifsc, sid, utcnow()),
        )
        return code


def list_vendors() -> List[Dict[str, Any]]:
    with connection() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM vendor_master ORDER BY vendor_code").fetchall())


# ---------------------------------------------------------------- stats/admin
def stats() -> Dict[str, Any]:
    with connection() as conn:
        by_status = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM submissions GROUP BY status").fetchall()}
        runs = conn.execute(
            """SELECT COUNT(*) AS n,
                      AVG((julianday(finished_at) - julianday(started_at)) * 86400.0) AS avg_seconds
               FROM runs WHERE status = 'completed'"""
        ).fetchone()
        auto = conn.execute(
            "SELECT COUNT(*) AS n FROM submissions WHERE status IN ('APPROVED','REJECTED') AND decided_by = 'system'"
        ).fetchone()["n"]
        decided = conn.execute(
            "SELECT COUNT(*) AS n FROM submissions WHERE status IN ('APPROVED','REJECTED')"
        ).fetchone()["n"]
        top = conn.execute("SELECT findings_json FROM runs WHERE status = 'completed'").fetchall()
    issue_counts: Dict[str, Dict[str, Any]] = {}
    for row in top:
        for f in (row_to_dict(row) or {}).get("findings") or []:
            if f.get("severity") in ("fail", "warn"):
                entry = issue_counts.setdefault(f["code"], {"code": f["code"], "title": f["title"], "count": 0})
                entry["count"] += 1
    total = sum(by_status.values())
    return {
        "total": total,
        "by_status": by_status,
        "runs_completed": runs["n"] or 0,
        "avg_run_seconds": round(runs["avg_seconds"], 1) if runs["avg_seconds"] else None,
        "straight_through_rate": round(100 * auto / decided) if decided else None,
        "top_issues": sorted(issue_counts.values(), key=lambda x: -x["count"])[:6],
    }


def reset_all() -> None:
    with connection() as conn:
        for table in ("run_events", "runs", "documents", "messages", "audit_log", "submission_versions",
                      "submissions", "vendor_master"):
            conn.execute(f"DELETE FROM {table}")
    if config.UPLOAD_DIR.exists():
        # On Windows a file held open by a viewer or antivirus cannot be deleted; the DB rows are already gone.
        shutil.rmtree(config.UPLOAD_DIR, ignore_errors=True)
    config.ensure_dirs()
    seed_vendor_master()
