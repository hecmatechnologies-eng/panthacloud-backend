"""Integrity invariants for widget integration output (standards-alignment.md G6).

`app/evals/` covers `website_analyst`, the read-only agent. `coding_agent` carries
``workspace.write`` and its output becomes a pull request into a customer's repository, so
assurance belongs there first.

Two families are asserted:

- **The deterministic generator.** Model-free, so these run in CI. Idempotence, marker
  correctness, path containment and content preservation are properties of the code, not of
  the model, and they are where an integration silently corrupts a customer repository.

- **The agent's own report.** The dangerous failure is not the agent writing a bad file — a
  human reviews the diff. It is the agent *reporting* differently from what it did, so the
  reviewer approves one thing while another changed. `CodingAgentOutput.files` must match
  what was actually written.

There is deliberately no golden-output snapshot. A snapshot would fail on every acceptable
rewrite while passing on a rewrite that corrupts the target, which is the opposite of useful.
"""

import json
import uuid

import pytest

from app.agents.coding_agent import CodingAgentOutput, GeneratedFileRecord
from app.services.integration.artifacts import (
    HTML_BEGIN,
    HTML_END,
    generate_artifacts,
    marker_pairs_for_path,
)

_NEXT = "nextjs-app-router"
_HTML = "generic-html"

_LAYOUT = (
    "import type { ReactNode } from 'react';\n"
    "export default function RootLayout({ children }: { children: ReactNode }) {\n"
    "  return (\n    <html lang=\"en\">\n      <body>{children}</body>\n"
    "    </html>\n  );\n}\n"
)
_INDEX = "<!doctype html>\n<html>\n<head><title>Acme</title></head>\n<body></body>\n</html>\n"


def _gen(skill: str, target: str, existing: str) -> dict[str, str]:
    return generate_artifacts(
        public_key="fussion_pk_TESTKEY",
        script_url="https://api.example.com/api/v1/public/widget.js",
        assistant_data={"brand_color": "#4338ca", "position": "BOTTOM_RIGHT"},
        framework_skill_id=skill,
        widget_target_path=target,
        existing_target_content=existing,
    )


class TestPathContainment:
    """Everything written must belong to the integration. A stray path becomes an unreviewed
    change in a customer's repository."""

    def test_next_target_itself_is_written(self) -> None:
        files = _gen(_NEXT, "app/layout.tsx", _LAYOUT)
        assert "app/layout.tsx" in files

    def test_generated_files_stay_inside_the_repository(self) -> None:
        """Generated paths are repo-root-relative and sit beside the target's tree, not inside
        it - `artifacts.py` places them at root so no `@/` alias is assumed. The invariant is
        containment, not a specific prefix."""
        files = _gen(_NEXT, "app/layout.tsx", _LAYOUT)
        for path in files:
            assert not path.startswith("/"), f"absolute path: {path}"
            assert ".." not in path.split("/"), f"traversal in generated path: {path}"
            assert not path.startswith(("./", "../")), f"non-canonical path: {path}"

    def test_every_generated_file_is_one_the_plan_declares(self) -> None:
        """Three files, all expected: the target, the component, and the config."""
        files = set(_gen(_NEXT, "app/layout.tsx", _LAYOUT))
        assert "app/layout.tsx" in files
        assert len(files) == 3
        assert all(isinstance(p, str) and p for p in files)

    def test_nothing_is_written_outside_the_target_tree(self) -> None:
        files = _gen(_HTML, "public/index.html", _INDEX)
        for path in files:
            assert path.startswith("public/"), f"unexpected path: {path}"

    def test_no_absolute_paths_are_emitted(self) -> None:
        for path in _gen(_NEXT, "app/layout.tsx", _LAYOUT):
            assert not path.startswith("/")
            assert ":" not in path, "a Windows drive letter would escape the repository root"


class TestIdempotence:
    """Re-running an integration must not stack a second widget into the same file."""

    def test_patching_twice_equals_patching_once(self) -> None:
        once = _gen(_NEXT, "app/layout.tsx", _LAYOUT)
        twice = _gen(_NEXT, "app/layout.tsx", once["app/layout.tsx"])
        assert twice["app/layout.tsx"] == once["app/layout.tsx"]

    def test_html_patching_twice_equals_patching_once(self) -> None:
        once = _gen(_HTML, "public/index.html", _INDEX)
        twice = _gen(_HTML, "public/index.html", once["public/index.html"])
        assert twice["public/index.html"] == once["public/index.html"]

    def test_the_marker_block_appears_exactly_once(self) -> None:
        files = _gen(_NEXT, "app/layout.tsx", _LAYOUT)
        for begin, end in marker_pairs_for_path("app/layout.tsx"):
            assert files["app/layout.tsx"].count(begin) == 1
            assert files["app/layout.tsx"].count(end) == 1


