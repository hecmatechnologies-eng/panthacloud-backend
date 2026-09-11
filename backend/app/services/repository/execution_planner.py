import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_plan import ExecutionPlan, ExecutionPlanStatus
from app.models.integration_adapter import (
    IntegrationAdapter,
)
from app.models.integration_plan import IntegrationPlan
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.schemas.execution_plan import SafetyClassification
from app.services.repository.acquisition import acquisition_service
from app.services.repository.integration_adapter import (
    IntegrationPlanNotFoundError,
    SnapshotNotReadyError,
    integration_adapter_service,
)

logger = logging.getLogger(__name__)


class ExecutionPlanningError(Exception):
    """Raised when execution planning fails."""


class ExecutionPlanningService:
    async def generate_execution_plan(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        repository: Repository,
        snapshot: RepositorySnapshot,
        integration_plan_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> ExecutionPlan:
        """
        Deterministically produces an ordered, safe, declarative ExecutionPlan
        based on available IntegrationAdapters and IntegrationPlan facts.
        """
        if snapshot.status != SnapshotStatus.READY:
            raise SnapshotNotReadyError(
                f"Cannot generate execution plan on snapshot with status '{snapshot.status}'. "
                "Snapshot must be in 'READY' status."
            )

        snapshot_id = snapshot.id

        # 1. Locate IntegrationPlan
        if integration_plan_id:
            stmt = select(IntegrationPlan).where(
                IntegrationPlan.id == integration_plan_id,
                IntegrationPlan.snapshot_id == snapshot_id,
            )
            res = await db.execute(stmt)
            plan = res.scalar_one_or_none()
            if not plan:
                raise IntegrationPlanNotFoundError(
                    f"Integration plan '{integration_plan_id}' not found for snapshot."
                )
        else:
            stmt = (
                select(IntegrationPlan)
                .where(IntegrationPlan.snapshot_id == snapshot_id)
                .order_by(IntegrationPlan.created_at.desc())
            )
            res = await db.execute(stmt)
            plan = res.scalars().first()
            if not plan:
                raise IntegrationPlanNotFoundError(
                    "No integration plan found for snapshot. Run integration planning first."
                )

        plan_id = plan.id

        # 2. Locate or generate IntegrationAdapters
        adapter_stmt = (
            select(IntegrationAdapter)
            .where(IntegrationAdapter.integration_plan_id == plan_id)
        )
        adapter_res = await db.execute(adapter_stmt)
        adapters = list(adapter_res.scalars().all())

        if not adapters:
            adapters = await integration_adapter_service.generate_adapters(
                db,
                organization_id=organization_id,
                project_id=project_id,
                repository=repository,
                snapshot=snapshot,
                integration_plan_id=plan_id,
                user_id=user_id,
            )

        # Sort adapters deterministically
        adapters.sort(key=lambda a: (a.adapter_type.value, a.name))

        # Record audit event: planning started
        await acquisition_service.record_audit(
            db,
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            event_type="repository.execution_plan.created",
            resource_id=snapshot_id,
            payload={
                "snapshot_id": str(snapshot_id),
                "integration_plan_id": str(plan_id),
            },
        )

        try:
            steps: list[dict[str, Any]] = []
            all_credentials: list[dict[str, Any]] = []
            cred_keys_seen: set[str] = set()

            for ad in adapters:
                for rc in (ad.required_credentials or []):
                    k = rc.get("key") or rc.get("name")
                    if k and k not in cred_keys_seen:
                        cred_keys_seen.add(k)
                        all_credentials.append({
                            "key": k,
                            "category": rc.get("category", "GENERAL"),
                            "required": rc.get("required", True),
                            "sensitive": rc.get("sensitive", True),
                            "description": rc.get("description"),
                        })

            all_credentials.sort(key=lambda c: c["key"])
            config_input_names = [c["key"] for c in all_credentials]

            # Step 1: Configuration Validation
            steps.append({
                "id": "step-1",
                "order": 1,
                "adapter_id": None,
                "action": "validate_configuration_keys",
                "description": "Verify all required configuration and credential variable names are defined in environment",
                "safety_classifications": [
                    SafetyClassification.CONFIGURATION.value,
                    SafetyClassification.READ_ONLY.value,
                ],
                "inputs": config_input_names,
                "outputs": ["configuration_keys_verified"],
                "depends_on": [],
                "requires_approval": False,
                "status": "READY",
                "blocked_reason": None,
                "evidence": {"plan_id": str(plan_id)},
            })

            # Step 2: Adapter Prerequisites Validation
            steps.append({
                "id": "step-2",
                "order": 2,
                "adapter_id": None,
                "action": "validate_adapter_prerequisites",
                "description": "Check prerequisite service reachability and schema contracts",
                "safety_classifications": [
                    SafetyClassification.READ_ONLY.value,
                    SafetyClassification.EXTERNAL_NETWORK.value,
                ],
                "inputs": ["configuration_keys_verified"],
                "outputs": ["adapter_prerequisites_verified"],
                "depends_on": ["step-1"],
                "requires_approval": False,
                "status": "BLOCKED",
                "blocked_reason": "External execution runtime not yet implemented in Phase 08",
                "evidence": {"adapters_count": len(adapters)},
            })

            approval_requirements: list[str] = []
            order_index = 3

            # Step 3+: Adapter Operations
            for ad in adapters:
                ad_creds = [c.get("key") or c.get("name") for c in (ad.required_credentials or []) if c.get("key") or c.get("name")]
                ad_creds.sort()

                ops = list(ad.operations or [])
                ops.sort(key=lambda o: (o["name"], o.get("target") or ""))

                for op in ops:
                    op_type = op.get("operation_type", "").upper()
                    safety: list[str] = []
                    requires_approval = bool(op.get("requires_approval", False))

                    if op_type == "PAYMENT":
                        safety = [
                            SafetyClassification.WRITE.value,
                            SafetyClassification.EXTERNAL_NETWORK.value,
                            SafetyClassification.CREDENTIAL_REQUIRED.value,
                        ]
                        requires_approval = True
                    elif op_type == "STORAGE":
                        if op.get("method") == "GET":
                            safety = [
                                SafetyClassification.READ_ONLY.value,
                                SafetyClassification.EXTERNAL_NETWORK.value,
                            ]
                        else:
                            safety = [
                                SafetyClassification.WRITE.value,
                                SafetyClassification.EXTERNAL_NETWORK.value,
                                SafetyClassification.CREDENTIAL_REQUIRED.value,
                            ]
                            requires_approval = True
                    elif op_type == "WRITE":
                        safety = [
                            SafetyClassification.WRITE.value,
                            SafetyClassification.CREDENTIAL_REQUIRED.value,
                        ]
                        requires_approval = True
                    elif op_type == "QUERY":
                        safety = [SafetyClassification.READ_ONLY.value]
                    elif op_type in ["RECEIVE", "SEND"]:
                        safety = [
                            SafetyClassification.WRITE.value,
                            SafetyClassification.EXTERNAL_NETWORK.value,
                        ]
                        requires_approval = True
                    elif op_type == "AUTHENTICATE":
                        safety = [SafetyClassification.READ_ONLY.value]
                    else:
                        safety = [
                            SafetyClassification.READ_ONLY.value,
                            SafetyClassification.EXTERNAL_NETWORK.value,
                        ]

                    step_id = f"step-{order_index}"
                    safe_action = f"{ad.name.lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')}_{op['name']}"

                    if requires_approval:
                        approval_requirements.append(
                            f"{safe_action}: Requires human authorization before external execution"
                        )
                        blocked_reason = "External execution runtime not yet implemented in Phase 08; requires human approval before future execution"
                    else:
                        blocked_reason = "External execution runtime not yet implemented in Phase 08"

                    steps.append({
                        "id": step_id,
                        "order": order_index,
                        "adapter_id": str(ad.id),
                        "action": safe_action,
                        "description": f"Execute {op['name']} against {ad.name} ({op.get('target', '')})",
                        "safety_classifications": safety,
                        "inputs": ad_creds,
                        "outputs": [f"{op['name']}_result"],
                        "depends_on": ["step-2"],
                        "requires_approval": requires_approval,
                        "status": "BLOCKED",
                        "blocked_reason": blocked_reason,
                        "evidence": op.get("evidence", {}),
                    })
                    order_index += 1

            # Compile overall execution plan
            prerequisites = [
                "All required environment configuration keys must be present",
                "Service endpoints must match discovered architectural contracts",
                "Zero external execution permitted in Phase 08 Control Plane boundary",
            ]

            blocked_reasons = [
                "Phase 08 Control Plane boundary: External network execution and code invocation are strictly disabled",
                "All external adapter operations are blocked pending future execution runtime",
            ]

            plan_status = ExecutionPlanStatus.PLANNED
            if any(s.get("requires_approval") for s in steps):
                plan_status = ExecutionPlanStatus.REVIEW_REQUIRED

            execution_plan = ExecutionPlan(
                project_id=project_id,
                snapshot_id=snapshot_id,
                integration_plan_id=plan_id,
                status=plan_status,
                steps=steps,
                required_credentials=all_credentials,
                prerequisites=prerequisites,
                approval_requirements=approval_requirements,
                blocked_reasons=blocked_reasons,
                evidence={
                    "adapters_count": len(adapters),
                    "steps_count": len(steps),
                    "blocked_steps_count": sum(1 for s in steps if s.get("status") == "BLOCKED"),
                },
                metadata_={
                    "total_steps": len(steps),
                    "requires_approval_count": len(approval_requirements),
                    "credentials_count": len(all_credentials),
                },
            )

            # Idempotent replacement for this integration_plan_id
            del_stmt = select(ExecutionPlan).where(
                ExecutionPlan.integration_plan_id == plan_id
            )
            del_res = await db.execute(del_stmt)
            existing_plans = del_res.scalars().all()
            for ep in existing_plans:
                await db.delete(ep)

            db.add(execution_plan)
            await db.commit()
            await db.refresh(execution_plan)

            # Record audit event: completed
            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.execution_plan.completed",
                resource_id=snapshot_id,
                payload={
                    "snapshot_id": str(snapshot_id),
                    "integration_plan_id": str(plan_id),
                    "execution_plan_id": str(execution_plan.id),
                    "total_steps": len(steps),
                },
            )

            return execution_plan

        except Exception as e:
            await db.rollback()
            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.execution_plan.failed",
                resource_id=snapshot_id,
                payload={
                    "snapshot_id": str(snapshot_id),
                    "integration_plan_id": str(plan_id) if 'plan_id' in locals() and plan_id else None,
                    "error": str(e),
                },
            )
            raise ExecutionPlanningError(str(e)) from e


execution_planning_service = ExecutionPlanningService()
