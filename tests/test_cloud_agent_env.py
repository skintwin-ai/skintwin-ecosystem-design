"""Contract tests for the hub Cloud Agent environment."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parents[1]
ENV_JSON = HUB_ROOT / ".cursor" / "environment.json"
INSTALL_SCRIPT = HUB_ROOT / "scripts" / "cloud-agent-install.sh"
AGENTS_MD = HUB_ROOT / "AGENTS.md"
README_MD = HUB_ROOT / "README.md"

HUB_REPO = "skintwin-ecosystem-design"
EXPECTED_KEYS = {"name", "install", "repositoryDependencies"}
CPU_CORE_NAMES = (
    "skintwinnector",
    "skinport",
    "skintwin-customer-portal",
    "cognitive-architecture",
    "regima-platform",
    "skintwin-bot",
    "org-skin",
    "skintwin-integrations",
    "neuro-symbolic-core",
    "pcsdbx",
)
CHECKOUT_ONLY_SAMPLES = ("multiskin", "Yggdrasil", "llm-foundry")
EXPECTED_DEPENDENCIES = [
    "github.com/skintwin-ai/SolutionSpaceKernel",
    "github.com/skintwin-ai/Yggdrasil",
    "github.com/skintwin-ai/anycog",
    "github.com/skintwin-ai/cognitive-architecture",
    "github.com/skintwin-ai/ecosystem-bridge",
    "github.com/skintwin-ai/esm",
    "github.com/skintwin-ai/gnu_gneuralnetwork",
    "github.com/skintwin-ai/llm-foundry",
    "github.com/skintwin-ai/mini-swe-agent",
    "github.com/skintwin-ai/multiskin",
    "github.com/skintwin-ai/neuro-symbolic-core",
    "github.com/skintwin-ai/ojskin",
    "github.com/skintwin-ai/openapi-skintwin",
    "github.com/skintwin-ai/org-analysis",
    "github.com/skintwin-ai/org-skin",
    "github.com/skintwin-ai/pcsdbx",
    "github.com/skintwin-ai/regima-persistence-docs",
    "github.com/skintwin-ai/regima-platform",
    "github.com/skintwin-ai/regima-train-nnllms",
    "github.com/skintwin-ai/regima-training-lms",
    "github.com/skintwin-ai/regima-website",
    "github.com/skintwin-ai/regular-polytope-networks",
    "github.com/skintwin-ai/skin-multiscale-model",
    "github.com/skintwin-ai/skin-zone",
    "github.com/skintwin-ai/skin7nn",
    "github.com/skintwin-ai/skincare-directory",
    "github.com/skintwin-ai/skincare-salon-app",
    "github.com/skintwin-ai/skinform",
    "github.com/skintwin-ai/skinport",
    "github.com/skintwin-ai/skinsource-pro",
    "github.com/skintwin-ai/skinsuitesdk",
    "github.com/skintwin-ai/skintwin",
    "github.com/skintwin-ai/skintwin-asi",
    "github.com/skintwin-ai/skintwin-backend-paphos",
    "github.com/skintwin-ai/skintwin-bot",
    "github.com/skintwin-ai/skintwin-customer-portal",
    "github.com/skintwin-ai/skintwin-integrations",
    "github.com/skintwin-ai/skintwin-salon",
    "github.com/skintwin-ai/skintwind",
    "github.com/skintwin-ai/skintwinnector",
]


class CloudAgentEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = json.loads(ENV_JSON.read_text())
        self.script = INSTALL_SCRIPT.read_text()
        self.agents = AGENTS_MD.read_text()
        self.readme = README_MD.read_text()

    def test_environment_json_exact_keys(self) -> None:
        self.assertEqual(set(self.env.keys()), EXPECTED_KEYS)
        self.assertEqual(self.env["install"], "./scripts/cloud-agent-install.sh")
        self.assertEqual(self.env["name"], "skintwin-ai org ecosystem")

    def test_repository_dependencies(self) -> None:
        deps = self.env["repositoryDependencies"]
        self.assertEqual(deps, EXPECTED_DEPENDENCIES)
        self.assertEqual(len(deps), 40)
        self.assertEqual(len(set(deps)), 40)
        hub = f"github.com/skintwin-ai/{HUB_REPO}"
        self.assertNotIn(hub, deps)
        for url in deps:
            self.assertTrue(url.startswith("github.com/skintwin-ai/"))

    def test_install_script_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(INSTALL_SCRIPT)], check=True)

    def test_install_script_is_executable(self) -> None:
        self.assertTrue(os.access(INSTALL_SCRIPT, os.X_OK))

    def test_skip_missing_with_empty_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["CLOUD_AGENT_REPO_ROOTS"] = tmp
            completed = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(HUB_ROOT),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for name in CPU_CORE_NAMES:
            self.assertIn(f"[skip] {name}: not present", completed.stdout)
        self.assertIn("[done] SkinTwin-AI ecosystem install", completed.stdout)
        self.assertNotIn("[node]", completed.stdout)
        self.assertNotIn("[py]", completed.stdout)

    def test_lockfile_policy_and_no_runners(self) -> None:
        self.assertIn("corepack pnpm install --frozen-lockfile", self.script)
        self.assertIn("corepack yarn install --frozen-lockfile", self.script)
        self.assertIn("npm ci", self.script)
        self.assertNotIn("pnpm-workspace.yaml", self.script)
        self.assertNotRegex(self.script, r"(?m)^\s*pytest\b")
        self.assertNotIn("vitest", self.script)
        self.assertNotIn("pnpm test", self.script)
        self.assertNotIn("npm test", self.script)
        self.assertIn(
            'install_python_editable neuro-symbolic-core -e "./packages/nettica" -e "./packages/neuro-symbolic-hybrid" pytest',
            self.script,
        )

    def test_checkout_only_repos_are_not_install_targets(self) -> None:
        for name in CHECKOUT_ONLY_SAMPLES:
            self.assertNotRegex(
                self.script,
                rf"install_(?:node_repo|python_editable)\s+{re.escape(name)}\b",
            )

    def test_script_does_not_source_secrets(self) -> None:
        self.assertNotIn("source .env", self.script)
        self.assertNotIn(".env", self.script)
        self.assertNotIn(".pem", self.script)
        self.assertNotIn("STRIPE", self.script)
        self.assertNotIn("MONGO", self.script)

    def test_orientation_docs(self) -> None:
        combined = f"{self.agents}\n{self.readme}"
        self.assertIn("skip", combined.lower())
        self.assertIn("CPU-core", combined)
        self.assertIn("checkout-only", combined)
        self.assertIn("skintwin-ecosystem-design", combined)
        self.assertIn("run application tests", self.agents)
        self.assertIn("Do not commit snapshot IDs", self.agents)
        self.assertIn(".venv", self.agents)
        self.assertIn("dist/entry.js", self.agents)


if __name__ == "__main__":
    unittest.main()
