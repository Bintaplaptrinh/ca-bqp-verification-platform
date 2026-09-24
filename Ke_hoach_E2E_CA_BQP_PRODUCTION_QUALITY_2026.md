# KẾ HOẠCH TRIỂN KHAI END-TO-END

## HỆ THỐNG TRA CỨU, XÁC MINH ĐỐI TƯỢNG VÀ HỖ TRỢ NGHIỆP VỤ AN SINH BCA/BQP

**Quality-first Production Architecture - 2026**

Mục tiêu. Xây dựng một hệ thống hoàn chỉnh có khả năng tiếp nhận thông tin dạng chuỗi hoặc tài liệu,
tự động trích xuất thông tin đối tượng và đơn vị hiện tại, đối chiếu với dữ liệu đơn vị để xác định phạm
vi quản lý Bộ Công an (BCA), Bộ Quốc phòng (BQP) hoặc ngoài phạm vi; đồng thời xác định nhóm
đối tượng và đánh giá thông tin lương/chế độ an sinh bằng một Policy/Eligibility Engine. Mọi kết luận
phải có evidence, version dữ liệu/rule và cơ chế Human Review khi không đủ căn cứ. Thiết kế ưu tiên
chất lượng quyết định: deterministic baseline trước, model chỉ dùng khi thực sự cải thiện kết quả; hệ
thống có khả năng abstain thay vì ép nhãn.

**Đầu vào:** (1) Chuỗi văn bản nhập trực tiếp; hoặc (2) PDF, DOCX, XLSX/XLS, hình ảnh.
Có thể chứa họ tên, mã/số hiệu, tên đơn vị, chức vụ, năm sinh và thông tin
nghiệp vụ.
**Dữ liệu thật:** Mã đơn vị (nếu nguồn có), tên đơn vị, nguồn tham chiếu được thu thập
từ nguồn chính thức/cung cấp và QA để xây Master Unit Registry.
**Dữ liệu synthetic:** Họ tên, mã cá nhân, chức vụ, quan hệ công tác, nhóm đối tượng, lương, phụ
cấp, chế độ, alias, typo/OCR noise và tài liệu mô phỏng.
**Kết quả:** Thông tin đối tượng; đơn vị hiện tại; BCA/BQP/OTHER/UNKNOWN; nhóm đối
tượng; trạng thái lương/chế độ; evidence; confidence; trạng thái xác minh.
**Nguyên tắc:** Không ép hệ thống phải kết luận khi dữ liệu không đủ; dữ liệu/rule synthetic
phải được đánh dấu rõ và có thể thay thế bằng nguồn chính thức mà không
đổi kiến trúc.

<!-- Trang 2/13 -->

## 1. Phân tích nghiệp vụ và phạm vi hoàn chỉnh

### 1.1. Bài toán nghiệp vụ

Hệ thống không chỉ thực hiện một phép phân loại nhãn. Quy trình nghiệp vụ gồm bốn lớp nối tiếp: (1) tiếp
nhận hồ sơ; (2) xác minh đơn vị hiện tại; (3) xác định nhóm đối tượng; (4) đánh giá lương/chế độ an
sinh theo rule. Kết quả cuối cùng phải giải thích được và truy vết lại được nguồn dữ liệu/rule đã sử dụng.

Chốt scope toàn dự án: Input đa định dạng → trích xuất đối tượng + quan hệ công tác hiện tại →
resolve đơn vị → xác định BCA/BQP/OTHER → xác định nhóm đối tượng → Policy/Eligibility Engine → kết
quả + evidence → Human Review khi cần.
### 1.2. Hai kênh đầu vào, một Case chung

```text
                                  NHẬP TRỰC TIẾP                             TẢI TỆP
                            free text / trường thông tin            PDF / DOCX / XLSX / hình ảnh

                               Validate + Text Intake                   Parser / Table Reader / OCR

                                             CASE + NORMALIZED RECORD
                                      subject, current unit, optional business fields
```

