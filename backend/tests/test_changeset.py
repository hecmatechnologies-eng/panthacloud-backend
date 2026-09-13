"""Step C · C12 — the recorded change set.

Computed once from the exact bytes the run wrote: created files diff against empty, modified files
against the content that was read.
"""

from app.services.integration.changeset import build_change_set


def test_create_and_modify_diff_against_the_right_side() -> None:
    generated = {
        "components/fussion/FussionAssistant.tsx": "export const A = 1;\n",
        "app/layout.tsx": "new\n",
    }
    original = {"app/layout.tsx": "old\n"}

    changes = build_change_set(
        generated, ["components/fussion/FussionAssistant.tsx"], original
    )
    by_path = {change["path"]: change for change in changes}

    created = by_path["components/fussion/FussionAssistant.tsx"]
    assert created["action"] == "create"
    assert "+export const A = 1;" in created["diff"]
    assert "-old" not in created["diff"]  # a created file has no "before" side

    modified = by_path["app/layout.tsx"]
    assert modified["action"] == "modify"
    assert "-old" in modified["diff"]  # the content that was read
    assert "+new" in modified["diff"]


def test_paths_are_sorted_for_a_deterministic_set() -> None:
    changes = build_change_set({"z.ts": "z\n", "a.ts": "a\n"}, ["z.ts", "a.ts"], {})
    assert [change["path"] for change in changes] == ["a.ts", "z.ts"]
