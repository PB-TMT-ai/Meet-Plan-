# Memories — Durable Project Facts

Stable facts about the Meet Plan pipeline. Update when they actually change — don't treat
as a changelog.

## Team universe

- **52 SM/TMs** total, split across three zones:
  - North: 32
  - Central: 10
  - East: 10
- Source of truth: `inputs/team_members/Headcount.xlsx`, column `SM/TM.1` is the name,
  `SM/TM` is the role (SM or TM), `State` is their assigned state.
- Some Headcount names are short (e.g. `Paritosh`, `Debjyoti`, `Punit`) while the KAM-Dealer
  mapping has the full name (e.g. `Paritosh Kaushik`). `tools/normalize_names.py` handles
  the aliasing via strict subset-token matching (one name's tokens must be a subset of the
  other).

## Zones

Three zones only: **North**, **East**, **Central**. West/South are out of scope.

## Meet types and caps

| Type | Cap / SM/TM | District filter |
| --- | --- | --- |
| Mason | fills to ≥ 8 | none (own district pool + state-wide prospect fallback) |
| Contractor | 2 | SM/TM must cover ≥ 1 HP district |
| Dealer | 1 | none |
| Architect / Engineer (one bucket) | 1 | SM/TM must cover ≥ 1 HP district |

**Hard rule**: Dealer and Architect are mutually exclusive for a given SM/TM in a given
month. `build_meet_plan.py` raises if the allocator violates this.

## Thresholds and defaults

- **Stock threshold**: `stock_mt > 10` for primary mason eligibility. Values are in MT.
- **Prospect fallback tier 1**: own counters with `stock_mt ≤ 10` not met last month.
- **Prospect fallback tier 2**: any counter in the SM/TM's state (for SM/TMs with no own
  counters or exhausted tier 1 pool).
- **MIN_MASON_TARGET**: 6 (used inside `eligible_mason_counters.py` to decide when to start
  prospect fallback).
- **MIN_OPTIONS per plan row count**: 8 (hard rule in `build_meet_plan.py`).
- **Contractor cap**: 2.
- **HP district categories**: `Very High` + `High` (from `Categorization of District`
  column in `inputs/high_potential_districts/District .xlsx`). `Medium` and `Low` are NOT
  HP.

## Monthly split pattern

Zone breakup arrives as **zone × meet_type** totals per month (not per-SM/TM). The
distributor (`tools/distribute_zone_slots.py`) spreads those totals across SM/TMs:

- Dealer slots → SM/TMs who did NOT do dealer last month first (rotation).
- Architect/Engineer → HP-district SM/TMs only, preferring those who DID dealer last month.
  Excludes anyone who got a dealer slot this month (mutual exclusion).
- Contractor → equal-as-possible across HP SM/TMs, capped at 2.
- Mason → not allocated here; fills each plan to ≥ 8 downstream.

## Counter ownership cascade

Every stock counter is attributed to an owner via:

1. `inputs/team_members/Dealer SMTM breakup.xlsx` (`Dealer SF ID` → `SM / TM`), aliased
   to the Headcount roster.
2. `inputs/high_potential_districts/District .xlsx` `TM` column for the counter's district.
3. Same file's `SM` column.
4. Otherwise: `UNASSIGNED` (stays in pool, available as state-wide prospect).

## Input file schemas (real column names)

| Folder | File | Key columns |
| --- | --- | --- |
| `team_members/` | `Headcount.xlsx` | `Zone`, `SM/TM`, `SM/TM.1`, `State` |
| `team_members/` | `Dealer SMTM breakup.xlsx` | `Dealer SF ID`, `SM / TM` |
| `high_potential_districts/` | `District .xlsx` | `District`, `State`, `Zone`, `Categorization of District`, `SM`, `TM`, `Distributor` |
| `stock/` | `Stock.xlsx` | `Account Sf ID`, `Name of the Dealer`, `District`, `Zone`, `Distributor Name`, `Retailer Current Stock As Per SF` |
| `previous_meets/` | `Previous Month Meet Plan.xlsx` | `Account Sf ID`, `Responsible SM/TM/KAM`, `Meet Type`, `Actual Meet Type`, `Actual Meet Date` |
| `zone_breakup/` | `Zone wise break up.xlsx` | `Zone`, `Meet Type`, `April`, `May`, `June`, `Total` — **long format**, one row per (zone, meet_type). |

## Meet type string normalizations

Previous-meets sheets have dirty data. Canonical mappings (handled in
`load_inputs._normalize_meet_type`):

- `Mason Meet`, `Masson Meet`, `mason meet` → `mason`
- `Contractor Meet` → `contractor`
- `Dealer Meet` → `dealer`
- `Architect Meet`, `Engineer Meet`, `Engineer meet` → `architect` (one bucket)

## Confirmed name aliases

These are one-to-one mappings the subset-token matcher resolves automatically. Listed here
for documentation / audit:

| Headcount | KAM-Dealer file |
| --- | --- |
| Paritosh | Paritosh Kaushik |
| Debjyoti | Debjyoti Lahiri |
| Punit | Punit Kumar |
| BIDYUT MISHRA | Bidyut Ranjan Mishra |
| Rahul Kumar Gautam | Rahul Gautam |
| Sudhir Kumar Garg | Sudhir Garg |
| Shiv Kumar Sharma | SHIV KUMAR |
| Shirshendu Saha | Shirshendu saha (case) |
| Bhanu Ayush | bhanu ayush (case) |
| Aman Kumar | Aman kumar (case) |
| DHARMENDRA KUMAR YADAV | Dharmendra Kumar Yadav (case) |

## Data gaps to work around

- `Stock.xlsx` has **zero rows for Himachal Pradesh and Chhattisgarh**, and only 1 for
  Maharashtra. SM/TMs in those states can't be fully planned without new stock data.
- ~20 names in `Dealer SMTM breakup.xlsx` aren't in Headcount (likely KAMs). Their
  counters fall through to the district-owner step of the cascade.

## Output layout

`Meet plan/<YYYY-MM>.xlsx`, one sheet `Meet Plan`, columns:

```
zone, sm_tm, role, state, meet_type,
counter_id, counter_name, district, stock_mt, notes
```

Mason rows are fully populated. Contractor / Dealer / Architect rows are slot-only —
the SM/TM fills in names locally. `notes` flags prospect fallback and non-HP drops.
