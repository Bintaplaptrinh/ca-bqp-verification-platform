"""
Config.py — Cấu hình chung toàn project
Vị trí: project root (c:/Crawl_Nang_Cap/Config.py)
Scripts trong pipelines/ import bằng cách thêm project root vào sys.path.

Phạm vi dữ liệu: 2018 – 2026
"""
import os

# ── Seed cố định để tái lập kết quả ─────────────────────────────────────────
SEED             = 42
REGISTRY_VERSION = "v1.0.0" 
SCHEMA_VERSION   = "2026_E2E_Schema"
# ── Phạm vi năm ──────────────────────────────────────────────────────────────
YEAR_START = 2018
YEAR_END   = 2026

# ── Project root (luôn là thư mục chứa file Config.py này) ───────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Thư mục làm việc nội bộ (pipeline working dirs) ─────────────────────────
DIR_RAW       = os.path.join(BASE_DIR, "data_raw")        # raw CSV từng năm
DIR_CLEAN     = os.path.join(BASE_DIR, "data_clean")      # clean_units, qa_approved
DIR_ARTIFACTS = os.path.join(BASE_DIR, "data_artifacts")  # master_units, unit_aliases
DIR_SCHEMA    = os.path.join(DIR_ARTIFACTS, "schema")     # 4 bảng chuẩn hóa 3NF
DIR_LOGS      = os.path.join(BASE_DIR, "logs")

# ── Thư mục output chuẩn (theo quy ước Phát) ─────────────────────────────────
DIR_SAMPLES   = os.path.join(BASE_DIR, "datasets", "samples")    # train/val/test/DataVietNam
DIR_MANIFESTS = os.path.join(BASE_DIR, "datasets", "manifests")  # dataset_manifest.yaml, reports

for _d in [DIR_RAW, DIR_CLEAN, DIR_ARTIFACTS, DIR_SCHEMA, DIR_LOGS, DIR_SAMPLES, DIR_MANIFESTS]:
    os.makedirs(_d, exist_ok=True)

# ── Hằng số định danh và namespace tất định ────────────────────────────────
UUID_NAMESPACE_STR = "vn.gov.registry.unit"
CRAWL_VERSION_STR  = "crawl_2018_2026_v2"
REGISTRY_VERSION   = "v2.5.0"
SCHEMA_VERSION     = "2026_E2E_BiTemporal_3NF_v2"

# ── Tỷ lệ split ──────────────────────────────────────────────────────────────
SPLIT_TRAIN = 0.70
SPLIT_VAL   = 0.15
SPLIT_TEST  = 0.15

# ── Ngưỡng QA ────────────────────────────────────────────────────────────────
MIN_KAPPA          = 0.90
MIN_UNIT_NAME_RATE = 0.85

# ── Số records sinh mỗi đơn vị ───────────────────────────────────────────────
RECORDS_PER_UNIT = 20  # Tăng lên 50-100 cho production

# ── Ưu tiên nhãn khi xung đột org_type ──────────────────────────────────────
ORG_PRIORITY = {"BCA": 2, "BQP": 2, "KHAC": 1, "KHONG_RO": 0} 

if __name__ == "__main__":
    print(f"[Config] Project root    : {BASE_DIR}")
    print(f"[Config] Registry version: {REGISTRY_VERSION}")
    print(f"[Config] Schema version  : {SCHEMA_VERSION}")
    print(f"[Config] Phạm vi năm     : {YEAR_START} – {YEAR_END}")
    print(f"[Config] DIR_SAMPLES     : {DIR_SAMPLES}")
    print(f"[Config] DIR_MANIFESTS   : {DIR_MANIFESTS}")
