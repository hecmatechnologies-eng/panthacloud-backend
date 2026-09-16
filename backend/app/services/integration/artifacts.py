import json
import posixpath
import re
from collections.abc import Callable
from typing import Any

from app.models.website_integration import (
    DEFAULT_FRAMEWORK_SKILL_ID,
    GENERIC_HTML_SKILL_ID,
)

# Wraps the assistant's configuration values inside generated files. The security scan (FR-097)
# checks code; these are the tenant's own settings — an avatar hosted on their CDN is not an
# "undeclared host", and scanning it blocked every run for any tenant who set one.
CONFIG_BEGIN = "/* FUSSION-CONFIG:BEGIN */"
CONFIG_END = "/* FUSSION-CONFIG:END */"

REACT_BEGIN_IMPORT = "/* FUSSION-ASSISTANT:BEGIN-IMPORTS */"
REACT_END_IMPORT = "/* FUSSION-ASSISTANT:END-IMPORTS */"

REACT_BEGIN_JSX = "{/* FUSSION-ASSISTANT:BEGIN-WIDGET */}"
REACT_END_JSX = "{/* FUSSION-ASSISTANT:END-WIDGET */}"

HTML_BEGIN = "<!-- FUSSION-ASSISTANT:BEGIN -->"
HTML_END = "<!-- FUSSION-ASSISTANT:END -->"

MarkerPair = tuple[str, str]

# What each patcher emits, per file kind. One source: the validator compares a file against its
# own family only, and deriving that from anywhere else is how the two drift apart.
REACT_MARKER_PAIRS: tuple[MarkerPair, ...] = (
    (REACT_BEGIN_IMPORT, REACT_END_IMPORT),
    (REACT_BEGIN_JSX, REACT_END_JSX),
)
HTML_MARKER_PAIRS: tuple[MarkerPair, ...] = ((HTML_BEGIN, HTML_END),)

# Regions of a customer file that Fussion owns; everything outside them belongs to the customer.
MANAGED_BLOCKS = REACT_MARKER_PAIRS + HTML_MARKER_PAIRS

REACT_SUFFIXES = (".tsx", ".jsx", ".ts", ".js", ".mjs", ".cjs", ".mts", ".cts")
HTML_SUFFIXES = (".html", ".htm")


class WidgetInjectionError(Exception):
    """No safe place to put the managed block was found in the customer's file.

    Raised instead of guessing. Appending blind produced a file that does not compile — the
    widget JSX landed after the component's closing brace — and the validator cannot catch it,
    because managed-block content is deliberately excluded from the customer-content comparison.
    """


def marker_pairs_for_path(path: str) -> tuple[MarkerPair, ...]:
    """The one marker family this file may contain. Unknown kinds may contain none.

    Suffixes are matched case-insensitively: `app/layout.TSX` is a React file, and treating it as
    an unknown kind made the patched file trip the validator's foreign-marker check instead.
    """
    lowered = path.lower()
    if lowered.endswith(REACT_SUFFIXES):
        return REACT_MARKER_PAIRS
    if lowered.endswith(HTML_SUFFIXES):
        return HTML_MARKER_PAIRS
    return ()


def source_root_for(target_path: str) -> str:
    """The directory holding the framework's `app/` or `pages/` tree — `""` or `"src/"`.

    Generated files go beside that tree rather than at the repository root. Putting them at the
    root while the layout imported `@/components/...` broke every `src/` layout, because `@/`
    resolves to `src/` there: the module did not exist and the pull request did not build (§3.3).
    """
    # The *last* app/pages segment before the filename, not the first: a monorepo package is
    # often itself called `app` (next-forge's `apps/app`, tamagui's `packages/app`), and taking
    # the first match put generated files outside the framework project root — outside its
    # tsconfig include and its loader scope, so the pull request did not build.
    segments = target_path.split("/")[:-1]
    for index in range(len(segments) - 1, -1, -1):
        if segments[index] in ("app", "pages"):
            return "/".join(segments[:index]) + ("/" if index else "")
    raise WidgetInjectionError(
        f"'{target_path}' is not inside an app/ or pages/ directory, so Fussion cannot tell where "
        "this project's source root is. Point the widget target at the root layout, for example "
        "app/layout.tsx or src/app/layout.tsx."
    )