*Hình 1: Mọi request, dù nhập tay hay tải file, đều tạo một Case và hội tụ về schema trung gian chung.*

### 1.3. Output nghiệp vụ chuẩn

```text
Trường                        Ý nghĩa
subject                       Họ tên/mã cá nhân/chức vụ và các trường định danh được trích xuất hoặc người
                              dùng nhập.
current_unit                  Đơn vị công tác hiện tại đã resolve về canonical unit.
organization_type             BCA | BQP | OTHER | UNKNOWN.
subject_group                 Nhóm đối tượng phục vụ rule nghiệp vụ; taxonomy được version hóa.
salary_status                 Trạng thái có/không/không đủ dữ liệu để xác định theo rule hiện hành của
                              dataset.
eligibility[]                 Danh sách chế độ/an sinh và kết quả đánh giá tương ứng.
evidence                      Nguồn đơn vị, match method, policy/rule ID, version dữ liệu và dữ kiện đầu vào.
resolution_status             MATCHED | AMBIGUOUS | NOT_FOUND | CONFLICT.
workflow_status               PROCESSING | NEED_REVIEW | COMPLETED | FAILED.
```

### 1.4. Business invariants

1. NOT_FOUND không đồng nghĩa OTHER; có thể registry thiếu dữ liệu.
2. Không suy ra “người thuộc lực lượng” chỉ từ tên đơn vị nếu thiếu dữ kiện nhóm đối tượng; chỉ xác minh
chắc chắn đơn vị quản lý trước.
3. Nếu có nhiều tổ chức trong văn bản, phải xác định CURRENT_WORK_UNIT; không chọn tổ chức xuất hiện
đầu tiên.
4. Policy Engine chỉ kết luận khi đủ trường bắt buộc của rule; thiếu trường phải trả INSUFFICIENT_DATA/NEED_REVIEW.
5. Mỗi kết quả phải tái lập được bằng registry version + taxonomy version + policy version + model version
(nếu model tham gia).
### 1.5. Căn cứ thiết kế module an sinh

Các quy định hiện hành về BHXH bắt buộc đối với quân nhân và Công an nhân dân cho thấy đối tượng áp dụng
và chế độ phụ thuộc vào nhóm đối tượng, không thể suy ra chỉ từ tên Bộ. Vì vậy hệ thống bắt buộc phải có
bước Subject Group Classification và Policy/Eligibility Engine riêng biệt. Ví dụ: Nghị định 157/2025/NĐ-CP;
Thông tư 90/2025/TT-BQP; Thông tư 88/2025/TT-BCA.

<!-- Trang 3/13 -->

## 2. Chiến lược dữ liệu toàn hệ thống

### 2.1. Phân lớp dữ liệu

```text
Nhóm                    Dữ liệu                                  Vai trò
Authoritative/real      Mã đơn vị (nếu có), tên đơn vị,          Xây Master Unit Registry; là nguồn quyết định phạm
                        nguồn tham chiếu                         vi BCA/BQP/OTHER.
Source metadata         URL/tài liệu, thời điểm crawl,           Audit, provenance, rollback và tái lập registry.
                        checksum, version
Human-approved          Viết tắt/tên cũ/tên thường dùng          Phục vụ production resolution.
alias                   đã QA
Synthetic identity      Họ tên, mã cá nhân, năm sinh,            Train/test extraction, subject matching và demo E2E.
                        chức vụ, quan hệ công tác
Synthetic business      Nhóm đối tượng, lương, phụ               Chạy đầy đủ Policy Engine trong phạm vi
                        cấp, chế độ, employment status           project/demo.
Synthetic noise         Typo, không dấu, OCR noise,              Stress test parser/NER/resolution.
                        layout/file variants
```

### 2.2. Master Unit Registry và provenance

Registry là nguồn master quyết định phạm vi quản lý; không để model thay thế authoritative data. Production
nên tách thực thể đơn vị, mã, tên và nguồn để xử lý trường hợp một đơn vị có nhiều mã/tên theo thời gian.

