import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.discovery import DiscoveryRun
    from app.models.integration_plan import IntegrationPlan
    from app.models.repository_snapshot import RepositorySnapshot


class ContractStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ContractSource(str, enum.Enum):
    OPENAPI = "OPENAPI"
    SWAGGER = "SWAGGER"
    STATIC_ROUTE = "STATIC_ROUTE"
    DISCOVERY = "DISCOVERY"


class ApiContract(BaseModel):
    __tablename__ = "api_contracts"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    discovery_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ContractStatus] = mapped_column(
        SQLEnum(
            ContractStatus,
            name="contract_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ContractStatus.PENDING,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(
        String(64),
        default="1.0.0",
        nullable=False,
    )
    format: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    servers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    authentication: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    schemas: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    reconciliation: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    snapshot: Mapped["RepositorySnapshot"] = relationship(
        "RepositorySnapshot",
        back_populates="api_contracts",
    )
    discovery_run: Mapped["DiscoveryRun"] = relationship(
        "DiscoveryRun",
        back_populates="api_contracts",
    )
    operations: Mapped[list["ApiOperation"]] = relationship(
        "ApiOperation",
        back_populates="contract",
        cascade="all, delete-orphan",
    )
    integration_plans: Mapped[list["IntegrationPlan"]] = relationship(
        "IntegrationPlan",
        back_populates="contract",
        cascade="all, delete-orphan",
    )


class ApiOperation(BaseModel):
    __tablename__ = "api_operations"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    operation_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    source: Mapped[ContractSource] = mapped_column(
        SQLEnum(
            ContractSource,
            name="contract_source",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    source_file: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )
    source_line: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    authentication_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    request_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    response_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    contract: Mapped["ApiContract"] = relationship(
        "ApiContract",
        back_populates="operations",
    )
