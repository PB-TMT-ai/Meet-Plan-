"""Build the monthly meet plan XLSX for every SM/TM.

Pipeline:
  1. load_inputs.load_all()  ->  team, kam_dealer, district master, stock,
                                 previous_meets, zone_breakup
  2. eligible_mason_counters.compute()  ->  per-SM/TM eligible counter pool
  3. distribute_zone_slots.distribute()  ->  per-SM/TM dealer/architect/contractor counts
                                             from zone_breakup with rotation + caps
  4. compose -> Meet plan/<YYYY-MM>.xlsx

Hard rules enforced:
  - Each SM/TM gets >= MIN_OPTIONS (8) total rows
  - Contractor cap 2; Dealer + Architect cap 1 each; Dealer XOR Architect (never both)
  - Non-HP SM/TMs: contractor + architect dropped, mason backfills

Usage:
    python tools/build_meet_plan.py --month 2026-05
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distribute_zone_slots  # noqa: E402
import eligible_mason_counters  # noqa: E402
import load_inputs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "Meet plan"
MIN_OPTIONS = 8

OUTPUT_COLUMNS = [
    "zone", "sm_tm", "role", "state", "meet_type",
    "counter_id", "counter_name", "district", "stock_mt", "notes",
]

MONTH_NAME_TO_COL = {"04": "april", "05": "may", "06": "june"}


def _month_arg(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise argparse.ArgumentTypeError("--month must be YYYY-MM")
    return value


def _slot_row(zone: str, sm_tm: str, role: str, state: str, meet_type: str, notes: str = "") -> dict:
    return {
        "zone": zone, "sm_tm": sm_tm, "role": role, "state": state,
        "meet_type": meet_type,
        "counter_id": "", "counter_name": "", "district": "", "stock_mt": "",
        "notes": notes,
    }


def _hp_lookup(district: pd.DataFrame) -> tuple[set[str], dict[str, set[str]]]:
    hp = set(
        district.loc[district["category"].isin(distribute_zone_slots.HP_CATEGORIES), "district"]
        .astype(str).str.strip().str.upper()
    )
    smtm_districts: dict[str, set[str]] = {}
    for _, r in district.iterrows():
        d = str(r["district"]).strip().upper()
        if not d or d == "NAN":
            continue
        for col in ("sm", "tm"):
            v = r.get(col)
            if v and str(v).strip().lower() not in {"", "nan", "none"}:
                smtm_districts.setdefault(str(v).strip(), set()).add(d)
    return hp, smtm_districts


def build(month: str) -> tuple[Path, dict]:
    data = load_inputs.load_all()
    team           = data["team_members"]
    kam_dealer     = data["kam_dealer"]
    district       = data["high_potential_districts"]
    stock          = data["stock"]
    previous_meets = data["previous_meets"]
    zone_breakup   = data["zone_breakup"]

    eligible, attributed = eligible_mason_counters.compute(
        stock=stock, previous_meets=previous_meets, team=team,
        kam_dealer=kam_dealer, district=district,
    )

    month_col = MONTH_NAME_TO_COL.get(month.split("-")[1])
    if month_col is None:
        raise ValueError(
            f"month {month} not in zone_breakup columns ({list(MONTH_NAME_TO_COL.values())}). "
            "Add the column to inputs/zone_breakup/ if you need a different month."
        )

    alloc = distribute_zone_slots.distribute(
        team=team, district=district, previous_meets=previous_meets,
        zone_breakup=zone_breakup, month_col=month_col,
    )

    hp, smtm_districts = _hp_lookup(district)

    rows: list[dict] = []
    warnings: list[str] = []

    for _, t in team.iterrows():
        sm_tm = t["sm_tm"]
        zone, role, state = t["zone"], t["role"], t["state"]
        is_hp = bool(smtm_districts.get(sm_tm, set()) & hp)

        slots = alloc.get(sm_tm, {"dealer": 0, "architect": 0, "contractor": 0})
        dealer_n = slots["dealer"]
        architect_n = slots["architect"]
        contractor_n = slots["contractor"]

        if dealer_n and architect_n:
            raise ValueError(
                f"SM/TM '{sm_tm}' allocated both dealer and architect "
                "— distributor logic must enforce mutual exclusion."
            )

        if not is_hp:
            if contractor_n or architect_n:
                warnings.append(
                    f"SM/TM '{sm_tm}' (state={state}) covers no HP district — "
                    "contractor/architect slots dropped."
                )
            contractor_n = 0
            architect_n = 0

        non_mason_n = contractor_n + dealer_n + architect_n
        mason_target = max(MIN_OPTIONS - non_mason_n, 0)

        # mason rows
        mason_pool = eligible[eligible["sm_tm"] == sm_tm].head(mason_target)
        for _, m in mason_pool.iterrows():
            rows.append({
                "zone": zone, "sm_tm": sm_tm, "role": role, "state": state,
                "meet_type": "mason",
                "counter_id": m["counter_id"], "counter_name": m["counter_name"],
                "district": m["district"], "stock_mt": m["stock_mt"],
                "notes": m["notes"],
            })

        if len(mason_pool) < mason_target:
            short = mason_target - len(mason_pool)
            warnings.append(
                f"SM/TM '{sm_tm}' short {short} mason counter(s) — pool exhausted."
            )

        non_hp_note = "non-HP coverage — slot dropped, backfilled with mason" if not is_hp else ""
        if not is_hp and (slots["contractor"] or slots["architect"]) and rows and rows[-1]["sm_tm"] == sm_tm:
            existing = rows[-1]["notes"]
            rows[-1]["notes"] = non_hp_note if not existing else f"{existing}; {non_hp_note}"

        for _ in range(contractor_n):
            rows.append(_slot_row(zone, sm_tm, role, state, "contractor"))
        for _ in range(dealer_n):
            rows.append(_slot_row(zone, sm_tm, role, state, "dealer"))
        for _ in range(architect_n):
            rows.append(_slot_row(zone, sm_tm, role, state, "architect"))

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    df = df.sort_values(["zone", "sm_tm", "meet_type"]).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{month}.xlsx"
    df.to_excel(out_path, index=False, sheet_name="Meet Plan")

    audit_info = {
        "warnings": warnings,
        "row_total": len(df),
        "sm_tm_total": df["sm_tm"].nunique(),
        "roster": team["sm_tm"].tolist(),
        "rows_per_sm_tm": df.groupby("sm_tm").size().to_dict(),
        "unassigned_counters_in_pool": int((attributed["sm_tm"] == eligible_mason_counters.UNASSIGNED).sum()),
        "unmapped_kam_names": data.get("_unmapped_kam_names", []),
        "alloc_audit": distribute_zone_slots.audit(alloc, team),
    }
    return out_path, audit_info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--month", type=_month_arg,
        default=date.today().strftime("%Y-%m"),
        help="Target month YYYY-MM (default: current month).",
    )
    args = parser.parse_args()

    try:
        out_path, info = build(args.month)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for w in info["warnings"][:20]:
        print(f"WARN: {w}", file=sys.stderr)
    if len(info["warnings"]) > 20:
        print(f"... ({len(info['warnings']) - 20} more warnings)", file=sys.stderr)

    # roster SM/TMs entirely missing from the plan (0 rows)
    missing = sorted(set(info["roster"]) - set(info["rows_per_sm_tm"]))
    if missing:
        print(
            f"WARN: {len(missing)} SM/TM(s) MISSING from the plan (0 rows):",
            file=sys.stderr,
        )
        for s in missing:
            print(f"  - {s}", file=sys.stderr)

    short = {s: n for s, n in info["rows_per_sm_tm"].items() if n < MIN_OPTIONS}
    if short:
        print(
            f"WARN: {len(short)} SM/TM(s) have < {MIN_OPTIONS} rows in the plan:",
            file=sys.stderr,
        )
        for s, n in sorted(short.items(), key=lambda kv: kv[1]):
            print(f"  - {s}: {n}", file=sys.stderr)

    print(f"Wrote {out_path.relative_to(REPO_ROOT)}  "
          f"(rows={info['row_total']}, sm_tms={info['sm_tm_total']}, "
          f"unassigned_pool={info['unassigned_counters_in_pool']}, "
          f"unmapped_kams={len(info['unmapped_kam_names'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
