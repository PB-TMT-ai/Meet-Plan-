# Meet Plan — Project Instructions

This repository automates the **monthly meet plan** for every SM / TM across North, East, and
Central zones. Each SM/TM gets ≥ 8 meet options per month (mason / contractor / dealer /
architect), filtered by stock levels, prior meets, and district tier.

- **SOP**: `workflows/monthly_meet_plan.md` — how to run the pipeline.
- **Durable facts** (roster size, HP threshold, name aliases, file schemas):
  `memories.md`. Read first so you don't rediscover constraints.
- **Session learnings** (what broke, what we figured out): `learnings.md`. Append as you
  discover new quirks.

## WAT Framework — Operating Instructions

This repository follows the **WAT** architecture: **Workflows, Agents, Tools**. Probabilistic AI handles reasoning; deterministic code handles execution. That separation is what makes the system reliable.

## Layers

**1. Workflows (`workflows/`)** — Markdown SOPs. Each defines objective, required inputs, which tools to use, expected outputs, and edge-case handling. Plain language.

**2. Agents (Claude)** — Read the relevant workflow, run tools in the correct sequence, handle failures gracefully, ask clarifying questions when needed. Connect intent to execution without trying to do everything directly.

**3. Tools (`tools/`)** — Python scripts that do the actual work: API calls, data transformations, file operations, DB queries. Consistent, testable, fast. Credentials live in `.env`.

Why: if each step is 90% accurate, five chained steps land at 59%. Offload execution to deterministic scripts so the agent stays focused on orchestration.

## How to Operate

1. **Read `memories.md` first.** Durable facts are there — don't waste a round rediscovering them.
2. **Look for existing tools first.** Check `tools/` before writing anything new. Only create new scripts when nothing fits.
3. **Learn and adapt when things fail.** Read the full error and trace. Fix the script and retest — if it uses paid APIs or credits, confirm before re-running. Capture what you learned in `learnings.md` and update the workflow if it changes the recipe.
4. **Keep workflows current.** Update them as you learn better methods or find new constraints. Don't create or overwrite workflows without asking unless explicitly told to.

## Self-Improvement Loop

Every failure makes the system stronger: identify what broke → fix the tool → verify the fix → record in `learnings.md` → update `memories.md` / the workflow if it's durable → move on.

## File Structure

```
CLAUDE.md      # This file. Project instructions + WAT operating rules.
memories.md    # Durable facts about this project (read first).
learnings.md   # Session discoveries, data quirks, gotchas.
workflows/     # Markdown SOPs defining what to do and how.
tools/         # Python scripts for deterministic execution.
inputs/        # Monthly user-provided data. Subfolders:
               #   team_members/ zone_breakup/ stock/
               #   previous_meets/ high_potential_districts/
Meet plan/     # Monthly output XLSX files (YYYY-MM.xlsx).
.tmp/          # Temporary / intermediate files. Regenerated as needed. Gitignored.
.env           # API keys and environment variables. NEVER store secrets anywhere else. Gitignored.
credentials.json, token.json   # Google OAuth (unused in v1). Gitignored.
```

Deliverables live in `Meet plan/` as local XLSX for now. When we wire this to Google
Sheets, outputs will move there — local files stay for processing only.

## Bottom Line

You sit between intent (workflows) and execution (tools). Read instructions, make smart decisions, call the right tools, recover from errors, keep improving the system.

