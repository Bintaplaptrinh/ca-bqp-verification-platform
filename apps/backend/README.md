# Backend Layer — CA/BQP Verification Platform

Dịch vụ backend FastAPI chuẩn hóa cho **Hệ thống Tra cứu & Xác minh Đối tượng CA/BQP** tuân thủ các quy định nghiệp vụ và kiến trúc **Quality-first 2026**.

---

## 1. Cấu trúc thư mục

```
apps/backend/
├── main.py                      # FastAPI Application Entry Point & CORS Setup
├── requirements.txt             # Danh sách dependencies chuẩn
├── README.md                    # Hướng dẫn cài đặt & vận hành
├── tests/
│   └── test_verification.py     # Bộ kiểm thử Pytest kiểm tra Endpoints & Invariants
└── src/
    └── cabqp/
        ├── api/
        │   ├── __init__.py
        │   └── cases.py         # HTTP Endpoints: POST & GET /api/v1/verification/cases
        ├── modules/
        │   └── cases/
        │       └── models.py    # SQLAlchemy DB Models (verification_cases table)
        └── shared/
            └── database.py      # SQLAlchemy Engine & Session Configuration (.env)
```

---

## 2. Hướng dẫn cài đặt & Khởi chạy cục bộ

### Bước 1: Khởi tạo môi trường ảo Python (Python 3.10+)

```bash
# Di chuyển vào thư mục backend
cd apps/backend

# Tạo virtual environment
python -m venv venv

# Kích hoạt virtual environment:
# Trên Linux / macOS:
source venv/bin/activate
# Trên Windows:
# venv\Scripts\activate
```

### Bước 2: Cài đặt dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Bước 3: Khởi chạy FastAPI Server

```bash
python -m uvicorn cabqp.main:app --reload --port 8000
```

Khi server khởi chạy thành công:
- **API Base URL**: `http://localhost:8000`
- **Tài liệu Swagger UI tương tác**: `http://localhost:8000/docs`
- **Tài liệu ReDoc**: `http://localhost:8000/redoc`
- **Kiểm tra tình trạng (Health check)**: `http://localhost:8000/health`

---

## 3. Danh sách API Endpoints chính

### 1. Tiếp nhận & Xác minh hồ sơ
- **Endpoint**: `POST /api/v1/verification/cases`
- **Mô tả**: Tiếp nhận thông tin đối tượng từ giao diện, chạy động cơ quy tắc và đối chiếu danh mục Master Units.
- **Payload mẫu**:
  ```json
  {
    "full_name": "Nguyễn Văn A",
    "birth_year": "1985",
    "current_unit": "Cục Cảnh sát điều tra tội phạm về trật tự xã hội (C02)",
    "identifier": "CA-8492",
    "position": "Cán bộ điều tra",
    "subject_group": "SQ_CAND"
  }
  ```
- **Response trả về**: Chi tiết hồ sơ, tổ chức quản lý (`BCA`/`BQP`/`OTHER`/`UNKNOWN`), `resolution_status`, `workflow_status`, `eligibility` (chế độ an sinh) và `evidence` (bằng chứng đối soát).

### 2. Tra cứu chi tiết hồ sơ
- **Endpoint**: `GET /api/v1/verification/cases/{case_id}`
- **Mô tả**: Lấy đầy đủ thông tin hồ sơ và căn cứ pháp lý theo UUID.

### 3. Tải lên tài liệu & Trích xuất tự động (OCR & Multi-Format Parsing)
- **Endpoint**: `POST /api/v1/cases/upload`
- **Mô tả**: Tải file tài liệu quyết định/hồ sơ (`.pdf`, `.docx`, `.txt`, `.png`, `.jpg`), tự động bóc tách thực thể họ tên, số hiệu, đơn vị công tác (`CURRENT_WORK_UNIT`) và đối soát qua Master Unit Registry.
- **Tham số form-data**:
  - `file`: Tệp tài liệu cần phân tích.
  - `full_name_hint` *(tùy chọn)*: Gợi ý họ tên nếu cần bổ trợ trích xuất.

---

## 4. Kiến trúc Pipeline Trích xuất Tài liệu (Document Intake & VietOCR)

Hệ thống được thiết kế theo mô hình **Đa kênh thông minh (Smart Multi-Engine Parser)** nằm tại `cabqp/modules/intake/extractors.py`:

```
                    ┌─────────────────────────┐
                    │ File Upload / Document  │
                    └────────────┬────────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           ▼                     ▼                     ▼
   [File Word .docx]       [Tài liệu PDF]         [Ảnh chụp .png/.jpg]
           │                     │                     │
      python-docx            pdfplumber / pypdf     VietOCR (VGG-Transformer)
  (Trích xuất bảng/đoạn)  (Bóc tách số hóa text)  (Mô hình OCR tiếng Việt)
           │                     │                     │
           └─────────────────────┼─────────────────────┘
                                 ▼
                     [Văn bản thô đã chuẩn hóa]
                                 │
                                 ▼
                    [InputProcessor NLP Engine]
              • Chuẩn hóa Unicode tiếng Việt (NFC)
              • Regex nhận diện mã số: CA-xxxx, BQP-xxxx, CCCD 12 số
              • Phân biệt CURRENT_WORK_UNIT vs FORMER_WORK_UNIT (Invariant 3)
                                 │
                                 ▼
                 [Master Unit Registry & Policy Engine]
```

### Cài đặt thư viện OCR & Document Parsers:

```bash
# Cài đặt các bộ đọc file Word & PDF thông thường:
pip install python-docx pdfplumber pypdf pillow

# Cài đặt VietOCR (chuyên dụng nhận diện chữ tiếng Việt có dấu từ ảnh/scan):
pip install vietocr
```

*Ghi chú*:
- Module `extractors.py` sử dụng kỹ thuật **Lazy Loading** đối với VietOCR. Nếu môi trường chưa cài PyTorch/VietOCR hoặc chạy trên thiết bị nhẹ, hệ thống sẽ tự động chuyển sang chế độ fallback an toàn mà **không làm dừng hay crash server**.
- Khi chạy VietOCR trên server production hoặc máy local cá nhân, mô hình `vgg_transformer` sẽ tự động tải trọng số cấu hình CPU trong lần chạy đầu tiên.

---

## 5. Chạy bộ kiểm thử tự động (Pytest)

Dự án đi kèm bộ test toàn diện kiểm tra các Business Invariants:

```bash
# Chạy tất cả các test case
pytest tests/ -v

# Chạy riêng kiểm thử verification & business invariants
pytest tests/test_verification.py -v

# Chạy kiểm thử SCRUM-14 (Input Processing, NFC normalization & Invariant 3)
pytest tests/test_intake_scrum14.py -v
```

### Các Invariant được kiểm định tự động:
1. **Invariant 1**: Trạng thái `NOT_FOUND` tuyệt đối không bị tự ý ép thành `OTHER` (bắt buộc phải là `UNKNOWN`).
2. **Invariant 2**: Khi thiếu dữ kiện xác định đối tượng hoặc có sự mơ hồ (`AMBIGUOUS`), trạng thái quy trình chuyển sang `NEED_REVIEW`.
3. **Invariant 3**: Xử lý văn bản điều động có nhiều đơn vị: Luôn bóc tách đúng đơn vị công tác hiện tại (`CURRENT_WORK_UNIT`), không lấy ngẫu nhiên đơn vị cũ (`FORMER_WORK_UNIT`).
