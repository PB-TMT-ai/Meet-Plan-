"""Compute per-SM/TM lists of mason-meet-eligible counters.

Counter -> SM/TM cascade:
  1. KAM-Dealer mapping (counter_id -> SM/TM, aliased to roster)
  2. District-file TM for the counter's district (if any)
  3. District-file SM for the counter's district (if any)
  4. otherwise: "Unassigned" (kept in pool, flagged in output)

Eligibility (mason meet):
  primary  = stock_mt > STOCK_THRESHOLD_MT AND counter not met (mason) last month
  prospect = stock_mt <= STOCK_THRESHOLD_MT in the same district pool, not met last month
             (used as fallback when an SM/TM has fewer than MIN_MASON_TARGET primary counters)

For the 5-ish SM/TMs with NO mapped counters, prospect counters in their state pool
are surfaced (user instruction: "those without counters mapped get prospect counters").

Usage:
    python tools/eligible_mason_counters.py --print
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import load_inputs  # noqa: E402

STOCK_THRESHOLD_MT = 10.0
MIN_MASON_TARGET = 6
UNASSIGNED = "UNASSIGNED"


def _prospect_row(sm_tm: str, r: pd.Series) -> dict:
    return {
        "sm_tm": sm_tm,
        "counter_id": r["counter_id"],
        "counter_name": r["counter_name"],
        "district": r["district"],
        "stock_mt": float(r["stock_mt"]),
        "notes": "prospect counter - stock fallback",
    }


def _district_owner_lookup(district: pd.DataFrame) -> dict[str, dict[str, str | None]]:
    """district name (upper-stripped) -> {'tm': name | None, 'sm': name | None}."""
    out: dict[str, dict[str, str | None]] = {}
    for _, r in district.iterrows():
        key = str(r["district"]).strip().upper()
        if not key or key == "NAN":
            continue
        out.setdefault(key, {"tm": None, "sm": None})
        for col in ("tm", "sm"):
            v = r.get(col)
            if v and str(v).strip().lower() not in {"", "nan", "none"}:
                out[key][col] = str(v).strip()
    return out


def _attribute_counters(
    stock: pd.DataFrame,
    kam_dealer: pd.DataFrame,
    district: pd.DataFrame,
    roster: list[str],
) -> pd.DataFrame:
    """Return stock with one extra `sm_tm` column (cascade-resolved)."""
    import normalize_names

    kam_lookup = dict(zip(kam_dealer["counter_id"].astype(str), kam_dealer["sm_tm"]))
    district_lookup = _district_owner_lookup(district)
    roster_alias = normalize_names.build_alias_map(
        roster, [v for owners in district_lookup.values() for v in owners.values() if v]
    )

    def resolve(row: pd.Series) -> str:
        cid = str(row["counter_id"])
        if cid in kam_lookup:
            return kam_lookup[cid]
        owners = district_lookup.get(str(row["district"]).strip().upper())
        if owners:
            for col in ("tm", "sm"):
                cand = owners.get(col)
                if cand:
                    return roster_alias.get(cand, cand)
        return UNASSIGNED

    out = stock.copy()
    out["sm_tm"] = out.apply(resolve, axis=1)
    out["sm_tm_in_roster"] = out["sm_tm"].isin(roster) | (out["sm_tm"] == UNASSIGNED)
    return out


def compute(
    stock: pd.DataFrame,
    previous_meets: pd.DataFrame,
    team: pd.DataFrame,
    kam_dealer: pd.DataFrame,
    district: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (eligible_rows, attributed_stock).

    eligible_rows columns: sm_tm, counter_id, counter_name, district, stock_mt, notes
    attributed_stock columns: stock + sm_tm column (used by other tools to inspect coverage).
    """
    roster = team["sm_tm"].tolist()
    attributed = _attribute_counters(stock, kam_dealer, district, roster)

    # mason previous meets only — we exclude only mason counter visits
    mason_prev = previous_meets[previous_meets["meet_type"] == "mason"]
    met_pairs = set(zip(mason_prev["sm_tm"].astype(str), mason_prev["counter_id"].astype(str)))

    rows: list[dict] = []

    for sm_tm in team["sm_tm"]:
        sm_district_pool = attributed[attributed["sm_tm"] == sm_tm]
        sm_state = team.loc[team["sm_tm"] == sm_tm, "state"].iloc[0]

        primary = sm_district_pool[sm_district_pool["stock_mt"] > STOCK_THRESHOLD_MT].copy()
        if not primary.empty:
            mask = primary["counter_id"].astype(str).map(lambda cid: (sm_tm, cid) not in met_pairs)
            primary = primary[mask].sort_values("stock_mt", ascending=False)

        for _, r in primary.iterrows():
            rows.append({
                "sm_tm": sm_tm,
                "counter_id": r["counter_id"],
                "counter_name": r["counter_name"],
                "district": r["district"],
                "stock_mt": float(r["stock_mt"]),
                "notes": "",
            })

        if len(primary) < MIN_MASON_TARGET:
            used = set(primary["counter_id"].astype(str))
            target_extra = MIN_MASON_TARGET + 4 - len(primary)  # cushion of 4 above target
            # tier 1: own low-stock counters
            tier1 = sm_district_pool[
                (sm_district_pool["stock_mt"] <= STOCK_THRESHOLD_MT)
                & (~sm_district_pool["counter_id"].astype(str).isin(used))
            ].sort_values("stock_mt", ascending=False)
            added = 0
            for _, r in tier1.iterrows():
                rows.append(_prospect_row(sm_tm, r))
                used.add(str(r["counter_id"]))
                added += 1
                if added >= target_extra:
                    break

            # tier 2: state-wide prospects (any owner) if we still need more
            if added < target_extra:
                state_districts = set(
                    district.loc[
                        district["state"].astype(str).str.strip().str.lower()
                        == sm_state.strip().lower(),
                        "district",
                    ].astype(str).str.strip().str.upper()
                )
                tier2 = attributed[
                    (~attributed["counter_id"].astype(str).isin(used))
                    & (attributed["district"].astype(str).str.strip().str.upper().isin(state_districts))
                ].sort_values("stock_mt", ascending=False)
                for _, r in tier2.iterrows():
                    rows.append(_prospect_row(sm_tm, r))
                    used.add(str(r["counter_id"]))
                    added += 1
                    if added >= target_extra:
                        break

    eligible = pd.DataFrame(rows, columns=[
        "sm_tm", "counter_id", "counter_name", "district", "stock_mt", "notes",
    ])
    return eligible, attributed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()

    try:
        data = load_inputs.load_all()
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    eligible, attributed = compute(
        stock=data["stock"],
        previous_meets=data["previous_meets"],
        team=data["team_members"],
        kam_dealer=data["kam_dealer"],
        district=data["high_potential_districts"],
    )

    if args.print:
        counts = eligible.groupby("sm_tm").size().reset_index(name="eligible_count").sort_values("eligible_count")
        print(counts.to_string(index=False))
        low = counts[counts["eligible_count"] < MIN_MASON_TARGET]
        if not low.empty:
            print(
                f"\nWARNING: {len(low)} SM/TM(s) still have < {MIN_MASON_TARGET} eligible "
                "mason counters even after prospect fallback:",
                file=sys.stderr,
            )
            print(low.to_string(index=False), file=sys.stderr)
        unassigned = (attributed["sm_tm"] == UNASSIGNED).sum()
        print(f"\nUnassigned counters in attributed stock: {unassigned}")
    else:
        print(f"Computed {len(eligible)} eligible mason rows across "
              f"{eligible['sm_tm'].nunique()} SM/TMs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
