"""Operable skincare supply chain. Stage ownership lives in supply-chain.json.

Quantities are integer milligrams. Stock and lot balances are derived from
append-only records, so a lot or location cannot go negative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from domain.model import Registry, load_registry

STAGES_FILENAME = "supply-chain.json"
DEFAULT_STAGES_PATH = Path(__file__).resolve().parent / STAGES_FILENAME
PLANT = "plant"
FulfillmentKind = Literal["retail", "treatment"]

COMMAND_STAGE = {
    "specify_ingredient": "specify",
    "qualify_supplier": "source",
    "receive_lot": "procure",
    "define_formula": "formulate",
    "manufacture": "manufacture",
    "catalog_sku": "catalog",
    "transfer": "distribute",
    "certify_practitioner": "certify",
    "fulfill": "fulfill",
    "settle": "account",
    "record_outcome": "outcome",
}


class ChainError(ValueError):
    """A supply-chain command violated an invariant."""


@dataclass(frozen=True)
class Stage:
    id: str
    owner: str
    artifact: str
    entry: str
    note: str = ""
    surface: str = ""
    marker: str = ""


@dataclass(frozen=True)
class Ingredient:
    id: str
    inci: str
    cas: str


@dataclass(frozen=True)
class Qualification:
    id: str
    supplier_name: str
    ingredient_id: str


@dataclass(frozen=True)
class Lot:
    id: str
    ingredient_id: str
    qualification_id: str
    milligrams: int


@dataclass(frozen=True)
class FormulaLine:
    ingredient_id: str
    mg_per_unit: int


@dataclass(frozen=True)
class Formula:
    id: str
    name: str
    lines: tuple[FormulaLine, ...]


@dataclass(frozen=True)
class Sku:
    id: str
    formula_id: str
    name: str


@dataclass(frozen=True)
class Consumption:
    lot_id: str
    milligrams: int


@dataclass(frozen=True)
class Batch:
    id: str
    sku_id: str
    formula_id: str
    units: int
    consumptions: tuple[Consumption, ...]


@dataclass(frozen=True)
class Movement:
    sku_id: str
    batch_id: str
    location: str
    milligrams: int
    ref: str


@dataclass(frozen=True)
class Certificate:
    id: str
    practitioner_id: str
    course: str


@dataclass(frozen=True)
class BatchDraw:
    batch_id: str
    milligrams: int


@dataclass(frozen=True)
class Fulfillment:
    id: str
    sku_id: str
    location: str
    kind: FulfillmentKind
    practitioner_id: str | None
    draws: tuple[BatchDraw, ...]


@dataclass(frozen=True)
class Settlement:
    id: str
    fulfillment_id: str
    amount_cents: int
    currency: str


@dataclass(frozen=True)
class Outcome:
    id: str
    fulfillment_id: str
    concern: str
    score: int


@dataclass(frozen=True)
class Chain:
    ingredients: tuple[Ingredient, ...] = ()
    qualifications: tuple[Qualification, ...] = ()
    lots: tuple[Lot, ...] = ()
    formulas: tuple[Formula, ...] = ()
    skus: tuple[Sku, ...] = ()
    batches: tuple[Batch, ...] = ()
    movements: tuple[Movement, ...] = ()
    certificates: tuple[Certificate, ...] = ()
    fulfillments: tuple[Fulfillment, ...] = ()
    settlements: tuple[Settlement, ...] = ()
    outcomes: tuple[Outcome, ...] = ()

    def specify_ingredient(self, ingredient_id: str, inci: str, cas: str) -> Chain:
        accepted = _accept(
            "specify_ingredient",
            {"ingredient_id": ingredient_id, "inci": inci, "cas": cas},
        )
        ingredient_id = str(accepted["ingredient_id"])
        inci = str(accepted["inci"])
        cas = str(accepted["cas"])
        _fresh_id(ingredient_id, self.ingredients)
        inci = _text(inci, "inci")
        cas = _text(cas, "cas")
        return replace(
            self,
            ingredients=self.ingredients + (Ingredient(ingredient_id, inci, cas),),
        )

    def qualify_supplier(
        self, qualification_id: str, supplier_name: str, ingredient_id: str
    ) -> Chain:
        accepted = _accept(
            "qualify_supplier",
            {
                "qualification_id": qualification_id,
                "supplier_name": supplier_name,
                "ingredient_id": ingredient_id,
            },
        )
        qualification_id = str(accepted["qualification_id"])
        supplier_name = str(accepted["supplier_name"])
        ingredient_id = str(accepted["ingredient_id"])
        _fresh_id(qualification_id, self.qualifications)
        self._ingredient(ingredient_id)
        supplier_name = _text(supplier_name, "supplier_name")
        return replace(
            self,
            qualifications=self.qualifications
            + (Qualification(qualification_id, supplier_name, ingredient_id),),
        )

    def receive_lot(
        self,
        lot_id: str,
        ingredient_id: str,
        qualification_id: str,
        milligrams: int,
    ) -> Chain:
        accepted = _accept(
            "receive_lot",
            {
                "lot_id": lot_id,
                "ingredient_id": ingredient_id,
                "qualification_id": qualification_id,
                "milligrams": milligrams,
            },
        )
        lot_id = str(accepted["lot_id"])
        ingredient_id = str(accepted["ingredient_id"])
        qualification_id = str(accepted["qualification_id"])
        milligrams = int(accepted["milligrams"])
        _fresh_id(lot_id, self.lots)
        _positive(milligrams, "lot milligrams")
        qualification = self._qualification(qualification_id)
        if qualification.ingredient_id != ingredient_id:
            raise ChainError(
                f"qualification {qualification_id} is not for ingredient {ingredient_id}"
            )
        return replace(
            self,
            lots=self.lots
            + (Lot(lot_id, ingredient_id, qualification_id, milligrams),),
        )

    def define_formula(
        self,
        formula_id: str,
        name: str,
        lines: Sequence[tuple[str, int]],
    ) -> Chain:
        accepted = _accept(
            "define_formula",
            {
                "formula_id": formula_id,
                "name": name,
                "lines": [list(line) for line in lines],
            },
        )
        formula_id = str(accepted["formula_id"])
        name = str(accepted["name"])
        lines = tuple((str(line[0]), int(line[1])) for line in accepted["lines"])
        _fresh_id(formula_id, self.formulas)
        name = _text(name, "formula name")
        if not lines:
            raise ChainError("formula requires at least one line")
        seen: set[str] = set()
        parsed: list[FormulaLine] = []
        for ingredient_id, mg_per_unit in lines:
            if ingredient_id in seen:
                raise ChainError(f"formula repeats ingredient {ingredient_id}")
            seen.add(ingredient_id)
            self._ingredient(ingredient_id)
            _positive(mg_per_unit, "mg_per_unit")
            parsed.append(FormulaLine(ingredient_id, mg_per_unit))
        return replace(
            self,
            formulas=self.formulas + (Formula(formula_id, name, tuple(parsed)),),
        )

    def catalog_sku(self, sku_id: str, formula_id: str, name: str) -> Chain:
        accepted = _accept(
            "catalog_sku",
            {"sku_id": sku_id, "formula_id": formula_id, "name": name},
        )
        sku_id = str(accepted["sku_id"])
        formula_id = str(accepted["formula_id"])
        name = str(accepted["name"])
        _fresh_id(sku_id, self.skus)
        self._formula(formula_id)
        name = _text(name, "sku name")
        return replace(self, skus=self.skus + (Sku(sku_id, formula_id, name),))

    def manufacture(
        self,
        batch_id: str,
        sku_id: str,
        units: int,
        allocations: Sequence[tuple[str, str, int]],
    ) -> Chain:
        accepted = _accept(
            "manufacture",
            {
                "batch_id": batch_id,
                "sku_id": sku_id,
                "units": units,
                "allocations": [list(item) for item in allocations],
            },
        )
        batch_id = str(accepted["batch_id"])
        sku_id = str(accepted["sku_id"])
        units = int(accepted["units"])
        allocations = tuple(
            (str(item[0]), str(item[1]), int(item[2])) for item in accepted["allocations"]
        )
        _fresh_id(batch_id, self.batches)
        _positive(units, "units")
        sku = self._sku(sku_id)
        formula = self._formula(sku.formula_id)
        if not allocations:
            raise ChainError("manufacture requires lot allocations")
        required = {
            line.ingredient_id: line.mg_per_unit * units for line in formula.lines
        }
        got: dict[str, int] = {}
        per_lot: dict[str, int] = {}
        consumptions: list[Consumption] = []
        for ingredient_id, lot_id, milligrams in allocations:
            _positive(milligrams, "allocation milligrams")
            lot = self._lot(lot_id)
            if lot.ingredient_id != ingredient_id:
                raise ChainError(f"lot {lot_id} is not ingredient {ingredient_id}")
            if ingredient_id not in required:
                raise ChainError(f"formula does not use ingredient {ingredient_id}")
            got[ingredient_id] = got.get(ingredient_id, 0) + milligrams
            per_lot[lot_id] = per_lot.get(lot_id, 0) + milligrams
            consumptions.append(Consumption(lot_id, milligrams))
        if got != required:
            raise ChainError(
                f"allocations {got} do not match formula requirement {required}"
            )
        for lot_id, used in per_lot.items():
            remaining = self.lot_remaining(lot_id)
            if used > remaining:
                raise ChainError(
                    f"lot {lot_id} has {remaining} mg, allocation needs {used} mg"
                )
        batch = Batch(
            batch_id,
            sku_id,
            formula.id,
            units,
            tuple(consumptions),
        )
        finished = sum(required.values())
        updated = replace(self, batches=self.batches + (batch,))
        return updated._move(sku_id, batch_id, PLANT, finished, batch_id)

    def transfer(
        self,
        transfer_id: str,
        sku_id: str,
        batch_id: str,
        source: str,
        destination: str,
        milligrams: int,
    ) -> Chain:
        accepted = _accept(
            "transfer",
            {
                "transfer_id": transfer_id,
                "sku_id": sku_id,
                "batch_id": batch_id,
                "source": source,
                "destination": destination,
                "milligrams": milligrams,
            },
        )
        transfer_id = str(accepted["transfer_id"])
        sku_id = str(accepted["sku_id"])
        batch_id = str(accepted["batch_id"])
        source = str(accepted["source"])
        destination = str(accepted["destination"])
        milligrams = int(accepted["milligrams"])
        _text(transfer_id, "transfer id")
        _text(source, "source")
        _text(destination, "destination")
        if source == destination:
            raise ChainError("transfer source and destination must differ")
        _positive(milligrams, "transfer milligrams")
        self._sku(sku_id)
        self._batch(batch_id)
        if self._batch(batch_id).sku_id != sku_id:
            raise ChainError(f"batch {batch_id} is not sku {sku_id}")
        moved = self._move(sku_id, batch_id, source, -milligrams, transfer_id)
        return moved._move(sku_id, batch_id, destination, milligrams, transfer_id)

    def certify_practitioner(
        self, certificate_id: str, practitioner_id: str, course: str
    ) -> Chain:
        accepted = _accept(
            "certify_practitioner",
            {
                "certificate_id": certificate_id,
                "practitioner_id": practitioner_id,
                "course": course,
            },
        )
        certificate_id = str(accepted["certificate_id"])
        practitioner_id = str(accepted["practitioner_id"])
        course = str(accepted["course"])
        _fresh_id(certificate_id, self.certificates)
        practitioner_id = _text(practitioner_id, "practitioner_id")
        course = _text(course, "course")
        return replace(
            self,
            certificates=self.certificates
            + (Certificate(certificate_id, practitioner_id, course),),
        )

    def fulfill(
        self,
        fulfillment_id: str,
        sku_id: str,
        location: str,
        milligrams: int,
        kind: FulfillmentKind,
        practitioner_id: str | None = None,
    ) -> Chain:
        accepted = _accept(
            "fulfill",
            {
                "fulfillment_id": fulfillment_id,
                "sku_id": sku_id,
                "location": location,
                "milligrams": milligrams,
                "kind": kind,
                "practitioner_id": practitioner_id,
            },
        )
        fulfillment_id = str(accepted["fulfillment_id"])
        sku_id = str(accepted["sku_id"])
        location = str(accepted["location"])
        milligrams = int(accepted["milligrams"])
        kind = accepted["kind"]
        practitioner_id = accepted.get("practitioner_id")
        _fresh_id(fulfillment_id, self.fulfillments)
        _text(location, "location")
        _positive(milligrams, "fulfillment milligrams")
        if kind not in ("retail", "treatment"):
            raise ChainError(f"unknown fulfillment kind {kind!r}")
        self._sku(sku_id)
        if kind == "treatment":
            practitioner_id = _text(practitioner_id or "", "practitioner_id")
            if not any(
                certificate.practitioner_id == practitioner_id
                for certificate in self.certificates
            ):
                raise ChainError(
                    f"practitioner {practitioner_id} has no certificate"
                )
        else:
            practitioner_id = None
        draws = self._fifo(sku_id, location, milligrams)
        updated = self
        for draw in draws:
            updated = updated._move(
                sku_id, draw.batch_id, location, -draw.milligrams, fulfillment_id
            )
        fulfillment = Fulfillment(
            fulfillment_id,
            sku_id,
            location,
            kind,
            practitioner_id,
            draws,
        )
        return replace(updated, fulfillments=updated.fulfillments + (fulfillment,))

    def settle(
        self,
        settlement_id: str,
        fulfillment_id: str,
        amount_cents: int,
        currency: str,
    ) -> Chain:
        accepted = _accept(
            "settle",
            {
                "settlement_id": settlement_id,
                "fulfillment_id": fulfillment_id,
                "amount_cents": amount_cents,
                "currency": currency,
            },
        )
        settlement_id = str(accepted["settlement_id"])
        fulfillment_id = str(accepted["fulfillment_id"])
        amount_cents = int(accepted["amount_cents"])
        currency = str(accepted["currency"])
        _fresh_id(settlement_id, self.settlements)
        self._fulfillment(fulfillment_id)
        if any(item.fulfillment_id == fulfillment_id for item in self.settlements):
            raise ChainError(f"fulfillment {fulfillment_id} is already settled")
        _positive(amount_cents, "amount_cents")
        currency = _text(currency, "currency")
        if len(currency) != 3 or not currency.isalpha():
            raise ChainError("currency must be a 3-letter code")
        return replace(
            self,
            settlements=self.settlements
            + (
                Settlement(
                    settlement_id,
                    fulfillment_id,
                    amount_cents,
                    currency.upper(),
                ),
            ),
        )

    def record_outcome(
        self, outcome_id: str, fulfillment_id: str, concern: str, score: int
    ) -> Chain:
        accepted = _accept(
            "record_outcome",
            {
                "outcome_id": outcome_id,
                "fulfillment_id": fulfillment_id,
                "concern": concern,
                "score": score,
            },
        )
        outcome_id = str(accepted["outcome_id"])
        fulfillment_id = str(accepted["fulfillment_id"])
        concern = str(accepted["concern"])
        score = int(accepted["score"])
        _fresh_id(outcome_id, self.outcomes)
        self._fulfillment(fulfillment_id)
        if any(item.fulfillment_id == fulfillment_id for item in self.outcomes):
            raise ChainError(f"fulfillment {fulfillment_id} already has an outcome")
        concern = _text(concern, "concern")
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
            raise ChainError("score must be an integer from 0 to 100")
        return replace(
            self,
            outcomes=self.outcomes
            + (Outcome(outcome_id, fulfillment_id, concern, score),),
        )

    def lot_remaining(self, lot_id: str) -> int:
        lot = self._lot(lot_id)
        used = sum(
            consumption.milligrams
            for batch in self.batches
            for consumption in batch.consumptions
            if consumption.lot_id == lot_id
        )
        return lot.milligrams - used

    def balance(self, sku_id: str, batch_id: str, location: str) -> int:
        return sum(
            movement.milligrams
            for movement in self.movements
            if movement.sku_id == sku_id
            and movement.batch_id == batch_id
            and movement.location == location
        )

    def trace(self, fulfillment_id: str) -> dict[str, Any]:
        fulfillment = self._fulfillment(fulfillment_id)
        sku = self._sku(fulfillment.sku_id)
        formula = self._formula(sku.formula_id)
        batch_ids = {draw.batch_id for draw in fulfillment.draws}
        batches = tuple(batch for batch in self.batches if batch.id in batch_ids)
        lot_ids = {
            consumption.lot_id
            for batch in batches
            for consumption in batch.consumptions
        }
        lots = tuple(lot for lot in self.lots if lot.id in lot_ids)
        qualification_ids = {lot.qualification_id for lot in lots}
        ingredient_ids = {line.ingredient_id for line in formula.lines}
        settlement = next(
            (item for item in self.settlements if item.fulfillment_id == fulfillment_id),
            None,
        )
        outcome = next(
            (item for item in self.outcomes if item.fulfillment_id == fulfillment_id),
            None,
        )
        return {
            "fulfillment": fulfillment.id,
            "kind": fulfillment.kind,
            "location": fulfillment.location,
            "sku": sku.id,
            "formula": formula.id,
            "ingredients": tuple(sorted(ingredient_ids)),
            "qualifications": tuple(sorted(qualification_ids)),
            "lots": tuple(lot.id for lot in lots),
            "batches": tuple(batch.id for batch in batches),
            "practitioner": fulfillment.practitioner_id,
            "settlement": None if settlement is None else settlement.id,
            "outcome": None if outcome is None else outcome.score,
        }

    def _move(
        self,
        sku_id: str,
        batch_id: str,
        location: str,
        milligrams: int,
        ref: str,
    ) -> Chain:
        if milligrams == 0:
            raise ChainError("movement milligrams cannot be zero")
        if milligrams < 0:
            available = self.balance(sku_id, batch_id, location)
            if available + milligrams < 0:
                raise ChainError(
                    f"{location} has {available} mg of batch {batch_id}, needs {-milligrams} mg"
                )
        movement = Movement(sku_id, batch_id, location, milligrams, ref)
        return replace(self, movements=self.movements + (movement,))

    def _fifo(self, sku_id: str, location: str, milligrams: int) -> tuple[BatchDraw, ...]:
        remaining = milligrams
        draws: list[BatchDraw] = []
        for batch in self.batches:
            if batch.sku_id != sku_id:
                continue
            available = self.balance(sku_id, batch.id, location)
            if available <= 0:
                continue
            take = min(available, remaining)
            draws.append(BatchDraw(batch.id, take))
            remaining -= take
            if remaining == 0:
                return tuple(draws)
        raise ChainError(
            f"{location} has insufficient {sku_id} stock; short {remaining} mg"
        )

    def _ingredient(self, ingredient_id: str) -> Ingredient:
        return _find(self.ingredients, ingredient_id, "ingredient")

    def _qualification(self, qualification_id: str) -> Qualification:
        return _find(self.qualifications, qualification_id, "qualification")

    def _lot(self, lot_id: str) -> Lot:
        return _find(self.lots, lot_id, "lot")

    def _formula(self, formula_id: str) -> Formula:
        return _find(self.formulas, formula_id, "formula")

    def _sku(self, sku_id: str) -> Sku:
        return _find(self.skus, sku_id, "sku")

    def _batch(self, batch_id: str) -> Batch:
        return _find(self.batches, batch_id, "batch")

    def _fulfillment(self, fulfillment_id: str) -> Fulfillment:
        return _find(self.fulfillments, fulfillment_id, "fulfillment")


def load_stages(
    registry: Registry | None = None, path: Path | None = None
) -> tuple[Stage, ...]:
    registry = registry or load_registry()
    stages_path = path or DEFAULT_STAGES_PATH
    data = json.loads(stages_path.read_text())
    raw_stages = data.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ChainError("stages must be a non-empty list")
    stages: list[Stage] = []
    seen_ids: set[str] = set()
    seen_artifacts: set[str] = set()
    known_owners = {registry.hub.name, *(repo.name for repo in registry.repos)}
    for raw in raw_stages:
        if not isinstance(raw, Mapping):
            raise ChainError("each stage must be an object")
        stage_id = _text(str(raw.get("id", "")), "stage id")
        owner = _text(str(raw.get("owner", "")), "stage owner")
        artifact = _text(str(raw.get("artifact", "")), "stage artifact")
        entry = _text(str(raw.get("entry", "")), "stage entry")
        surface = _text(str(raw.get("surface", "")), "stage surface")
        marker = _text(str(raw.get("marker", "")), "stage marker")
        note = raw.get("note") or ""
        if not isinstance(note, str):
            raise ChainError(f"{stage_id}: note must be a string")
        if stage_id in seen_ids:
            raise ChainError(f"duplicate stage {stage_id}")
        if artifact in seen_artifacts:
            raise ChainError(f"duplicate artifact {artifact}")
        if owner not in known_owners:
            raise ChainError(f"{stage_id}: owner {owner} is not a known repository")
        seen_ids.add(stage_id)
        seen_artifacts.add(artifact)
        stages.append(Stage(stage_id, owner, artifact, entry, note, surface, marker))
    commanded = set(COMMAND_STAGE.values())
    if seen_ids != commanded:
        missing = commanded - seen_ids
        extra = seen_ids - commanded
        raise ChainError(
            f"stage ids must match ledger commands; missing={sorted(missing)} extra={sorted(extra)}"
        )
    return tuple(stages)


def reference_serum() -> Chain:
    """One finished serum from INCI identity through a recorded skin outcome."""
    chain = Chain()
    chain = chain.specify_ingredient("ascorbic", "Ascorbic Acid", "50-81-7")
    chain = chain.specify_ingredient("hyaluronic", "Sodium Hyaluronate", "9067-32-7")
    chain = chain.qualify_supplier("qual-ascorbic", "Cape Acids", "ascorbic")
    chain = chain.qualify_supplier("qual-hyaluronic", "Coastal Polymers", "hyaluronic")
    chain = chain.receive_lot("lot-ascorbic", "ascorbic", "qual-ascorbic", 50_000)
    chain = chain.receive_lot("lot-hyaluronic", "hyaluronic", "qual-hyaluronic", 5_000)
    chain = chain.define_formula(
        "serum-c",
        "Vitamin C serum",
        (("ascorbic", 10_000), ("hyaluronic", 500)),
    )
    chain = chain.catalog_sku("sku-serum-c", "serum-c", "Vitamin C serum 10.5g")
    chain = chain.manufacture(
        "batch-1",
        "sku-serum-c",
        2,
        (
            ("ascorbic", "lot-ascorbic", 20_000),
            ("hyaluronic", "lot-hyaluronic", 1_000),
        ),
    )
    chain = chain.transfer(
        "xfer-cape-town",
        "sku-serum-c",
        "batch-1",
        PLANT,
        "cape-town",
        10_500,
    )
    chain = chain.certify_practitioner("cert-aya", "aya", "RegimA facial protocol")
    chain = chain.fulfill(
        "order-retail", "sku-serum-c", "cape-town", 5_000, "retail"
    )
    chain = chain.fulfill(
        "order-treatment",
        "sku-serum-c",
        "cape-town",
        2_000,
        "treatment",
        "aya",
    )
    chain = chain.settle("pay-retail", "order-retail", 18_500, "ZAR")
    chain = chain.settle("pay-treatment", "order-treatment", 45_000, "ZAR")
    chain = chain.record_outcome("outcome-retail", "order-retail", "dullness", 72)
    return chain.record_outcome(
        "outcome-treatment", "order-treatment", "pigmentation", 81
    )


def format_trace(chain: Chain, fulfillment_id: str) -> str:
    traced = chain.trace(fulfillment_id)
    lines = [f"{key}: {value}" for key, value in traced.items()]
    return "\n".join(lines)


def main() -> None:
    load_stages()
    chain = reference_serum()
    print(format_trace(chain, "order-retail"))
    print("---")
    print(format_trace(chain, "order-treatment"))


def _accept(command: str, args: dict[str, Any]) -> dict[str, Any]:
    import os

    if os.environ.get("SKINTWIN_CHAIN_SKIP_DISPATCH") == "1":
        return args
    from domain.dispatch import accept

    return accept(command, args)


def _text(value: str | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChainError(f"{label} is required")
    return value.strip()


def _positive(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ChainError(f"{label} must be a positive integer")


def _fresh_id(record_id: str, records: Sequence[Any]) -> None:
    record_id = _text(record_id, "id")
    if any(record.id == record_id for record in records):
        raise ChainError(f"id {record_id} already exists")


def _find(records: Sequence[Any], record_id: str, label: str) -> Any:
    for record in records:
        if record.id == record_id:
            return record
    raise ChainError(f"unknown {label} {record_id}")


if __name__ == "__main__":
    main()
