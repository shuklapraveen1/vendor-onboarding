"""Generate realistic demo inputs: vendor form JSON + document PDFs per scenario.

All companies, identifiers and people are fictional. GSTIN check digits are
computed with the real algorithm so format validation behaves exactly as it
would on genuine data.

Run:  python -m scripts.generate_samples   (from backend/)
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

OUT = config.SAMPLE_DIR
TODAY = date.today()
W, H = A4


def dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def iso_to_dmy(s: str) -> str:
    y, m, d = s.split("-")
    return f"{d}/{m}/{y}"


# ------------------------------------------------------------------ PDF drawing
class Doc:
    def __init__(self, path: Path, band: colors.Color):
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.c.setTitle(path.stem)
        self.y = H - 60
        self.band = band

    def header(self, lines: List[str]) -> None:
        c = self.c
        c.setFillColor(self.band)
        c.rect(0, H - 40, W, 40, stroke=0, fill=1)
        c.setStrokeColor(self.band)
        c.setLineWidth(2)
        c.rect(30, 30, W - 60, H - 90, stroke=1, fill=0)
        c.setFillColor(colors.black)
        self.y = H - 75
        for i, line in enumerate(lines):
            c.setFont("Helvetica-Bold", 14 if i == 0 else 11)
            c.drawCentredString(W / 2, self.y, line)
            self.y -= 18
        self.y -= 10

    def line(self, text: str, bold: bool = False, size: float = 10.5, gap: float = 17, x: float = 55) -> None:
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawString(x, self.y, text)
        self.y -= gap

    def space(self, n: float = 10) -> None:
        self.y -= n

    def stamp(self, text: str, color: colors.Color = colors.red) -> None:
        c = self.c
        c.saveState()
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 42)
        c.translate(W / 2, H / 2 + 40)
        c.rotate(25)
        c.drawCentredString(0, 0, text)
        c.restoreState()

    def save(self) -> None:
        self.c.showPage()
        self.c.save()


def addr(v: Dict[str, Any]) -> str:
    a = v["address"]
    return f"{a['line1']}, {a['city']}, {a['state']} - {a['pincode']}"


def gst_certificate(path: Path, v: Dict[str, Any]) -> None:
    gst = v.get("gst_doc", {})
    d = Doc(path, colors.HexColor("#1f4e79"))
    d.header(["Government of India", "Form GST REG-06", "[See Rule 10(1)]", "Registration Certificate"])
    d.line("Goods and Services Tax", bold=True)
    d.line(f"Registration Number: {gst.get('gstin', v['gstin'])}", bold=True)
    d.space()
    d.line(f"1. Legal Name: {v['legal_name'].upper()}")
    d.line(f"2. Trade Name, if any: {v['trade_name'].upper()}")
    d.line("3. Constitution of Business: Private Limited Company")
    d.line(f"4. Address of Principal Place of Business: {gst.get('address', addr(v))}")
    d.line(f"5. Date of Liability: {gst.get('liability', '01/07/2017')}")
    d.line("6. Period of Validity: From 01/07/2017 To Not Applicable")
    d.line("7. Type of Registration: Regular")
    d.line("8. Particulars of Approving Authority: Superintendent, Range-II, Central Tax")
    d.space(20)
    d.line("This is a system generated digitally signed Registration Certificate.", size=9)
    d.line("Signature not verified. Digitally signed by Goods and Services Tax Network.", size=9)
    d.save()


def pan_card(path: Path, v: Dict[str, Any]) -> None:
    d = Doc(path, colors.HexColor("#5b3a8c"))
    d.header(["INCOME TAX DEPARTMENT", "GOVT. OF INDIA"])
    d.line("Permanent Account Number Card", bold=True, size=12)
    d.line(v.get("pan_doc", v["pan"]), bold=True, size=16, gap=26)
    d.line("Name", size=9)
    d.line(v["legal_name"].upper(), bold=True)
    d.line("Date of Incorporation/Formation", size=9)
    d.line(iso_to_dmy(v["doi"]), bold=True)
    d.save()


def coi(path: Path, v: Dict[str, Any]) -> None:
    roc_state = v["address"]["state"] if not v.get("roc_state") else v["roc_state"]
    d = Doc(path, colors.HexColor("#7a4f01"))
    d.header(["Government of India", "Ministry of Corporate Affairs", f"Registrar of Companies, {roc_state}",
              "Certificate of Incorporation"])
    d.line("[Pursuant to sub-section (2) of section 7 and sub-section (1) of section 8 of the", size=9)
    d.line("Companies Act, 2013 (18 of 2013) and rule 18 of the Companies (Incorporation) Rules, 2014]", size=9)
    d.space()
    d.line(f"I hereby certify that {v['legal_name'].upper()} is incorporated")
    d.line(f"on {iso_to_dmy(v['doi'])} under the Companies Act, 2013 (18 of 2013) and that the company")
    d.line("is limited by shares.")
    d.space()
    d.line(f"The Corporate Identity Number of the company is {v['cin']}.", bold=True)
    d.line(f"Date of Incorporation: {iso_to_dmy(v['doi'])}")
    d.space(20)
    d.line("Given under my hand at the Central Registration Centre.", size=9)
    d.line("Digitally signed by DS MINISTRY OF CORPORATE AFFAIRS", size=9)
    d.save()


def udyam(path: Path, v: Dict[str, Any]) -> None:
    d = Doc(path, colors.HexColor("#0b6e4f"))
    d.header(["Government of India", "Ministry of Micro, Small and Medium Enterprises", "UDYAM REGISTRATION CERTIFICATE"])
    d.line(f"UDYAM REGISTRATION NUMBER: {v['udyam']}", bold=True)
    d.line(f"NAME OF ENTERPRISE: {v['legal_name'].upper()}")
    d.line("TYPE OF ENTERPRISE: Small")
    d.line("MAJOR ACTIVITY: Manufacturing")
    d.line(f"SOCIAL CATEGORY OF ENTREPRENEUR: General")
    d.line(f"OFFICIAL ADDRESS OF ENTERPRISE: {addr(v)}")
    d.line("DATE OF INCORPORATION / REGISTRATION OF ENTERPRISE: " + iso_to_dmy(v["doi"]))
    d.line("DATE OF UDYAM REGISTRATION: 05/09/2020")
    d.save()


def cheque(path: Path, v: Dict[str, Any]) -> None:
    b = v["bank"]
    holder = b.get("doc_holder", b["holder"])
    c = canvas.Canvas(str(path), pagesize=(W, 300))
    c.setTitle(path.stem)
    c.setFillColor(colors.HexColor("#eaf2fb"))
    c.rect(20, 20, W - 40, 260, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(40, 250, b["bank_name"].upper())
    c.setFont("Helvetica", 9.5)
    c.drawString(40, 234, f"Branch: {b['branch']}")
    c.drawString(40, 220, f"IFSC: {b['ifsc']}    MICR: {b.get('micr', '000240009')}")
    c.drawString(W - 170, 250, f"Date: __/__/____")
    c.drawString(40, 190, "Pay ____________________________________________________ or Bearer")
    c.drawString(40, 170, "Rupees __________________________________________   Rs. ____________")
    c.drawString(40, 140, f"A/c No: {b['account']}")
    c.drawString(40, 126, f"Account Type: {b.get('type', 'Current')}")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(W - 300, 80, holder.upper())
    c.setFont("Helvetica", 9)
    c.drawString(W - 300, 66, "Authorised Signatory")
    c.setFont("Courier", 11)
    c.drawString(60, 34, f"\"{b['account'][-6:]}\"  {b.get('micr', '000240009')}:  {b['account'][:6]}\"  29")
    c.saveState()
    c.setFillColor(colors.red)
    c.setFont("Helvetica-Bold", 40)
    c.translate(W / 2, 150)
    c.rotate(12)
    c.drawCentredString(0, 0, "CANCELLED")
    c.restoreState()
    c.showPage()
    c.save()


def bank_letter(path: Path, v: Dict[str, Any]) -> None:
    b = v["bank"]
    d = Doc(path, colors.HexColor("#123c69"))
    d.header([b["bank_name"].upper(), f"Branch: {b['branch']}"])
    d.line(f"Date: {b['letter_date']}")
    d.space()
    d.line("TO WHOM IT MAY CONCERN", bold=True)
    d.line("Sub: Bank Account Confirmation")
    d.space()
    d.line("This is to certify that the following account is maintained with our branch:")
    d.line(f"Account Holder Name: {b.get('doc_holder', b['holder']).upper()}")
    d.line(f"Account Number: {b['account']}")
    d.line(f"Account Type: {b.get('type', 'Current')}")
    d.line(f"IFSC Code: {b['ifsc']}")
    d.space()
    d.line("This letter is issued at the request of the account holder without any risk or")
    d.line("responsibility on the part of the bank or its officials.")
    d.space(30)
    d.line("Branch Manager", bold=True)
    d.save()


RENDERERS: Dict[str, Callable[[Path, Dict[str, Any]], None]] = {
    "gst": gst_certificate, "pan": pan_card, "coi": coi, "udyam": udyam, "cheque": cheque, "letter": bank_letter,
}


# ------------------------------------------------------------------ vendor data
def vendor(**kw: Any) -> Dict[str, Any]:
    return kw


KAVERI = vendor(
    legal_name="Kaveri Precision Components Private Limited", trade_name="Kaveri Precision",
    doi="2015-03-12", cin="U29100KA2015PTC081234", pan="AABCK4127M", gstin="29AABCK4127M1ZA",
    msme=True, udyam="UDYAM-KR-03-0012345",
    address={"line1": "Plot 42, 4th Cross, KIADB Industrial Area, Bommasandra", "line2": "", "city": "Bengaluru",
             "state": "Karnataka", "pincode": "560099"},
    bank={"holder": "Kaveri Precision Components Pvt Ltd", "account": "50200012345678", "ifsc": "HDFC0000523",
          "bank_name": "HDFC Bank", "branch": "Koramangala, Bengaluru", "micr": "560240009"},
    contact={"name": "Ananya Rao", "designation": "Finance Manager", "email": "ananya.rao@kaveriprecision.example", "phone": "+91 98450 12345"},
    signatory={"name": "Suresh Gowda", "designation": "Managing Director"},
)

SAHYADRI = vendor(
    legal_name="Sahyadri Freight Movers Private Limited", trade_name="Sahyadri Freight",
    doi="2018-06-04", cin="U63090MH2018PTC305512", pan="AAKCS7731Q", gstin="27AAKCS7731Q1ZH",
    msme=False, udyam="",
    address={"line1": "Office 7, Shivneri Complex, Paud Road, Kothrud", "line2": "", "city": "Pune",
             "state": "Maharashtra", "pincode": "411038"},
    bank={"holder": "Sahyadri Freight Movers Private Limited", "account": "000405012345", "ifsc": "ICIC0000104",
          "bank_name": "ICICI Bank", "branch": "Kothrud, Pune", "micr": "411229004"},
    contact={"name": "Rohit Deshpande", "designation": "Operations Head", "email": "rohit@sahyadrifreight.example", "phone": "9822011223"},
    signatory={"name": "Meera Kulkarni", "designation": "Director"},
)

GANGA = vendor(
    legal_name="Ganga Textiles Private Limited", trade_name="Ganga Textiles",
    doi="2011-01-19", cin="U17110UP2011PTC045678", pan="AACCG2290H", gstin="09AACCG2290H1ZM",
    msme=True, udyam="UDYAM-UP-36-0004567",
    address={"line1": "14/116 Civil Lines", "line2": "", "city": "Kanpur", "state": "Uttar Pradesh", "pincode": "208001"},
    bank={"holder": "Ganga Textiles Private Limited", "account": "32145678901", "ifsc": "SBIN0001055",
          "bank_name": "State Bank of India", "branch": "Civil Lines, Kanpur",
          "letter_date": dmy(TODAY - timedelta(days=243))},
    contact={"name": "Prakash Mishra", "designation": "Accounts Manager", "email": "accounts@gangatextiles.example", "phone": "9415098765"},
    signatory={"name": "Alok Agarwal", "designation": "Director"},
)

NARMADA = vendor(
    legal_name="Narmada Agro Exports Private Limited", trade_name="Narmada Agro",
    doi="2016-10-07", cin="U01400GJ2016PTC092345", pan="AAECN4821K", gstin="27AAECN4821K1ZB",
    msme=False, udyam="",
    address={"line1": "5th Floor, Sakar Complex, Ashram Road, Navrangpura", "line2": "", "city": "Ahmedabad",
             "state": "Gujarat", "pincode": "380009"},
    gst_doc={"address": "Unit 12, APMC Market Phase II, Vashi, Navi Mumbai, Maharashtra - 400703", "liability": "01/04/2019"},
    bank={"holder": "Narmada Agro Exports Pvt Ltd", "account": "917020045678123", "ifsc": "UTIB0000048",
          "bank_name": "Axis Bank", "branch": "Navrangpura, Ahmedabad", "micr": "380211002"},
    contact={"name": "Hetal Shah", "designation": "CFO", "email": "hetal.shah@narmadaagro.example", "phone": "9825012345"},
    signatory={"name": "Kiran Patel", "designation": "Managing Director"},
)

TUNGABHADRA = vendor(
    legal_name="Tungabhadra Steel Fabricators Private Limited", trade_name="Tungabhadra Steel",
    doi="2019-05-23", cin="U28100KA2019PTC123456", pan="AAFCT5567R", gstin="29AAFCT5567R1Z9",
    msme=False, udyam="",
    address={"line1": "Survey No. 88, Gokul Road Industrial Estate", "line2": "", "city": "Hubballi",
             "state": "Karnataka", "pincode": "580030"},
    bank={"holder": "Tungabhadra Steel Fabricators Pvt Ltd", "account": "8412345609", "ifsc": "KKBK0008067",
          "bank_name": "Kotak Mahindra Bank", "branch": "Vidyanagar, Hubballi", "micr": "580485002"},
    contact={"name": "Ravi Kumar", "designation": "Accounts Executive", "email": "payments.tungabhadrasteel@gmail.example", "phone": "9036612345"},
    signatory={"name": "Basavaraj Hiremath", "designation": "Director"},
)

DECCAN = vendor(
    legal_name="Deccan Paper Products Private Limited", trade_name="Deccan Paper",
    doi="2012-04-16", cin="U21012TG2012PTC081122", pan="AADCD3344E", gstin="36AADCD3344E1Z0",
    msme=False, udyam="",
    address={"line1": "Plot 9, IDA Uppal", "line2": "", "city": "Hyderabad", "state": "Telangana", "pincode": "500039"},
    bank={"holder": "Deccan Paper Products Pvt Ltd", "account": "062305001122", "ifsc": "ICIC0000623",
          "bank_name": "ICICI Bank", "branch": "Secunderabad, Hyderabad", "micr": "500229011"},
    contact={"name": "Srinivas Reddy", "designation": "Commercial Manager", "email": "srinivas@deccanpaper.example", "phone": "9849012345"},
    signatory={"name": "Lakshmi Narayana", "designation": "Director"},
)

DECCAN_NEW = copy.deepcopy(DECCAN)
DECCAN_NEW.update(
    legal_name="Deccan Paper & Packaging Private Limited", trade_name="Deccan Packaging",
    bank={"holder": "Deccan Paper & Packaging Pvt Ltd", "account": "50100098765432", "ifsc": "HDFC0001234",
          "bank_name": "HDFC Bank", "branch": "Banjara Hills, Hyderabad", "micr": "500240012"},
    contact={"name": "Vamshi Krishna", "designation": "Accounts", "email": "accounts@deccanpackaging.example", "phone": "9700012345"},
)

ZENITH = vendor(
    legal_name="Zenith Global Traders Private Limited", trade_name="Zenith Global Trading",
    doi="2020-02-11", cin="U51909TN2020PTC134567", pan="AAHCZ9087B", gstin="33AAHCZ9087B1Z2",
    msme=False, udyam="",
    address={"line1": "No. 21, SIDCO Industrial Estate, Guindy", "line2": "", "city": "Chennai",
             "state": "Tamil Nadu", "pincode": "600032"},
    bank={"holder": "Zenith Global Traders Private Limited", "account": "39876543210", "ifsc": "SBIN0000915",
          "bank_name": "State Bank of India", "branch": "Guindy, Chennai", "letter_date": dmy(TODAY - timedelta(days=12))},
    contact={"name": "Arjun Mehta", "designation": "Director", "email": "arjun@zenithglobal.example", "phone": "9840012345"},
    signatory={"name": "Arjun Mehta", "designation": "Director"},
)

VINDHYA = vendor(
    legal_name="Vindhya Infra Projects Private Limited", trade_name="Vindhya Infra",
    doi="2014-08-29", cin="U45200MP2014PTC033221", pan="AAGCV6612D", gstin="23AAGCV6612D1ZN",
    msme=False, udyam="",
    address={"line1": "201, Shekhar Central, AB Road", "line2": "", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    bank={"holder": "Vindhya Infra Projects Pvt Ltd", "account": "045605009876", "ifsc": "ICIC0000456",
          "bank_name": "ICICI Bank", "branch": "Vijay Nagar, Indore", "micr": "452229003"},
    contact={"name": "Nitin Jain", "designation": "Director", "email": "nitin@vindhyainfra.example", "phone": "9826012345"},
    signatory={"name": "Nitin Jain", "designation": "Director"},
)


def form_for(v: Dict[str, Any], **overrides: Any) -> Dict[str, Any]:
    form = {
        "company": {"legal_name": v["legal_name"], "trade_name": v["trade_name"], "business_type": "PRIVATE_LIMITED",
                    "date_of_incorporation": v["doi"], "cin": v["cin"], "llpin": "", "website": ""},
        "address": dict(v["address"]),
        "tax": {"pan": v["pan"], "gstin": v["gstin"], "msme_registered": v["msme"], "udyam_number": v["udyam"]},
        "bank": {"account_holder_name": v["bank"]["holder"], "account_number": v["bank"]["account"],
                 "confirm_account_number": v["bank"]["account"], "ifsc": v["bank"]["ifsc"],
                 "bank_name": v["bank"]["bank_name"], "account_type": v["bank"].get("type", "Current")},
        "contact": dict(v["contact"]),
        "signatory": dict(v["signatory"]),
        "declaration": {"accepted": True},
    }
    for path, value in overrides.items():
        section, key = path.split("__")
        form[section][key] = value
    return form


def standard_docs(v: Dict[str, Any], bank: str = "cheque") -> Dict[str, Any]:
    docs = {"gst_certificate": ("gst", v), "pan_card": ("pan", v), "incorporation_certificate": ("coi", v),
            "bank_proof": (bank, v)}
    if v["msme"]:
        docs["msme_certificate"] = ("udyam", v)
    return docs


SLUG = {"gst_certificate": "gst_certificate", "pan_card": "pan_card", "incorporation_certificate": "certificate_of_incorporation",
        "bank_proof": "bank_proof", "msme_certificate": "udyam_certificate"}

TUNG_DOCS = standard_docs(TUNGABHADRA)
GANGA_DOCS = standard_docs(GANGA, bank="letter")
GANGA_DOCS["gst_certificate"] = ("udyam", GANGA)
SAHYADRI_DOCS = standard_docs(SAHYADRI)
del SAHYADRI_DOCS["bank_proof"]

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "01-happy-path", "featured": True, "edge_case": None, "expected": "APPROVED",
        "title": "Happy path — clean MSME manufacturer",
        "company": KAVERI["legal_name"],
        "description": "Complete, consistent submission. Note the bank-registered name is 'KAVERI PRECISION COMPONENTS PVT LTD' — "
                       "the matcher treats 'Pvt Ltd' and 'Private Limited' as the same legal form.",
        "talking_points": ["All 11 stages pass", "Name normalisation: Pvt Ltd = Private Limited", "Vendor code issued + welcome email"],
        "form": form_for(KAVERI), "docs": standard_docs(KAVERI),
    },
    {
        "id": "02-incomplete-then-fixed", "featured": True, "edge_case": "incomplete_resubmit", "expected": "PENDING_VENDOR → APPROVED",
        "title": "Incomplete submission → targeted request → vendor fixes → approved",
        "company": SAHYADRI["legal_name"],
        "description": "GSTIN has transposed digits (fails checksum), no authorised signatory, and no cancelled cheque. "
                       "The process collects ALL gaps in one pass, suggests the correct GSTIN from the uploaded certificate, "
                       "and sends a portal link. Resubmitting only the fixes re-runs the full pipeline.",
        "talking_points": ["One consolidated request, not drip-fed", "GSTIN suggestion read from the certificate",
                           "Portal keeps prior data/docs; only fixes are uploaded", "Version history + re-run"],
        "form": form_for(SAHYADRI, tax__gstin="27AAKCS7371Q1ZH", signatory__name="", signatory__designation=""),
        "docs": SAHYADRI_DOCS,
        "fix": {"form": form_for(SAHYADRI), "docs": {"bank_proof": ("cheque", SAHYADRI)}},
    },
    {
        "id": "03-wrong-and-stale-documents", "featured": False, "edge_case": "doc_mismatch", "expected": "PENDING_VENDOR",
        "title": "Documents contradict the form — wrong file + stale bank letter",
        "company": GANGA["legal_name"],
        "description": "The vendor uploaded their Udyam certificate in the GST slot (the classifier reads the content, not the slot) "
                       "and a bank letter dated ~8 months ago (policy: 90 days).",
        "talking_points": ["Content-based document classification", "Same file uploaded twice detected by hash",
                           "Document freshness policy"],
        "form": form_for(GANGA), "docs": GANGA_DOCS,
    },
    {
        "id": "04-tax-state-cross-field", "featured": True, "edge_case": "tax_country", "expected": "PENDING_VENDOR",
        "title": "Every field valid on its own — inconsistent together",
        "company": NARMADA["legal_name"],
        "description": "Address is in Gujarat but the GSTIN (valid checksum, correct PAN, active on the GST portal) is the company's "
                       "Maharashtra registration. Date of incorporation says 2017 but the CIN encodes 2016. "
                       "Field-level validation passes everything; only cross-referencing catches it.",
        "talking_points": ["GSTIN is state-specific: wrong GSTIN = invoices with wrong tax", "CIN encodes year/state/type",
                           "Field-valid ≠ submission-valid"],
        "form": form_for(NARMADA, company__date_of_incorporation="2017-10-07"), "docs": standard_docs(NARMADA),
    },
    {
        "id": "05-bank-account-not-vendor", "featured": True, "edge_case": "bank_name_mismatch", "expected": "PENDING_REVIEW",
        "title": "Looks perfect — but the bank account belongs to someone else",
        "company": TUNGABHADRA["legal_name"],
        "description": "Form and the (edited) cancelled cheque both say the company name, but penny-drop verification returns "
                       "'RAVI KUMAR ENTERPRISES' — the contact person's own business. Classic payment diversion. Routed to "
                       "internal review; the vendor is NOT told why.",
        "talking_points": ["Documents can be forged — bank-side verification can't", "No tip-off to the vendor",
                           "Internal alert with the evidence"],
        "form": form_for(TUNGABHADRA), "docs": TUNG_DOCS,
    },
    {
        "id": "06-existing-vendor-new-bank", "featured": False, "edge_case": "duplicate", "expected": "PENDING_REVIEW",
        "title": "Existing vendor's PAN/GSTIN with a new name and new bank account",
        "company": DECCAN_NEW["legal_name"],
        "description": "PAN, GSTIN and CIN belong to existing vendor VEND-0003 (Deccan Paper Products). The submission uses a new "
                       "name and a new bank account, with documents edited to match. Registries and the vendor master expose it.",
        "talking_points": ["Bank changes must go through change control", "Registry name ≠ submitted name",
                           "Vendor master cross-check"],
        "form": form_for(DECCAN_NEW), "docs": standard_docs(DECCAN_NEW),
    },
    {
        "id": "07-sanctions-near-match", "featured": True, "edge_case": "sanctions", "expected": "PENDING_REVIEW → reviewer clears → APPROVED",
        "title": "Watchlist near-match → human review, not auto-reject",
        "company": ZENITH["legal_name"],
        "description": "Trade name 'Zenith Global Trading' matches listed entity 'ZENITH GLOBAL TRADING FZE' (UAE). Different "
                       "jurisdiction, no identifier match → potential match routed to a compliance reviewer, who can clear it "
                       "as a false positive with a mandatory note.",
        "talking_points": ["Fuzzy screening: score + jurisdiction + identifiers", "False positives cost real vendors",
                           "Reviewer override is audited"],
        "form": form_for(ZENITH), "docs": standard_docs(ZENITH, bank="letter"),
    },
    {
        "id": "08-exact-duplicate", "featured": False, "edge_case": "duplicate", "expected": "REJECTED",
        "title": "Already a vendor — duplicate registration",
        "company": DECCAN["legal_name"],
        "description": "Same PAN, GSTIN, name and bank account as existing vendor VEND-0003. Rejected as a duplicate with a "
                       "pointer to the existing vendor code.",
        "talking_points": ["Duplicate vendors = duplicate payments", "Reject with a helpful next step"],
        "form": form_for(DECCAN), "docs": standard_docs(DECCAN),
    },
    {
        "id": "09-cancelled-gst-struck-off", "featured": False, "edge_case": None, "expected": "REJECTED",
        "title": "GST cancelled and company struck off",
        "company": VINDHYA["legal_name"],
        "description": "All formats valid and documents consistent, but the GST portal shows the registration Cancelled and MCA "
                       "shows the company as 'Strike Off'. Disqualifying → rejected with the reason disclosed.",
        "talking_points": ["Documents are a snapshot; registries are the truth", "Hard reject vs. pending"],
        "form": form_for(VINDHYA), "docs": standard_docs(VINDHYA),
    },
]


def render_docs(target: Path, docs: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    out: Dict[str, str] = {}
    rendered: Dict[str, str] = {}
    for slot, (kind, v) in docs.items():
        key = f"{kind}:{id(v)}"
        if key in rendered:
            # Same underlying document reused in another slot -> identical file bytes.
            src = target / rendered[key]
            name = f"{prefix}{SLUG[slot]}.pdf"
            shutil.copyfile(src, target / name)
            out[slot] = name
            continue
        name = f"{prefix}{SLUG[slot]}.pdf"
        RENDERERS[kind](target / name, v)
        rendered[key] = name
        out[slot] = name
    return out


def main() -> None:
    if OUT.exists():
        # Every file is rewritten below, so a file locked by a PDF viewer on Windows is not fatal.
        shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for sc in SCENARIOS:
        target = OUT / sc["id"]
        target.mkdir(exist_ok=True)
        files = render_docs(target, sc["docs"])
        entry = {k: v for k, v in sc.items() if k not in ("docs", "fix")}
        entry["documents"] = files
        (target / "submission.json").write_text(json.dumps(sc["form"], indent=2), encoding="utf-8")
        if "fix" in sc:
            fix_files = render_docs(target, sc["fix"]["docs"], prefix="fix_")
            entry["fix"] = {"form": sc["fix"]["form"], "documents": fix_files}
            (target / "fix_submission.json").write_text(json.dumps(sc["fix"]["form"], indent=2), encoding="utf-8")
        manifest.append(entry)
    (OUT / "scenarios.json").write_text(json.dumps({"generated_on": TODAY.isoformat(), "scenarios": manifest}, indent=2),
                                        encoding="utf-8")
    print(f"Generated {len(manifest)} scenarios in {OUT}")


if __name__ == "__main__":
    main()
