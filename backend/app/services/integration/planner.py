from typing import Any

from app.models.website_integration import WebsiteFramework
from app.schemas.website_integration import IntegrationPlanPayload


class IntegrationPlanner:
    """
    Produces deterministic, human-readable integration plans before any repository modifications occur.
    """

    @staticmethod
    def generate_plan(
        framework: WebsiteFramework,
        widget_target_path: str,
        assistant_data: dict[str, Any] | None = None,
        has_knowledge_base: bool = False,
    ) -> IntegrationPlanPayload:
        files_to_create: list[str] = []
        files_to_modify: list[str] = []
        files_to_delete: list[str] = []
        warnings: list[str] = []

        target_path = widget_target_path.strip() or (
            "app/layout.tsx" if framework == WebsiteFramework.REACT_NEXTJS else "index.html"
        )

        if framework == WebsiteFramework.REACT_NEXTJS:
            files_to_create = [
                "components/fussion/FussionAssistant.tsx",
                "lib/fussion-assistant.ts",
            ]
            files_to_modify = [target_path]
        elif framework == WebsiteFramework.GENERIC_HTML:
            files_to_create = [
                "fussion-assistant.js",
            ]
            files_to_modify = [target_path]

        # Invariant checks & warnings
        if assistant_data:
            if not assistant_data.get("is_enabled", True):
                warnings.append("Assistant is currently disabled. The widget will remain inactive on the storefront.")
        else:
            warnings.append("No active assistant configured. Default fallback configuration will be used.")

        if not has_knowledge_base:
            warnings.append("Knowledge Base contains no indexed documents. Assistant will operate without document grounding.")

        summary = (
            f"Deterministic plan for {framework.value}: create {len(files_to_create)} file(s), "
            f"modify {len(files_to_modify)} file(s) ({', '.join(files_to_modify)})."
        )

        return IntegrationPlanPayload(
            framework=framework,
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
            files_to_delete=files_to_delete,
            warnings=warnings,
            summary=summary,
        )
