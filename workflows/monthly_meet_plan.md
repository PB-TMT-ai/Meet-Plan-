# Monthly Meet Plan

## Objective

Produce a monthly meet plan for every SM/TM/KAM across **North**, **East**, and **Central**
zones. Each plan should contain **at least 8 meet options** (5 to be executed) across four
meet types, respecting per-type caps and zone-level monthly targets.

Output: `Meet plan/<YYYY-MM>.xlsx` — one row per SM/TM per meet option.

## Meet types and rules

| Type | Filter | Cap per SM/TM |
| --- | --- | --- |
| **Mason** | Counter stock > 10 MT AND counter not had a mason meet last month. Prospect fallback when short. | Fills to ≥ 8. |
| **Contractor** | SM/TM covers at least one HP district (Very High + High). | 2 |
| **Dealer** | No district filter. | 1 |
| **Architect / Engineer** (one bucket) | SM/TM covers at least one HP district. | 1 |

Hard rules:
- **Dealer XOR Architect** for the same SM/TM in a month — `build_meet_plan.py` raises if violated.
- Dealer slot rotation: SM/TMs who did NOT do a dealer meet last month are prioritized for this month's dealer slots; those who DID dealer last month are prioritized for architect/engineer.

## Inputs

Drop the latest files into the matching subfolders. The loader picks the most recent file per
folder by mtime and tolerates spaces / case in column names.

| Folder | Expected file | Real columns used |
| --- | --- | --- |
| `inputs/team_members/` | `Headcount.xlsx` (52 SM/TM roster) | `Zone`, `SM/TM`, `SM/TM.1` (name), `State` |
| `inputs/team_members/` | `Dealer SMTM breakup.xlsx` (counter→SM/TM mapping) | `Dealer SF ID`, `SM / TM` |
| `inputs/high_potential_districts/` | `District .xlsx` (district master) | `District`, `State`, `Zone`, `Categorization of District`, `SM`, `TM` |
| `inputs/stock/` | `Stock.xlsx` | `Account Sf ID`, `Name of the Dealer`, `District`, `Zone`, `Distributor Name`, `Retailer Current Stock As Per SF` |
| `inputs/previous_meets/` | `Previous Month Meet Plan.xlsx` | `Account Sf ID`, `Responsible SM/TM/KAM`, `Meet Type`, `Actual Meet Type`, `Actual Meet Date` |
| `inputs/zone_breakup/` | `Zone wise break up.xlsx` (long format) | `Zone`, `Meet Type`, `April`, `May`, `June` |

## Tools (run order)

```
python tools/load_inputs.py --print-summary
python tools/eligible_mason_counters.py --print
python tools/build_meet_plan.py --month YYYY-MM
```

- **`load_inputs.py`** — reads + normalizes every input. Maps real column names to canonical
  schemas (`sm_tm`, `counter_id`, `stock_mt`, etc). Applies SM/TM name aliasing (`Paritosh` ↔
  `Paritosh Kaushik`, `Rahul Kumar Gautam` ↔ `Rahul Gautam`, etc) via subset-token matching.
  Pivots `Zone wise break up` from long to wide. Combines Architect + Engineer meet types.
- **`normalize_names.py`** — strict subset-token name matcher used by `load_inputs.py`.
- **`eligible_mason_counters.py`** — per SM/TM, returns mason-eligible counters with a 2-tier
  prospect fallback:
    1. Primary: own counters with stock > 10 MT, not met last month.
    2. Tier 1 fallback: own counters with stock ≤ 10 MT.
    3. Tier 2 fallback: any counter in the same state (for SM/TMs with no own counters).
- **`distribute_zone_slots.py`** — distributes zone-level monthly targets across SM/TMs in
  the zone with rotation (Dealer↔Architect) and caps (Contractor ≤ 2, Dealer/Architect ≤ 1,
  never both).
- **`build_meet_plan.py`** — orchestrator. Composes the per-SM/TM plan, drops contractor/
  architect for non-HP SM/TMs (mason backfills to reach 8), writes
  `Meet plan/<YYYY-MM>.xlsx`.

## Counter ownership cascade

Each stock counter is attributed to an SM/TM via:
1. **KAM-Dealer mapping** (`Dealer SMTM breakup.xlsx`) → matched against Headcount roster
   using subset-token aliases.
2. **District file's TM column** — when KAM mapping has no roster match.
3. **District file's SM column** — when district has no TM.
4. Otherwise: `UNASSIGNED` (still kept in pool, available as state-wide prospect).

## Outputs

`Meet plan/<YYYY-MM>.xlsx` columns:
`zone, sm_tm, role, state, meet_type, counter_id, counter_name, district, stock_mt, notes`.

Mason rows have counter details. Contractor / Dealer / Architect rows are slot-only — name
left blank for the SM/TM to fill in the field. `notes` flags prospect-fallback rows and
non-HP slot drops.

## Edge cases / known gaps

- **State has no stock data** → SM/TMs in that state get 0 mason rows and appear in the
  `MISSING from the plan` warning. As of 2026-04, this affects Himachal Pradesh and
  Chhattisgarh (and Maharashtra has only 1 counter). To fix: add stock rows for those states.
- **HP-district SM/TM pool exhausted by dealer assignment** → architect target may underrun.
  Emitted in stderr alloc audit.
- **Names mismatched between Headcount and KAM-Dealer mapping** → `_unmapped_kam_names`
  audit lists names treated as KAMs (counters owned by them fall back to district lookup).

## Verification

1. Every SM/TM has at least 8 rows (warnings list any shortfalls).
2. No SM/TM has both a dealer and an architect row.
3. No SM/TM has more than 2 contractor rows.
4. No mason `counter_id` appears in this month's plan AND in last month's mason meets.
5. Prospect-fallback rows carry a `notes` flag.
6. `MISSING from the plan` SM/TMs need manual review (state-level stock gap).
