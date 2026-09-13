"""Read-only repository tools (FR-064, FR-067, FR-070; AGENT-ARCHITECTURE §3.1).

`read_tree`, `read_file` and `search_code` — the analyst's entire view of a customer repository.
Each resolves its reader from the trusted ``ExecutionContext``; none accepts a repository or path
scope from the model. Outputs are bounded and signal truncation so the model can page.
"""

from collections.abc import Callable

from pydantic import BaseModel, Field

from app.harness.context import ExecutionContext
from app.services.repository.reader import RepositoryReader, RepositoryReaderError
from app.tools.base import Tool, ToolError, ToolKind, ToolResult
from app.tools.registry import ToolRegistry

READ_CAPABILITY = "repository.read"

RepositoryReaderResolver = Callable[[ExecutionContext], RepositoryReader]


class ReadTreeArgs(BaseModel):
    path: str = Field("", description="Subdirectory to list; empty lists the repository root.")
    offset: int = Field(0, ge=0, description="Number of entries to skip, for paging.")
    max_entries: int = Field(500, ge=1, le=5000)


class ReadFileArgs(BaseModel):
    path: str = Field(..., min_length=1, description="Repository-relative path of the file to read.")
    offset: int = Field(0, ge=0, description="Zero-based line to start from.")
    limit: int = Field(200, ge=1, le=2000, description="Maximum number of lines to return.")


class SearchCodeArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="Case-insensitive substring.")
    offset: int = Field(0, ge=0, description="Number of matches to skip, for paging.")
    max_results: int = Field(50, ge=1, le=500)


class _RepositoryTool(Tool):
    kind = ToolKind.READ
    required_capability = READ_CAPABILITY

    def __init__(self, resolve_reader: RepositoryReaderResolver) -> None:
        self._resolve_reader = resolve_reader

    def _reader(self, context: ExecutionContext) -> RepositoryReader:
        try:
            return self._resolve_reader(context)
        except RepositoryReaderError as exc:
            raise ToolError(str(exc)) from exc


class ReadTreeTool(_RepositoryTool):
    name = "read_tree"
    description = (
        "List files in the repository (or a subdirectory), excluding dependencies and build output. "
        "Returns up to max_entries paths; when truncated, narrow the path or raise max_entries."
    )
    input_schema = ReadTreeArgs

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        args: ReadTreeArgs = arguments  # type: ignore[assignment]
        try:
            listing = await self._reader(context).list_tree(
                path=args.path, offset=args.offset, max_entries=args.max_entries
            )
        except RepositoryReaderError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(
            output={
                "entries": [
                    {"path": entry.path, "type": entry.entry_type, "size": entry.size}
                    for entry in listing.entries
                ],
                "count": len(listing.entries),
                "total": listing.total,
            },
            truncated=listing.truncated,
        )


class ReadFileTool(_RepositoryTool):
    name = "read_file"
    description = (
        "Read a UTF-8 text file by repository-relative path. Returns numbered lines from offset up "
        "to limit; when truncated, continue from start_line + returned line count."
    )
    input_schema = ReadFileArgs

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        args: ReadFileArgs = arguments  # type: ignore[assignment]
        try:
            content = await self._reader(context).read_file(
                path=args.path, offset=args.offset, limit=args.limit
            )
        except RepositoryReaderError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(
            output={
                "path": content.path,
                "start_line": content.start_line,
                "total_lines": content.total_lines,
                "text": content.text,
            },
            truncated=content.truncated,
        )


class SearchCodeTool(_RepositoryTool):
    name = "search_code"
    description = (
        "Search repository text files for a case-insensitive substring. Returns matching "
        "path:line pairs with the line text; when truncated, refine the query."
    )
    input_schema = SearchCodeArgs

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        args: SearchCodeArgs = arguments  # type: ignore[assignment]
        try:
            results = await self._reader(context).search(
                query=args.query, offset=args.offset, max_results=args.max_results
            )
        except RepositoryReaderError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(
            output={
                "hits": [
                    {"path": hit.path, "line": hit.line_number, "text": hit.line}
                    for hit in results.hits
                ],
                "count": len(results.hits),
                "total": results.total,
            },
            truncated=results.truncated,
        )


def build_repository_tools(resolve_reader: RepositoryReaderResolver) -> list[Tool]:
    return [
        ReadTreeTool(resolve_reader),
        ReadFileTool(resolve_reader),
        SearchCodeTool(resolve_reader),
    ]


def register_repository_tools(
    registry: ToolRegistry, resolve_reader: RepositoryReaderResolver
) -> None:
    for tool in build_repository_tools(resolve_reader):
        registry.register(tool)
