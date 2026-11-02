"""Document reading: text extraction, classification and field extraction.

Strategy: deterministic first, LLM for the long tail.
  1. pypdf text extraction (no text => likely a scanned image => ask vendor).
  2. Keyword-weighted classification, independent of the slot the vendor
     uploaded into — that's how "wrong document in the GST slot" is caught.
  3. Regex field extraction for the known government/bank templates.
  4. If required fields are still missing and an LLM key is configured, the
     LLM fills only the gaps. Its output is re-validated with the same format
     validators; anything that fails is discarded, never trusted.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader

from . import llm
from .validators import india

DOCUMENT_SLOTS: Dict[str, str] = {
    "gst_certificate": "GST Registration Certificate (Form GST REG-06)",
    "pan_card": "PAN Card",
    "bank_proof": "Cancelled Cheque or Bank Confirmation Letter",
    "incorporation_certificate": "Certificate of Incorporation",
    "msme_certificate": "Udyam (MSME) Registration Certificate",
}

_KEYWORDS: Dict[str, List[Tuple[str, int]]] = {
    "gst_certificate": [
        ("GST REG-06", 5),
        ("GOODS AND SERVICES TAX", 3),
        ("REGISTRATION CERTIFICATE", 1),
        ("DATE OF LIABILITY", 3),
        ("CONSTITUTION OF BUSINESS", 2),
        ("LEGAL NAME", 1),
    ],
    "pan_card": [
        ("INCOME TAX DEPARTMENT", 5),
        ("PERMANENT ACCOUNT NUMBER", 5),
    ],
    "bank_proof": [
        ("CANCELLED", 3),
        ("TO WHOM IT MAY CONCERN", 2),
        ("MICR", 2),
        ("IFSC", 2),
        ("A/C NO", 2),
        ("ACCOUNT NUMBER", 1),
        ("BRANCH MANAGER", 2),
        ("AUTHORISED SIGNATORY", 1),
    ],
    "incorporation_certificate": [
        ("CERTIFICATE OF INCORPORATION", 5),
        ("CORPORATE IDENTITY NUMBER", 4),
        ("REGISTRAR OF COMPANIES", 3),
        ("COMPANIES ACT", 2),
    ],
    "msme_certificate": [
        ("UDYAM REGISTRATION", 5),
        ("MICRO, SMALL AND MEDIUM", 4),
        ("NAME OF ENTERPRISE", 3),
        ("TYPE OF ENTERPRISE", 2),
    ],
}

REQUIRED_FIELDS: Dict[str, List[str]] = {
    "gst_certificate": ["gstin", "legal_name"],
    "pan_card": ["pan", "name"],
    "bank_proof": ["account_number", "ifsc"],
    "incorporation_certificate": ["cin", "company_name"],
    "msme_certificate": ["udyam_number", "enterprise_name"],
}

_ID_PATTERNS = {
    "gstin": re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"),
    "pan": re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b"),
    "ifsc": re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b"),
    "cin": re.compile(r"\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b"),
    "udyam_number": re.compile(r"\b(UDYAM-[A-Z]{2}-\d{2}-\d{7})\b"),
}

_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y")


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    value = value.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def extract_text(path: Path) -> Tuple[str, Optional[str], int]:
    """Return (text, error, page_count)."""
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return "", "PDF is password-protected", 0
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages), None, len(pages)
    except Exception as exc:
        return "", f"Could not open PDF: {exc.__class__.__name__}", 0


def classify(text: str) -> Tuple[str, int, Dict[str, int]]:
    upper = text.upper()
    scores = {
        doc_type: sum(weight for kw, weight in kws if kw in upper)
        for doc_type, kws in _KEYWORDS.items()
    }
    best = max(scores, key=lambda k: scores[k])
    if scores[best] < 4:
        return "unknown", scores[best], scores
    return best, scores[best], scores


def _label_value(lines: List[str], *labels: str) -> Optional[str]:
    for label in labels:
        pattern = re.compile(rf"{label}\s*[:\-]\s*(.+)$", re.IGNORECASE)
        for line in lines:
            m = pattern.search(line)
            if m and m.group(1).strip():
                return m.group(1).strip()
    return None


def _next_line_after(lines: List[str], label: str) -> Optional[str]:
    for i, line in enumerate(lines):
        if line.strip().lower() == label.lower() and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt:
                return nxt
    return None


def _first_id(kind: str, text: str) -> Optional[str]:
    m = _ID_PATTERNS[kind].search(text.upper())
    return m.group(1) if m else None


def _parse_gst(lines: List[str], text: str) -> Dict[str, Any]:
    return {
        "gstin": _first_id("gstin", _label_value(lines, "Registration Number") or text),
        "legal_name": _label_value(lines, r"Legal Name(?: of Business)?"),
        "trade_name": _label_value(lines, r"Trade Name(?:, if any)?"),
        "constitution": _label_value(lines, "Constitution of Business"),
        "address": _label_value(lines, r"Address of Principal Place of\s*Business"),
        "date_of_liability": _label_value(lines, "Date of Liability"),
    }


def _parse_pan(lines: List[str], text: str) -> Dict[str, Any]:
    name = _label_value(lines, "Name") or _next_line_after(lines, "Name")
    return {
        "pan": _first_id("pan", _label_value(lines, "Permanent Account Number") or text),
        "name": name,
        "date": _label_value(lines, r"Date of (?:Incorporation/Formation|Birth|Incorporation)")
        or _next_line_after(lines, "Date of Incorporation/Formation"),
    }


def _parse_bank(lines: List[str], text: str) -> Dict[str, Any]:
    upper = text.upper()
    subtype = "letter" if ("TO WHOM IT MAY CONCERN" in upper or "THIS IS TO CERTIFY" in upper) else "cheque"
    account = _label_value(lines, r"A/c No\.?", "Account Number", r"Account No\.?")
    account = re.sub(r"\D", "", account) if account else None
    holder = _label_value(lines, "Account Holder Name", r"A/c Name", "Account Name")
    if not holder:
        for i, line in enumerate(lines):
            if re.search(r"Authori[sz]ed Signator", line, re.IGNORECASE) and i > 0:
                holder = lines[i - 1].strip() or None
                break
    bank_name = lines[0].strip() if lines else None
    return {
        "subtype": subtype,
        "bank_name": bank_name,
        "ifsc": _first_id("ifsc", _label_value(lines, "IFSC(?: Code)?") or text),
        "account_number": account,
        "account_holder_name": holder,
        "document_date": _label_value(lines, "Date") if subtype == "letter" else None,
    }


def _parse_coi(lines: List[str], text: str) -> Dict[str, Any]:
    flat = re.sub(r"\s+", " ", text)
    m = re.search(r"certify that\s+(?:M/s\.?\s+)?(.+?)\s+is incorporated", flat, re.IGNORECASE)
    return {
        "cin": _first_id("cin", flat),
        "company_name": m.group(1).strip() if m else _label_value(lines, "Name of the Company"),
        "date_of_incorporation": _label_value(lines, "Date of Incorporation"),
        "roc": _label_value(lines, "Registrar of Companies"),
    }


def _parse_msme(lines: List[str], text: str) -> Dict[str, Any]:
    return {
        "udyam_number": _first_id("udyam_number", text),
        "enterprise_name": _label_value(lines, "Name of Enterprise"),
        "enterprise_type": _label_value(lines, "Type of Enterprise"),
        "registration_date": _label_value(lines, "Date of Udyam Registration"),
    }


_PARSERS = {
    "gst_certificate": _parse_gst,
    "pan_card": _parse_pan,
    "bank_proof": _parse_bank,
    "incorporation_certificate": _parse_coi,
    "msme_certificate": _parse_msme,
}

_FIELD_VALIDATORS = {
    "gstin": india.validate_gstin,
    "pan": india.validate_pan,
    "ifsc": india.validate_ifsc,
    "cin": india.validate_cin,
    "udyam_number": india.validate_udyam,
    "account_number": india.validate_account_number,
}


def _validate_fields(fields: Dict[str, Any], issues: List[str], source: str) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in fields.items():
        if value in (None, ""):
            continue
        if isinstance(value, str):
            value = value.strip()
        validator = _FIELD_VALIDATORS.get(key)
        if validator:
            res = validator(value)
            if not res.valid:
                issues.append(f"{source} read {key}='{value}' but it failed validation ({res.reason}); ignored")
                continue
            value = res.value
        clean[key] = value
    return clean


def _llm_fill(doc_type: str, text: str, missing: List[str]) -> Optional[Dict[str, Any]]:
    system = (
        "You extract fields from Indian business documents. Return ONLY a JSON object. "
        "Use null for anything not literally present in the text. Never guess or invent values."
    )
    user = (
        f"Document type: {DOCUMENT_SLOTS.get(doc_type, doc_type)}\n"
        f"Return JSON with exactly these keys: {missing}\n\n"
        f"Document text:\n\"\"\"\n{text[:6000]}\n\"\"\""
    )
    return llm.complete_json(system, user)


def _llm_classify(text: str) -> Optional[str]:
    system = "Classify Indian vendor-onboarding documents. Return JSON {\"document_type\": <one of the allowed values>}."
    allowed = list(DOCUMENT_SLOTS.keys()) + ["unknown"]
    out = llm.complete_json(system, f"Allowed values: {allowed}\n\nText:\n{text[:4000]}")
    value = (out or {}).get("document_type")
    return value if value in allowed else None


def analyse_document(path: Path, slot: str, filename: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "slot": slot,
        "slot_label": DOCUMENT_SLOTS.get(slot, slot),
        "filename": filename,
        "readable": False,
        "pages": 0,
        "text_chars": 0,
        "classified_as": "unknown",
        "classification_score": 0,
        "classification_engine": "parser",
        "fields": {},
        "field_sources": {},
        "issues": [],
        "engine": "parser",
        "text_preview": "",
    }
    text, error, pages = extract_text(path)
    result["pages"] = pages
    if error:
        result["issues"].append(error)
        return result
    stripped = text.strip()
    result["text_chars"] = len(stripped)
    result["text_preview"] = stripped[:600]
    if len(stripped) < 40:
        result["issues"].append("No machine-readable text found (likely a scanned image or blank page)")
        return result
    result["readable"] = True

    doc_type, score, _scores = classify(text)
    if doc_type == "unknown" and llm.provider():
        llm_type = _llm_classify(text)
        if llm_type:
            doc_type = llm_type
            result["classification_engine"] = "llm"
    result["classified_as"] = doc_type
    result["classification_score"] = score
    if doc_type == "unknown":
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    issues: List[str] = result["issues"]
    fields = _validate_fields(_PARSERS[doc_type](lines, text), issues, "Parser")
    sources = {k: "parser" for k in fields}

    missing = [f for f in REQUIRED_FIELDS[doc_type] if f not in fields]
    if missing and llm.provider():
        llm_out = _llm_fill(doc_type, text, missing)
        if llm_out:
            filled = _validate_fields({k: llm_out.get(k) for k in missing}, issues, "LLM")
            for k, v in filled.items():
                fields[k] = v
                sources[k] = "llm"
            if filled:
                result["engine"] = "parser+llm"

    result["fields"] = fields
    result["field_sources"] = sources
    result["missing_fields"] = [f for f in REQUIRED_FIELDS[doc_type] if f not in fields]
    return result
