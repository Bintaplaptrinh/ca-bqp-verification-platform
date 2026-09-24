# Phân tích nghiệp vụ — Input Intake, Verification, Review và Batch Ingestion (2026)

## 1. Mục tiêu nghiệp vụ

Hệ thống CA/BQP Verification không phải bài toán “phân loại BCA/BQP” đơn lẻ. Một hồ sơ chỉ được xem là xử lý đúng khi đi qua chuỗi nghiệp vụ:

1. tiếp nhận hồ sơ;
2. trích xuất đối tượng và `CURRENT_WORK_UNIT`;
3. resolve đơn vị về Master Unit Registry;
4. xác định `organization_type`;
5. xác định `subject_group` bằng evidence độc lập;
6. chạy Policy/Eligibility Engine theo đúng thời điểm hiệu lực;
7. nếu thiếu/mâu thuẫn evidence thì **abstain** và đưa Human Review;
8. lưu evidence, version và audit để tái lập kết quả.

Nguyên tắc ưu tiên là **precision + khả năng từ chối đúng chỗ**, không ép mọi input thành một kết luận.

## 2. Actor và trách nhiệm

| Actor | Trách nhiệm nghiệp vụ |
|---|---|
| `USER` | Tạo hồ sơ text, upload tài liệu đơn, upload batch; xem Case của mình. |
| `REVIEWER` | Xử lý Case `NEED_REVIEW` trong `coverage_group` được cấp; xác nhận/correct unit hoặc subject group; kết luận thiếu dữ kiện. |
| `ADMIN` | Toàn quyền review; QA Registry/alias/candidate; publish/rollback version; xem audit toàn hệ thống. |
| `SYSTEM` | Router/parser/OCR, extraction, resolver, policy, worker, retry/DLQ, tạo audit kỹ thuật/nghiệp vụ. |

## 3. Business objects chính

| Object | Ý nghĩa |
|---|---|
| `Case` | Hồ sơ nghiệp vụ gốc. Mọi kênh input cuối cùng đều hội tụ về Case. |
| `Document` | Tệp gắn với Case đơn; lưu checksum, storage URI và trạng thái parse. |
| `ExtractedRecord` | Dữ liệu trung gian: subject, position, current/former unit và confidence. |
| `VerificationResult` | Kết quả resolve + subject group + evidence + các version đã sử dụng. |
| `EligibilityAssessment` | Kết quả policy theo từng rule có hiệu lực. |
| `ReviewCase` | Công việc Human Review khi hệ thống không đủ evidence để auto-complete. |
| `BulkIngestJob` | Một lần nhập danh sách nhiều dòng. |
| `BulkIngestRow` | Một dòng nguồn; dòng hợp lệ tạo đúng một Case con. |
| `RowError` | Lỗi/cảnh báo theo đúng dòng và header người dùng nhìn thấy. |

## 4. Ba kênh input và quy tắc định tuyến

### 4.1. Text/manual input

- Tạo một Case ngay.
- Các field người dùng nhập có cấu trúc được ưu tiên hơn việc đoán từ free text.
- `as_of_date` là ngày nghiệp vụ dùng cho cả Registry validity và Policy effective date.
- Nếu người dùng không nhập `as_of_date`, hệ thống khóa theo **ngày tạo Case**, không lấy “ngày chạy lại hiện tại”; điều này bảo đảm reproducibility.

### 4.2. Tài liệu đơn

- PDF/DOCX/image/XLSX dạng biểu mẫu có thể đi endpoint Case đơn.
- Người dùng có thể truyền `as_of_date` cùng multipart upload; nếu bỏ trống, hệ thống khóa theo ngày tạo Case giống text input.
- Router không tin extension; dùng magic-byte/content-aware probe.
- PDF phân loại theo từng trang: `PDF_TEXT / PDF_SCAN / PDF_HYBRID`.
- OCR chỉ chạy ở trang/vùng cần OCR.
- Low quality, OCR rỗng, scan table nguy hiểm hoặc relation extraction yếu → `NEED_REVIEW`.
- `NEED_REVIEW` phải luôn có `ReviewCase` tương ứng; không được có Case “cần review” nhưng biến mất khỏi queue.

### 4.3. Batch XLS/XLSX/CSV

- File danh sách nhiều dòng **không được tạo một Case duy nhất**.
- Luồng đúng:

```text
Upload → probe TABULAR_LIST → profile header → map schema → validate toàn file
      → user confirm mapping → queue → 1 dòng hợp lệ = 1 Case con
```

