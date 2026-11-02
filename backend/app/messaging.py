"""Vendor and internal message drafting.

Guardrails:
  * The list of required actions is always rendered from findings by the
    template — the LLM (if enabled) only writes the greeting paragraph, so
    it can't drop, soften or invent a requirement.
  * Fraud / sanctions signals are never disclosed to the vendor (tipping
    off a bad actor teaches them how to pass the checks). They get a
    neutral "under review" note; the detail goes to the internal alert.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config, llm
from .validators import india


def _g(item: Any, key: str) -> Any:
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _contact(data: Dict[str, Any]) -> Dict[str, str]:
    c = data.get("contact") or {}
    company = data.get("company") or {}
    return {
        "name": (c.get("name") or "").strip() or "Vendor team",
        "email": (c.get("email") or "").strip() or "(no email on file)",
        "company": (company.get("legal_name") or "").strip() or "your company",
    }


def portal_url(submission: Dict[str, Any]) -> str:
    return f"{config.PUBLIC_BASE_URL}/portal/{submission['portal_token']}"


def case_url(submission: Dict[str, Any]) -> str:
    return f"{config.PUBLIC_BASE_URL}/submissions/{submission['id']}"


def _intro(kind: str, contact: Dict[str, str], n_items: int, fallback: str) -> Tuple[str, str]:
    if not llm.provider():
        return fallback, "template"
    system = (
        "You write short, warm, professional emails from a procurement team to a vendor in India. "
        "Write exactly 2 sentences. Do not list requirements, do not mention fraud, sanctions, risk or internal checks, "
        "do not invent facts, deadlines or names. Plain text only."
    )
    user = f"Email type: {kind}. Vendor contact: {contact['name']} at {contact['company']}. Number of items to fix: {n_items}."
    text = llm.complete_text(system, user, max_tokens=150)
    if not text or len(text) > 600 or any(w in text.lower() for w in ("fraud", "sanction", "risk", "suspicious")):
        return fallback, "template"
    return text, f"template+llm:{llm.provider()}"


def _signoff() -> str:
    return f"Regards,\nVendor Onboarding Team\n{config.BUYER_COMPANY}\n{config.PROCUREMENT_EMAIL}"


def _action_list(vendor_actions: Iterable[Any]) -> List[str]:
    lines, seen = [], set()
    for f in vendor_actions:
        action = _g(f, "vendor_action")
        if not action or action in seen:
            continue
        seen.add(action)
        hint = _g(f, "hint")
        lines.append(f"{len(lines) + 1}. {action}" + (f"\n   Tip: {hint}" if hint else ""))
    return lines


def info_request(submission: Dict[str, Any], data: Dict[str, Any], vendor_actions: List[Any],
                 vendor_note: Optional[str] = None) -> Dict[str, Any]:
    contact = _contact(data)
    items = _action_list(vendor_actions)
    fallback = (f"Thank you for submitting the vendor registration for {contact['company']}. "
                f"We've reviewed it and need {len(items) or 'a few'} correction(s) before we can activate your account.")
    intro, engine = _intro("request for missing/incorrect information", contact, len(items), fallback)
    url = portal_url(submission)
    note = f"\nNote from our team:\n{vendor_note.strip()}\n" if vendor_note and vendor_note.strip() else ""
    body = (
        f"Dear {contact['name']},\n\n{intro}\n\n"
        f"Please address the following:\n\n" + "\n".join(items or ["(see note below)"]) + "\n"
        f"{note}\n"
        f"Update your submission here — everything you've already provided is saved, so you only need to fix the items above:\n{url}\n\n"
        f"Reference: {submission['id']}\n\n{_signoff()}"
    )
    return {"audience": "vendor", "kind": "info_request", "to": contact["email"],
            "subject": f"Action needed: vendor registration {submission['id']} — {len(items)} item(s) to update",
            "body": body, "action_url": url, "engine": engine}


def approval(submission: Dict[str, Any], data: Dict[str, Any], vendor_code: Optional[str]) -> Dict[str, Any]:
    contact = _contact(data)
    bank = data.get("bank") or {}
    tax = data.get("tax") or {}
    fallback = (f"Good news — {contact['company']} has been approved as a vendor with {config.BUYER_COMPANY}. "
                "Thank you for providing complete and accurate details.")
    intro, engine = _intro("vendor approved / welcome", contact, 0, fallback)
    body = (
        f"Dear {contact['name']},\n\n{intro}\n\n"
        f"Your vendor code: {vendor_code}\n"
        f"Payments will be made to account {india.mask_account(bank.get('account_number'))} (IFSC {india.clean_id(bank.get('ifsc'))}).\n\n"
        f"Next steps:\n"
        f"1. Quote vendor code {vendor_code} and GSTIN {india.clean_id(tax.get('gstin'))} on every invoice.\n"
        f"2. Invoices must reference a valid purchase order number.\n"
        f"3. Any change to bank details must be requested through {config.PROCUREMENT_EMAIL} and will be re-verified.\n\n"
        f"Reference: {submission['id']}\n\n{_signoff()}"
    )
    return {"audience": "vendor", "kind": "approval", "to": contact["email"],
            "subject": f"Welcome aboard — {contact['company']} is an approved vendor ({vendor_code})",
            "body": body, "action_url": None, "engine": engine}


def under_review(submission: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    contact = _contact(data)
    body = (
        f"Dear {contact['name']},\n\n"
        f"Thank you for submitting the vendor registration for {contact['company']}. "
        f"Your application is going through our standard verification, which needs a manual step on our side.\n\n"
        f"No action is needed from you right now. We'll contact you within 2 business days, "
        f"either to confirm approval or if we need anything further.\n\n"
        f"Reference: {submission['id']}\n\n{_signoff()}"
    )
    return {"audience": "vendor", "kind": "under_review", "to": contact["email"],
            "subject": f"Your vendor registration {submission['id']} is being reviewed",
            "body": body, "action_url": None, "engine": "template"}


def rejection(submission: Dict[str, Any], data: Dict[str, Any], reasons: List[str],
              vendor_note: Optional[str] = None) -> Dict[str, Any]:
    contact = _contact(data)
    if reasons:
        detail = "This is because:\n" + "\n".join(f"- {r}" for r in dict.fromkeys(reasons))
    else:
        detail = "After completing our verification process, we are unable to proceed with this registration at this time."
    note = f"\n\n{vendor_note.strip()}" if vendor_note and vendor_note.strip() else ""
    body = (
        f"Dear {contact['name']},\n\n"
        f"Thank you for your interest in working with {config.BUYER_COMPANY}. "
        f"We're unable to approve the vendor registration for {contact['company']}.\n\n{detail}{note}\n\n"
        f"If you believe this is an error, please reply to this email quoting reference {submission['id']}.\n\n{_signoff()}"
    )
    return {"audience": "vendor", "kind": "rejection", "to": contact["email"],
            "subject": f"Update on your vendor registration {submission['id']}",
            "body": body, "action_url": None, "engine": "template"}


def internal_alert(submission: Dict[str, Any], data: Dict[str, Any], findings: List[Any]) -> Dict[str, Any]:
    contact = _contact(data)
    flags = [f for f in findings if _g(f, "resolution") in ("review", "reject") and _g(f, "severity") in ("warn", "fail")]
    held = [f for f in findings if _g(f, "resolution") == "vendor" and _g(f, "severity") == "fail"]
    lines = [f"- [{_g(f, 'stage')}] {_g(f, 'title')}: {_g(f, 'detail')}" for f in flags]
    held_lines = [f"- {_g(f, 'title')}" for f in held]
    body = (
        f"Case {submission['id']} — {contact['company']} needs a reviewer.\n"
        f"Risk score: {submission.get('risk_score')}/100\n\n"
        f"Why it was routed to you:\n" + ("\n".join(lines) or "- Cumulative risk above threshold") + "\n\n"
        + (f"Vendor-fixable items held until you decide:\n" + "\n".join(held_lines) + "\n\n" if held_lines else "")
        + f"The vendor has been told only that the application is under review.\n"
        f"Open the case: {case_url(submission)}\n"
    )
    return {"audience": "internal", "kind": "review_alert", "to": config.REVIEW_TEAM_EMAIL,
            "subject": f"[Review needed] {submission['id']} {contact['company']} — {_g(flags[0], 'title') if flags else 'risk threshold'}",
            "body": body, "action_url": case_url(submission), "engine": "template"}


def _disclosable_rejections(findings: List[Any]) -> List[str]:
    return [_g(f, "vendor_action") for f in findings
            if _g(f, "resolution") == "reject" and _g(f, "severity") == "fail" and _g(f, "vendor_action")]


def for_decision(submission: Dict[str, Any], data: Dict[str, Any], decision: str, vendor_actions: List[Any],
                 findings: List[Any], vendor_code: Optional[str]) -> List[Dict[str, Any]]:
    if decision == "APPROVED":
        return [approval(submission, data, vendor_code)]
    if decision == "PENDING_VENDOR":
        return [info_request(submission, data, vendor_actions)]
    if decision == "REJECTED":
        return [rejection(submission, data, _disclosable_rejections(findings))]
    return [under_review(submission, data), internal_alert(submission, data, findings)]
