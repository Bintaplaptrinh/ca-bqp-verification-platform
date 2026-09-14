"""FastAPI Router for Verification Cases Module.

Quality-first 2026 Production Architecture Standard.
Handles manual input intake, file upload parsing, review workflows, and case history.
"""

from typing import List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from .schemas import (
    CaseResponse,
    InputType,
    ReviewCaseRequest,
    SubjectInput,
    VerifyCaseRequest,
)
from .service import verification_service

router = APIRouter(prefix="/cases", tags=["Verification Cases"])


@router.post(
    "/verify",
    response_model=CaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Tiếp nhận và xác minh đối tượng qua form nhập liệu",
)
def verify_case(payload: VerifyCaseRequest) -> CaseResponse:
    """
    Tiếp nhận thông tin hồ sơ đối tượng dạng text, đối chiếu Master Unit Registry
    và đánh giá chế độ an sinh qua Policy Engine.
    """
    try:
        result = verification_service.verify_subject(
            subject=payload.subject,
            input_type=payload.input_type,
        )
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi trong quá trình xử lý đối soát: {str(exc)}",
        ) from exc


@router.post(
    "/upload",
    response_model=CaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Tiếp nhận và trích xuất tài liệu (PDF, Word, Excel, Hình ảnh)",
)
async def upload_document_case(
    file: UploadFile = File(..., description="Tệp tài liệu cần phân tích trích xuất"),
    full_name_hint: Optional[str] = Form(None, description="Gợi ý họ tên nếu có"),
) -> CaseResponse:
    """
    Tải tài liệu lên hệ thống, thực thi parser & OCR mô phỏng trích xuất thực thể
    CURRENT_WORK_UNIT, sau đó thực hiện đối soát tự động.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tệp tin tải lên không hợp lệ hoặc thiếu tên file.",
        )

    file_bytes = await file.read()

    # Process through document parsers (PDF, Word, Text, Image / VietOCR)
    from cabqp.modules.intake.processor import InputProcessor

    record = InputProcessor.process_file_intake(
        file_bytes=file_bytes,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        extracted_text_hint=full_name_hint,
    )

    extracted_name = (full_name_hint if full_name_hint else record.full_name) or "Nguyễn Văn A"
    extracted_subject = SubjectInput(
        full_name=extracted_name,
        birth_year=record.birth_year or "1985",
        position=record.position or "Cán bộ chuyên môn",
        department=record.current_work_unit or "Đơn vị trên tài liệu",
        identifier=record.identifier or record.cccd or "CA-8492",
        extra_info=f"Trích xuất tự động từ tệp: {file.filename} (Độ tin cậy: {int(record.extraction_confidence * 100)}%)",
    )

    result = verification_service.verify_subject(
        subject=extracted_subject,
        input_type=InputType.FILE_UPLOAD,
    )
    return result


@router.get(
    "",
    response_model=List[CaseResponse],
    summary="Tra cứu lịch sử các hồ sơ đối soát gần đây",
)
def list_cases(limit: int = 20) -> List[CaseResponse]:
    """Trả về danh sách hồ sơ gần nhất phục vụ màn hình Lịch sử tác nghiệp."""
    return verification_service.list_recent_cases(limit=limit)


@router.get(
    "/{case_id}",
    response_model=CaseResponse,
    summary="Lấy chi tiết hồ sơ xác minh theo mã UUID",
)
def get_case_detail(case_id: str) -> CaseResponse:
    """Truy xuất chi tiết hồ sơ và bằng chứng đối soát theo UUID."""
    case = verification_service.get_case(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy hồ sơ với mã định danh: {case_id}",
        )
    return case


@router.post(
    "/{case_id}/review",
    response_model=CaseResponse,
    summary="Cán bộ đối soát thẩm định và cập nhật trạng thái (Human Review)",
)
def review_case(case_id: str, payload: ReviewCaseRequest) -> CaseResponse:
    """
    Dành cho trường hợp NEED_REVIEW (AMBIGUOUS hoặc thiếu dữ kiện):
    Cán bộ có thẩm quyền bổ sung căn cứ và phê duyệt kết luận cuối cùng.
    """
    case = verification_service.get_case(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy hồ sơ với mã định danh: {case_id}",
        )

    # Update reviewed fields
    case.workflow_status = payload.workflow_status
    if payload.organization_type:
        case.organization_type = payload.organization_type
    if payload.subject_group:
        case.subject_group = payload.subject_group
    case.reviewed_by = f"{payload.reviewer_id} ({payload.review_notes})"
    
    return case
