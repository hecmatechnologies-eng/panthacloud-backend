from typing import Any, Protocol


class GitProvider(Protocol):
    async def get_repository(
        self, owner: str, repo: str, token: str | None = None
    ) -> dict[str, Any]:
        """Fetch repository metadata."""
        ...

    async def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        token: str | None = None,
    ) -> str | None:
        """Return the text of the file at `path` on `ref`, or None if it does not exist."""
        ...

    async def get_branch_head(
        self, owner: str, repo: str, branch: str, token: str | None = None
    ) -> str:
        """Return the commit SHA the branch currently points at."""
        ...

    async def create_branch(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        new_branch: str,
        base_sha: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Create new_branch at base_sha — the commit the caller has already read.

        `base_sha` is required on purpose: re-resolving the branch head here would reintroduce
        the read-then-branch race that silently reverted a customer commit (CLAUDE.md §3.1).
        """
        ...

    async def commit_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        commit_message: str,
        files: dict[str, str],
        token: str | None = None,
    ) -> str:
        """Commit files to a branch and return the new commit SHA."""
        ...

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Open a pull request from head_branch to base_branch."""
        ...

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve pull request metadata."""
        ...