```text
Artifact / bảng             Mục đích
UNITS                       unit_id, canonical identity, organization_type, parent_unit_id, validity, QA status,
                            registry version.
UNIT_CODES                  Nhiều mã cho một đơn vị: code, code_type, namespace, source, validity. Không giả
                            định một unit_code duy nhất.
UNIT_NAMES                  Canonical name, official alias, historical name, approved common name; mọi alias
                            production phải có source/QA.
SOURCES                     URL/tài liệu, checksum, retrieved/effective date, authority, source kind; phục vụ
                            provenance, rollback và reproducibility.
REGISTRY_SNAPSHOTS          Snapshot bất biến đã QA; trạng thái Draft → Validated → Approved → Published →
                            Deprecated.
```

Invariant dữ liệu: crawler không ghi trực tiếp vào registry đang active. Mọi record phải đi qua raw
snapshot → normalize/dedupe → Data QA → approved snapshot → publish. Synthetic typo/OCR noise
chỉ nằm ở offline dataset, không trở thành authoritative alias nếu chưa được con người phê duyệt.
### 2.3. Pipeline xây dữ liệu

```text
                         1. SOURCE            2. CRAWL                 3. CLEAN           4. DATA QA
                      official/provided     raw snapshot           normalize/dedupe      approve/label

                       8. SPLIT + QA        7. ANNOTATE               6. SYNTHETIC       5. REGISTRY
                     golden/hard cases    entity/relation/rule     person/policy/noise    versioned
```

*Hình 2: Dữ liệu đơn vị thật được QA trước; dữ liệu người, lương/chế độ và noise được sinh sau để hoàn thiện pipeline E2E.*

### 2.4. Artifact dữ liệu

master_units.csv; unit_aliases.csv; synthetic_subjects.jsonl; synthetic_employment.jsonl; synthetic_policy_rules.yaml;
synthetic_records.jsonl; extraction_annotations.jsonl; relation_annotations.jsonl; hard_cases.jsonl; dataset_manifest.yaml.
### 2.5. Chống leakage và benchmark đúng nghiệp vụ

Split theo canonical unit và document template, không random alias của cùng đơn vị sang train/test. Tách hai
test suite: Known Registry Test (đơn vị có trong registry nhưng mention/alias mới) và Cold-start Test (đơn
vị mới hoàn toàn, kỳ vọng UNKNOWN/NEED_REVIEW thay vì ép nhãn).

<!-- Trang 4/13 -->

## 3. Kiến trúc End-to-End hoàn chỉnh

### 3.1. Luồng xử lý online - quality-first critical path

```text
    INPUT                   INPUT ROUTER                       PARSER / OCR
   Text / File         structured / unstructured       structured-first + quality gate

                                                                EXTRACTION
                                 NORMALIZE
                                                            Regex + NER + Relation
                               entity + unit text
                                                            CURRENT_WORK_UNIT

                          CANDIDATE GENERATION                           UNIT RESOLUTION                       MASTER UNIT
                       code / exact / alias / fuzzy / ANN           ranking + calibration + margin              REGISTRY

                                                                             Đủ evidence?

                                                               ACCEPT                               ABSTAIN

                                                 SUBJECT GROUP                                          HUMAN REVIEW
                                            rule-first + model fallback                          AMBIGUOUS / CONFLICT / UNKNOWN

                                                                    POLICY / ELIGIBILITY ENGINE
                                                                     deterministic + versioned

                                                                           Đủ required fields?

                                                               Có                                Không

                                      FINAL RESULT                                                  NEED REVIEW
                        evidence + versions + calibrated confidence                              INSUFFICIENT_DATA

                                             PERSIST + AUDIT + EXPORT + FEEDBACK QA
```

*Hình 3: Quality-first critical path: deterministic/registry-first, multi-stage retrieval, calibration và abstention trước khi kết*

luận.
### 3.2. Vai trò AI/ML, rule engine và quality gates

