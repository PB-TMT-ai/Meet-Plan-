# WAT Framework — Operating Instructions

This repository follows the **WAT** architecture: **Workflows, Agents, Tools**. Probabilistic AI handles reasoning; deterministic code handles execution. That separation is what makes the system reliable.

## Layers

**1. Workflows (`workflows/`)** — Markdown SOPs. Each defines objective, required inputs, which tools to use, expected outputs, and edge-case handling. Plain language.

**2. Agents (Claude)** — Read the relevant workflow, run tools in the correct sequence, handle failures gracefully, ask clarifying questions when needed. Connect intent to execution without trying to do everything directly.

**3. Tools (`tools/`)** — Python scripts that do the actual work: API calls, data transformations, file operations, DB queries. Consistent, testable, fast. Credentials live in `.env`.

Why: if each step is 90% accurate, five chained steps land at 59%. Offload execution to deterministic scripts so the agent stays focused on orchestration.

## How to Operate

1. **Look for existing tools first.** Check `tools/` before writing anything new. Only create new scripts when nothing fits.
2. **Learn and adapt when things fail.** Read the full error and trace. Fix the script and retest — if it uses paid APIs or credits, confirm before re-running. Document what you learned in the workflow (rate limits, timing quirks, unexpected behavior).
3. **Keep workflows current.** Update them as you learn better methods or find new constraints. Don't create or overwrite workflows without asking unless explicitly told to.

## Self-Improvement Loop

Every failure makes the system stronger: identify what broke → fix the tool → verify the fix → update the workflow → move on.

## File Structure

```
.tmp/         # Temporary / intermediate files. Regenerated as needed. Gitignored.
tools/        # Python scripts for deterministic execution.
workflows/    # Markdown SOPs defining what to do and how.
.env          # API keys and environment variables. NEVER store secrets anywhere else. Gitignored.
credentials.json, token.json   # Google OAuth. Gitignored.
```

**Deliverables** go to cloud services (Google Sheets, Slides, etc.) where the user can access them directly. Local files are just for processing — anything in `.tmp/` is disposable.

## Bottom Line

You sit between intent (workflows) and execution (tools). Read instructions, make smart decisions, call the right tools, recover from errors, keep improving the system.
