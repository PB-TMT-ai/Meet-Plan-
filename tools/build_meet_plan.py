"""Build the monthly meet plan XLSX for every SM/TM.

Applies the split rules from workflows/monthly_meet_plan.md:
- Mason: takes remaining slots to reach MIN_OPTIONS (default 8).
- Contractor: capped at 2, only if SM/TM's district is high-potential.
- Dealer: slot-only (no district filter).
- Architect/Engineer: slot-only, only if SM/TM's district is high-potential.
- Dealer XOR Architect for a given SM/TM (hard-fail if both > 0).

Usage:
    python tools/build_meet_plan.py --month 2026-04
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eligible_mason_counters  # noqa: E402
import load_inputs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "Meet plan"
MIN_OPTIONS = 8
CONTRACTOR_CAP = 2
DEFAULT_SPLIT = {"mason": 6, "contractor": 1, "dealer": 1, "architect": 0}

OUTPUT_COLUMNS = [
    "zone", "sm_tm", "district", "meet_type",
    "counter_id", "counter_name", "stock_mt", "notes",
]


def _month_arg(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise argparse.ArgumentTypeError("--month must be YYYY-MM")
    return value


def _breakup_for(sm_tm: str, breakup: pd.DataFrame, warnings: list[str]) -> dict[str, int]:
    row = breakup[breakup["sm_tm"] == sm_tm]
    if row.empty:
        warnings.append(f"zone_breakup has no row for SM/TM '{sm_tm}' — using default split")
        return dict(DEFAULT_SPLIT)
    row = row.iloc[0]
    return {
        key: int(row[key]) if key in row.index and pd.notna(row[key]) else DEFAULT_SPLIT[key]
        for key in DEFAULT_SPLIT
    }


def _build_for_sm(
    sm_tm: str,
    team_row: pd.Series,
    split: dict[str, int],
    mason_pool: pd.DataFrame,
    is_high_potential: bool,
    warnings: list[str],
) -> list[dict]:
    zone = team_row["zone"]
    district = team_row["district"]

    if split["dealer"] > 0 and split["architect"] > 0:
        raise ValueError(
            f"SM/TM '{sm_tm}' has both dealer={split['dealer']} and "
            f"architect={split['architect']} in zone_breakup — only one is allowed per month."
        )

    contractor_n = min(split["contractor"], CONTRACTOR_CAP)
    architect_n = split["architect"]
    dealer_n = split["dealer"]
    mason_target = split["mason"]

    if not is_high_potential:
        if contractor_n or architect_n:
            warnings.append(
                f"SM/TM '{sm_tm}' district '{district}' is not high-potential — "
                f"dropping contractor/architect slots and backfilling with mason."
            )
        contractor_n = 0
        architect_n = 0

    total = mason_target + contractor_n + dealer_n + architect_n
    if total < MIN_OPTIONS:
        mason_target += MIN_OPTIONS - total

    rows: list[dict] = []

    mason_rows = mason_pool[mason_pool["sm_tm"] == sm_tm].head(mason_target)
    for _, m in mason_rows.iterrows():
        rows.append({
            "zone": zone,
            "sm_tm": sm_tm,
            "district": m["district"],
            "meet_type": "mason",
            "counter_id": m["counter_id"],
            "counter_name": m["counter_name"],
            "stock_mt": m["stock_mt"],
            "notes": m["notes"],
        })

    if len(mason_rows) < mason_target:
        short = mason_target - len(mason_rows)
        warnings.append(
            f"SM/TM '{sm_tm}' short {short} mason counter(s) even after prospect fallback."
        )

    non_hp_note = "non-HP district — slot dropped, backfilled with mason" if not is_high_potential else ""

    for _ in range(contractor_n):
        rows.append(_slot_row(zone, sm_tm, district, "contractor", ""))
    for _ in range(dealer_n):
        rows.append(_slot_row(zone, sm_tm, district, "dealer", ""))
    for _ in range(architect_n):
        rows.append(_slot_row(zone, sm_tm, district, "architect", ""))

    if not is_high_potential and (split["contractor"] or split["architect"]):
        # leave a single audit note on the first mason row (or append if no mason rows)
        if rows and rows[0]["meet_type"] == "mason":
            existing = rows[0]["notes"]
            rows[0]["notes"] = non_hp_note if not existing else f"{existing}; {non_hp_note}"

    return rows


def _slot_row(zone: str, sm_tm: str, district: str, meet_type: str, notes: str) -> dict:
    return {
        "zone": zone,
        "sm_tm": sm_tm,
        "district": district,
        "meet_type": meet_type,
        "counter_id": "",
        "counter_name": "",
        "stock_mt": "",
        "notes": notes,
    }


def build(month: str) -> Path:
    data = load_inputs.load_all()
    team = data["team_members"]
    breakup = data["zone_breakup"]
    hp_districts = set(data["high_potential_districts"]["district"].astype(str))

    mason_pool = eligible_mason_counters.compute(
        stock=data["stock"],
        previous_meets=data["previous_meets"],
        team=team,
    )

    warnings: list[str] = []
    all_rows: list[dict] = []

    for _, team_row in team.iterrows():
        sm_tm = team_row["sm_tm"]
        split = _breakup_for(sm_tm, breakup, warnings)
        is_hp = str(team_row["district"]) in hp_districts
        all_rows.extend(_build_for_sm(sm_tm, team_row, split, mason_pool, is_hp, warnings))

    df = pd.DataFrame(all_rows, columns=OUTPUT_COLUMNS)
    df = df.sort_values(["zone", "sm_tm", "meet_type"]).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{month}.xlsx"
    df.to_excel(out_path, index=False, sheet_name="Meet Plan")

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    short_counts = (
        df.groupby("sm_tm").size().reset_index(name="n").query("n < @MIN_OPTIONS")
    )
    if not short_counts.empty:
        print(
            f"WARN: {len(short_counts)} SM/TM(s) have < {MIN_OPTIONS} rows in the plan:",
            file=sys.stderr,
        )
        print(short_counts.to_string(index=False), file=sys.stderr)

    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--month", type=_month_arg,
        default=date.today().strftime("%Y-%m"),
        help="Target month as YYYY-MM (default: current month).",
    )
    args = parser.parse_args()

    try:
        out_path = build(args.month)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
