"""Run a supply-chain command through the stage owner's product entry."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from domain.bootstrap import find_repo
from domain.model import load_registry
from domain.supply_chain import COMMAND_STAGE, ChainError, load_stages

HUB_ROOT = Path(__file__).resolve().parents[1]


def accept(command: str, args: dict) -> dict:
    stage_id = COMMAND_STAGE.get(command)
    if stage_id is None:
        raise ChainError(f"unknown command {command}")
    registry = load_registry()
    stage = next(item for item in load_stages(registry) if item.id == stage_id)
    if stage.owner == registry.hub.name:
        entry = HUB_ROOT / stage.entry
    else:
        checkout = find_repo(stage.owner, registry)
        if checkout is None:
            raise ChainError(f"{stage.owner} checkout is not present for {stage_id}")
        entry = checkout / stage.entry
    if not entry.is_file():
        raise ChainError(f"{stage.owner} is missing stage entry {stage.entry}")
    if entry.suffix == ".py":
        runner = [sys.executable, str(entry)]
    elif entry.suffix == ".mjs":
        runner = ["node", str(entry)]
    else:
        raise ChainError(f"{stage.owner} entry {stage.entry} is not a python or node stage")
    completed = subprocess.run(
        runner,
        input=json.dumps({"command": command, "args": args}),
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ChainError(
            f"{stage.owner} {command} returned invalid JSON: {completed.stderr.strip()}"
        ) from exc
    if completed.returncode != 0 or not payload.get("ok"):
        message = payload.get("error") or completed.stderr.strip() or "stage rejected the command"
        raise ChainError(f"{stage.owner}: {message}")
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        raise ChainError(f"{stage.owner} {command} returned no artifact")
    return artifact
