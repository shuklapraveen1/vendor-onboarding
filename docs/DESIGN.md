# Design notes — VendorGate (PS-2)

This is the reference document for the live pitch: the process map, the decision rules, every assumption made, the edge cases, and what comes next.

---

## 1. The problem, restated

Before a company pays a vendor, someone must confirm the vendor is **who they say they are** and that **the money goes to them**. Today that is manual:

- **Collect.** Forms arrive incomplete, documents are wrong or missing, and follow-up happens over email, one issue at a time.
- **Check.** A reviewer eyeballs each field. Subtle problems are only visible when fields are cross-referenced: a GSTIN from another state, or a bank account in someone else's name.
- **Audit.** The only trail is whatever is in someone's inbox.

A bad onboarding means **payment fraud**, where money is redirected to a fraudster's account, or **compliance exposure**, such as a sanctioned party, a non-existent company or a cancelled GST registration that makes input-tax credit claims invalid.

**The goal** is to take a submission and produce *approved*, *pending* or *rejected* with visible reasoning, and to tell the vendor exactly what's needed when it isn't approved.

## 2. Who it's built for

| Person | What they need from it |
|---|---|
| **Vendor** | One clear list of what to fix, a link to fix it, and no jargon. Never told *why* they're under fraud review. |
| **Procurement ops** | Clean cases approved automatically, so they only touch what needs judgement. |
| **Compliance / risk reviewer** | The evidence for each flag in one place, a mandatory note, and an audit trail. |
| **Finance / auditor** | Who decided, when, on which data version, and why. |

## 3. Process map

```
 Vendor form + PDFs
        │
        ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ 1 Intake & completeness   mandatory fields + documents for the business type   │
 │ 2 Format validation       GSTIN checksum, PAN structure, IFSC, CIN, Udyam,     │
 │                           email, phone, PIN, account number = confirmation     │
 │ 3 Document reading        extract text → classify by CONTENT → parse fields    │
 │ 4 Cross-field consistency PAN inside GSTIN, GSTIN state vs address,            │
 │                           PAN 4th char vs constitution, CIN year/state/type    │
 │ 5 Documents vs form       name/PAN/GSTIN/CIN/account on each doc vs the form,  │
 │                           bank letter age, cheque payee                        │
 │ 6 Registry verification   GST portal (active? legal name? state?)              │
 │                           MCA (active? name? date of incorporation?)           │
 │ 7 Bank verification       IFSC directory + penny-drop beneficiary name         │
 │ 8 Duplicates & fraud      vendor master + open submissions: PAN/GSTIN/account  │
 │ 9 Sanctions screening     legal name, trade name, signatory vs watchlist       │
 │10 Decision                precedence rules over all findings → status + risk   │
 │11 Communication           vendor email (+ portal link) and internal alert      │
 └──────────────────────────────────────────────────────────────────────────────┘
        │
        ├── APPROVED ─────────► vendor code issued, added to vendor master
        ├── PENDING_VENDOR ───► vendor fixes in portal ─► new version ─► re-run (1–11)
        ├── PENDING_REVIEW ───► reviewer: approve / reject / request info (note required)
        └── REJECTED
```

**Design choice: every stage always runs.** A process that stops at the first failure forces the vendor into a fix-one-thing-per-round-trip loop, which is exactly today's pain. Running every stage gives the vendor one consolidated list. Cross-checks only use values that passed format validation, so one typo doesn't cascade into ten confusing errors.

## 4. Findings, the unit of reasoning

Every check emits a **finding** with these fields:

| Field | Purpose |
|---|---|
| `code` | Stable machine code, e.g. `GST_STATE_MISMATCH` (used for stats and tests) |
| `severity` | `pass` · `info` · `warn` · `fail` |
| `resolution` | **Who can resolve it:** `vendor` (they can fix it), `review` (a human must judge), `reject` (disqualifying) |
| `vendor_action` | The exact sentence the vendor sees, with an optional `hint`, e.g. "your certificate shows 27AAKCS7731Q1ZH — did you mean that?" |
| `weight` | Contribution to the 0–100 risk score |
| `evidence` | Raw data behind it: registry response, match scores, extracted document fields |

The **resolution owner** is the key design idea. It separates "the vendor made a typo" from "this looks like fraud" from "this can't be onboarded". Each needs a different status and a different message.

## 5. Decision rules (applied in this order)

1. **Any `fail` with resolution `reject`** → **REJECTED**. Examples: GST registration cancelled, company struck off, exact duplicate of an existing vendor, confirmed sanctions match.
2. **Any finding with resolution `review`** → **PENDING_REVIEW**. If vendor-fixable items also exist, they are *held* until review completes, so we don't ask a possibly fraudulent vendor to "fix" their way past a fraud flag.
3. **Any `fail` with resolution `vendor`** → **PENDING_VENDOR**, with a consolidated request and a portal link.
4. **Cumulative risk ≥ 30** (warnings only) → **PENDING_REVIEW**. Several small oddities together deserve a look.
5. Otherwise → **APPROVED**. A vendor code is created and the vendor is added to the vendor master.

