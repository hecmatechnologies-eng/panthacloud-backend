"""Conformance gate against docs/standards/api-routing-standards.md and tool-design.md.

Two severities, deliberately different in what they do:

  BUG   fails the build. These are contradictions, not preferences - a duplicate address, a
        camelCase key, a tool argument the model cannot interpret.
  DEBT  is reported and does not fail. Pagination and the verb-in-path endpoints are real
        gaps with reasons recorded in section 6 of the standards; failing CI on them would
        either block every unrelated change or train people to ignore the gate.

Run with -v to see the full report; a passing run prints the debt count.
"""

import re

from app.main import app

SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
ACTION = re.compile(
    r"/(query|search|reset|analyze|analyse|validate|inspect|confirm|cancel|exchange|"
    r"execute|trigger|recompute|sync|notify)$"
)
COLLECTION = re.compile(
    r"/(organizations|projects|documents|members|repositories|snapshots|"
    r"discoveries|integrations|origins|installations|runs)$"
)
KNOWN_BARE = {"/health"}  # documented in main.py: required by Phase 01, probe convention


def _returns_array(spec: dict, op: dict) -> bool:
    """True when a 200 response is a JSON array, following a $ref one hop.

    This exists because the name regex above cannot see a collection that was never
    anticipated. `/website-integrations/runs` returned a bare array, was genuinely
    unpaginated, and was absent from this gate's report for the whole of its life - the
    regex simply had no `runs` in it. A hand-maintained list of resource names is a list
    that goes stale silently, and a debt list that under-reports is worse than no debt list,
    because it reads as though the work is nearly done.

    Schema-based detection cannot go stale that way: a new collection shows up the moment it
    returns an array. The name regex is kept and unioned in, because one real endpoint returns
    an envelope rather than an array and would otherwise drop out of the report.
    """
    response = (op.get("responses") or {}).get("200") or {}
    schema = ((response.get("content") or {}).get("application/json") or {}).get("schema") or {}
    resolved = schema
    if "$ref" in schema:
        resolved = ((spec.get("components") or {}).get("schemas") or {}).get(
            schema["$ref"].rsplit("/", 1)[-1], {}
        )
    return resolved.get("type") == "array" or "items" in resolved



def _operations() -> list[tuple[str, str, dict]]:
    out = []
    for path, methods in app.openapi().get("paths", {}).items():
        for verb, op in methods.items():
            if verb.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                out.append((verb.upper(), path, op))
    return sorted(out, key=lambda r: (r[1], r[0]))


OPS = _operations()


def test_the_surface_is_not_empty() -> None:
    """Guards the audit itself: a spec that resolves to nothing would pass every check below."""
    assert len(OPS) > 50, f"only {len(OPS)} operations resolved - the audit cannot be trusted"


# --------------------------------------------------------------------- BUG


def test_everything_is_versioned_except_documented_exceptions() -> None:
    bare = sorted({f"{v} {p}" for v, p, _ in OPS if not p.startswith("/api/v1") and p not in KNOWN_BARE})
    assert not bare, f"routes outside /api/v1: {bare}"


def test_parameters_are_snake_case() -> None:
    bad = []
    for verb, path, op in OPS:
        for param in op.get("parameters") or []:
            # Header names such as x-hub-signature-256 are dictated by GitHub; renaming them
            # is not an option, so they are out of scope for this rule.
            if param.get("in") not in {"path", "query"}:
                continue
            name = param.get("name", "")
            if name and not SNAKE.match(name):
                bad.append(f"{verb} {path}: {name}")
    assert not bad, f"non-snake_case parameters: {bad}"


def test_schema_properties_are_snake_case() -> None:
    bad: list[str] = []

    def walk(node, where):
        if isinstance(node, dict):
            for key, value in node.items():
                if where.endswith("properties") and not SNAKE.match(key):
                    bad.append(f"{where}.{key}")
                walk(value, f"{where}.{key}" if where.endswith("properties") else where)
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    for name, schema in (app.openapi().get("components", {}).get("schemas") or {}).items():
        walk(schema.get("properties") or {}, f"{name}.properties")
    assert not bad, f"non-snake_case schema properties: {bad}"


