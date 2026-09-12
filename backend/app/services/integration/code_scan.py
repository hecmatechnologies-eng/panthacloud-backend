"""Security scan of the code Fussion ships to a customer's site (FR-097).

Fussion writes JavaScript that runs on someone else's domain, in their visitors' browsers. That
is an npm-package trust position: a poisoned repository README or file comment persuading the
step-D coding agent to emit an exfiltrating widget would backdoor the *customer's* site, in a pull
request carrying Fussion's name (AGENT-ARCHITECTURE §11).

Scope matters as much as the patterns. Apply this to files Fussion creates, and to the content of
Fussion-managed blocks in files it modifies — never to a customer's own code, which is theirs and
may legitimately do any of this.
"""

import json
import re

from app.services.integration.artifacts import CONFIG_BEGIN, CONFIG_END

# Hosts generated code may talk to. Relative URLs are always allowed: the widget calls back to the
# origin that served it. Extend this list only with a Fussion-owned origin.
ALLOWED_HOSTS = ("fussion.dev", "cdn.fussion.dev")

# Schemes that carry executable or opaque payloads. A `data:` or `javascript:` script source is
# the FR-097 category exactly, and treating either as "relative because it has no //" is how the
# first version of this module let them through.
_OPAQUE_SCHEMES = ("data:", "javascript:", "vbscript:", "blob:", "filesystem:")
_RELATIVE_PREFIXES = ("/", "./", "../", "#", "?")

_URL_IN_STRING = re.compile(r"""["'`]([^"'`\s]*(?://|:)[^"'`\s]*)["'`]""")
_RESOURCE_ATTRIBUTE = re.compile(
    r"""<[a-z][^>]*?\s(?:src|href|action|formaction|poster|data)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE | re.DOTALL,
)
_NETWORK_CALL = re.compile(
    r"""\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|navigator\.sendBeacon|importScripts)\b"""
)
_INLINE_HANDLER = re.compile(r"""\son[a-z]+\s*=\s*["'{]""", re.IGNORECASE)

_FORBIDDEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\beval\s*\("), "dynamic evaluation (eval)"),
    (re.compile(r"\bnew\s+Function\s*\("), "dynamic evaluation (new Function)"),
    (re.compile(r"\bdocument\.write\s*\("), "document.write"),
    (re.compile(r"\batob\s*\(|\bbtoa\s*\(|\bfromCharCode\s*\("), "obfuscated or encoded payload"),
    (re.compile(r"\bdocument\.cookie\b"), "cookie access"),
    (re.compile(r"\blocalStorage\b|\bsessionStorage\b"), "host-page storage access"),
    (re.compile(r"\bpostMessage\s*\([^)]*\*"), "postMessage to any origin"),
    (re.compile(r"\bdocument\.forms\b|\bquerySelectorAll\s*\(\s*['\"]input"), "host-page form access"),
    (re.compile(r"\binnerHTML\s*="), "innerHTML assignment"),
    (re.compile(r"\bsetTimeout\s*\(\s*['\"]|\bsetInterval\s*\(\s*['\"]"), "string-bodied timer"),
)


def foreign_target(url: str) -> str | None:
    """Describe the non-allowed origin `url` points at, or None if it is acceptable.

    One implementation, used by every caller in this module. The previous two copies disagreed
    about protocol-relative URLs, which is precisely the case that matters.
    """
    value = url.strip()
    if not value:
        return None

    lowered = value.lower()
    for scheme in _OPAQUE_SCHEMES:
        if lowered.startswith(scheme):
            return f"{scheme.rstrip(':')} URI"

    if value.startswith("//"):  # protocol-relative: the browser fetches this cross-origin
        remainder = value[2:]
    elif "://" in value:
        remainder = value.split("://", 1)[1]
    elif value.startswith(_RELATIVE_PREFIXES):
        return None
    elif ":" in value.split("/", 1)[0]:
        return f"{value.split(':', 1)[0]} URI"
    else:
        return None  # bare relative path

    host = remainder.split("/")[0].split("?")[0].split("#")[0].split("@")[-1].split(":")[0].lower()
    if not host:
        return None
    if any(host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_HOSTS):
        return None
    return host


