"""Load and validate every monthly input sheet under `inputs/<category>/`.

Each subfolder holds one DataFrame's worth of data (XLSX or CSV). The most recently
modified file in each folder is the one used — old files can stay as history.

Usage:
    python tools/load_inputs.py --print-summary
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUTS_DIR = REPO_ROOT / "inputs"

# folder -> (required columns, optional columns)
EXPECTED_INPUTS: dict[str, tuple[list[str], list[str]]] = {
    "team_members": (["sm_tm", "zone", "district"], []),
    "zone_breakup": (
        ["zone", "sm_tm"],
        ["mason", "contractor", "dealer", "architect"],
    ),
    "stock": (
        ["counter_id", "counter_name", "district", "sm_tm", "stock_mt"],
        ["is_prospect"],
    ),
    "previous_meets": (["sm_tm", "counter_id"], []),
    "high_potential_districts": (["district"], []),
}

SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".csv"}


def _normalize_col(name: str) -> str:
    """Lowercase, strip, collapse runs of non-alphanumerics into a single underscore."""
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip().lower())
    return slug.strip("_")


def _latest_file(folder: Path) -> Path:
    candidates = [
        p for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_SUFFIXES
        and not p.name.startswith(".")
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No XLSX/CSV files in {folder.relative_to(REPO_ROOT)}/ — "
            f"drop the month's file there."
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)
    df.columns = [_normalize_col(c) for c in df.columns]
    return df


def _validate(name: str, df: pd.DataFrame, required: list[str], path: Path) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path.relative_to(REPO_ROOT)} is missing required columns for "
            f"'{name}': {missing}. Found columns: {list(df.columns)}"
        )


def load_all() -> dict[str, pd.DataFrame]:
    """Load every expected input folder into a DataFrame. Raises on validation errors."""
    if not INPUTS_DIR.exists():
        raise FileNotFoundError(f"{INPUTS_DIR} does not exist — create the inputs/ folder first.")

    out: dict[str, pd.DataFrame] = {}
    for name, (required, _optional) in EXPECTED_INPUTS.items():
        folder = INPUTS_DIR / name
        if not folder.exists():
            raise FileNotFoundError(
                f"inputs/{name}/ does not exist — create the folder and drop the file."
            )
        path = _latest_file(folder)
        df = _read_table(path)
        _validate(name, df, required, path)
        out[name] = df
    return out


def _print_summary(data: dict[str, pd.DataFrame]) -> None:
    for name, df in data.items():
        print(f"[{name}] rows={len(df)} cols={list(df.columns)}")
        if not df.empty:
            print(df.head(3).to_string(index=False))
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-summary", action="store_true",
        help="Print row counts and the first 3 rows of each input.",
    )
    args = parser.parse_args()

    try:
        data = load_all()
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.print_summary:
        _print_summary(data)
    else:
        print(f"Loaded {len(data)} inputs: {list(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
