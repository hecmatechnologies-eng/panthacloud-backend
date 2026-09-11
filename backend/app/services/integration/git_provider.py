from typing import Any, Protocol


class GitProvider(Protocol):
    async def get_repository(
        self, owner: str, repo: str, token: str | None = None
    ) -> dict[str, Any]:
        """Fetch repository metadata."""
        ...

    async def create_branch(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        new_branch: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Create a new branch from a base branch."""
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
