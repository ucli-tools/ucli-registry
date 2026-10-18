#!/usr/bin/env python3
"""Validate registry/apps.yaml.

Checks: required fields, 40-hex pin, unique names across all lists, repo URL
ends in the entry name, and that the file round-trips through the same dump
settings update-versions.py uses. index.tsv must match what apps.yaml generates. Use --online to also check that each repo
URL resolves.
"""
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import index_tsv  # noqa: E402

REGISTRY = Path(__file__).parent.parent / "registry" / "apps.yaml"
REQUIRED = ["name", "repo", "description", "pattern", "status", "maintainer", "tags", "version"]
LISTS = ["official", "community", "templates"]
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def check_index(data, path: Path) -> list:
    """index.tsv must equal what apps.yaml generates, byte for byte."""
    if not path.exists():
        return [f"{path.name} is missing (generate it with update-versions.py)"]
    if path.read_bytes().decode("utf-8", "replace") != index_tsv.render(data):
        return [f"{path.name} disagrees with apps.yaml (a pin or entry was edited by hand)"]
    return []


def main() -> int:
    online = "--online" in sys.argv
    text = REGISTRY.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    errors = []
    apps = data.get("apps", {})
    for lst in LISTS:
        if lst not in apps:
            errors.append(f"missing list: {lst}")
    seen = {}
    for lst in LISTS:
        for app in apps.get(lst) or []:
            name = app.get("name", "?")
            where = f"{lst}/{name}"
            for field in REQUIRED:
                if not app.get(field):
                    errors.append(f"{where}: missing {field}")
            if not HEX40.match(str(app.get("version", ""))):
                errors.append(f"{where}: version is not a 40-hex commit")
            if name in seen:
                errors.append(f"{where}: duplicate name (also in {seen[name]})")
            seen[name] = lst
            repo = str(app.get("repo", ""))
            m = re.match(r"^github\.com/([^/]+)/([^/]+)$", repo)
            if not m:
                errors.append(f"{where}: bad repo URL {repo}")
            elif m.group(2) != name:
                errors.append(f"{where}: repo name {m.group(2)} differs from entry name")
            elif online:
                from urllib.request import urlopen
                try:
                    urlopen(f"https://github.com/{m.group(1)}/{m.group(2)}").close()
                except Exception as e:
                    errors.append(f"{where}: repo URL does not resolve ({e})")
    rt = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True, indent=2)
    if rt != text:
        errors.append("apps.yaml does not round-trip with the update-versions.py dump settings")
    errors.extend(check_index(data, REGISTRY.parent / "index.tsv"))
    for e in errors:
        print(f"[ERROR] {e}", file=sys.stderr)
    total = sum(len(apps.get(l) or []) for l in LISTS)
    print(f"{'FAILED' if errors else 'OK'}: {total} entries, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
