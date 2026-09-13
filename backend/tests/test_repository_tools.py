"""Step C · C4 — read-only repository tools (FR-064, FR-067, FR-070).

`read_tree`, `read_file` and `search_code` over a containment-checked workspace: bounded output with
a truncation signal, model-readable errors, and scope resolved from the ExecutionContext.
"""

import os
import shutil
import subprocess
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.agents.base import AgentDefinition, Budget
from app.core.database import get_session_factory
from app.harness.context import ExecutionContext
from app.harness.run import start_agent_run
from app.models.agent_run import AgentRun, AgentToolCall
from app.services.repository.reader import LocalWorkspaceReader
from app.tools.base import ToolError
from app.tools.gateway import ToolGateway
from app.tools.registry import ToolRegistry
from app.tools.repository import (
    ReadFileArgs,
    ReadFileTool,
    ReadTreeArgs,
    SearchCodeArgs,
    build_repository_tools,
    register_repository_tools,
)

READ_CAP = "repository.read"


@pytest.fixture
def workspace() -> Path:
    root = Path(tempfile.mkdtemp(prefix="c4-workspace-"))
    (root / "app").mkdir()
    (root / "app" / "layout.tsx").write_text(
        "export default function Root() {\n  return null;\n}\n", encoding="utf-8"
    )
    (root / "package.json").write_text('{"name": "store"}', encoding="utf-8")
    (root / "README.md").write_text(
        "Welcome to the store.\nRefund policy: 30 days.\n", encoding="utf-8"
    )
    # Ignored by the reader.
    (root / "node_modules").mkdir()
    (root / "node_modules" / "left-pad.js").write_text("ignored", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("ignored", encoding="utf-8")
    yield root
    shutil.rmtree(root, ignore_errors=True)


def context() -> ExecutionContext:
    return ExecutionContext(
        organization_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        environment="test",
        agent_name="website_analyst",
        agent_version="1.0.0",
        capabilities=frozenset({READ_CAP}),
        commit_sha="a" * 40,
        workspace_reference="ws-test",
    )


def tools_for(workspace: Path) -> dict[str, object]:
    reader = LocalWorkspaceReader(workspace)
    return {tool.name: tool for tool in build_repository_tools(lambda _ctx: reader)}


# ============================================================
# 1. read_tree
# ============================================================


@pytest.mark.asyncio
async def test_read_tree_lists_files_and_skips_ignored_dirs(workspace: Path) -> None:
    tool = tools_for(workspace)["read_tree"]
    result = await tool.execute(context(), ReadTreeArgs())

    paths = [entry["path"] for entry in result.output["entries"]]
    assert paths == ["README.md", "app/layout.tsx", "package.json"]
    assert result.truncated is False


@pytest.mark.asyncio
async def test_read_tree_signals_truncation(workspace: Path) -> None:
    tool = tools_for(workspace)["read_tree"]
    result = await tool.execute(context(), ReadTreeArgs(max_entries=1))
    assert len(result.output["entries"]) == 1
    assert result.truncated is True


@pytest.mark.asyncio
async def test_read_tree_is_deterministic(workspace: Path) -> None:
    tool = tools_for(workspace)["read_tree"]
    first = await tool.execute(context(), ReadTreeArgs())
    second = await tool.execute(context(), ReadTreeArgs())
    assert first.output == second.output


# ============================================================
# 2. read_file
# ============================================================


@pytest.mark.asyncio
async def test_read_file_pages_with_offset_and_limit(workspace: Path) -> None:
    tool = tools_for(workspace)["read_file"]
    result = await tool.execute(context(), ReadFileArgs(path="app/layout.tsx", offset=1, limit=1))

    assert result.output["text"] == "  return null;"
    assert result.output["start_line"] == 2
    assert result.output["total_lines"] == 3
    assert result.truncated is True


@pytest.mark.asyncio
async def test_read_file_missing_is_a_readable_error(workspace: Path) -> None:
    tool = tools_for(workspace)["read_file"]
    with pytest.raises(ToolError, match="File not found"):
        await tool.execute(context(), ReadFileArgs(path="does/not/exist.ts"))


@pytest.mark.asyncio
async def test_read_file_refuses_traversal_and_absolute_paths(workspace: Path) -> None:
    tool = tools_for(workspace)["read_file"]
    with pytest.raises(ToolError):
        await tool.execute(context(), ReadFileArgs(path="../../etc/passwd"))
    with pytest.raises(ToolError):
        await tool.execute(context(), ReadFileArgs(path="/etc/passwd"))


# ============================================================
# 3. search_code
# ============================================================


@pytest.mark.asyncio
async def test_search_code_finds_matches_with_line_numbers(workspace: Path) -> None:
    tool = tools_for(workspace)["search_code"]
    result = await tool.execute(context(), SearchCodeArgs(query="refund"))

    assert result.output["count"] == 1
    hit = result.output["hits"][0]
    assert hit["path"] == "README.md"
    assert hit["line"] == 2
    assert "30 days" in hit["text"]


@pytest.mark.asyncio
async def test_search_code_skips_ignored_dirs(workspace: Path) -> None:
    tool = tools_for(workspace)["search_code"]
    result = await tool.execute(context(), SearchCodeArgs(query="ignored"))
    assert result.output["hits"] == []


# ============================================================
# 3b. Secrets, VCS metadata and symlinks are never readable
# ============================================================


@pytest.mark.asyncio
async def test_read_file_refuses_secret_and_vcs_paths(workspace: Path) -> None:
    (workspace / ".env").write_text("DATABASE_URL=postgres://u:p@host/db", encoding="utf-8")
    (workspace / ".env.local").write_text("SECRET=1", encoding="utf-8")
    (workspace / ".git" / "config").write_text(
        "url = https://x-access-token:ghp_secret@github.com/acme/store.git", encoding="utf-8"
    )
    (workspace / "credentials").mkdir()
    (workspace / "credentials" / "token.json").write_text("{}", encoding="utf-8")

    tool = tools_for(workspace)["read_file"]
    for denied in (
        ".git/config",
        ".GIT/config",
        ".git./config",
        "GIT~1/config",
        ".env",
        ".env.",
        ".env.local",
        "credentials/token.json",
        "credentials./token.json",
    ):
        with pytest.raises(ToolError):
            await tool.execute(context(), ReadFileArgs(path=denied))


def _make_directory_link(link: Path, target: Path) -> bool:
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    return False


@pytest.mark.asyncio
async def test_read_file_refuses_a_directory_link_into_git(workspace: Path) -> None:
    (workspace / ".git" / "config").write_text(
        "url = https://x-access-token:ghp_secret@github.com/acme/store.git", encoding="utf-8"
    )
    if not _make_directory_link(workspace / "vendor", workspace / ".git"):
        pytest.skip("cannot create a directory link on this platform")

    with pytest.raises(ToolError):
        await tools_for(workspace)["read_file"].execute(context(), ReadFileArgs(path="vendor/config"))

    # Nor may it surface through the listing or search.
    tree = await tools_for(workspace)["read_tree"].execute(context(), ReadTreeArgs())
    assert "vendor/config" not in [entry["path"] for entry in tree.output["entries"]]


@pytest.mark.asyncio
async def test_listing_and_search_skip_secret_files(workspace: Path) -> None:
    (workspace / ".env").write_text("SECRET_CANARY=1", encoding="utf-8")

    tree = await tools_for(workspace)["read_tree"].execute(context(), ReadTreeArgs())
    assert ".env" not in [entry["path"] for entry in tree.output["entries"]]

    search = await tools_for(workspace)["search_code"].execute(
        context(), SearchCodeArgs(query="SECRET_CANARY")
    )
    assert search.output["hits"] == []


@pytest.mark.asyncio
async def test_read_file_refuses_a_symlink_escape(workspace: Path) -> None:
    outside = workspace.parent / "outside-secret.txt"
    outside.write_text("TOPSECRET", encoding="utf-8")
    link = workspace / "escape.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted on this platform")

    with pytest.raises(ToolError):
        await tools_for(workspace)["read_file"].execute(context(), ReadFileArgs(path="escape.txt"))


