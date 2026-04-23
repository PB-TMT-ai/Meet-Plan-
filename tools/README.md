# Tools

Python scripts that do the deterministic work: API calls, data transforms, file I/O, DB queries.

## Conventions

- One script per task. File names are lowercase with underscores, e.g. `scrape_single_site.py`.
- Each script should be runnable standalone: `python tools/<name>.py [args]`.
- Load secrets from `.env` (use `python-dotenv` or `os.environ`). Never hardcode keys.
- Fail loudly with a clear error message — the agent relies on stderr/traceback to diagnose.
- Print structured output (JSON) to stdout when the agent needs to parse results.
- Write intermediate artifacts to `.tmp/` — never commit them.

## Dependencies

Add new dependencies to `requirements.txt` so the environment is reproducible.
