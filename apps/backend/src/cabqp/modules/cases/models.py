"""SQLAlchemy Database Models for Verification Cases.

Standard: Quality-first 2026 Production Architecture.
Table: verification_cases
Key Invariant: Strict column typing, JSONB structured storage, and status enums.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.types import JSON, TypeDecorator, CHAR
from cabqp.shared.database import Base


class GUID(TypeDecorator):
    """Platform-independent GUID/UUID type.
    Uses PostgreSQL's native UUID type, otherwise uses CHAR(36).
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return str(value)
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            try:
                return uuid.UUID(str(value))
            except ValueError:
                return value
        return value


class FlexibleJSON(TypeDecorator):
    """Platform-independent JSON type.
    Uses PostgreSQL's JSONB for indexing and query performance,
    falls back to standard JSON for SQLite compatibility.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class VerificationCase(Base):
    """SQLAlchemy Model mapping to 'verification_cases' table in database."""

    __tablename__ = "verification_cases"

    id = Column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
        doc="Khóa chính UUID gen_random_uuid()",
    )

    # Subject payload stored as JSONB
    subject = Column(
        FlexibleJSON(),
        nullable=False,
        doc="Thông tin đối tượng: fullName, birthYear, identifier, position, department, cccd",
    )

    # Unit & Organization categorization
    current_unit = Column(
        String(255),
        nullable=False,
        index=True,
        doc="Tên đơn vị công tác hiện tại hoặc gần nhất",
    )

    organization_type = Column(
        String(50),
        nullable=False,
        index=True,
        doc="Phân loại cơ quan: 'BCA' | 'BQP' | 'OTHER' | 'UNKNOWN'",
    )

    subject_group = Column(
        String(100),
        nullable=False,
        doc="Nhóm đối tượng: Sĩ quan, Hạ sĩ quan, CNVQP, v.v.",
    )

    salary_status = Column(
        String(100),
        nullable=False,
        doc="Tình trạng chi trả lương theo ngân sách",
    )

    # Eligibility & Evidence payloads
    eligibility = Column(
        FlexibleJSON(),
        nullable=False,
        default=dict,
        doc="Chi tiết chế độ chính sách và căn cứ pháp lý áp dụng",
    )

    evidence = Column(
        FlexibleJSON(),
        nullable=False,
        default=list,
        doc="Danh sách chứng cứ đối soát và nguồn dữ liệu kiểm chứng",
    )

    # Resolution & Workflow statuses
    resolution_status = Column(
        String(50),
        nullable=False,
        index=True,
        doc="Trạng thái phân giải: 'MATCHED' | 'AMBIGUOUS' | 'NOT_FOUND' | 'CONFLICT'",
    )

    workflow_status = Column(
        String(50),
        nullable=False,
        index=True,
        doc="Trạng thái quy trình: 'PROCESSING' | 'NEED_REVIEW' | 'COMPLETED' | 'FAILED'",
    )

    audit_notes = Column(
        Text,
        nullable=True,
        doc="Ghi chú thẩm định nghiệp vụ hoặc nhật ký đối soát",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self):
        """Serialize model instance to dictionary representation."""
        return {
            "id": str(self.id),
            "subject": self.subject,
            "current_unit": self.current_unit,
            "organization_type": self.organization_type,
            "subject_group": self.subject_group,
            "salary_status": self.salary_status,
            "eligibility": self.eligibility,
            "evidence": self.evidence,
            "resolution_status": self.resolution_status,
            "workflow_status": self.workflow_status,
            "audit_notes": self.audit_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
