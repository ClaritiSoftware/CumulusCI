# Repository Guidelines

## Project Structure & Module Organization
- `cumulusci/` holds the package; CLI commands live in `cli/`, pluggable tasks in `tasks/`, and shared helpers in `utils/`.
- Tests sit in `cumulusci/tests`, org-level suites in `integration_tests/`, Robot assets in `robot/`, and docs in `docs/`.
- Release scaffolding is kept under `metadeploy/`, Salesforce metadata samples in `src/`, and reusable datasets in `datasets/`.
- Project-level automation is configured via `cumulusci.yml`, with its schema helpers in `cumulusci/schema/`.

## Build, Test, and Development Commands
- `uv venv && source .venv/bin/activate` followed by `uv sync --dev` prepares a local environment.
- `uv run pytest -q` (or `make test`) runs the fast pytest suite; add `-k keyword` to focus runs.
- `make lint` invokes flake8; run `uv run black .` and `uv run isort .` before committing for consistent formatting.
- `make docs` builds the Sphinx site, `make dist` creates release artifacts, and `uv run cci doctor` verifies CLI wiring.

## Coding Style & Naming Conventions
- Target Python 3.11+, 4-space indentation, Black's 88-character width, snake_case for modules/functions, CapWords for classes.
- Keep code in the domain-specific module tree and name new tests `test_<feature>.py` so pytest auto-discovers them.
- Type hints are encouraged; Pyright basic mode covers the whitelisted files in `pyproject.toml`.

## Testing Guidelines
- Mirror production modules with pytest files and reuse fixtures in `cumulusci/tests` to avoid brittle setups.
- Use `pytest.mark` markers already registered (e.g., `metadeploy`, `use_real_env`) for slow or external cases.
- Refresh VCR-backed tests with `make vcr`; when hitting real orgs, pass `--org <alias>` and keep secrets out of the repo.
- `make coverage` reports coverage—ensure new logic is backed by unit tests or Robot suites where it makes sense.

## Commit & Pull Request Guidelines
- Follow the observed format `<ticket> <type>: imperative summary` (e.g., `DEVOPS-657 feat: extend update_dependency task`).
- Keep commits scoped and reference issues or Trailhead work items in the body when additional context helps reviewers.
- PRs should describe the change, note test evidence (`pytest`, `make docs`, etc.), and flag follow-up tasks early.
- Attach CLI output or screenshots for user-facing updates and refresh docs or release notes if behavior shifts.

## Configuration & Security Tips
- Never store Salesforce credentials in the repo; rely on CumulusCI keychains or environment variables instead.
- Regenerate `cumulusci/schema/cumulusci.jsonschema.json` with `make schema` when expanding `cumulusci.yml` structures and validate new YAML against it.
