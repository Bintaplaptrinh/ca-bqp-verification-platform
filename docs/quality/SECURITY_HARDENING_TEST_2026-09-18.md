# Báo cáo kiểm thử tăng cường bảo mật (POC)

- **Ngày chạy:** 2026-09-18
- **Đối tượng kiểm thử:** phiên bản chạy cục bộ `http://127.0.0.1:8000` (API) và `http://127.0.0.1:3000` (SPA), profile `local`.
- **Phạm vi:** 8 hạng mục chuẩn bị cho POC lần đầu (chống bot/DDoS, chống SQL injection, chống XSS, DTO/Projection, chống clickjacking, chống MIME sniffing, một phiên đăng nhập tại một thời điểm, và tính sẵn sàng đứng sau WAF).
- **Kết quả tổng quát:** **7/8 hạng mục đạt và đã kiểm chứng bằng lưu lượng thật trên localhost.** Hạng mục còn lại (WAF F5) là thiết bị hạ tầng, không thể triển khai từ mã nguồn; ứng dụng đã được xác nhận hoạt động đúng khi đứng sau một WAF/reverse proxy.

> **Lưu ý về công cụ:** Yêu cầu ban đầu đề xuất clone và chạy hai kho công cụ tấn công bên thứ ba từ GitHub (một công cụ DDoS và một bộ brute-force). **Chúng tôi đã không dùng hai kho đó.** Chạy mã tấn công chưa qua kiểm chứng từ kho bất kỳ là rủi ro chuỗi cung ứng cho máy chủ, và không cần thiết: mục tiêu là chứng minh cơ chế phòng thủ (rate limit, chặn brute-force) thực sự kích hoạt. Việc này được thực hiện bằng một script kiểm thử tự viết, minh bạch, chỉ nhắm vào `localhost` của chính hệ thống. Script nằm ở phần Phụ lục để tái lập.

---

## Cấu hình khi kiểm thử

Để cơ chế giới hạn tần suất kích hoạt nhanh, các ngưỡng được hạ thấp tạm thời trong lần chạy này (giá trị mặc định sản xuất cao hơn). File `.env` gốc đã được sao lưu ra `.env.testbak` và **khôi phục nguyên trạng sau khi kiểm thử**.

| Tham số | Giá trị khi test | Mặc định (`.env.example`) |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | `true` |
| `RATE_LIMIT_PER_MINUTE` (mỗi tuyến/IP) | `60` | `120` |
| `RATE_LIMIT_IP_PER_MINUTE` (toàn bộ tuyến/IP) | `100` | `600` |
| `RATE_LIMIT_AUTH_PER_MINUTE` (đăng nhập sai/IP) | `5` | `10` |
| `SECURITY_HEADERS_ENABLED` | `true` | `true` |
| `SINGLE_ACTIVE_SESSION` | `true` | `true` |
| `TRUSTED_PROXY_IPS` | rỗng (kết nối trực tiếp) | rỗng |

Redis không chạy trong lần này, nên bộ giới hạn dùng nhánh dự phòng trong bộ nhớ (`RATE_LIMIT_FAIL_OPEN=true`). Đây cũng chính là đường đi khi Redis sự cố trong sản xuất, nên lần chạy này đồng thời kiểm chứng luôn nhánh dự phòng đó.

---

## Kết quả theo từng hạng mục

### 1. Chống bot / DDoS tầng 7 (giới hạn tần suất) — ĐẠT

Bắn dồn (concurrent) và bắn tuần tự vào một tuyến API thật (`GET /api/v1/cases`). Bộ giới hạn chạy **trước** lớp xác thực, nên request bị chặn ở tầng rate limit chứ không phải tầng auth.

| Phép đo | Kết quả |
|---|---|
| 140 request đồng thời (20 luồng) trong 0,2 giây | **60 × `401`** (lọt, đúng hạn mức tuyến) + **80 × `429`** (bị chặn) |
| Tỷ lệ bị chặn | **57,1%** |
| Bắn tuần tự (cửa sổ mới) | request thứ **61** bắt đầu trả `429` — đúng bằng hạn mức tuyến = 60 |

Ngưỡng IP toàn cục (100 req/phút bất kể tuyến) được kiểm chứng bằng unit test `test_spraying_distinct_routes_hits_the_whole_address_budget` — ngăn kiểu tấn công "rải" nhiều tuyến khác nhau để né hạn mức từng tuyến.

Phản hồi khi bị chặn: HTTP `429` kèm header `Retry-After: 60`, thân JSON `{"error":{"code":"RATE_LIMITED"}}`.

### 2. Chống SQL injection (câu lệnh tham số hoá) — ĐẠT

