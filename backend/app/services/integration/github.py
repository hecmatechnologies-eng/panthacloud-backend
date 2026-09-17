import asyncio
import base64
import hashlib
import logging
import random
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.services.integration.git_provider import GitProvider

logger = logging.getLogger("fussion.integration.github")


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubUnavailableError(GitHubAPIError):
    """GitHub could not answer right now (network, rate limit, 5xx); a later retry may succeed."""


def _is_rate_limited(resp: httpx.Response) -> bool:
    return resp.status_code == 429 or (
        resp.status_code == 403
        and (
            resp.headers.get("x-ratelimit-remaining") == "0"
            or "retry-after" in resp.headers
            or "rate limit" in resp.text.lower()
        )
    )


def _raise_for_status(resp: httpx.Response, action: str) -> None:
    """Raise for a failed response; transient failures raise GitHubUnavailableError."""
    if resp.status_code < 400:
        return
    if _is_rate_limited(resp):
        raise GitHubUnavailableError(
            f"GitHub rate limit reached while {action}; try again later.", resp.status_code
        )
    if resp.status_code >= 500:
        raise GitHubUnavailableError(
            f"GitHub is unavailable ({resp.status_code}) while {action}.", resp.status_code
        )
    if resp.status_code in (401, 403):
        raise GitHubAPIError(
            f"GitHub authentication error while {action}: {resp.text}", resp.status_code
        )
    raise GitHubAPIError(f"GitHub API error while {action}: {resp.text}", resp.status_code)


def _json_field(resp: httpx.Response, keys: tuple[str, ...], what: str) -> str:
    """Read a nested field from a GitHub response, classifying the failure rather than KeyError-ing.

    The write path used to index straight into `.json()`, so a 403 or a 422 surfaced to the user as
    `Integration pipeline execution failed: 'sha'`, naming nothing and suggesting nothing.
    """
    _raise_for_status(resp, f"reading the {what}")
    value: object = resp.json()
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise GitHubAPIError(
                f"GitHub returned an unexpected response for the {what}: '{key}' is missing.",
                resp.status_code,
            )
        value = value[key]
    if not isinstance(value, str):
        raise GitHubAPIError(
            f"GitHub returned an unexpected {what}: expected a string, got {type(value).__name__}.",
            resp.status_code,
        )
    return value


def assert_safe_repo_path(path: str) -> None:
    """Reject any path that could address something other than one file inside the repository."""
    if (
        not path
        or "\\" in path
        or "\0" in path
        or any(segment in ("", ".", "..") for segment in path.split("/"))
    ):
        raise GitHubAPIError(
            f"Invalid repository file path '{path}'. "
            "Use a relative path such as 'app/layout.tsx'.",
            400,
        )