**Risk score** = sum of the weights of warn and fail findings, capped at 100. The defaults are reject 100, review 40 and vendor 10, and individual checks override them (penny-drop mismatch 60, minor bank-name difference 5). The score is used for **prioritising the review queue** and the threshold in rule 4. It never overrides rules 1–3.

**Fail-closed.** If any stage throws, a `SYSTEM_ERROR` finding (resolution `review`) is recorded and the case goes to a human. It is never silently approved. Runs interrupted by a server restart are marked failed at startup and routed to review.

**Reviewer controls:**
- **Approve**, **Reject** and **Request info** each require a reviewer name and a note of at least 10 characters, both written to the audit log.
- **Approve is blocked (HTTP 409)** while vendor-fixable `fail` items are open. A reviewer can't approve a submission with, say, a missing PAN card; they must use *Request info*.
- The banner shows both the **final decision** and the **system decision for that run**, so overrides are visible.

## 6. What the vendor is told, and what they're not

| Status | Vendor message | Internal |
|---|---|---|
| Approved | Welcome + vendor code | — |
| Pending · vendor | Numbered list of exactly what to fix, each with a hint where we can infer the fix; portal link | — |
| Pending · review | Neutral: "your registration is under review, no action needed" | Alert to the review team with every flag and its evidence |
| Rejected | The reason, **only if it's safe to disclose** (GST cancelled, already registered); otherwise generic | — |

**Fraud and sanctions signals are never disclosed to the vendor.** Telling a fraudster "the bank account doesn't match your company" teaches them what to forge next. The internal alert carries the evidence instead.

The action list is **always templated** from findings, never LLM-generated, so the vendor is never asked for something the rules didn't find. The LLM, if configured, only writes the one-line greeting, and that greeting is rejected if it contains words like *fraud*, *sanction*, *risk* or *suspicious*.

## 7. Where AI is used, and where it deliberately isn't

| Task | Approach | Why |
|---|---|---|
| Reading documents | Deterministic text extraction + regex parsers per document type; **LLM fills only fields the parser missed**, and every LLM value is re-validated (checksum, format) | Extraction is the messy part where an LLM helps, but its output is treated as an untrusted suggestion |
| Classifying unknown documents | Keyword-weighted classifier; LLM fallback when nothing scores | Catches "Udyam certificate uploaded in the GST slot" |
| Email greeting | LLM, with a word guard; template fallback | Tone only |
| **Deciding status** | **Rules only** | Decisions must be explainable, reproducible and auditable. Same input, same output, every time. |
| **Vendor action list** | **Templates only** | No hallucinated requirements |

Everything works with **no API key**. The app shows "Rules only" in the sidebar, and every test runs offline.

## 8. Edge cases

All six requested categories are built. Five scenarios are featured in the demo (the happy path plus four edge cases) and four more are available.

| # | Scenario | What's subtle about it | Outcome |
|---|---|---|---|
| 01 | **Happy path** — Kaveri Precision Components | Bank says "KAVERI PRECISION COMPONENTS PVT LTD"; the matcher knows *Pvt Ltd ≡ Private Limited* | Approved, vendor code issued |
| 02 ★ | **Incomplete → targeted request → fixed** — Sahyadri Freight | GSTIN has transposed characters (fails mod-36 checksum), no signatory, no cheque. All three are collected in **one** request, and the correct GSTIN is **suggested from the uploaded certificate**. Vendor fixes them in the portal; documents already provided carry over | Pending vendor → **Approved** (v2) |
| 04 ★ | **Every field valid alone, inconsistent together** — Narmada Agro | GSTIN is real, active and has the right PAN, but it's the **Maharashtra** registration while the address is in **Gujarat** (state code 27 vs 24). Date of incorporation says 2017; the CIN encodes 2016 | Pending vendor, field-level asks |
| 05 ★ | **Bank account belongs to someone else** — Tungabhadra Steel | Form and (edited) cheque both say the company name; **penny-drop returns "RAVI KUMAR ENTERPRISES"**, the contact person's own business. Classic payment diversion | Pending review. Vendor gets a neutral message; internal alert has the evidence |
| 07 ★ | **Sanctions near-match** — Zenith Global Traders | Trade name "Zenith Global Trading" scores 100 against listed "ZENITH GLOBAL TRADING FZE" (UAE), but different country and no identifier match. **Not auto-rejected:** false positives are common, so a compliance reviewer clears or confirms | Pending review → reviewer clears → Approved |
| 03 | Wrong + stale documents — Ganga Textiles | Udyam certificate uploaded in the GST slot (the classifier reads content, not the slot name); bank letter is 8 months old (policy is 90 days) | Pending vendor |
| 06 | Existing vendor's tax ID, new name and bank — Deccan Paper & Packaging | PAN/GSTIN belong to VEND-0003, but the name and bank account are new, with documents edited to match. Bank changes must go through change control, not re-onboarding | Pending review |
| 08 | Exact duplicate — Deccan Paper Products | Same PAN, GSTIN, name and account as VEND-0003 | Rejected, pointing to the existing code |
| 09 | GST cancelled + company struck off — Vindhya Infra | Every format is valid and documents are consistent, but registries say no | Rejected, reason disclosed |

