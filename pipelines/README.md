# CA/BQP Dataset Pipeline — Auto-Crawl + Single Config E2E

## Chạy duy nhất

```bash
pip install -r requirements.txt
python run.py
```

Runtime chỉ đọc:

```text
config.yaml
```

## Nguyên tắc mới

```text
CÀO ĐƯỢC
→ crawler lấy tối đa từ official BCA/BQP public sources

KHÔNG CÀO ỔN ĐỊNH / KHÔNG CÓ FULL NAME ROSTER PUBLIC
→ config trỏ tới curated fallback roster

KHÔNG CÓ EVIDENCE
→ không tự bịa đơn vị
```

Không còn coi:

```text
34 Công an tỉnh + 7 Quân khu + 2 Quân đoàn
```

là full Registry.

File 43 đơn vị được đổi thành:

```text
datasets/curated/master_units_baseline43.csv
```

và chỉ là **fallback baseline**.

---

## End-to-End flow

```text
config.yaml
   ↓
official BCA/BQP seeds
   ↓
robots-aware recursive crawler
   ↓
sitemap + same-site link discovery
   ↓
HTML/PDF raw snapshots + SHA-256
   ↓
candidate extraction
   ↓
source corroboration
   ↓
merge curated fallback
   ↓
strict auto-QA
   ├── APPROVED
   └── PENDING_QA
   ↓
published Master Registry
   ↓
coverage report
   ↓
synthetic generation
   ↓
annotations + hard cases + policy demo
```

## Crawl tối đa nhưng vẫn an toàn

Crawler:

- chỉ đi trong official host suffix đã khai báo;
- tôn trọng `robots.txt`;
- có rate delay;
- có timeout;
- giới hạn depth/page để tránh crawler chạy vô hạn;
- lưu raw HTML/PDF-derived content metadata;
- lưu SHA-256 raw response;
- chỉ follow link cùng official site;
- ưu tiên page có keyword cấu trúc/đơn vị;
- source loại `AUTHORITATIVE_LIST` mạnh hơn article discovery.

`OFFICIAL_DISCOVERY` không tự động APPROVED chỉ vì một bài báo nhắc tên đơn vị.
Nó cần corroboration từ nhiều official URLs.

## Nguồn hiện cấu hình

### BCA

- Cổng Bộ Công an.
- Các trang Cụm thi đua khối đơn vị trực thuộc Bộ.
- Trang tuyển sinh CAND 2026.
- Thông cáo sắp xếp 34 Công an cấp tỉnh / 3.319 Công an cấp xã.
- Link discovery tự đi tiếp trong official `*.bocongan.gov.vn`.

Mục tiêu crawler tìm:

```text
Văn phòng
Cục
Bộ Tư lệnh
Viện / Trung tâm
Học viện / Trường
Bệnh viện
Công an tỉnh/thành
Công an xã/phường/đặc khu
```

### BQP

- Cổng Bộ Quốc phòng.
- Trang cơ cấu QĐND Việt Nam.
- Danh mục học viện/nhà trường.
- Trang tái cơ cấu 2025.
- Link discovery tiếp tục trong `*.mod.gov.vn`.

Mục tiêu crawler tìm:

```text
Bộ Tổng Tham mưu
Tổng cục / Cục
Quân khu
Quân chủng
Binh chủng
Quân đoàn
Bộ Tư lệnh
Bộ CHQS tỉnh/thành
Ban CH BĐBP
Sư đoàn / Lữ đoàn / Trung đoàn / Tiểu đoàn
Học viện / Trường Sĩ quan
Bệnh viện / Viện / Trung tâm
Binh đoàn
```

## Những gì crawler không được phép "đoán"

Ví dụ Bộ Công an công khai rằng có:

```text
3.319 Công an cấp xã
```

nhưng nếu nguồn crawl không đưa ra roster đủ **3.319 tên**, pipeline chỉ được báo:

```text
BCA_COMMUNE_POLICE = INCOMPLETE
```

Không được lấy danh sách xã rồi tự ghép `"Công an " + tên xã` và gọi là ground truth.

Tương tự:

```text
34 đầu mối quân sự cấp tỉnh
30 Ban Chỉ huy BĐBP
```

nếu chưa crawl được full-name roster, config để fallback path ở trạng thái disabled.

Khi có file authoritative:

```yaml
curated_fallbacks:
  - fallback_id: bqp_border_guard_commands
    enabled: true
    path: datasets/curated/bqp_border_guard_commands_current.csv
```

Không phải sửa code.

## Output

```text
artifacts/
└── registry/
    ├── raw/
    ├── candidates/
    └── published/
        ├── master_units_registry.csv
        ├── registry_pending_qa.csv
        └── coverage_report.json

artifacts/
└── synthetic/
    ├── synthetic_records.csv
    ├── synthetic_records.jsonl
    ├── extraction_annotations.jsonl
    ├── relation_annotations.jsonl
    ├── hard_cases.jsonl
    ├── synthetic_policy_rules.yaml
    └── dataset_manifest.json
```

## Coverage semantics

Có 3 loại:

```text
COUNT_PLUS_PUBLIC_EVIDENCE
ROSTER_REQUIRED_FOR_COMPLETE
PUBLIC_SATURATION
```

`PUBLIC_SATURATION` chỉ có nghĩa:

> đã crawl hết nguồn public được cấu hình

không có nghĩa:

> đã biết toàn bộ tổ chức nội bộ BCA/BQP.

## Một config duy nhất

Muốn crawl sâu hơn chỉ sửa:

```yaml
registry:
  crawler:
    max_depth: 5
    max_pages_per_source: 8000
```

Muốn bổ sung một official portal:

```yaml
registry:
  sources:
    - source_id: ...
      organization_type: BCA
      role: OFFICIAL_DISCOVERY
      allowed_host_suffixes:
        - bocongan.gov.vn
      seed_urls:
        - https://...
```

Muốn dùng roster không crawl được thì bật `curated_fallbacks`.

Sau cùng vẫn chỉ:

```bash
python run.py
```
