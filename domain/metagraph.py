"""Typed hypergraph over the supply-chain ledger.

Supply types (raw materials, packaging) and demand types (product sales,
treatments) meet at the formulation waist. A sale at an outlet becomes
integer material demand on the lots that fed its batch, packaging demand as
an exact fraction of a piece, and a Stripe Connect split from the platform
template. This is a projection of the ledger, not a second chain of custody.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import gcd
from pathlib import Path
from typing import Mapping

from domain.supply_chain import PLANT, Chain, ChainError, reference_serum

DOCUMENT_PATH = Path(__file__).resolve().parent / "metagraph.json"
SIDES = frozenset({"supply", "demand", "center"})


class MetagraphError(ValueError):
    """The typed hypergraph document does not match the supply chain."""


@dataclass(frozen=True)
class TypeNode:
    id: str
    parents: tuple[str, ...]


@dataclass(frozen=True)
class ConnectTemplate:
    id: str
    type_id: str
    charge: str
    extends: str | None
    fee_bps: int | None


@dataclass(frozen=True)
class PackagingSpec:
    id: str
    formula_id: str
    pieces_per_unit: int


@dataclass(frozen=True)
class Fiber:
    stage: str
    type_id: str
    side: str


@dataclass(frozen=True)
class Document:
    types: tuple[TypeNode, ...]
    templates: tuple[ConnectTemplate, ...]
    packaging: tuple[PackagingSpec, ...]
    fibers: tuple[Fiber, ...]


@dataclass(frozen=True)
class MaterialDraw:
    ingredient_id: str
    qualification_id: str
    supplier_name: str
    milligrams: int


@dataclass(frozen=True)
class PackagingDraw:
    component_id: str
    numerator: int
    denominator: int
    supplier_name: str = ""


@dataclass(frozen=True)
class ConnectSplit:
    template_id: str
    destination_role: str
    currency: str
    platform_fee_cents: int
    destination_cents: int


@dataclass(frozen=True)
class SaleLink:
    fulfillment_id: str
    outlet: str
    kind: str
    type_id: str
    sku_id: str
    formula_id: str
    milligrams: int
    materials: tuple[MaterialDraw, ...]
    packaging: tuple[PackagingDraw, ...]
    connect: ConnectSplit | None


@dataclass(frozen=True)
class Bowtie:
    sales: tuple[SaleLink, ...]
    logistics: tuple[tuple[str, str, str, int], ...] = ()

    def supplier_demand(self) -> tuple[tuple[str, str, str, int], ...]:
        """(qualification, supplier, ingredient, milligrams) across every outlet."""
        totals: dict[tuple[str, str, str], int] = {}
        for sale in self.sales:
            for draw in sale.materials:
                key = (draw.qualification_id, draw.supplier_name, draw.ingredient_id)
                totals[key] = totals.get(key, 0) + draw.milligrams
        return tuple((*key, milligrams) for key, milligrams in sorted(totals.items()))

    def packaging_demand(self) -> tuple[tuple[str, str, int, int], ...]:
        """(component, supplier, numerator, denominator) in lowest terms."""
        totals: dict[tuple[str, str], tuple[int, int]] = {}
        for sale in self.sales:
            for draw in sale.packaging:
                key = (draw.component_id, draw.supplier_name)
                numer, denom = totals.get(key, (0, 1))
                totals[key] = _add_fraction(numer, denom, draw.numerator, draw.denominator)
        return tuple(
            (component, supplier, numer, denom)
            for (component, supplier), (numer, denom) in sorted(totals.items())
            if numer
        )


def load_document(path: Path | None = None) -> Document:
    source = path or DOCUMENT_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MetagraphError("metagraph document must be an object")
    types = _types(data.get("types"))
    known = {item.id for item in types}
    _acyclic(types)
    return Document(
        types,
        _templates(data.get("connectTemplates"), known),
        _packaging(data.get("packaging")),
        _fibers(data.get("fibers"), known),
    )


def ancestors(document: Document, type_id: str) -> frozenset[str]:
    by_id = {item.id: item for item in document.types}
    if type_id not in by_id:
        raise MetagraphError(f"unknown type {type_id}")
    found = {type_id}
    stack = [type_id]
    while stack:
        current = by_id[stack.pop()]
        for parent in current.parents:
            if parent not in found:
                found.add(parent)
                stack.append(parent)
    return frozenset(found)


def project(chain: Chain, document: Document | None = None) -> Bowtie:
    """Project ledger sales into supply demand through the formulation waist."""
    loaded = document or load_document()
    _fibers_cover_stages(loaded)
    templates = {item.id: item for item in loaded.templates}
    packaging_by_formula: dict[str, list[PackagingSpec]] = {}
    for spec in loaded.packaging:
        packaging_by_formula.setdefault(spec.formula_id, []).append(spec)
    returned = {item.fulfillment_id for item in chain.returns}
    sales: list[SaleLink] = []
    for fulfillment in chain.fulfillments:
        if fulfillment.id in returned:
            continue
        sku = chain._sku(fulfillment.sku_id)
        formula = chain._formula(sku.formula_id)
        sold = sum(draw.milligrams for draw in fulfillment.draws)
        materials = _materials(chain, fulfillment)
        if sum(item.milligrams for item in materials) != sold:
            raise MetagraphError(
                f"{fulfillment.id} material demand {sum(item.milligrams for item in materials)} "
                f"does not equal sale {sold}"
            )
        packs = _sale_packaging(
            chain,
            fulfillment,
            formula,
            sold,
            packaging_by_formula.get(formula.id, []),
        )
        type_id = "Treatment" if fulfillment.kind == "treatment" else "ProductSale"
        if "Demand" not in ancestors(loaded, type_id):
            raise MetagraphError(f"{type_id} is not a demand type")
        sales.append(
            SaleLink(
                fulfillment.id,
                fulfillment.location,
                fulfillment.kind,
                type_id,
                sku.id,
                formula.id,
                sold,
                materials,
                packs,
                _connect(chain, fulfillment, templates),
            )
        )
    from domain.platform import replenishment_shipment

    plan = tuple(
        (
            item["args"]["sku_id"],
            item["args"]["batch_id"],
            item["args"]["destination"],
            item["args"]["milligrams"],
        )
        for item in replenishment_commands(chain, replenishment_shipment())
    )
    return Bowtie(tuple(sales), plan)


def format_bowtie(bowtie: Bowtie) -> str:
    lines: list[str] = []
    for sale in bowtie.sales:
        lines.append(
            f"{sale.outlet} {sale.type_id} {sale.sku_id} {sale.milligrams} mg "
            f"via {sale.formula_id}"
        )
        for draw in sale.materials:
            lines.append(
                f"  {draw.ingredient_id} {draw.supplier_name} {draw.milligrams} mg"
            )
        for pack in sale.packaging:
            supplier = f" {pack.supplier_name}" if pack.supplier_name else ""
            lines.append(
                f"  packaging {pack.component_id}{supplier} {pack.numerator}/{pack.denominator}"
            )
        if sale.connect is not None:
            lines.append(
                f"  connect {sale.connect.destination_role} "
                f"{sale.connect.destination_cents} platform "
                f"{sale.connect.platform_fee_cents} {sale.connect.currency}"
            )
    lines.append("supplier demand:")
    for qualification, supplier, ingredient, milligrams in bowtie.supplier_demand():
        lines.append(f"  {supplier} {ingredient} {qualification} {milligrams} mg")
    lines.append("packaging demand:")
    for component, supplier, numer, denom in bowtie.packaging_demand():
        lines.append(f"  {supplier} {component} {numer}/{denom}")
    lines.append("logistics:")
    for sku_id, batch_id, destination, milligrams in bowtie.logistics:
        lines.append(f"  {PLANT} {destination} {sku_id} {batch_id} {milligrams} mg")
    return "\n".join(lines)


def replenishment_commands(chain: Chain, shipment_id: str) -> list[dict]:
    """Transfers that replace what each outlet sold, drawn from plant stock.

    Repeating the same shipment id sends nothing further, including after more
    stock arrives at the plant. A later shipment id replaces only what earlier
    replenishment has not already sent. Distribution transfers stay uncovered.
    A short plant is shared across outlets in proportion to what they sold.
    """
    if not isinstance(shipment_id, str) or not shipment_id.strip():
        raise MetagraphError("shipment id is required")
    shipment_id = shipment_id.strip()
    if _shipment_already_sent(chain, shipment_id):
        return []
    prefix = f"replenish:{shipment_id}:"
    demand: dict[tuple[str, str, str], int] = {}
    returned = {item.fulfillment_id for item in chain.returns}
    for fulfillment in chain.fulfillments:
        if fulfillment.id in returned or fulfillment.location == PLANT:
            continue
        for draw in fulfillment.draws:
            key = (fulfillment.sku_id, draw.batch_id, fulfillment.location)
            demand[key] = demand.get(key, 0) + draw.milligrams
    covered: dict[tuple[str, str, str], int] = {}
    for movement in chain.movements:
        if movement.milligrams < 1 or not _replenishment_ref(str(movement.ref)):
            continue
        key = (movement.sku_id, movement.batch_id, movement.location)
        covered[key] = covered.get(key, 0) + movement.milligrams
    by_batch: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for (sku_id, batch_id, location), sold in sorted(demand.items()):
        need = sold - covered.get((sku_id, batch_id, location), 0)
        if need < 1:
            continue
        by_batch.setdefault((sku_id, batch_id), []).append((location, need))
    commands: list[dict] = []
    index = 0
    for sku_id, batch_id in sorted(by_batch):
        outlets = by_batch[(sku_id, batch_id)]
        available = chain.balance(sku_id, batch_id, PLANT)
        if available < 1:
            continue
        requested = [milligrams for _location, milligrams in outlets]
        total = sum(requested)
        granted = requested if total <= available else _attribute(available, requested, total)
        for (location, _need), milligrams in zip(outlets, granted):
            if milligrams < 1:
                continue
            commands.append(
                {
                    "command": "transfer",
                    "args": {
                        "transfer_id": f"{prefix}{index}",
                        "sku_id": sku_id,
                        "batch_id": batch_id,
                        "source": PLANT,
                        "destination": location,
                        "milligrams": milligrams,
                    },
                }
            )
            index += 1
    return commands


def _shipment_already_sent(chain: Chain, shipment_id: str) -> bool:
    """True when this shipment id already moved stock."""
    from domain.platform import replenishment_shipments

    current = f"replenish:{shipment_id}:"
    legacy = f"{shipment_id}:" if shipment_id in replenishment_shipments() else ""
    for movement in chain.movements:
        if movement.milligrams < 1:
            continue
        ref = str(movement.ref)
        if ref.startswith(current) or (legacy and ref.startswith(legacy)):
            return True
    return False


def _replenishment_ref(ref: str) -> bool:
    """A replenishment transfer, not a distribution or a return.

    New transfers are ``replenish:{shipment}:{index}``. A ledger written before
    that prefix still counts an operations shipment id.
    """
    from domain.platform import replenishment_shipments

    if ref.startswith("replenish:"):
        return True
    for shipment_id in replenishment_shipments():
        prefix = f"{shipment_id}:"
        if ref.startswith(prefix) and ref[len(prefix) :].isdigit():
            return True
    return False


def main() -> None:
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "--replenish":
        from domain.ledger import ledger_path, replay

        shipment = sys.argv[2] if len(sys.argv) > 2 else ""
        path = ledger_path()
        if path is None:
            sys.stdout.write(json.dumps({"error": "ledger is not set"}))
            raise SystemExit(1)
        try:
            commands = replenishment_commands(replay(path), shipment)
        except (MetagraphError, ChainError) as exc:
            sys.stdout.write(json.dumps({"error": str(exc)}))
            raise SystemExit(1)
        json.dump(commands, sys.stdout)
        return
    print(format_bowtie(project(reference_serum())))


def _materials(chain: Chain, fulfillment) -> tuple[MaterialDraw, ...]:
    totals: dict[tuple[str, str, str], int] = {}
    for draw in fulfillment.draws:
        batch = chain._batch(draw.batch_id)
        finished = sum(item.milligrams for item in batch.consumptions)
        if finished < 1:
            raise MetagraphError(f"batch {batch.id} consumed no material")
        shares = _attribute(draw.milligrams, [item.milligrams for item in batch.consumptions], finished)
        for consumption, share in zip(batch.consumptions, shares):
            if share == 0:
                continue
            lot = chain._lot(consumption.lot_id)
            qualification = chain._qualification(lot.qualification_id)
            key = (lot.ingredient_id, qualification.id, qualification.supplier_name)
            totals[key] = totals.get(key, 0) + share
    return tuple(
        MaterialDraw(ingredient, qualification, supplier, milligrams)
        for (ingredient, qualification, supplier), milligrams in sorted(totals.items())
    )


def _attribute(draw: int, consumptions: list[int], finished: int) -> list[int]:
    quotas: list[int] = []
    remainders: list[int] = []
    allocated = 0
    for used in consumptions:
        numer = draw * used
        quota = numer // finished
        quotas.append(quota)
        remainders.append(numer % finished)
        allocated += quota
    leftover = draw - allocated
    order = sorted(range(len(quotas)), key=lambda index: (-remainders[index], index))
    for index in order:
        if leftover == 0:
            break
        quotas[index] += 1
        leftover -= 1
    if leftover != 0:
        raise MetagraphError("material attribution did not conserve the sale")
    return quotas


def _sale_packaging(chain: Chain, fulfillment, formula, sold: int, specs: list[PackagingSpec]) -> tuple[PackagingDraw, ...]:
    totals: dict[tuple[str, str], tuple[int, int]] = {}
    saw_lot = False
    for draw in fulfillment.draws:
        batch = chain._batch(draw.batch_id)
        if not batch.packages:
            continue
        saw_lot = True
        finished = sum(item.milligrams for item in batch.consumptions)
        for use in batch.packages:
            lot = chain._package_lot(use.lot_id)
            numer, denom = _reduce(draw.milligrams * use.pieces, finished)
            key = (lot.component_id, lot.supplier_name)
            previous = totals.get(key, (0, 1))
            totals[key] = _add_fraction(previous[0], previous[1], numer, denom)
    if saw_lot:
        return tuple(
            PackagingDraw(component, numer, denom, supplier)
            for (component, supplier), (numer, denom) in sorted(totals.items())
            if numer
        )
    unit = sum(line.mg_per_unit for line in formula.lines)
    return tuple(_pieces(spec, sold, unit) for spec in specs)


def _pieces(spec: PackagingSpec, sold: int, unit: int) -> PackagingDraw:
    numer, denom = _reduce(sold * spec.pieces_per_unit, unit)
    return PackagingDraw(spec.id, numer, denom)


def _connect(chain: Chain, fulfillment, templates: Mapping[str, ConnectTemplate]) -> ConnectSplit | None:
    settlement = next(
        (item for item in chain.settlements if item.fulfillment_id == fulfillment.id),
        None,
    )
    if settlement is None:
        return None
    template_id = "practitioner" if fulfillment.kind == "treatment" else "outlet"
    template = templates[template_id]
    fee_bps = _fee_bps(template, templates)
    fee = settlement.amount_cents * fee_bps // 10_000
    return ConnectSplit(
        template.id,
        template.type_id,
        settlement.currency,
        fee,
        settlement.amount_cents - fee,
    )


def _fee_bps(template: ConnectTemplate, templates: Mapping[str, ConnectTemplate]) -> int:
    seen: set[str] = set()
    current: ConnectTemplate | None = template
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.fee_bps is not None:
            return current.fee_bps
        if current.extends is None:
            break
        current = templates.get(current.extends)
    raise MetagraphError(f"{template.id} does not extend a platform fee")


def _fibers_cover_stages(document: Document) -> None:
    from domain.supply_chain import load_stages

    stages = {stage.id for stage in load_stages()}
    fibers = {fiber.stage for fiber in document.fibers}
    if fibers != stages:
        missing = ", ".join(sorted(stages - fibers))
        extra = ", ".join(sorted(fibers - stages))
        raise MetagraphError(f"fibers must match stages (missing {missing or 'none'}, extra {extra or 'none'})")


def _types(raw: object) -> tuple[TypeNode, ...]:
    if not isinstance(raw, list) or not raw:
        raise MetagraphError("types must be a non-empty list")
    nodes: list[TypeNode] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise MetagraphError("each type must be an object")
        type_id = item.get("id")
        parents = item.get("parents")
        if not isinstance(type_id, str) or not type_id or type_id in seen:
            raise MetagraphError("each type needs a unique id")
        if not isinstance(parents, list) or not all(isinstance(parent, str) for parent in parents):
            raise MetagraphError(f"{type_id} parents must be a list of type ids")
        seen.add(type_id)
        nodes.append(TypeNode(type_id, tuple(parents)))
    known = {item.id for item in nodes}
    for item in nodes:
        for parent in item.parents:
            if parent not in known:
                raise MetagraphError(f"{item.id} parent {parent} is not a type")
    return tuple(nodes)


def _acyclic(types: tuple[TypeNode, ...]) -> None:
    by_id = {item.id: item for item in types}
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(type_id: str) -> None:
        if type_id in visited:
            return
        if type_id in visiting:
            raise MetagraphError(f"type cycle at {type_id}")
        visiting.add(type_id)
        for parent in by_id[type_id].parents:
            walk(parent)
        visiting.remove(type_id)
        visited.add(type_id)

    for item in types:
        walk(item.id)


def _templates(raw: object, types: set[str]) -> tuple[ConnectTemplate, ...]:
    if not isinstance(raw, list) or not raw:
        raise MetagraphError("connectTemplates must be a non-empty list")
    loaded: list[ConnectTemplate] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise MetagraphError("each connect template must be an object")
        template_id = item.get("id")
        type_id = item.get("type")
        charge = item.get("charge")
        extends = item.get("extends")
        fee = item.get("feeBps")
        if not isinstance(template_id, str) or not template_id or template_id in seen:
            raise MetagraphError("each connect template needs a unique id")
        if type_id not in types:
            raise MetagraphError(f"{template_id} type {type_id} is not a type")
        if not isinstance(charge, str) or not charge:
            raise MetagraphError(f"{template_id} needs a charge")
        if extends is not None and not isinstance(extends, str):
            raise MetagraphError(f"{template_id} extends must be a template id")
        if fee is not None and (isinstance(fee, bool) or not isinstance(fee, int) or fee < 0):
            raise MetagraphError(f"{template_id} feeBps must be a non-negative integer")
        seen.add(template_id)
        loaded.append(ConnectTemplate(template_id, str(type_id), charge, extends, fee))
    by_id = {item.id: item for item in loaded}
    roots = [item for item in loaded if item.extends is None]
    if len(roots) != 1 or roots[0].fee_bps is None:
        raise MetagraphError("one platform template sets feeBps and the others extend it")
    for item in loaded:
        if item.extends is not None and item.extends not in by_id:
            raise MetagraphError(f"{item.id} extends unknown template {item.extends}")
    return tuple(loaded)


def _packaging(raw: object) -> tuple[PackagingSpec, ...]:
    if not isinstance(raw, list):
        raise MetagraphError("packaging must be a list")
    loaded: list[PackagingSpec] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise MetagraphError("each packaging component must be an object")
        component_id = item.get("id")
        formula_id = item.get("formula_id")
        pieces = item.get("pieces_per_unit")
        if not isinstance(component_id, str) or not component_id or component_id in seen:
            raise MetagraphError("each packaging component needs a unique id")
        if not isinstance(formula_id, str) or not formula_id:
            raise MetagraphError(f"{component_id} needs a formula_id")
        if isinstance(pieces, bool) or not isinstance(pieces, int) or pieces < 1:
            raise MetagraphError(f"{component_id} pieces_per_unit must be a positive integer")
        seen.add(component_id)
        loaded.append(PackagingSpec(component_id, formula_id, pieces))
    return tuple(loaded)


def _fibers(raw: object, types: set[str]) -> tuple[Fiber, ...]:
    if not isinstance(raw, list) or not raw:
        raise MetagraphError("fibers must be a non-empty list")
    loaded: list[Fiber] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise MetagraphError("each fiber must be an object")
        stage = item.get("stage")
        type_id = item.get("type")
        side = item.get("side")
        if not isinstance(stage, str) or not stage or stage in seen:
            raise MetagraphError("each fiber needs a unique stage")
        if type_id not in types:
            raise MetagraphError(f"{stage} fiber type {type_id} is not a type")
        if side not in SIDES:
            raise MetagraphError(f"{stage} side must be supply, demand, or center")
        seen.add(stage)
        loaded.append(Fiber(stage, str(type_id), str(side)))
    return tuple(loaded)


def _add_fraction(an: int, ad: int, bn: int, bd: int) -> tuple[int, int]:
    return _reduce(an * bd + bn * ad, ad * bd)


def _reduce(numer: int, denom: int) -> tuple[int, int]:
    if denom < 1:
        raise MetagraphError("packaging denominator must be positive")
    divisor = gcd(numer, denom)
    return numer // divisor, denom // divisor


if __name__ == "__main__":
    main()
