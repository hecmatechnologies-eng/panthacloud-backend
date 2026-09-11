import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.contract import ApiContract, ContractStatus
from app.models.discovery import DiscoveryRun, DiscoveryStatus
from app.models.integration_adapter import (
    AdapterStatus,
    AdapterType,
    IntegrationAdapter,
)
from app.models.integration_plan import IntegrationPlan
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.services.repository.acquisition import acquisition_service

logger = logging.getLogger(__name__)


class SnapshotNotReadyError(Exception):
    """Raised when snapshot is not in READY status."""


class IntegrationPlanNotFoundError(Exception):
    """Raised when integration plan is not found."""


class IntegrationAdapterPlanningError(Exception):
    """Raised when adapter planning fails."""


# Deterministic mapping from service category / name to AdapterType and default operations
ADAPTER_TYPE_MAPPING: dict[str, AdapterType] = {
    "DATABASE": AdapterType.DATABASE,
    "CACHE": AdapterType.CACHE,
    "PAYMENT": AdapterType.PAYMENT,
    "PAYMENTS": AdapterType.PAYMENT,
    "STORAGE": AdapterType.STORAGE,
    "MESSAGE_BROKER": AdapterType.MESSAGE_BROKER,
    "AUTHENTICATION": AdapterType.AUTHENTICATION,
    "HTTP_API": AdapterType.HTTP_API,
    "EXTERNAL_API": AdapterType.HTTP_API,
    "VERSION_CONTROL": AdapterType.VERSION_CONTROL,
    "WEBHOOK": AdapterType.WEBHOOK,
}


