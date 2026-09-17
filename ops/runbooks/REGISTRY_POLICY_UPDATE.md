# Registry / Policy Update Runbook

## Registry

`raw source -> candidate -> normalize/dedupe -> PENDING_QA -> approved master -> DRAFT snapshot -> VALIDATED -> APPROVED -> PUBLISHED`.

Crawler và reviewer feedback không được ghi trực tiếp vào snapshot production. Published snapshot là immutable.

## Policy

- Rule phải có source, effective period, subject groups và version.
- `subject_groups=[]` fail-closed; global rule phải khai báo `['*']` rõ ràng.
- Không tính số tiền nếu rule/case không có đủ biến bắt buộc.
- Thay đổi policy phải tạo version/release mới và chạy GOLDEN-POLICY.