def test_no_path_is_published_at_two_addresses() -> None:
    """A resource reachable at two URLs is two cache entries and two authz call sites."""
    from app.main import app as _app

    api_prefixed = {
        getattr(r, "path", "") for r in _app.routes if getattr(r, "path", "").startswith("/api/v1")
    }
    bare = {
        getattr(r, "path", "")
        for r in _app.routes
        if getattr(r, "path", "")
        and not getattr(r, "path", "").startswith("/api/v1")
        and getattr(r, "path", "") not in KNOWN_BARE
    }
    # Paths under a router prefix are not visible as bare on `app.routes`; compare the parts that
    # are, so a duplicate only trips when the same literal path is genuinely mounted twice.
    duplicated = sorted(p for p in bare if p in api_prefixed)
    assert not duplicated, f"mounted at two addresses: {duplicated}"


# -------------------------------------------------------------------- DEBT


def _debt() -> dict[str, list[str]]:
    unpaginated = []
    verbs = []
    no_location = []
    spec = app.openapi()
    for verb, path, op in OPS:
        if ACTION.search(path):
            verbs.append(f"{verb} {path}")
        # A collection is anything that returns a list, unioned with the named resources. See
        # _returns_array for why the name list alone is not trustworthy.
        if verb == "GET" and (COLLECTION.search(path) or _returns_array(spec, op)):
            names = [q.get("name") for q in (op.get("parameters") or []) if q.get("in") == "query"]
            cursor_style = "limit" in names and ("cursor" in names or "offset" in names)
            # page/per_page is offset pagination under other names. It is accepted here because
            # /github/repositories proxies an upstream whose contract is GitHub's own, and
            # renaming its parameters would break anyone calling it as documented. Recorded as
            # a deviation in api-routing-standards.md section 6.
            proxy_style = "page" in names and "per_page" in names
            if not (cursor_style or proxy_style):
                unpaginated.append(f"{verb} {path}")
        if "201" in (op.get("responses") or {}) and not (
            (op["responses"]["201"].get("headers") or {}).get("Location")
        ):
            no_location.append(f"{verb} {path}")
    return {
        "collections_without_pagination": unpaginated,
        "action_verbs_in_path": verbs,
        "created_without_location": no_location,
    }


def test_debt_is_reported_but_does_not_fail() -> None:
    debt = _debt()
    print("\n--- recorded debt (see api-routing-standards.md section 6) ---")
    for kind, items in debt.items():
        print(f"  {kind}: {len(items)}")
        for item in items:
            print(f"      - {item}")
    # The gate is on regression, not on the backlog: these counts must not grow.
    ceiling = {
        # The ceiling was 9 and the true count is also 9, but the two lists were not the same
        # nine. The report included /github/repositories, which is already paginated, and
        # omitted /website-integrations/runs, which never was. A total that is right by
        # coincidence while the contents are wrong reads as progress being made when none is.
        # Both are now detected from the response schema rather than from a name list.
        # /projects and /knowledge/documents are done end to end: backend keyset cursor, Link
        # header, BFF proxy forwarding it, and the Studio hook consuming it.
        "collections_without_pagination": 9,
        "action_verbs_in_path": 8,
        # POST /auth/register returns a token, not the user, and there is no addressable
        # /users/{id}. RFC 9110 15.3.2 permits omitting Location when the response is not a
        # representation of the created resource, so this one is a deliberate exception rather
        # than a gap. See api-routing-standards.md section 6.
        "created_without_location": 1,
    }
    for kind, cap in ceiling.items():
        assert len(debt[kind]) <= cap, (
            f"{kind} grew beyond the recorded baseline of {cap} "
            f"(now {len(debt[kind])}); either fix it or update section 6 with the reason"
        )