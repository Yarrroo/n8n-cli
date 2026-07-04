# Suggested Commands

## Install
```
pip install -e ".[dev]"
```

## Test
```
pytest                                           # all tests (unit + integration cassettes)
pytest tests/unit/                               # unit only — no live instance needed
pytest -m "not integration and not acceptance"   # skip live-instance tests
pytest tests/acceptance/ -m acceptance           # success-criteria; needs N8N_CLI_TEST_INSTANCE
```
Integration tests use VCR cassettes (`tests/integration/cassettes/`) — no live instance needed unless recording new cassettes.

## Lint / type-check
```
ruff check .          # lint
ruff format .         # format (or --check for CI)
mypy n8n_cli/         # type check (strict; excludes models/_generated/)
pre-commit run --all-files   # all hooks at once
```

## Run CLI
```
n8n-cli --help
n8n-cli workflow list --instance prod
n8n-cli --verbose workflow get --id <id>   # shows which backend (public/frontend) handled call
```

## Build / publish
```
python -m build   # wheel + sdist via hatchling
```
