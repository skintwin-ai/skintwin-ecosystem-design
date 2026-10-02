"""Inventory consumer and analysis lockstep tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parents[1]
if str(HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(HUB_ROOT))

from domain.inventory import (  # noqa: E402
    ANALYSIS_PATH,
    GENERATED_MARKER,
    OUT_OF_SNAPSHOT_EXAMPLES,
    RETIRED_WORKSPACE_NAMES,
    analysis_is_current,
    build_inventory,
    render_repository_analysis,
    write_analysis,
)
from domain.model import load_registry  # noqa: E402

ANALYSIS_MD = HUB_ROOT / "analysis" / "repository_analysis.md"
AGENTS_MD = HUB_ROOT / "AGENTS.md"
README_MD = HUB_ROOT / "README.md"
INTEGRATION_MD = HUB_ROOT / "analysis" / "integration_mapping.md"


class InventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry()

    def test_analysis_is_registry_render(self) -> None:
        rendered = render_repository_analysis(self.registry)
        self.assertTrue(rendered.startswith("# SkinTwin-AI Repository Analysis\n"))
        self.assertIn(GENERATED_MARKER, rendered)
        self.assertEqual(ANALYSIS_MD.read_text(), rendered)
        self.assertTrue(analysis_is_current())
        self.assertEqual(ANALYSIS_PATH, ANALYSIS_MD)

    def test_analysis_lists_every_registry_sibling_and_hub(self) -> None:
        text = ANALYSIS_MD.read_text()
        self.assertIn(self.registry.hub.name, text)
        for repo in self.registry.repos:
            self.assertIn(f"| {repo.name} |", text)
            self.assertIn(f"| {repo.install_kind} |" if repo.is_cpu_core() else repo.name, text)
        self.assertIn("| yarn |", text)
        self.assertIn("| presence-only |", text)
        self.assertIn("never-add-pnpm-workspace-yaml", text)

    def test_analysis_keeps_retired_names_out_of_inventory_tables(self) -> None:
        text = ANALYSIS_MD.read_text()
        inventory, _, outside = text.partition("## Outside this Cloud Agent snapshot")
        self.assertTrue(outside)
        for name in RETIRED_WORKSPACE_NAMES:
            self.assertNotIn(f"| {name} |", inventory)
            self.assertIn(f"`{name}`", outside)
        for name in OUT_OF_SNAPSHOT_EXAMPLES:
            self.assertIn(f"`{name}`", outside)
        self.assertIn("`skincare-directory`", outside)

    def test_empty_roots_mark_every_sibling_undiscoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("CLOUD_AGENT_REPO_ROOTS")
            os.environ["CLOUD_AGENT_REPO_ROOTS"] = tmp
            try:
                report = build_inventory(self.registry)
            finally:
                if previous is None:
                    os.environ.pop("CLOUD_AGENT_REPO_ROOTS", None)
                else:
                    os.environ["CLOUD_AGENT_REPO_ROOTS"] = previous
        self.assertEqual(report.unregistered, ())
        self.assertEqual(report.kind_drift, ())
        self.assertEqual(report.checkout_only_installable, ())
        self.assertEqual(len(report.missing_discoverable), len(self.registry.repos))
        self.assertIsNone(report.hub_directory)

    def test_fixture_reports_kind_drift_and_unregistered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            platform = root / "regima-platform"
            platform.mkdir()
            (platform / "package.json").write_text('{"name":"regima-platform"}')
            salon = root / "skintwin-salon"
            salon.mkdir()
            (salon / "package.json").write_text('{"name":"skintwin-salon"}')
            (salon / "yarn.lock").write_text("")
            extra = root / "paperclip"
            extra.mkdir()
            (extra / "README.md").write_text("out of snapshot")
            unmarked = root / "gnu_gneuralnetwork"
            unmarked.mkdir()
            (unmarked / "README").write_text("autotools")
            previous = os.environ.get("CLOUD_AGENT_REPO_ROOTS")
            os.environ["CLOUD_AGENT_REPO_ROOTS"] = tmp
            try:
                report = build_inventory(self.registry)
            finally:
                if previous is None:
                    os.environ.pop("CLOUD_AGENT_REPO_ROOTS", None)
                else:
                    os.environ["CLOUD_AGENT_REPO_ROOTS"] = previous
        by_name = {item.name: item for item in report.siblings}
        self.assertEqual(report.unregistered, ("paperclip",))
        self.assertEqual(by_name["regima-platform"].role, "cpu-core")
        self.assertTrue(by_name["regima-platform"].discoverable)
        self.assertEqual(by_name["regima-platform"].missing_kind_files, ("pnpm-lock.yaml",))
        self.assertIn("regima-platform", report.kind_drift)
        self.assertEqual(by_name["skintwin-salon"].role, "checkout-only")
        self.assertTrue(by_name["skintwin-salon"].installable_checkout_only)
        self.assertEqual(by_name["skintwin-salon"].missing_kind_files, ())
        self.assertIsNotNone(by_name["gnu_gneuralnetwork"].directory)
        self.assertFalse(by_name["gnu_gneuralnetwork"].discoverable)
        self.assertIn("gnu_gneuralnetwork", report.unmarked_directories)

    def test_cli_check_and_write_analysis(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(HUB_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            env["CLOUD_AGENT_REPO_ROOTS"] = tmp
            check = subprocess.run(
                [sys.executable, "-m", "domain.inventory", "--check-analysis"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(HUB_ROOT),
            )
            self.assertEqual(check.returncode, 0, check.stderr)
            probe = subprocess.run(
                [sys.executable, "-m", "domain.inventory", "--json"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(HUB_ROOT),
            )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        payload = json.loads(probe.stdout)
        self.assertEqual(payload["hubName"], self.registry.hub.name)
        self.assertEqual(len(payload["siblings"]), 40)
        self.assertEqual(payload["unregistered"], [])
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "repository_analysis.md"
            stale.write_text("stale\n")
            write_analysis(stale, self.registry)
            self.assertTrue(analysis_is_current(stale, self.registry))

    def test_orientation_docs_point_at_inventory(self) -> None:
        combined = "\n".join(
            (
                AGENTS_MD.read_text(),
                README_MD.read_text(),
                INTEGRATION_MD.read_text(),
            )
        )
        self.assertIn("python3 -m domain.inventory", combined)
        self.assertIn("domain/org-ecosystem.json", combined)
        self.assertIn("skincare-directory", INTEGRATION_MD.read_text())
        self.assertIn("outside", INTEGRATION_MD.read_text().lower())


if __name__ == "__main__":
    unittest.main()