class GitHubProvider(GitProvider):
    """
    Production GitHub REST API provider.
    Operates strictly as data via HTTP; never clones or executes repository code.
    """

    def __init__(
        self,
        base_url: str = "https://api.github.com",
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

    def _headers(self, token: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Fussion-Control-Plane",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request(
        self,
        method: str,
        url: str,
        token: str | None,
        action: str,
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        """Issue an HTTP request to GitHub with exponential backoff retries for transient errors."""
        retries = self._max_retries
        # In test environments using a mock transport, skip artificial delays
        backoff = 0.0 if self._transport is not None else self._retry_backoff

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(transport=self._transport) as client:
                    resp = await client.request(
                        method=method,
                        url=url,
                        headers=self._headers(token),
                        params=params,
                        json=json,
                        timeout=15.0,
                    )
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < retries:
                    delay = backoff * (2**attempt) + random.uniform(0, 0.1) if backoff > 0 else 0.0
                    logger.warning(
                        "GitHub request '%s %s' failed (%s); retrying (%d/%d) in %.2fs...",
                        method,
                        url,
                        exc,
                        attempt + 1,
                        retries,
                        delay,
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                raise GitHubUnavailableError(
                    f"Could not reach GitHub while {action}: {exc}", 503
                ) from exc

            # Transient responses: rate limit (429 or 403 secondary) or server error (>= 500)
            if (_is_rate_limited(resp) or resp.status_code >= 500) and attempt < retries:
                if self._transport is not None or backoff == 0.0:
                    delay = 0.0
                else:
                    retry_after = resp.headers.get("retry-after")
                    if retry_after and retry_after.isdigit():
                        delay = min(float(retry_after), 10.0)
                    else:
                        delay = backoff * (2**attempt) + random.uniform(0, 0.1)

                logger.warning(
                    "GitHub request '%s %s' returned status %s; retrying (%d/%d) in %.2fs...",
                    method,
                    url,
                    resp.status_code,
                    attempt + 1,
                    retries,
                    delay,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                continue

            return resp

        if last_error:
            raise GitHubUnavailableError(
                f"Could not reach GitHub while {action}: {last_error}", 503
            ) from last_error
        raise GitHubUnavailableError(f"GitHub is unavailable while {action}.", 503)

    async def _get(
        self,
        url: str,
        token: str | None,
        action: str,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request("GET", url, token, action, params=params)

    @staticmethod
    def _json(resp: httpx.Response, action: str) -> Any:
        try:
            return resp.json()
        except ValueError as exc:
            raise GitHubUnavailableError(
                f"GitHub returned an unreadable response while {action}.", 502
            ) from exc

    async def get_repository(
        self, owner: str, repo: str, token: str | None = None
    ) -> dict[str, Any]:
        action = f"reading repository {owner}/{repo}"
        resp = await self._get(f"{self.base_url}/repos/{owner}/{repo}", token, action)
        if resp.status_code == 404:
            raise GitHubAPIError(f"Repository {owner}/{repo} not found on GitHub.", 404)
        _raise_for_status(resp, action)
        return self._json(resp, action)

    async def get_branch_head(
        self, owner: str, repo: str, branch: str, token: str | None = None
    ) -> str:
        action = f"resolving branch '{branch}'"
        url = f"{self.base_url}/repos/{owner}/{repo}/git/ref/heads/{quote(branch)}"
        resp = await self._get(url, token, action)
        if resp.status_code == 404:
            raise GitHubAPIError(f"Branch '{branch}' not found in {owner}/{repo}.", 404)
        _raise_for_status(resp, action)
        data = self._json(resp, action)
        try:
            return data["object"]["sha"]
        except (KeyError, TypeError) as exc:
            raise GitHubUnavailableError(
                f"GitHub returned an unreadable response while {action}.", 502
            ) from exc

    async def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        token: str | None = None,
    ) -> str | None:
        assert_safe_repo_path(path)
        action = f"reading '{path}'"
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{quote(path)}"
        resp = await self._get(url, token, action, params={"ref": ref})
        # GitHub also answers 404 for an unknown ref; callers treat both as "not there".
        if resp.status_code == 404:
            return None
        _raise_for_status(resp, action)

        data = self._json(resp, action)
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubAPIError(f"'{path}' is not a regular file in {owner}/{repo}@{ref}.", 400)
        if data.get("encoding") != "base64":
            # The contents API omits the body of files larger than 1 MB.
            raise GitHubAPIError(f"'{path}' is too large to read (over 1 MB).", 400)
        try:
            return base64.b64decode(data["content"]).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubAPIError(f"'{path}' is not a UTF-8 text file.", 400) from exc

    async def create_branch(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        new_branch: str,
        base_sha: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        # Branch from the commit the caller read. Required, never re-resolved here: that is the
        # read-then-branch race of CLAUDE.md §3.1.
        action = f"creating branch '{new_branch}'"
        create_url = f"{self.base_url}/repos/{owner}/{repo}/git/refs"
        body = {"ref": f"refs/heads/{new_branch}", "sha": base_sha}
        create_resp = await self._request("POST", create_url, token, action, json=body)
        if create_resp.status_code not in (200, 201):
            _raise_for_status(create_resp, action)
            raise GitHubAPIError(
                f"Failed to create branch '{new_branch}': {create_resp.text}",
                create_resp.status_code,
            )
        return self._json(create_resp, action)

    async def commit_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        commit_message: str,
        files: dict[str, str],
        token: str | None = None,
    ) -> str:
        for path in files:
            # Every path goes through the same containment check as a read. Today these are the
            # validated target plus Fussion's own files; a step-D ChangeSet arrives here too.
            assert_safe_repo_path(path)

        # 0. Never commit to the repository's default branch (CLAUDE.md §4.7). The mock has
        # always refused this; the real provider did not, which made the fake stricter than
        # the thing it stands in for, so no test could catch a caller that got it wrong.
        repo_resp = await self._request(
            "GET", f"{self.base_url}/repos/{owner}/{repo}", token, "reading the repository's default branch"
        )
        _raise_for_status(repo_resp, "reading the repository's default branch")
        if repo_resp.json().get("default_branch") == branch:
            raise GitHubAPIError(
                f"Refusing to commit directly to the default branch '{branch}'. Fussion "
                "commits to an integration branch and opens a pull request.",
                422,
            )

        # 1. Get branch commit SHA
        ref_url = f"{self.base_url}/repos/{owner}/{repo}/git/ref/heads/{branch}"
        ref_resp = await self._request("GET", ref_url, token, f"reading branch '{branch}'")
        if ref_resp.status_code != 200:
            _raise_for_status(ref_resp, f"reading branch '{branch}'")
            raise GitHubAPIError(f"Branch '{branch}' not found: {ref_resp.text}", ref_resp.status_code)
        latest_commit_sha = _json_field(ref_resp, ("object", "sha"), "branch reference")

        # 2. Get latest commit to find base tree
        commit_url = f"{self.base_url}/repos/{owner}/{repo}/git/commits/{latest_commit_sha}"
        commit_resp = await self._request("GET", commit_url, token, "reading base commit")
        base_tree_sha = _json_field(commit_resp, ("tree", "sha"), "base commit")

        # 3. Create blobs & tree items
        tree_items = []
        for path, content in files.items():
            blob_resp = await self._request(
                "POST",
                f"{self.base_url}/repos/{owner}/{repo}/git/blobs",
                token,
                f"creating blob for '{path}'",
                json={"content": content, "encoding": "utf-8"},
            )
            blob_sha = _json_field(blob_resp, ("sha",), f"blob for '{path}'")
            tree_items.append(
                {"path": path, "mode": "100644", "type": "blob", "sha": blob_sha}
            )

        # 4. Create new tree
        tree_resp = await self._request(
            "POST",
            f"{self.base_url}/repos/{owner}/{repo}/git/trees",
            token,
            "creating git tree",
            json={"base_tree": base_tree_sha, "tree": tree_items},
        )
        new_tree_sha = _json_field(tree_resp, ("sha",), "tree")

        # 5. Create new commit
        new_commit_resp = await self._request(
            "POST",
            f"{self.base_url}/repos/{owner}/{repo}/git/commits",
            token,
            "creating commit",
            json={
                "message": commit_message,
                "tree": new_tree_sha,
                "parents": [latest_commit_sha],
            },
        )
        new_commit_sha = _json_field(new_commit_resp, ("sha",), "commit")

        # 6. Update reference
        patch_resp = await self._request(
            "PATCH",
            ref_url,
            token,
            f"updating branch '{branch}' reference",
            json={"sha": new_commit_sha, "force": False},
        )
        if patch_resp.status_code != 200:
            _raise_for_status(patch_resp, f"updating branch '{branch}' reference")
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
        action = "creating pull request"
        resp = await self._request("POST", url, token, action, json=payload)
        if resp.status_code not in (200, 201):
            _raise_for_status(resp, action)
            raise GitHubAPIError(f"Failed to create pull request: {resp.text}", resp.status_code)
        return self._json(resp, action)

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        token: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        action = f"reading pull request #{pr_number}"
        resp = await self._request("GET", url, token, action)
        if resp.status_code == 404:
            raise GitHubAPIError(f"Pull request #{pr_number} not found.", 404)
        if resp.status_code >= 400:
            _raise_for_status(resp, action)
            raise GitHubAPIError(f"GitHub API error: {resp.text}", resp.status_code)
        return self._json(resp, action)


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
        # Repository contents per commit: (owner, repo, commit_sha) -> {path: content}
        self.trees: dict[tuple[str, str, str], dict[str, str]] = {}
        # Commit graph: commit_sha -> parent commit_sha
        self.parents: dict[str, str] = {}

    def add_repository(self, owner: str, repo: str, default_branch: str = "main") -> None:
        self.repositories[(owner, repo)] = {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "default_branch": default_branch,
            "private": False,
        }
        self.branches[(owner, repo, default_branch)] = f"commit_{owner}_{repo}_init"

    def add_file(
        self, owner: str, repo: str, path: str, content: str, branch: str | None = None
    ) -> None:
        branch = branch or self.repositories[(owner, repo)]["default_branch"]
        head = self.branches[(owner, repo, branch)]
        self.trees.setdefault((owner, repo, head), {})[path] = content

    async def get_repository(
        self, owner: str, repo: str, token: str | None = None
    ) -> dict[str, Any]:
        key = (owner, repo)
        if key not in self.repositories:
            raise GitHubAPIError(f"Repository '{owner}/{repo}' not found.", 404)
        return self.repositories[key]

    async def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        token: str | None = None,
    ) -> str | None:
        assert_safe_repo_path(path)
        commit_sha = self.branches.get((owner, repo, ref), ref)  # ref: branch name or SHA
        return self.trees.get((owner, repo, commit_sha), {}).get(path)

    async def get_branch_head(
        self, owner: str, repo: str, branch: str, token: str | None = None
    ) -> str:
        key = (owner, repo, branch)
        if key not in self.branches:
            raise GitHubAPIError(f"Branch '{branch}' not found in {owner}/{repo}.", 404)
        return self.branches[key]

    async def create_branch(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        new_branch: str,
        base_sha: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        base_key = (owner, repo, base_branch)
        if base_key not in self.branches:
            raise GitHubAPIError(f"Base branch '{base_branch}' not found.", 404)
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

        # Generate deterministic commit SHA from the parent and file contents
        parent_sha = self.branches[branch_key]
        content_hash = hashlib.sha256(
            (parent_sha + "".join(sorted(f"{k}:{v}" for k, v in files.items()))).encode("utf-8")
        ).hexdigest()
        new_sha = f"commit_{content_hash[:16]}"
        self.branches[branch_key] = new_sha
        self.committed_files[branch_key] = files.copy()
        self.trees[(owner, repo, new_sha)] = {**self.trees.get((owner, repo, parent_sha), {}), **files}
        self.parents[new_sha] = parent_sha
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


class _UnconfiguredGitProvider:
    """What a process gets before `configure_git_provider()` runs. Every method refuses.

    The default used to be a `MockGitProvider`, which *fabricates* a commit SHA and a plausible
    pull-request URL. Any process that skipped `lifespan` — a future worker — would therefore
    record `PR_CREATED` with a dead link and no error: a silent fallback, which §4.10 prohibits
    outright. Failing here makes "the mock is only for tests" structural instead of conventional.

    Deliberately not a `GitProvider` subclass: the Protocol's method bodies are `...`, so an
    unoverridden method would return `None` and `__getattr__` would never be consulted — a silent
    wrong answer instead of a loud refusal. Each method is spelled out for that reason.
    """

    _MESSAGE = (
        "No git provider is configured in this process. Call configure_git_provider() during "
        "startup, or set_git_provider(MockGitProvider()) in a test."
    )

    async def _refuse(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(self._MESSAGE)

    # `async def`, matching the Protocol: a sync raise would also surface, but an awaiting caller
    # should not have to care which kind of callable refused it.
    get_repository = _refuse
    get_file_contents = _refuse
    get_branch_head = _refuse
    create_branch = _refuse
    commit_files = _refuse
    create_pull_request = _refuse
    get_pull_request = _refuse


def _default_provider() -> GitProvider:
    """Tests and local development get the mock; anything else must configure a provider."""
    if settings.may_generate_dev_keys:
        return MockGitProvider()
    return _UnconfiguredGitProvider()


# Replaced at startup by configure_git_provider(), and by tests with an explicit mock.
_current_git_provider: GitProvider = _default_provider()


def get_git_provider() -> GitProvider:
    return _current_git_provider


def set_git_provider(provider: GitProvider) -> None:
    global _current_git_provider
    _current_git_provider = provider