- Validation pha 1 không tạo Case.
- Dòng ERROR không tạo Case.
- Dòng WARNING vẫn tạo Case nhưng downstream có thể `NEED_REVIEW`.
- Retry phải idempotent theo `(job_id, row_index)` và Case child có idempotency key tương ứng.
- Cùng file được nhận diện bằng SHA-256 để tránh nhập lại toàn bộ danh sách.

## 5. Business invariants bắt buộc

### 5.1. Resolution

1. `NOT_FOUND != OTHER`.
2. Trusted code/canonical exact/approved alias có priority cao hơn fuzzy/model.
3. `CURRENT_WORK_UNIT` phải tách khỏi `FORMER_WORK_UNIT`.
4. Nhiều ORG nhưng không xác định được quan hệ hiện tại → không chọn ORG đầu tiên.
5. Fuzzy/semantic chỉ auto-accept khi score + margin + calibration đủ chuẩn; nếu không → review.

### 5.2. Subject group

- Đơn vị BCA/BQP **không tự chứng minh** người đó là CAND/quân nhân.
- Subject group phải đến từ explicit field hoặc evidence riêng trong position/text.
- Không đủ evidence → `SUBJECT_GROUP_INSUFFICIENT`.

### 5.3. Policy

- Chỉ chạy rule nằm trong effective period của `as_of_date`.
- Rule thiếu `required_fields` → `INSUFFICIENT_DATA`.
- `INSUFFICIENT_DATA` không được coi là Case thành công hoàn toàn; hệ thống tạo `ReviewCase` với reason `POLICY_INSUFFICIENT_DATA`.
- Evidence policy phải lưu `policy_id`, `policy_version`, `facts_used`, `source_ref`, `as_of_date`.
- Policy là deterministic/versioned; không dùng model để override rule.

## 6. Workflow state model

### 6.1. Case

```text
RECEIVED
   ↓
PROCESSING
   ├─ đủ evidence + policy đủ dữ kiện ─────────→ COMPLETED
   ├─ ambiguity / unknown / low quality / thiếu policy facts → NEED_REVIEW
   └─ lỗi terminal không phục hồi được ───────→ FAILED
```

Invariant vận hành: **không có `NEED_REVIEW` mà không có open `ReviewCase`**, trừ thời điểm transaction chưa commit.

### 6.2. Review

```text
OPEN → RESOLVED
  └──→ DISMISSED
```

Ý nghĩa quyết định:

| Decision | Ý nghĩa |
|---|---|
| `CONFIRM` | Xác nhận/correct unit hoặc subject group. Nếu unit đã MATCHED, reviewer không phải nhập lại `unit_id`. |
| `UNKNOWN` | Không đủ evidence xác định `CURRENT_WORK_UNIT`; clear unit và đưa organization về UNKNOWN. |
| `INSUFFICIENT` | Thiếu dữ kiện nghiệp vụ/policy; **không xóa unit đã verify đúng**. |
| `DISMISS` | Đóng review theo hướng fail-closed; Case thành `FAILED`, không coi kết quả tạm là final. |

Review dùng optimistic locking (`expected_version`) để chặn hai reviewer ghi đè lẫn nhau.

### 6.3. Bulk job

```text
UPLOADED
 → PROFILED | AWAITING_MAPPING
 → QUEUED
 → PROCESSING
 → COMPLETED | COMPLETED_WITH_ERRORS | FAILED
```

Row status:

```text
PENDING → SUCCEEDED | FAILED | SKIPPED_DUPLICATE
```

## 7. Validation batch

### 7.1. Mapping

Mapping chỉ cho phép các field nghiệp vụ đã whitelist:

`subject_name, subject_code, position, unit_name, unit_code, subject_group, employment_status, birth_year, as_of_date`.

Không cho:

- map một source header không tồn tại;
- map vào field lạ;
- map hai cột nguồn vào cùng một field đích.

Mapping operator xác nhận chỉ tạo alias candidate `PENDING_QA`; không auto-learn vào production mapping.

### 7.2. Row-level validation

- Thiếu `subject_name` → `MISSING_REQUIRED`/ERROR.
- CCCD/CMND số nhưng sai 9/12 digit → `BAD_FORMAT`/ERROR.
- Trùng personal code trong cùng file → dòng sau `SKIPPED_DUPLICATE`.
- Unit cell chứa nhiều giá trị phân tách `;`/`|` → `AMBIGUOUS_UNIT`/WARNING và Case đi review nếu resolver/relation không chắc.
- `RowError.row_index` phải đúng dòng Excel người dùng nhìn thấy; `column` phải là header gốc.
- `as_of_date` sai định dạng/không tồn tại phải là `BAD_FORMAT` ở pha 1; không được fallback âm thầm sang ngày hiện tại/ngày tạo Case.
- Mã cá nhân dạng số (kể cả có khoảng trắng/dấu gạch) nếu giống CCCD/CMND phải có đúng 9 hoặc 12 chữ số.
- Mọi WARNING dữ liệu (ví dụ `AMBIGUOUS_UNIT`) vẫn tạo Case nhưng **bắt buộc** Case đi Human Review; warning không được chỉ tồn tại trong report rồi bị downstream bỏ qua.

