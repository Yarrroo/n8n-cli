# Tech Stack

**Runtime**: Python 3.11+ (3.11 & 3.12 tested)
**Build**: hatchling; `pip install -e ".[dev]"` for development

## Runtime dependencies
- `typer>=0.12,<1` — CLI framework (Typer sub-apps, one per resource)
- `httpx>=0.27,<1` — HTTP client (sync; Transport wraps it)
- `pydantic[email]>=2.6,<3` — models (strict mypy plugin enabled)
- `jsonpath-ng>=1.6,<2` — dot-notation patch paths (`--set a.b.c=v`)
- `PyYAML>=6,<7` — config serialization
- `rich>=13,<15` — `--human` tables + error console
- `platformdirs>=4,<5` — XDG config paths
- `python-dotenv>=1,<2` — `.env` override loading

## Dev tools
- `pytest>=8` + `pytest-vcr` / `vcrpy>=6` — cassette-based integration tests (no live instance required for unit+integration)
- `mypy>=1.10` strict + pydantic plugin; exclude `models/_generated/`
- `ruff>=0.6` — lint (E/F/W/I/UP/B/SIM/RUF/N/C4/PTH/TID) + format (double quotes, line-length 100)
- `pre-commit>=3.7`
- `datamodel-code-generator>=0.26` — generate `models/_generated/` from n8n OpenAPI spec

## Entry point
`n8n-cli` → `n8n_cli.main:run`
Config: `~/.config/n8n-cli/config.yaml`
Sessions: `~/.config/n8n-cli/sessions/<instance>.session` (chmod 600)
