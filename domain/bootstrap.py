"""Install CPU-core siblings from the domain registry. Skip missing checkouts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from domain.model import NODE_KINDS, PYTHON_KINDS, Registry, Repo, load_registry

MARKER_FILES = ("package.json", "pyproject.toml", "requirements.txt", "README.md")


def default_repo_roots(registry: Registry) -> str:
    return ":".join(registry.search_roots)


def find_repo(name: str, registry: Registry) -> Path | None:
    override = os.environ.get("CLOUD_AGENT_REPO_ROOTS")
    roots = override if override is not None else default_repo_roots(registry)
    for raw in roots.split(":"):
        if not raw:
            continue
        directory = Path(raw) / name
        if directory.is_dir() and any((directory / marker).is_file() for marker in MARKER_FILES):
            return directory
    if override is None:
        workspace_pkg = Path("/workspace/package.json")
        if workspace_pkg.is_file() and f'"name": "{name}"' in workspace_pkg.read_text():
            return Path("/workspace")
    return None


def node_command(kind: str) -> list[str]:
    if kind == "pnpm":
        return ["corepack", "pnpm", "install", "--frozen-lockfile"]
    if kind == "yarn":
        return ["corepack", "yarn", "install", "--frozen-lockfile"]
    if kind == "npm":
        return ["npm", "ci"]
    raise ValueError(f"unsupported node kind {kind}")


def python_command(repo: Repo) -> list[str]:
    if repo.install_kind == "python-editable":
        return ["-e", str(repo.editable_spec)]
    if repo.install_kind == "python-requirements":
        return ["-r", str(repo.requirements_file)]
    if repo.install_kind == "python-packages":
        args: list[str] = []
        for spec in repo.editable_packages:
            args.extend(["-e", spec])
        args.extend(repo.packages)
        return args
    raise ValueError(f"unsupported python kind {repo.install_kind}")


def install_node(repo: Repo, directory: Path) -> None:
    print(f"[node] {repo.name} @ {directory}", flush=True)
    subprocess.run(node_command(repo.install_kind), cwd=directory, check=True)


def install_python(repo: Repo, directory: Path) -> None:
    print(f"[py] {repo.name} @ {directory}", flush=True)
    subprocess.run([sys.executable, "-m", "venv", ".venv"], cwd=directory, check=True)
    pip = directory / ".venv" / "bin" / "pip"
    subprocess.run(
        [str(pip), "install", "-U", "pip", "setuptools", "wheel"],
        cwd=directory,
        check=True,
    )
    subprocess.run([str(pip), "install", *python_command(repo)], cwd=directory, check=True)


def bootstrap_repo(repo: Repo, registry: Registry) -> None:
    directory = find_repo(repo.name, registry)
    if directory is None:
        print(f"[skip] {repo.name}: not present", flush=True)
        return
    kind = repo.install_kind
    if kind in NODE_KINDS:
        install_node(repo, directory)
        return
    if kind in PYTHON_KINDS:
        install_python(repo, directory)
        return
    if kind == "presence-only":
        note = repo.presence_note or "present"
        print(f"[ok] {repo.name} present at {directory} ({note})", flush=True)
        return
    raise ValueError(f"{repo.name}: unhandled install kind {kind}")


def main() -> int:
    registry = load_registry()
    for repo in registry.cpu_core():
        bootstrap_repo(repo, registry)
    print("[done] SkinTwin-AI ecosystem install", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
