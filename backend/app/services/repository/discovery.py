import datetime
import json
import logging
import os
import re
import tomllib
import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveryRun, DiscoveryStatus
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.schemas.discovery import (
    ApiContractFinding,
    ConfigurationFinding,
    DependencyFinding,
    DeploymentFinding,
    DiscoveryResult,
    EntrypointFinding,
    Evidence,
    FrameworkFinding,
    ModuleFinding,
    RouteFinding,
)
from app.services.repository.acquisition import acquisition_service
from app.services.repository.workspace import workspace_manager

logger = logging.getLogger(__name__)

# Files / directories to skip during deep recursive inspection
IGNORE_DIR_NAMES: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
}

# Extension to language mapping
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".php": "PHP",
    ".rb": "Ruby",
    ".cs": "C#",
    ".cpp": "C/C++",
    ".c": "C/C++",
    ".h": "C/C++",
}

MAX_FILE_SIZE_FOR_INSPECTION = 1024 * 1024  # 1 MB limit for static AST/regex analysis


class SnapshotNotReadyError(Exception):
    """Raised when attempting discovery on a snapshot that is not in READY status."""


class RepositoryDiscoveryService:
    async def run_discovery(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        repository: Repository,
        snapshot: RepositorySnapshot,
        user_id: uuid.UUID | None = None,
    ) -> DiscoveryRun:
        """
        Executes static, deterministic, read-only contract & architecture discovery
        against an immutable, acquired RepositorySnapshot workspace.
        """
        if snapshot.status != SnapshotStatus.READY:
            raise SnapshotNotReadyError(
                f"Cannot run discovery on snapshot with status '{snapshot.status}'. "
                "Snapshot must be in 'READY' status."
            )

        run = DiscoveryRun(
            snapshot_id=snapshot.id,
            status=DiscoveryStatus.RUNNING,
            started_at=datetime.datetime.now(datetime.UTC),
            metadata_={},
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        # Record audit event: discovery started
        await acquisition_service.record_audit(
            db,
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            event_type="repository.discovery.started",
            resource_id=run.id,
            payload={
                "snapshot_id": str(snapshot.id),
                "commit_sha": snapshot.commit_sha,
                "repository_id": str(repository.id),
            },
        )
        await db.commit()

        workspace_path = workspace_manager.get_workspace_path(
            organization_id, project_id, snapshot.id
        )

        if not workspace_path.exists():
            run.status = DiscoveryStatus.FAILED
            run.completed_at = datetime.datetime.now(datetime.UTC)
            run.error_code = "WORKSPACE_NOT_FOUND"
            run.error_message = f"Snapshot workspace directory not found at {workspace_path.name}."
            await db.commit()

            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.discovery.failed",
                resource_id=run.id,
                payload={"error_code": run.error_code, "error_message": run.error_message},
            )
            await db.commit()
            return run

        try:
            real_workspace = workspace_path.resolve()
            workspace_manager.assert_path_contained(workspace_path, workspace_path)

            # Discover all components
            result = self._inspect_workspace(real_workspace, repository, snapshot)

            run.metadata_ = result.model_dump(mode="json")
            run.status = DiscoveryStatus.COMPLETED
            run.completed_at = datetime.datetime.now(datetime.UTC)
            run.error_code = None
            run.error_message = None
            await db.commit()
            await db.refresh(run)

            # Record audit event: discovery completed
            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.discovery.completed",
                resource_id=run.id,
                payload={
                    "snapshot_id": str(snapshot.id),
                    "commit_sha": snapshot.commit_sha,
                    "frameworks_count": len(result.frameworks),
                    "entrypoints_count": len(result.entrypoints),
                    "routes_count": len(result.routes),
                    "contracts_count": len(result.api_contracts),
                    "dependencies_count": len(result.dependencies),
                    "modules_count": len(result.modules),
                    "configurations_count": len(result.configurations),
                    "deployment_count": len(result.deployment),
                },
            )
            await db.commit()
            return run

        except Exception as exc:
            logger.exception("Unexpected error during discovery execution")
            run.status = DiscoveryStatus.FAILED
            run.completed_at = datetime.datetime.now(datetime.UTC)
            run.error_code = "DISCOVERY_EXECUTION_ERROR"
            run.error_message = str(exc)
            await db.commit()

            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.discovery.failed",
                resource_id=run.id,
                payload={"error_code": run.error_code, "error_message": str(exc)},
            )
            await db.commit()
            return run

    def _inspect_workspace(
        self,
        real_workspace: Path,
        repository: Repository,
        snapshot: RepositorySnapshot,
    ) -> DiscoveryResult:
        """
        Pure deterministic inspection of the local workspace.
        """
        manifest_files: list[Path] = []
        source_files: list[Path] = []
        contract_files: list[Path] = []
        config_files: list[tuple[Path, str, bool]] = []
        deployment_files: list[Path] = []
        all_dirs: list[Path] = []

        # 1. Walk directory tree safely
        for root, dirs, files in os.walk(real_workspace):
            root_path = Path(root)

            # Filter out ignored directories
            dirs[:] = [
                d
                for d in dirs
                if d not in IGNORE_DIR_NAMES
                and not (root_path / d).is_symlink()
                or (
                    (root_path / d).is_symlink()
                    and (root_path / d).resolve().is_relative_to(real_workspace)
                )
            ]

            for d in dirs:
                dir_path = root_path / d
                if not dir_path.is_symlink() or dir_path.resolve().is_relative_to(real_workspace):
                    all_dirs.append(dir_path)

            for f in files:
                file_path = root_path / f
                if file_path.is_symlink():
                    try:
                        resolved = file_path.resolve()
                        if not resolved.is_relative_to(real_workspace):
                            continue
                    except (OSError, RuntimeError):
                        continue

                f_lower = f.lower()
                rel_parts = file_path.relative_to(real_workspace).parts

                # Manifests
                if f in {
                    "pyproject.toml",
                    "requirements.txt",
                    "package.json",
                    "composer.json",
                    "Cargo.toml",
                    "go.mod",
                    "Pipfile",
                }:
                    manifest_files.append(file_path)

                # API Contracts
                if f_lower in {
                    "openapi.yaml",
                    "openapi.yml",
                    "openapi.json",
                    "swagger.yaml",
                    "swagger.yml",
                    "swagger.json",
                } or (
                    ("openapi" in f_lower or "swagger" in f_lower)
                    and f_lower.endswith((".yaml", ".yml", ".json"))
                ):
                    contract_files.append(file_path)

                # Configuration
                config_info = self._classify_config(file_path, real_workspace)
                if config_info:
                    config_files.append(config_info)

                # Deployment
                if f in {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "fly.toml", "Procfile", "vercel.json"} or len(rel_parts) >= 2 and rel_parts[0] == ".github" and rel_parts[1] == "workflows" and f_lower.endswith((".yml", ".yaml")):
                    deployment_files.append(file_path)

                # Source code files
                if file_path.suffix.lower() in EXTENSION_LANGUAGE_MAP:
                    source_files.append(file_path)

        # 2. Extract findings
        dependencies = self._extract_dependencies(manifest_files, real_workspace)
        frameworks = self._extract_frameworks(manifest_files, source_files, dependencies, real_workspace)
        entrypoints = self._extract_entrypoints(source_files, real_workspace)
        routes = self._extract_routes(source_files, real_workspace)
        api_contracts = self._extract_contracts(contract_files, real_workspace)
        modules = self._extract_modules(all_dirs, real_workspace)
        configurations = [
            ConfigurationFinding(
                file=f.relative_to(real_workspace).as_posix(),
                category=cat,
                sensitive=is_sens,
            )
            for f, cat, is_sens in config_files
        ]
        deployment = self._extract_deployment(deployment_files, real_workspace)

        # 3. Sort deterministically
        return DiscoveryResult(
            snapshot_id=snapshot.id,
            commit_sha=snapshot.commit_sha or "",
            repository={
                "name": repository.name,
                "default_branch": repository.default_branch,
            },
            frameworks=sorted(frameworks, key=lambda x: x.name.lower()),
            entrypoints=sorted(entrypoints, key=lambda x: (x.path, x.symbol, x.framework)),
            routes=sorted(routes, key=lambda x: (x.path, x.method, x.source_file, x.source_line or 0)),
            api_contracts=sorted(api_contracts, key=lambda x: x.file),
            dependencies=sorted(dependencies, key=lambda x: (x.name.lower(), x.manifest_file, x.is_dev)),
            modules=sorted(modules, key=lambda x: x.path),
            configurations=sorted(configurations, key=lambda x: x.file),
            deployment=sorted(deployment, key=lambda x: x.file),
        )

    def _classify_config(self, file_path: Path, real_workspace: Path) -> tuple[Path, str, bool] | None:
        """Classify configuration files and identify sensitivity without reading sensitive contents."""
        name = file_path.name

        # Sensitive environment variables (.env, .env.local, etc.)
        if name == ".env" or name.startswith(".env."):
            return (file_path, "environment", True)

        # Tooling and linters
        if name in {"tsconfig.json", "jsconfig.json"} or name.startswith("tsconfig."):
            return (file_path, "typescript", False)
        if name in {"ruff.toml", ".ruff.toml", "biome.json"} or name.startswith((".eslintrc", ".prettierrc")):
            return (file_path, "linter", False)
        if name in {"pytest.ini", "setup.cfg"} or name.startswith(("jest.config.", "vitest.config.")):
            return (file_path, "testing", False)
        if name.startswith(("tailwind.config.", "postcss.config.")):
            return (file_path, "styling", False)
        if name in {"alembic.ini"}:
            return (file_path, "database", False)
        if name.endswith((".config.js", ".config.ts", ".config.mjs")):
            return (file_path, "tooling", False)

        return None

    def _extract_dependencies(
        self, manifest_files: list[Path], real_workspace: Path
    ) -> list[DependencyFinding]:
        dependencies: list[DependencyFinding] = []

        for m in manifest_files:
            rel_path = m.relative_to(real_workspace).as_posix()
            name = m.name

            try:
                if m.stat().st_size > MAX_FILE_SIZE_FOR_INSPECTION:
                    continue
                content = m.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if name == "package.json":
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        deps = data.get("dependencies", {})
                        if isinstance(deps, dict):
                            for k, v in deps.items():
                                dependencies.append(
                                    DependencyFinding(
                                        name=k,
                                        version_spec=str(v) if v else None,
                                        manifest_file=rel_path,
                                        is_dev=False,
                                    )
                                )
                        dev_deps = data.get("devDependencies", {})
                        if isinstance(dev_deps, dict):
                            for k, v in dev_deps.items():
                                dependencies.append(
                                    DependencyFinding(
                                        name=k,
                                        version_spec=str(v) if v else None,
                                        manifest_file=rel_path,
                                        is_dev=True,
                                    )
                                )
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    logger.debug("Failed parsing package.json %s: %s", rel_path, exc)

            elif name == "pyproject.toml":
                try:
                    data = tomllib.loads(content)
                    # PEP 621 project.dependencies
                    project = data.get("project", {})
                    if isinstance(project, dict):
                        for dep_str in project.get("dependencies", []):
                            dep_name, dep_spec = self._parse_python_dependency_string(str(dep_str))
                            dependencies.append(
                                DependencyFinding(
                                    name=dep_name,
                                    version_spec=dep_spec,
                                    manifest_file=rel_path,
                                    is_dev=False,
                                )
                            )
                        opt_deps = project.get("optional-dependencies", {})
                        if isinstance(opt_deps, dict):
                            for group_deps in opt_deps.values():
                                for dep_str in group_deps:
                                    dep_name, dep_spec = self._parse_python_dependency_string(str(dep_str))
                                    dependencies.append(
                                        DependencyFinding(
                                            name=dep_name,
                                            version_spec=dep_spec,
                                            manifest_file=rel_path,
                                            is_dev=True,
                                        )
                                    )
                    # Poetry tool.poetry.dependencies
                    tool = data.get("tool", {})
                    if isinstance(tool, dict):
                        poetry = tool.get("poetry", {})
                        if isinstance(poetry, dict):
                            p_deps = poetry.get("dependencies", {})
                            if isinstance(p_deps, dict):
                                for k, v in p_deps.items():
                                    if k.lower() != "python":
                                        dependencies.append(
                                            DependencyFinding(
                                                name=k,
                                                version_spec=str(v) if isinstance(v, str) else None,
                                                manifest_file=rel_path,
                                                is_dev=False,
                                            )
                                        )
                            # Poetry dev dependencies
                            p_dev = poetry.get("dev-dependencies", {})
                            if isinstance(p_dev, dict):
                                for k, v in p_dev.items():
                                    dependencies.append(
                                        DependencyFinding(
                                            name=k,
                                            version_spec=str(v) if isinstance(v, str) else None,
                                            manifest_file=rel_path,
                                            is_dev=True,
                                        )
                                    )
                except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as exc:
                    logger.debug("Failed parsing pyproject.toml %s: %s", rel_path, exc)

            elif name == "requirements.txt":
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith(("#", "-")):
                        continue
                    dep_name, dep_spec = self._parse_python_dependency_string(line)
                    if dep_name:
                        dependencies.append(
                            DependencyFinding(
                                name=dep_name,
                                version_spec=dep_spec,
                                manifest_file=rel_path,
                                is_dev=False,
                            )
                        )

            elif name == "composer.json":
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        req = data.get("require", {})
                        if isinstance(req, dict):
                            for k, v in req.items():
                                dependencies.append(
                                    DependencyFinding(
                                        name=k,
                                        version_spec=str(v) if v else None,
                                        manifest_file=rel_path,
                                        is_dev=False,
                                    )
                                )
                        req_dev = data.get("require-dev", {})
                        if isinstance(req_dev, dict):
                            for k, v in req_dev.items():
                                dependencies.append(
                                    DependencyFinding(
                                        name=k,
                                        version_spec=str(v) if v else None,
                                        manifest_file=rel_path,
                                        is_dev=True,
                                    )
                                )
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    logger.debug("Failed parsing composer.json %s: %s", rel_path, exc)

            elif name == "Cargo.toml":
                try:
                    data = tomllib.loads(content)
                    for k, v in data.get("dependencies", {}).items():
                        dependencies.append(
                            DependencyFinding(
                                name=k,
                                version_spec=str(v) if isinstance(v, str) else None,
                                manifest_file=rel_path,
                                is_dev=False,
                            )
                        )
                    for k, v in data.get("dev-dependencies", {}).items():
                        dependencies.append(
                            DependencyFinding(
                                name=k,
                                version_spec=str(v) if isinstance(v, str) else None,
                                manifest_file=rel_path,
                                is_dev=True,
                            )
                        )
                except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as exc:
                    logger.debug("Failed parsing Cargo.toml %s: %s", rel_path, exc)

        return dependencies

    def _parse_python_dependency_string(self, dep_str: str) -> tuple[str, str | None]:
        clean = dep_str.split(";")[0].strip()
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:\[.*?\])?\s*([<>=!~^].*)?$", clean)
        if match:
            name = match.group(1).strip()
            spec = match.group(2).strip() if match.group(2) else None
            return name, spec
        return clean, None

    def _extract_frameworks(
        self,
        manifest_files: list[Path],
        source_files: list[Path],
        dependencies: list[DependencyFinding],
        real_workspace: Path,
    ) -> list[FrameworkFinding]:
        framework_map: dict[str, FrameworkFinding] = {}

        # 1. Match from dependencies
        dep_lookup = {d.name.lower(): d for d in dependencies}

        checks = [
            ("fastapi", "FastAPI"),
            ("flask", "Flask"),
            ("django", "Django"),
            ("next", "Next.js"),
            ("react", "React"),
            ("express", "Express"),
            ("@nestjs/core", "NestJS"),
            ("laravel/framework", "Laravel"),
        ]

        for dep_key, fw_name in checks:
            if dep_key in dep_lookup:
                d = dep_lookup[dep_key]
                fw = framework_map.setdefault(
                    fw_name,
                    FrameworkFinding(name=fw_name, version=d.version_spec, evidence=[]),
                )
                if not fw.version and d.version_spec:
                    fw.version = d.version_spec
                fw.evidence.append(
                    Evidence(
                        file=d.manifest_file,
                        reason=f"Declared dependency '{d.name}' found in {d.manifest_file}",
                    )
                )

        # 2. Structural/source heuristics if manifest didn't specify
        for s in source_files:
            rel_path = s.relative_to(real_workspace).as_posix()
            try:
                if s.stat().st_size > MAX_FILE_SIZE_FOR_INSPECTION:
                    continue
                content = s.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if "from fastapi import" in content or "import fastapi" in content:
                fw = framework_map.setdefault(
                    "FastAPI",
                    FrameworkFinding(name="FastAPI", version=None, evidence=[]),
                )
                if len(fw.evidence) < 5:
                    fw.evidence.append(
                        Evidence(
                            file=rel_path,
                            reason=f"FastAPI import found in {rel_path}",
                        )
                    )

            if "from flask import" in content or "import flask" in content:
                fw = framework_map.setdefault(
                    "Flask",
                    FrameworkFinding(name="Flask", version=None, evidence=[]),
                )
                if len(fw.evidence) < 5:
                    fw.evidence.append(
                        Evidence(
                            file=rel_path,
                            reason=f"Flask import found in {rel_path}",
                        )
                    )

            if "from django" in content or "import django" in content or s.name == "manage.py":
                fw = framework_map.setdefault(
                    "Django",
                    FrameworkFinding(name="Django", version=None, evidence=[]),
                )
                if len(fw.evidence) < 5:
                    fw.evidence.append(
                        Evidence(
                            file=rel_path,
                            reason=f"Django signature found in {rel_path}",
                        )
                    )

        return list(framework_map.values())

    def _extract_entrypoints(
        self, source_files: list[Path], real_workspace: Path
    ) -> list[EntrypointFinding]:
        entrypoints: list[EntrypointFinding] = []

        for s in source_files:
            rel_path = s.relative_to(real_workspace).as_posix()
            try:
                if s.stat().st_size > MAX_FILE_SIZE_FOR_INSPECTION:
                    continue
                content = s.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            # Python: FastAPI & Flask
            for line_no, line in enumerate(content.splitlines(), start=1):
                fastapi_match = re.search(r"^\s*([a-zA-Z0-9_]+)\s*=\s*(?:fastapi\.)?FastAPI\(", line)
                if fastapi_match:
                    symbol = fastapi_match.group(1)
                    entrypoints.append(
                        EntrypointFinding(
                            path=rel_path,
                            symbol=symbol,
                            framework="FastAPI",
                            type="web_application",
                            evidence=[
                                Evidence(
                                    file=rel_path,
                                    line=line_no,
                                    symbol=symbol,
                                    reason=f"FastAPI application instantiated as '{symbol}'",
                                )
                            ],
                        )
                    )

                flask_match = re.search(r"^\s*([a-zA-Z0-9_]+)\s*=\s*(?:flask\.)?Flask\(", line)
                if flask_match:
                    symbol = flask_match.group(1)
                    entrypoints.append(
                        EntrypointFinding(
                            path=rel_path,
                            symbol=symbol,
                            framework="Flask",
                            type="web_application",
                            evidence=[
                                Evidence(
                                    file=rel_path,
                                    line=line_no,
                                    symbol=symbol,
                                    reason=f"Flask application instantiated as '{symbol}'",
                                )
                            ],
                        )
                    )

                # JS/TS: Express
                express_match = re.search(r"(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*express\(", line)
                if express_match:
                    symbol = express_match.group(1)
                    entrypoints.append(
                        EntrypointFinding(
                            path=rel_path,
                            symbol=symbol,
                            framework="Express",
                            type="web_application",
                            evidence=[
                                Evidence(
                                    file=rel_path,
                                    line=line_no,
                                    symbol=symbol,
                                    reason=f"Express application instantiated as '{symbol}'",
                                )
                            ],
                        )
                    )

                # JS/TS: NestJS
                if "NestFactory.create" in line:
                    entrypoints.append(
                        EntrypointFinding(
                            path=rel_path,
                            symbol="bootstrap",
                            framework="NestJS",
                            type="web_application",
                            evidence=[
                                Evidence(
                                    file=rel_path,
                                    line=line_no,
                                    symbol="bootstrap",
                                    reason="NestFactory bootstrap entrypoint found",
                                )
                            ],
                        )
                    )

            # Python: Django manage.py
            if s.name == "manage.py" and ("DJANGO_SETTINGS_MODULE" in content or "execute_from_command_line" in content):
                entrypoints.append(
                    EntrypointFinding(
                        path=rel_path,
                        symbol="execute_from_command_line",
                        framework="Django",
                        type="cli_entrypoint",
                        evidence=[
                            Evidence(
                                file=rel_path,
                                symbol="execute_from_command_line",
                                reason="Django CLI management entrypoint",
                            )
                        ],
                    )
                )

            # Next.js page entrypoint
            if s.name in {"page.tsx", "page.jsx", "page.js", "index.tsx", "index.jsx", "index.js"}:
                parts = Path(rel_path).parts
                if "app" in parts or "pages" in parts or "frontend" in parts or "src" in parts:
                    entrypoints.append(
                        EntrypointFinding(
                            path=rel_path,
                            symbol="Page",
                            framework="Next.js",
                            type="page_entrypoint",
                            evidence=[
                                Evidence(
                                    file=rel_path,
                                    symbol="Page",
                                    reason="Next.js routed page entrypoint",
                                )
                            ],
                        )
                    )

        return entrypoints

    def _extract_routes(
        self, source_files: list[Path], real_workspace: Path
    ) -> list[RouteFinding]:
        routes: list[RouteFinding] = []

        for s in source_files:
            rel_path = s.relative_to(real_workspace).as_posix()
            try:
                if s.stat().st_size > MAX_FILE_SIZE_FOR_INSPECTION:
                    continue
                content = s.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            lines = content.splitlines()

            # Python files (FastAPI, Flask, Django)
            if s.suffix == ".py":
                for i, line in enumerate(lines):
                    # FastAPI route decorators: @app.get("/items"), @router.post("/users")
                    fastapi_match = re.search(
                        r"@(?:[a-zA-Z0-9_]+\.)?(get|post|put|delete|patch|options|head)\s*\(\s*([\"'])(.*?)\2",
                        line,
                    )
                    if fastapi_match:
                        method = fastapi_match.group(1).upper()
                        route_path = fastapi_match.group(3)
                        handler = "anonymous"
                        # Look ahead for def handler(...)
                        for next_line in lines[i + 1 : min(i + 5, len(lines))]:
                            fn_match = re.search(r"def\s+([a-zA-Z0-9_]+)\s*\(", next_line)
                            if fn_match:
                                handler = fn_match.group(1)
                                break
                        routes.append(
                            RouteFinding(
                                method=method,
                                path=route_path,
                                handler=handler,
                                framework="FastAPI",
                                source_file=rel_path,
                                source_line=i + 1,
                                evidence=[
                                    Evidence(
                                        file=rel_path,
                                        line=i + 1,
                                        reason=f"FastAPI @route({method} '{route_path}') decorator",
                                    )
                                ],
                            )
                        )

                    # Flask route decorators: @app.route("/items", methods=["GET", "POST"])
                    flask_match = re.search(
                        r"@(?:[a-zA-Z0-9_]+\.)?route\s*\(\s*([\"'])(.*?)\1(?:,\s*methods\s*=\s*\[(.*?)\])?",
                        line,
                    )
                    if flask_match:
                        route_path = flask_match.group(2)
                        methods_str = flask_match.group(3)
                        if methods_str:
                            extracted_methods = re.findall(r"[\"']([A-Z]+)[\"']", methods_str)
                        else:
                            extracted_methods = ["GET"]

                        handler = "anonymous"
                        for next_line in lines[i + 1 : min(i + 5, len(lines))]:
                            fn_match = re.search(r"def\s+([a-zA-Z0-9_]+)\s*\(", next_line)
                            if fn_match:
                                handler = fn_match.group(1)
                                break

                        for m in extracted_methods:
                            routes.append(
                                RouteFinding(
                                    method=m.upper(),
                                    path=route_path,
                                    handler=handler,
                                    framework="Flask",
                                    source_file=rel_path,
                                    source_line=i + 1,
                                    evidence=[
                                        Evidence(
                                            file=rel_path,
                                            line=i + 1,
                                            reason=f"Flask @route({m} '{route_path}')",
                                        )
                                    ],
                                )
                            )

                    # Django urls.py: path("api/v1/users/", views.users_view)
                    if s.name == "urls.py":
                        django_match = re.search(
                            r"path\s*\(\s*([\"'])(.*?)\1\s*,\s*([a-zA-Z0-9_\.]+)",
                            line,
                        )
                        if django_match:
                            route_path = "/" + django_match.group(2).lstrip("/")
                            handler = django_match.group(3)
                            routes.append(
                                RouteFinding(
                                    method="ALL",
                                    path=route_path,
                                    handler=handler,
                                    framework="Django",
                                    source_file=rel_path,
                                    source_line=i + 1,
                                    evidence=[
                                        Evidence(
                                            file=rel_path,
                                            line=i + 1,
                                            reason=f"Django path pattern '{route_path}' -> {handler}",
                                        )
                                    ],
                                )
                            )

            # JS/TS files (Express)
            elif s.suffix in {".js", ".ts"}:
                for i, line in enumerate(lines):
                    express_match = re.search(
                        r"(?:app|router)\.(get|post|put|delete|patch|options|head)\s*\(\s*([\"'])(.*?)\2",
                        line,
                    )
                    if express_match:
                        method = express_match.group(1).upper()
                        route_path = express_match.group(3)
                        handler = "anonymous"
                        fn_match = re.search(r",\s*([a-zA-Z0-9_]+)\s*(?:\)|,)", line)
                        if fn_match:
                            handler = fn_match.group(1)
                        routes.append(
                            RouteFinding(
                                method=method,
                                path=route_path,
                                handler=handler,
                                framework="Express",
                                source_file=rel_path,
                                source_line=i + 1,
                                evidence=[
                                    Evidence(
                                        file=rel_path,
                                        line=i + 1,
                                        reason=f"Express {method} '{route_path}' definition",
                                    )
                                ],
                            )
                        )

        return routes

    def _extract_contracts(
        self, contract_files: list[Path], real_workspace: Path
    ) -> list[ApiContractFinding]:
        contracts: list[ApiContractFinding] = []

        for c in contract_files:
            rel_path = c.relative_to(real_workspace).as_posix()
            try:
                if c.stat().st_size > MAX_FILE_SIZE_FOR_INSPECTION:
                    contracts.append(
                        ApiContractFinding(
                            file=rel_path,
                            format="OpenAPI",
                            status="INVALID",
                            error_message="File size exceeds safe inspection limit (1 MB)",
                            evidence=[Evidence(file=rel_path, reason="Contract file too large to parse")],
                        )
                    )
                    continue

                content = c.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                contracts.append(
                    ApiContractFinding(
                        file=rel_path,
                        format="OpenAPI",
                        status="INVALID",
                        error_message=str(exc),
                        evidence=[Evidence(file=rel_path, reason=f"Failed to read file: {exc}")],
                    )
                )
                continue

            # Parse YAML or JSON safely
            data: Any = None
            try:
                if c.suffix.lower() == ".json":
                    data = json.loads(content)
                else:
                    data = yaml.safe_load(content)
            except (yaml.YAMLError, json.JSONDecodeError, ValueError, TypeError) as exc:
                contracts.append(
                    ApiContractFinding(
                        file=rel_path,
                        format="OpenAPI" if "openapi" in c.name.lower() else "Swagger",
                        status="INVALID",
                        error_message=f"Contract parser syntax error: {exc}",
                        evidence=[Evidence(file=rel_path, reason=f"Syntax parsing failure: {exc}")],
                    )
                )
                continue

            if not isinstance(data, dict):
                contracts.append(
                    ApiContractFinding(
                        file=rel_path,
                        format="OpenAPI" if "openapi" in c.name.lower() else "Swagger",
                        status="INVALID",
                        error_message="Contract root structure must be an object/dict.",
                        evidence=[Evidence(file=rel_path, reason="Root document is not a mapping/object")],
                    )
                )
                continue

            is_openapi = "openapi" in data
            is_swagger = "swagger" in data

            if not is_openapi and not is_swagger:
                contracts.append(
                    ApiContractFinding(
                        file=rel_path,
                        format="Unknown",
                        status="INVALID",
                        error_message="Missing required 'openapi' or 'swagger' root specification key.",
                        evidence=[Evidence(file=rel_path, reason="Missing OpenAPI/Swagger root key")],
                    )
                )
                continue

            spec_format = "OpenAPI" if is_openapi else "Swagger"
            info = data.get("info", {}) if isinstance(data.get("info"), dict) else {}
            title = str(info.get("title")) if info.get("title") else None
            spec_version = str(info.get("version")) if info.get("version") else None

            # Server URLs
            servers: list[str] = []
            if is_openapi and isinstance(data.get("servers"), list):
                for s in data["servers"]:
                    if isinstance(s, dict) and s.get("url"):
                        servers.append(str(s["url"]))
            elif is_swagger:
                host = data.get("host")
                base_path = data.get("basePath", "")
                if host:
                    servers.append(f"{host}{base_path}")

            # Routes and operations count
            paths = data.get("paths", {})
            routes: list[dict[str, Any]] = []
            operations_count = 0

            if isinstance(paths, dict):
                for path_str, path_item in paths.items():
                    if isinstance(path_item, dict):
                        for m in ["get", "post", "put", "delete", "patch", "options", "head", "trace"]:
                            if m in path_item and isinstance(path_item[m], dict):
                                operations_count += 1
                                op = path_item[m]
                                routes.append(
                                    {
                                        "method": m.upper(),
                                        "path": str(path_str),
                                        "operation_id": op.get("operationId"),
                                        "summary": op.get("summary"),
                                    }
                                )

            routes.sort(key=lambda r: (r["path"], r["method"]))

            contracts.append(
                ApiContractFinding(
                    file=rel_path,
                    format=spec_format,
                    title=title,
                    version=spec_version,
                    status="VALID",
                    servers=sorted(servers),
                    paths_count=len(paths) if isinstance(paths, dict) else 0,
                    operations_count=operations_count,
                    routes=routes,
                    evidence=[
                        Evidence(
                            file=rel_path,
                            reason=f"Parsed valid {spec_format} contract with {operations_count} operations across {len(paths)} paths",
                        )
                    ],
                )
            )

        return contracts

    def _extract_modules(
        self, all_dirs: list[Path], real_workspace: Path
    ) -> list[ModuleFinding]:
        modules: list[ModuleFinding] = []

        for d in all_dirs:
            rel = d.relative_to(real_workspace)
            parts = rel.parts

            # Only consider 1-deep or 2-deep directories
            if not (1 <= len(parts) <= 2):
                continue

            name = d.name.lower()

            if name in {"routers", "routes", "controllers", "api", "endpoints"}:
                mod_type = "api"
            elif name in {"models", "schemas", "entities"}:
                mod_type = "data_models"
            elif name in {"services", "business", "logic"}:
                mod_type = "services"
            elif name in {"components", "views", "pages", "ui"}:
                mod_type = "ui_components"
            elif name in {"utils", "helpers", "lib", "common", "core"}:
                mod_type = "utilities"
            elif len(parts) == 1:
                mod_type = "root_module"
            else:
                mod_type = "submodule"

            children = list(d.iterdir())
            lang_counts: dict[str, int] = {}
            for child in children:
                if child.is_file() and child.suffix.lower() in EXTENSION_LANGUAGE_MAP:
                    lang = EXTENSION_LANGUAGE_MAP[child.suffix.lower()]
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1

            predominant_lang = (
                max(lang_counts.items(), key=lambda x: x[1])[0]
                if lang_counts
                else "Generic"
            )

            modules.append(
                ModuleFinding(
                    path=rel.as_posix(),
                    type=mod_type,
                    language=predominant_lang,
                    children_count=len(children),
                )
            )

        return modules

    def _extract_deployment(
        self, deployment_files: list[Path], real_workspace: Path
    ) -> list[DeploymentFinding]:
        deployments: list[DeploymentFinding] = []

        for f in deployment_files:
            rel_path = f.relative_to(real_workspace).as_posix()
            name = f.name
            name_lower = name.lower()

            if name.startswith("Dockerfile"):
                dep_type = "docker"
            elif "docker-compose" in name_lower:
                dep_type = "docker-compose"
            elif ".github/workflows" in rel_path:
                dep_type = "github_actions"
            elif name == "Procfile":
                dep_type = "procfile"
            elif name == "fly.toml":
                dep_type = "fly_io"
            elif name == "vercel.json":
                dep_type = "vercel"
            else:
                dep_type = "deployment_config"

            deployments.append(DeploymentFinding(file=rel_path, type=dep_type))

        return deployments


discovery_service = RepositoryDiscoveryService()
