"""The onboarding pipeline.

Design rules:
  * Every stage runs, even after failures, so the vendor gets ONE
    consolidated list of what to fix instead of being drip-fed.
  * Checks only run on inputs that passed format validation, so one typo
    doesn't cascade into five confusing findings.
  * Every check emits a Finding with a `resolution` route:
        vendor  -> vendor can fix it            -> PENDING (awaiting vendor)
        review  -> needs a human / fraud signal -> PENDING (internal review)
        reject  -> disqualifying                -> REJECTED
  * Decisions are deterministic rules over findings. The LLM never decides.
  * Fail closed: an unexpected error routes to manual review, never approval.
"""
from __future__ import annotations

import logging
import time
import traceback
from dataclasses import asdict, dataclass, field as dc_field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import config, documents, llm, messaging, repository
from .matching import best_match, compare_names, normalize_name
from .mock_services import BankDirectory, GSTPortal, MCARegistry, PennyDrop, SanctionsScreening
from .validators import india

log = logging.getLogger("vendor_onboarding.pipeline")

STAGES = [
    ("intake", "Intake & completeness", "Mandatory fields and documents for the declared business type"),
    ("format", "Format validation", "GSTIN checksum, PAN, IFSC, CIN, Udyam and contact formats"),
    ("documents", "Document reading", "Extract text, classify each upload, pull key fields"),
    ("consistency", "Cross-field consistency", "PAN vs GSTIN, GST state vs address, PAN type vs constitution, CIN vs declared data"),
    ("doc_match", "Documents vs. form", "Do the uploaded documents say what the form says?"),
    ("registry", "Registry verification", "GST portal and MCA: registration status and registered name"),
    ("bank", "Bank verification", "IFSC directory and penny-drop account-holder name"),
    ("duplicates", "Duplicate & fraud checks", "Vendor master: same PAN, GSTIN or bank account"),
    ("sanctions", "Sanctions screening", "Entity and signatory names against the watchlist"),
    ("decision", "Decision", "Apply rules to all findings, score risk, set status"),
    ("notify", "Communication", "Draft the vendor message and any internal alert"),
]

FIELD_LABELS: Dict[str, str] = {
    "company.legal_name": "Legal name",
    "company.trade_name": "Trade name",
    "company.business_type": "Business type (constitution)",
    "company.date_of_incorporation": "Date of incorporation",
    "company.cin": "CIN (Corporate Identity Number)",
    "company.llpin": "LLPIN",
    "address.line1": "Registered address",
    "address.city": "City",
    "address.state": "State",
    "address.pincode": "PIN code",
    "tax.pan": "PAN",
    "tax.gstin": "GSTIN",
    "tax.udyam_number": "Udyam registration number",
    "bank.account_holder_name": "Bank account holder name",
    "bank.account_number": "Bank account number",
    "bank.confirm_account_number": "Confirm bank account number",
    "bank.ifsc": "IFSC code",
    "bank.bank_name": "Bank name",
    "contact.name": "Contact person name",
    "contact.email": "Contact email",
    "contact.phone": "Contact mobile number",
    "signatory.name": "Authorised signatory name",
}

BASE_REQUIRED_FIELDS = [
    "company.legal_name", "company.business_type", "address.line1", "address.city", "address.state",
    "address.pincode", "tax.pan", "tax.gstin", "bank.account_holder_name", "bank.account_number",
    "bank.confirm_account_number", "bank.ifsc", "contact.name", "contact.email", "contact.phone",
    "signatory.name",
]

COMPANY_TYPES = ("PRIVATE_LIMITED", "PUBLIC_LIMITED")

DEFAULT_WEIGHTS = {"reject": 100, "review": 40, "vendor": 10}


@dataclass
class Finding:
    code: str
    stage: str
    severity: str  # pass | info | warn | fail
    title: str
    detail: str = ""
    field: Optional[str] = None
    resolution: Optional[str] = None  # vendor | review | reject
    vendor_action: Optional[str] = None
    hint: Optional[str] = None
    weight: Optional[int] = None
    evidence: Dict[str, Any] = dc_field(default_factory=dict)

    @property
    def effective_weight(self) -> int:
        if self.severity not in ("warn", "fail"):
            return 0
        if self.weight is not None:
            return self.weight
        return DEFAULT_WEIGHTS.get(self.resolution or "", 5)

    @property
    def blocking(self) -> bool:
        if self.severity == "fail":
            return self.resolution in ("vendor", "review", "reject")
        return self.severity == "warn" and self.resolution in ("review", "reject")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["weight"] = self.effective_weight
        d["blocking"] = self.blocking
        return d


def _req_docs(business_type: Optional[str], msme: bool) -> List[str]:
    slots = ["gst_certificate", "pan_card", "bank_proof"]
    if business_type in COMPANY_TYPES or business_type == "LLP":
        slots.append("incorporation_certificate")
    if msme:
        slots.append("msme_certificate")
    return slots