@pytest.mark.asyncio
async def test_search_does_not_follow_symlinks(workspace: Path) -> None:
    outside = workspace.parent / "outside-secret.txt"
    outside.write_text("TOPSECRET_CANARY", encoding="utf-8")
    link = workspace / "innocent.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted on this platform")

    result = await tools_for(workspace)["search_code"].execute(
        context(), SearchCodeArgs(query="TOPSECRET_CANARY")
    )
    assert result.output["hits"] == []


# ============================================================
# 3c. Paging reports a total
# ============================================================


@pytest.mark.asyncio
async def test_read_tree_pages_with_offset_and_reports_total(workspace: Path) -> None:
    result = await tools_for(workspace)["read_tree"].execute(
        context(), ReadTreeArgs(offset=1, max_entries=1)
    )
    assert result.output["count"] == 1
    assert result.output["total"] == 3
    assert result.output["entries"][0]["path"] == "app/layout.tsx"
    assert result.truncated is True


@pytest.mark.asyncio
async def test_search_reports_total(workspace: Path) -> None:
    (workspace / "notes.txt").write_text("needle\nneedle\n", encoding="utf-8")
    result = await tools_for(workspace)["search_code"].execute(
        context(), SearchCodeArgs(query="needle", max_results=1)
    )
    assert result.output["count"] == 1
    assert result.output["total"] == 2
    assert result.truncated is True