def relative_import(from_file: str, to_file: str) -> str:
    """A relative module specifier from one file to another, extension stripped.

    Relative rather than `@/…`: the alias depends on a `tsconfig.json` `paths` entry that Fussion
    has not read and cannot assume. A relative path is correct in every project.
    """
    target = posixpath.splitext(to_file)[0]
    specifier = posixpath.relpath(target, posixpath.dirname(from_file) or ".")
    return specifier if specifier.startswith(".") else f"./{specifier}"


def _insert_after_directive_prologue(content: str, block: str) -> str:
    """Insert `block` below any leading `'use client'`-style directive, never above it.

    An import above the directive stops it being a directive, and next-swc then fails the build
    with "'use client' directive must be placed before other expressions" — a non-compiling file
    inside a managed block, which the validator does not inspect.
    """
    lines = content.split("\n")
    insert_at = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*", "*/")):
            continue
        if re.fullmatch(r"""['"]use (client|server|strict)['"]\s*;?""", stripped):
            insert_at = index + 1
            continue
        break
    if insert_at == 0:
        return f"{block}\n{content}"
    return "\n".join([*lines[:insert_at], block, *lines[insert_at:]])


def _sole_closing_tag(content: str, tags: tuple[str, ...], advice: str) -> str:
    """The one closing tag Fussion may insert before, or a refusal.

    Textual matching cannot tell an element from the same characters inside a string literal or a
    comment, so where a candidate appears more than once the honest answer is that the file is
    ambiguous. Guessing the last one corrupted a layout that exported an HTML template string.
    """
    for tag in tags:
        # Case-insensitive: legacy static pages use `</BODY>`, and `marker_pairs_for_path` already
        # treats file kinds case-insensitively. Matching case-sensitively here refused those pages
        # with a message written for a React layout.
        matches = list(re.finditer(re.escape(tag), content, flags=re.IGNORECASE))
        if len(matches) == 1:
            return content[matches[0].start() : matches[0].end()]
        if len(matches) > 1:
            raise WidgetInjectionError(
                f"'{tag}' appears {len(matches)} times, so Fussion cannot tell which one is the "
                "real element — one may be inside a string or a comment. Add the widget by hand, "
                "or point the target at a file with a single shell element."
            )
    raise WidgetInjectionError(f"none of {', '.join(tags)} was found to insert the widget before. {advice}")


def _patch_preserving_line_endings(patch: Callable[[str], str], content: str) -> str:
    """Patch LF-normalised content, then restore the file's dominant line ending."""
    crlf = content.count("\r\n")
    line_ending = "\r\n" if crlf > content.count("\n") - crlf else "\n"
    patched = patch(content.replace("\r\n", "\n"))
    return patched.replace("\n", line_ending) if line_ending != "\n" else patched


def _widget_config(
    public_key: str, script_url: str, assistant_data: dict[str, Any]
) -> dict[str, Any]:
    """The one config shape both loaders emit, so the React and static paths cannot drift apart."""
    return {
        "publicKey": public_key,
        "scriptUrl": script_url,
        "name": str(assistant_data.get("name", "Fussion Assistant")),
        "welcomeMessage": str(
            assistant_data.get("welcome_message", "Hi! How can I help you today?")
        ),
        "brandColor": str(assistant_data.get("brand_color", "#4338CA")),
        "textColor": str(assistant_data.get("text_color", "#FFFFFF")),
        "position": str(assistant_data.get("position", "BOTTOM_RIGHT")),
        # The widget is not injected at all for a switched-off assistant, rather than showing a
        # launcher whose every question the API would refuse with a 503.
        "isEnabled": bool(assistant_data.get("is_enabled", True)),
    }


