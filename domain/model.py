"""Typed org-ecosystem registry. Invalid role/kind/stack combos cannot load."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

INSTALL_KINDS = (
    "pnpm",
    "yarn",
    "npm",
    "python-editable",
    "python-requirements",
    "python-packages",
    "presence-only",
    "none",
)
ROLES = ("hub", "cpu-core", "checkout-only")
NODE_KINDS = ("pnpm", "yarn", "npm")
PYTHON_KINDS = ("python-editable", "python-requirements", "python-packages")
DEFERRED_STACKS = frozenset({"gpu", "julia", "php"})
KNOWN_STACKS = frozenset(
    {"node", "python", "gpu", "julia", "php", "docs", "mixed"}
)
InstallKind = Literal[
    "pnpm",
    "yarn",
    "npm",
    "python-editable",
    "python-requirements",
    "python-packages",
    "presence-only",
    "none",
]
Role = Literal["hub", "cpu-core", "checkout-only"]

REGISTRY_FILENAME = "org-ecosystem.json"
HUB_DIR = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = HUB_DIR / REGISTRY_FILENAME

REPO_MARKERS = ("package.json", "pyproject.toml", "requirements.txt", "README.md")


class DomainError(ValueError):
    """Registry failed invariant checks."""


@dataclass(frozen=True)
class Hub:
    org: str
    name: str
    environment_name: str
    install: str
    environment_keys: tuple[str, ...]


@dataclass(frozen=True)
class Policies:
    skip_missing: bool
    frozen_lockfiles: bool
    hub_only_files: bool
    allow_start: bool
    allow_terminals: bool
    allow_live_secrets: bool
    allow_schema_key: bool
    allow_gpu_julia_php_default_install: bool
    never_add_pnpm_workspace_yaml_to: tuple[str, ...]
    do_not_fix_preexisting_sibling_bugs: tuple[str, ...]


@dataclass(frozen=True)
class Repo:
    name: str
    github: str
    role: Role
    install_kind: InstallKind
    stack: str
    install_order: int | None = None
    editable_spec: str | None = None
    requirements_file: str | None = None
    editable_packages: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    presence_note: str | None = None
    constraints: tuple[str, ...] = ()

    def is_cpu_core(self) -> bool:
        return self.role == "cpu-core"

    def is_checkout_only(self) -> bool:
        return self.role == "checkout-only"


@dataclass(frozen=True)
class Registry:
    hub: Hub
    policies: Policies
    search_roots: tuple[str, ...]
    repos: tuple[Repo, ...]

    def repo_by_name(self, name: str) -> Repo:
        for repo in self.repos:
            if repo.name == name:
                return repo
        raise KeyError(name)

    def cpu_core(self) -> tuple[Repo, ...]:
        cores = [repo for repo in self.repos if repo.is_cpu_core()]
        cores.sort(key=lambda repo: (repo.install_order is None, repo.install_order or 0))
        return tuple(cores)

    def checkout_only(self) -> tuple[Repo, ...]:
        return tuple(repo for repo in self.repos if repo.is_checkout_only())

    def sibling_github_urls(self) -> list[str]:
        return [repo.github for repo in self.repos]

    def cpu_core_names(self) -> tuple[str, ...]:
        return tuple(repo.name for repo in self.cpu_core())

    def environment_document(self) -> dict[str, Any]:
        return {
            "name": self.hub.environment_name,
            "install": self.hub.install,
            "repositoryDependencies": self.sibling_github_urls(),
        }


def load_registry(path: Path | None = None) -> Registry:
    registry_path = path or DEFAULT_REGISTRY_PATH
    data = json.loads(registry_path.read_text())
    return parse_registry(data)


def parse_registry(data: Mapping[str, Any]) -> Registry:
    hub = _parse_hub(data.get("hub"))
    policies = _parse_policies(data.get("policies"))
    roots = data.get("searchRoots")
    if not isinstance(roots, list) or not roots or not all(isinstance(item, str) for item in roots):
        raise DomainError("searchRoots must be a non-empty list of strings")
    raw_repos = data.get("repos")
    if not isinstance(raw_repos, list) or not raw_repos:
        raise DomainError("repos must be a non-empty list")
    repos = tuple(_parse_repo(item, hub, policies) for item in raw_repos)
    registry = Registry(
        hub=hub,
        policies=policies,
        search_roots=tuple(roots),
        repos=repos,
    )
    _validate_registry(registry)
    return registry


def _parse_hub(raw: Any) -> Hub:
    if not isinstance(raw, Mapping):
        raise DomainError("hub object is required")
    keys = raw.get("environmentKeys")
    if not isinstance(keys, list) or not all(isinstance(item, str) for item in keys):
        raise DomainError("hub.environmentKeys must be a list of strings")
    name = _req_str(raw, "name")
    org = _req_str(raw, "org")
    return Hub(
        org=org,
        name=name,
        environment_name=_req_str(raw, "environmentName"),
        install=_req_str(raw, "install"),
        environment_keys=tuple(keys),
    )


def _parse_policies(raw: Any) -> Policies:
    if not isinstance(raw, Mapping):
        raise DomainError("policies object is required")
    return Policies(
        skip_missing=_req_bool(raw, "skipMissing"),
        frozen_lockfiles=_req_bool(raw, "frozenLockfiles"),
        hub_only_files=_req_bool(raw, "hubOnlyFiles"),
        allow_start=_req_bool(raw, "allowStart"),
        allow_terminals=_req_bool(raw, "allowTerminals"),
        allow_live_secrets=_req_bool(raw, "allowLiveSecrets"),
        allow_schema_key=_req_bool(raw, "allowSchemaKey"),
        allow_gpu_julia_php_default_install=_req_bool(
            raw, "allowGpuJuliaPhpDefaultInstall"
        ),
        never_add_pnpm_workspace_yaml_to=_req_str_tuple(
            raw, "neverAddPnpmWorkspaceYamlTo"
        ),
        do_not_fix_preexisting_sibling_bugs=_req_str_tuple(
            raw, "doNotFixPreexistingSiblingBugs"
        ),
    )


def _parse_repo(raw: Any, hub: Hub, policies: Policies) -> Repo:
    if not isinstance(raw, Mapping):
        raise DomainError("each repo must be an object")
    name = _req_str(raw, "name")
    role = _req_str(raw, "role")
    kind = _req_str(raw, "installKind")
    stack = _req_str(raw, "stack")
    if role not in ROLES:
        raise DomainError(f"{name}: role {role!r} is not a known role")
    if kind not in INSTALL_KINDS:
        raise DomainError(f"{name}: installKind {kind!r} is not a known kind")
    if stack not in KNOWN_STACKS:
        raise DomainError(f"{name}: stack {stack!r} is not a known stack")
    if name == hub.name:
        raise DomainError("hub repository must not appear in sibling repos")
    install_order = raw.get("installOrder")
    if install_order is not None and not isinstance(install_order, int):
        raise DomainError(f"{name}: installOrder must be an int when set")
    editable_packages = tuple(raw.get("editablePackages") or ())
    packages = tuple(raw.get("packages") or ())
    constraints = tuple(raw.get("constraints") or ())
    if not all(isinstance(item, str) for item in (*editable_packages, *packages, *constraints)):
        raise DomainError(f"{name}: package and constraint lists must be strings")
    repo = Repo(
        name=name,
        github=_req_str(raw, "github"),
        role=role,  # type: ignore[arg-type]
        install_kind=kind,  # type: ignore[arg-type]
        stack=stack,
        install_order=install_order,
        editable_spec=raw.get("editableSpec"),
        requirements_file=raw.get("requirementsFile"),
        editable_packages=editable_packages,
        packages=packages,
        presence_note=raw.get("presenceNote"),
        constraints=constraints,
    )
    _validate_repo(repo, hub, policies)
    return repo


def _validate_repo(repo: Repo, hub: Hub, policies: Policies) -> None:
    expected_github = f"github.com/{hub.org}/{repo.name}"
    if repo.github != expected_github:
        raise DomainError(f"{repo.name}: github must be {expected_github!r}")
    if repo.role == "checkout-only" and repo.install_kind != "none":
        raise DomainError(f"{repo.name}: checkout-only repos must use installKind none")
    if repo.role == "cpu-core" and repo.install_kind == "none":
        raise DomainError(f"{repo.name}: cpu-core repos cannot use installKind none")
    if repo.role == "hub":
        raise DomainError(f"{repo.name}: hub role belongs on the hub object, not repos")
    if repo.install_kind == "none":
        if repo.install_order is not None:
            raise DomainError(f"{repo.name}: checkout-only repos cannot have installOrder")
        if repo.editable_spec or repo.requirements_file or repo.editable_packages or repo.packages:
            raise DomainError(f"{repo.name}: none install cannot carry python install fields")
    if repo.install_kind in NODE_KINDS:
        if not policies.frozen_lockfiles:
            raise DomainError("node installs require policies.frozenLockfiles")
        if repo.editable_spec or repo.requirements_file or repo.editable_packages or repo.packages:
            raise DomainError(f"{repo.name}: node install cannot carry python fields")
        if repo.install_order is None:
            raise DomainError(f"{repo.name}: cpu-core node install requires installOrder")
    if repo.install_kind == "python-editable":
        if not repo.editable_spec:
            raise DomainError(f"{repo.name}: python-editable requires editableSpec")
        if repo.requirements_file or repo.editable_packages or repo.packages:
            raise DomainError(f"{repo.name}: python-editable cannot mix other python fields")
        if repo.install_order is None:
            raise DomainError(f"{repo.name}: cpu-core python install requires installOrder")
    if repo.install_kind == "python-requirements":
        if not repo.requirements_file:
            raise DomainError(f"{repo.name}: python-requirements requires requirementsFile")
        if repo.editable_spec or repo.editable_packages or repo.packages:
            raise DomainError(
                f"{repo.name}: python-requirements cannot mix other python fields"
            )
        if repo.install_order is None:
            raise DomainError(f"{repo.name}: cpu-core python install requires installOrder")
    if repo.install_kind == "python-packages":
        if not repo.editable_packages and not repo.packages:
            raise DomainError(f"{repo.name}: python-packages requires packages")
        if repo.editable_spec or repo.requirements_file:
            raise DomainError(f"{repo.name}: python-packages cannot mix other python fields")
        if repo.install_order is None:
            raise DomainError(f"{repo.name}: cpu-core python install requires installOrder")
    if repo.install_kind == "presence-only":
        if repo.install_order is None:
            raise DomainError(f"{repo.name}: presence-only requires installOrder")
        if repo.editable_spec or repo.requirements_file or repo.editable_packages or repo.packages:
            raise DomainError(f"{repo.name}: presence-only cannot carry install payloads")
    if repo.stack in DEFERRED_STACKS:
        if policies.allow_gpu_julia_php_default_install:
            raise DomainError("allowGpuJuliaPhpDefaultInstall must stay false")
        if repo.role != "checkout-only" or repo.install_kind != "none":
            raise DomainError(
                f"{repo.name}: gpu/julia/php stacks cannot be default-installed"
            )
    if "never-add-pnpm-workspace-yaml" in repo.constraints:
        if repo.install_kind != "pnpm":
            raise DomainError(
                f"{repo.name}: never-add-pnpm-workspace-yaml only applies to pnpm"
            )


def _validate_registry(registry: Registry) -> None:
    names = [repo.name for repo in registry.repos]
    githubs = [repo.github for repo in registry.repos]
    if len(names) != len(set(names)):
        raise DomainError("duplicate repo names")
    if len(githubs) != len(set(githubs)):
        raise DomainError("duplicate github urls")
    if registry.hub.name in names:
        raise DomainError("hub must not be listed as a sibling")
    keys = registry.hub.environment_keys
    if tuple(keys) != ("name", "install", "repositoryDependencies"):
        raise DomainError("environment keys must be exactly name, install, repositoryDependencies")
    if registry.policies.allow_schema_key:
        raise DomainError("environment.json must not allow $schema")
    if registry.policies.allow_start or registry.policies.allow_terminals:
        raise DomainError("start/terminals are not part of this environment")
    if registry.policies.allow_live_secrets:
        raise DomainError("live secrets are not part of this environment")
    if not registry.policies.skip_missing:
        raise DomainError("skip-missing is required")
    if not registry.policies.hub_only_files:
        raise DomainError("hub-only file policy is required")
    if not registry.policies.frozen_lockfiles:
        raise DomainError("frozen lockfiles are required")
    cores = registry.cpu_core()
    if not cores:
        raise DomainError("cpu-core set is empty")
    orders = [repo.install_order for repo in cores]
    if None in orders or len(set(orders)) != len(orders):
        raise DomainError("cpu-core installOrder values must be unique ints")
    named = {repo.name for repo in registry.repos}
    for extra in registry.policies.never_add_pnpm_workspace_yaml_to:
        if extra not in named:
            raise DomainError(f"neverAddPnpmWorkspaceYamlTo unknown repo {extra}")
        repo = registry.repo_by_name(extra)
        if "never-add-pnpm-workspace-yaml" not in repo.constraints:
            raise DomainError(f"{extra} must declare never-add-pnpm-workspace-yaml")


def default_search_roots(registry: Registry) -> tuple[str, ...]:
    return registry.search_roots


def _req_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise DomainError(f"{key} must be a non-empty string")
    return value


def _req_bool(raw: Mapping[str, Any], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise DomainError(f"{key} must be a boolean")
    return value


def _req_str_tuple(raw: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DomainError(f"{key} must be a list of strings")
    return tuple(value)
