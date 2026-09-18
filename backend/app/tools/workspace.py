"""Workspace write tools for the CodingAgent (Step D, FR-064, FR-066).

Includes write_file and apply_patch.
Both require the 'workspace.write' capability and an ApprovedPlan to be executed by ToolGateway.
All operations are caged inside the ephemeral run sandbox via LocalWorkspaceProvider.assert_path_contained.
"""

import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from app.harness.context import ExecutionContext
from app.services.integration.sandbox import (
    LocalWorkspaceProvider,
    SandboxError,
    SandboxSecurityError,
)
from app.services.integration.sandbox import (
    workspace_provider as default_workspace_provider,
)
from app.tools.base import Tool, ToolError, ToolKind, ToolResult
from app.tools.registry import ToolRegistry

WRITE_CAPABILITY = "workspace.write"

WorkspacePathResolver = Callable[[ExecutionContext], Path]

_PROTECTED_PATH_PATTERNS = (
    re.compile(r"^\.git(/|\\|$)"),
    re.compile(r"^\.env(\..+)?$"),
    re.compile(r"^id_rsa.*$"),
)


def _assert_safe_relative_path(path: str) -> None:
    norm = path.strip().replace("\\", "/")
    while norm.startswith("/"):
        norm = norm[1:]
    for pattern in _PROTECTED_PATH_PATTERNS:
        if pattern.search(norm):
            raise ToolError(f"Modifying protected path '{path}' is strictly prohibited.")


class WriteFileArgs(BaseModel):
    path: str = Field(..., min_length=1, description="Repository-relative path of the file to write.")
    content: str = Field(..., description="UTF-8 text content to write into the file.")


class ApplyPatchArgs(BaseModel):
    path: str = Field(..., min_length=1, description="Repository-relative path of the file to patch.")
    target: str = Field(..., min_length=1, description="Exact substring to find in the file.")
    replacement: str = Field(..., description="Replacement substring to substitute for target.")


class _WorkspaceTool(Tool):
    kind = ToolKind.WRITE
    required_capability = WRITE_CAPABILITY

    def __init__(
        self,
        resolve_path: WorkspacePathResolver | None = None,
        provider: LocalWorkspaceProvider | None = None,
    ) -> None:
        self._resolve_path = resolve_path
        self._provider = provider or default_workspace_provider

    def _get_sandbox_path(self, context: ExecutionContext) -> Path:
        if self._resolve_path is not None:
            try:
                return self._resolve_path(context)
            except Exception as exc:
                raise ToolError(f"Could not resolve workspace sandbox: {exc}") from exc

        if context.workspace_reference:
            cand = Path(context.workspace_reference)
            if cand.is_absolute() and cand.exists():
                return cand
        raise ToolError("No workspace sandbox configured for this execution context.")


class WriteFileTool(_WorkspaceTool):
    name = "write_file"
    description = (
        "Write full content to a repository-relative path inside the workspace sandbox. "
        "Creates parent directories if necessary."
    )
    input_schema = WriteFileArgs

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        args: WriteFileArgs = arguments  # type: ignore[assignment]
        _assert_safe_relative_path(args.path)
        sandbox_path = self._get_sandbox_path(context)

        try:
            written = self._provider.write_file(sandbox_path, args.path, args.content)
            size = written.stat().st_size
            return ToolResult(
                output={
                    "path": args.path,
                    "size_bytes": size,
                    "status": "written",
                }
            )
        except SandboxSecurityError as exc:
            raise ToolError(f"Security refusal: {exc}") from exc
        except SandboxError as exc:
            raise ToolError(f"Sandbox error: {exc}") from exc
        except Exception as exc:
            raise ToolError(f"Failed to write file '{args.path}': {exc}") from exc


class ApplyPatchTool(_WorkspaceTool):
    name = "apply_patch"
    description = (
        "Replace an exact contiguous block of code (target) with new code (replacement) "
        "in an existing file inside the workspace sandbox."
    )
    input_schema = ApplyPatchArgs

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        args: ApplyPatchArgs = arguments  # type: ignore[assignment]
        _assert_safe_relative_path(args.path)
        sandbox_path = self._get_sandbox_path(context)

        try:
            current_content = self._provider.read_file(sandbox_path, args.path)
        except FileNotFoundError:
            raise ToolError(f"File '{args.path}' does not exist to patch. Use write_file instead.") from None
        except SandboxSecurityError as exc:
            raise ToolError(f"Security refusal: {exc}") from exc

        count = current_content.count(args.target)
        if count == 0:
            raise ToolError(
                f"Target block not found in '{args.path}'. Check spacing and exact character matches."
            )
        if count > 1:
            raise ToolError(
                f"Target block matches {count} occurrences in '{args.path}'. Provide more surrounding context to make it unique."
            )

        new_content = current_content.replace(args.target, args.replacement, 1)
        try:
            self._provider.write_file(sandbox_path, args.path, new_content)
            return ToolResult(
                output={
                    "path": args.path,
                    "status": "patched",
                    "occurrences_replaced": 1,
                }
            )
        except SandboxError as exc:
            raise ToolError(f"Failed to apply patch to '{args.path}': {exc}") from exc


def build_workspace_tools(
    resolve_path: WorkspacePathResolver | None = None,
    provider: LocalWorkspaceProvider | None = None,
) -> list[Tool]:
    return [
        WriteFileTool(resolve_path, provider),
        ApplyPatchTool(resolve_path, provider),
    ]


def register_workspace_tools(
    registry: ToolRegistry,
    resolve_path: WorkspacePathResolver | None = None,
    provider: LocalWorkspaceProvider | None = None,
) -> None:
    for tool in build_workspace_tools(resolve_path, provider):
        registry.register(tool)