class IntegrationAdapterPlanningService:
    async def generate_adapters(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        repository: Repository,
        snapshot: RepositorySnapshot,
        integration_plan_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[IntegrationAdapter]:
        """
        Deterministically transforms an IntegrationPlan and Discovery/Contract facts
        into structured, declarative IntegrationAdapter definitions.
        """
        if snapshot.status != SnapshotStatus.READY:
            raise SnapshotNotReadyError(
                f"Cannot generate integration adapters on snapshot with status '{snapshot.status}'. "
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

        # 2. Locate DiscoveryRun and ApiContract
        disc_stmt = (
            select(DiscoveryRun)
            .where(
                DiscoveryRun.snapshot_id == snapshot_id,
                DiscoveryRun.status == DiscoveryStatus.COMPLETED,
            )
            .order_by(DiscoveryRun.completed_at.desc())
        )
        disc_res = await db.execute(disc_stmt)
        discovery_run = disc_res.scalars().first()

        contract_stmt = (
            select(ApiContract)
            .options(selectinload(ApiContract.operations))
            .where(
                ApiContract.snapshot_id == snapshot_id,
                ApiContract.status == ContractStatus.COMPLETED,
            )
            .order_by(ApiContract.created_at.desc())
        )
        contract_res = await db.execute(contract_stmt)
        contract = contract_res.scalars().first()

        # Record audit event: planning started
        await acquisition_service.record_audit(
            db,
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            event_type="repository.integration_adapter.created",
            resource_id=snapshot_id,
            payload={
                "snapshot_id": str(snapshot_id),
                "integration_plan_id": str(plan_id),
            },
        )

        try:
            created_adapters: list[IntegrationAdapter] = []
            candidates = plan.candidates or []
            plan_credentials = plan.required_credentials or []

            # 3. Process candidate services
            for cand in candidates:
                cat = (cand.get("category") or cand.get("type") or "").upper()
                service_name = cand.get("service") or cand.get("name", "Unknown")
                adapter_type = ADAPTER_TYPE_MAPPING.get(cat, AdapterType.UNKNOWN)

                if adapter_type == AdapterType.UNKNOWN:
                    provider = None
                    adapter_status = AdapterStatus.REVIEW_REQUIRED
                    adapter_name = f"{service_name} Adapter"
                    description = f"Unclassified external dependency '{service_name}' requiring architectural review"
                else:
                    provider = service_name
                    adapter_name = f"{service_name} Adapter"
                    adapter_status = AdapterStatus.PLANNED
                    description = f"Declarative adapter for {service_name} integration"

                # Filter matching credentials (variable names ONLY, no secret values)
                matched_creds: list[dict[str, Any]] = []
                for cred in plan_credentials:
                    var_name = cred.get("key") or cred.get("name")
                    if not var_name:
                        continue
                    cred_cat = (cred.get("category") or cred.get("type") or "").upper()
                    cred_service = cred.get("service") or ""
                    if cred_cat == cat or cred_cat in service_name.upper() or cred_service.upper() == service_name.upper():
                        matched_creds.append({
                            "key": var_name,
                            "category": cred.get("category") or cred.get("type", cat),
                            "required": cred.get("required", True),
                            "sensitive": cred.get("sensitive", True),
                            "description": cred.get("description"),
                        })

                # Sort credentials deterministically by key
                matched_creds.sort(key=lambda c: c["key"])

                # Determine operations
                operations: list[dict[str, Any]] = []

                if adapter_type == AdapterType.PAYMENT:
                    # Look for payment endpoints in contract or static discovery
                    detected_ops = []
                    if contract and contract.operations:
                        for op in contract.operations:
                            if any(k in op.path.lower() for k in ["payment", "charge", "checkout", "billing", "stripe"]):
                                detected_ops.append({
                                    "name": op.operation_id or f"{op.method.lower()}_{op.path.strip('/').replace('/', '_')}",
                                    "operation_type": "PAYMENT",
                                    "method": op.method,
                                    "target": op.path,
                                    "description": op.summary or f"Payment endpoint {op.path}",
                                    "source": "DETECTED",
                                    "evidence": op.evidence or {},
                                    "requires_approval": True,
                                })
                    if detected_ops:
                        operations.extend(detected_ops)
                    else:
                        operations.append({
                            "name": "charge_customer",
                            "operation_type": "PAYMENT",
                            "method": "POST",
                            "target": f"{service_name.lower()}.charges.create",
                            "description": f"Process customer payment through {service_name}",
                            "source": "INFERRED",
                            "evidence": cand.get("evidence", {}),
                            "requires_approval": True,
                        })

                elif adapter_type == AdapterType.STORAGE:
                    detected_ops = []
                    if contract and contract.operations:
                        for op in contract.operations:
                            if any(k in op.path.lower() for k in ["file", "upload", "storage", "asset", "document"]):
                                detected_ops.append({
                                    "name": op.operation_id or f"{op.method.lower()}_{op.path.strip('/').replace('/', '_')}",
                                    "operation_type": "STORAGE",
                                    "method": op.method,
                                    "target": op.path,
                                    "description": op.summary or f"Storage endpoint {op.path}",
                                    "source": "DETECTED",
                                    "evidence": op.evidence or {},
                                    "requires_approval": op.method in ["POST", "PUT", "DELETE"],
                                })
                    if detected_ops:
                        operations.extend(detected_ops)
                    else:
                        operations.extend([
                            {
                                "name": "upload_object",
                                "operation_type": "STORAGE",
                                "method": "PUT",
                                "target": "storage.objects.upload",
                                "description": f"Upload binary object to {service_name}",
                                "source": "INFERRED",
                                "evidence": cand.get("evidence", {}),
                                "requires_approval": True,
                            },
                            {
                                "name": "get_object",
                                "operation_type": "STORAGE",
                                "method": "GET",
                                "target": "storage.objects.get",
                                "description": f"Retrieve binary object from {service_name}",
                                "source": "INFERRED",
                                "evidence": cand.get("evidence", {}),
                                "requires_approval": False,
                            },
                        ])

                elif adapter_type == AdapterType.DATABASE:
                    operations.extend([
                        {
                            "name": "execute_query",
                            "operation_type": "QUERY",
                            "method": None,
                            "target": f"{service_name.lower()}.query",
                            "description": f"Execute read query against {service_name}",
                            "source": "INFERRED",
                            "evidence": cand.get("evidence", {}),
                            "requires_approval": False,
                        },
                        {
                            "name": "execute_mutation",
                            "operation_type": "WRITE",
                            "method": None,
                            "target": f"{service_name.lower()}.mutation",
                            "description": f"Execute state-altering mutation against {service_name}",
                            "source": "INFERRED",
                            "evidence": cand.get("evidence", {}),
                            "requires_approval": True,
                        },
                    ])

                elif adapter_type == AdapterType.CACHE:
                    operations.extend([
                        {
                            "name": "cache_get",
                            "operation_type": "QUERY",
                            "method": None,
                            "target": f"{service_name.lower()}.get",
                            "description": f"Fetch cached value from {service_name}",
                            "source": "INFERRED",
                            "evidence": cand.get("evidence", {}),
                            "requires_approval": False,
                        },
                        {
                            "name": "cache_set",
                            "operation_type": "WRITE",
                            "method": None,
                            "target": f"{service_name.lower()}.set",
                            "description": f"Set key in {service_name}",
                            "source": "INFERRED",
                            "evidence": cand.get("evidence", {}),
                            "requires_approval": False,
                        },
                    ])

                elif adapter_type == AdapterType.MESSAGE_BROKER:
                    operations.extend([
                        {
                            "name": "publish_message",
                            "operation_type": "SEND",
                            "method": None,
                            "target": f"{service_name.lower()}.publish",
                            "description": f"Publish event message to {service_name}",
                            "source": "INFERRED",
                            "evidence": cand.get("evidence", {}),
                            "requires_approval": False,
                        },
                        {
                            "name": "consume_task",
                            "operation_type": "RECEIVE",
                            "method": None,
                            "target": f"{service_name.lower()}.consume",
                            "description": f"Consume task event from {service_name}",
                            "source": "INFERRED",
                            "evidence": cand.get("evidence", {}),
                            "requires_approval": False,
                        },
                    ])

                elif adapter_type == AdapterType.AUTHENTICATION:
                    operations.append({
                        "name": "verify_token",
                        "operation_type": "AUTHENTICATE",
                        "method": None,
                        "target": f"{service_name.lower()}.verify_token",
                        "description": f"Validate user token via {service_name}",
                        "source": "INFERRED",
                        "evidence": cand.get("evidence", {}),
                        "requires_approval": False,
                    })

                else:
                    operations.append({
                        "name": "inspect_unknown",
                        "operation_type": "QUERY",
                        "method": None,
                        "target": "unknown.inspect",
                        "description": "Manual verification required for unclassified integration",
                        "source": "UNKNOWN",
                        "evidence": cand.get("evidence", {}),
                        "requires_approval": True,
                    })

                # Sort operations deterministically
                operations.sort(key=lambda o: (o["name"], o.get("target") or ""))

                prerequisites = [
                    "Validate environment configuration variable names",
                    f"Ensure {service_name} credentials exist in secure vault boundary",
                    "Phase 08 boundary: Zero external execution permitted in Control Plane",
                ]

                constraints = [
                    "Declarative planning model only — no external socket or HTTP connection allowed",
                    "Sensitive credential values are strictly concealed and never stored",
                ]

                adapter = IntegrationAdapter(
                    integration_plan_id=plan.id,
                    snapshot_id=snapshot.id,
                    name=adapter_name,
                    adapter_type=adapter_type,
                    provider=provider,
                    status=adapter_status,
                    description=description,
                    configuration={"provider": provider, "category": cat},
                    required_credentials=matched_creds,
                    operations=operations,
                    prerequisites=prerequisites,
                    constraints=constraints,
                    evidence={"candidate": cand},
                    metadata_={
                        "operations_count": len(operations),
                        "credentials_count": len(matched_creds),
                    },
                )
                created_adapters.append(adapter)

            # 4. Webhook Detection
            # Look in Contract operations or Discovery static routes
            webhook_routes: list[dict[str, Any]] = []
            if contract and contract.operations:
                for op in contract.operations:
                    p = op.path.lower()
                    if "/webhook" in p or "/callback" in p:
                        webhook_routes.append({
                            "path": op.path,
                            "method": op.method,
                            "evidence": op.evidence or {},
                        })
            if discovery_run and discovery_run.metadata_:
                routes = discovery_run.metadata_.get("routes", [])
                for r in routes:
                    p = r.get("path", "").lower()
                    if ("/webhook" in p or "/callback" in p) and not any(
                        wr["path"] == r.get("path") and wr["method"] == r.get("method")
                        for wr in webhook_routes
                    ):
                        webhook_routes.append({
                                "path": r.get("path"),
                                "method": r.get("method"),
                                "evidence": r.get("evidence", {}),
                            })

            for wr in webhook_routes:
                p_lower = wr["path"].lower()
                if "stripe" in p_lower:
                    provider = "Stripe"
                    name = "Stripe Webhook Adapter"
                elif "github" in p_lower:
                    provider = "GitHub"
                    name = "GitHub Webhook Adapter"
                else:
                    provider = "Generic Webhook"
                    name = f"Webhook Adapter ({wr['path']})"

                wh_ops = [{
                    "name": f"receive_{provider.lower().replace(' ', '_')}_webhook",
                    "operation_type": "RECEIVE",
                    "method": wr["method"],
                    "target": wr["path"],
                    "description": f"Receive and verify inbound webhook events from {provider}",
                    "source": "DETECTED",
                    "evidence": wr.get("evidence", {}),
                    "requires_approval": True,
                }]

                wh_creds = [{
                    "key": f"{provider.upper().replace(' ', '_')}_WEBHOOK_SECRET",
                    "category": "WEBHOOK",
                    "required": True,
                    "sensitive": True,
                    "description": f"Signing secret used to verify incoming {provider} webhooks",
                }]

                webhook_adapter = IntegrationAdapter(
                    integration_plan_id=plan.id,
                    snapshot_id=snapshot.id,
                    name=name,
                    adapter_type=AdapterType.WEBHOOK,
                    provider=provider,
                    status=AdapterStatus.PLANNED,
                    description=f"Declarative inbound webhook verification adapter for {wr['path']}",
                    configuration={"path": wr["path"], "method": wr["method"]},
                    required_credentials=wh_creds,
                    operations=wh_ops,
                    prerequisites=[
                        "Configure inbound webhook endpoint route",
                        "Provision webhook secret in secure credential store",
                    ],
                    constraints=[
                        "No external webhook triggering or receiving in Phase 08",
                    ],
                    evidence={"route": wr},
                    metadata_={"route": wr["path"], "method": wr["method"]},
                )
                created_adapters.append(webhook_adapter)

            # 5. Check for unknown integrations from discovery dependencies not covered by candidates
            if discovery_run and discovery_run.metadata_:
                deps = discovery_run.metadata_.get("dependencies", [])
                for dep in deps:
                    d_name = dep.get("name", "")
                    if (
                        "custom" in d_name.lower() or "proprietary" in d_name.lower()
                    ) and not any(a.name == f"{d_name} Adapter" for a in created_adapters):
                        unknown_adapter = IntegrationAdapter(
                            integration_plan_id=plan.id,
                            snapshot_id=snapshot.id,
                            name=f"{d_name} Adapter",
                            adapter_type=AdapterType.UNKNOWN,
                            provider=None,
                            status=AdapterStatus.REVIEW_REQUIRED,
                            description=f"Unclassified dependency '{d_name}' requiring human review",
                            configuration={"dependency": d_name},
                            required_credentials=[],
                            operations=[{
                                "name": "inspect_unclassified_dependency",
                                "operation_type": "QUERY",
                                "method": None,
                                "target": f"{d_name}.inspect",
                                "description": f"Analyze contract requirements for {d_name}",
                                "source": "UNKNOWN",
                                "evidence": dep.get("evidence", {}),
                                "requires_approval": True,
                            }],
                            prerequisites=["Conduct human architectural review to determine adapter specification"],
                            constraints=["Do not execute or import unclassified dependencies"],
                            evidence={"dependency": dep},
                            metadata_={"dependency": d_name},
                        )
                        created_adapters.append(unknown_adapter)

            # 6. Sort adapters deterministically
            created_adapters.sort(key=lambda a: (a.adapter_type.value, a.name))

            # 7. Persist to database (idempotent replacement for this integration_plan_id)
            del_stmt = select(IntegrationAdapter).where(
                IntegrationAdapter.integration_plan_id == plan.id
            )
            del_res = await db.execute(del_stmt)
            existing_adapters = del_res.scalars().all()
            for ea in existing_adapters:
                await db.delete(ea)

            for ad in created_adapters:
                db.add(ad)

            await db.commit()
            for ad in created_adapters:
                await db.refresh(ad)

            # Record audit event: completed
            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.integration_adapter.completed",
                resource_id=snapshot_id,
                payload={
                    "snapshot_id": str(snapshot_id),
                    "integration_plan_id": str(plan_id),
                    "adapters_count": len(created_adapters),
                },
            )

            return created_adapters

        except Exception as e:
            await db.rollback()
            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.integration_adapter.failed",
                resource_id=snapshot_id,
                payload={
                    "snapshot_id": str(snapshot_id),
                    "integration_plan_id": str(plan_id) if 'plan_id' in locals() and plan_id else None,
                    "error": str(e),
                },
            )
            raise IntegrationAdapterPlanningError(str(e)) from e


integration_adapter_service = IntegrationAdapterPlanningService()