```text
Module                         Chiến lược production quality
Input routing / parser         Content-aware, structured-first. XLS/XLSX dùng schema/header mapping;
                               PDF/DOCX ưu tiên text/layout parser; OCR chỉ là fallback.
OCR                            Có quality estimation sau OCR; confidence thấp/empty layout thì retry
                               preprocessing hoặc review, không âm thầm đẩy text lỗi xuống downstream.
Entity    +     Relation       Regex cho mã/pattern; NER cho PERSON/UNIT/POSITION; relation extraction tách
Extraction                     CURRENT_WORK_UNIT khỏi FORMER_WORK_UNIT.
Unit Resolution                Cascade: trusted code → canonical exact → approved alias →
                               normalized/fuzzy/BM25 → embedding fallback → calibrated ranking.
Subject Group                  Deterministic taxonomy rules trước; classifier/ranker chỉ fallback cho case thiếu
                               cấu trúc hoặc mơ hồ.
Policy Engine                  100% deterministic và versioned; rule có required fields, effective period, source;
                               thiếu field trả INSUFFICIENT_DATA.
Human Review                   First-class workflow cho ambiguity, low margin, conflict, unknown,
                               OCR/extraction uncertainty; feedback phải QA trước khi thành alias/golden case.
```

### 3.3. Decision policy, confidence và abstention

1. Exact trusted code + tên không xung đột là evidence mạnh nhất; không dùng classifier để override authoritative
match.

<!-- Trang 5/13 -->

2. Không có code: canonical/approved alias exact được auto-accept nếu registry record đang active và QA
approved.
3. Fuzzy/semantic chỉ auto-accept khi top-1 score đạt threshold AND top-1–top-2 margin đạt threshold
AND không có conflict AND đủ evidence. Nếu không, ABSTAIN → Human Review.
4. Không dùng một confidence duy nhất. Lưu riêng extraction_confidence, relation_confidence, resolution_score,
candidate_margin, decision_confidence, match_method.
5. Score/model phải calibration trên validation set (ví dụ isotonic/Platt/temperature tùy loại score) để confidence
có ý nghĩa thực tế.
6. Nhiều ORG trong input phải resolve CURRENT_WORK_UNIT; historical unit không được dùng làm current
unit.
7. NOT_FOUND không map sang OTHER; cold-start/unseen phải trả UNKNOWN/NEED_REVIEW nếu thiếu positive
evidence cho OTHER.
8. Policy Engine chỉ chạy rule có hiệu lực và đủ required fields; lưu rule ID + policy version + facts đã dùng
trong evidence.

<!-- Trang 6/13 -->

## 4. Evidence, versioning và reproducibility contract

### 4.1. Evidence là first-class object

Mỗi kết luận phải lưu được chuỗi bằng chứng thay vì chỉ một JSON tùy ý. Evidence tối thiểu gồm: raw/normalized
value, source, match method, candidate score/margin, rule ID, registry/taxonomy/model/policy/threshold version
và actor/reviewer nếu có. UI phải hiển thị được: Kết luận gì? Vì sao? Dựa trên nguồn nào? Rule/version
nào?
### 4.2. Versioning độc lập

Version                      Vai trò
registry_version             Snapshot đơn vị/alias/source đã publish.
taxonomy_version             Taxonomy nhóm đối tượng.
policy_version               Snapshot rule/policy theo hiệu lực.
parser_version               Parser/layout/OCR preprocessing.
model_version                NER/ranker/embedding nếu tham gia.
threshold_version            Threshold, margin và calibration config.

Một release manifest phải tái lập được toàn bộ pipeline từ request đến final result.
### 4.3. Data lineage và feedback loop

Raw source/document được checksum và giữ provenance. Review correction không auto-learn trực tiếp;
feedback đi qua QA rồi mới trở thành approved alias, hard case hoặc training artifact ở release kế tiếp.

<!-- Trang 7/13 -->

## 5. Activity Diagram và Sequence Diagram

### 5.1. Activity Diagram - luồng nghiệp vụ hoàn chỉnh

