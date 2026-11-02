"""Request schemas.

Submission fields are deliberately optional: an incomplete submission is a
valid *input* — the completeness stage turns gaps into precise requests
back to the vendor instead of a 422 the vendor never sees.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Str = Optional[str]


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, str_max_length=300)


class Company(_Section):
    legal_name: Str = None
    trade_name: Str = None
    business_type: Str = None
    date_of_incorporation: Str = None
    cin: Str = None
    llpin: Str = None
    website: Str = None


class Address(_Section):
    line1: Str = None
    line2: Str = None
    city: Str = None
    state: Str = None
    pincode: Str = None


class Tax(_Section):
    pan: Str = None
    gstin: Str = None
    msme_registered: bool = False
    udyam_number: Str = None


class Bank(_Section):
    account_holder_name: Str = None
    account_number: Str = None
    confirm_account_number: Str = None
    ifsc: Str = None
    bank_name: Str = None
    account_type: Str = None


class Contact(_Section):
    name: Str = None
    designation: Str = None
    email: Str = None
    phone: Str = None


class Signatory(_Section):
    name: Str = None
    designation: Str = None


class Declaration(_Section):
    accepted: bool = False


class VendorSubmission(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company: Company = Field(default_factory=Company)
    address: Address = Field(default_factory=Address)
    tax: Tax = Field(default_factory=Tax)
    bank: Bank = Field(default_factory=Bank)
    contact: Contact = Field(default_factory=Contact)
    signatory: Signatory = Field(default_factory=Signatory)
    declaration: Declaration = Field(default_factory=Declaration)


class ReviewAction(BaseModel):
    action: Literal["approve", "reject", "request_info"]
    reviewer: str = Field(min_length=2, max_length=80)
    note: str = Field(min_length=10, max_length=2000, description="Internal justification, kept in the audit trail")
    vendor_note: Optional[str] = Field(default=None, max_length=2000, description="Optional text added to the vendor message")
