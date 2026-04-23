"""Compute per-SM/TM lists of mason-meet-eligible counters.

Eligibility: counter's stock > 10 MT AND counter_id NOT in last month's meet log.
If an SM/TM has fewer than `MIN_MASON_TARGET` eligible counters, prospect counters
(same district, `is_prospect == True`) are appended to fill the gap — flagged in `notes`.

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


def compute(
    stock: pd.DataFrame,
    previous_meets: pd.DataFrame,
    team: pd.DataFrame,
) -> pd.DataFrame:
    """Return DataFrame: sm_tm, counter_id, counter_name, district, stock_mt, notes."""
    stock = stock.copy()
    stock["stock_mt"] = pd.to_numeric(stock["stock_mt"], errors="coerce").fillna(0.0)

    is_prospect = (
        stock["is_prospect"].fillna(False).astype(bool)
        if "is_prospect" in stock.columns
        else pd.Series(False, index=stock.index)
    )
    stock["is_prospect"] = is_prospect

    met_pairs = set(
        zip(
            previous_meets["sm_tm"].astype(str),
            previous_meets["counter_id"].astype(str),
        )
    )

    def _not_met_last_month(row: pd.Series) -> bool:
        return (str(row["sm_tm"]), str(row["counter_id"])) not in met_pairs

    stock["_not_met"] = stock.apply(_not_met_last_month, axis=1)

    rows: list[dict] = []
    for sm_tm in team["sm_tm"].unique():
        sm_stock = stock[stock["sm_tm"] == sm_tm]

        primary = sm_stock[
            (sm_stock["stock_mt"] > STOCK_THRESHOLD_MT)
            & sm_stock["_not_met"]
            & (~sm_stock["is_prospect"])
        ].sort_values("stock_mt", ascending=False)

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
            used_ids = set(primary["counter_id"].astype(str))
            prospects = sm_stock[
                sm_stock["is_prospect"]
                & sm_stock["_not_met"]
                & (~sm_stock["counter_id"].astype(str).isin(used_ids))
            ].sort_values("stock_mt", ascending=False)

            for _, r in prospects.iterrows():
                rows.append({
                    "sm_tm": sm_tm,
                    "counter_id": r["counter_id"],
                    "counter_name": r["counter_name"],
                    "district": r["district"],
                    "stock_mt": float(r["stock_mt"]),
                    "notes": "prospect counter - stock fallback",
                })

    return pd.DataFrame(rows, columns=[
        "sm_tm", "counter_id", "counter_name", "district", "stock_mt", "notes",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", action="store_true", help="Print per-SM/TM counts.")
    args = parser.parse_args()

    try:
        data = load_inputs.load_all()
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    result = compute(
        stock=data["stock"],
        previous_meets=data["previous_meets"],
        team=data["team_members"],
    )

    if args.print:
        counts = result.groupby("sm_tm").size().reset_index(name="eligible_count")
        print(counts.to_string(index=False))
        low = counts[counts["eligible_count"] < MIN_MASON_TARGET]
        if not low.empty:
            print(
                f"\nWARNING: {len(low)} SM/TM(s) have < {MIN_MASON_TARGET} "
                "eligible mason counters even after prospect fallback:",
                file=sys.stderr,
            )
            print(low.to_string(index=False), file=sys.stderr)
    else:
        print(f"Computed {len(result)} eligible mason rows across "
              f"{result['sm_tm'].nunique()} SM/TMs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
