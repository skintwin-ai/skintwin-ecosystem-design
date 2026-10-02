"""Walk every product in the operations document through its stage owners."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

from domain.bootstrap import find_repo
from domain.ledger import replay
from domain.model import load_registry
from domain.supply_chain import (
    COMMAND_STAGE,
    Chain,
    ChainError,
    format_trace,
    load_stages,
)

HUB_ROOT = Path(__file__).resolve().parents[1]
OPERATIONS_PATH = HUB_ROOT / "domain" / "operations.json"
RETAIL_FULFILLMENT = "order-retail:0:sku-serum-c"
TREATMENT_FULFILLMENT = "order-treatment:0:sku-serum-c"
CLEANSER_FULFILLMENT = "order-cleanser:0:sku-cleanser"

REFERENCE_COMMANDS: tuple[tuple[str, dict], ...] = (
    ("specify_ingredient", {"ingredient_id": "ascorbic", "inci": "Ascorbic Acid", "cas": "50-81-7"}),
    ("specify_ingredient", {"ingredient_id": "hyaluronic", "inci": "Sodium Hyaluronate", "cas": "9067-32-7"}),
    ("qualify_supplier", {"qualification_id": "qual-ascorbic", "supplier_name": "Cape Acids", "ingredient_id": "ascorbic"}),
    ("qualify_supplier", {"qualification_id": "qual-hyaluronic", "supplier_name": "Coastal Polymers", "ingredient_id": "hyaluronic"}),
    ("receive_lot", {"lot_id": "lot-ascorbic", "ingredient_id": "ascorbic", "qualification_id": "qual-ascorbic", "milligrams": 50000}),
    ("receive_lot", {"lot_id": "lot-hyaluronic", "ingredient_id": "hyaluronic", "qualification_id": "qual-hyaluronic", "milligrams": 5000}),
    ("define_formula", {"formula_id": "serum-c", "name": "Vitamin C serum", "lines": [["ascorbic", 10000], ["hyaluronic", 500]]}),
    ("catalog_sku", {"sku_id": "sku-serum-c", "formula_id": "serum-c", "name": "Vitamin C serum 10.5g"}),
    ("manufacture", {"batch_id": "batch-1", "sku_id": "sku-serum-c", "units": 2, "allocations": [["ascorbic", "lot-ascorbic", 20000], ["hyaluronic", "lot-hyaluronic", 1000]]}),
    ("transfer", {"transfer_id": "xfer-cape-town", "sku_id": "sku-serum-c", "batch_id": "batch-1", "source": "plant", "destination": "cape-town", "milligrams": 10500}),
    ("certify_practitioner", {"certificate_id": "cert-aya", "practitioner_id": "aya", "course": "RegimA facial protocol"}),
    ("fulfill", {"fulfillment_id": "order-retail", "sku_id": "sku-serum-c", "location": "cape-town", "milligrams": 5000, "kind": "retail", "practitioner_id": None}),
    ("fulfill", {"fulfillment_id": "order-treatment", "sku_id": "sku-serum-c", "location": "cape-town", "milligrams": 2000, "kind": "treatment", "practitioner_id": "aya"}),
    ("settle", {"settlement_id": "pay-retail", "fulfillment_id": "order-retail", "amount_cents": 18500, "currency": "ZAR"}),
    ("settle", {"settlement_id": "pay-treatment", "fulfillment_id": "order-treatment", "amount_cents": 45000, "currency": "ZAR"}),
    ("record_outcome", {"outcome_id": "outcome-retail", "fulfillment_id": "order-retail", "concern": "dullness", "score": 72}),
    ("record_outcome", {"outcome_id": "outcome-treatment", "fulfillment_id": "order-treatment", "concern": "pigmentation", "score": 81}),
)


class ProductWalk(NamedTuple):
    id: str
    traces: tuple[str, ...]
    calls: tuple[tuple[str, list], ...]


def load_products(path: Path | None = None) -> tuple[ProductWalk, ...]:
    """Products the platform walks, in document order."""
    source = path or OPERATIONS_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list) or not products:
        raise ChainError("operations must list at least one product")
    known = {stage.id for stage in load_stages()}
    loaded: list[ProductWalk] = []
    seen: set[str] = set()
    for product in products:
        if not isinstance(product, dict):
            raise ChainError("each operation product must be an object")
        product_id = product.get("id")
        traces = product.get("traces")
        calls = product.get("calls")
        if not isinstance(product_id, str) or not product_id.strip() or product_id in seen:
            raise ChainError("each operation product needs a unique id")
        seen.add(product_id)
        if (
            not isinstance(traces, list)
            or not traces
            or not all(isinstance(item, str) and item.strip() for item in traces)
        ):
            raise ChainError(f"{product_id} needs fulfillment traces")
        if not isinstance(calls, list) or not calls:
            raise ChainError(f"{product_id} needs calls")
        parsed: list[tuple[str, list]] = []
        for call in calls:
            stage_id = call.get("stage") if isinstance(call, dict) else None
            args = call.get("args") if isinstance(call, dict) else None
            if stage_id not in known:
                raise ChainError(f"{product_id} calls unknown stage {stage_id}")
            if not isinstance(args, list):
                raise ChainError(f"{product_id} {stage_id} args must be a list")
            parsed.append((stage_id, args))
        loaded.append(ProductWalk(product_id, tuple(traces), tuple(parsed)))
    return tuple(loaded)


def owner_runner(command: str) -> list[str]:
    stage_id = COMMAND_STAGE[command]
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
        return [sys.executable, str(entry)]
    if entry.suffix == ".mjs":
        return ["node", str(entry)]
    raise ChainError(f"{stage.owner} entry {stage.entry} is not a python or node stage")


def run_owner(command: str, args: dict, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        owner_runner(command),
        input=json.dumps({"command": command, "args": args}),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def ledger_env(ledger: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["SKINTWIN_CHAIN_LEDGER"] = str(ledger)
    env["SKINTWIN_HUB_ROOT"] = str(HUB_ROOT)
    env.pop("SKINTWIN_CHAIN_SKIP_DISPATCH", None)
    return env


def verify_surfaces(registry=None) -> None:
    """Each stage names the product file that records it. That file must exist."""
    loaded = registry or load_registry()
    for stage in load_stages(loaded):
        holder = stage.surface_owner or stage.owner
        if holder == loaded.hub.name:
            path = HUB_ROOT / stage.surface
        else:
            checkout = find_repo(holder, loaded)
            if checkout is None:
                raise ChainError(f"{holder} checkout is not present for {stage.id}")
            path = checkout / stage.surface
        if not path.is_file():
            raise ChainError(f"{stage.id}: surface {stage.surface} is missing")
        if stage.marker not in path.read_text(encoding="utf-8"):
            raise ChainError(f"{stage.id}: {stage.surface} does not implement {stage.marker}")


def surface_runner(stage_id: str) -> list[str]:
    registry = load_registry()
    stage = next(item for item in load_stages(registry) if item.id == stage_id)
    holder = stage.surface_owner or stage.owner
    if holder == registry.hub.name:
        checkout = HUB_ROOT
    else:
        checkout = find_repo(holder, registry)
        if checkout is None:
            raise ChainError(f"{holder} checkout is not present for {stage_id}")
    module = checkout / stage.invoke_module
    if not module.is_file():
        raise ChainError(f"{stage_id}: invoke module {stage.invoke_module} is missing")
    if module.suffix == ".py":
        runner = HUB_ROOT / "domain" / "call_surface.py"
        return [sys.executable, str(runner), str(module), stage.invoke_function]
    if module.suffix == ".mjs":
        runner = HUB_ROOT / "domain" / "call_surface.mjs"
        return ["node", str(runner), str(module), stage.invoke_function]
    raise ChainError(f"{stage_id}: invoke module {stage.invoke_module} is not a python or node surface")


def run_surface(stage_id: str, args: list, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        surface_runner(stage_id),
        input=json.dumps(args),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def run(ledger: Path) -> Chain:
    """Append every product by calling the function named in its operations."""
    verify_surfaces()
    products = load_products()
    if ledger.exists() and ledger.stat().st_size:
        raise ChainError(f"ledger {ledger} already has records")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    env = ledger_env(ledger)
    for product in products:
        for stage_id, args in product.calls:
            completed = run_surface(stage_id, args, env)
            if completed.returncode != 0:
                raise ChainError(
                    f"{product.id} {stage_id} failed: "
                    f"{completed.stdout.strip() or completed.stderr.strip()}"
                )
    return replay(ledger)


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = Path(tempfile.mkdtemp(prefix="skintwin-chain-")) / "supply-chain.jsonl"
    chain = run(path)
    blocks = [
        format_trace(chain, fulfillment_id)
        for product in load_products()
        for fulfillment_id in product.traces
    ]
    print("\n---\n".join(blocks))


if __name__ == "__main__":
    main()