class Pipeline:
    def __init__(self, submission_id: str, version: int, run_id: str) -> None:
        self.sid = submission_id
        self.version = version
        self.run_id = run_id
        self.data: Dict[str, Any] = repository.get_version_data(submission_id, version) or {}
        self.docs = repository.documents_for(submission_id, version)
        self.findings: List[Finding] = []
        self.valid: Dict[str, Any] = {}
        self.analyses: Dict[str, Dict[str, Any]] = {}
        self.usable_docs: Dict[str, Dict[str, Any]] = {}
        self.seq = 0
        self.decision: Optional[str] = None
        self.decision_reason: Optional[str] = None
        self.risk = 0
        self.vendor_code: Optional[str] = None
        self.stage_results: List[Dict[str, Any]] = []
        self.engine: Dict[str, Any] = {
            "llm": llm.describe(),
            "documents": {},
            "services": [GSTPortal.name, MCARegistry.name, BankDirectory.name, PennyDrop.name, SanctionsScreening.name],
        }
        self.check_delay = min(0.15, config.STAGE_DELAY_SECONDS / 4)

    # ------------------------------------------------------------ helpers
    def get(self, path: str) -> Any:
        node: Any = self.data
        for part in path.split("."):
            if not isinstance(node, dict):
                return None
            node = node.get(part)
        if isinstance(node, str):
            node = node.strip()
            return node or None
        return node

    def emit(self, type_: str, stage: Optional[str], payload: Dict[str, Any]) -> None:
        self.seq += 1
        repository.append_event(self.run_id, self.seq, stage, type_, payload)

    def add(self, finding: Finding) -> Finding:
        self.findings.append(finding)
        self.emit("check", finding.stage, finding.to_dict())
        if self.check_delay:
            time.sleep(self.check_delay)
        return finding

    def _f(self, stage: str) -> Callable[..., Finding]:
        def make(code: str, severity: str, title: str, **kw: Any) -> Finding:
            return self.add(Finding(code=code, stage=stage, severity=severity, title=title, **kw))
        return make

    def find(self, code: str, field_: Optional[str] = None) -> Optional[Finding]:
        for f in self.findings:
            if f.code == code and (field_ is None or f.field == field_):
                return f
        return None

    # ------------------------------------------------------------ orchestration
    def run(self) -> None:
        self.emit("run_started", None, {
            "submission_id": self.sid, "version": self.version,
            "stages": [{"key": k, "label": l, "description": d} for k, l, d in STAGES],
            "engine": self.engine,
        })
        repository.audit(self.sid, "system", "run_started", {"run_id": self.run_id, "version": self.version})
        for key, label, _desc in STAGES:
            self.emit("stage_started", key, {"label": label})
            before = len(self.findings)
            started = time.time()
            status_override = None
            try:
                getattr(self, f"stage_{key}")()
            except Exception as exc:  # fail closed
                log.exception("Stage %s failed", key)
                status_override = "error"
                self.add(Finding(
                    code="SYSTEM_ERROR", stage=key, severity="fail",
                    title=f"Internal error during '{label}'",
                    detail=f"{exc.__class__.__name__}: {exc}. Routed to manual review — the system never auto-approves when a check could not run.",
                    resolution="review", evidence={"trace": traceback.format_exc(limit=3)},
                ))
                if key == "decision":
                    self._fallback_decision()
            produced = self.findings[before:]
            result = {
                "stage": key,
                "label": label,
                "status": status_override or self._stage_status(produced),
                "counts": self._counts(produced),
                "duration_ms": int((time.time() - started) * 1000),
            }
            self.stage_results.append(result)
            self.emit("stage_completed", key, result)
            if config.STAGE_DELAY_SECONDS:
                time.sleep(config.STAGE_DELAY_SECONDS)

        findings = [f.to_dict() for f in self.findings]
        summary = {
            "counts": self._counts(self.findings),
            "stages": self.stage_results,
            "vendor_actions": len(self._vendor_actions()),
            "review_flags": len([f for f in self.findings if f.resolution == "review" and f.severity in ("warn", "fail")]),
        }
        repository.finish_run(
            self.run_id, status="completed", decision=self.decision, reason=self.decision_reason,
            risk=self.risk, findings=findings, summary=summary, engine=self.engine,
        )
        self.emit("run_completed", None, {"decision": self.decision, "reason": self.decision_reason, "risk_score": self.risk})
        repository.audit(self.sid, "system", "run_completed", {
            "run_id": self.run_id, "decision": self.decision, "risk_score": self.risk,
        })

    @staticmethod
    def _counts(items: List[Finding]) -> Dict[str, int]:
        out = {"pass": 0, "info": 0, "warn": 0, "fail": 0}
        for f in items:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    @staticmethod
    def _stage_status(items: List[Finding]) -> str:
        if not items:
            return "skipped"
        if any(f.severity == "fail" for f in items):
            return "fail"
        if any(f.severity == "warn" for f in items):
            return "warn"
        if all(f.severity == "info" for f in items):
            return "info"
        return "pass"

    def _vendor_actions(self) -> List[Finding]:
        return [f for f in self.findings if f.resolution == "vendor" and f.severity == "fail" and f.vendor_action]

    # ------------------------------------------------------------ stage 1
    def stage_intake(self) -> None:
        f = self._f("intake")
        bt = self.get("company.business_type")
        if bt and bt not in india.BUSINESS_TYPES:
            f("INVALID_BUSINESS_TYPE", "fail", "Business type not recognised", field="company.business_type",
              detail=f"'{bt}' is not one of: {', '.join(india.BUSINESS_TYPES.values())}",
              resolution="vendor", vendor_action="Select your business constitution (e.g. Private Limited Company, LLP).")
        required = list(BASE_REQUIRED_FIELDS)
        if bt in COMPANY_TYPES:
            required.append("company.cin")
        if bt == "LLP":
            required.append("company.llpin")
        if self.get("tax.msme_registered"):
            required.append("tax.udyam_number")

        missing = [p for p in required if not self.get(p)]
        for p in missing:
            label = FIELD_LABELS.get(p, p)
            f("MISSING_FIELD", "fail", f"Missing: {label}", field=p,
              detail=f"'{label}' is mandatory for a {india.BUSINESS_TYPES.get(bt or '', 'vendor')}.",
              resolution="vendor", vendor_action=f"Provide your {label}.")
        if not (self.data.get("declaration") or {}).get("accepted"):
            f("MISSING_DECLARATION", "fail", "Declaration not accepted", field="declaration.accepted",
              resolution="vendor", vendor_action="Accept the declaration that the information provided is true and complete.")

        required_docs = _req_docs(bt, bool(self.get("tax.msme_registered")))
        present = {d["slot"] for d in self.docs}
        missing_docs = [s for s in required_docs if s not in present]
        for slot in missing_docs:
            label = documents.DOCUMENT_SLOTS[slot]
            f("MISSING_DOCUMENT", "fail", f"Missing document: {label}", field=f"documents.{slot}",
              detail=f"Required for a {india.BUSINESS_TYPES.get(bt or '', 'vendor')}"
                     f"{' registered as MSME' if slot == 'msme_certificate' else ''}.",
              resolution="vendor", vendor_action=f"Upload your {label} (PDF).")

        by_hash: Dict[str, List[str]] = {}
        for d in self.docs:
            by_hash.setdefault(d["sha256"], []).append(d["slot"])
        for sha, slots in by_hash.items():
            if len(slots) > 1:
                names = " and ".join(documents.DOCUMENT_SLOTS.get(s, s) for s in slots)
                f("DUPLICATE_FILE", "warn", "Same file uploaded twice", weight=10,
                  detail=f"The identical file (sha256 {sha[:12]}…) was uploaded as {names}.",
                  evidence={"slots": slots})

        if not missing and not missing_docs:
            f("COMPLETENESS_OK", "pass", "Submission is complete",
              detail=f"All {len(required)} mandatory fields and {len(required_docs)} required documents are present "
                     f"for a {india.BUSINESS_TYPES.get(bt or '', 'vendor')}.")

    # ------------------------------------------------------------ stage 2
    def stage_format(self) -> None:
        f = self._f("format")

        def check(path: str, key: str, validator: Callable[[Any], india.ValidationResult], fmt_hint: str,
                  ok_detail: Callable[[india.ValidationResult], str]) -> None:
            raw = self.get(path)
            if not raw:
                return
            res = validator(raw)
            label = FIELD_LABELS.get(path, path)
            if res.valid:
                self.valid[key] = res.value
                f(f"VALID_{key.upper()}", "pass", f"{label} format is valid", field=path, detail=ok_detail(res),
                  evidence={"value": res.value, **res.details})
            else:
                f(f"INVALID_{key.upper()}", "fail", f"{label} is invalid", field=path,
                  detail=f"'{raw}': {res.reason}.", resolution="vendor",
                  vendor_action=f"Correct your {label}: {res.reason}. {fmt_hint}".strip(),
                  evidence={"value": raw, **res.details})

        check("tax.gstin", "gstin", india.validate_gstin, "Format: 2-digit state code + PAN + entity code + Z + check character.",
              lambda r: f"{r.value}: structure OK, state {r.details['state']}, check digit verified.")
        check("tax.pan", "pan", india.validate_pan, "Format: AAAAA9999A.",
              lambda r: f"{r.value}: holder type '{r.details['holder_type']}'.")
        check("bank.ifsc", "ifsc", india.validate_ifsc, "", lambda r: f"{r.value}: bank code {r.details['bank_code']}.")
        check("bank.account_number", "account", india.validate_account_number, "", lambda r: f"{india.mask_account(r.value)}")
        check("company.cin", "cin", india.validate_cin, "",
              lambda r: f"{r.value}: {r.details['listed']}, {r.details['ownership_label']}, RoC state {r.details['state']}, incorporated {r.details['year']}.")
        check("company.llpin", "llpin", india.validate_llpin, "", lambda r: r.value)
        if self.get("tax.msme_registered") or self.get("tax.udyam_number"):
            check("tax.udyam_number", "udyam", india.validate_udyam, "", lambda r: r.value)
        check("contact.email", "email", india.validate_email, "", lambda r: r.value)
        check("contact.phone", "phone", india.validate_phone, "", lambda r: f"+91 {r.value}")
        check("address.pincode", "pincode", india.validate_pincode, "", lambda r: r.value)

        acct, confirm = self.get("bank.account_number"), self.get("bank.confirm_account_number")
        if acct and confirm and india.clean_id(acct) != india.clean_id(confirm):
            self.valid.pop("account", None)
            f("ACCOUNT_CONFIRM_MISMATCH", "fail", "Account number and confirmation differ", field="bank.confirm_account_number",
              detail="The two account-number entries do not match, so we can't be sure which is correct.",
              resolution="vendor", vendor_action="Re-enter your bank account number; both entries must match exactly.")

        state = self.get("address.state")
        if state:
            if state in india.STATE_TO_GST_CODE:
                self.valid["state"] = state
            else:
                f("INVALID_STATE", "fail", "State not recognised", field="address.state", detail=f"'{state}'",
                  resolution="vendor", vendor_action="Select the state of your registered address from the list.")

        doi = self.get("company.date_of_incorporation")
        if doi:
            parsed = documents.parse_date(doi)
            if not parsed:
                f("INVALID_DOI", "fail", "Date of incorporation unreadable", field="company.date_of_incorporation",
                  detail=f"'{doi}'", resolution="vendor", vendor_action="Enter your date of incorporation as DD/MM/YYYY.")
            elif parsed > date.today():
                f("FUTURE_DOI", "fail", "Date of incorporation is in the future", field="company.date_of_incorporation",
                  detail=str(parsed), resolution="vendor", vendor_action="Correct your date of incorporation.")
            else:
                self.valid["doi"] = parsed

    # ------------------------------------------------------------ stage 3
    def stage_documents(self) -> None:
        f = self._f("documents")
        if not self.docs:
            f("NO_DOCUMENTS", "info", "No documents uploaded", detail="Nothing to read.")
            return
        for doc in self.docs:
            slot = doc["slot"]
            if slot not in documents.DOCUMENT_SLOTS:
                continue
            label = documents.DOCUMENT_SLOTS[slot]
            analysis = documents.analyse_document(Path(doc["path"]), slot, doc["filename"])
            analysis["document_id"] = doc["id"]
            repository.set_document_extraction(doc["id"], analysis)
            self.analyses[slot] = analysis
            self.engine["documents"][slot] = analysis["engine"]
            ev = {"document_id": doc["id"], "filename": doc["filename"], "fields": analysis["fields"],
                  "field_sources": analysis["field_sources"], "classified_as": analysis["classified_as"]}

            if not analysis["readable"]:
                f("DOC_UNREADABLE", "fail", f"{label}: cannot be read", field=f"documents.{slot}",
                  detail="; ".join(analysis["issues"]) or "No text extracted.",
                  resolution="vendor",
                  vendor_action=f"Re-upload your {label} as a clear, text-based PDF (downloaded from the issuing portal, not a phone photo).",
                  evidence=ev)
                continue
            if analysis["classified_as"] == "unknown":
                f("DOC_UNRECOGNISED", "fail", f"{label}: document not recognised", field=f"documents.{slot}",
                  detail="The file does not look like any accepted document type.",
                  resolution="vendor", vendor_action=f"Upload your {label} — the file you sent doesn't appear to be one.",
                  evidence=ev)
                continue
            if analysis["classified_as"] != slot:
                actual = documents.DOCUMENT_SLOTS.get(analysis["classified_as"], analysis["classified_as"])
                f("DOC_WRONG_TYPE", "fail", f"Wrong document in '{label}'", field=f"documents.{slot}",
                  detail=f"The file uploaded as {label} is actually a {actual}.",
                  resolution="vendor",
                  vendor_action=f"The file you uploaded as your {label} is a {actual}. Please upload the {label} itself.",
                  evidence=ev)
                continue

            self.usable_docs[slot] = analysis
            shown = ", ".join(f"{k}: {v}" for k, v in analysis["fields"].items() if k in documents.REQUIRED_FIELDS[slot])
            via = " (LLM-assisted)" if analysis["engine"] != "parser" else ""
            f("DOC_READ", "pass", f"{label} read{via}", field=f"documents.{slot}", detail=shown or "Fields extracted.", evidence=ev)
            if analysis.get("missing_fields"):
                f("DOC_FIELDS_UNREADABLE", "warn", f"{label}: some fields could not be read", field=f"documents.{slot}",
                  detail=f"Could not extract {', '.join(analysis['missing_fields'])}; the document needs a manual check.",
                  resolution="review", weight=15, evidence=ev)

    # ------------------------------------------------------------ stage 4
    def stage_consistency(self) -> None:
        f = self._f("consistency")
        bt = self.get("company.business_type")
        pan, gstin = self.valid.get("pan"), self.valid.get("gstin")
        legal = self.get("company.legal_name")

        if pan and gstin:
            embedded = gstin[2:12]
            if embedded == pan:
                f("PAN_GSTIN_MATCH", "pass", "GSTIN belongs to the declared PAN", detail=f"GSTIN characters 3-12 = {pan}.")
            else:
                f("PAN_GSTIN_MISMATCH", "fail", "GSTIN is registered under a different PAN", field="tax.gstin",
                  detail=f"GSTIN {gstin} embeds PAN {embedded}, but the declared PAN is {pan}. A GSTIN and PAN must belong to the same legal entity.",
                  resolution="vendor",
                  vendor_action=f"Your GSTIN {gstin} is registered under PAN {embedded}, not your declared PAN {pan}. Provide the GSTIN issued to PAN {pan}, or correct your PAN.",
                  evidence={"gstin_pan": embedded, "declared_pan": pan})

        state = self.valid.get("state")
        if gstin and state:
            gst_state = india.GST_STATE_CODES.get(gstin[:2])
            if gst_state == state:
                f("GST_STATE_MATCH", "pass", "GST state matches address", detail=f"State code {gstin[:2]} = {state}.")
            else:
                f("GST_STATE_MISMATCH", "fail", "GSTIN is from a different state than the address", field="tax.gstin",
                  detail=f"GSTIN state code {gstin[:2]} is {gst_state}, but the registered address is in {state}. GST is state-specific: invoices from {state} need a {state} GSTIN.",
                  resolution="vendor",
                  vendor_action=f"Your GSTIN is registered in {gst_state} but your address is in {state}. Provide the GSTIN for your {state} registration, or correct the address if you operate from {gst_state}.",
                  evidence={"gstin_state": gst_state, "address_state": state})

        if pan and bt in india.EXPECTED_PAN_TYPE:
            expected = india.EXPECTED_PAN_TYPE[bt]
            if pan[3] == expected:
                f("PAN_TYPE_MATCH", "pass", "PAN holder type matches constitution",
                  detail=f"4th character '{pan[3]}' = {india.PAN_HOLDER_TYPES[pan[3]]}, as expected for a {india.BUSINESS_TYPES[bt]}.")
            else:
                f("PAN_TYPE_MISMATCH", "fail", "PAN type doesn't match business type", field="tax.pan",
                  detail=f"PAN 4th character '{pan[3]}' means {india.PAN_HOLDER_TYPES.get(pan[3])}, but a {india.BUSINESS_TYPES[bt]} should have '{expected}' ({india.PAN_HOLDER_TYPES[expected]}). This usually means a director's or partner's personal PAN was entered.",
                  resolution="vendor",
                  vendor_action=f"The PAN you provided belongs to a {india.PAN_HOLDER_TYPES.get(pan[3])}, not a {india.BUSINESS_TYPES[bt]}. Provide the PAN issued to the business itself.",
                  evidence={"pan_type": pan[3], "expected": expected})

        if pan and legal and bt and bt != "PROPRIETORSHIP":
            first = (normalize_name(legal) or " ")[0]
            if first.isalpha() and pan[4] != first:
                f("PAN_NAME_INITIAL", "warn", "PAN 5th character doesn't match the name", field="tax.pan", weight=15,
                  detail=f"For entities the 5th PAN character is the first letter of the name. PAN has '{pan[4]}', name starts with '{first}'.",
                  evidence={"pan_char": pan[4], "name_initial": first})

        cin = self.valid.get("cin")
        if cin and bt in india.EXPECTED_CIN_TYPES:
            ownership = cin[12:15]
            if ownership not in india.EXPECTED_CIN_TYPES[bt]:
                f("CIN_TYPE_MISMATCH", "fail", "CIN company type doesn't match business type", field="company.cin",
                  detail=f"CIN ownership code {ownership} ({india.CIN_OWNERSHIP_TYPES.get(ownership)}) conflicts with declared {india.BUSINESS_TYPES[bt]}.",
                  resolution="vendor", vendor_action="Your CIN indicates a different company type than you selected. Correct the business type or the CIN.")
            doi = self.valid.get("doi")
            if doi and str(doi.year) != cin[8:12]:
                f("CIN_YEAR_MISMATCH", "fail", "Incorporation year differs from CIN", field="company.date_of_incorporation",
                  detail=f"CIN says {cin[8:12]}, form says {doi.year}.",
                  resolution="vendor", vendor_action=f"Your CIN shows incorporation in {cin[8:12]} but you entered {doi.year}. Correct the date of incorporation.")
            if state and india.CIN_STATE_CODES.get(cin[6:8]) != state:
                f("CIN_STATE_DIFFERS", "info", "Registered office state differs from address",
                  detail=f"CIN RoC state is {india.CIN_STATE_CODES.get(cin[6:8])}; operating address is in {state}. Common for multi-state businesses.")

        holder = self.get("bank.account_holder_name")
        if holder and legal:
            candidates = [legal, self.get("company.trade_name")]
            if bt == "PROPRIETORSHIP":
                candidates.append(self.get("signatory.name"))
            m = best_match(holder, candidates)
            ev = {"holder": holder, "legal_name": legal, "match": m.to_dict()}
            if m.is_match:
                f("PAYEE_NAME_MATCH", "pass", "Account holder name matches the vendor", detail=f"{m.explanation} (score {m.score}).", evidence=ev)
            elif m.verdict == "partial":
                f("PAYEE_NAME_PARTIAL", "warn", "Account holder name only partly matches", field="bank.account_holder_name",
                  weight=15, detail=f"'{holder}' vs '{legal}': {m.explanation} (score {m.score}).", evidence=ev)
            else:
                f("THIRD_PARTY_PAYEE", "fail", "Payments would go to a third party", field="bank.account_holder_name",
                  detail=f"Account holder '{holder}' is not the vendor '{legal}' (score {m.score}). Paying a third-party account is a top payment-fraud pattern.",
                  resolution="review", evidence=ev)

    # ------------------------------------------------------------ stage 5
    def stage_doc_match(self) -> None:
        f = self._f("doc_match")
        if not self.usable_docs:
            f("NO_USABLE_DOCS", "info", "No readable documents to cross-check")
            return
        legal = self.get("company.legal_name")

        def compare_id(slot: str, doc_field: str, form_path: str, valid_key: str, code: str) -> None:
            doc_value = self.usable_docs[slot]["fields"].get(doc_field)
            label, doc_label = FIELD_LABELS[form_path], documents.DOCUMENT_SLOTS[slot]
            if not doc_value:
                return
            form_valid = self.valid.get(valid_key)
            form_raw = india.clean_id(self.get(form_path))
            if form_valid and form_valid == doc_value:
                f(f"{code}_MATCH", "pass", f"{label} matches {doc_label}", detail=doc_value)
            elif form_valid:
                f(f"{code}_MISMATCH", "fail", f"{label} differs from {doc_label}", field=form_path,
                  detail=f"Form: {form_valid}; document: {doc_value}.", resolution="vendor",
                  vendor_action=f"The {label} you entered ({form_valid}) is different from the one on your {doc_label} ({doc_value}). Correct the form or upload the right document.",
                  evidence={"form": form_valid, "document": doc_value})
            elif form_raw:
                existing = self.find(f"INVALID_{valid_key.upper()}", form_path)
                if existing:
                    existing.hint = f"Your {doc_label} shows {doc_value} — did you mean that?"
                f(f"{code}_SUGGESTION", "info", f"{doc_label} shows a valid {label}",
                  detail=f"Form value '{form_raw}' is invalid; document shows {doc_value}. Added as a suggestion to the vendor request.",
                  evidence={"form": form_raw, "document": doc_value})

        def compare_name(slot: str, doc_field: str, against: Optional[str], code: str, what: str) -> None:
            doc_name = self.usable_docs[slot]["fields"].get(doc_field)
            doc_label = documents.DOCUMENT_SLOTS[slot]
            if not doc_name or not against:
                return
            m = compare_names(against, doc_name)
            ev = {"form": against, "document": doc_name, "match": m.to_dict()}
            if m.is_match:
                f(f"{code}_NAME_MATCH", "pass", f"{what} on {doc_label} matches", detail=f"{m.explanation} (score {m.score}).", evidence=ev)
            elif m.verdict == "partial":
                f(f"{code}_NAME_PARTIAL", "warn", f"{what} on {doc_label} only partly matches", weight=15,
                  detail=f"Form '{against}' vs document '{doc_name}': {m.explanation}.", evidence=ev)
            else:
                f(f"{code}_NAME_MISMATCH", "fail", f"{doc_label} is in a different name", field=f"documents.{slot}",
                  detail=f"Form '{against}' vs document '{doc_name}' (score {m.score}).", resolution="vendor",
                  vendor_action=f"Your {doc_label} is in the name '{doc_name}', not '{against}'. Upload the document issued to {against}.",
                  evidence=ev)

        if "gst_certificate" in self.usable_docs:
            compare_id("gst_certificate", "gstin", "tax.gstin", "gstin", "DOC_GSTIN")
            compare_name("gst_certificate", "legal_name", legal, "DOC_GST", "Legal name")
        if "pan_card" in self.usable_docs:
            compare_id("pan_card", "pan", "tax.pan", "pan", "DOC_PAN")
            compare_name("pan_card", "name", legal, "DOC_PAN", "Name")
        if "incorporation_certificate" in self.usable_docs:
            compare_id("incorporation_certificate", "cin", "company.cin", "cin", "DOC_CIN")
            compare_name("incorporation_certificate", "company_name", legal, "DOC_COI", "Company name")
        if "msme_certificate" in self.usable_docs:
            compare_id("msme_certificate", "udyam_number", "tax.udyam_number", "udyam", "DOC_UDYAM")
            compare_name("msme_certificate", "enterprise_name", legal, "DOC_MSME", "Enterprise name")
        if "bank_proof" in self.usable_docs:
            bank_doc = self.usable_docs["bank_proof"]["fields"]
            compare_id("bank_proof", "account_number", "bank.account_number", "account", "DOC_ACCOUNT")
            compare_id("bank_proof", "ifsc", "bank.ifsc", "ifsc", "DOC_IFSC")
            holder_doc = bank_doc.get("account_holder_name")
            if holder_doc and legal:
                m = best_match(holder_doc, [legal, self.get("company.trade_name"), self.get("bank.account_holder_name")])
                ev = {"document": holder_doc, "legal_name": legal, "match": m.to_dict()}
                if m.is_match:
                    f("DOC_HOLDER_MATCH", "pass", "Name on bank proof matches vendor", detail=f"{m.explanation} (score {m.score}).", evidence=ev)
                else:
                    f("DOC_HOLDER_MISMATCH", "fail", "Bank proof is in a different name", field="documents.bank_proof",
                      detail=f"Bank proof shows '{holder_doc}', vendor is '{legal}' (score {m.score}).",
                      resolution="review", evidence=ev)
            if bank_doc.get("subtype") == "letter":
                raw_date = bank_doc.get("document_date")
                letter_date = documents.parse_date(raw_date)
                if not letter_date:
                    f("BANK_LETTER_UNDATED", "fail", "Bank letter has no readable date", field="documents.bank_proof",
                      resolution="vendor", vendor_action="Upload a dated bank confirmation letter (issued within the last 90 days) or a cancelled cheque.")
                else:
                    age = (date.today() - letter_date).days
                    if age < 0:
                        f("BANK_LETTER_FUTURE", "fail", "Bank letter is post-dated", field="documents.bank_proof",
                          detail=f"Dated {letter_date.isoformat()}, which is in the future.", resolution="review")
                    elif age > config.BANK_LETTER_MAX_AGE_DAYS:
                        f("BANK_LETTER_STALE", "fail", "Bank letter is too old", field="documents.bank_proof",
                          detail=f"Dated {letter_date.strftime('%d %b %Y')} ({age} days ago); policy accepts letters up to {config.BANK_LETTER_MAX_AGE_DAYS} days old.",
                          resolution="vendor",
                          vendor_action=f"Your bank letter is dated {letter_date.strftime('%d %b %Y')} ({age} days ago). Upload a letter issued within the last {config.BANK_LETTER_MAX_AGE_DAYS} days, or a cancelled cheque.",
                          evidence={"date": letter_date.isoformat(), "age_days": age})
                    else:
                        f("BANK_LETTER_FRESH", "pass", "Bank letter is recent", detail=f"Dated {letter_date.strftime('%d %b %Y')} ({age} days ago).")

    # ------------------------------------------------------------ stage 6
    def stage_registry(self) -> None:
        f = self._f("registry")
        legal = self.get("company.legal_name")
        gstin = self.valid.get("gstin")
        if not gstin:
            f("GST_LOOKUP_SKIPPED", "info", "GST portal lookup skipped", detail="No valid GSTIN to look up.")
        else:
            rec = GSTPortal().lookup(gstin, legal)
            ev = {"source": rec["source"], "record": rec}
            if rec["source"] == "simulated":
                f("GST_SIMULATED", "info", "GSTIN not in seeded registry — simulated response",
                  detail="In production this is a live GST portal call. Ad-hoc demo inputs get an 'Active' echo.", evidence=ev)
            status = (rec.get("status") or "").lower()
            if status != "active":
                extra = f" on {rec['cancellation_date']}" if rec.get("cancellation_date") else ""
                reason = f" ({rec['cancellation_reason']})" if rec.get("cancellation_reason") else ""
                f("GST_NOT_ACTIVE", "fail", f"GST registration is {rec.get('status')}", field="tax.gstin",
                  detail=f"GST portal shows GSTIN {gstin} as {rec.get('status')}{extra}{reason}.",
                  resolution="reject",
                  vendor_action=f"The GST portal shows your GSTIN {gstin} as {rec.get('status')}{extra}. We can only onboard vendors with an active GST registration; you're welcome to re-apply once it is restored.",
                  evidence=ev)
            else:
                f("GST_ACTIVE", "pass", "GST registration is active", detail=f"{gstin} — {rec.get('state')}.", evidence=ev)
            if rec["source"] == "seeded" and legal:
                m = compare_names(legal, rec.get("legal_name"))
                ev["match"] = m.to_dict()
                if m.is_match:
                    f("GST_NAME_MATCH", "pass", "Name matches GST records", detail=f"{rec.get('legal_name')} — {m.explanation}.", evidence=ev)
                else:
                    f("GST_NAME_MISMATCH", "fail", "GSTIN is registered to a different entity", field="company.legal_name",
                      detail=f"GST portal legal name is '{rec.get('legal_name')}', submission says '{legal}' (score {m.score}). Someone may be using another business's GSTIN.",
                      resolution="review", evidence=ev)

        cin = self.valid.get("cin")
        if cin and self.get("company.business_type") in COMPANY_TYPES:
            rec = MCARegistry().lookup(cin, legal)
            ev = {"source": rec["source"], "record": rec}
            if rec["source"] == "simulated":
                f("MCA_SIMULATED", "info", "CIN not in seeded registry — simulated response", evidence=ev)
            status = (rec.get("status") or "").lower()
            if status != "active":
                f("MCA_NOT_ACTIVE", "fail", f"Company status is '{rec.get('status')}'", field="company.cin",
                  detail=f"MCA master data shows {cin} as '{rec.get('status')}'. A struck-off company cannot legally contract.",
                  resolution="reject",
                  vendor_action=f"Ministry of Corporate Affairs records show your company ({cin}) as '{rec.get('status')}'. We can only onboard companies with an active status.",
                  evidence=ev)
            else:
                f("MCA_ACTIVE", "pass", "Company is active on MCA", detail=f"{cin}, {rec.get('roc') or rec.get('state')}.", evidence=ev)
            if rec["source"] == "seeded" and legal:
                m = compare_names(legal, rec.get("company_name"))
                ev["match"] = m.to_dict()
                if m.is_match:
                    f("MCA_NAME_MATCH", "pass", "Name matches MCA records", detail=f"{rec.get('company_name')}.", evidence=ev)
                else:
                    f("MCA_NAME_MISMATCH", "fail", "CIN is registered to a different company", field="company.legal_name",
                      detail=f"MCA name is '{rec.get('company_name')}', submission says '{legal}' (score {m.score}).",
                      resolution="review", evidence=ev)
                reg_doi = documents.parse_date(rec.get("date_of_incorporation"))
                doi = self.valid.get("doi")
                if reg_doi and doi and reg_doi != doi:
                    f("MCA_DOI_DIFFERS", "warn", "Date of incorporation differs from MCA", weight=10,
                      detail=f"MCA: {reg_doi.isoformat()}, form: {doi.isoformat()}.")
        elif self.get("company.business_type") == "LLP" and self.valid.get("llpin"):
            f("LLP_REGISTRY_SKIPPED", "info", "LLP registry lookup not configured", detail="LLPIN format was validated; no LLP mock registry in this build.")

    # ------------------------------------------------------------ stage 7
    def stage_bank(self) -> None:
        f = self._f("bank")
        ifsc, acct = self.valid.get("ifsc"), self.valid.get("account")
        legal = self.get("company.legal_name")
        if not ifsc:
            f("BANK_SKIPPED", "info", "Bank verification skipped", detail="No valid IFSC.")
            return
        branch = BankDirectory().lookup_ifsc(ifsc)
        if not branch["found"]:
            f("IFSC_UNKNOWN", "fail", "IFSC not found in RBI directory", field="bank.ifsc",
              detail=f"Bank code '{ifsc[:4]}' is not a recognised bank.", resolution="vendor",
              vendor_action=f"IFSC {ifsc} doesn't match any bank branch. Check it on your cheque book or passbook.",
              evidence=branch)
            return
        where = ", ".join(x for x in [branch.get("branch"), branch.get("city")] if x)
        f("IFSC_FOUND", "pass", f"IFSC resolves to {branch['bank']}", detail=where or "Branch details simulated.", evidence=branch)
        declared_bank = self.get("bank.bank_name")
        if declared_bank and normalize_name(branch["bank"]).split()[0] not in normalize_name(declared_bank):
            f("BANK_NAME_DIFFERS", "warn", "Declared bank name differs from IFSC", weight=5, field="bank.bank_name",
              detail=f"Declared '{declared_bank}', IFSC belongs to {branch['bank']}.")
        if not acct:
            return
        result = PennyDrop().verify(acct, ifsc, self.get("bank.account_holder_name"))
        registered = result["registered_name"]
        ev = {"source": result["source"], "registered_name": registered, "account": india.mask_account(acct)}
        if result["source"] == "simulated":
            f("PENNY_DROP_SIMULATED", "info", "Account not in seeded bank data — simulated penny-drop",
              detail="In production a ₹1 IMPS penny-drop returns the real beneficiary name.", evidence=ev)
        m = best_match(registered, [legal, self.get("company.trade_name")])
        ev["match"] = m.to_dict()
        if m.is_match:
            f("PENNY_DROP_MATCH", "pass", "Bank confirms the account belongs to the vendor",
              detail=f"Bank-registered name '{registered}' — {m.explanation} (score {m.score}).", evidence=ev)
        elif m.verdict == "partial":
            f("PENNY_DROP_PARTIAL", "warn", "Bank-registered name only partly matches", resolution="review", weight=30,
              detail=f"Bank says '{registered}', vendor is '{legal}': {m.explanation}.", evidence=ev)
        else:
            f("PENNY_DROP_MISMATCH", "fail", "Bank account belongs to someone else",
              detail=f"Penny-drop returned '{registered}' for account {india.mask_account(acct)}, but the vendor is '{legal}' (score {m.score}). "
                     f"The form{' and the uploaded bank proof' if 'bank_proof' in self.usable_docs else ''} claim otherwise — a classic payment-diversion pattern.",
              resolution="review", weight=60, evidence=ev)

    # ------------------------------------------------------------ stage 8
    def stage_duplicates(self) -> None:
        f = self._f("duplicates")
        pan, gstin = self.valid.get("pan"), self.valid.get("gstin")
        acct, ifsc = self.valid.get("account"), self.valid.get("ifsc")
        legal = self.get("company.legal_name")
        matches = repository.vendor_master_matches(pan, gstin, acct, ifsc, self.sid)
        flagged = False
        for v in matches:
            same_tax = (pan and v["pan"] == pan) or (gstin and v["gstin"] == gstin)
            same_bank = bool(acct and ifsc and v["account_number"] == acct and v["ifsc"] == ifsc)
            name = compare_names(legal, v["legal_name"])
            ev = {"vendor": v, "same_tax_id": bool(same_tax), "same_bank": same_bank, "name_match": name.to_dict()}
            flagged = True
            if same_tax and name.is_match and same_bank:
                f("DUPLICATE_VENDOR", "fail", f"Already an approved vendor ({v['vendor_code']})",
                  detail=f"{v['legal_name']} with the same PAN/GSTIN and bank account already exists as {v['vendor_code']}.",
                  resolution="reject",
                  vendor_action=f"You're already registered with us as vendor {v['vendor_code']}. No new registration is needed — to update any details, contact {config.PROCUREMENT_EMAIL}.",
                  evidence=ev)
            elif same_tax:
                changes = []
                if not name.is_match:
                    changes.append(f"a different name ('{legal}' vs '{v['legal_name']}')")
                if not same_bank:
                    changes.append("a different bank account")
                f("TAX_ID_REUSED", "fail", f"Same PAN/GSTIN as existing vendor {v['vendor_code']}",
                  detail=f"{v['vendor_code']} ({v['legal_name']}) already uses this PAN/GSTIN. This submission has {' and '.join(changes) or 'changes'}. "
                         "Bank-detail changes must go through change control, not a fresh onboarding — possible payment-redirection attempt.",
                  resolution="review", weight=60, evidence=ev)
            elif same_bank:
                f("SHARED_BANK_ACCOUNT", "fail", f"Bank account already belongs to {v['vendor_code']}",
                  detail=f"Account {india.mask_account(acct)} at {ifsc} is registered to {v['legal_name']} (different PAN). Two vendors sharing one account is a strong fraud signal.",
                  resolution="review", weight=60, evidence=ev)

        open_dupes = repository.open_submissions_matching(pan, acct, ifsc, self.sid)
        for o in open_dupes:
            flagged = True
            f("PARALLEL_SUBMISSION", "warn", f"Another open submission: {o['id']}", resolution="review", weight=20,
              detail=f"{o['legal_name']} ({o['status']}) has the {' and '.join(o['reasons'])}.", evidence=o)
        if not flagged:
            f("NO_DUPLICATES", "pass", "No duplicates in vendor master",
              detail="No existing vendor or open submission shares this PAN, GSTIN or bank account.")

    # ------------------------------------------------------------ stage 9
    def stage_sanctions(self) -> None:
        f = self._f("sanctions")
        screener = SanctionsScreening()
        parties = [
            ("entity", "Legal name", self.get("company.legal_name")),
            ("entity", "Trade name", self.get("company.trade_name")),
            ("individual", "Authorised signatory", self.get("signatory.name")),
        ]
        pan = self.valid.get("pan")
        any_hit = False
        screened = 0
        for party_type, role, name in parties:
            if not name:
                continue
            screened += 1
            for hit in screener.screen(name, party_type):
                any_hit = True
                id_match = bool(pan and hit["identifiers"].get("pan") == pan)
                ev = {"screened_name": name, "role": role, "hit": hit, "identifier_match": id_match}
                if hit["score"] >= config.SANCTIONS_BLOCK_SCORE and (hit["country_matches"] or id_match):
                    f("SANCTIONS_MATCH", "fail", f"Watchlist match: {role}",
                      detail=f"'{name}' matches '{hit['listed_name']}' ({hit['program']}, {hit['country']}) with score {hit['score']}"
                             f"{' and matching PAN' if id_match else ''}. Blocked and escalated to compliance.",
                      resolution="reject", evidence=ev)
                else:
                    reasons = []
                    if not hit["country_matches"]:
                        reasons.append(f"listed entity is in {hit['country']}")
                    if not id_match:
                        reasons.append("no identifier match")
                    f("SANCTIONS_POTENTIAL", "fail", f"Potential watchlist match: {role}",
                      detail=f"'{name}' resembles '{hit['listed_name']}' (matched on '{hit['matched_on']}', score {hit['score']}, {hit['program']}). "
                             f"Not auto-rejected: {', '.join(reasons) or 'below block threshold'}. A compliance reviewer must confirm or clear it.",
                      resolution="review", weight=50, evidence=ev)
        if not any_hit:
            f("SANCTIONS_CLEAR", "pass", "No watchlist matches",
              detail=f"Screened {screened} name(s) against {screener.list_name} v{screener.list_version} ({len(screener.entries)} entries).")

    # ------------------------------------------------------------ stage 10
    def stage_decision(self) -> None:
        f = self._f("decision")
        issues = [x for x in self.findings if x.severity in ("warn", "fail")]
        self.risk = min(100, sum(x.effective_weight for x in issues))
        rejects = [x for x in issues if x.severity == "fail" and x.resolution == "reject"]
        reviews = [x for x in issues if x.resolution == "review"]
        vendor = self._vendor_actions()
        passes = len([x for x in self.findings if x.severity == "pass"])

        def titles(items: List[Finding], n: int = 3) -> str:
            seen: List[str] = []
            for i in items:
                if i.title not in seen:
                    seen.append(i.title)
            more = f" (+{len(seen) - n} more)" if len(seen) > n else ""
            return "; ".join(seen[:n]) + more

        if rejects:
            self.decision = "REJECTED"
            self.decision_reason = f"Rejected — {titles(rejects)}."
        elif reviews:
            self.decision = "PENDING_REVIEW"
            self.decision_reason = f"Pending internal review — {titles(reviews)}."
            if vendor:
                self.decision_reason += f" {len(vendor)} vendor-fixable item(s) are held until review completes."
        elif vendor:
            self.decision = "PENDING_VENDOR"
            self.decision_reason = f"Pending vendor — {len(vendor)} item(s) need correction: {titles(vendor)}."
        elif self.risk >= config.REVIEW_RISK_THRESHOLD:
            self.decision = "PENDING_REVIEW"
            self.decision_reason = (f"Pending internal review — no single blocking issue, but cumulative risk {self.risk} "
                                    f"≥ threshold {config.REVIEW_RISK_THRESHOLD}: {titles(issues)}.")
        else:
            self.decision = "APPROVED"
            note = f"; {len(issues)} minor warning(s) within tolerance" if issues else ""
            self.decision_reason = f"Approved — {passes} checks passed, no blocking issues{note} (risk {self.risk}/100)."

        update: Dict[str, Any] = {"status": self.decision, "risk_score": self.risk,
                                  "decision_reason": self.decision_reason, "decided_by": "system"}
        if self.decision == "APPROVED":
            self.vendor_code = repository.create_vendor(
                self.sid, self.get("company.legal_name") or "", self.valid.get("pan") or "",
                self.valid.get("gstin"), self.valid.get("account"), self.valid.get("ifsc"))
            update["vendor_code"] = self.vendor_code
        repository.update_submission(self.sid, **update)

        f("DECISION", "info", self.decision.replace("_", " ").title(),
          detail=self.decision_reason,
          evidence={"risk_score": self.risk, "rejects": len(rejects), "review_flags": len(reviews),
                    "vendor_actions": len(vendor), "passes": passes, "vendor_code": self.vendor_code,
                    "threshold": config.REVIEW_RISK_THRESHOLD})
        self.emit("decision", "decision", {"decision": self.decision, "reason": self.decision_reason,
                                           "risk_score": self.risk, "vendor_code": self.vendor_code})

    def _fallback_decision(self) -> None:
        self.decision = "PENDING_REVIEW"
        self.decision_reason = "Pending internal review — the decision step failed, so the case was routed to a human."
        repository.update_submission(self.sid, status=self.decision, decision_reason=self.decision_reason,
                                     decided_by="system", risk_score=self.risk)

    # ------------------------------------------------------------ stage 11
    def stage_notify(self) -> None:
        f = self._f("notify")
        submission = repository.get_submission(self.sid) or {}
        drafts = messaging.for_decision(submission, self.data, self.decision or "PENDING_REVIEW",
                                        self._vendor_actions(), self.findings, self.vendor_code)
        for d in drafts:
            msg_id = repository.add_message(self.sid, self.run_id, d["audience"], d["kind"], d["to"], d["subject"],
                                            d["body"], d.get("action_url"), d["engine"])
            f("MESSAGE_QUEUED", "info", f"{'Vendor' if d['audience'] == 'vendor' else 'Internal'} message drafted: {d['kind'].replace('_', ' ')}",
              detail=f"To {d['to']} — \"{d['subject']}\"", evidence={"message_id": msg_id, "engine": d["engine"]})
            self.emit("message", "notify", {"message_id": msg_id, **d})
        repository.audit(self.sid, "system", "messages_queued", {"count": len(drafts), "run_id": self.run_id})


def run_pipeline(submission_id: str, version: int, run_id: str) -> None:
    """Entry point for background execution. Never raises."""
    try:
        Pipeline(submission_id, version, run_id).run()
    except Exception as exc:
        log.exception("Pipeline crashed for %s", submission_id)
        try:
            repository.finish_run(run_id, status="failed", decision="PENDING_REVIEW",
                                  reason=f"Pipeline error: {exc}", risk=None, findings=[], summary={}, engine={})
            repository.update_submission(submission_id, status="PENDING_REVIEW",
                                         decision_reason="Pipeline error — routed to manual review", decided_by="system")
            repository.append_event(run_id, 10_000, None, "run_completed",
                                    {"decision": "PENDING_REVIEW", "reason": f"Pipeline error: {exc}", "error": True})
        except Exception:
            log.exception("Could not record pipeline failure")