Golden contract `batch_50.xlsx`: 50 dòng → 45 Case; 41 `COMPLETED`, 4 `NEED_REVIEW`, 4 lỗi validation, 1 duplicate skip.

## 8. Async reliability và idempotency

### 8.1. Document

- DB commit và publish async event tách bằng durable Outbox.
- Worker retry; quá số lần retry → Case/Document `FAILED` + DLQ.
- Job replay không xử lý lại tài liệu đã `PARSED` + Case terminal hợp lệ.

### 8.2. Batch

- Confirm job là idempotent; double-click không queue một batch mới.
- `BulkIngestRow` được DB row lock trước khi tạo Case child.
- Case child tra lại idempotency key trước khi insert.
- Reconciler định kỳ redispatch các row còn `PENDING`; do row lock + idempotency nên redispatch an toàn.
- Broker lỗi ngay lúc confirm không làm mất job: job ở `QUEUED`, reconciler thử lại sau.

## 9. Evidence và audit contract

Mỗi Case decision phải lưu tối thiểu:

- `current_unit_raw`, former unit;
- extraction/relation confidence;
- match method, score, margin, calibrated confidence;
- registry/taxonomy/parser/model/threshold version;
- parse method/quality/evidence;
- `as_of_date`;
- policy summary + policy version/facts ở `EligibilityAssessment`;
- reviewer/review id khi có Human Review.

Audit bắt buộc cho:

- Case create/upload;
- Case decision;
- document processing/failure;
- bulk create/confirm;
- bulk child Case create;
- review decision/dismiss;
- Registry QA/version actions.

## 10. RBAC và dữ liệu

- USER chỉ xem Case/batch của mình.
- REVIEWER chỉ review và xem Case thuộc `coverage_group` được cấp (hoặc Case do chính reviewer tạo); không có quyền đọc toàn bộ Case chỉ nhờ role REVIEWER.
- Bulk source/job chỉ owner hoặc ADMIN được xem/xác nhận; REVIEWER không có blanket access vào file danh sách nhiều người.
- ADMIN có quyền toàn hệ thống.
- Review correction không ghi trực tiếp vào Registry production; chỉ tạo candidate chờ QA.
- Source `SYNTHETIC_DEMO` không được masquerade thành OFFICIAL.

## 11. Các gap nghiệp vụ phát hiện trong lần review này và cách sửa

| Mức | Gap trước khi sửa | Rủi ro nghiệp vụ | Cách đã sửa |
|---|---|---|---|
| Critical | Policy thiếu required field vẫn có thể `COMPLETED` | Final hóa hồ sơ khi chưa đủ căn cứ | Policy `INSUFFICIENT_DATA` tạo review `POLICY_INSUFFICIENT_DATA`. |
| Critical | Policy dùng `date.today()` thay vì ngày hồ sơ | Replay cùng Case ở ngày khác có kết quả khác | Dùng `as_of_date`; nếu trống khóa theo `Case.created_at`. |
| Critical | OCR empty/wrong endpoint set `NEED_REVIEW` nhưng không tạo queue item | Reviewer không thấy Case | Worker luôn `_ensure_review_case(...)`. |
| High | UI review không gửi `expected_version` | Mọi review submit bị 422 | UI gửi version và backend giữ optimistic lock. |
| High | `INSUFFICIENT` xóa unit/org đã verify | Làm mất evidence đúng ở stage trước | `INSUFFICIENT` chỉ đóng trục policy/business, giữ resolution. |
| High | `CONFIRM` luôn bắt nhập lại unit | Không xử lý được subject-group-only review | Cho reuse unit MATCHED hiện có. |
| High | Manual dismiss làm Case kẹt `NEED_REVIEW` nhưng review đã đóng | Case không còn đường xử lý | Dismiss → `FAILED` fail-closed. |
| High | Double dispatch row batch có nguy cơ tạo Case trùng | Sai số liệu/case duplicate | Row lock + child idempotency lookup + periodic redispatch safe. |
| Medium | Mapping API nhận field lạ/duplicate target | Dữ liệu đổ sai schema | Whitelist + duplicate-target validation. |
| Medium | Batch user action thiếu audit | Không tái lập ai đã confirm import | Audit `BULK_CREATE`, `BULK_CONFIRM`, child create. |
| Medium | Text API không có `as_of_date` | Không test đúng policy theo lịch sử | Thêm schema + UI date field. |
| High | REVIEWER đọc được toàn bộ Case/batch chỉ nhờ role | Vượt coverage scope, lộ dữ liệu ngoài phạm vi review | Case list/detail lọc theo review scope; bulk chỉ owner/ADMIN. |
| High | Batch WARNING không đảm bảo Case vào review | Cảnh báo `AMBIGUOUS_UNIT` có thể bị mất ý nghĩa downstream | Propagate `_batch_warnings`; warning luôn ép `NEED_REVIEW` và giữ reason cụ thể. |
| High | `as_of_date` sai trong Excel fallback âm thầm | Policy/registry chạy sai mốc thời gian nhưng trông hợp lệ | Phase-1 `BAD_FORMAT`; không tạo Case cho dòng lỗi. |
| Medium | Upload file không truyền được ngày nghiệp vụ | Tài liệu lịch sử luôn bị đánh theo ngày upload | Thêm multipart `as_of_date` + UI upload date. |
| Medium | Review nhận `subject_group` tùy ý | Dữ liệu domain bẩn có thể lọt vào result/policy | Chỉ nhận nhóm trong `KNOWN_GROUPS`; invalid → 422. |
| Medium | Sau Human Review, `result.evidence.policy_summary` có thể stale | Audit UI không khớp EligibilityAssessment mới nhất | Recompute policy rồi refresh summary + `policy_as_of_date`. |