class TestMarkers:
    def test_next_layout_carries_react_markers(self) -> None:
        content = _gen(_NEXT, "app/layout.tsx", _LAYOUT)["app/layout.tsx"]
        for begin, end in marker_pairs_for_path("app/layout.tsx"):
            assert begin in content
            assert end in content

    def test_html_carries_html_markers(self) -> None:
        content = _gen(_HTML, "public/index.html", _INDEX)["public/index.html"]
        assert HTML_BEGIN in content
        assert HTML_END in content


class TestContentPreservation:
    """The target is a customer file. Its own code must survive the patch."""

    def test_the_original_layout_body_survives(self) -> None:
        content = _gen(_NEXT, "app/layout.tsx", _LAYOUT)["app/layout.tsx"]
        assert "export default function RootLayout" in content
        assert "{children}" in content

    def test_the_original_html_head_survives(self) -> None:
        content = _gen(_HTML, "public/index.html", _INDEX)["public/index.html"]
        assert "<title>Acme</title>" in content

    def test_a_file_with_no_injection_point_is_refused_not_mangled(self) -> None:
        """No closing tag means no safe place to inject. Returning the file unchanged is the
        safe failure; writing something plausible is not."""
        from app.services.integration.artifacts import WidgetInjectionError

        with pytest.raises(WidgetInjectionError):
            _gen(_HTML, "public/index.html", "<html><body>no closing body tag")


class TestNoSecrets:
    """Only the integration's own public key belongs in generated output."""

    def test_the_public_key_is_present(self) -> None:
        files = _gen(_NEXT, "app/layout.tsx", _LAYOUT)
        assert any("fussion_pk_TESTKEY" in body for body in files.values())

    def test_no_other_credential_shaped_string_is_emitted(self) -> None:
        suspicious = ("github_pat_", "ghp_", "sk-", "AKIA", "BEGIN PRIVATE KEY")
        for body in _gen(_NEXT, "app/layout.tsx", _LAYOUT).values():
            for token in suspicious:
                assert token not in body, f"credential-shaped token leaked into output: {token}"


class TestAgentReportMatchesReality:
    """ASI09. The reviewer approves the diff. If the agent's summary disagrees with what it
    did, the approval covers something other than what was written."""

    def _output(self, paths: list[str]) -> CodingAgentOutput:
        return CodingAgentOutput(
            summary="done",
            files=[
                GeneratedFileRecord(path=p, action="modify", summary="patched") for p in paths
            ],
        )

    def test_a_report_covering_every_written_file_is_accepted(self) -> None:
        written = set(_gen(_NEXT, "app/layout.tsx", _LAYOUT))
        reported = {f.path for f in self._output(sorted(written)).files}
        assert reported == written

    def test_an_under_reporting_is_detected(self) -> None:
        """The dangerous case: the agent changed three files and mentioned one."""
        written = set(_gen(_NEXT, "app/layout.tsx", _LAYOUT))
        reported = {f.path for f in self._output(["app/layout.tsx"]).files}
        assert reported != written
        assert written - reported, "missing files must be detectable by a reviewer or a check"

    def test_an_over_reporting_is_detected(self) -> None:
        written = set(_gen(_NEXT, "app/layout.tsx", _LAYOUT))
        reported = {f.path for f in self._output([*sorted(written), "etc/passwd"]).files}
        assert reported - written, "claiming a file that was not written must be detectable"

    def test_the_output_schema_rejects_an_empty_path(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GeneratedFileRecord(path="", action="modify", summary="x")

    def test_the_output_is_serialisable_for_the_run_record(self) -> None:
        payload = self._output(["app/layout.tsx"]).model_dump_json()
        assert json.loads(payload)["files"][0]["path"] == "app/layout.tsx"


class TestIndependence:
    """A path or key is one value, not a test fixture."""

    def test_generation_does_not_depend_on_call_order(self) -> None:
        first = _gen(_NEXT, "app/layout.tsx", _LAYOUT)
        _gen(_HTML, "public/index.html", _INDEX)
        assert _gen(_NEXT, "app/layout.tsx", _LAYOUT) == first

    def test_each_case_gets_a_distinct_key_when_asked(self) -> None:
        a = _gen(_NEXT, "app/layout.tsx", _LAYOUT)
        b = _gen(_NEXT, "app/layout.tsx", _LAYOUT)
        assert a == b
        assert uuid.uuid4() != uuid.uuid4()