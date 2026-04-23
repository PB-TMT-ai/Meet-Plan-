"""Distribute zone-level monthly meet targets across SM/TMs in that zone.

Input:
  - team:               sm_tm, role, zone, state
  - district master:    district, zone, category, sm, tm
  - previous_meets:     sm_tm, counter_id, meet_type
  - zone_breakup wide:  zone, meet_type, april/may/june counts

Rules:
  - Dealer slots: prioritize SM/TMs who did NOT do dealer last month (rotation).
  - Architect slots: HP-district SM/TMs only; prefer those who DID dealer last month.
  - Hard rule: a SM/TM cannot get both dealer and architect in the same month.
  - Contractor slots: HP-district SM/TMs only; equal-as-possible distribution; cap 2 per SM/TM.
  - Mason: not allocated here — the planner fills mason to reach >= MIN_OPTIONS per SM/TM.

Returns a per-SM/TM dict of slot counts: {'dealer': 0|1, 'architect': 0|1, 'contractor': 0..2}.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

CONTRACTOR_CAP = 2
HP_CATEGORIES = {"Very High", "High"}


def _hp_districts(district: pd.DataFrame) -> set[str]:
    return set(
        district.loc[district["category"].isin(HP_CATEGORIES), "district"]
        .astype(str).str.strip().str.upper()
    )


def _sm_tm_to_districts(district: pd.DataFrame) -> dict[str, set[str]]:
    """Reverse map: SM/TM name -> set of upper-stripped districts they cover (via SM or TM column)."""
    out: dict[str, set[str]] = {}
    for _, r in district.iterrows():
        d = str(r["district"]).strip().upper()
        if not d or d == "NAN":
            continue
        for col in ("sm", "tm"):
            v = r.get(col)
            if v and str(v).strip().lower() not in {"", "nan", "none"}:
                out.setdefault(str(v).strip(), set()).add(d)
    return out


def _is_hp_smtm(sm_tm: str, sm_tm_districts: dict[str, set[str]], hp: set[str]) -> bool:
    """True if any of the SM/TM's covered districts is high-potential."""
    return bool(sm_tm_districts.get(sm_tm, set()) & hp)


def _did_dealer_last_month(prev: pd.DataFrame) -> set[str]:
    return set(prev.loc[prev["meet_type"] == "dealer", "sm_tm"].astype(str))


def distribute(
    team: pd.DataFrame,
    district: pd.DataFrame,
    previous_meets: pd.DataFrame,
    zone_breakup: pd.DataFrame,
    month_col: str,
) -> dict[str, dict[str, int]]:
    """Return {sm_tm: {'dealer': n, 'architect': n, 'contractor': n}} for the chosen month.

    Mason slots are computed downstream by the planner.
    """
    hp = _hp_districts(district)
    sm_tm_to_districts = _sm_tm_to_districts(district)
    did_dealer = _did_dealer_last_month(previous_meets)

    # init zero-slot allocation for everyone
    alloc: dict[str, dict[str, int]] = {
        s: {"dealer": 0, "architect": 0, "contractor": 0} for s in team["sm_tm"]
    }

    for zone, group in team.groupby("zone"):
        members = group["sm_tm"].tolist()
        zb = zone_breakup[zone_breakup["zone"] == zone]
        targets = {row["meet_type"]: int(row[month_col]) for _, row in zb.iterrows()}

        dealer_target = targets.get("dealer", 0)
        architect_target = targets.get("architect", 0)
        contractor_target = targets.get("contractor", 0)

        # ---- Dealer: prefer SM/TMs who did NOT do dealer last month ----
        non_dealer_pool = [s for s in members if s not in did_dealer]
        dealer_pool     = [s for s in members if s in did_dealer]
        dealer_assignees = (non_dealer_pool + dealer_pool)[:dealer_target]
        for s in dealer_assignees:
            alloc[s]["dealer"] = 1

        # ---- Architect: HP only, prefer those who DID dealer last month, exclude dealer assignees ----
        dealer_set = set(dealer_assignees)
        hp_pool = [s for s in members if _is_hp_smtm(s, sm_tm_to_districts, hp) and s not in dealer_set]
        prefer = [s for s in hp_pool if s in did_dealer]
        rest   = [s for s in hp_pool if s not in did_dealer]
        architect_assignees = (prefer + rest)[:architect_target]
        for s in architect_assignees:
            alloc[s]["architect"] = 1

        # ---- Contractor: HP only, equal-as-possible, cap 2 ----
        hp_members = [s for s in members if _is_hp_smtm(s, sm_tm_to_districts, hp)]
        if hp_members and contractor_target > 0:
            base = contractor_target // len(hp_members)
            remainder = contractor_target - base * len(hp_members)
            for s in hp_members:
                alloc[s]["contractor"] = min(base, CONTRACTOR_CAP)
            i = 0
            while remainder > 0 and i < len(hp_members) * 2:  # safety cap
                idx = i % len(hp_members)
                if alloc[hp_members[idx]]["contractor"] < CONTRACTOR_CAP:
                    alloc[hp_members[idx]]["contractor"] += 1
                    remainder -= 1
                i += 1

    return alloc


def audit(
    alloc: dict[str, dict[str, int]],
    team: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for s, slots in alloc.items():
        zone = team.loc[team["sm_tm"] == s, "zone"].iloc[0]
        rows.append({"sm_tm": s, "zone": zone, **slots})
    return pd.DataFrame(rows)
