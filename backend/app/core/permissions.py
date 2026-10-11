import enum

from app.models.membership import RoleEnum


class Permission(str, enum.Enum):
    ORG_VIEW = "org:view"
    ORG_UPDATE = "org:update"
    ORG_DELETE = "org:delete"
    MEMBERS_VIEW = "members:view"
    MEMBERS_INVITE = "members:invite"
    MEMBERS_ROLE_CHANGE = "members:role_change"
    MEMBERS_REMOVE = "members:remove"
    PROJECT_CREATE = "project:create"
    PROJECT_VIEW = "project:view"
    PROJECT_MODIFY = "project:modify"
    PROJECT_DELETE = "project:delete"
    INTEGRATION_VIEW = "integration:view"
    INTEGRATION_CREATE = "integration:create"
    INTEGRATION_MODIFY = "integration:modify"
    INTEGRATION_UPDATE = "integration:update"
    INTEGRATION_EXECUTE = "integration:execute"
    INTEGRATION_DELETE = "integration:delete"
    REPOSITORY_VIEW = "repository:view"
    REPOSITORY_CREATE = "repository:create"
    REPOSITORY_MODIFY = "repository:modify"
    REPOSITORY_DELETE = "repository:delete"
    REPOSITORY_SNAPSHOT_VIEW = "repository:snapshot:view"
    REPOSITORY_SNAPSHOT_CREATE = "repository:snapshot:create"
    REPOSITORY_INSPECT = "repository:inspect"
    REPOSITORY_DISCOVERY_VIEW = "repository:discovery:view"
    REPOSITORY_DISCOVERY_CREATE = "repository:discovery:create"
    KNOWLEDGE_VIEW = "knowledge:view"
    KNOWLEDGE_CREATE = "knowledge:create"
    KNOWLEDGE_DELETE = "knowledge:delete"
    ASSISTANT_VIEW = "assistant:view"
    ASSISTANT_CREATE = "assistant:create"
    ASSISTANT_UPDATE = "assistant:update"
    ASSISTANT_DELETE = "assistant:delete"


ROLE_PERMISSIONS: dict[RoleEnum, set[Permission]] = {
    RoleEnum.OWNER: {
        Permission.ORG_VIEW,
        Permission.ORG_UPDATE,
        Permission.ORG_DELETE,
        Permission.MEMBERS_VIEW,
        Permission.MEMBERS_INVITE,
        Permission.MEMBERS_ROLE_CHANGE,
        Permission.MEMBERS_REMOVE,
        Permission.PROJECT_CREATE,
        Permission.PROJECT_VIEW,
        Permission.PROJECT_MODIFY,
        Permission.PROJECT_DELETE,
        Permission.INTEGRATION_VIEW,
        Permission.INTEGRATION_CREATE,
        Permission.INTEGRATION_MODIFY,
        Permission.INTEGRATION_UPDATE,
        Permission.INTEGRATION_EXECUTE,
        Permission.INTEGRATION_DELETE,
        Permission.REPOSITORY_VIEW,
        Permission.REPOSITORY_CREATE,
        Permission.REPOSITORY_MODIFY,
        Permission.REPOSITORY_DELETE,
        Permission.REPOSITORY_SNAPSHOT_VIEW,
        Permission.REPOSITORY_SNAPSHOT_CREATE,
        Permission.REPOSITORY_INSPECT,
        Permission.REPOSITORY_DISCOVERY_VIEW,
        Permission.REPOSITORY_DISCOVERY_CREATE,
        Permission.KNOWLEDGE_VIEW,
        Permission.KNOWLEDGE_CREATE,
        Permission.KNOWLEDGE_DELETE,
        Permission.ASSISTANT_VIEW,
        Permission.ASSISTANT_CREATE,
        Permission.ASSISTANT_UPDATE,
        Permission.ASSISTANT_DELETE,
    },
    RoleEnum.ADMIN: {
        Permission.ORG_VIEW,
        Permission.ORG_UPDATE,
        Permission.MEMBERS_VIEW,
        Permission.MEMBERS_INVITE,
        Permission.MEMBERS_REMOVE,
        Permission.PROJECT_CREATE,
        Permission.PROJECT_VIEW,
        Permission.PROJECT_MODIFY,
        Permission.PROJECT_DELETE,
        Permission.INTEGRATION_VIEW,
        Permission.INTEGRATION_CREATE,
        Permission.INTEGRATION_MODIFY,
        Permission.INTEGRATION_UPDATE,
        Permission.INTEGRATION_EXECUTE,
        Permission.INTEGRATION_DELETE,
        Permission.REPOSITORY_VIEW,
        Permission.REPOSITORY_CREATE,
        Permission.REPOSITORY_MODIFY,
        Permission.REPOSITORY_DELETE,
        Permission.REPOSITORY_SNAPSHOT_VIEW,
        Permission.REPOSITORY_SNAPSHOT_CREATE,
        Permission.REPOSITORY_INSPECT,
        Permission.REPOSITORY_DISCOVERY_VIEW,
        Permission.REPOSITORY_DISCOVERY_CREATE,
        Permission.KNOWLEDGE_VIEW,
        Permission.KNOWLEDGE_CREATE,
        Permission.KNOWLEDGE_DELETE,
        Permission.ASSISTANT_VIEW,
        Permission.ASSISTANT_CREATE,
        Permission.ASSISTANT_UPDATE,
        Permission.ASSISTANT_DELETE,
    },
    RoleEnum.MEMBER: {
        Permission.ORG_VIEW,
        Permission.MEMBERS_VIEW,
        Permission.PROJECT_VIEW,
        Permission.PROJECT_MODIFY,
        Permission.INTEGRATION_VIEW,
        Permission.INTEGRATION_CREATE,
        Permission.INTEGRATION_MODIFY,
        Permission.INTEGRATION_UPDATE,
        Permission.INTEGRATION_EXECUTE,
        Permission.REPOSITORY_VIEW,
        Permission.REPOSITORY_CREATE,
        Permission.REPOSITORY_MODIFY,
        Permission.REPOSITORY_SNAPSHOT_VIEW,
        Permission.REPOSITORY_SNAPSHOT_CREATE,
        Permission.REPOSITORY_INSPECT,
        Permission.REPOSITORY_DISCOVERY_VIEW,
        Permission.REPOSITORY_DISCOVERY_CREATE,
        # Knowledge and assistant configuration are OWNER/ADMIN only. A document goes straight
        # to READY and is then retrievable, and under semantic embeddings a poisoned one is
        # reachable by meaning rather than keyword — so a member who could upload could change
        # what the tenant's guests are told. A member keeps read access; mutating the corpus
        # the assistant answers from is an owner/admin decision.
        #
        # DELETE is removed alongside CREATE deliberately: a member who cannot add a document
        # but could remove one would have strictly more destructive reach than one who could do
        # both, which is not a coherent role.
        Permission.KNOWLEDGE_VIEW,
        Permission.ASSISTANT_VIEW,
    },
    RoleEnum.VIEWER: {
        Permission.ORG_VIEW,
        Permission.MEMBERS_VIEW,
        Permission.PROJECT_VIEW,
        Permission.INTEGRATION_VIEW,
        Permission.REPOSITORY_VIEW,
        Permission.REPOSITORY_SNAPSHOT_VIEW,
        Permission.REPOSITORY_DISCOVERY_VIEW,
        Permission.KNOWLEDGE_VIEW,
        Permission.ASSISTANT_VIEW,
    },
}



def has_permission(role: RoleEnum, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())
