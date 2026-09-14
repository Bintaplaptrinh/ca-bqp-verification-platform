# BÁO CÁO TỔNG HỢP KIẾN TRÚC HỆ THỐNG (SYSTEM ARCHITECTURE REPORT)

## HỆ THỐNG TRA CỨU, XÁC MINH ĐỐI TƯỢNG VÀ HỖ TRỢ NGHIỆP VỤ AN SINH BCA/BQP

**Tiêu chuẩn chất lượng:** Quality-first Production Architecture — 2026  
**Mã công việc:** SCRUM-13  
**Tác giả:** Đội ngũ Kỹ thuật Hệ thống CA/BQP  
**Phiên bản tài liệu:** 2026.2.0

---

## 1. MỤC TIÊU VÀ PHẠM VI HỆ THỐNG (SYSTEM SCOPE)

### 1.1. Bài toán nghiệp vụ cốt lõi

Hệ thống giải quyết bài toán tra cứu, thẩm định và đối soát thông tin cán bộ, chiến sĩ, người lao động phục vụ việc xác định phạm vi quản lý của **Bộ Công an (BCA)**, **Bộ Quốc phòng (BQP)** hoặc khối **Dân sự ngoài ngành (OTHER)**; đồng thời áp dụng động cơ chính sách (_Policy/Eligibility Engine_) để đánh giá quyền lợi an sinh xã hội theo các văn bản pháp lý hiện hành (Nghị định 157/2025/NĐ-CP, Thông tư 88/2025/TT-BCA, Thông tư 90/2025/TT-BQP).

Quy trình nghiệp vụ gồm 4 lớp nối tiếp:

1. **Tiếp nhận hồ sơ (Intake):** Đa kênh (chuỗi văn bản trực tiếp hoặc tải tệp tài liệu OCR).
2. **Xác minh đơn vị hiện tại (Unit Resolution):** Đối chiếu với danh bạ thực thể có thẩm quyền (_Master Unit Registry_).
3. **Xác định nhóm đối tượng (Subject Grouping):** Phân định ngạch Sĩ quan, Quân nhân chuyên nghiệp, Công nhân viên quốc phòng, Hợp đồng lao động.
4. **Đánh giá chế độ an sinh (Policy Evaluation):** Đưa ra kết luận quyền lợi có căn cứ pháp lý, chuỗi bằng chứng (_evidence_) và kiểm soát tự động.

### 1.2. Hai kênh đầu vào — Một Case trung gian duy nhất

```text
  [Kênh 1: NHẬP TRỰC TIẾP]             [Kênh 2: TẢI TỆP TÀI LIỆU]
(Form có cấu trúc / Chuỗi tự do)        (PDF / DOCX / XLSX / File Ảnh Scan)
              │                                      │
              ▼                                      ▼
      Validate & Normalize                  Parser / Table Reader / OCR
              │                                      │
              └──────────────────┬───────────────────┘
                                 ▼
                    [CASE + NORMALIZED RECORD]
               (subject, current_unit, identifiers)
```

---

## 2. NGUYÊN TẮC BẤT BIẾN NGHIỆP VỤ (BUSINESS INVARIANTS 2026)

Hệ thống được thiết kế theo tư duy **Abstention-capable Decision Support** (dám từ chối kết luận khi thiếu căn cứ):

1. **Invariant 1 (`NOT_FOUND != OTHER`):**
   Trạng thái `NOT_FOUND` tuyệt đối **không đồng nghĩa với `OTHER`**. Trường hợp Master Registry chưa có dữ liệu, cơ quan quản lý bắt buộc phải là `UNKNOWN`.
2. **Invariant 2 (`COMPLETED Requires Subject Group`):**
   Không suy ra người thuộc lực lượng vũ trang chỉ từ tên đơn vị. Nếu một hồ sơ thuộc BCA/BQP mà chưa đủ căn cứ xác định `subject_group`, hệ thống **không được chuyển sang `COMPLETED` mà bắt buộc phải chuyển sang `NEED_REVIEW`**.
3. **Invariant 3 (`CURRENT_WORK_UNIT Isolation`):**
   Nếu tài liệu chứa nhiều tổ chức/đơn vị (ví dụ đơn vị cũ, cơ quan phối hợp), hệ thống bắt buộc phải bóc tách đúng `CURRENT_WORK_UNIT`, tuyệt đối không lấy thực thể xuất hiện đầu tiên.
4. **Invariant 4 (`Deterministic Policy Rule`):**
   Policy Engine chỉ kết luận khi đủ trường bắt buộc của luật; thiếu trường dữ liệu phải trả về `INSUFFICIENT_DATA` / `NEED_REVIEW`.
5. **Invariant 5 (`Full Provenance & Reproducibility`):**
   Mọi kết luận phải truy vết và tái lập được bằng: `registry_version` + `taxonomy_version` + `policy_version` + `model_version`.

---

## 3. KIẾN TRÚC LUỒNG XỬ LÝ ONLINE (QUALITY-FIRST CRITICAL PATH)