Nhận yêu cầu tra cứu

Input là file?
```text
                                                           Không                                            Có

                        Validate text/trường nhập                                                                 Parse bảng / PDF / OCR

                                                           Extract subject + CURRENT_WORK_UNIT

                                                              Resolve với Master Unit Registry

                                                                         Unit match đủ tin cậy?

                                                       Có                                                        Không

        Xác định organization + subject group                                                                            Tạo review case

                                                                      Policy/Eligibility Engine

                                                                           Đủ dữ kiện policy?

                                                            Có                                                   Không

                    Tạo kết quả cuối + evidence                                                                   Review thiếu/xung đột dữ liệu

                                                             Persist + audit + hiển thị + export
```

*Hình 4: Activity Diagram: một flow thống nhất từ input đến xác minh đơn vị, nhóm đối tượng và policy.*

### 5.2. Sequence Diagram - request upload file

```text
              User                API                Doc Intel            Resolver               Registry           Policy Engine   Operational DB
                1. submit text/file
                                                                                   2. create Case
                                        3. parse/extract
                                                       4. subject + current unit
                                                                              5. query candidates
                                                                           6. canonical/aliases/source
                                                                                    7. resolved unit + group input
                                                              8. eligibility + policy evidence
                                                                             9. persist result/audit
                   10. response

                                                                   ambiguity/missing data: create review case
```

*Hình 5: Sequence Diagram: Registry chỉ tra cứu master data; Operational DB lưu Case/result/audit; Policy Engine là service*

nghiệp vụ riêng.

<!-- Trang 8/13 -->

## 6. Mô hình dữ liệu production-oriented

### 6.1. ERD lõi - Case, đối tượng và đơn vị

```text
                      CASES                                               SUBJECTS
                      case_id (PK)                                        subject_id (PK)
                      input_type                                          synthetic/real flag
                      workflow_status                                     identity fields
                      created_by/at                                       subject_group

                                         N:1                                                    N:1

                                                                          EMPLOYMENT_RELATIONS
                      DOCUMENTS
                      document_id (PK)                                    employment_id (PK)
                      case_id (FK)                                        subject_id/unit_id
                      file_name/type                                      position/status
                      storage_uri/checksum                                is_current
                                                                          validity

                                         N:1                                                    1:N

                      EXTRACTED_RECORDS                                   UNITS
                      record_id (PK)                 resolve / create-link unit_id (PK)
                      case_id (FK)                                         unit_code
                      document_id (nullable FK)                            canonical_name
                      subject fields                                       organization_type
                      unit_code/name_raw                                   source/version
```

*Hình 6: ERD lõi được tách hai lane: Intake/Case ở trái; Subject-Employment-Unit ở phải. Quan hệ được tạo sau bước resolve.*

### 6.2. Registry schema mở rộng cho nhiều mã/tên

```text
Bảng                          Trường cốt lõi
UNITS                         unit_id, organization_type, parent_unit_id, validity, qa_status, registry_version.
UNIT_CODES                    unit_id, code, code_type, namespace, source_id, valid_from/to.
UNIT_NAMES                    unit_id, name, name_type, source_id, valid_from/to, approved_by.
SOURCES                       source_id, authority, URL/document, checksum, retrieved/effective date.
```

### 6.3. ERD policy, review và audit

VERIFICATION_RESULTS
result_id (PK)
case/subject/unit
organization/group
resolution status
registry/model version

N:1

POLICY_RULES
ELIGIBILITY_ASSESSMENTS
policy_id (PK)
assessment_id (PK)
```text
                                                             N:1         policy_type
                        result_id/policy_id
                                                                         required fields
                        eligible/status
                                                                         rule expression
                        reason/evidence
                                                                         effective/version
                        policy_version
                                                                         source_kind

                        REVIEW_CASES                                     AUDIT_LOGS
                        review_id (PK)                                   audit_id (PK)
                                                            audit
                        case/result ID                                   actor/action
                        reason/status                                    entity type/id
                        reviewed_by                                      timestamp
                        decision_note                                    metadata
```

