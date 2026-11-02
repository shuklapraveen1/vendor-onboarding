"""Mock external verification services.

Each class mirrors the shape of a real integration (GST public search API,
MCA master data, RBI IFSC directory, a penny-drop bank verification API and a
sanctions screening provider) so swapping in the real thing only changes
the class body, not the pipeline. Responses carry `source` so the UI and the
audit trail always show whether a result came from seeded data or was
simulated for an unknown identifier.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, List, Optional

from rapidfuzz import fuzz

from . import config
from .matching import core_name, normalize_name
from .validators.india import GST_STATE_CODES, CIN_STATE_CODES


@lru_cache(maxsize=None)
def _load(name: str) -> Dict[str, Any]:
    with open(config.SEED_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


class GSTPortal:
    """Stand-in for the GST 'Search Taxpayer' API."""

    name = "GST Portal (mock)"

    def lookup(self, gstin: str, submitted_name: Optional[str] = None) -> Dict[str, Any]:
        record = _load("gst_portal.json")["records"].get(gstin)
        state = GST_STATE_CODES.get(gstin[:2], "Unknown")
        if record:
            return {"found": True, "source": "seeded", "gstin": gstin, "state": state, **record}
        # Unknown GSTIN with a valid structure: simulate an active registration
        # so ad-hoc inputs during a demo still flow end-to-end.
        return {
            "found": True,
            "source": "simulated",
            "gstin": gstin,
            "state": state,
            "legal_name": (submitted_name or "").upper(),
            "trade_name": None,
            "status": "Active",
            "constitution": None,
            "registration_date": None,
        }


class MCARegistry:
    """Stand-in for MCA company master data lookup."""

    name = "MCA Registry (mock)"

    def lookup(self, cin: str, submitted_name: Optional[str] = None) -> Dict[str, Any]:
        record = _load("mca_registry.json")["records"].get(cin)
        state = CIN_STATE_CODES.get(cin[6:8], "Unknown") if len(cin) == 21 else "Unknown"
        if record:
            return {"found": True, "source": "seeded", "cin": cin, "state": state, **record}
        return {
            "found": True,
            "source": "simulated",
            "cin": cin,
            "state": state,
            "company_name": (submitted_name or "").upper(),
            "status": "Active",
            "date_of_incorporation": None,
        }


class BankDirectory:
    """Stand-in for the RBI IFSC directory."""

    name = "IFSC Directory (mock)"

    def lookup_ifsc(self, ifsc: str) -> Dict[str, Any]:
        data = _load("banks.json")
        bank = data["bank_codes"].get(ifsc[:4])
        if not bank:
            return {"found": False, "source": "seeded", "ifsc": ifsc}
        branch = data["branches"].get(ifsc)
        if branch:
            return {"found": True, "source": "seeded", "ifsc": ifsc, "bank": bank, **branch}
        return {"found": True, "source": "simulated", "ifsc": ifsc, "bank": bank, "branch": None, "city": None, "state": None}


class PennyDrop:
    """Stand-in for a penny-drop / account validation API (e.g. via NPCI IMPS).

    Real APIs deposit ₹1 and return the beneficiary name registered with the
    bank. That returned name is the ground truth we compare against.
    """

    name = "Bank Account Verification (mock penny-drop)"

    def verify(self, account_number: str, ifsc: str, submitted_holder: Optional[str]) -> Dict[str, Any]:
        accounts = _load("banks.json")["accounts"]
        registered = accounts.get(f"{account_number}|{ifsc}")
        if registered:
            return {"account_exists": True, "source": "seeded", "registered_name": registered}
        return {
            "account_exists": True,
            "source": "simulated",
            "registered_name": (submitted_holder or "").upper(),
        }


class SanctionsScreening:
    """Fuzzy name screening against a (fictional) consolidated watchlist."""

    name = "Sanctions Screening (demo watchlist)"

    def __init__(self) -> None:
        data = _load("sanctions.json")
        self.list_name = data["list_name"]
        self.list_version = data["list_version"]
        self.entries: List[Dict[str, Any]] = data["entries"]

    @staticmethod
    def _score(a: str, b: str) -> int:
        ca, cb = core_name(a), core_name(b)
        if not ca or not cb:
            return 0
        if ca == cb:
            return 100
        # token_sort_ratio, not token_set_ratio: set-ratio scores a subset
        # ("GLOBAL TRADING" vs "ZENITH GLOBAL TRADING") as 100 and floods
        # reviewers with false positives.
        return int(round(fuzz.token_sort_ratio(ca, cb)))

    def screen(self, name: str, party_type: str, country: str = "India") -> List[Dict[str, Any]]:
        hits = []
        if not normalize_name(name):
            return hits
        for entry in self.entries:
            if party_type != entry["type"]:
                continue
            names = [entry["name"], *entry.get("aliases", [])]
            best_name, best_score = max(((n, self._score(name, n)) for n in names), key=lambda x: x[1])
            if best_score >= config.SANCTIONS_REVIEW_SCORE:
                hits.append(
                    {
                        "entry_id": entry["id"],
                        "listed_name": entry["name"],
                        "matched_on": best_name,
                        "score": best_score,
                        "country": entry["country"],
                        "country_matches": entry["country"].lower() == country.lower(),
                        "program": entry["program"],
                        "listed_on": entry["listed_on"],
                        "identifiers": entry.get("identifiers", {}),
                    }
                )
        return sorted(hits, key=lambda h: -h["score"])


def seeded_vendor_master() -> List[Dict[str, Any]]:
    return list(_load("vendor_master.json")["vendors"])
