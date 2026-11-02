"""Entity-name normalisation and fuzzy comparison.

Indian company names show up in many spellings across documents
("Private Limited", "Pvt. Ltd.", "P Ltd", "M/s ..."), and bank core systems
often truncate the account name. Naive string equality produces false
mismatches; naive fuzzy matching lets "ABC Traders LLP" pass for
"ABC Traders Pvt Ltd" (a different legal entity). This module handles both.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

_TOKEN_REWRITES: Dict[str, str] = {
    "PRIVATE": "PVT",
    "PVT": "PVT",
    "LIMITED": "LTD",
    "LTD": "LTD",
    "COMPANY": "CO",
    "CORPORATION": "CORP",
    "INCORPORATED": "INC",
    "AND": "AND",
    "INDUSTRIES": "INDUSTRIES",
}

# Legal-form suffix groups. Two names whose cores match but whose suffix
# groups differ are *different legal entities* (e.g. LLP vs Pvt Ltd).
_SUFFIX_GROUPS: List[Tuple[str, Tuple[str, ...]]] = [
    ("PVT LTD", ("PVT LTD", "P LTD", "PVT")),
    ("LTD", ("LTD",)),
    ("LLP", ("LLP",)),
    ("OPC", ("OPC PVT LTD", "OPC")),
    ("FZE", ("FZE", "FZCO", "FZ LLC")),
    ("LLC", ("LLC",)),
    ("INC", ("INC",)),
    ("CORP", ("CORP",)),
    ("CO", ("CO",)),
]

_PREFIXES = ("M/S", "MS", "THE")


@dataclass
class NameMatch:
    score: int
    verdict: str  # exact | strong | partial | mismatch
    left_normalized: str
    right_normalized: str
    explanation: str

    @property
    def is_match(self) -> bool:
        return self.verdict in ("exact", "strong")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_match"] = self.is_match
        return d


def normalize_name(name: Optional[str]) -> str:
    if not name:
        return ""
    s = name.upper().replace("&", " AND ")
    s = re.sub(r"\bM\s*/\s*S\b\.?", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    tokens = [t for t in s.split() if t]
    while tokens and tokens[0] in _PREFIXES:
        tokens = tokens[1:]
    tokens = [_TOKEN_REWRITES.get(t, t) for t in tokens]
    return " ".join(tokens)


def split_suffix(normalized: str) -> Tuple[str, str]:
    """Return (core_name, suffix_group). suffix_group is '' when absent."""
    for group, variants in _SUFFIX_GROUPS:
        for variant in variants:
            if normalized == variant:
                continue
            if normalized.endswith(" " + variant):
                return normalized[: -len(variant) - 1].strip(), group
    return normalized, ""


def core_name(name: Optional[str]) -> str:
    return split_suffix(normalize_name(name))[0]


def compare_names(left: Optional[str], right: Optional[str]) -> NameMatch:
    ln, rn = normalize_name(left), normalize_name(right)
    if not ln or not rn:
        return NameMatch(0, "mismatch", ln, rn, "One of the names is empty")
    if ln == rn:
        return NameMatch(100, "exact", ln, rn, "Identical after normalising punctuation and legal-suffix spelling")

    lcore, lsuf = split_suffix(ln)
    rcore, rsuf = split_suffix(rn)

    if lcore == rcore:
        if lsuf and rsuf and lsuf != rsuf:
            return NameMatch(
                70,
                "partial",
                ln,
                rn,
                f"Same name but different legal form ({lsuf} vs {rsuf}) — these are different entities",
            )
        return NameMatch(96, "strong", ln, rn, "Same entity name; legal suffix omitted on one side")

    # Bank core systems truncate long account names (often ~30-35 chars).
    shorter, longer = sorted([ln, rn], key=len)
    if len(shorter.split()) >= 2 and len(shorter) >= 15 and longer.startswith(shorter):
        return NameMatch(92, "strong", ln, rn, "One name is a truncated form of the other")

    score = int(round(fuzz.token_sort_ratio(lcore, rcore)))
    if score >= 90:
        return NameMatch(score, "strong", ln, rn, "Minor spelling variation")
    if score >= 75:
        return NameMatch(score, "partial", ln, rn, "Names are similar but not the same — needs a closer look")
    return NameMatch(score, "mismatch", ln, rn, "Names refer to different parties")


def best_match(name: Optional[str], candidates: List[Optional[str]]) -> NameMatch:
    results = [compare_names(name, c) for c in candidates if c]
    if not results:
        return compare_names(name, None)
    return max(results, key=lambda m: m.score)