*Hình 7: Policy Engine lưu assessment theo rule version; review và audit độc lập với registry.*

<!-- Trang 9/13 -->

### 6.4. Trạng thái nên tách riêng

Trục trạng thái        Giá trị điển hình
Organization           BCA / BQP / OTHER / UNKNOWN.
Resolution             MATCHED / AMBIGUOUS / NOT_FOUND / CONFLICT.
Workflow               RECEIVED / PROCESSING / NEED_REVIEW / COMPLETED / FAILED.
Eligibility            ELIGIBLE / NOT_ELIGIBLE / INSUFFICIENT_DATA / NOT_APPLICABLE.
Source kind            OFFICIAL / PROVIDED / SYNTHETIC_DEMO.

<!-- Trang 10/13 -->

## 7. Kiến trúc triển khai production-oriented

### 7.1. Online Serving Plane và Offline Data/ML Plane

```text
                 Client          API Gateway         FastAPI App        Policy Engine          PostgreSQL

                                                                           Worker
                                    Review UI       Queue / Redis                            Object Storage
                                                                          OCR/NLP

                                                                                                     publish

                Crawler           Data QA             Synthetic          Train/Eval           Versioned
                unit data       Registry Build      Person/Policy       NER/Ranking            Artifacts
```

*Hình 8: Online serving và offline data/ML tách biệt; Policy Engine được triển khai ngay trong full scope.*

### 7.2. Kiến trúc vật lý và nguyên tắc triển khai

Logic có thể chia module rõ ràng nhưng không bắt buộc mỗi module thành microservice. Runtime production
tối thiểu có thể gồm: Web/API, Backend modular, Worker cho OCR/batch, PostgreSQL, Redis/queue và Object
Storage. Chỉ tách service khi có bottleneck độc lập, yêu cầu scale/security boundary rõ ràng hoặc lifecycle khác
biệt.
### 7.3. Reliability patterns bắt buộc

- Timeout, retry với exponential backoff và circuit breaker cho dependency ngoài.
- Idempotency key cho create/upload/batch; transaction boundary rõ ràng.
- Dead-letter queue cho job OCR/batch lỗi; checksum để chống xử lý trùng file.
- Outbox pattern nếu phát event async cần bảo đảm DB commit và event publish nhất quán.
- DB migration phải có rollback plan; backup/restore phải được diễn tập, không chỉ cấu hình.
### 7.4. Yêu cầu production tối thiểu

```text
Nhóm                      Yêu cầu
Security                  OIDC/OAuth2, RBAC, TLS, secret manager, WAF/rate limit, magic-byte + MIME
                          validation, size limit, antimalware, encryption at rest, least privilege.
Privacy                   Data minimization, retention/xóa dữ liệu, access log, PII masking trong technical log,
                          tách synthetic/dev/test khỏi dữ liệu thật.
Auditability              Evidence, top-K candidates, score/margin, registry/model/policy/threshold version,
                          reviewer, decision reason và change history.
Reliability               Queue, timeout, retry/backoff, idempotency, circuit breaker, DLQ, checksum,
                          backup/restore drill, migration rollback.
Observability             Technical metrics + business metrics: parse/OCR failure, unresolved/unknown/review
                          rate, false-positive, current-unit conflict, policy insufficient rate, drift.
Quality gates             Unit/integration/contract/E2E; golden suites; calibration test; hard-case regression;
                          policy rule regression 100%; release blocked nếu critical gate fail.
Operations                Dev/test/staging/prod, CI/CD, SBOM/dependency/container scan, artifact
                          signing/versioning, rollout/rollback, runbook registry/policy update.
```

### 7.5. Ranh giới dữ liệu synthetic

Trong phạm vi project, hệ thống thực hiện đầy đủ flow lương/chế độ bằng synthetic person/business/policy
data. Tuy nhiên kết quả phải mang source_kind=SYNTHETIC_DEMO. Khi có dữ liệu/rule chính thức, chỉ thay data
provider và policy snapshot; API, workflow, audit, review và kiến trúc không đổi.

