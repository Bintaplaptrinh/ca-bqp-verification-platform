"""Pydantic V2 Schemas for CA/BQP Verification Platform Cases Module.

Quality-first 2026 Production Architecture Standard.
Enforces strict schema validation for input requests and output contracts.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field


class OrganizationType(str, Enum):
    """Organization jurisdiction classification."""
    BCA = "BCA"          # Bộ Công an
    BQP = "BQP"          # Bộ Quốc phòng
    OTHER = "OTHER"      # Dân sự hoặc ngoài ngành
    UNKNOWN = "UNKNOWN"  # Chưa đủ căn cứ xác định


class ResolutionStatus(str, Enum):
    """Status of unit and identity resolution against Master Unit Registry."""
    MATCHED = "MATCHED"        # Khớp chính xác với đơn vị và căn cứ
    AMBIGUOUS = "AMBIGUOUS"    # Tìm thấy nhiều ứng viên gần nhau
    NOT_FOUND = "NOT_FOUND"    # Không tìm thấy trong Registry hiện tại
    CONFLICT = "CONFLICT"      # Xung đột thông tin giữa các trường


class WorkflowStatus(str, Enum):
    """Lifecycle workflow status of the verification case."""
    PROCESSING = "PROCESSING"    # Đang trong tiến trình trích xuất / đối soát
    NEED_REVIEW = "NEED_REVIEW"  # Chuyển cán bộ chuyên môn thẩm định
    COMPLETED = "COMPLETED"      # Đã xác định đầy đủ căn cứ và kết luận
    FAILED = "FAILED"            # Lỗi hệ thống hoặc định dạng không hợp lệ


class InputType(str, Enum):
    """Channel of intake."""
    MANUAL_TEXT = "MANUAL_TEXT"
    FILE_UPLOAD = "FILE_UPLOAD"
    BATCH_JOB = "BATCH_JOB"


# ============================================================================
# Input Schemas
# ============================================================================

class SubjectInput(BaseModel):
    """Identity attributes for verification input."""
    model_config = ConfigDict(extra="allow")

    full_name: str = Field(..., min_length=2, description="Họ và tên đối tượng (bắt buộc)")
    birth_year: Optional[str] = Field(None, description="Năm sinh hoặc ngày tháng năm sinh")
    position: Optional[str] = Field(None, description="Chức vụ công tác")
    department: Optional[str] = Field(None, description="Đơn vị nghiệp vụ hoặc cơ quan công tác")
    identifier: Optional[str] = Field(None, description="Số hiệu, mã định danh hoặc CCCD")
    extra_info: Optional[str] = Field(None, description="Thông tin bổ sung, quyết định tiếp nhận...")


class VerifyCaseRequest(BaseModel):
    """Request payload for manual verification intake."""
    input_type: InputType = Field(default=InputType.MANUAL_TEXT, description="Loại kênh đầu vào")
    subject: SubjectInput = Field(..., description="Thông tin đối tượng tra cứu")
    notes: Optional[str] = Field(None, description="Ghi chú tác nghiệp của cán bộ")


class ReviewCaseRequest(BaseModel):
    """Request payload for Human Review decision override or confirmation."""
    workflow_status: WorkflowStatus = Field(..., description="Trạng thái phê duyệt mới")
    organization_type: Optional[OrganizationType] = Field(None, description="Phân loại xác nhận")
    subject_group: Optional[str] = Field(None, description="Nhóm đối tượng sau thẩm định")
    review_notes: str = Field(..., min_length=5, description="Lý do chuyên môn hoặc căn cứ hồ sơ")
    reviewer_id: str = Field(..., description="Mã định danh cán bộ đối soát")


# ============================================================================
# Output Contracts
# ============================================================================

class EligibilityAssessment(BaseModel):
    """Evaluation result for specific social policy or insurance entitlement."""
    policy_id: str = Field(..., description="Mã quy tắc chính sách")
    policy_name: str = Field(..., description="Tên chính sách")
    status: str = Field(..., description="Trạng thái hưởng (ELIGIBLE | NOT_ELIGIBLE | INSUFFICIENT_DATA)")
    benefit_description: str = Field(..., description="Mô tả quyền lợi hoặc lý do từ chối")
    legal_basis: str = Field(..., description="Căn cứ pháp lý (Nghị định 157/2025/NĐ-CP,...)")


class EvidenceDetail(BaseModel):
    """Traceability object containing match methods, versions, and audit trail."""
    model_config = ConfigDict(extra="allow")

    source_kind: str = Field(default="SYNTHETIC_DEMO", description="Nguồn dữ liệu đối soát")
    match_method: Optional[str] = Field(None, description="Phương thức so khớp (CANONICAL_EXACT, ALIAS_MATCH, FUZZY)")
    registry_version: str = Field(default="2026.01.v1", description="Phiên bản Master Unit Registry")
    policy_version: str = Field(default="2026.R1", description="Phiên bản Policy Engine")
    decision_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Độ tin cậy tổng hợp")
    rules_triggered: List[str] = Field(default_factory=list, description="Danh sách mã rule đã duyệt")
    audit_notes: Optional[str] = Field(None, description="Ghi chú kiểm toán")


class CandidateMatch(BaseModel):
    """Candidate match when search result is ambiguous or requires manual selection."""
    candidate_id: int
    name: str
    year: str
    department: str
    subject_group: str
    group_badge_style: str = "bg-blue-50 text-blue-700 border-blue-200"
    similarity_score: float = 0.95


class CaseResponse(BaseModel):
    """
    Standard Response Contract for Verification Cases.
    Required by project Quality-first 2026 guidelines to include all standard fields:
    - id
    - subject
    - current_unit
    - organization_type
    - subject_group
    - salary_status
    - eligibility
    - evidence
    - resolution_status
    - workflow_status
    """
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4, description="Mã UUID duy nhất của Case")
    case_code: str = Field(..., description="Mã định danh hiển thị trên UI (#20250909-001)")
    
    # Core Standard Output Fields
    subject: Dict[str, Any] = Field(..., description="Thông tin định danh linh hoạt dạng JSONB")
    current_unit: Optional[str] = Field(None, description="Đơn vị công tác hiện tại đã resolve")
    organization_type: OrganizationType = Field(..., description="Phạm vi quản lý: BCA | BQP | OTHER | UNKNOWN")
    subject_group: Optional[str] = Field(None, description="Nhóm đối tượng chuẩn hóa")
    salary_status: Optional[str] = Field(None, description="Trạng thái chi trả lương & chế độ")
    eligibility: List[EligibilityAssessment] = Field(default_factory=list, description="Danh sách đánh giá quyền lợi")
    evidence: EvidenceDetail = Field(..., description="Chuỗi bằng chứng, phiên bản rule và độ tin cậy")
    resolution_status: ResolutionStatus = Field(..., description="Trạng thái đối chiếu: MATCHED | AMBIGUOUS | NOT_FOUND | CONFLICT")
    workflow_status: WorkflowStatus = Field(..., description="Trạng thái luồng: PROCESSING | NEED_REVIEW | COMPLETED | FAILED")

    # Optional Candidates for AMBIGUOUS state
    candidates: Optional[List[CandidateMatch]] = Field(default=None, description="Danh sách hồ sơ gợi ý khi cần xác minh thêm")
    created_at: str = Field(..., description="Thời điểm khởi tạo hồ sơ")
    reviewed_by: Optional[str] = Field(None, description="Cán bộ thẩm định")
