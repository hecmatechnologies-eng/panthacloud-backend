"""Who may change the corpus and the assistant (standards-alignment.md G3 remediation).

A knowledge document goes straight to READY and is then retrievable, and under semantic
embeddings a poisoned one is reachable by *meaning* rather than keyword. Assistant configuration
carries the tenant's grounding contract. Both are therefore owner/admin decisions; a member gets
read-only views.

This tests the permission matrix directly rather than through the endpoints, so the policy is
pinned even if no endpoint exercises a given cell yet.
"""

from app.core.permissions import ROLE_PERMISSIONS, Permission
from app.models.membership import RoleEnum

CORPUS_MUTATIONS = (
    Permission.KNOWLEDGE_CREATE,
    Permission.KNOWLEDGE_DELETE,
    Permission.ASSISTANT_CREATE,
    Permission.ASSISTANT_UPDATE,
    Permission.ASSISTANT_DELETE,
)


def _has(role: RoleEnum, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


class TestOwnerAndAdmin:
    def test_can_upload_to_the_corpus(self) -> None:
        assert _has(RoleEnum.OWNER, Permission.KNOWLEDGE_CREATE)
        assert _has(RoleEnum.ADMIN, Permission.KNOWLEDGE_CREATE)

    def test_can_configure_the_assistant(self) -> None:
        for role in (RoleEnum.OWNER, RoleEnum.ADMIN):
            assert _has(role, Permission.ASSISTANT_UPDATE)

    def test_can_remove_a_document(self) -> None:
        for role in (RoleEnum.OWNER, RoleEnum.ADMIN):
            assert _has(role, Permission.KNOWLEDGE_DELETE)

    def test_can_invite_members(self) -> None:
        """The account creator administers the org, which is how members get their views."""
        for role in (RoleEnum.OWNER, RoleEnum.ADMIN):
            assert _has(role, Permission.MEMBERS_INVITE)


class TestMember:
    def test_cannot_extend_the_corpus(self) -> None:
        assert not _has(RoleEnum.MEMBER, Permission.KNOWLEDGE_CREATE)

    def test_cannot_remove_from_the_corpus(self) -> None:
        """If a member could delete but not upload, they would have strictly more destructive
        reach than one who could do both. Not a coherent role."""
        assert not _has(RoleEnum.MEMBER, Permission.KNOWLEDGE_DELETE)

    def test_cannot_configure_the_assistant(self) -> None:
        """Assistant instructions carry the grounding contract; changing them changes what
        every guest is told."""
        for permission in (
            Permission.ASSISTANT_CREATE,
            Permission.ASSISTANT_UPDATE,
            Permission.ASSISTANT_DELETE,
        ):
            assert not _has(RoleEnum.MEMBER, permission)

    def test_still_sees_the_corpus_and_the_assistant(self) -> None:
        """Restricting mutation must not quietly demote a member to viewer."""
        assert _has(RoleEnum.MEMBER, Permission.KNOWLEDGE_VIEW)
        assert _has(RoleEnum.MEMBER, Permission.ASSISTANT_VIEW)

    def test_keeps_the_developing_permissions_they_had(self) -> None:
        """Only the corpus and assistant changed. Integration and repository work is what a
        member is for."""
        for permission in (
            Permission.PROJECT_MODIFY,
            Permission.INTEGRATION_CREATE,
            Permission.REPOSITORY_CREATE,
        ):
            assert _has(RoleEnum.MEMBER, permission)


class TestViewer:
    def test_can_read_the_corpus(self) -> None:
        assert _has(RoleEnum.VIEWER, Permission.KNOWLEDGE_VIEW)

    def test_cannot_mutate_anything_in_the_corpus_or_assistant(self) -> None:
        for permission in CORPUS_MUTATIONS:
            assert not _has(RoleEnum.VIEWER, permission)

    def test_cannot_run_an_integration(self) -> None:
        assert not _has(RoleEnum.VIEWER, Permission.INTEGRATION_EXECUTE)


class TestTheMatrixIsTotal:
    def test_every_role_has_an_entry(self) -> None:
        """A role added to RoleEnum without a permission set would silently authenticate as
        nothing at all, or as everything."""
        for role in RoleEnum:
            assert role in ROLE_PERMISSIONS, f"{role.name} has no permission set"

    def test_no_role_holds_view_without_create(self) -> None:
        """A view without create is the normal shape (viewer, member). The reverse is not."""
        for role in RoleEnum:
            perms = ROLE_PERMISSIONS[role]
            if Permission.KNOWLEDGE_CREATE in perms:
                assert Permission.KNOWLEDGE_VIEW in perms, f"{role.name} can upload but not read"

    def test_viewer_is_a_strict_subset_of_member(self) -> None:
        """If viewer gains a permission, member must have it too."""
        assert ROLE_PERMISSIONS[RoleEnum.VIEWER] <= ROLE_PERMISSIONS[RoleEnum.MEMBER]