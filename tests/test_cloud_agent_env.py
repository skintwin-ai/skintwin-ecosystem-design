"""Contract tests for the hub Cloud Agent environment and domain registry."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parents[1]
if str(HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(HUB_ROOT))

from domain.model import DomainError, load_registry, parse_registry  # noqa: E402

ENV_JSON = HUB_ROOT / ".cursor" / "environment.json"
INSTALL_SCRIPT = HUB_ROOT / "scripts" / "cloud-agent-install.sh"
BOOTSTRAP = HUB_ROOT / "domain" / "bootstrap.py"
REGISTRY_JSON = HUB_ROOT / "domain" / "org-ecosystem.json"
AGENTS_MD = HUB_ROOT / "AGENTS.md"
README_MD = HUB_ROOT / "README.md"
AGENTS_DIR = HUB_ROOT / ".cursor" / "agents"

HUB_REPO = "skintwin-ecosystem-design"
EXPECTED_KEYS = {"name", "install", "repositoryDependencies"}
CHECKOUT_ONLY_SAMPLES = ("multiskin", "Yggdrasil", "llm-foundry")
REQUIRED_SUBAGENTS = (
    "org-cloud-env",
    "cpu-core-bootstrap",
    "hub-only-guard",
    "ecosystem-domain",
    "agents-memory-updater",
)


class CloudAgentEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry()
        self.env = json.loads(ENV_JSON.read_text())
        self.script = INSTALL_SCRIPT.read_text()
        self.bootstrap = BOOTSTRAP.read_text()
        self.agents = AGENTS_MD.read_text()
        self.readme = README_MD.read_text()

    def test_environment_json_exact_keys(self) -> None:
        self.assertEqual(set(self.env.keys()), EXPECTED_KEYS)
        self.assertEqual(self.env["install"], "./scripts/cloud-agent-install.sh")
        self.assertEqual(self.env["name"], "skintwin-ai org ecosystem")
        self.assertNotIn("$schema", self.env)

    def test_repository_dependencies(self) -> None:
        deps = self.env["repositoryDependencies"]
        self.assertEqual(deps, self.registry.sibling_github_urls())
        self.assertEqual(self.env, self.registry.environment_document())
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

    def test_install_script_delegates_to_registry(self) -> None:
        self.assertIn("domain/org-ecosystem.json", self.script)
        self.assertIn("python3 -m domain.bootstrap", self.script)
        self.assertIn("load_registry", self.bootstrap)
        self.assertIn("cpu_core", self.bootstrap)
        self.assertNotIn("start", json.dumps(self.env))
        self.assertNotIn("terminals", json.dumps(self.env))

    def test_skip_missing_with_empty_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["CLOUD_AGENT_REPO_ROOTS"] = tmp
            env["PYTHONPATH"] = str(HUB_ROOT)
            completed = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(HUB_ROOT),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for name in self.registry.cpu_core_names():
            self.assertIn(f"[skip] {name}: not present", completed.stdout)
        self.assertIn("[done] SkinTwin-AI ecosystem install", completed.stdout)
        self.assertNotIn("[node]", completed.stdout)
        self.assertNotIn("[py]", completed.stdout)

    def test_lockfile_policy_and_no_runners(self) -> None:
        self.assertIn('["corepack", "pnpm", "install", "--frozen-lockfile"]', self.bootstrap)
        self.assertIn('["corepack", "yarn", "install", "--frozen-lockfile"]', self.bootstrap)
        self.assertIn('["npm", "ci"]', self.bootstrap)
        self.assertNotIn("pnpm-workspace.yaml", self.script)
        self.assertNotIn("pnpm-workspace.yaml", self.bootstrap)
        self.assertNotRegex(self.script, r"(?m)^\s*pytest\b")
        self.assertNotRegex(self.bootstrap, r"(?m)^\s*pytest\b")
        self.assertNotIn("vitest", self.script)
        self.assertNotIn("vitest", self.bootstrap)
        self.assertNotIn("pnpm test", self.script)
        self.assertNotIn("npm test", self.script)
        nsc = self.registry.repo_by_name("neuro-symbolic-core")
        self.assertEqual(nsc.install_kind, "python-packages")
        self.assertEqual(
            nsc.editable_packages,
            ("./packages/nettica", "./packages/neuro-symbolic-hybrid"),
        )
        self.assertEqual(nsc.packages, ("pytest",))
        platform = self.registry.repo_by_name("regima-platform")
        self.assertEqual(platform.install_kind, "pnpm")
        self.assertIn("never-add-pnpm-workspace-yaml", platform.constraints)

    def test_checkout_only_repos_are_not_install_targets(self) -> None:
        core_names = set(self.registry.cpu_core_names())
        for name in CHECKOUT_ONLY_SAMPLES:
            self.assertNotIn(name, core_names)
            self.assertEqual(self.registry.repo_by_name(name).install_kind, "none")
            self.assertNotRegex(self.bootstrap, rf"\b{re.escape(name)}\b")

    def test_present_checkout_only_is_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            multi = root / "multiskin"
            multi.mkdir()
            (multi / "package.json").write_text('{"name":"multiskin"}')
            pcs = root / "pcsdbx"
            pcs.mkdir()
            (pcs / "README.md").write_text("stdlib")
            env = os.environ.copy()
            env["CLOUD_AGENT_REPO_ROOTS"] = tmp
            env["PYTHONPATH"] = str(HUB_ROOT)
            completed = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(HUB_ROOT),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("[node] multiskin", completed.stdout)
        self.assertNotIn("[py] multiskin", completed.stdout)
        self.assertIn("[ok] pcsdbx present", completed.stdout)
        self.assertNotIn("[skip] pcsdbx", completed.stdout)

    def test_script_does_not_source_secrets(self) -> None:
        combined = f"{self.script}\n{self.bootstrap}\n{REGISTRY_JSON.read_text()}"
        self.assertNotIn("source .env", combined)
        self.assertNotIn("load_dotenv", combined)
        self.assertNotIn('".env"', combined)
        self.assertNotIn("'.env'", combined)
        self.assertNotIn(".pem", combined)
        self.assertNotIn("STRIPE", combined)
        self.assertNotIn("MONGO", combined)

    def test_orientation_docs(self) -> None:
        combined = f"{self.agents}\n{self.readme}"
        self.assertIn("skip", combined.lower())
        self.assertIn("CPU-core", combined)
        self.assertIn("checkout-only", combined)
        self.assertIn("skintwin-ecosystem-design", combined)
        self.assertIn("domain/org-ecosystem.json", combined)
        self.assertIn("run application tests", self.agents)
        self.assertIn("Do not commit snapshot IDs", self.agents)
        self.assertIn(".venv", self.agents)
        self.assertIn("dist/entry.js", self.agents)

    def test_deferred_stacks_cannot_be_cpu_core(self) -> None:
        data = json.loads(REGISTRY_JSON.read_text())
        for repo in data["repos"]:
            if repo["name"] == "Yggdrasil":
                repo["role"] = "cpu-core"
                repo["installKind"] = "python-requirements"
                repo["requirementsFile"] = "requirements.txt"
                repo["installOrder"] = 99
                break
        with self.assertRaises(DomainError):
            parse_registry(data)

    def test_checkout_only_cannot_carry_an_install_kind(self) -> None:
        data = json.loads(REGISTRY_JSON.read_text())
        for repo in data["repos"]:
            if repo["name"] == "multiskin":
                repo["installKind"] = "pnpm"
                break
        with self.assertRaises(DomainError):
            parse_registry(data)

    def test_subagents_have_yaml_frontmatter(self) -> None:
        self.assertTrue(AGENTS_DIR.is_dir())
        found: set[str] = set()
        for path in sorted(AGENTS_DIR.glob("*.md")):
            text = path.read_text()
            self.assertTrue(text.startswith("---\n"), path)
            parts = text.split("---", 2)
            self.assertGreaterEqual(len(parts), 3, path)
            front = parts[1]
            name_match = re.search(r"^name:\s*([a-z0-9-]+)\s*$", front, re.M)
            desc_match = re.search(r"^description:\s*.+$", front, re.M)
            self.assertIsNotNone(name_match, path)
            self.assertIsNotNone(desc_match, path)
            name = name_match.group(1)
            found.add(name)
            self.assertEqual(path.name, f"{name}.md")
            self.assertIn("use proactively", front.lower())
            self.assertTrue(parts[2].strip())
        self.assertEqual(set(REQUIRED_SUBAGENTS), found)


if __name__ == "__main__":
    unittest.main()