★ = featured in the demo.

## 9. Indian validation rules implemented

| Identifier | Checks |
|---|---|
| **GSTIN** (15) | Structure `SS PPPPPPPPPP E Z C`; state code 01–38 (+97, 99); **mod-36 checksum** (catches typos and transpositions); embedded PAN must equal the declared PAN; state code must equal the address state |
| **PAN** (10) | `AAAAA9999A`; 4th char = holder type (C company, F firm/LLP, P individual…) must suit the business type; 5th char normally the first letter of the name (a warning only, since there are legitimate exceptions) |
| **CIN** (21) | Listing status, industry code, state, **year**, ownership type (PTC, PLC…), registration number. Year must match the date of incorporation; ownership must match the business type |
| **LLPIN**, **Udyam** | Format |
| **IFSC** | `AAAA0XXXXXX`, resolved against a bank directory |
| Bank | Account number 9–18 digits, must equal confirmation; penny-drop beneficiary name |
| Contact | Email, Indian mobile (normalised to +91), 6-digit PIN |

**Name matching** (`matching.py`): uppercase, strip "M/s", turn `&` into "AND", collapse legal suffixes (*Pvt Ltd*, *Private Limited* and *P. Ltd* are all the same), then fuzzy token-sort comparison. Legal forms are compared separately: "X LLP" is **not** the same entity as "X Private Limited". Truncation is detected, since bank systems cut names at about 35 characters. Sanctions screening uses token-sort, not token-set, so "Global Trading" doesn't match every company containing those words.

## 10. Assumptions (noted for the live pitch, as the brief asks)

1. **Buyer is an Indian company onboarding Indian vendors.** GST, PAN and Indian bank rails. International vendors (W-8/W-9, VAT, IBAN) would be another country pack.
2. **The submission is a web form plus PDFs.** Text PDFs are assumed; scanned images need OCR.
3. **Mandatory documents:** GST certificate, PAN card, cancelled cheque or bank letter, plus a Certificate of Incorporation for companies. MSME is optional; the Udyam certificate is required only if MSME is declared (MSME status matters for the 45-day payment rule).
4. **Every vendor is GST-registered.** Unregistered vendors under the threshold would need a declaration path instead of a GSTIN.
5. **External services are mocked with seeded, fictional data.** The fake GST portal, MCA, IFSC directory, penny-drop and watchlist all behave like the real ones (statuses, registered names, beneficiary names). Unknown identifiers get a flagged *simulated* response rather than a failure, so a free-form demo still works.
6. **Bank letters must be under 90 days old;** cheques don't expire for this purpose.
7. **No authentication.** Reviewer identity is a typed name. The vendor portal uses an unguessable 32-character token per submission and only accepts resubmissions while the status is *pending vendor*.
8. **Email is an in-app outbox.** Messages are stored and shown, not sent.
9. **Thresholds are policy, not code.** Risk threshold, bank-letter age and sanctions scores are environment variables.

## 11. Data and audit

SQLite (WAL mode). Tables are submissions, versions, documents, runs, run events, messages, audit log and vendor master.

- **Versioned submissions.** Each resubmission is a new immutable version. Documents not re-uploaded carry over and are marked as such.
- **Each run is pinned to a version** and stores its findings, summary and engine mode (rules vs AI assist).
- **The audit log** records every submission, run, message, reviewer action and resubmission, with actor and timestamp.
- Bank account numbers are masked in the UI and in messages.

## 12. What I'd build next (production roadmap)

| Area | Next step |
|---|---|
| Real integrations | GSP API for GST, MCA21 master data, Razorpay or Cashfree penny-drop, OFAC/UN/EU/MHA lists via a screening vendor, ERP (SAP, Oracle, NetSuite) vendor-master sync |
| Documents | OCR (Textract, Google DocAI) for scans; LLM vision for messy layouts; tamper detection (PDF metadata, font inconsistencies) |
| Platform | Postgres, a real job queue (Celery/SQS) instead of a thread pool, object storage for files, SMTP/SES email, SSO + role-based access (requester vs reviewer vs admin), four-eyes approval for high risk |
| Process | SLA timers and reminders for pending-vendor cases; auto-expiry; periodic re-screening of approved vendors (sanctions, GST status); bank-detail **change control** flow |
| Policy | Rules as configuration per buyer (which documents, thresholds, which checks block); reviewer feedback loop to tune thresholds and false-positive rates |
| Scale | International country packs (VAT, EIN, IBAN), multilingual vendor portal |
