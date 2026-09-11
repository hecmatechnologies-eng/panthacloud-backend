import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.contract import ApiContract, ApiOperation, ContractSource, ContractStatus
from app.models.discovery import DiscoveryRun, DiscoveryStatus
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.services.repository.acquisition import acquisition_service
from app.services.repository.workspace import workspace_manager

logger = logging.getLogger(__name__)


class SnapshotNotReadyError(Exception):
    """Raised when attempting normalization on a snapshot not in READY status."""


class DiscoveryRunNotFoundError(Exception):
    """Raised when no completed discovery run exists for the snapshot."""


class ContractNormalizationError(Exception):
    """Raised when contract normalization fails."""


def canonicalize_path(path: str) -> str:
    """
    Normalizes route paths to canonical OpenAPI parameter format:
    - Replaces Express `:param` with `{param}`
    - Replaces Flask `<param>` or `<converter:param>` with `{param}`
    - Replaces Django `<param>` or `<type:param>` with `{param}`
    - Ensures leading slash
    - Removes trailing slash (unless root `/`)
    """
    if not path:
        return "/"

    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p

    # Strip trailing slash if longer than 1 character
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")

    # Flask/Django <converter:name> -> {name}
    p = re.sub(r"<(?:\w+:)?([a-zA-Z_][a-zA-Z0-9_]*)>", r"{\1}", p)

    # Express /users/:id -> /users/{id}
    p = re.sub(r"(?<=/):([a-zA-Z_][a-zA-Z0-9_]*)", r"{\1}", p)

    return p


def resolve_local_refs(node: Any, root_doc: dict[str, Any], seen_refs: set[str] | None = None) -> Any:
    """
    Recursively resolves local JSON pointer references (#/components/schemas/X or #/definitions/X).
    Refuses external or remote references without network requests.
    Safely breaks circular references.
    """
    if seen_refs is None:
        seen_refs = set()

    if isinstance(node, dict):
        if "$ref" in node:
            ref_val = str(node["$ref"])
            # Check for local references
            if ref_val.startswith("#/"):
                if ref_val in seen_refs:
                    return {"$ref": ref_val, "status": "CIRCULAR_REFERENCE"}

                # Resolve pointer
                parts = ref_val.lstrip("#/").split("/")
                target: Any = root_doc
                valid = True
                for part in parts:
                    # Unescape JSON pointer tokens
                    token = part.replace("~1", "/").replace("~0", "~")
                    if isinstance(target, dict) and token in target:
                        target = target[token]
                    else:
                        valid = False
                        break

                if valid and target is not None:
                    next_seen = seen_refs | {ref_val}
                    resolved = resolve_local_refs(target, root_doc, next_seen)
                    # Merge any sibling keys from node (except $ref)
                    if isinstance(resolved, dict):
                        merged = dict(resolved)
                        for k, v in node.items():
                            if k != "$ref":
                                merged[k] = resolve_local_refs(v, root_doc, next_seen)
                        return merged
                    return resolved
                else:
                    return {"$ref": ref_val, "status": "UNRESOLVED_LOCAL_REFERENCE"}
            else:
                # External / remote reference - NEVER fetch from network or escape sandbox
                return {"$ref": ref_val, "status": "UNRESOLVED_EXTERNAL_REFERENCE"}

        # Recursively resolve dictionary children
        return {k: resolve_local_refs(v, root_doc, seen_refs) for k, v in node.items()}

    elif isinstance(node, list):
        return [resolve_local_refs(item, root_doc, seen_refs) for item in node]

    return node


