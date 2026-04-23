# Monthly Meet Plan

## Objective

Produce a monthly meet plan for every SM / TM across **North**, **East**, and **Central**
zones. Each SM/TM must receive **at least 8 meet options** (they will execute 5 of them)
spread across four meet types with specific constraints.

Output: `Meet plan/<YYYY-MM>.xlsx` — one row per SM/TM per meet option.

## Meet types and rules

| Type | Filter | Cap per SM/TM |
| --- | --- | --- |
| **Mason** | Counter's stock > 10 MT AND counter NOT met last month. Prospect counters used as fallback. | No cap (fills remaining slots to reach 8). |
| **Contractor** | SM/TM's district is high-potential. | 2 |
| **Dealer** | No district filter — just a slot assigned to the SM/TM. | 1 |
| **Architect / Engineer** | SM/TM's district is high-potential. | 1 |

Hard rule: **a given SM/TM gets Dealer OR Architect/Engineer in a month, never both.**
If the zone-breakup input has both counts > 0 for the same SM/TM,
`build_meet_plan.py` fails loudly with the offending SM/TM name.

Default split when the zone breakup is silent for an SM/TM:
`Mason 6 / Contractor 1 / Dealer 1 / Architect 0` — with the 1 shifting to Architect for
SM/TMs who had Dealer last month (rotate).

## Inputs

Drop the month's files into the matching subfolder under `inputs/`. `load_inputs.py`
picks the most recently modified file per folder, so old files can stay in place.

| Folder | File | Required columns |
| --- | --- | --- |
| `inputs/team_members/` | XLSX or CSV | `sm_tm`, `zone`, `district` |
| `inputs/zone_breakup/` | XLSX or CSV | `zone`, `sm_tm`, `mason`, `contractor`, `dealer`, `architect` (any missing column defaults to the rule above) |
| `inputs/stock/` | XLSX or CSV | `counter_id`, `counter_name`, `district`, `sm_tm`, `stock_mt`, `is_prospect` (optional — bool; true flags prospect counter) |
| `inputs/previous_meets/` | XLSX or CSV | `sm_tm`, `counter_id` (last month's mason meets only) |
| `inputs/high_potential_districts/` | XLSX or CSV | `district` |

Column-name matching is case-insensitive and tolerates spaces / punctuation; the loader
normalizes everything to `snake_case`. If a required column is missing, the loader stops
and prints the missing columns.

## Tools (run order)

```
python tools/load_inputs.py --print-summary
python tools/eligible_mason_counters.py --print
python tools/build_meet_plan.py --month YYYY-MM
```

- **`load_inputs.py`** — reads + validates every input folder, returns a dict of pandas DataFrames.
  Use `--print-summary` to sanity-check before building the plan.
- **`eligible_mason_counters.py`** — per SM/TM, returns counters with stock > 10 MT that were
  not met last month. Falls back to prospect counters (flagged in `notes`) if fewer than 6.
- **`build_meet_plan.py`** — orchestrator. Applies the split rules, enforces the
  dealer-vs-architect mutual exclusion, pushes mason count up when a district is not
  high-potential, writes `Meet plan/<month>.xlsx`.

## Outputs

`Meet plan/<YYYY-MM>.xlsx` with one row per meet option:

| Column | Notes |
| --- | --- |
| `zone` | North / East / Central |
| `sm_tm` | SM/TM name |
| `district` | SM/TM's district |
| `meet_type` | mason / contractor / dealer / architect |
| `counter_id` | Only filled for mason rows |
| `counter_name` | Only filled for mason rows |
| `stock_mt` | Only filled for mason rows |
| `notes` | e.g. "prospect counter — stock fallback" or "non-HP district, extra mason slot" |

The SM/TM fills in specific contractor / dealer / architect names locally — the tool
doesn't pick those.

## Edge cases / notes

- **Fewer than 6 eligible mason counters** — fill remaining slots with prospect counters
  from the same district, flagged in `notes`.
- **SM/TM's district is NOT high-potential** — zero out contractor and architect slots,
  keep dealer slot if the breakup has one, push mason count up to reach 8.
- **Zone-breakup row missing for an SM/TM** — apply the default split, warn on stderr.
- **Dealer + Architect both > 0 for the same SM/TM** — hard fail with the SM/TM name.
- **No files in an `inputs/<folder>/`** — `load_inputs.py` fails loudly naming the empty folder.

## Verification

1. Every SM/TM has at least 8 rows.
2. No SM/TM has more than 2 contractor rows.
3. No SM/TM has both a dealer and an architect row.
4. No mason `counter_id` appears in this month's plan and in last month's meet log.
5. Prospect-counter fallback rows carry a `notes` flag.
