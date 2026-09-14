"""Pytest Test Suite for Verification Cases API & 2026 Business Invariants.

Standard: Quality-first 2026 Production Architecture.
Tests the endpoints:
- POST /api/v1/verification/cases
- GET /api/v1/verification/cases/{case_id}
And verifies 2026 Invariants:
- Invariant 1: 'NOT_FOUND' must NOT be mapped to 'OTHER'.
- Invariant 2: Missing required factors for Policy Engine must result in 'NEED_REVIEW'.
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Ensure src is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from main import app

client = TestClient(app)


def test_create_verification_case_bca():
    """Test creating a verification case for Ministry of Public Security (BCA)."""
    payload = {
        "full_name": "Nguyễn Văn A",
        "birth_year": "1985",
        "current_unit": "Cục Cảnh sát điều tra tội phạm về trật tự xã hội (C02)",
        "identifier": "CA-8492",
        "position": "Cán bộ điều tra",
        "subject_group": "SQ_CAND",
    }
    response = client.post("/api/v1/verification/cases", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    # Mandatory fields check
    assert "id" in data
    assert data["subject"]["fullName"] == "Nguyễn Văn A"
    assert data["current_unit"] == "Cục Cảnh sát điều tra tội phạm về trật tự xã hội (C02)"
    assert data["organization_type"] == "BCA"
    assert data["subject_group"] == "SQ_CAND"
    assert data["resolution_status"] == "MATCHED"
    assert data["workflow_status"] == "COMPLETED"
    assert "eligibility" in data
    assert data["eligibility"]["benefitsActive"] is True
    assert "evidence" in data
    assert len(data["evidence"]) >= 2


def test_create_verification_case_bqp():
    """Test creating a verification case for Ministry of National Defense (BQP)."""
    payload = {
        "full_name": "Phạm Quốc Dũng",
        "birth_year": "1980",
        "current_unit": "Cục Tác chiến - Bộ Tổng Tham mưu",
        "identifier": "BQP-7712",
        "position": "Sĩ quan tham mưu",
        "subject_group": "QNCN_SI_QUAN",
    }
    response = client.post("/api/v1/verification/cases", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["organization_type"] == "BQP"
    assert data["resolution_status"] == "MATCHED"
    assert data["workflow_status"] == "COMPLETED"
    assert "Luật Sĩ quan" in data["eligibility"]["legalBasis"]
    assert data["eligibility"]["annualLeaveDays"] == 25


def test_business_invariant_1_not_found_never_other():
    """
    CRITICAL BUSINESS INVARIANT 1:
    Trạng thái 'NOT_FOUND' tuyệt đối KHÔNG ĐƯỢC tự ý gán thành 'OTHER'.
    Trường hợp không tìm thấy đơn vị, organization_type bắt buộc phải là 'UNKNOWN'.
    """
    payload = {
        "full_name": "Vô Danh Cần Tìm",
        "birth_year": "1990",
        "current_unit": "Đơn vị không tồn tại hoặc không rõ 99999",
        "identifier": "UNKNOWN-000",
    }
    response = client.post("/api/v1/verification/cases", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["resolution_status"] == "NOT_FOUND"
    assert data["organization_type"] == "UNKNOWN"
    # Verification that it is definitely NOT 'OTHER'
    assert data["organization_type"] != "OTHER"


def test_business_invariant_2_insufficient_data_need_review():
    """
    CRITICAL BUSINESS INVARIANT 2:
    Nếu thiếu dữ kiện hoặc có sự mơ hồ (AMBIGUOUS), workflow_status
    phải chuyển về 'NEED_REVIEW', tuyệt đối không tự ý kết luận 'COMPLETED'.
    """
    payload = {
        "full_name": "Trần Văn Bình",
        "birth_year": "1985",
        "current_unit": "Phòng tham mưu cần xác minh",
        "identifier": "CA-AMBIGUOUS",
        # subject_group is intentionally omitted
    }
    response = client.post("/api/v1/verification/cases", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["resolution_status"] == "AMBIGUOUS"
    assert data["workflow_status"] == "NEED_REVIEW"


def test_create_verification_case_civilian_other():
    """Test creating a verification case for explicitly Civilian/Outside Armed Forces."""
    payload = {
        "full_name": "Lê Hoàng Dân",
        "birth_year": "1994",
        "current_unit": "Đơn vị dân sự ngoài ngành - Công ty Công nghệ",
        "position": "Kỹ sư",
        "subject_group": "HDLD_DAN_SU",
    }
    response = client.post("/api/v1/verification/cases", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["organization_type"] == "OTHER"
    assert data["resolution_status"] == "MATCHED"
    assert data["workflow_status"] == "COMPLETED"


def test_get_verification_case_detail():
    """Test retrieving case detail by UUID."""
    # Seeded UUID
    case_id = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    response = client.get(f"/api/v1/verification/cases/{case_id}")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == case_id
    assert data["subject"]["fullName"] == "Nguyễn Văn A"
    assert data["organization_type"] == "BCA"
    assert data["resolution_status"] == "MATCHED"


def test_get_verification_case_not_found():
    """Test retrieving non-existent UUID returns 404."""
    non_existent_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/verification/cases/{non_existent_id}")
    assert response.status_code == 404
    assert "Không tìm thấy hồ sơ" in response.json()["detail"]


def test_validation_error_blank_name():
    """Test validation fails when full_name is whitespace or empty."""
    payload = {
        "full_name": "   ",
        "current_unit": "Cục CSDT",
    }
    response = client.post("/api/v1/verification/cases", json=payload)
    assert response.status_code == 422


def test_input_intake_pipeline_current_vs_former_unit():
    """
    Test SCRUM-14 & Invariant 3:
    Input Intake pipeline must correctly parse current work unit and not get confused by former unit mentions.
    """
    payload = {
        "full_name": "Trần Hải Nam",
        "birth_year": "1988",
        "current_unit": "Cục Tác chiến - Bộ Tổng Tham mưu",
        "identifier": "BQP-9912",
        "department": "trước đây công tác tại Công ty X, hiện công tác tại Cục Tác chiến",
    }
    response = client.post("/api/v1/verification/cases", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["organization_type"] == "BQP"
    assert "Tác chiến" in data["current_unit"]


def test_input_intake_pipeline_file_upload():
    """
    Test SCRUM-14:
    File upload endpoint (/upload) parses document bytes and creates normalized case.
    """
    file_content = b"HO SO CAN BO: Ho va ten: Tran Quoc Tuan. So hieu: CA-1234. Don vi: Cuc Canh sat A05."
    files = {"file": ("dossier.txt", file_content, "text/plain")}
    response = client.post("/api/v1/verification/cases/upload", files=files)
    assert response.status_code == 201, response.text
    data = response.json()
    assert "id" in data
    assert data["organization_type"] == "BCA"

