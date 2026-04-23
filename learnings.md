# Learnings — What We Discovered the Hard Way

Append new findings as you discover them. Each entry should state the problem, root cause,
and fix so we don't rediscover it next session.

## 2026-04 — First real build (May 2026 plan)

### Inputs don't match the SOP's assumed column names

**Expected** (v1 loader): canonical names like `sm_tm`, `counter_id`, `stock_mt`.

**Actual**: `SM/TM.1`, `Account Sf ID`, `Retailer Current Stock As Per SF`, etc. Also,
two distinct files share the `team_members/` folder (Headcount roster and KAM-Dealer
mapping).

**Fix**: `tools/load_inputs.py` now maps real columns to canonical names. Folder → file
disambiguation is done by filename substring hints (`FOLDER_TO_FILE_HINTS`).

**Avoid next time**: when a user says "data is in folder X", inspect the file before
rewriting logic. Multiple files per folder is common.

### Zone breakup is long format, not per-SM/TM

**Expected**: one row per SM/TM with columns `mason, contractor, dealer, architect`.

**Actual**: one row per `(zone, Meet Type)` with month columns `April, May, June, Total`,
plus summary rows like "North Total" and "MEET-WISE × ZONE-WISE SUMMARY".

**Fix**: `load_inputs._load_zone_breakup` pivots the long sheet, drops total/summary rows
(checks for `.endswith("total")` and `"summary"` in zone column), and collapses Architect
+ Engineer meet types into one `architect` bucket.

### Stock sheet has no SM/TM column

**Expected**: every counter carries a `sm_tm` column.

**Actual**: stock only has `District` + `Zone`. Ownership must be derived.

**Fix**: three-step ownership cascade in `eligible_mason_counters.compute`:
1. `Dealer SMTM breakup.xlsx` → roster name (via subset-token aliasing).
2. District master's `TM` column.
3. District master's `SM` column.
Otherwise `UNASSIGNED`. After the cascade only ~2 counters stay Unassigned (from 174
originally missing from the direct mapping).

### Name matching needs subset-token fuzzy matching, not exact match

**Symptom**: 29 names in the KAM-Dealer file didn't match Headcount on first try.

**Reality**: same person, different spelling — `Paritosh` vs `Paritosh Kaushik`,
`Rahul Kumar Gautam` vs `Rahul Gautam`, `BIDYUT MISHRA` vs `Bidyut Ranjan Mishra`.

**Wrong first attempt**: ranking by token-overlap count caused false positives like
`Amit Shukla` → `Amit Behera` (shared "Amit") and `Vishal Sharma` → `Amit Kumar Sharma`
(shared "Sharma").

**Right fix** in `tools/normalize_names.py`: a match requires one name's tokens to be a
**subset** of the other's. Plus exact (case-insensitive) match wins ambiguity
(resolves `Ravi Kumar` / `Ravi Kumar Kulmi`).

### Prospect fallback has to be multi-tier

**Wrong v1**: single tier — either own low-stock counters or state-wide Unassigned. If
own pool returned 1 row and state-wide was empty, the SM/TM plan stayed at 1 row.

**Fix**: chained fallbacks with an explicit `target_extra = MIN_MASON_TARGET + 4 - primary`.
Tier 1 (own low-stock) runs until exhausted or target hit; tier 2 (state-wide any owner)
kicks in if tier 1 didn't cover.

**Still open**: a few SM/TMs end up with < 8 rows when their state has almost no stock
(Maharashtra has 1 counter; Himachal Pradesh and Chhattisgarh have zero).

### `apply(..., axis=1)` on possibly-empty DataFrame drops columns

**Symptom**: `KeyError: 'stock_mt'` from `primary.sort_values("stock_mt")` after a filter.

**Cause**: `primary[~primary.apply(lambda r: ..., axis=1)]` returned an empty frame whose
column set didn't include `stock_mt` — pandas' behavior when the apply result is empty.

**Fix**: guard with `if not primary.empty:` before `apply`. Prefer vectorized
`primary["counter_id"].astype(str).map(...)` over row-wise apply.

### Previous-meet "Meet Type" values are inconsistent

**Samples**: `Mason Meet`, `Masson Meet`, `mason meet`, `Engineer meet`.

**Fix**: `_normalize_meet_type` does substring matching (`"mason" in s or "masson" in s`
→ `mason`). Architect + Engineer both → `architect`.

### Zone-target vs ≥ 8 options arithmetic doesn't line up

**Expected**: zone Mason totals equal sum of per-SM/TM mason counts.

**Actual**: zone Mason totals are much smaller than `8 × n_smtms`. Per user, the ≥ 8 rule
wins — mason fills each plan to reach 8 regardless of zone Mason totals.

**Implication**: zone Mason total is informational, not a constraint. Only Dealer,
Architect, and Contractor totals are distributed strictly.

### HP pool can underfill architect targets

**Symptom**: Central zone May architect target 2 but actual 0. After assigning 5 dealer
slots to the 10 Central SM/TMs, the remaining 5 didn't cover HP districts, so architect
couldn't be placed.

**Status**: not fixed yet — distribution is strict. Options if user cares:
1. Relax HP filter for architect when HP pool is exhausted.
2. Adjust rotation priority so HP-district SM/TMs get dealer slots last.

### Always run with real data before declaring done

**Lesson**: the synthetic smoke test passed cleanly, but the real files exposed 6+ issues
in the first run. Design fixtures to **mimic the user's actual data shape** (long format,
messy names, missing columns) to catch problems before the user does.