# ============================================================
# 4. Scope from the context, not the model
# ============================================================


@pytest.mark.asyncio
async def test_reader_is_resolved_from_the_context(workspace: Path) -> None:
    seen: dict[str, ExecutionContext] = {}
    reader = LocalWorkspaceReader(workspace)

    def resolver(ctx: ExecutionContext):
        seen["ctx"] = ctx
        return reader

    tool = ReadFileTool(resolver)
    ctx = context()
    await tool.execute(ctx, ReadFileArgs(path="package.json"))
    assert seen["ctx"] is ctx


def test_tool_schemas_carry_no_repository_identifier() -> None:
    for tool in build_repository_tools(lambda _ctx: LocalWorkspaceReader(Path("."))):
        assert "repository" not in tool.input_schema.model_json_schema()["properties"]


# ============================================================
# 5. Through the gateway
# ============================================================


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "org_name": f"{name}'s Org",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    orgs = await client.get(
        "/api/v1/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return token, orgs.json()[0]["id"]


async def create_project(client: AsyncClient, token: str, org_id: str, name: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": name.lower().replace(" ", "-")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_read_tool_records_through_the_gateway(client: AsyncClient, workspace: Path) -> None:
    token, org_id = await register_user(client, "c4_gateway@example.com", "C4Gateway")
    proj_id = await create_project(client, token, org_id, "C4Gateway Proj")

    reader = LocalWorkspaceReader(workspace)
    registry = ToolRegistry()
    register_repository_tools(registry, lambda _ctx: reader)
    gateway = ToolGateway(registry)

    definition = AgentDefinition(
        name="website_analyst",
        version="1.0.0",
        instructions="...",
        capabilities=frozenset({READ_CAP}),
        tools=("read_file",),
        output_schema=None,
        budget=Budget(tool_calls=10, tokens=1000, seconds=30, cost_usd=Decimal("0.10")),
    )
    ctx = ExecutionContext(
        organization_id=uuid.UUID(org_id),
        project_id=uuid.UUID(proj_id),
        repository_id=None,
        environment="test",
        agent_name="website_analyst",
        agent_version="1.0.0",
        capabilities=frozenset({READ_CAP}),
    )

    session_factory = get_session_factory()
    async with session_factory() as db:
        run = await start_agent_run(db, ctx, definition)
        await db.commit()
        run_id = run.id

    async with session_factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
        result = await gateway.execute(db, run, ctx, "read_file", {"path": "package.json"})
        await db.commit()

    assert result.is_error is False
    assert result.output["text"] == '{"name": "store"}'

    async with session_factory() as db:
        recorded = (
            await db.execute(select(AgentToolCall).where(AgentToolCall.agent_run_id == run_id))
        ).scalar_one()
    assert recorded.tool_name == "read_file"
    assert recorded.outcome == "ok"
