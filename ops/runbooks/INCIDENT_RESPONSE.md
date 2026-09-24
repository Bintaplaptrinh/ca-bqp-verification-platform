# Incident Response Runbook

## Các tín hiệu chính

- `FAILED` case tăng đột biến.
- queue/outbox backlog tăng.
- unknown/review rate tăng bất thường.
- false-positive BCA/BQP/OTHER từ golden/feedback.
- `/health/ready` fail dependency.
- antimalware/rate-limit backend unavailable.

## Xử lý

1. Khoanh release/version liên quan bằng evidence (`registry`, `policy`, `parser`, `model`, `threshold`).
2. Tạm dừng auto-publish Registry và batch ingestion khi nghi dữ liệu lỗi.
3. Nếu resolver regression: tăng abstention/disable semantic auto-accept thay vì ép nhãn.
4. Nếu security incident: rotate Keycloak signing/client credentials và storage secrets; backend JWKS cache có TTL/refresh.
5. Bảo toàn audit log và raw source checksum phục vụ điều tra.
