"""Strict subset-token name normalizer for SM/TM aliases.

Two names match if one's significant tokens (alphabetic, len>1) are a subset of
the other's. Exact (case-insensitive) matches always win when there's ambiguity.

This handles the messy reality that SM/TM names appear in different forms across
files — e.g. "Paritosh" in Headcount vs "Paritosh Kaushik" in the dealer mapping,
"Rahul Kumar Gautam" vs "Rahul Gautam", "BIDYUT MISHRA" vs "Bidyut Ranjan Mishra".
"""

from __future__ import annotations

import re

JUNK_VALUES = {"#SPILL!", "0", "nan", "", "none"}


def tokens(name: str) -> frozenset[str]:
    """Significant alphabetic tokens of a name, lowercased, length > 1."""
    return frozenset(t for t in re.findall(r"[a-z]+", str(name).lower()) if len(t) > 1)


def is_junk(name: str) -> bool:
    return str(name).strip() in JUNK_VALUES or not str(name).strip()


def build_alias_map(roster: list[str], candidates: list[str]) -> dict[str, str]:
    """Map each candidate name -> a roster name when it matches.

    Exact (case-insensitive) match wins. Otherwise strict subset-token match.
    Candidates with no roster match (KAMs, junk) are absent from the result.
    """
    roster_clean = [r for r in roster if not is_junk(r)]
    roster_by_lower = {r.lower(): r for r in roster_clean}
    roster_tokens = {r: tokens(r) for r in roster_clean}

    out: dict[str, str] = {}
    for c in candidates:
        if is_junk(c):
            continue
        # exact (case-insensitive) match wins
        exact = roster_by_lower.get(c.lower())
        if exact is not None:
            out[c] = exact
            continue
        ct = tokens(c)
        if not ct:
            continue
        for r, rt in roster_tokens.items():
            if rt and (rt <= ct or ct <= rt):
                out[c] = r
                break
    return out
