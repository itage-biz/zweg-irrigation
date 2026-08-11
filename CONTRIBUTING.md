# Developing Zweg Irrigation

Use Python 3.14 or the runtime supported by Home Assistant Core 2026.7.0. Create an
isolated environment, install the project development extra, and run the full gate:

```shell
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
ruff format --check .
ruff check .
mypy custom_components
pytest
```

Do not add a license file until the repository owner has selected a license.
