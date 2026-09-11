import logging
import os
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot
from app.services.repository.acquisition import acquisition_service
from app.services.repository.workspace import workspace_manager

logger = logging.getLogger(__name__)

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

# Known manifest filenames
KNOWN_MANIFESTS: set[str] = {
    "package.json",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "composer.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
}

# Known API contracts
KNOWN_API_CONTRACTS: set[str] = {
    "openapi.yaml",
    "openapi.yml",
    "openapi.json",
    "swagger.yaml",
    "swagger.yml",
    "swagger.json",
}

# Known deployment files
KNOWN_DEPLOYMENT_FILES: set[str] = {
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
}


class RepositoryInspectionService:
    async def inspect(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        repository: Repository,
        snapshot: RepositorySnapshot,
        user_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """
        Executes read-only, deterministic source inspection on the snapshot's workspace.
        Never executes code, imports libraries, or invokes interpreters.
        """
        workspace_path = workspace_manager.get_workspace_path(
            organization_id, project_id, snapshot.id
        )

        if not workspace_path.exists():
            raise FileNotFoundError("Snapshot workspace does not exist or has expired.")

        real_workspace = workspace_path.resolve()

        file_count = 0
        directory_count = 0
        total_size_bytes = 0
        max_depth = 0

        detected_languages: set[str] = set()
        detected_manifests: set[str] = set()
        detected_contracts: set[str] = set()
        detected_deployment: set[str] = set()
        detected_frameworks: set[str] = set()

        # Cache file content for manifest inspection
        manifest_contents: dict[str, str] = {}

        for root, dirs, files in os.walk(real_workspace):
            root_path = Path(root)

            # Ignore .git metadata folder
            if ".git" in root_path.parts:
                continue

            rel_depth = len(root_path.relative_to(real_workspace).parts)
            max_depth = max(max_depth, rel_depth)

            # Symlink guard for directories
            for d in list(dirs):
                if d == ".git":
                    continue
                dir_path = root_path / d
                if dir_path.is_symlink():
                    try:
                        resolved_dir = dir_path.resolve()
                        if not resolved_dir.is_relative_to(real_workspace):
                            dirs.remove(d)  # Symlink escape blocked
                            continue
                    except (OSError, RuntimeError):
                        dirs.remove(d)
                        continue
                directory_count += 1

            for f in files:
                file_path = root_path / f

                # Symlink guard for files
                if file_path.is_symlink():
                    try:
                        resolved_file = file_path.resolve()
                        if not resolved_file.is_relative_to(real_workspace):
                            continue  # Symlink escape blocked
                    except (OSError, RuntimeError):
                        continue

                file_count += 1
                try:
                    f_size = file_path.stat().st_size
                    total_size_bytes += f_size
                except OSError:
                    f_size = 0

                # Language detection
                ext = file_path.suffix.lower()
                if ext in EXTENSION_LANGUAGE_MAP:
                    detected_languages.add(EXTENSION_LANGUAGE_MAP[ext])

                f_lower = f.lower()

                # Manifest detection
                for manifest in KNOWN_MANIFESTS:
                    if f_lower == manifest.lower():
                        detected_manifests.add(manifest)
                        # Read small manifest file (< 1MB) for framework signatures
                        if f_size < 1024 * 1024:
                            try:
                                content = file_path.read_text(
                                    encoding="utf-8", errors="ignore"
                                )
                                if f_lower in manifest_contents:
                                    manifest_contents[f_lower] += "\n" + content
                                else:
                                    manifest_contents[f_lower] = content
                            except (OSError, UnicodeDecodeError) as exc:
                                logger.debug("Could not read manifest %s: %s", file_path, exc)

                # API Contract detection
                for contract in KNOWN_API_CONTRACTS:
                    if f_lower == contract.lower():
                        detected_contracts.add(contract)

                # Deployment config detection
                for deploy_file in KNOWN_DEPLOYMENT_FILES:
                    if f_lower == deploy_file.lower():
                        detected_deployment.add(deploy_file)

        # Framework detection heuristics based on manifest content
        # Python manifests
        py_content = manifest_contents.get("pyproject.toml", "") + "\n" + manifest_contents.get("requirements.txt", "")
        py_content_lower = py_content.lower()
        if "fastapi" in py_content_lower:
            detected_frameworks.add("FastAPI")
        if "django" in py_content_lower:
            detected_frameworks.add("Django")

        # Node / JS manifests
        pkg_content = manifest_contents.get("package.json", "")
        pkg_lower = pkg_content.lower()
        if '"next"' in pkg_lower or "'next'" in pkg_lower:
            detected_frameworks.add("Next.js")
        if '"react"' in pkg_lower or "'react'" in pkg_lower:
            detected_frameworks.add("React")
        if '"express"' in pkg_lower or "'express'" in pkg_lower:
            detected_frameworks.add("Express")
        if '"@nestjs"' in pkg_lower or "'@nestjs'" in pkg_lower:
            detected_frameworks.add("NestJS")

        # PHP manifests
        composer_content = manifest_contents.get("composer.json", "").lower()
        if "laravel" in composer_content:
            detected_frameworks.add("Laravel")

        result = {
            "snapshot_id": snapshot.id,
            "commit_sha": snapshot.commit_sha,
            "repository": {
                "name": repository.name,
                "default_branch": repository.default_branch,
            },
            "structure": {
                "file_count": file_count,
                "directory_count": directory_count,
                "total_size_bytes": total_size_bytes,
                "maximum_depth": max_depth,
            },
            "languages": sorted(detected_languages),
            "frameworks": sorted(detected_frameworks),
            "manifests": sorted(detected_manifests),
            "api_contracts": sorted(detected_contracts),
            "deployment_files": sorted(detected_deployment),
        }

        # Record audit event
        await acquisition_service.record_audit(
            db,
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            event_type="repository.inspection.completed",
            resource_id=snapshot.id,
            payload={
                "commit_sha": snapshot.commit_sha,
                "file_count": file_count,
                "languages": list(detected_languages),
                "frameworks": list(detected_frameworks),
            },
        )
        await db.commit()

        return result


inspection_service = RepositoryInspectionService()
