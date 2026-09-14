"""Pytest Test Suite for CA/BQP Verification Platform.

Quality-first 2026 Production Architecture Standard.
Validates business invariants, API contracts, and policy engine abstention behaviors.
"""

import pytest
from fastapi.testclient import TestClient

from cabqp.main import app
from cabqp.modules.cases.schemas import (
    OrganizationType,
    ResolutionStatus,
    WorkflowStatus,
)

client = TestClient(app)


def test_health_endpoint():
    """Verify backend health check returns status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ca-bqp-backend"


def test_full_response_contract_structure():
    """
    Quality-first 2026 Mandate:
    Response data MUST strictly contain:
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
    payload = {
        "input_type": "MANUAL_TEXT",
        "subject": {
            "full_name": "Nguyễn Văn A",
            "birth_year": "1985",
            "position": "Cán bộ điều tra",
            "department": "Đơn vị X - Cục CSDT",
            "identifier": "CA-8492",
        },
    }
    response = client.post("/api/v1/cases/verify", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Assert all mandatory top-level contract keys exist
    required_keys = [
        "id",
        "case_code",
        "subject",
        "current_unit",
        "organization_type",
        "subject_group",
        "salary_status",
        "eligibility",
        "evidence",
        "resolution_status",
        "workflow_status",
        "created_at",
    ]
    for key in required_keys:
        assert key in data, f"Missing required response field: {key}"

    # Verify Evidence structure
    assert "source_kind" in data["evidence"]
    assert "registry_version" in data["evidence"]
    assert "policy_version" in data["evidence"]
    assert "decision_confidence" in data["evidence"]


def test_business_invariant_1_not_found_is_not_other():
    """
    Business Invariant 1:
    'NOT_FOUND' không được đồng nghĩa với 'OTHER'.
    Một đơn vị/đối tượng không tìm thấy trong Master Registry chỉ phản ánh thiếu dữ liệu
    hoặc chưa số hóa, KHÔNG được tự ý gán nhãn OTHER (Dân sự/Ngoài ngành).
    """
    payload = {
        "input_type": "MANUAL_TEXT",
        "subject": {
            "full_name": "Lê Hoàng D",
            "birth_year": "1994",
            "position": "Nhân viên",
            "department": "Đơn vị chưa đăng ký số hóa",
            "identifier": "CA-8492",
        },
    }
    response = client.post("/api/v1/cases/verify", json=payload)
    assert response.status_code == 200
    data = response.json()

    # If resolution is NOT_FOUND, organization_type must NOT be OTHER
    if data["resolution_status"] == ResolutionStatus.NOT_FOUND.value:
        assert data["organization_type"] != OrganizationType.OTHER.value, (
            "INVARIANT VIOLATION: NOT_FOUND was coerced into OTHER without positive civilian proof!"
        )
        assert data["organization_type"] == OrganizationType.UNKNOWN.value


def test_business_invariant_2_no_inference_solely_from_unit_name():
    """
    Business Invariant 2:
    Không được suy ra 'người thuộc lực lượng' chỉ từ tên đơn vị nếu thiếu dữ kiện nhóm đối tượng.
    Nếu phát hiện nhiều ứng viên hoặc chưa rõ nhóm đối tượng, hệ thống phải trả AMBIGUOUS
    và chuyển workflow_status sang NEED_REVIEW thay vì tự ép hoàn tất.
    """
    payload = {
        "input_type": "MANUAL_TEXT",
        "subject": {
            "full_name": "Trần Văn Bình",
            "birth_year": "1985",
            "position": "Cán bộ",
            "department": "Công an quận Hoàng Mai",
        },
    }
    response = client.post("/api/v1/cases/verify", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Must abstain and demand human review
    assert data["resolution_status"] == ResolutionStatus.AMBIGUOUS.value
    assert data["workflow_status"] == WorkflowStatus.NEED_REVIEW.value
    assert data["candidates"] is not None
    assert len(data["candidates"]) >= 2, "Must return candidate options for disambiguation"


def test_business_invariant_3_strict_error_handling_and_no_forced_conclusion():
    """
    Business Invariant 3:
    Phải có cơ chế xử lý lỗi chặt chẽ (Error Handling) và không tự động ép kết luận
    khi thiếu trường dữ liệu bắt buộc (trả về trạng thái NEED_REVIEW).
    """
    # Empty name or missing mandatory attributes
    payload = {
        "input_type": "MANUAL_TEXT",
        "subject": {
            "full_name": "   ",  # Invalid empty name
            "birth_year": "1990",
        },
    }
    response = client.post("/api/v1/cases/verify", json=payload)
    assert response.status_code == 200
    data = response.json()

    # System must abstain and signal NEED_REVIEW
    assert data["workflow_status"] == WorkflowStatus.NEED_REVIEW.value
    assert data["resolution_status"] == ResolutionStatus.NOT_FOUND.value
    assert data["organization_type"] == OrganizationType.UNKNOWN.value


def test_human_review_workflow():
    """Verify that a reviewer can inspect an ambiguous case and apply authoritative decision."""
    # 1. Create an ambiguous case
    create_res = client.post(
        "/api/v1/cases/verify",
        json={
            "input_type": "MANUAL_TEXT",
            "subject": {
                "full_name": "Trần Văn Bình",
                "birth_year": "1985",
                "department": "Công an quận Hoàng Mai",
            },
        },
    )
    case_id = create_res.json()["id"]

    # 2. Officer reviews and confirms
    review_res = client.post(
        f"/api/v1/cases/{case_id}/review",
        json={
            "workflow_status": "COMPLETED",
            "organization_type": "BCA",
            "subject_group": "Cán bộ, công chức",
            "review_notes": "Đã đối chiếu bản gốc quyết định điều động công tác số 45/QĐ-BCA.",
            "reviewer_id": "CB-9928",
        },
    )
    assert review_res.status_code == 200
    reviewed_data = review_res.json()
    assert reviewed_data["workflow_status"] == "COMPLETED"
    assert reviewed_data["organization_type"] == "BCA"
    assert reviewed_data["subject_group"] == "Cán bộ, công chức"
    assert "CB-9928" in reviewed_data["reviewed_by"]
