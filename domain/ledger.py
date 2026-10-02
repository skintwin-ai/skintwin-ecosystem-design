"""Append-only supply-chain ledger shared by stage owners.

Replay applies recorded commands with owner dispatch turned off. The owner
already accepted the command before it was appended.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from domain.supply_chain import Chain, ChainError

HUB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = HUB_ROOT / "var" / "supply-chain.jsonl"


def ledger_path() -> Path | None:
    raw = os.environ.get("SKINTWIN_CHAIN_LEDGER")
    if not raw:
        return None
    return Path(raw)


def replay(path: Path) -> Chain:
    chain = Chain()
    if not path.is_file():
        return chain
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        chain = apply_command(chain, record["command"], record["args"])
    return chain


def append_command(command: str, args: dict, path: Path | None = None) -> dict:
    target = path or ledger_path()
    if target is None:
        raise ChainError("SKINTWIN_CHAIN_LEDGER is not set")
    chain = replay(target)
    chain = apply_command(chain, command, args)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"command": command, "args": args}, sort_keys=True) + "\n")
    return {"ok": True}


def apply_command(chain: Chain, command: str, args: dict) -> Chain:
    previous = os.environ.get("SKINTWIN_CHAIN_SKIP_DISPATCH")
    os.environ["SKINTWIN_CHAIN_SKIP_DISPATCH"] = "1"
    try:
        return _APPLY[command](chain, args)
    finally:
        if previous is None:
            os.environ.pop("SKINTWIN_CHAIN_SKIP_DISPATCH", None)
        else:
            os.environ["SKINTWIN_CHAIN_SKIP_DISPATCH"] = previous


def _specify(chain: Chain, args: dict) -> Chain:
    return chain.specify_ingredient(args["ingredient_id"], args["inci"], args["cas"])


def _qualify(chain: Chain, args: dict) -> Chain:
    return chain.qualify_supplier(
        args["qualification_id"], args["supplier_name"], args["ingredient_id"]
    )


def _receive(chain: Chain, args: dict) -> Chain:
    return chain.receive_lot(
        args["lot_id"],
        args["ingredient_id"],
        args["qualification_id"],
        int(args["milligrams"]),
    )


def _formula(chain: Chain, args: dict) -> Chain:
    lines = tuple((item[0], int(item[1])) for item in args["lines"])
    return chain.define_formula(args["formula_id"], args["name"], lines)


def _catalog(chain: Chain, args: dict) -> Chain:
    return chain.catalog_sku(args["sku_id"], args["formula_id"], args["name"])


def _manufacture(chain: Chain, args: dict) -> Chain:
    allocations = tuple(
        (item[0], item[1], int(item[2])) for item in args["allocations"]
    )
    return chain.manufacture(args["batch_id"], args["sku_id"], int(args["units"]), allocations)


def _transfer(chain: Chain, args: dict) -> Chain:
    return chain.transfer(
        args["transfer_id"],
        args["sku_id"],
        args["batch_id"],
        args["source"],
        args["destination"],
        int(args["milligrams"]),
    )


def _certify(chain: Chain, args: dict) -> Chain:
    return chain.certify_practitioner(
        args["certificate_id"], args["practitioner_id"], args["course"]
    )


def _fulfill(chain: Chain, args: dict) -> Chain:
    return chain.fulfill(
        args["fulfillment_id"],
        args["sku_id"],
        args["location"],
        int(args["milligrams"]),
        args["kind"],
        args.get("practitioner_id"),
    )


def _settle(chain: Chain, args: dict) -> Chain:
    return chain.settle(
        args["settlement_id"],
        args["fulfillment_id"],
        int(args["amount_cents"]),
        args["currency"],
    )


def _outcome(chain: Chain, args: dict) -> Chain:
    return chain.record_outcome(
        args["outcome_id"],
        args["fulfillment_id"],
        args["concern"],
        int(args["score"]),
    )


_APPLY = {
    "specify_ingredient": _specify,
    "qualify_supplier": _qualify,
    "receive_lot": _receive,
    "define_formula": _formula,
    "catalog_sku": _catalog,
    "manufacture": _manufacture,
    "transfer": _transfer,
    "certify_practitioner": _certify,
    "fulfill": _fulfill,
    "settle": _settle,
    "record_outcome": _outcome,
}


def main() -> None:
    import sys

    request = json.load(sys.stdin)
    try:
        append_command(request["command"], request.get("args") or {})
    except (ChainError, KeyError, TypeError, ValueError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        raise SystemExit(1)
    json.dump({"ok": True}, sys.stdout)


if __name__ == "__main__":
    main()