<!-- Trang 11/13 -->

## 8. Quality engineering, Golden Set và Release Gates

### 8.1. Golden regression suites

```text
Suite                       Mục tiêu
GOLDEN-CLEAN                Exact code/name và structured inputs sạch.
GOLDEN-NOISY                Alias, typo, không dấu, format bất thường.
GOLDEN-OCR                  Scan/image, OCR noise và quality-gate behavior.
GOLDEN-CONTEXT              Nhiều ORG, current vs historical unit, relation extraction.
GOLDEN-CONFLICT             code-name conflict, top-1/top-2 gần nhau, ambiguous candidates.
GOLDEN-UNKNOWN              Cold-start/unseen, registry thiếu, yêu cầu abstain đúng.
GOLDEN-POLICY               Rule version/effective date/required fields/INSUFFICIENT_DATA.
GOLDEN-E2E                  Full request → evidence → review/audit/export.
```

### 8.2. Quality targets ban đầu

```text
Metric                                                                                         Quality gate đề
                                                                                                    xuất
Registry label/QA accuracy                                                                          ≥ 99.5%
Exact + approved-alias resolution precision                                                         ≥ 99.5%
Auto-decision precision BCA/BQP/OTHER                                                                ≥ 99%
CURRENT_WORK_UNIT relation F1                                                                        ≥ 95%
Unknown detection recall                                                                             ≥ 95%
Structured file parse success                                                                        ≥ 99%
OCR document parse success                                                                           ≥ 95%
Policy regression tests                                                                              100%
Audit completeness                                                                                   100%
Critical golden regression                                                                           100%
```

### 8.3. Release gate

Không release nếu có critical regression fail, policy tests dưới 100%, audit incomplete, security critical finding,
false-positive vượt ngưỡng, unknown detection giảm mạnh, hoặc migration/rollback chưa được kiểm chứng.
Mục tiêu tối ưu là precision và khả năng abstain đúng, không chạy theo accuracy tổng.

<!-- Trang 12/13 -->

## 9. Thứ tự triển khai toàn dự án và tiêu chí nghiệm thu

### 9.1. Roadmap theo dependency

```text
                               P1                      P2                    P3               P4
                      Business + Contracts       Data + Registry      Case + Resolution   Document AI

                              P8                       P7                     P6               P5
                      Hardening + Deploy         Product + Review       Policy Engine     Subject Group
```

*Hình 9: Triển khai full scope: Policy Engine là một phase bắt buộc, không để sang phiên bản sau.*

### 9.2. Kế hoạch thực hiện và Definition of Done

```text
               P     Hạng mục                    Đầu ra nghiệm thu
               1     Business                +   Chốt use case, schema input/output, taxonomy nhóm đối
                     Contracts                   tượng, status model, evidence contract, rule/review policy.
               2     Data + Registry             Source list/crawler; raw snapshot; Master Unit
                                                 Registry     versioned;    alias    đã    QA;     synthetic
                                                 subject/employment/policy datasets; manifest và quality
                                                 report.
               3     Case + Resolution           Manual      input    tạo   Case;    resolve   unit     bằng
                                                 code/exact/alias/fuzzy;    UNKNOWN/CONFLICT            đúng
                                                 rule; evidence và hard-case test.
               4     Document AI                 PDF/DOCX/XLSX/XLS/image          parse;   OCR      fallback;
                                                 NER/regex; relation extraction CURRENT_WORK_UNIT;
                                                 benchmark extraction.
               5     Subject Group               Xác định/chuẩn hóa nhóm đối tượng; xử lý thiếu/xung đột;
                                                 taxonomy versioned; test theo từng nhóm.
               6     Policy Engine               Salary/eligibility rules versioned; đánh giá đủ/không
                                                 đủ điều kiện; reason/evidence; synthetic demo policy
                                                 snapshot; policy regression tests.
               7     Product + Review            API/UI nhập text/upload/batch; result detail; evidence;
                                                 review queue; correction workflow; export CSV/XLSX;
                                                 feedback có QA.
               8     Hardening               +   RBAC, privacy, audit, reliability patterns, business
                     Deploy                      observability, CI/CD + security scans, backup/restore drill,
                                                 staging/UAT, golden regression, release gates, deploy,
                                                 runbook và rollback.
```

