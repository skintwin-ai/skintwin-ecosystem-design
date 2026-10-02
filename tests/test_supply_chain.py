"""Supply-chain ledger: stage ownership and a full lot-to-outcome walk."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parents[1]
if str(HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(HUB_ROOT))

from domain.model import load_registry  # noqa: E402
from domain.supply_chain import (  # noqa: E402
    COMMAND_STAGE,
    PLANT,
    Chain,
    ChainError,
    load_stages,
    reference_serum,
)

STAGES_JSON = HUB_ROOT / "domain" / "supply-chain.json"


class SupplyChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry()
        self.stages = load_stages(self.registry)
        self.chain = reference_serum()

    def test_every_stage_has_one_command_and_a_known_owner(self) -> None:
        self.assertEqual(
            {stage.id for stage in self.stages},
            set(COMMAND_STAGE.values()),
        )
        known = {self.registry.hub.name, *(repo.name for repo in self.registry.repos)}
        owners = {stage.owner for stage in self.stages}
        self.assertTrue(owners <= known)
        self.assertIn("skinsource-pro", owners)
        self.assertIn("skinform", owners)
        self.assertIn("skintwin-customer-portal", owners)
        self.assertIn("skintwin-salon", owners)
        self.assertIn("regima-training-lms", owners)
        self.assertIn("skintwin-integrations", owners)
        self.assertIn("skintwin", owners)
        manufacture = next(stage for stage in self.stages if stage.id == "manufacture")
        self.assertEqual(manufacture.owner, self.registry.hub.name)

    def test_reference_serum_traces_both_fulfillments(self) -> None:
        retail = self.chain.trace("order-retail")
        treatment = self.chain.trace("order-treatment")
        self.assertEqual(retail["ingredients"], ("ascorbic", "hyaluronic"))
        self.assertEqual(retail["lots"], ("lot-ascorbic", "lot-hyaluronic"))
        self.assertEqual(retail["batches"], ("batch-1",))
        self.assertEqual(retail["kind"], "retail")
        self.assertEqual(retail["practitioner"], None)
        self.assertEqual(retail["settlement"], "pay-retail")
        self.assertEqual(retail["outcome"], 72)
        self.assertEqual(treatment["kind"], "treatment")
        self.assertEqual(treatment["practitioner"], "aya")
        self.assertEqual(treatment["outcome"], 81)
        self.assertEqual(self.chain.lot_remaining("lot-ascorbic"), 30_000)
        self.assertEqual(self.chain.lot_remaining("lot-hyaluronic"), 4_000)
        self.assertEqual(self.chain.balance("sku-serum-c", "batch-1", PLANT), 10_500)
        self.assertEqual(
            self.chain.balance("sku-serum-c", "batch-1", "cape-town"), 3_500
        )

    def test_mass_is_conserved(self) -> None:
        finished = 21_000
        held = sum(movement.milligrams for movement in self.chain.movements)
        fulfilled = sum(
            draw.milligrams
            for fulfillment in self.chain.fulfillments
            for draw in fulfillment.draws
        )
        self.assertEqual(held, finished - fulfilled)
        self.assertEqual(fulfilled, 7_000)

    def test_unknown_owner_and_missing_stage_fail_to_load(self) -> None:
        data = json.loads(STAGES_JSON.read_text())
        data["stages"][0]["owner"] = "not-a-repo"
        path = HUB_ROOT / "domain" / "_bad_owner.json"
        path.write_text(json.dumps(data))
        try:
            with self.assertRaises(ChainError):
                load_stages(self.registry, path)
        finally:
            path.unlink()
        data = json.loads(STAGES_JSON.read_text())
        data["stages"] = [
            stage for stage in data["stages"] if stage["id"] != "outcome"
        ]
        path.write_text(json.dumps(data))
        try:
            with self.assertRaises(ChainError):
                load_stages(self.registry, path)
        finally:
            path.unlink(missing_ok=True)

    def test_cannot_receive_or_manufacture_without_upstream_records(self) -> None:
        chain = Chain().specify_ingredient("ascorbic", "Ascorbic Acid", "50-81-7")
        with self.assertRaises(ChainError):
            chain.receive_lot("lot", "ascorbic", "missing", 10)
        chain = chain.qualify_supplier("qual", "Cape Acids", "ascorbic")
        chain = chain.receive_lot("lot", "ascorbic", "qual", 100)
        chain = chain.define_formula("formula", "Serum", (("ascorbic", 40),))
        chain = chain.catalog_sku("sku", "formula", "Serum")
        with self.assertRaises(ChainError):
            chain.manufacture("batch", "sku", 2, (("ascorbic", "lot", 100),))
        with self.assertRaises(ChainError):
            chain.manufacture("batch", "sku", 1, (("ascorbic", "lot", 10),))

    def test_stock_cannot_be_overdrawn(self) -> None:
        with self.assertRaises(ChainError):
            self.chain.transfer(
                "too-much", "sku-serum-c", "batch-1", PLANT, "johannesburg", 10_501
            )
        with self.assertRaises(ChainError):
            self.chain.fulfill(
                "too-much", "sku-serum-c", "cape-town", 3_501, "retail"
            )

    def test_treatment_requires_a_certificate_and_outcome_requires_fulfillment(self) -> None:
        bare = Chain()
        with self.assertRaises(ChainError):
            self.chain.fulfill(
                "uncertified",
                "sku-serum-c",
                "cape-town",
                100,
                "treatment",
                "no-one",
            )
        with self.assertRaises(ChainError):
            bare.record_outcome("outcome", "missing-order", "dryness", 10)
        with self.assertRaises(ChainError):
            bare.settle("pay", "missing-order", 100, "ZAR")
        with self.assertRaises(ChainError):
            self.chain.settle("again", "order-retail", 100, "ZAR")


if __name__ == "__main__":
    unittest.main()