def generate_react_widget_component(config_import: str = "../../lib/fussion-assistant") -> str:
    """A component that loads the hosted widget (B8).

    It renders nothing of its own. The UI, the shadow root and the isolation live in the bundle
    Fussion serves, so a widget fix reaches every customer without a new pull request — and this
    file only has to inject one script tag.
    """
    return f"""'use client';

import {{ useEffect }} from 'react';
import {{ fussionConfig }} from '{config_import}';

export function FussionAssistant() {{
  useEffect(() => {{
    if (!fussionConfig.isEnabled) {{
      return;
    }}
    const script = document.createElement('script');
    script.src = fussionConfig.scriptUrl;
    script.async = true;
    script.dataset.fussionKey = fussionConfig.publicKey;
    script.dataset.fussionName = fussionConfig.name;
    script.dataset.fussionBrandColor = fussionConfig.brandColor;
    script.dataset.fussionTextColor = fussionConfig.textColor;
    script.dataset.fussionPosition = fussionConfig.position;
    script.dataset.fussionWelcome = fussionConfig.welcomeMessage;
    document.body.appendChild(script);
    return () => {{
      document.body.removeChild(script);
    }};
  }}, []);

  return null;
}}
"""


def generate_react_config_ts(
    public_key: str, script_url: str, assistant_data: dict[str, Any]
) -> str:
    """What the loader needs: where the widget lives, which assistant it is, and how it looks."""
    serialized = json.dumps(_widget_config(public_key, script_url, assistant_data), indent=2)

    return f"""// Auto-generated by Fussion. Edit your assistant's settings in Fussion, not here:
// this file is replaced on the next integration run.

export const fussionConfig = {CONFIG_BEGIN} {serialized} {CONFIG_END} as const;

export type FussionConfig = typeof fussionConfig;
"""


def patch_react_layout(
    content: str, component_import: str = "../components/fussion/FussionAssistant"
) -> str:
    """
    Patches a Next.js layout (app/layout.tsx) idempotently using managed markers.
    """
    import_statement = (
        f"{REACT_BEGIN_IMPORT}\n"
        f"import {{ FussionAssistant }} from '{component_import}';\n"
        f"{REACT_END_IMPORT}"
    )

    jsx_statement = (
        f"\n        {REACT_BEGIN_JSX}\n"
        f"        <FussionAssistant />\n"
        f"        {REACT_END_JSX}"
    )

    # 1. Check if import marker already exists
    import_pattern = re.escape(REACT_BEGIN_IMPORT) + r".*?" + re.escape(REACT_END_IMPORT)
    if re.search(import_pattern, content, flags=re.DOTALL):
        new_content = re.sub(import_pattern, import_statement, content, flags=re.DOTALL)
    else:
        new_content = _insert_after_directive_prologue(content, import_statement)

    # 2. Check if JSX marker already exists
    jsx_pattern = re.escape(REACT_BEGIN_JSX) + r".*?" + re.escape(REACT_END_JSX)
    if re.search(jsx_pattern, new_content, flags=re.DOTALL):
        return re.sub(jsx_pattern, jsx_statement.strip(), new_content, flags=re.DOTALL)

    # Exactly one candidate, or refuse. Patching every occurrence corrupted layouts with a
    # `</body>` in a string; patching the last one corrupted layouts that export an HTML template
    # after the component. Neither is detectable afterwards: the validator does not inspect
    # managed-block content, so a non-compiling file would ship in Fussion's own pull request.
    closing_tag = _sole_closing_tag(
        new_content,
        ("</body>", "</main>"),
        "The file may delegate its shell to another component — integrate that component instead. "
        "Note that a pages-router `_app.tsx` has no shell element; use `_document.tsx`'s sibling "
        "layout or a component it renders.",
    )
    head, separator, tail = new_content.partition(closing_tag)
    return f"{head}{jsx_statement}\n      {separator}{tail}"


def generate_html_widget_script(
    public_key: str, script_url: str, assistant_data: dict[str, Any]
) -> str:
    """A static page's loader: inject the hosted widget with this assistant's settings.

    A static site has no component to hook into, so this file is the loader the page's script tag
    pulls in.
    """
    serialized = json.dumps(_widget_config(public_key, script_url, assistant_data), indent=2)

    # No console logging: this runs on the customer's production site, where their console is
    # theirs. Configuration values are fenced so the security scan checks code, not settings.
    return f"""// Auto-generated by Fussion. Edit your assistant's settings in Fussion, not here:
// this file is replaced on the next integration run.
(function() {{
  var config = {CONFIG_BEGIN} {serialized} {CONFIG_END};
  if (!config.isEnabled) {{
    return;
  }}
  var script = document.createElement('script');
  script.src = config.scriptUrl;
  script.async = true;
  script.dataset.fussionKey = config.publicKey;
  script.dataset.fussionName = config.name;
  script.dataset.fussionBrandColor = config.brandColor;
  script.dataset.fussionTextColor = config.textColor;
  script.dataset.fussionPosition = config.position;
  script.dataset.fussionWelcome = config.welcomeMessage;
  document.body.appendChild(script);
}})();
"""


