import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.contract import ApiContract, ContractStatus
from app.models.discovery import DiscoveryRun, DiscoveryStatus
from app.models.integration_plan import IntegrationPlan, IntegrationPlanStatus
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.services.repository.acquisition import acquisition_service
from app.services.repository.workspace import workspace_manager

logger = logging.getLogger(__name__)


class SnapshotNotReadyError(Exception):
    """Raised when attempting integration planning on a snapshot not in READY status."""


class DiscoveryRunNotFoundError(Exception):
    """Raised when no completed discovery run exists for the snapshot."""


class IntegrationPlanningError(Exception):
    """Raised when integration planning fails."""


# Dependency knowledge mapping: dependency substring/name -> (Service Name, Category, Credential Keys)
DEPENDENCY_CATALOG = [
    {
        "keys": ["psycopg", "asyncpg", "pg"],
        "name": "PostgreSQL",
        "type": "DATABASE",
        "env_vars": ["DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST"],
        "description": "PostgreSQL relational database service",
    },
    {
        "keys": ["mysql", "pymysql", "aiomysql", "mysqlclient"],
        "name": "MySQL",
        "type": "DATABASE",
        "env_vars": ["DATABASE_URL", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"],
        "description": "MySQL relational database service",
    },
    {
        "keys": ["pymongo", "motor", "mongodb", "mongoose"],
        "name": "MongoDB",
        "type": "DATABASE",
        "env_vars": ["MONGODB_URI", "MONGO_URL"],
        "description": "MongoDB document store",
    },
    {
        "keys": ["sqlite3", "aiosqlite"],
        "name": "SQLite",
        "type": "DATABASE",
        "env_vars": ["SQLITE_PATH", "DATABASE_URL"],
        "description": "SQLite embedded database",
    },
    {
        "keys": ["redis", "aioredis", "ioredis"],
        "name": "Redis",
        "type": "CACHE",
        "env_vars": ["REDIS_URL", "REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD"],
        "description": "Redis in-memory caching and messaging store",
    },
    {
        "keys": ["celery", "pika", "kombu", "amqplib", "amqp"],
        "name": "RabbitMQ / AMQP",
        "type": "MESSAGE_BROKER",
        "env_vars": ["CELERY_BROKER_URL", "RABBITMQ_URL", "AMQP_URI"],
        "description": "Message broker and distributed task queue",
    },
    {
        "keys": ["kafka", "kafkajs", "confluent-kafka"],
        "name": "Apache Kafka",
        "type": "MESSAGE_BROKER",
        "env_vars": ["KAFKA_BROKERS", "KAFKA_BOOTSTRAP_SERVERS"],
        "description": "Distributed event streaming platform",
    },
    {
        "keys": ["stripe", "@stripe/stripe-js"],
        "name": "Stripe",
        "type": "PAYMENTS",
        "env_vars": ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET"],
        "description": "Payment processing and billing integration",
    },
    {
        "keys": ["boto3", "botocore", "@aws-sdk/client-s3"],
        "name": "Amazon S3",
        "type": "STORAGE",
        "env_vars": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "AWS_S3_BUCKET"],
        "description": "Amazon Web Services object storage",
    },
    {
        "keys": ["@google-cloud/storage", "google-cloud-storage"],
        "name": "Google Cloud Storage",
        "type": "STORAGE",
        "env_vars": ["GCS_BUCKET", "GOOGLE_APPLICATION_CREDENTIALS"],
        "description": "Google Cloud object storage",
    },
    {
        "keys": ["sendgrid", "@sendgrid/mail", "resend", "postmark"],
        "name": "Email Service",
        "type": "EXTERNAL_API",
        "env_vars": ["SENDGRID_API_KEY", "RESEND_API_KEY", "MAIL_HOST", "MAIL_PASSWORD"],
        "description": "Transactional email service",
    },
    {
        "keys": ["openai", "@openai/api", "anthropic", "@anthropic-ai/sdk"],
        "name": "AI / LLM Provider",
        "type": "EXTERNAL_API",
        "env_vars": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
        "description": "External AI / Large Language Model service",
    },
    {
        "keys": ["pyjwt", "python-jose", "jsonwebtoken", "jose", "passport", "auth0"],
        "name": "Authentication & JWT",
        "type": "AUTHENTICATION",
        "env_vars": ["JWT_SECRET", "SECRET_KEY", "AUTH_SECRET", "NEXTAUTH_SECRET"],
        "description": "Identity and token authentication service",
    },
]

