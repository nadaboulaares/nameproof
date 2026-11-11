# Contributing to nameproof

Thanks for helping make payee name matching fairer and safer across scripts.

## Setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: pipx install uv
uv sync
uv run pre-commit install
```

Or open the repo in a GitHub Codespace — the dev container does this for you.

## Before you open a PR

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest --cov
```

CI runs the same checks on Python 3.11–3.14. Coverage must stay at or above 95%.

## Ground rules

- **Every change ships with tests.** Bug fixes include a regression test that fails before the fix.
- **No real personal data.** Never commit real customer, payer or account-holder names. Use
  public-domain sources (e.g. Wikidata labels of public figures) or synthetic names.
- **Permissive dependencies only.** The core must stay Apache-2.0 compatible — no GPL/AGPL/LGPL
  dependencies or copied tables. Romanisation and legal-form tables must cite their public source.
- **Explainability is a feature.** New matching rules must add a stable explanation code to
  `Verdict.explanation`.
- **Deterministic output.** The same input and policy version must always give the same verdict.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`,
`test:`, `chore:` …).
