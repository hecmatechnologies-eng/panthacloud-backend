import hashlib
import logging
from typing import Any

import httpx

from app.services.integration.git_provider import GitProvider

logger = logging.getLogger("fussion.integration.github")


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubProvider(GitProvider):
    """
    Production GitHub REST API provider.
    Operates strictly as data via HTTP; never clones or executes repository code.
    """

    def __init__(self, base_url: str = "https://api.github.com") -> None:
        self.base_url = base_url.rstrip("/")

    def _headers(self, token: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Fussion-Control-Plane",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def get_repository(
        self, owner: str, repo: str, token: str | None = None
    ) -> dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers(token), timeout=15.0)
            if resp.status_code == 404:
                raise GitHubAPIError(f"Repository {owner}/{repo} not found on GitHub.", 404)
            if resp.status_code == 401 or resp.status_code == 403:
                raise GitHubAPIError(f"GitHub authentication error: {resp.text}", resp.status_code)
            if resp.status_code >= 400:
                raise GitHubAPIError(f"GitHub API error: {resp.text}", resp.status_code)
            return resp.json()

    async def create_branch(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        new_branch: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            # 1. Fetch base branch SHA
            ref_url = f"{self.base_url}/repos/{owner}/{repo}/git/ref/heads/{base_branch}"
            resp = await client.get(ref_url, headers=self._headers(token), timeout=15.0)
            if resp.status_code != 200:
                raise GitHubAPIError(
                    f"Base branch '{base_branch}' not found in {owner}/{repo}.", resp.status_code
                )
            base_sha = resp.json()["object"]["sha"]

            # 2. Create new reference
            create_url = f"{self.base_url}/repos/{owner}/{repo}/git/refs"
            body = {"ref": f"refs/heads/{new_branch}", "sha": base_sha}
            create_resp = await client.post(
                create_url, headers=self._headers(token), json=body, timeout=15.0
            )
            if create_resp.status_code not in (200, 201):
                raise GitHubAPIError(
                    f"Failed to create branch '{new_branch}': {create_resp.text}",
                    create_resp.status_code,
                )
            return create_resp.json()

    async def commit_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        commit_message: str,
        files: dict[str, str],
        token: str | None = None,
    ) -> str:
        async with httpx.AsyncClient() as client:
            headers = self._headers(token)
            # 1. Get branch commit SHA
            ref_url = f"{self.base_url}/repos/{owner}/{repo}/git/ref/heads/{branch}"
            ref_resp = await client.get(ref_url, headers=headers, timeout=15.0)
            if ref_resp.status_code != 200:
                raise GitHubAPIError(f"Branch '{branch}' not found: {ref_resp.text}", ref_resp.status_code)
            latest_commit_sha = ref_resp.json()["object"]["sha"]

            # 2. Get latest commit to find base tree
            commit_url = f"{self.base_url}/repos/{owner}/{repo}/git/commits/{latest_commit_sha}"
            commit_resp = await client.get(commit_url, headers=headers, timeout=15.0)
            base_tree_sha = commit_resp.json()["tree"]["sha"]

            # 3. Create blobs & tree items
            tree_items = []
            for path, content in files.items():
                blob_resp = await client.post(
                    f"{self.base_url}/repos/{owner}/{repo}/git/blobs",
                    headers=headers,
                    json={"content": content, "encoding": "utf-8"},
                    timeout=15.0,
                )
                blob_sha = blob_resp.json()["sha"]
                tree_items.append(
                    {"path": path, "mode": "100644", "type": "blob", "sha": blob_sha}
                )

            # 4. Create new tree
            tree_resp = await client.post(
                f"{self.base_url}/repos/{owner}/{repo}/git/trees",
                headers=headers,
                json={"base_tree": base_tree_sha, "tree": tree_items},
                timeout=15.0,
            )
            new_tree_sha = tree_resp.json()["sha"]

            # 5. Create new commit
            new_commit_resp = await client.post(
                f"{self.base_url}/repos/{owner}/{repo}/git/commits",
                headers=headers,
                json={
                    "message": commit_message,
                    "tree": new_tree_sha,
                    "parents": [latest_commit_sha],
                },
                timeout=15.0,
            )
            new_commit_sha = new_commit_resp.json()["sha"]

            # 6. Update reference
            patch_resp = await client.patch(
                ref_url,
                headers=headers,
                json={"sha": new_commit_sha, "force": False},
                timeout=15.0,
            )
            if patch_resp.status_code != 200:
                raise GitHubAPIError(f"Failed to update branch ref: {patch_resp.text}", patch_resp.status_code)

            return new_commit_sha

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
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=self._headers(token), json=payload, timeout=15.0)
            if resp.status_code not in (200, 201):
                raise GitHubAPIError(f"Failed to create pull request: {resp.text}", resp.status_code)
            return resp.json()

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        token: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers(token), timeout=15.0)
            if resp.status_code == 404:
                raise GitHubAPIError(f"Pull request #{pr_number} not found.", 404)
            if resp.status_code >= 400:
                raise GitHubAPIError(f"GitHub API error: {resp.text}", resp.status_code)
            return resp.json()


