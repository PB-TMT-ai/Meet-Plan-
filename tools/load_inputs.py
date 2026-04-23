"""Load and normalize every monthly input sheet under `inputs/<category>/`.

Each subfolder holds the raw XLSX/CSV the user dropped in. This loader reads each,
maps the real column names to canonical names, applies SM/TM name aliasing where
relevant, and returns a dict of pandas DataFrames keyed by category.

Canonical schemas (after this loader):
- team_members:            sm_tm, role, zone, state
- high_potential_districts: district, state, zone, category, sm, tm  (full District master)
- kam_dealer:              counter_id, sm_tm  (sm_tm aliased to roster names)
- stock:                   counter_id, counter_name, district, zone, distributor, stock_mt
- previous_meets:          sm_tm, counter_id, meet_type, meet_date  (sm_tm aliased)
- zone_breakup:            zone, meet_type, april, may, june  (wide form)

Usage:
    python tools/load_inputs.py --print-summary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalize_names

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUTS_DIR = REPO_ROOT / "inputs"

SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".csv"}

# Map an input folder to the substring(s) used to identify its file (case-insensitive).
# Required because team_members/ now holds two distinct files (Headcount + Dealer SMTM).
FOLDER_TO_FILE_HINTS: dict[str, dict[str, list[str]]] = {
    "team_members": {
        "team_members": ["headcount"],
        "kam_dealer":   ["dealer", "smtm", "kam"],
    },
    "high_potential_districts": {
        "high_potential_districts": ["district"],
    },
    "stock": {
        "stock": ["stock"],
    },
    "previous_meets": {
        "previous_meets": ["meet"],
    },
    "zone_breakup": {
        "zone_breakup": ["zone", "break"],
    },
}


def _list_files(folder: Path) -> list[Path]:
    return [
        p for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_SUFFIXES
        and not p.name.startswith(".")
    ]


def _pick_file(folder: Path, hints: list[str]) -> Path:
    name_l = lambda p: p.name.lower()
    matches = [p for p in _list_files(folder) if all(h in name_l(p) for h in hints)]
    if not matches:
        # fallback: any hint matches
        matches = [p for p in _list_files(folder) if any(h in name_l(p) for h in hints)]
    if not matches:
        raise FileNotFoundError(
            f"No files matching hints {hints} in {folder.relative_to(REPO_ROOT)}/"
        )
    return max(matches, key=lambda p: p.stat().st_mtime)


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _load_team_members(path: Path) -> pd.DataFrame:
    df = _read(path)
    # Headcount.xlsx columns: Zone, SM/TM, SM/TM.1, Email IDs, State
    out = pd.DataFrame({
        "sm_tm": df["SM/TM.1"].astype(str).str.strip(),
        "role":  df["SM/TM"].astype(str).str.strip(),
        "zone":  df["Zone"].astype(str).str.strip(),
        "state": df["State"].astype(str).str.strip(),
    })
    return out[out["sm_tm"].astype(bool) & (out["sm_tm"].str.lower() != "nan")].reset_index(drop=True)


def _load_kam_dealer(path: Path, roster: list[str]) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    df = _read(path)
    # columns: Dealer SF ID, SM / TM
    raw = pd.DataFrame({
        "counter_id": df["Dealer SF ID"].astype(str).str.strip(),
        "raw_sm_tm":  df["SM / TM"].astype(str).str.strip(),
    })
    raw = raw[raw["counter_id"].astype(bool) & (raw["counter_id"].str.lower() != "nan")]
    raw = raw[~raw["raw_sm_tm"].apply(normalize_names.is_junk)]

    candidates = sorted(raw["raw_sm_tm"].unique().tolist())
    alias_map = normalize_names.build_alias_map(roster, candidates)
    raw["sm_tm"] = raw["raw_sm_tm"].map(alias_map)
    unmapped = sorted(raw.loc[raw["sm_tm"].isna(), "raw_sm_tm"].unique().tolist())

    out = raw.loc[raw["sm_tm"].notna(), ["counter_id", "sm_tm"]].drop_duplicates().reset_index(drop=True)
    return out, alias_map, unmapped


def _load_district(path: Path) -> pd.DataFrame:
    df = _read(path)
    # District .xlsx columns include: District, State, Zone, Distributor,
    # Categorization of District, SM, TM
    out = pd.DataFrame({
        "district": df["District"].astype(str).str.strip(),
        "state":    df["State"].astype(str).str.strip(),
        "zone":     df["Zone"].astype(str).str.strip(),
        "category": df["Categorization of District"].astype(str).str.strip(),
        "sm":       df["SM"].astype(str).str.strip().where(df["SM"].notna(), None),
        "tm":       df["TM"].astype(str).str.strip().where(df["TM"].notna(), None),
    })
    return out[out["district"].astype(bool) & (out["district"].str.lower() != "nan")].reset_index(drop=True)


def _load_stock(path: Path) -> pd.DataFrame:
    df = _read(path)
    # Stock.xlsx columns: Sr. No., Account Sf ID, Name of the Dealer, State,
    # District, Distributor Name, Zone, Retailer Current Stock As Per SF
    out = pd.DataFrame({
        "counter_id":   df["Account Sf ID"].astype(str).str.strip(),
        "counter_name": df["Name of the Dealer"].astype(str).str.strip(),
        "district":     df["District"].astype(str).str.strip(),
        "zone":         df["Zone"].astype(str).str.strip(),
        "distributor":  df["Distributor Name"].astype(str).str.strip(),
        "stock_mt":     pd.to_numeric(df["Retailer Current Stock As Per SF"], errors="coerce").fillna(0.0),
    })
    return out[out["counter_id"].astype(bool) & (out["counter_id"].str.lower() != "nan")].reset_index(drop=True)


def _normalize_meet_type(raw: str) -> str:
    """Map noisy meet-type strings to canonical {mason, contractor, dealer, architect}."""
    s = str(raw).strip().lower()
    if "mason" in s or "masson" in s:
        return "mason"
    if "contractor" in s:
        return "contractor"
    if "dealer" in s:
        return "dealer"
    if "architect" in s or "engineer" in s:
        return "architect"
    return ""


def _load_previous_meets(path: Path, roster: list[str]) -> pd.DataFrame:
    df = _read(path)
    actual = df["Actual Meet Type"].fillna(df["Meet Type"])
    raw = pd.DataFrame({
        "raw_sm_tm": df["Responsible SM/TM/KAM"].astype(str).str.strip(),
        "counter_id": df["Account Sf ID"].astype(str).str.strip(),
        "meet_type": actual.apply(_normalize_meet_type),
        "meet_date": pd.to_datetime(df["Actual Meet Date"], errors="coerce"),
    })
    raw = raw[raw["counter_id"].astype(bool) & raw["meet_type"].astype(bool)]
    candidates = sorted(raw["raw_sm_tm"].unique().tolist())
    alias_map = normalize_names.build_alias_map(roster, candidates)
    raw["sm_tm"] = raw["raw_sm_tm"].map(alias_map).fillna(raw["raw_sm_tm"])
    return raw[["sm_tm", "counter_id", "meet_type", "meet_date"]].reset_index(drop=True)


MEET_TYPE_LABEL_TO_CANONICAL = {
    "mason meet": "mason",
    "masson meet": "mason",
    "contractor meet": "contractor",
    "dealer meet": "dealer",
    "architect meet": "architect",
    "engineer meet": "architect",  # interchangeable with architect per SOP
}


def _load_zone_breakup(path: Path) -> pd.DataFrame:
    """Parse the long-format breakup sheet into one row per (zone, meet_type)."""
    df = _read(path)
    rows = []
    for _, r in df.iterrows():
        zone = str(r.get("Zone", "")).strip()
        mt_raw = str(r.get("Meet Type", "")).strip().lower()
        if not zone or not mt_raw or zone.lower().endswith("total") or "summary" in zone.lower():
            continue
        canonical = MEET_TYPE_LABEL_TO_CANONICAL.get(mt_raw)
        if not canonical:
            continue
        rows.append({
            "zone": zone,
            "meet_type": canonical,
            "april": int(pd.to_numeric(r.get("April"), errors="coerce") or 0),
            "may":   int(pd.to_numeric(r.get("May"),   errors="coerce") or 0),
            "june":  int(pd.to_numeric(r.get("June"),  errors="coerce") or 0),
        })
    long = pd.DataFrame(rows)
    # collapse duplicates (architect + engineer both map to "architect")
    return long.groupby(["zone", "meet_type"], as_index=False).sum()


def load_all() -> dict[str, object]:
    """Load every input. Returns dataframes plus aliasing audit info."""
    if not INPUTS_DIR.exists():
        raise FileNotFoundError(f"{INPUTS_DIR} does not exist.")

    team_path     = _pick_file(INPUTS_DIR / "team_members",            FOLDER_TO_FILE_HINTS["team_members"]["team_members"])
    kam_path      = _pick_file(INPUTS_DIR / "team_members",            FOLDER_TO_FILE_HINTS["team_members"]["kam_dealer"])
    district_path = _pick_file(INPUTS_DIR / "high_potential_districts", FOLDER_TO_FILE_HINTS["high_potential_districts"]["high_potential_districts"])
    stock_path    = _pick_file(INPUTS_DIR / "stock",                    FOLDER_TO_FILE_HINTS["stock"]["stock"])
    prev_path     = _pick_file(INPUTS_DIR / "previous_meets",           FOLDER_TO_FILE_HINTS["previous_meets"]["previous_meets"])
    breakup_path  = _pick_file(INPUTS_DIR / "zone_breakup",             FOLDER_TO_FILE_HINTS["zone_breakup"]["zone_breakup"])

    team = _load_team_members(team_path)
    roster = team["sm_tm"].tolist()
    kam_dealer, kam_alias_map, unmapped_kam = _load_kam_dealer(kam_path, roster)
    district = _load_district(district_path)
    stock = _load_stock(stock_path)
    previous_meets = _load_previous_meets(prev_path, roster)
    zone_breakup = _load_zone_breakup(breakup_path)

    return {
        "team_members": team,
        "kam_dealer": kam_dealer,
        "high_potential_districts": district,
        "stock": stock,
        "previous_meets": previous_meets,
        "zone_breakup": zone_breakup,
        # audit info
        "_kam_alias_map": kam_alias_map,
        "_unmapped_kam_names": unmapped_kam,
    }


def _print_summary(data: dict) -> None:
    for name in ["team_members", "kam_dealer", "high_potential_districts",
                 "stock", "previous_meets", "zone_breakup"]:
        df = data[name]
        print(f"[{name}] rows={len(df)} cols={list(df.columns)}")
        if not df.empty:
            print(df.head(3).to_string(index=False))
        print()
    print(f"Aliases applied (kam_dealer): {sum(1 for k, v in data['_kam_alias_map'].items() if k != v)}")
    print(f"KAM/junk names with no roster match: {len(data['_unmapped_kam_names'])}")
    if data["_unmapped_kam_names"]:
        for n in data["_unmapped_kam_names"][:10]:
            print(f"  - {n}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    try:
        data = load_all()
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.print_summary:
        _print_summary(data)
    else:
        print("Loaded:", [k for k in data if not k.startswith("_")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
