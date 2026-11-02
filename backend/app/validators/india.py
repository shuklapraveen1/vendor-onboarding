"""Format and structural validators for Indian vendor identifiers.

Every validator returns a ValidationResult so the pipeline can explain *why*
a value failed (wrong length vs. bad checksum vs. unknown state code), which
is what lets the vendor message say something more useful than "invalid".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional

GSTIN_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# GST state codes (first two digits of a GSTIN).
GST_STATE_CODES: Dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

STATE_TO_GST_CODE: Dict[str, str] = {
    v: k for k, v in GST_STATE_CODES.items() if k not in ("97", "99")
}
INDIAN_STATES = sorted(STATE_TO_GST_CODE.keys())

# Registrar-of-Companies state codes used inside a CIN.
CIN_STATE_CODES: Dict[str, str] = {
    "AP": "Andhra Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CH": "Chandigarh",
    "CT": "Chhattisgarh",
    "DL": "Delhi",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HP": "Himachal Pradesh",
    "HR": "Haryana",
    "JH": "Jharkhand",
    "JK": "Jammu and Kashmir",
    "KA": "Karnataka",
    "KL": "Kerala",
    "MH": "Maharashtra",
    "MP": "Madhya Pradesh",
    "OR": "Odisha",
    "PB": "Punjab",
    "PY": "Puducherry",
    "RJ": "Rajasthan",
    "TG": "Telangana",
    "TN": "Tamil Nadu",
    "UP": "Uttar Pradesh",
    "UR": "Uttarakhand",
    "WB": "West Bengal",
}

CIN_OWNERSHIP_TYPES: Dict[str, str] = {
    "PTC": "Private Limited Company",
    "PLC": "Public Limited Company",
    "FTC": "Subsidiary of Foreign Company",
    "GOI": "Government of India Company",
    "SGC": "State Government Company",
    "NPL": "Not-for-profit (Section 8) Company",
    "OPC": "One Person Company",
    "ULL": "Public Unlimited Company",
    "ULT": "Private Unlimited Company",
}

# PAN 4th character -> holder type.
PAN_HOLDER_TYPES: Dict[str, str] = {
    "P": "Individual",
    "C": "Company",
    "H": "Hindu Undivided Family",
    "F": "Firm / LLP",
    "A": "Association of Persons",
    "T": "Trust",
    "B": "Body of Individuals",
    "L": "Local Authority",
    "J": "Artificial Juridical Person",
    "G": "Government",
}

BUSINESS_TYPES: Dict[str, str] = {
    "PRIVATE_LIMITED": "Private Limited Company",
    "PUBLIC_LIMITED": "Public Limited Company",
    "LLP": "Limited Liability Partnership",
    "PARTNERSHIP": "Partnership Firm",
    "PROPRIETORSHIP": "Sole Proprietorship",
}

# Which PAN holder type is legitimate for each declared constitution.
EXPECTED_PAN_TYPE: Dict[str, str] = {
    "PRIVATE_LIMITED": "C",
    "PUBLIC_LIMITED": "C",
    "LLP": "F",
    "PARTNERSHIP": "F",
    "PROPRIETORSHIP": "P",
}

EXPECTED_CIN_TYPES: Dict[str, tuple] = {
    "PRIVATE_LIMITED": ("PTC", "OPC", "FTC"),
    "PUBLIC_LIMITED": ("PLC", "GOI", "SGC"),
}

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
CIN_RE = re.compile(r"^([LU])([0-9]{5})([A-Z]{2})([0-9]{4})([A-Z]{3})([0-9]{6})$")
LLPIN_RE = re.compile(r"^[A-Z]{3}-[0-9]{4}$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[6-9][0-9]{9}$")
PINCODE_RE = re.compile(r"^[1-9][0-9]{5}$")
ACCOUNT_RE = re.compile(r"^[0-9]{9,18}$")


@dataclass
class ValidationResult:
    valid: bool
    value: str
    reason: str = ""
    details: Dict[str, str] = field(default_factory=dict)


def clean_id(value: Optional[str]) -> str:
    """Upper-case and strip whitespace — vendors paste IDs with spaces."""
    if not value:
        return ""
    return re.sub(r"\s+", "", str(value)).upper()


def gstin_checksum_char(first14: str) -> str:
    """GSTIN check character: Luhn mod-36 over the first 14 characters."""
    total = 0
    for i, ch in enumerate(first14):
        code = GSTIN_CHARSET.index(ch)
        product = code * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return GSTIN_CHARSET[(36 - total % 36) % 36]


def validate_pan(value: Optional[str]) -> ValidationResult:
    pan = clean_id(value)
    if len(pan) != 10:
        return ValidationResult(False, pan, f"PAN must be 10 characters (got {len(pan)})")
    if not PAN_RE.match(pan):
        return ValidationResult(
            False, pan, "PAN must be 5 letters, 4 digits, 1 letter (e.g. AABCK1234L)"
        )
    holder = PAN_HOLDER_TYPES.get(pan[3])
    if not holder:
        return ValidationResult(False, pan, f"4th character '{pan[3]}' is not a valid PAN holder type")
    return ValidationResult(True, pan, details={"holder_type_code": pan[3], "holder_type": holder})


def validate_gstin(value: Optional[str]) -> ValidationResult:
    gstin = clean_id(value)
    if len(gstin) != 15:
        return ValidationResult(False, gstin, f"GSTIN must be 15 characters (got {len(gstin)})")
    if not GSTIN_RE.match(gstin):
        return ValidationResult(
            False, gstin, "GSTIN structure is invalid (expected 2-digit state code + PAN + entity no. + 'Z' + check char)"
        )
    state_code = gstin[:2]
    if state_code not in GST_STATE_CODES:
        return ValidationResult(False, gstin, f"'{state_code}' is not a valid GST state code")
    expected = gstin_checksum_char(gstin[:14])
    if gstin[14] != expected:
        return ValidationResult(
            False,
            gstin,
            "GSTIN check digit does not match — the number has a typo",
            {"expected_check_char": expected},
        )
    return ValidationResult(
        True,
        gstin,
        details={
            "state_code": state_code,
            "state": GST_STATE_CODES[state_code],
            "embedded_pan": gstin[2:12],
        },
    )


def validate_ifsc(value: Optional[str]) -> ValidationResult:
    ifsc = clean_id(value)
    if not IFSC_RE.match(ifsc):
        return ValidationResult(
            False, ifsc, "IFSC must be 11 characters: 4-letter bank code, '0', 6-character branch code"
        )
    return ValidationResult(True, ifsc, details={"bank_code": ifsc[:4]})


def validate_cin(value: Optional[str], today: Optional[date] = None) -> ValidationResult:
    cin = clean_id(value)
    today = today or date.today()
    m = CIN_RE.match(cin)
    if not m:
        return ValidationResult(False, cin, "CIN must be 21 characters, e.g. U29100KA2015PTC081234")
    listing, _industry, state, year, ownership, _reg = m.groups()
    if state not in CIN_STATE_CODES:
        return ValidationResult(False, cin, f"'{state}' is not a valid Registrar-of-Companies state code")
    if not (1850 <= int(year) <= today.year):
        return ValidationResult(False, cin, f"Incorporation year {year} in CIN is not plausible")
    if ownership not in CIN_OWNERSHIP_TYPES:
        return ValidationResult(False, cin, f"'{ownership}' is not a valid company ownership code")
    return ValidationResult(
        True,
        cin,
        details={
            "listed": "Listed" if listing == "L" else "Unlisted",
            "state_code": state,
            "state": CIN_STATE_CODES[state],
            "year": year,
            "ownership": ownership,
            "ownership_label": CIN_OWNERSHIP_TYPES[ownership],
        },
    )


def validate_llpin(value: Optional[str]) -> ValidationResult:
    llpin = clean_id(value)
    if not LLPIN_RE.match(llpin):
        return ValidationResult(False, llpin, "LLPIN must look like AAB-1234")
    return ValidationResult(True, llpin)


def validate_udyam(value: Optional[str]) -> ValidationResult:
    udyam = clean_id(value)
    if not UDYAM_RE.match(udyam):
        return ValidationResult(False, udyam, "Udyam number must look like UDYAM-KR-03-0012345")
    return ValidationResult(True, udyam)


def validate_email(value: Optional[str]) -> ValidationResult:
    email = (value or "").strip()
    if not EMAIL_RE.match(email):
        return ValidationResult(False, email, "Email address is not valid")
    return ValidationResult(True, email.lower())


def normalize_phone(value: Optional[str]) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def validate_phone(value: Optional[str]) -> ValidationResult:
    phone = normalize_phone(value)
    if not PHONE_RE.match(phone):
        return ValidationResult(False, phone, "Mobile number must be 10 digits starting with 6-9 (optional +91)")
    return ValidationResult(True, phone)


def validate_pincode(value: Optional[str]) -> ValidationResult:
    pin = clean_id(value)
    if not PINCODE_RE.match(pin):
        return ValidationResult(False, pin, "PIN code must be 6 digits and cannot start with 0")
    return ValidationResult(True, pin)


def validate_account_number(value: Optional[str]) -> ValidationResult:
    acct = clean_id(value)
    if not ACCOUNT_RE.match(acct):
        return ValidationResult(False, acct, "Bank account number must be 9-18 digits")
    return ValidationResult(True, acct)


def mask_account(value: Optional[str]) -> str:
    acct = clean_id(value)
    if len(acct) <= 4:
        return acct
    return "X" * (len(acct) - 4) + acct[-4:]