class MockGitProvider(GitProvider):
    """
    Deterministic in-memory mock for automated testing and local simulations.
    Requires no network access or external credentials.
    """

    def __init__(self) -> None:
        # Key: (owner, repo) -> repo metadata
        self.repositories: dict[tuple[str, str], dict[str, Any]] = {
            ("fussion-org", "storefront"): {
                "name": "storefront",
                "full_name": "fussion-org/storefront",
                "default_branch": "main",
                "private": False,
            },
            ("acme", "website"): {
                "name": "website",
                "full_name": "acme/website",
                "default_branch": "main",
                "private": True,
            },
        }
        # Key: (owner, repo, branch) -> list of commit SHAs
        self.branches: dict[tuple[str, str, str], str] = {
            ("fussion-org", "storefront", "main"): "commit_base_main_123456",
            ("acme", "website", "main"): "commit_base_acme_789012",
        }
        # Key: (owner, repo, pr_number) -> PR metadata
        self.pull_requests: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.pr_counter = 100
        # Recorded commits: (owner, repo, branch) -> list of files committed
        self.committed_files: dict[tuple[str, str, str], dict[str, str]] = {}

    def add_repository(self, owner: str, repo: str, default_branch: str = "main") -> None:
        self.repositories[(owner, repo)] = {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "default_branch": default_branch,
            "private": False,
        }
        self.branches[(owner, repo, default_branch)] = f"commit_{owner}_{repo}_init"

    async def get_repository(
        self, owner: str, repo: str, token: str | None = None
    ) -> dict[str, Any]:
        key = (owner, repo)
        if key not in self.repositories:
            raise GitHubAPIError(f"Repository '{owner}/{repo}' not found.", 404)
        return self.repositories[key]

    async def create_branch(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        new_branch: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        base_key = (owner, repo, base_branch)
        if base_key not in self.branches:
            raise GitHubAPIError(f"Base branch '{base_branch}' not found.", 404)
        base_sha = self.branches[base_key]
        self.branches[(owner, repo, new_branch)] = base_sha
        return {
            "ref": f"refs/heads/{new_branch}",
            "object": {"sha": base_sha},
        }

    async def commit_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        commit_message: str,
        files: dict[str, str],
        token: str | None = None,
    ) -> str:
        # Invariant: Never allow committing directly to default branch
        repo_meta = await self.get_repository(owner, repo, token)
        if branch == repo_meta["default_branch"]:
            raise GitHubAPIError(
                f"Direct commits to default branch '{branch}' are prohibited.", 400
            )

        branch_key = (owner, repo, branch)
        if branch_key not in self.branches:
            raise GitHubAPIError(f"Branch '{branch}' not found.", 404)

        # Generate deterministic commit SHA from file contents
        content_hash = hashlib.sha256(
            "".join(sorted(f"{k}:{v}" for k, v in files.items())).encode("utf-8")
        ).hexdigest()
        new_sha = f"commit_{content_hash[:16]}"
        self.branches[branch_key] = new_sha
        self.committed_files[branch_key] = files.copy()
        return new_sha

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
        if (owner, repo, head_branch) not in self.branches:
            raise GitHubAPIError(f"Head branch '{head_branch}' not found.", 404)
        if (owner, repo, base_branch) not in self.branches:
            raise GitHubAPIError(f"Base branch '{base_branch}' not found.", 404)

        self.pr_counter += 1
        pr_number = self.pr_counter
        pr_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}"
        pr_data = {
            "number": pr_number,
            "html_url": pr_url,
            "title": title,
            "body": body,
            "head": {"ref": head_branch},
            "base": {"ref": base_branch},
            "state": "open",
            "merged": False,
        }
        self.pull_requests[(owner, repo, pr_number)] = pr_data
        return pr_data

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        token: str | None = None,
    ) -> dict[str, Any]:
        key = (owner, repo, pr_number)
        if key not in self.pull_requests:
            raise GitHubAPIError(f"Pull request #{pr_number} not found.", 404)
        return self.pull_requests[key]


# Global instance provider: defaults to MockGitProvider for local/dev/tests unless overridden
_current_git_provider: GitProvider = MockGitProvider()


def get_git_provider() -> GitProvider:
    return _current_git_provider


def set_git_provider(provider: GitProvider) -> None:
    global _current_git_provider
    _current_git_provider = provider