## 12. Traceability: yêu cầu → code → test

| Yêu cầu | Code chính | Regression |
|---|---|---|
| Router structured-first | `modules/document_intelligence/router.py` | `test_input_intelligence_upgrade.py` |
| Quality PASS/FAIL/NOT_APPLICABLE | `document_intelligence/quality.py` | golden quality tests |
| 1 batch row = 1 Case | `modules/bulk/service.py` | `test_golden_batch_50_contract_and_idempotency` |
| Policy thiếu fact → review | `modules/cases/service.py` | `test_policy_missing_required_fact_routes_case_to_review_and_is_audited` |
| Effective-date correctness | `cases/service.py`, `review/service.py` | `test_policy_effective_date_comes_from_case_not_wall_clock` |
| `INSUFFICIENT` không xóa unit | `review/service.py` | `test_review_insufficient_preserves_verified_unit` |
| Subject-group review không cần nhập lại unit | `review/service.py` | `test_subject_group_review_can_confirm_without_reentering_matched_unit` |
| Manual dismiss fail-closed | `review/service.py` | `test_manual_dismiss_fails_closed_instead_of_stranding_need_review_case` |
| Mapping validation | `bulk/service.py` | `test_bulk_mapping_rejects_duplicate_or_unknown_targets` |
| Review optimistic lock UI | `apps/web/src/pages/Reviews.tsx` | JS syntax check + backend optimistic-lock regression |
| Reviewer Case scope | `api/cases.py` | `test_reviewer_case_access_is_limited_to_coverage_scope_and_bulk_is_owner_only` |
| Bulk owner-only access | `api/bulk.py` | `test_reviewer_case_access_is_limited_to_coverage_scope_and_bulk_is_owner_only` |
| Batch warning → review | `bulk/service.py`, `cases/service.py` | `test_batch_warning_always_routes_child_case_to_review` |
| Batch date/CCCD validation | `bulk/service.py` | `test_batch_invalid_date_and_numeric_like_bad_cccd_fail_phase1` |
| Review domain + policy evidence refresh | `review/service.py` | `test_review_rejects_unknown_subject_group_and_refreshes_policy_summary` |

## 13. Ranh giới còn giữ nguyên

- Repo hiện có official-scope policy metadata và synthetic policy generator; **không tự suy diễn mức lương/tiền hưởng thực tế** nếu nguồn rule/dataset không cung cấp. Không được biến demo rule thành kết luận pháp lý thật.
- Benchmark OCR thật vẫn phải chạy với model/weights đã bake trong môi trường deploy; golden CI chỉ khóa logic deterministic.
- Quality target 99%/95% là release target; test unit pass không đồng nghĩa đã chứng minh target trên production corpus.

## 14. Definition of Done cho Input Intake + Review + Batch

Được coi là đạt khi đồng thời:

1. Text/file/batch vào đúng route.
2. Batch list không bao giờ collapse thành một Case.
3. Mọi Case `NEED_REVIEW` có review queue item.
4. Policy dùng effective date ổn định và thiếu field không final hóa Case.
5. Human Review không làm mất evidence đúng ở stage trước.
6. Batch retry/double-dispatch không tạo Case trùng.
7. Evidence + version + audit đủ để trace request → result → reviewer.
8. Golden tests và business workflow regressions xanh.