class ContractNormalizationService:
    async def normalize_contract(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        repository: Repository,
        snapshot: RepositorySnapshot,
        discovery_run_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> ApiContract:
        """
        Executes deterministic contract normalization and route reconciliation.
        """
        if snapshot.status != SnapshotStatus.READY:
            raise SnapshotNotReadyError(
                f"Cannot normalize contract on snapshot with status '{snapshot.status}'. "
                "Snapshot must be in 'READY' status."
            )

        # 1. Locate DiscoveryRun
        if discovery_run_id:
            stmt = select(DiscoveryRun).where(
                DiscoveryRun.id == discovery_run_id,
                DiscoveryRun.snapshot_id == snapshot.id,
            )
            result = await db.execute(stmt)
            discovery_run = result.scalar_one_or_none()
            if not discovery_run:
                raise DiscoveryRunNotFoundError(
                    f"Discovery run '{discovery_run_id}' not found for snapshot."
                )
        else:
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

        # 2. Check workspace path
        workspace_path = workspace_manager.get_workspace_path(
            organization_id, project_id, snapshot.id
        )
        if not workspace_path.exists():
            raise ContractNormalizationError(
                f"Snapshot workspace directory not found at {workspace_path.name}."
            )

        # 3. Create initial ApiContract row
        contract = ApiContract(
            snapshot_id=snapshot.id,
            discovery_run_id=discovery_run.id,
            status=ContractStatus.RUNNING,
            title=f"{repository.name} API Contract",
            version="1.0.0",
            format="pending",
            servers=[],
            authentication=[],
            schemas={},
            reconciliation={},
            metadata_={},
        )
        db.add(contract)
        await db.commit()
        await db.refresh(contract)

        # Record audit event: contract normalization started
        await acquisition_service.record_audit(
            db,
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            event_type="repository.contract.started",
            resource_id=contract.id,
            payload={
                "snapshot_id": str(snapshot.id),
                "discovery_run_id": str(discovery_run.id),
                "commit_sha": snapshot.commit_sha,
            },
        )
        await db.commit()

        try:
            real_workspace = workspace_path.resolve()
            discovery_meta = discovery_run.metadata_ or {}
            contract_findings = discovery_meta.get("api_contracts", [])
            static_routes = discovery_meta.get("routes", [])

            # Check if an OpenAPI / Swagger contract file was discovered
            valid_contracts = [
                c for c in contract_findings if c.get("status") == "VALID"
            ]

            operations_to_add: list[ApiOperation] = []
            servers: list[dict[str, Any]] = []
            authentication_schemes: list[dict[str, Any]] = []
            normalized_schemas: dict[str, Any] = {}
            contract_title = f"{repository.name} API Contract"
            contract_version = "1.0.0"
            contract_format = "discovered"

            documented_ops_by_path_method: dict[tuple[str, str], dict[str, Any]] = {}

            if valid_contracts:
                # Use the primary valid contract (deterministically first)
                primary_contract = min(valid_contracts, key=lambda x: x.get("file", ""))
                contract_file_rel = primary_contract.get("file", "")
                contract_file_path = workspace_manager.assert_path_contained(
                    real_workspace, Path(contract_file_rel)
                )

                content = contract_file_path.read_text(encoding="utf-8", errors="ignore")
                if contract_file_path.suffix.lower() == ".json":
                    raw_doc = json.loads(content)
                else:
                    raw_doc = yaml.safe_load(content)

                if not isinstance(raw_doc, dict):
                    raise ContractNormalizationError("Contract root is not a mapping object.")

                is_openapi = "openapi" in raw_doc
                contract_format = f"openapi_{raw_doc.get('openapi', '3.0')}" if is_openapi else f"swagger_{raw_doc.get('swagger', '2.0')}"

                info = raw_doc.get("info", {}) if isinstance(raw_doc.get("info"), dict) else {}
                if info.get("title"):
                    contract_title = str(info["title"])
                if info.get("version"):
                    contract_version = str(info["version"])

                # Servers
                if is_openapi and isinstance(raw_doc.get("servers"), list):
                    for s in raw_doc["servers"]:
                        if isinstance(s, dict) and s.get("url"):
                            servers.append({
                                "url": str(s["url"]),
                                "description": str(s.get("description", "")),
                            })
                elif not is_openapi and raw_doc.get("host"):
                    host = str(raw_doc.get("host"))
                    base_path = str(raw_doc.get("basePath", ""))
                    servers.append({"url": f"https://{host}{base_path}", "description": "Swagger Host"})

                # Authentication schemes
                global_security = raw_doc.get("security", [])
                global_auth_required = bool(global_security)

                if is_openapi:
                    components = raw_doc.get("components", {})
                    sec_schemes = components.get("securitySchemes", {}) if isinstance(components, dict) else {}
                    if isinstance(sec_schemes, dict):
                        for name, scheme_dict in sec_schemes.items():
                            if isinstance(scheme_dict, dict):
                                authentication_schemes.append({
                                    "name": str(name),
                                    "type": str(scheme_dict.get("type", "unknown")),
                                    "scheme": scheme_dict.get("scheme"),
                                    "bearer_format": scheme_dict.get("bearerFormat"),
                                    "in": scheme_dict.get("in"),
                                    "description": scheme_dict.get("description"),
                                    "flows": scheme_dict.get("flows"),
                                })
                else:
                    # Swagger 2.0 securityDefinitions
                    sec_defs = raw_doc.get("securityDefinitions", {})
                    if isinstance(sec_defs, dict):
                        for name, scheme_dict in sec_defs.items():
                            if isinstance(scheme_dict, dict):
                                authentication_schemes.append({
                                    "name": str(name),
                                    "type": str(scheme_dict.get("type", "unknown")),
                                    "in": scheme_dict.get("in"),
                                    "description": scheme_dict.get("description"),
                                    "flows": None,
                                })

                # Schemas
                raw_schemas = {}
                if is_openapi and isinstance(raw_doc.get("components"), dict):
                    raw_schemas = raw_doc["components"].get("schemas", {}) or {}
                elif not is_openapi:
                    raw_schemas = raw_doc.get("definitions", {}) or {}

                if isinstance(raw_schemas, dict):
                    for schema_name, schema_body in raw_schemas.items():
                        resolved_schema = resolve_local_refs(schema_body, raw_doc)
                        normalized_schemas[str(schema_name)] = resolved_schema

                # Parse paths and operations
                paths = raw_doc.get("paths", {})
                if isinstance(paths, dict):
                    for path_str, path_item in paths.items():
                        if not isinstance(path_item, dict):
                            continue
                        canon_path = canonicalize_path(path_str)
                        for method_name in ["get", "post", "put", "delete", "patch", "options", "head"]:
                            op_dict = path_item.get(method_name)
                            if not isinstance(op_dict, dict):
                                continue

                            method_upper = method_name.upper()
                            op_id = op_dict.get("operationId")
                            summary = op_dict.get("summary")
                            description = op_dict.get("description")
                            tags = op_dict.get("tags", []) if isinstance(op_dict.get("tags"), list) else []

                            op_sec = op_dict.get("security")
                            auth_required = bool(op_sec) if op_sec is not None else global_auth_required

                            # Request Schema
                            req_schema: dict[str, Any] | None = None
                            if is_openapi and "requestBody" in op_dict:
                                rb = op_dict["requestBody"]
                                if isinstance(rb, dict):
                                    content_map = rb.get("content", {})
                                    if isinstance(content_map, dict):
                                        json_content = content_map.get("application/json") or next(iter(content_map.values()), None)
                                        if isinstance(json_content, dict) and "schema" in json_content:
                                            req_schema = resolve_local_refs(json_content["schema"], raw_doc)
                            elif not is_openapi and "parameters" in op_dict:
                                for param in op_dict.get("parameters", []):
                                    if isinstance(param, dict) and param.get("in") == "body" and "schema" in param:
                                        req_schema = resolve_local_refs(param["schema"], raw_doc)
                                        break

                            # Response Schema
                            resp_schema: dict[str, Any] | None = None
                            responses = op_dict.get("responses", {})
                            if isinstance(responses, dict):
                                success_resp = responses.get("200") or responses.get("201") or responses.get("default")
                                if isinstance(success_resp, dict):
                                    if is_openapi:
                                        content_map = success_resp.get("content", {})
                                        if isinstance(content_map, dict):
                                            json_content = content_map.get("application/json") or next(iter(content_map.values()), None)
                                            if isinstance(json_content, dict) and "schema" in json_content:
                                                resp_schema = resolve_local_refs(json_content["schema"], raw_doc)
                                    else:
                                        if "schema" in success_resp:
                                            resp_schema = resolve_local_refs(success_resp["schema"], raw_doc)

                            op_model = ApiOperation(
                                contract_id=contract.id,
                                method=method_upper,
                                path=canon_path,
                                operation_id=str(op_id) if op_id else None,
                                summary=str(summary) if summary else None,
                                description=str(description) if description else None,
                                source=ContractSource.OPENAPI if is_openapi else ContractSource.SWAGGER,
                                source_file=contract_file_rel,
                                source_line=None,
                                authentication_required=auth_required,
                                request_schema=req_schema,
                                response_schema=resp_schema,
                                tags=[str(t) for t in tags],
                                evidence={
                                    "source_file": contract_file_rel,
                                    "raw_path": path_str,
                                    "method": method_upper,
                                },
                            )
                            operations_to_add.append(op_model)
                            documented_ops_by_path_method[(canon_path, method_upper)] = {
                                "operation_id": op_id,
                                "source_file": contract_file_rel,
                                "raw_path": path_str,
                            }

            # Route reconciliation
            # Group static routes by (canonical_path, method.upper())
            static_ops_by_path_method: dict[tuple[str, str], dict[str, Any]] = {}
            for r in static_routes:
                c_path = canonicalize_path(r.get("path", ""))
                m = str(r.get("method", "GET")).upper()
                if m == "ALL":
                    for std_m in ["GET", "POST", "PUT", "DELETE"]:
                        static_ops_by_path_method[(c_path, std_m)] = r
                else:
                    static_ops_by_path_method[(c_path, m)] = r

            reconciliation_findings: list[dict[str, Any]] = []
            matched_count = 0
            documented_only_count = 0
            implemented_only_count = 0
            conflict_count = 0

            # 1. Match documented ops against static routes
            for (c_path, method), doc_info in documented_ops_by_path_method.items():
                if (c_path, method) in static_ops_by_path_method:
                    matched_count += 1
                    static_info = static_ops_by_path_method[(c_path, method)]
                    reconciliation_findings.append({
                        "path": c_path,
                        "method": method,
                        "category": "MATCHED",
                        "details": f"Contract operation matches route handler in {static_info.get('source_file')}",
                        "contract_operation_id": doc_info.get("operation_id"),
                        "source_file": static_info.get("source_file"),
                        "source_line": static_info.get("source_line"),
                    })
                else:
                    # Check if path exists with different methods
                    paths_matching = [
                        m for (p, m) in static_ops_by_path_method if p == c_path
                    ]
                    if paths_matching:
                        conflict_count += 1
                        reconciliation_findings.append({
                            "path": c_path,
                            "method": method,
                            "category": "CONFLICT",
                            "details": f"Path '{c_path}' documented for {method}, but code implements {paths_matching}",
                            "contract_operation_id": doc_info.get("operation_id"),
                            "source_file": None,
                            "source_line": None,
                        })
                    else:
                        documented_only_count += 1
                        reconciliation_findings.append({
                            "path": c_path,
                            "method": method,
                            "category": "DOCUMENTED_ONLY",
                            "details": "Documented in contract specification, but no code route implementation found",
                            "contract_operation_id": doc_info.get("operation_id"),
                            "source_file": doc_info.get("source_file"),
                            "source_line": None,
                        })

            # 2. Check for static routes absent from contract
            for (c_path, method), static_info in static_ops_by_path_method.items():
                if (c_path, method) not in documented_ops_by_path_method:
                    # Check if path was already recorded as CONFLICT
                    already_conflict = any(
                        f["path"] == c_path and f["category"] == "CONFLICT"
                        for f in reconciliation_findings
                    )
                    if not already_conflict:
                        implemented_only_count += 1
                        reconciliation_findings.append({
                            "path": c_path,
                            "method": method,
                            "category": "IMPLEMENTED_ONLY",
                            "details": f"Route handler in {static_info.get('source_file')} is not documented in API contract",
                            "contract_operation_id": None,
                            "source_file": static_info.get("source_file"),
                            "source_line": static_info.get("source_line"),
                        })

                    # If no contract file existed, or route is implemented-only, add as ApiOperation
                    if not valid_contracts:
                        op_model = ApiOperation(
                            contract_id=contract.id,
                            method=method,
                            path=c_path,
                            operation_id=static_info.get("handler"),
                            summary=f"{method} {c_path}",
                            description=f"Statically discovered {static_info.get('framework', 'route')} handler",
                            source=ContractSource.STATIC_ROUTE,
                            source_file=static_info.get("source_file"),
                            source_line=static_info.get("source_line"),
                            authentication_required=False,
                            request_schema=None,
                            response_schema=None,
                            tags=[static_info.get("framework", "StaticRoute")],
                            evidence={
                                "source_file": static_info.get("source_file"),
                                "source_line": static_info.get("source_line"),
                                "framework": static_info.get("framework"),
                            },
                        )
                        operations_to_add.append(op_model)

            # Deterministic sorting
            reconciliation_findings = sorted(
                reconciliation_findings,
                key=lambda x: (x["path"], x["method"], x["category"]),
            )
            operations_to_add = sorted(
                operations_to_add,
                key=lambda x: (x.path, x.method, x.source.value),
            )
            authentication_schemes = sorted(
                authentication_schemes,
                key=lambda x: x["name"].lower(),
            )
            servers = sorted(
                servers,
                key=lambda x: x["url"],
            )

            # Persist operations
            for op_item in operations_to_add:
                db.add(op_item)

            # Update ApiContract
            contract.title = contract_title
            contract.version = contract_version
            contract.format = contract_format
            contract.servers = servers
            contract.authentication = authentication_schemes
            contract.schemas = normalized_schemas
            contract.reconciliation = {
                "matched_count": matched_count,
                "documented_only_count": documented_only_count,
                "implemented_only_count": implemented_only_count,
                "conflict_count": conflict_count,
                "findings": reconciliation_findings,
            }
            contract.status = ContractStatus.COMPLETED
            contract.metadata_ = {
                "operations_count": len(operations_to_add),
                "schemas_count": len(normalized_schemas),
                "authentication_schemes_count": len(authentication_schemes),
                "reconciliation_summary": {
                    "matched": matched_count,
                    "documented_only": documented_only_count,
                    "implemented_only": implemented_only_count,
                    "conflict": conflict_count,
                },
            }

            await db.commit()
            await db.refresh(contract)

            # Record audit event: contract normalization completed
            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.contract.completed",
                resource_id=contract.id,
                payload={
                    "snapshot_id": str(snapshot.id),
                    "contract_id": str(contract.id),
                    "commit_sha": snapshot.commit_sha,
                    "operations_count": len(operations_to_add),
                    "matched_count": matched_count,
                    "conflict_count": conflict_count,
                },
            )
            await db.commit()

            # Eagerly load operations for return
            stmt = (
                select(ApiContract)
                .options(selectinload(ApiContract.operations))
                .where(ApiContract.id == contract.id)
            )
            loaded_result = await db.execute(stmt)
            return loaded_result.scalar_one()

        except Exception as exc:
            logger.exception("Contract normalization failed")
            contract.status = ContractStatus.FAILED
            contract.metadata_ = {"error": str(exc)}
            await db.commit()

            await acquisition_service.record_audit(
                db,
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                event_type="repository.contract.failed",
                resource_id=contract.id,
                payload={"error": str(exc)},
            )
            await db.commit()
            raise


contract_service = ContractNormalizationService()
