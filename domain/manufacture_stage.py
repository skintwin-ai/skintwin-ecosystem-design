#!/usr/bin/env python3
"""Batch manufacture acceptance. The hub ledger is the plant record until a plant service exists."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def manufacture(args: dict) -> dict:
    allocations = args.get("allocations")
    if not isinstance(allocations, list) or not allocations:
        raise ValueError("manufacture requires lot allocations")
    parsed = []
    for item in allocations:
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError("each allocation is [ingredient_id, lot_id, milligrams]")
        ingredient_id, lot_id, milligrams = item
        parsed.append(
            [
                _text(ingredient_id, "ingredient_id"),
                _text(lot_id, "lot_id"),
                _positive(milligrams, "milligrams"),
            ]
        )
    return {
        "batch_id": _text(args.get("batch_id"), "batch_id"),
        "sku_id": _text(args.get("sku_id"), "sku_id"),
        "units": _positive(args.get("units"), "units"),
        "allocations": parsed,
    }


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def main() -> None:
    request = json.load(sys.stdin)
    if request.get("command") != "manufacture":
        _fail(f"unknown command {request.get('command')}")
    try:
        artifact = manufacture(request.get("args") or {})
    except ValueError as exc:
        _fail(str(exc))
    committed = _commit(request)
    if committed is not None:
        _fail(committed)
    json.dump({"ok": True, "artifact": artifact}, sys.stdout)


def _commit(request: dict) -> str | None:
    if os.environ.get("SKINTWIN_CHAIN_SKIP_DISPATCH") == "1":
        return None
    ledger = os.environ.get("SKINTWIN_CHAIN_LEDGER")
    if not ledger:
        return None
    hub = Path(__file__).resolve().parents[1]
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


def _fail(message: str) -> None:
    json.dump({"ok": False, "error": message}, sys.stdout)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
