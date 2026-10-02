#!/usr/bin/env python3
"""Batch manufacture acceptance. The hub owns this stage until a plant service exists."""

from __future__ import annotations

import json
import sys


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
    json.dump({"ok": True, "artifact": artifact}, sys.stdout)


def _fail(message: str) -> None:
    json.dump({"ok": False, "error": message}, sys.stdout)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