def _split_config(content: str) -> tuple[str, list[str]]:
    """Separate code from fenced configuration values.

    Generated files embed the tenant's own settings — an avatar hosted on their CDN is not an
    "undeclared host". Scanning those values as code meant any tenant who filled in the avatar
    field could never obtain a pull request. Code is scanned for everything; configuration is
    scanned only for what is dangerous in data.
    """
    fence = re.compile(re.escape(CONFIG_BEGIN) + r"(.*?)" + re.escape(CONFIG_END), re.DOTALL)
    values = fence.findall(content)
    return fence.sub(" {} ", content), values


def _config_issues(path: str, blocks: list[str]) -> list[str]:
    """Configuration may carry URLs to anywhere, but never an executable scheme.

    Parsed as JSON rather than matched with a regex: a regex over quoted runs skipped any value
    containing an escaped quote, so `javascript:alert("x")` passed while `javascript:alert(1)` was
    caught. The scheme list is the one `foreign_target` uses — spelling it twice is how the two
    disagreed.
    """
    issues: list[str] = []
    for block in blocks:
        try:
            parsed = json.loads(block.strip())
        except json.JSONDecodeError:
            issues.append(
                f"Configuration in '{path}' is not valid JSON, so it cannot be checked. This is a "
                "Fussion bug; please report it."
            )
            continue
        for value in _strings_in(parsed):
            lowered = value.strip().lower()
            if lowered.startswith(_OPAQUE_SCHEMES):
                issues.append(
                    f"Configuration in '{path}' contains a {lowered.split(':', 1)[0]}: URL, which "
                    "must never be rendered into a page."
                )
    return issues


def _strings_in(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [found for item in value.values() for found in _strings_in(item)]
    if isinstance(value, list):
        return [found for item in value for found in _strings_in(item)]
    return []


def scan_generated_code(path: str, content: str) -> list[str]:
    """Return the reasons `content` must not ship, or an empty list if it is acceptable."""
    content, config_blocks = _split_config(content)
    issues: list[str] = _config_issues(path, config_blocks)

    for pattern, reason in _FORBIDDEN:
        if pattern.search(content):
            issues.append(f"Generated code in '{path}' uses {reason}.")

    # Markup resources: `<script src>`, but also `<img src>`, `<link href>`, `<iframe src>` and
    # form actions. A one-pixel image to a foreign host is the cheapest exfiltration channel there
    # is, and needs no network-call token to fire.
    for url in _RESOURCE_ATTRIBUTE.findall(content):
        target = foreign_target(url)
        if target:
            issues.append(f"Generated code in '{path}' loads a resource from a foreign origin: {target}.")

    if _INLINE_HANDLER.search(content):
        issues.append(f"Generated code in '{path}' contains an inline event handler.")

    # URL literals in script: checked whether or not a fetch/XHR token is present, because
    # `new Image().src = ...` and a stylesheet injection are neither.
    for url in _URL_IN_STRING.findall(content):
        target = foreign_target(url)
        if target:
            issues.append(f"Generated code in '{path}' references an undeclared host: {target}.")

    # A network call whose destination is computed rather than written down. Not provably wrong,
    # but generated code has no reason to hide where it connects.
    if (
        _NETWORK_CALL.search(content)
        and not any("undeclared host" in issue for issue in issues)
        and re.search(r"""\b(?:fetch|WebSocket|EventSource)\s*\(\s*[^'"`)\s]""", content)
    ):
        issues.append(
            f"Generated code in '{path}' makes a network call to a computed destination; "
            "generated code must name its host."
        )

    return _deduplicated(issues)


def _deduplicated(issues: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            unique.append(issue)
    return unique
