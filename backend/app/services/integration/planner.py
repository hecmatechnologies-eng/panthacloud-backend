from typing import Any

from app.models.website_integration import WebsiteFramework
from app.schemas.website_integration import IntegrationPlanPayload, TargetStatus


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
        *,
        target_status: TargetStatus,
    ) -> IntegrationPlanPayload:
        files_to_create: list[str] = []
        files_to_modify: list[str] = []
        files_to_delete: list[str] = []
        warnings: list[str] = []

        # Exactly the path that was read: a defaulted path here would plan a file nobody read.
        target_path = widget_target_path

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
        # The widget target is always a modification: Fussion never creates an application shell.
        if target_status == "missing":
            warnings.append(
                f"Target file '{target_path}' was not found in the repository. Fussion only modifies "
                "an existing application shell and will not create one; correct the widget target "
                "path before starting a run."
            )
        elif target_status == "unknown":
            warnings.append(
                f"Could not confirm that '{target_path}' exists because the repository was "
                "unreachable. The run checks again before modifying anything."
            )

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
            target_status=target_status,
        )
