import asyncio
import datetime
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.secrets import secret_store
from app.models.audit_event import AuditEvent
from app.models.integration import Integration
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.services.repository.workspace import (
    WorkspaceLimitExceededError,
    workspace_manager,
)

logger = logging.getLogger(__name__)


def sanitize_git_output(text: str, token: str | None = None) -> str:
    """Removes secret tokens and credentials from command output and error logs."""
    if not text:
        return ""
    sanitized = text
    if token:
        sanitized = sanitized.replace(token, "[REDACTED]")
    # Sanitize general HTTP credentials in URLs (e.g., https://user:pass@host or https://token@host)
    sanitized = re.sub(r"://([^@\s]+)@", "://[REDACTED]@", sanitized)
    return sanitized


class RepositoryAcquisitionService:
    @staticmethod
    async def record_audit(
        db: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID | None,
        event_type: str,
        resource_id: uuid.UUID,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Safely persists a lightweight audit event without sensitive credential exposure."""
        clean_payload = dict(payload or {})
        # Security invariant: redact any accidental credential keys
        for sensitive_key in ("token", "password", "secret", "credentials", "authorization"):
            clean_payload.pop(sensitive_key, None)

        event = AuditEvent(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            event_type=event_type,
            resource_type="repository_snapshot",
            resource_id=resource_id,
            payload=clean_payload,
        )
        db.add(event)
        await db.flush()

    async def acquire(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        snapshot: RepositorySnapshot,
        repository: Repository,
        integration: Integration,
        user_id: uuid.UUID | None = None,
    ) -> RepositorySnapshot:
        """
        Executes shallow acquisition of the repository into an isolated workspace.
        Binds the immutable commit SHA on success or cleanly handles failure.
        """
        snapshot.status = SnapshotStatus.ACQUIRING
        await self.record_audit(
            db,
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            event_type="repository.snapshot.acquisition_started",
            resource_id=snapshot.id,
            payload={"branch": snapshot.branch},
        )
        await db.commit()
        await db.refresh(snapshot)

        # Allocate workspace
        workspace_path, workspace_ref = workspace_manager.allocate_workspace(
            organization_id, project_id, snapshot.id
        )
        snapshot.workspace_reference = workspace_ref

        # Resolve credentials if available
        auth_token: str | None = None
        if integration.encrypted_secrets:
            try:
                decrypted = secret_store.decrypt(integration.encrypted_secrets)
                auth_token = (
                    decrypted.get("token")
                    or decrypted.get("github_token")
                    or decrypted.get("gitlab_token")
                    or decrypted.get("access_token")
                )
            except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
                logger.warning(f"Could not decrypt secrets for integration {integration.id}: {exc}")

        # Resolve clone target URL
        clone_url: str
        if repository.url and repository.url.startswith("file://"):
            from urllib.parse import urlparse
            from urllib.request import url2pathname
            clone_url = url2pathname(urlparse(repository.url).path)
        elif repository.url and (
            Path(repository.url).exists() or repository.url.startswith("/") or ":" in repository.url[:3]
        ):
            # Local Git fixture path
            clone_url = repository.url
        elif auth_token:
            if repository.provider.value == "gitlab":
                clone_url = f"https://oauth2:{auth_token}@gitlab.com/{repository.full_name}.git"
            else:
                clone_url = f"https://x-access-token:{auth_token}@github.com/{repository.full_name}.git"
        else:
            clone_url = repository.url or f"https://github.com/{repository.full_name}.git"

        # Controlled Git clone command with no shell expansion
        cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            snapshot.branch,
            clone_url,
            str(workspace_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=float(settings.ACQUISITION_TIMEOUT_SECONDS),
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError(
                    f"Repository acquisition timed out after {settings.ACQUISITION_TIMEOUT_SECONDS} seconds."
                )

            if proc.returncode != 0:
                err_msg = sanitize_git_output(stderr.decode("utf-8", errors="replace"), auth_token)
                raise RuntimeError(f"Git clone failed (exit {proc.returncode}): {err_msg}")

            # Enforce resource limits immediately after acquisition
            workspace_manager.check_workspace_limits(workspace_path)

            # Determine immutable commit SHA
            rev_proc = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "HEAD",
                cwd=str(workspace_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            rev_stdout, _rev_stderr = await rev_proc.communicate()
            if rev_proc.returncode != 0:
                raise RuntimeError("Failed to resolve commit SHA via git rev-parse HEAD.")

            commit_sha = rev_stdout.decode("utf-8").strip()
            now = datetime.datetime.now(datetime.UTC)

            snapshot.commit_sha = commit_sha
            snapshot.status = SnapshotStatus.READY
            snapshot.acquired_at = now
            snapshot.completed_at = now
            snapshot.error_code = None
            snapshot.error_message = None

            await self.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.snapshot.completed",
                resource_id=snapshot.id,
                payload={"branch": snapshot.branch, "commit_sha": commit_sha},
            )
            await db.commit()
            await db.refresh(snapshot)
            return snapshot

        except (WorkspaceLimitExceededError, TimeoutError, RuntimeError, OSError, ValueError) as exc:
            workspace_manager.cleanup_workspace(workspace_path)
            clean_err = sanitize_git_output(str(exc), auth_token)

            snapshot.status = SnapshotStatus.FAILED
            snapshot.error_code = (
                "LIMIT_EXCEEDED"
                if isinstance(exc, WorkspaceLimitExceededError)
                else "TIMEOUT"
                if isinstance(exc, TimeoutError)
                else "ACQUISITION_FAILED"
            )
            snapshot.error_message = clean_err
            snapshot.completed_at = datetime.datetime.now(datetime.UTC)

            await self.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.snapshot.failed",
                resource_id=snapshot.id,
                payload={"branch": snapshot.branch, "error_code": snapshot.error_code},
            )
            await db.commit()
            await db.refresh(snapshot)
            return snapshot


acquisition_service = RepositoryAcquisitionService()