### 9.3. Bộ chỉ số nghiệm thu

```text
Nhóm                            Metric chính
Data                            duplicate/invalid rate, QA accuracy, source coverage, provenance completeness,
                                registry freshness.
Extraction                      precision/recall/F1 PERSON/UNIT/POSITION; CURRENT_WORK_UNIT relation F1;
                                OCR quality/failure; parse success.
Resolution                      candidate recall@K, auto-decision precision, false-positive BCA/BQP/OTHER,
                                unknown recall, top-1/top-2 margin, calibration error.
Subject Group                   rule coverage, macro-F1/accuracy fallback model, insufficient-data accuracy.
Policy                          100% rule regression, eligibility accuracy trên golden scenarios, effective-date
                                correctness, missing-field handling.
E2E                             correctness, abstention/review routing precision, evidence completeness, latency,
                                success rate, audit completeness.
Operations                      availability/SLO, error rate, queue backlog, backup restore success, rollback
                                success, security findings, regression pass rate.
```

### 9.4. Tiêu chí hoàn thành toàn dự án

Dự án hoàn thành khi: (1) text và file đều tạo Case; (2) trích xuất được subject + current unit; (3) resolve
BCA/BQP/OTHER/UNKNOWN có evidence; (4) xác định được nhóm đối tượng; (5) Policy Engine trả salary/eligibility
theo rule versioned; (6) ambiguity/missing data đi Human Review; (7) dữ liệu thật và synthetic được tách
nguồn rõ ràng; (8) mọi kết quả có audit trail; (9) CI/CD, monitoring, backup/rollback và deploy hoạt động; (10)

<!-- Trang 13/13 -->

golden suites được khóa và chạy ở CI; calibration/abstention đạt gate; security/reliability/rollback được kiểm
chứng trước release.

Chốt nghiệp vụ: Full scope được triển khai ngay trong một hệ thống. Phần lương/chế độ không bị loại
khỏi project; nó được xây dưới dạng Policy Engine hoàn chỉnh và chạy bằng synthetic business/policy
data trong giai đoạn đồ án. Khi có nguồn chính thức, thay snapshot dữ liệu/rule mà không thay kiến
trúc.

Chốt kỹ thuật: Đây là một evidence-driven, registry-first, abstention-capable decision support
platform. Chất lượng đến từ authoritative data + multi-stage resolution + calibrated confidence +
deterministic policy + Human Review + golden regression + release gates; không đến từ việc thêm nhiều
model/service.
### 9.5. Tài liệu pháp lý tham chiếu cho thiết kế

Các văn bản dưới đây được dùng để xác nhận rằng logic an sinh phải theo nhóm đối tượng và rule có hiệu lực,
thay vì suy ra trực tiếp từ tên Bộ. Trong đồ án, rule nghiệp vụ được mô phỏng bằng snapshot synthetic nhưng
giữ cùng contract/versioning để có thể thay bằng rule chính thức.

- Nghị định 157/2025/NĐ-CP: BHXH bắt buộc đối với quân nhân, Công an nhân dân, dân quân thường trực
và người làm công tác cơ yếu hưởng lương như quân nhân.
- Thông tư 90/2025/TT-BQP: hướng dẫn BHXH bắt buộc đối với quân nhân và người làm công tác cơ yếu
hưởng lương như quân nhân.
- Thông tư 88/2025/TT-BCA: hướng dẫn BHXH bắt buộc đối với sĩ quan, hạ sĩ quan, chiến sĩ Công an nhân
dân.
