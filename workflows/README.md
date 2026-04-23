# Workflows

Markdown SOPs. One file per workflow. Keep them in plain language — brief the agent the way you'd brief a teammate.

## Template

Each workflow should cover:

- **Objective** — What this workflow accomplishes.
- **Inputs** — What the agent needs before starting (URLs, IDs, files, parameters).
- **Tools** — Which scripts in `tools/` to run, in what order.
- **Outputs** — Where results land (cloud service, file path, return value).
- **Edge cases / notes** — Known failure modes, rate limits, retries, gotchas discovered on past runs.

## Conventions

- File names are lowercase with underscores, e.g. `scrape_website.md`.
- Update the workflow whenever you learn something new — that's how the system improves.
- Don't overwrite an existing workflow without confirming with the user first.