def patch_html_index(content: str, script_src: str = "./fussion-assistant.js") -> str:
    """Patches an HTML file (index.html) idempotently using managed markers.

    `script_src` is relative by default. An absolute `/fussion-assistant.js` 404s whenever the
    page is not served from the repository root — `public/index.html` under Vite, `docs/index.html`
    on GitHub Pages, or any project-site deployment served from `/repo/`.
    """
    script_tag = f'{HTML_BEGIN}\n<script src="{script_src}"></script>\n{HTML_END}'

    marker_pattern = re.escape(HTML_BEGIN) + r".*?" + re.escape(HTML_END)
    if re.search(marker_pattern, content, flags=re.DOTALL):
        return re.sub(marker_pattern, script_tag, content, flags=re.DOTALL)

    # Exactly one `</body>`, or refuse: a second one may be inside a script string, and inserting
    # there corrupts the page while hiding inside a managed block the validator does not compare.
    closing_tag = _sole_closing_tag(
        content,
        ("</body>",),
        "Add the script tag by hand, or point the target at a page with a single </body> element.",
    )
    head, separator, tail = content.partition(closing_tag)
    # A marker must stand alone on its line, and minified HTML — the common case — has no newline
    # before `</body>`. Without this the run refused, blaming the customer's file.
    prefix = "" if head.endswith("\n") or not head else "\n"
    return f"{head}{prefix}  {script_tag}\n{separator}{tail}"


def generate_artifacts(
    *,
    public_key: str,
    script_url: str,
    assistant_data: dict[str, Any],
    framework_skill_id: str,
    widget_target_path: str,
    existing_target_content: str,
) -> dict[str, str]:
    """
    Generates all required files for website integration deterministically.
    Returns a mapping of relative file paths to their string contents.
    The widget target is always patched from its real contents, which the caller must have read.

    What is generated is a *loader*, not the widget: the bundle Fussion serves
    (`GET /api/v1/public/widget.js`) owns the UI, so a widget fix reaches every customer at once
    instead of through a pull request each.
    """
    files: dict[str, str] = {}

    if framework_skill_id == DEFAULT_FRAMEWORK_SKILL_ID:
        # Generated files sit beside the project's app/ or pages/ tree, and the imports between
        # them are relative, so neither depends on a `@/` alias Fussion has not verified.
        root = source_root_for(widget_target_path)
        component_path = f"{root}components/fussion/FussionAssistant.tsx"
        config_path = f"{root}lib/fussion-assistant.ts"

        files[component_path] = generate_react_widget_component(
            config_import=relative_import(component_path, config_path)
        )
        files[config_path] = generate_react_config_ts(public_key, script_url, assistant_data)
        files[widget_target_path] = _patch_preserving_line_endings(
            lambda content: patch_react_layout(
                content, component_import=relative_import(widget_target_path, component_path)
            ),
            existing_target_content,
        )

    elif framework_skill_id == GENERIC_HTML_SKILL_ID:
        # Patch the file that was read. Substituting `index.html` for any other target generated a
        # file the plan never declared, so the run failed with the plan taking the blame.
        if not widget_target_path.lower().endswith(HTML_SUFFIXES):
            raise WidgetInjectionError(
                f"'{widget_target_path}' is not an HTML file. For a static site, point the widget "
                "target at the page that should carry the assistant, such as index.html."
            )
        # The script sits beside the page that loads it, referenced relatively, so it resolves
        # whatever directory the site is served from.
        script_path = posixpath.join(posixpath.dirname(widget_target_path), "fussion-assistant.js")
        files[script_path] = generate_html_widget_script(public_key, script_url, assistant_data)
        files[widget_target_path] = _patch_preserving_line_endings(
            lambda content: patch_html_index(content, script_src="./fussion-assistant.js"),
            existing_target_content,
        )

    return files
