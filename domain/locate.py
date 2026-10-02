"""Find the supply-chain hub, ledger, and sibling checkouts from domain data.

Stage owners load this module. Search roots live in org-ecosystem.json. The
ledger path lives in supply-chain.json. Owners do not keep their own copies.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

MARKER_FILES = ("package.json", "pyproject.toml", "requirements.txt", "README.md")
REGISTRY_NAME = "domain/org-ecosystem.json"
STAGES_NAME = "domain/supply-chain.json"


def module_hub() -> Path:
    """Hub that contains this file."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if _is_hub(parent):
            return parent
    raise FileNotFoundError("supply-chain hub is not present")


def find_hub() -> Path | None:
    """Hub named by SKINTWIN_HUB_ROOT, or the hub that contains this module."""
    override = os.environ.get("SKINTWIN_HUB_ROOT")
    if override and _is_hub(Path(override)):
        return Path(override).resolve()
    try:
        return module_hub()
    except FileNotFoundError:
        return None


def ledger_file(hub: Path | None = None) -> Path:
    root = hub or module_hub()
    return root / _ledger_relative(root)


def bind_ledger() -> Path | None:
    """Point this process at the shared ledger without replacing an explicit path."""
    hub = find_hub()
    if hub is None:
        return None
    os.environ.setdefault("SKINTWIN_HUB_ROOT", str(hub))
    os.environ.setdefault("SKINTWIN_CHAIN_LEDGER", str(ledger_file(hub)))
    return hub


def checkout(name: str) -> Path | None:
    """Resolve a sibling from registry search roots."""
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return None
    hub = find_hub()
    if hub is None:
        return None
    registry = _registry(hub)
    hub_name = registry.get("hub", {}).get("name")
    if name == hub_name:
        return hub
    for root in _search_roots(hub, registry):
        directory = root / name
        if directory.is_dir() and any((directory / marker).is_file() for marker in MARKER_FILES):
            return directory
    return None


def commit_command(request: dict) -> str | None:
    """Append one accepted command. Return an error string when the ledger rejects it."""
    hub = find_hub()
    if hub is None or not os.environ.get("SKINTWIN_CHAIN_LEDGER"):
        return "supply-chain hub is not present"
    completed = subprocess.run(
        [sys.executable, "-m", "domain.ledger"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=hub,
        check=False,
    )
    if completed.returncode == 0:
        return None
    try:
        message = json.loads(completed.stdout or "{}").get("error")
    except json.JSONDecodeError:
        message = None
    return str(message or completed.stderr or "ledger rejected the command")


def stage_entry(stage_id: str) -> Path | None:
    """Owner command script named by supply-chain.json."""
    hub = find_hub()
    if hub is None:
        return None
    for stage in _stages(hub):
        if stage.get("id") != stage_id:
            continue
        owner = stage.get("owner")
        entry = stage.get("entry")
        if not isinstance(owner, str) or not isinstance(entry, str):
            return None
        root = checkout(owner)
        if root is None:
            return None
        path = root / entry
        return path if path.is_file() else None
    return None


def _is_hub(path: Path) -> bool:
    return (path / REGISTRY_NAME).is_file() and (path / STAGES_NAME).is_file()


def _registry(hub: Path) -> Mapping[str, object]:
    data = json.loads((hub / REGISTRY_NAME).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("org ecosystem registry must be an object")
    return data


def _stages(hub: Path) -> list:
    data = json.loads((hub / STAGES_NAME).read_text(encoding="utf-8"))
    stages = data.get("stages") if isinstance(data, dict) else None
    if not isinstance(stages, list):
        raise ValueError("supply-chain stages must be a list")
    return stages


def _ledger_relative(hub: Path) -> str:
    data = json.loads((hub / STAGES_NAME).read_text(encoding="utf-8"))
    relative = data.get("ledger") if isinstance(data, dict) else None
    if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")):
        raise ValueError("supply-chain ledger must be a relative path")
    if ".." in Path(relative).parts:
        raise ValueError("supply-chain ledger must stay inside the hub")
    return relative


def _search_roots(hub: Path, registry: Mapping[str, object]) -> list[Path]:
    override = os.environ.get("CLOUD_AGENT_REPO_ROOTS")
    if override is not None:
        return [Path(raw).resolve() for raw in override.split(":") if raw]
    listed = registry.get("searchRoots")
    if not isinstance(listed, list) or not listed or not all(isinstance(item, str) and item for item in listed):
        raise ValueError("searchRoots must be a non-empty list of strings")
    roots = [Path(item).resolve() for item in listed]
    parent = hub.resolve().parent
    if parent not in roots:
        roots.append(parent)
    return roots


def main() -> None:
    hub = bind_ledger()
    if hub is None:
        json.dump({"ok": False, "error": "supply-chain hub is not present"}, sys.stdout)
        raise SystemExit(1)
    json.dump(
        {"ok": True, "hub": str(hub), "ledger": os.environ["SKINTWIN_CHAIN_LEDGER"]},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