SENSITIVE_PATTERNS = [
    r"_KEY$",
    r"_SECRET$",
    r"_TOKEN$",
    r"_PASSWORD$",
    r"_CREDENTIALS?$",
    r"_AUTH$",
    r"^DATABASE_URL$",
    r"^REDIS_URL$",
    r"^RABBITMQ_URL$",
    r"^MONGODB_URI$",
]


class IntegrationPlanningService:
    async def generate_plan(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        repository: Repository,
        snapshot: RepositorySnapshot,
        contract_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> IntegrationPlan:
        """
        Deterministically transforms discovery facts and contract findings into an integration plan.
        """
        if snapshot.status != SnapshotStatus.READY:
            raise SnapshotNotReadyError(
                f"Cannot generate integration plan on snapshot with status '{snapshot.status}'. "
                "Snapshot must be in 'READY' status."
            )

        # 1. Locate DiscoveryRun
        stmt = (
            select(DiscoveryRun)
            .where(
                DiscoveryRun.snapshot_id == snapshot.id,
                DiscoveryRun.status == DiscoveryStatus.COMPLETED,
            )
            .order_by(DiscoveryRun.completed_at.desc())
        )
        result = await db.execute(stmt)
        discovery_run = result.scalars().first()
        if not discovery_run:
            raise DiscoveryRunNotFoundError(
                "No completed discovery run found for snapshot. Run discovery first."
            )

        # 2. Locate ApiContract if available
        contract: ApiContract | None = None
        if contract_id:
            c_stmt = (
                select(ApiContract)
                .options(selectinload(ApiContract.operations))
                .where(
                    ApiContract.id == contract_id,
                    ApiContract.snapshot_id == snapshot.id,
                )
            )
            c_res = await db.execute(c_stmt)
            contract = c_res.scalar_one_or_none()
        else:
            c_stmt = (
                select(ApiContract)
                .options(selectinload(ApiContract.operations))
                .where(
                    ApiContract.snapshot_id == snapshot.id,
                    ApiContract.status == ContractStatus.COMPLETED,
                )
                .order_by(ApiContract.created_at.desc())
            )
            c_res = await db.execute(c_stmt)
            contract = c_res.scalars().first()

        # 3. Create initial IntegrationPlan row
        plan = IntegrationPlan(
            project_id=project_id,
            snapshot_id=snapshot.id,
            contract_id=contract.id if contract else None,
            status=IntegrationPlanStatus.PENDING,
            candidates=[],
            required_credentials=[],
            unresolved_questions=[],
            evidence={},
            metadata_={},
        )
        db.add(plan)
        await db.commit()
        await db.refresh(plan)

        # Record audit event: plan generation started
        await acquisition_service.record_audit(
            db,
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            event_type="repository.integration_plan.started",
            resource_id=plan.id,
            payload={
                "snapshot_id": str(snapshot.id),
                "contract_id": str(contract.id) if contract else None,
                "commit_sha": snapshot.commit_sha,
            },
        )
        await db.commit()

        try:
            workspace_path = workspace_manager.get_workspace_path(
                organization_id, project_id, snapshot.id
            )
            real_workspace = workspace_path.resolve() if workspace_path.exists() else None

            discovery_meta = discovery_run.metadata_ or {}
            dependencies = discovery_meta.get("dependencies", [])
            dep_names_lower = {d.get("name", "").lower(): d for d in dependencies}

            # 4. Extract configuration variable names from workspace files (ZERO values stored)
            declared_env_vars: dict[str, list[dict[str, Any]]] = {}
            if real_workspace and real_workspace.exists():
                candidate_config_files = [
                    f
                    for f in real_workspace.iterdir()
                    if f.is_file()
                    and f.name.lower()
                    in {
                        ".env.example",
                        ".env.sample",
                        ".env.template",
                        "docker-compose.yml",
                        "docker-compose.yaml",
                    }
                ]

                for cfg_file in candidate_config_files:
                    rel_f = cfg_file.relative_to(real_workspace).as_posix()
                    try:
                        content = cfg_file.read_text(encoding="utf-8", errors="ignore")
                        lines = content.splitlines()
                        for idx, line in enumerate(lines):
                            stripped = line.strip()
                            if not stripped or stripped.startswith("#"):
                                continue

                            # Matches VAR_NAME=...
                            env_match = re.match(r"^([A-Z0-9_]{2,})\s*=", stripped)
                            if env_match:
                                var_name = env_match.group(1)
                                declared_env_vars.setdefault(var_name, []).append({
                                    "file": rel_f,
                                    "line": idx + 1,
                                    "reason": f"Declared in environment template {rel_f}",
                                })

                            # Matches ${VAR_NAME} in docker-compose
                            dc_matches = re.findall(r"\$\{([A-Z0-9_]{2,})", stripped)
                            for dc_var in dc_matches:
                                declared_env_vars.setdefault(dc_var, []).append({
                                    "file": rel_f,
                                    "line": idx + 1,
                                    "reason": f"Referenced in {rel_f}",
                                })
                    except OSError:
                        continue

            # 5. Detect Candidates & Infer Credentials
            candidates: list[dict[str, Any]] = []
            required_credentials: list[dict[str, Any]] = []
            unresolved_questions: list[dict[str, Any]] = []

            for entry in DEPENDENCY_CATALOG:
                matched_deps = []
                for key in entry["keys"]:
                    if key in dep_names_lower:
                        matched_deps.append(dep_names_lower[key])
                    else:
                        # Check partial substring match
                        for d_name, d_obj in dep_names_lower.items():
                            if key in d_name and d_obj not in matched_deps:
                                matched_deps.append(d_obj)

                if matched_deps:
                    evidence_list = [
                        {
                            "file": d.get("manifest_file", "manifest"),
                            "reason": f"Declared dependency '{d.get('name')}' ({d.get('version_spec', 'any')})",
                        }
                        for d in matched_deps
                    ]

                    # Check if expected environment variables are configured
                    configured_vars = [
                        v for v in entry["env_vars"] if v in declared_env_vars
                    ]

                    confidence = "HIGH" if configured_vars else "MEDIUM"

                    candidates.append({
                        "name": entry["name"],
                        "type": entry["type"],
                        "source": "DETECTED",
                        "confidence": confidence,
                        "description": entry["description"],
                        "evidence": evidence_list,
                    })

                    # Add required credentials for detected candidate
                    for var_name in entry["env_vars"]:
                        # Credential type inference
                        cred_type = "API_KEY"
                        if "URL" in var_name or "URI" in var_name:
                            cred_type = "CONNECTION_STRING"
                        elif "SECRET" in var_name:
                            cred_type = "SECRET_KEY"
                        elif "TOKEN" in var_name:
                            cred_type = "TOKEN"
                        elif "PASSWORD" in var_name:
                            cred_type = "PASSWORD"

                        var_evidence = declared_env_vars.get(var_name, evidence_list)

                        required_credentials.append({
                            "name": var_name,
                            "type": cred_type,
                            "service": entry["name"],
                            "required": True,
                            "sensitive": True,  # NEVER store or display value
                            "description": f"{entry['name']} configuration parameter {var_name}",
                            "evidence": var_evidence,
                        })

                    # If HIGH-importance service has no declared config in .env.example, formulate question
                    if not configured_vars and entry["type"] in {"DATABASE", "PAYMENTS", "AUTHENTICATION"}:
                        unresolved_questions.append({
                            "id": f"Q-CONFIG-{entry['name'].upper().replace(' ', '_')}-01",
                            "category": "CONFIGURATION",
                            "question": (
                                f"{entry['name']} is declared in dependencies, but no environment configuration "
                                f"(e.g. {', '.join(entry['env_vars'][:2])}) was found in environment templates."
                            ),
                            "impact": "HIGH",
                            "suggested_action": f"Add {entry['env_vars'][0]} to your .env.example template.",
                            "evidence": evidence_list,
                        })

            # 6. Add any remaining declared sensitive env vars not already linked
            existing_cred_names = {c["name"] for c in required_credentials}
            for env_name, env_ev in declared_env_vars.items():
                if env_name not in existing_cred_names:
                    is_sensitive = any(re.search(pat, env_name) for pat in SENSITIVE_PATTERNS)
                    cred_type = "API_KEY"
                    if "URL" in env_name or "URI" in env_name:
                        cred_type = "CONNECTION_STRING"
                    elif "SECRET" in env_name:
                        cred_type = "SECRET_KEY"
                    elif "TOKEN" in env_name:
                        cred_type = "TOKEN"
                    elif "PASSWORD" in env_name:
                        cred_type = "PASSWORD"

                    required_credentials.append({
                        "name": env_name,
                        "type": cred_type,
                        "service": None,
                        "required": True,
                        "sensitive": is_sensitive,
                        "description": f"Declared environment variable {env_name}",
                        "evidence": env_ev,
                    })

            # 7. Check Contract Discrepancies if ApiContract exists
            if contract and contract.reconciliation:
                recon = contract.reconciliation
                doc_only = recon.get("documented_only_count", 0)
                conflicts = recon.get("conflict_count", 0)

                if doc_only > 0:
                    unresolved_questions.append({
                        "id": "Q-CONTRACT-UNIMPLEMENTED-01",
                        "category": "CONTRACT",
                        "question": (
                            f"API Contract declares {doc_only} endpoint(s) with no matching code route implementation."
                        ),
                        "impact": "HIGH",
                        "suggested_action": "Review API contract specification or implement missing route handlers.",
                        "evidence": [
                            {"file": f.get("source_file") or "contract", "reason": f.get("details", "")}
                            for f in recon.get("findings", [])
                            if f.get("category") == "DOCUMENTED_ONLY"
                        ][:5],
                    })

                if conflicts > 0:
                    unresolved_questions.append({
                        "id": "Q-CONTRACT-CONFLICT-01",
                        "category": "CONTRACT",
                        "question": (
                            f"Found {conflicts} path/method conflict(s) between API contract specification and code routes."
                        ),
                        "impact": "HIGH",
                        "suggested_action": "Reconcile HTTP method handlers with the API contract specification.",
                        "evidence": [
                            {"file": f.get("source_file") or "contract", "reason": f.get("details", "")}
                            for f in recon.get("findings", [])
                            if f.get("category") == "CONFLICT"
                        ][:5],
                    })

            # 8. Deterministic sorting
            candidates = sorted(candidates, key=lambda x: x["name"])
            required_credentials = sorted(required_credentials, key=lambda x: x["name"])
            unresolved_questions = sorted(unresolved_questions, key=lambda x: x["id"])

            # 9. Plan Status Determination
            has_high_impact = any(q.get("impact") == "HIGH" for q in unresolved_questions)
            plan_status = (
                IntegrationPlanStatus.REVIEW_REQUIRED
                if has_high_impact
                else IntegrationPlanStatus.READY
            )

            plan.status = plan_status
            plan.candidates = candidates
            plan.required_credentials = required_credentials
            plan.unresolved_questions = unresolved_questions
            plan.evidence = {
                "dependencies_scanned": len(dependencies),
                "env_vars_declared": len(declared_env_vars),
                "has_contract": contract is not None,
            }
            plan.metadata_ = {
                "candidates_count": len(candidates),
                "credentials_count": len(required_credentials),
                "unresolved_questions_count": len(unresolved_questions),
                "status": plan_status.value,
            }

            await db.commit()
            await db.refresh(plan)

            # Record audit event: plan generation completed
            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.integration_plan.completed",
                resource_id=plan.id,
                payload={
                    "snapshot_id": str(snapshot.id),
                    "plan_id": str(plan.id),
                    "status": plan_status.value,
                    "candidates_count": len(candidates),
                    "credentials_count": len(required_credentials),
                    "unresolved_questions_count": len(unresolved_questions),
                },
            )
            await db.commit()
            return plan

        except Exception as exc:
            logger.exception("Integration planning failed")
            plan.status = IntegrationPlanStatus.FAILED
            plan.metadata_ = {"error": str(exc)}
            await db.commit()

            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.integration_plan.failed",
                resource_id=plan.id,
                payload={"error": str(exc)},
            )
            await db.commit()
            raise


integration_planning_service = IntegrationPlanningService()