```text
               ┌───────────────────────┐
               │    INPUT (Text/File)  │
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │     INPUT ROUTER      │
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │   PARSER / OCR GATE   │
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │ NORMALIZE & EXTRACTION│ (CURRENT_WORK_UNIT)
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │ CANDIDATE GENERATION  │ (Code, Canonical, Alias, Fuzzy)
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐      ┌─────────────────────────┐
               │    UNIT RESOLUTION    │ ◄─── │   MASTER UNIT REGISTRY  │
               └───────────┬───────────┘      └─────────────────────────┘
                           │
                 [Đủ Evidence tin cậy?]
                 ├── KHÔNG ──► [HUMAN REVIEW / AMBIGUOUS / CONFLICT / UNKNOWN]
                 └── CÓ
                      ▼
               ┌───────────────────────┐
               │  SUBJECT GROUP (Rule) │
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │ POLICY/ELIGIBILITY ENG│ (100% Deterministic & Versioned)
               └───────────┬───────────┘
                           │
                 [Đủ Required Fields?]
                 ├── KHÔNG ──► [NEED_REVIEW: INSUFFICIENT_DATA]
                 └── CÓ
                      ▼
               ┌───────────────────────┐
               │     FINAL RESULT      │
               │ (Evidence + Confidence│
               │  + Version Snapshot)  │
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │ PERSIST & AUDIT LOG   │
               └───────────────────────┘
```

---

## 4. MÔ HÌNH DỮ LIỆU SẢN XUẤT (ERD & SCHEMA DESIGN)

Hệ thống phân tách rõ 2 lane dữ liệu:

- **Lane 1: Intake & Operational Cases** (`CASES`, `DOCUMENTS`, `EXTRACTED_RECORDS`, `VERIFICATION_CASES`).
- **Lane 2: Authoritative Master Registry & Policies** (`UNITS`, `UNIT_CODES`, `UNIT_NAMES`, `POLICY_RULES`, `ELIGIBILITY_ASSESSMENTS`, `AUDIT_LOGS`).

### Chi tiết bảng `verification_cases` lõi:

- `id`: UUID (Khóa chính)
- `subject`: JSONB (fullName, birthYear, identifier, position, department, cccd)
- `current_unit`: VARCHAR(255) (Tên đơn vị công tác chuẩn tắc)
- `organization_type`: VARCHAR(16) (`BCA` | `BQP` | `OTHER` | `UNKNOWN`)
- `subject_group`: VARCHAR(64) (`SQ_CAND`, `QNCN`, `CN_QP`, `HDLD`, `CHUA_RO`)
- `salary_status`: VARCHAR(128) (Tình trạng chi trả lương ngân sách)
- `eligibility`: JSONB (Quyền lợi BHXH, phụ cấp nghề, thâm niên theo NĐ 157/2025/NĐ-CP)
- `evidence`: JSONB (Chuỗi bằng chứng từng trường đối soát)
- `resolution_status`: VARCHAR(16) (`MATCHED` | `AMBIGUOUS` | `NOT_FOUND` | `CONFLICT`)
- `workflow_status`: VARCHAR(16) (`PROCESSING` | `NEED_REVIEW` | `COMPLETED` | `FAILED`)
- `audit_notes`: TEXT (Ghi chú nghiệp vụ / lịch sử thẩm định)
- `created_at`, `updated_at`: TIMESTAMPTZ

---

## 5. BÁO CÁO TIẾN ĐỘ THỰC HIỆN ĐẾN SPRINT 2

### Các hạng mục đã hoàn thành (Done):

1. **Khởi tạo Skeleton & Kiến trúc Monorepo (SCRUM-7):**
   - Phân chia rõ ràng `apps/web` và `apps/backend`.
2. **Xây dựng Database Layer & ORM Models:**
   - Cấu hình kết nối PostgreSQL + SQLite Fallback (`apps/backend/src/cabqp/shared/database.py`).
   - Xây dựng model ORM SQLAlchemy `VerificationCase` hoàn chỉnh.
3. **Phát triển Backend API Endpoints:**
   - Hoàn thành `POST /api/v1/verification/cases` và `GET /api/v1/verification/cases/{case_id}`.
   - Thêm endpoint tiếp nhận tệp tin upload `POST /api/v1/verification/cases/upload`.
4. **Thực thi Input Intake Pipeline (SCRUM-14):**
   - Xây dựng module `apps/backend/src/cabqp/modules/intake/processor.py` chuẩn hóa Unicode NFC, nhận dạng Regex số hiệu ngành (`CA-xxxx`, `BQP-xxxx`), bóc tách độc lập `CURRENT_WORK_UNIT` không lấy nhầm đơn vị cũ.
5. **Giao diện Web Frontend (React Vite Tailwind):**
   - Xây dựng `VerificationModule.jsx` responsive Mobile-first thích ứng đa kích thước màn hình, kết nối Axios trực tiếp sang Backend API.
   - Hỗ trợ stepper trạng thái 4 bước, modal xem hồ sơ gốc, modal đối chiếu chi tiết và tab lịch sử thẩm định.
6. **Kiểm thử tự động (Quality Gates):**
   - Bộ kiểm thử Pytest bao phủ toàn bộ Business Invariants 2026, kiểm tra tính toàn vẹn của dữ liệu và luồng xử lý input.

---