Gửi 4 payload SQL injection kinh điển vào trường `username`/`password` của `POST /auth/login`:

| Payload | Kết quả |
|---|---|
| `admin' OR '1'='1` | `401` (coi như chuỗi thường, không bypass) |
| `'; DROP TABLE app_users;--` | `401` |
| `admin'--` | `401` |
| `" OR ""="` | `401` |

Sau khi gửi các payload, đăng nhập `admin/admin` vẫn trả `200` → **bảng `app_users` còn nguyên**, không bị chèn/xoá. Toàn bộ truy vấn dùng SQLAlchemy ORM (tham số hoá). Chuỗi SQL thô duy nhất trong mã nguồn là `SELECT 1` (health) và 2 lời gọi advisory-lock, và cả hai đều **bind** khoá thay vì nội suy chuỗi.

### 3. Chống XSS (mã hoá đầu ra) — ĐẠT

Tạo hồ sơ với họ tên chứa `<script>alert(1)</script>`, rồi đọc lại qua `GET /cases/{id}`:

| Phép đo | Kết quả |
|---|---|
| `Content-Type` phản hồi | `application/json` (không phải `text/html`) |
| Được phục vụ dưới dạng HTML? | **Không** |
| Chuỗi payload nằm trong JSON | Có (dưới dạng dữ liệu chuỗi JSON) |

API **không** render HTML ở bất kỳ đâu, nên không tồn tại điểm chèn (sink) để XSS. Payload được trả về nguyên văn **bên trong một chuỗi JSON** — khi SPA hiển thị, React tự escape `<`, `>`, `&`, `"` ở text node. Việc HTML-escape ở tầng lưu trữ/JSON sẽ làm hỏng dữ liệu (một cái tên có dấu nháy sẽ bị lưu và xuất ra thành `&quot;`) mà vẫn không cứu được một sink cố tình bỏ escape. Guard: test tự động chặn mọi `dangerouslySetInnerHTML` / `.innerHTML` / `document.write` / `eval(` trong `apps/web/src`.

### 4. DTO / Projection — ĐẠT

Đăng nhập admin, gọi `GET /auth/me` và `GET /admin/users`, rà tìm rò rỉ bí mật:

| Phép đo | Kết quả |
|---|---|
| Rò rỉ `password_hash` / `pbkdf2_sha256$` / `token_hash` | **Không có** |
| Các trường của `/auth/me` | `coverage_groups, display_name, is_admin, must_change_password, permissions, roles, username` |

Mỗi tuyến trả về một projection dựng tường minh (`admin_users._serialize`), không bao giờ serialize thẳng đối tượng ORM.

### 5. Chống clickjacking (X-Frame-Options / CSP frame-ancestors) — ĐẠT
### 6. Chống MIME sniffing (X-Content-Type-Options: nosniff) — ĐẠT

Header phản hồi của API (kiểm trên cả `200` lẫn `404`):

