"""Supply-chain ledger: stage ownership and a full lot-to-outcome walk."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parents[1]
if str(HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(HUB_ROOT))

from domain.model import load_registry  # noqa: E402
from domain.platform import (  # noqa: E402
    CLEANSER_FULFILLMENT,
    REFERENCE_COMMANDS,
    RETAIL_FULFILLMENT,
    TREATMENT_FULFILLMENT,
    load_products,
    run as run_platform,
)
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
        self.assertEqual(manufacture.owner, "skinform")
        outcome = next(stage for stage in self.stages if stage.id == "outcome")
        self.assertEqual(outcome.owner, "skintwin")
        self.assertEqual(outcome.surface_owner, "skintwin-customer-portal")
        from domain.platform import verify_surfaces

        verify_surfaces(self.registry)

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
        with self.assertRaises(ChainError):
            self.chain.manufacture(
                "batch-too-many-bottles",
                "sku-serum-c",
                1,
                (
                    ("ascorbic", "lot-ascorbic", 10_000),
                    ("hyaluronic", "lot-hyaluronic", 500),
                ),
                (("bottle-30", "lot-bottle", 3),),
            )
        self.assertEqual(self.chain.package_remaining("lot-bottle"), 2)

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

    def test_owner_entries_reject_bad_payloads_and_run_the_serum(self) -> None:
        from domain import dispatch

        calls: list[str] = []
        real = dispatch.accept

        def wrapped(command: str, args: dict) -> dict:
            calls.append(command)
            return real(command, args)

        dispatch.accept = wrapped
        try:
            with self.assertRaises(ChainError):
                Chain().specify_ingredient("water", "Aqua", "not-a-cas")
            walked = reference_serum()
        finally:
            dispatch.accept = real
        self.assertEqual(walked.trace("order-treatment")["outcome"], 81)
        self.assertEqual(set(calls), set(COMMAND_STAGE))
        for stage in self.stages:
            self.assertTrue(stage.entry.endswith((".py", ".mjs")))

    def test_owner_commands_share_one_replayable_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "supply-chain.jsonl"
            env = os.environ.copy()
            env["SKINTWIN_CHAIN_LEDGER"] = str(ledger)
            env["SKINTWIN_HUB_ROOT"] = str(HUB_ROOT)
            env.pop("SKINTWIN_CHAIN_SKIP_DISPATCH", None)
            from domain.platform import run_owner

            refused = run_owner(
                "record_outcome",
                {
                    "outcome_id": "too-soon",
                    "fulfillment_id": "missing",
                    "concern": "dryness",
                    "score": 1,
                },
                env,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse(ledger.exists())
            chain = run_platform(ledger)
        self.assertEqual(chain.trace(TREATMENT_FULFILLMENT)["outcome"], 81)
        self.assertEqual(chain.trace(RETAIL_FULFILLMENT)["ingredients"], ("ascorbic", "hyaluronic"))
        self.assertEqual(chain.trace(RETAIL_FULFILLMENT)["outcome"], 72)
        self.assertEqual(chain.trace(TREATMENT_FULFILLMENT)["practitioner"], "aya")
        self.assertEqual(chain.lot_remaining("lot-ascorbic"), 30_000)
        self.assertEqual(chain.lot_remaining("lot-hyaluronic"), 4_000)
        cleanser = chain.trace(CLEANSER_FULFILLMENT)
        self.assertEqual(cleanser["ingredients"], ("glycerin",))
        self.assertEqual(cleanser["lots"], ("lot-glycerin",))
        self.assertEqual(cleanser["batches"], ("batch-cleanser",))
        self.assertEqual(cleanser["kind"], "retail")
        self.assertEqual(cleanser["location"], "johannesburg")
        self.assertEqual(cleanser["settlement"], "pay-cleanser")
        self.assertEqual(cleanser["outcome"], 64)
        self.assertEqual(chain.lot_remaining("lot-glycerin"), 12_000)
        self.assertEqual(chain.balance("sku-cleanser", "batch-cleanser", PLANT), 0)
        self.assertEqual(
            chain.balance("sku-cleanser", "batch-cleanser", "johannesburg"), 4_000
        )
        self.assertEqual(chain.balance("sku-serum-c", "batch-1", PLANT), 10_500)
        self.assertEqual(chain.balance("sku-serum-c", "batch-1", "cape-town"), 3_500)
        self.assertEqual(chain.package_remaining("lot-bottle"), 2)
        self.assertEqual(chain.package_remaining("lot-tube"), 2)
        from domain.metagraph import project

        self.assertEqual(
            project(chain).packaging_demand(),
            (
                ("bottle-30", "Cape Glass", 2, 3),
                ("tube-cleanser", "Joburg Tubes", 1, 2),
            ),
        )
        self.assertEqual(
            sum(movement.milligrams for movement in chain.movements),
            18_000,
        )
        self.assertEqual(
            [record[0] for record in REFERENCE_COMMANDS].count("manufacture"),
            1,
        )

    def test_operations_list_every_product_the_platform_walks(self) -> None:
        products = load_products()
        self.assertEqual([product.id for product in products], ["serum-c", "cleanser"])
        self.assertEqual(products[0].traces, (RETAIL_FULFILLMENT, TREATMENT_FULFILLMENT))
        self.assertEqual(products[1].traces, (CLEANSER_FULFILLMENT,))
        called = {stage_id for product in products for stage_id, _args in product.calls}
        self.assertEqual(called, {stage.id for stage in self.stages})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operations.json"
            path.write_text(json.dumps({"products": [{"id": "x", "traces": ["a"], "calls": [{"stage": "nope", "args": []}]}]}))
            with self.assertRaises(ChainError):
                load_products(path)

    def test_stage_owners_read_the_hub_from_the_registry(self) -> None:
        import importlib.util
        import subprocess

        from domain.bootstrap import find_repo
        from domain.locate import checkout, ledger_file, module_hub, stage_entry

        previous_hub = os.environ.pop("SKINTWIN_HUB_ROOT", None)
        previous_roots = os.environ.pop("CLOUD_AGENT_REPO_ROOTS", None)
        try:
            self.assertEqual(module_hub(), HUB_ROOT)
            self.assertEqual(ledger_file(HUB_ROOT), HUB_ROOT / "var" / "supply-chain.jsonl")
            skinform = find_repo("skinform", self.registry)
            skintwin = find_repo("skintwin", self.registry)
            self.assertIsNotNone(skinform)
            self.assertIsNotNone(skintwin)
            self.assertEqual(checkout("skinform"), skinform)
            self.assertEqual(stage_entry("outcome"), skintwin / "chain_stage.py")
            self.assertEqual(stage_entry("manufacture"), skinform / "chain_stage.mjs")
            spec = importlib.util.spec_from_file_location(
                "skintwin_chain_locate", HUB_ROOT / "domain" / "locate.py"
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec and spec.loader)
            loaded = importlib.util.module_from_spec(spec)
            assert spec is not None and spec.loader is not None
            spec.loader.exec_module(loaded)
            self.assertEqual(loaded.stage_entry("outcome"), skintwin / "chain_stage.py")
            env = os.environ.copy()
            env.pop("SKINTWIN_HUB_ROOT", None)
            env.pop("CLOUD_AGENT_REPO_ROOTS", None)
            completed = subprocess.run(
                [
                    "node",
                    "-e",
                    "const locate = require('./domain/locate.cjs');"
                    "const entry = locate.stageEntry('outcome');"
                    "if (!entry || !entry.endsWith('/skintwin/chain_stage.py')) process.exit(1);"
                    "process.stdout.write(locate.hubRoot());",
                ],
                cwd=HUB_ROOT,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(Path(completed.stdout.strip()), HUB_ROOT)
            forbidden = (
                "skintwin-ecosystem-design",
                "/agent/repos/skintwin/chain_stage.py",
                "/workspace/repos/skintwin/chain_stage.py",
                "supply-chain.jsonl",
            )
            owners = (
                ("skinsource-pro", "backend/src/chain_commands.py", "locate.py"),
                ("skinform", "chain_stage.mjs", "locate.cjs"),
                ("skinform", "app/routes/api.supply-chain.ts", "useSharedLedger"),
                ("skintwin-customer-portal", "chain_stage.mjs", "locate.cjs"),
                ("skintwin-customer-portal", "outcome.mjs", "stageEntry"),
                ("skintwin-customer-portal", "server/supplyChain.ts", "useSharedLedger"),
                ("skintwin-salon", "chain_stage.mjs", "locate.cjs"),
                ("skintwin-salon", "src/api/dev-server.mjs", "useSharedLedger"),
                ("regima-training-lms", "chain_stage.mjs", "locate.cjs"),
                ("regima-training-lms", "server/routes.ts", "recordCertificate"),
                ("skintwin-integrations", "chain_stage.py", "locate.py"),
                ("skintwin-integrations", "AmazingSalonApp9ragbot3/app.py", "use_shared_ledger"),
                ("skintwin", "chain_stage.py", "locate.py"),
            )
            for name, relative, marker in owners:
                directory = find_repo(name, self.registry)
                self.assertIsNotNone(directory, name)
                assert directory is not None
                text = (directory / relative).read_text(encoding="utf-8")
                self.assertIn(marker, text, relative)
                if marker in {"locate.py", "locate.cjs"}:
                    self.assertIn("org-ecosystem.json", text, relative)
                for needle in forbidden:
                    self.assertNotIn(needle, text, f"{relative} hardcodes {needle}")
        finally:
            if previous_hub is None:
                os.environ.pop("SKINTWIN_HUB_ROOT", None)
            else:
                os.environ["SKINTWIN_HUB_ROOT"] = previous_hub
            if previous_roots is None:
                os.environ.pop("CLOUD_AGENT_REPO_ROOTS", None)
            else:
                os.environ["CLOUD_AGENT_REPO_ROOTS"] = previous_roots

    def test_a_rejected_command_list_appends_nothing(self) -> None:
        from domain.ledger import append_command, append_commands, replay

        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "supply-chain.jsonl"
            append_command(
                "specify_ingredient",
                {"ingredient_id": "glycerin", "inci": "Glycerin", "cas": "56-81-5"},
                ledger,
            )
            before = ledger.read_text(encoding="utf-8")
            with self.assertRaises(ChainError):
                append_commands(
                    [
                        {
                            "command": "define_formula",
                            "args": {
                                "formula_id": "cleanser",
                                "name": "Gentle cleanser",
                                "lines": [["glycerin", 8000]],
                            },
                        },
                        {
                            "command": "define_formula",
                            "args": {
                                "formula_id": "missing",
                                "name": "Missing",
                                "lines": [["not-an-ingredient", 1000]],
                            },
                        },
                    ],
                    ledger,
                )
            self.assertEqual(ledger.read_text(encoding="utf-8"), before)
            self.assertEqual(replay(ledger).formulas, ())

    def test_sales_project_to_supplier_and_packaging_demand(self) -> None:
        from domain.metagraph import ancestors, load_document, project

        document = load_document()
        self.assertIn("Supply", ancestors(document, "RawMaterial"))
        self.assertIn("Supply", ancestors(document, "Packaging"))
        self.assertIn("Demand", ancestors(document, "ProductSale"))
        self.assertIn("Demand", ancestors(document, "Treatment"))
        self.assertIn("Center", ancestors(document, "Formulation"))
        bowtie = project(self.chain, document)
        retail = next(sale for sale in bowtie.sales if sale.fulfillment_id == "order-retail")
        treatment = next(sale for sale in bowtie.sales if sale.fulfillment_id == "order-treatment")
        self.assertEqual(retail.type_id, "ProductSale")
        self.assertEqual(retail.outlet, "cape-town")
        self.assertEqual(
            tuple((item.ingredient_id, item.milligrams) for item in retail.materials),
            (("ascorbic", 4762), ("hyaluronic", 238)),
        )
        self.assertEqual(retail.packaging[0].component_id, "bottle-30")
        self.assertEqual(retail.packaging[0].supplier_name, "Cape Glass")
        self.assertEqual((retail.packaging[0].numerator, retail.packaging[0].denominator), (10, 21))
        self.assertEqual(self.chain.package_remaining("lot-bottle"), 2)
        self.assertEqual(treatment.type_id, "Treatment")
        self.assertEqual(
            tuple((item.ingredient_id, item.milligrams) for item in treatment.materials),
            (("ascorbic", 1905), ("hyaluronic", 95)),
        )
        self.assertEqual(
            (treatment.packaging[0].numerator, treatment.packaging[0].denominator),
            (4, 21),
        )
        self.assertEqual(sum(sale.milligrams for sale in bowtie.sales), 7_000)
        self.assertEqual(
            sum(milligrams for *_rest, milligrams in bowtie.supplier_demand()),
            7_000,
        )
        self.assertEqual(
            bowtie.supplier_demand(),
            (
                ("qual-ascorbic", "Cape Acids", "ascorbic", 6667),
                ("qual-hyaluronic", "Coastal Polymers", "hyaluronic", 333),
            ),
        )
        self.assertEqual(bowtie.packaging_demand(), (("bottle-30", "Cape Glass", 2, 3),))
        assert retail.connect is not None and treatment.connect is not None
        self.assertEqual(retail.connect.destination_role, "Outlet")
        self.assertEqual(retail.connect.platform_fee_cents, 462)
        self.assertEqual(retail.connect.destination_cents, 18_038)
        self.assertEqual(treatment.connect.destination_role, "Practitioner")
        self.assertEqual(treatment.connect.platform_fee_cents, 1_125)
        self.assertEqual(treatment.connect.destination_cents, 43_875)
        self.assertEqual(
            {fiber.stage for fiber in document.fibers},
            {stage.id for stage in self.stages},
        )

    def test_platform_refuses_a_ledger_that_already_has_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "supply-chain.jsonl"
            ledger.write_text("{}\n")
            with self.assertRaises(ChainError):
                run_platform(ledger)


if __name__ == "__main__":
    unittest.main()
