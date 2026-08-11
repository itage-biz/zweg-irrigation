"""Minimal local validation for the HACS custom-component layout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(__file__).parents[1]
components = root / "custom_components"
integrations = [
    path for path in components.iterdir() if path.is_dir() and (path / "manifest.json").is_file()
]
if [path.name for path in integrations] != ["zweg_irrigation"]:
    print("exactly one custom integration named zweg_irrigation is required", file=sys.stderr)
    raise SystemExit(1)

manifest = json.loads((integrations[0] / "manifest.json").read_text())
required = {
    "domain",
    "name",
    "version",
    "documentation",
    "issue_tracker",
    "codeowners",
    "config_flow",
    "integration_type",
}
missing = required - manifest.keys()
if missing or manifest["domain"] != "zweg_irrigation" or not manifest["config_flow"]:
    print(f"invalid manifest; missing={sorted(missing)}", file=sys.stderr)
    raise SystemExit(1)