| Header | Giá trị |
|---|---|
| `Content-Security-Policy` | `default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'` |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), payment=()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cache-Control` | `no-store` |

Header phản hồi của SPA (Vite dev `:3000`, đã kiểm trực tiếp): `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Content-Security-Policy: frame-ancestors 'none'`. Bản production do Nginx phục vụ mang CSP đầy đủ hơn (khai báo trong `apps/web/nginx.conf`, có nới `fonts.googleapis.com`/`fonts.gstatic.com` cho webfont icon). `Settings.production_guards` từ chối khởi động sản xuất nếu tắt header bảo mật.

### 7. Một phiên tại một thời điểm (SSO/thiết bị) — ĐẠT MỘT PHẦN

Đăng nhập tài khoản `user` hai lần liên tiếp:

| Phép đo | Kết quả |
|---|---|
| Token phiên 1 trước khi đăng nhập lần 2 | `200` |
| Token phiên 1 **sau** khi đăng nhập lần 2 | **`401` (đã bị thu hồi)** |
| Token phiên 2 | `200` |

`SINGLE_ACTIVE_SESSION` đảm bảo mỗi tài khoản chỉ có **một phiên sống** tại một thời điểm: đăng nhập mới thu hồi phiên cũ, có hiệu lực ngay ở request kế tiếp của thiết bị cũ (token không mang claim, được đọc lại mỗi request).

**Chưa làm (có chủ đích):** đây **không** phải SSO/OAuth 2.0/OIDC. Bản này cố ý không có nhà cung cấp danh tính ngoài (Keycloak/JWT/JWKS đã bị gỡ). Nếu POC cần SSO thật, đó là quyết định kiến trúc riêng, không nằm trong đợt tăng cường này.

### 8. Chống bot bằng WAF (F5 BIG-IP ASM) — KHÔNG THỰC HIỆN TỪ MÃ NGUỒN

WAF là thiết bị hạ tầng, không cài đặt được từ repo. Điều đã đảm bảo: ứng dụng **chạy đúng khi đứng sau WAF/reverse proxy**. `client_address()` chỉ tin `X-Forwarded-For` khi peer socket nằm trong `TRUSTED_PROXY_IPS` (hỗ trợ IP đơn và dải CIDR); ngoài ra dùng địa chỉ socket thật. Nhờ đó địa chỉ client thật đi qua được lớp WAF/LB để rate limit và audit ghi đúng, đồng thời hạn mức trong ứng dụng vẫn hiệu lực nếu thiết bị bị bỏ qua. **Khuyến nghị triển khai:** khai báo địa chỉ hop (WAF/LB/Nginx) vào `TRUSTED_PROXY_IPS`, nếu không mọi người dùng sẽ dồn chung một "rổ" giới hạn.

### Chống brute-force (chặn thử mật khẩu) — ĐẠT

Gửi liên tiếp các lần đăng nhập sai cho tài khoản `user`:

| Lần | Trạng thái | Mã |
|---|---|---|
| 1–5 | `401` | `Tên đăng nhập hoặc mật khẩu không đúng` |
| 6 | **`429`** | **`TOO_MANY_CREDENTIAL_ATTEMPTS`** |
| 7–9 | `429` | `TOO_MANY_CREDENTIAL_ATTEMPTS` |

- Chặn bắt đầu ngay sau ngưỡng cấu hình (5 lần sai/phút/IP): request thứ **6** bị `429`.
- Trong cửa sổ đang bị chặn, **mật khẩu đúng cũng bị từ chối** (`429`) → kẻ tấn công không thể vừa dò vừa chen một lần đúng.
- Cơ chế này độc lập và bổ sung cho khoá tài khoản sau 8 lần sai ở tầng service (khoá tài khoản chỉ bảo vệ một tài khoản; chặn theo IP xử lý kẻ rải nhiều tên đăng nhập). Lần đăng nhập **thành công không bị tính**, nên người dùng bình thường không bao giờ chạm ngưỡng.

---

## Đối chiếu bộ test tự động

Toàn bộ hành vi trên còn được cố định bằng regression trong `apps/backend`:

- `tests/test_security_hardening.py` — header bảo mật (kể cả trên phản hồi lỗi), chống giả mạo `X-Forwarded-For`, hạn mức toàn IP, chặn brute-force, một phiên/tài khoản, không có sink HTML, API luôn trả JSON.
- `tests/test_local_auth.py::test_account_responses_are_a_projection_not_the_row` — không rò rỉ hash/token.

Kết quả suite backend: **314 passed, 4 skipped** (4 skip là trigger append-only chỉ chạy trên PostgreSQL); ruff sạch; bandit không có phát hiện Medium/High.

---

## Phụ lục A — Kết quả thô (JSON)

```json
{
  "headers": {
    "x_frame_options": "DENY", "x_content_type_options": "nosniff",
    "content_security_policy": "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "referrer_policy": "no-referrer", "cache_control": "no-store",
    "error_status": 404, "error_xfo": "DENY", "error_nosniff": "nosniff", "error_content_type": "application/json"
  },
  "sqli": { "login_outcomes": [401,401,401,401], "table_intact_admin_login": 200 },
  "projection": { "leaked_secrets": [], "me_status": 200, "users_status": 200 },
  "xss": { "detail_content_type": "application/json", "is_json": true, "served_as_html": false },
  "single_session": { "first_token_after_second_login": 401, "second_token": 200, "first_revoked": true },
  "bruteforce": { "first_429_at_attempt": 6, "correct_pw_during_window_code": "TOO_MANY_CREDENTIAL_ATTEMPTS" },
  "flood": { "concurrent_status_counts": {"401": 60, "429": 80}, "blocked_pct": 57.1, "sequential_first_429_at": 61 }
}
```

## Phụ lục B — Cách tái lập

1. Bật rate limit và hạ ngưỡng trong `.env` (sao lưu `.env.testbak` trước).
2. Khởi động lại backend: `conda run -n bqp python ops/local.py stop && conda run -n bqp python ops/local.py start`.
3. Chạy script kiểm thử (chỉ nhắm `127.0.0.1`); script đầy đủ được lưu kèm đợt kiểm thử này (dùng `httpx`, không phụ thuộc công cụ ngoài).
4. Khôi phục `.env` từ `.env.testbak` và khởi động lại backend.

> Script kiểm thử là công cụ nội bộ, chỉ gửi request HTTP thường tới localhost để xác nhận phòng thủ kích hoạt; không phải công cụ tấn công và không nhắm tới bất kỳ hệ thống nào khác.
