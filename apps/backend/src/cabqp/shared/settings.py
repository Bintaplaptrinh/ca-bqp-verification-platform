import logging
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CA/BQP Verification Platform"
    app_env: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://cabqp:change_me@localhost:5432/cabqp"
    redis_url: str = "redis://localhost:6379/0"

    # Deployment profile. "local" runs the whole platform in one process against
    # PostgreSQL alone: object storage becomes a directory, the Celery queue
    # becomes an in-process outbox dispatcher, and rate limiting uses its own
    # in-memory window instead of Redis. "docker" keeps MinIO/Redis/Celery.
    runtime_profile: str = "local"
    storage_backend: str = "auto"  # auto | filesystem | minio
    queue_backend: str = "auto"  # auto | inline | celery
    storage_root: str = ".local/documents"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "cabqp"
    minio_secret_key: str = "change_me_minio"
    minio_bucket: str = "cabqp-documents"
    minio_secure: bool = False
    external_retry_attempts: int = 3
    external_retry_base_seconds: float = 0.15
    circuit_breaker_failures: int = 5
    circuit_breaker_recovery_seconds: int = 30

    # Accounts and sessions are this platform's own; there is no external
    # identity provider to configure. AUTH_DISABLED is development-only and
    # production_guards() below refuses to start with it on.
    auth_disabled: bool = False
    session_hours: int = 12

    # Outgoing mail. An issued password is delivered by email, so this is a
    # dependency of account creation, not a nicety. The only transport is Gmail
    # SMTP authenticated with a Google app password; the self-hosted SMTP host
    # settings and the offline .eml file writer were removed, so a deployment
    # cannot point issued passwords at an unauthenticated relay or leave them in
    # a local directory. The host/port are not configurable on purpose.
    gmail_user: str | None = None
    gmail_app_password: str | None = None
    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 587
    smtp_timeout_seconds: float = 15.0
    # Gmail rewrites a From it does not own, so only the display name in front
    # of GMAIL_USER is configurable.
    mail_from_name: str = "Hệ thống tra cứu CA/BQP"

    # One-time sign-in codes, mailed to the account's own address. Every knob
    # here is a spam control, so the defaults are the conservative end:
    #   ttl / length / attempts  — how much a single challenge is worth to guess
    #   cooldown + per-hour caps — how much mail one account or one address can
    #                              cause, which is the abuse this endpoint
    #                              invites (the attacker's target is someone
    #                              else's inbox, not our session table).
    # The feature turns itself off when mail is not configured; there is no
    # profile in which a code can be issued without being sent somewhere.
    otp_login_enabled: bool = True
    otp_ttl_seconds: int = 60
    otp_code_length: int = 6
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_max_per_account_per_hour: int = 5
    otp_max_per_ip_per_hour: int = 20
    otp_retention_hours: int = 24

    resolver_fuzzy_threshold: float = 91.0
    resolver_margin_threshold: float = 6.0
    resolver_candidate_limit: int = 10
    resolver_calibrated_accept_threshold: float = 0.90
    resolver_semantic_threshold: float = 0.82
    resolver_semantic_margin_threshold: float = 0.08
    resolver_allow_semantic_autoaccept: bool = False
    resolver_cache_ttl_seconds: int = 60
    resolver_calibration_path: str = "artifacts/resolver_calibration.json"
    resolver_require_calibration_for_fuzzy_autoaccept: bool = True
    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_enabled: bool = True
    embedding_local_files_only: bool = True

    parser_version: str = "parser-2026.09-production.3"
    model_version: str = "hybrid-rule-ner-2026.09-production.1"
    threshold_version: str = "threshold-calibrated-2026.09-v2"
    taxonomy_version: str = "taxonomy-2026.09"

    max_upload_mb: int = 25
    ocr_min_confidence: float = 0.70
    document_parse_min_confidence: float = 0.60
    extraction_min_confidence: float = 0.75
    document_failed_gate_confidence_cap: float = 0.50

    # Configurable resource guards for document processing. These are safety limits,
    # not business rules; deployments can tune them from environment variables.
    document_max_pdf_pages: int = 200
    document_max_ocr_pages: int = 20
    document_max_image_pixels: int = 40_000_000
    document_max_raster_pixels: int = 200_000_000
    document_max_tables: int = 200
    document_max_worksheets: int = 50
    document_max_spreadsheet_rows: int = 100_000
    document_soft_timeout_seconds: int = 240

    # Document intelligence / OCR. Thresholds are configuration, never literals in gate code.
    ocr_detector: str = "easyocr"
    ocr_recognizer: str = "easyocr"
    ocr_fallback_detector: str = "paddle"
    ocr_fallback_recognizer: str = "paddle"
    ocr_fallback_enabled: bool = True
    easyocr_decoder: str = "greedy"
    easyocr_contrast_threshold: float = 0.10
    easyocr_adjust_contrast: float = 0.50
    easyocr_text_threshold: float = 0.70
    easyocr_low_text: float = 0.40
    easyocr_link_threshold: float = 0.40
    easyocr_canvas_size: int = 2560
    easyocr_magnification: float = 1.0
    easyocr_result_confidence_min: float = 0.15
    tesseract_page_segmentation_mode: int = 6
    quality_conf_p10_min: float = 0.70
    quality_conf_min: float = 0.30
    quality_low_conf_line: float = 0.70
    quality_low_conf_ratio_max: float = 0.20
    quality_charset_violation_max: float = 0.02
    quality_min_alpha_chars: int = 200
    quality_min_tokens: int = 30
    quality_min_alpha_token_ratio: float = 0.60
    quality_diacritic_ratio_min: float = 0.08
    quality_dictionary_gate_enabled: bool = False
    quality_dict_hit_min: float = 0.35
    quality_ioc_min_chars: int = 100
    quality_ioc_min: float = 1.10
    quality_entropy_min: float = 3.50
    quality_image_blur_variance_min: float = 50.0
    quality_image_contrast_std_min: float = 12.0
    # How many people one import may create Cases for. This is a workload cap,
    # not a parser guard: `document_max_spreadsheet_rows` already stops a file
    # large enough to exhaust memory, while this bounds what a single operator
    # request queues onto the worker and what the result screen has to show.
    bulk_max_rows: int = 50
    bulk_auto_map_threshold: float = 0.90
    bulk_ocr_table_confidence_min: float = 0.80
    bulk_header_alias_min: float = 0.75
    bulk_record_name_value_min: float = 0.60
    bulk_table_label_antisignal_max: float = 0.25
    header_alias_path: str = "config/header_aliases.yaml"
    quality_config_path: str = "config/document_quality.yaml"
    scan_table_detection_enabled: bool = True
    cors_origins: str = "http://localhost:3000"
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120
    rate_limit_fail_open: bool = True
    # A single client gets its own budget per route shape (above) *and* one across
    # every route (below). Without the second one, a flood just sprays requests
    # over many paths and stays under the per-route limit on each of them.
    rate_limit_ip_per_minute: int = 600
    # Credential endpoints are far cheaper to abuse than they are to use: a person
    # signs in once, a password sprayer signs in continuously.
    rate_limit_auth_per_minute: int = 10
    # X-Forwarded-For is client-supplied unless a proxy we control wrote it. Only
    # peers listed here may set the address the limiter and audit log record;
    # anyone else is rate-limited by the socket address they actually connect from.
    trusted_proxy_ips: str = ""

    # Response hardening. Frame embedding is refused outright: nothing in this
    # platform is meant to be rendered inside another site's page.
    security_headers_enabled: bool = True
    frame_ancestors: str = "'none'"
    hsts_max_age_seconds: int = 31536000

    # One live session per account. A second sign-in ends the first, so an account
    # cannot be shared across devices or left signed in on a machine walked away from.
    single_active_session: bool = True

    clamav_host: str = "localhost"
    clamav_port: int = 3310
    antimalware_enabled: bool = True
    antimalware_required: bool = False
    antimalware_timeout_seconds: float = 8.0

    metrics_enabled: bool = True

    seed_allow_production: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env.casefold() in {"prod", "production"}

    @property
    def is_local_profile(self) -> bool:
        return self.runtime_profile.casefold() == "local"

    @property
    def effective_storage_backend(self) -> str:
        if self.storage_backend != "auto":
            return self.storage_backend
        return "filesystem" if self.is_local_profile else "minio"

    @property
    def effective_queue_backend(self) -> str:
        if self.queue_backend != "auto":
            return self.queue_backend
        return "inline" if self.is_local_profile else "celery"

    @property
    def mail_configured(self) -> bool:
        """Both halves of the Gmail app-password credential are present."""
        return bool((self.gmail_user or "").strip() and (self.gmail_app_password or "").strip())

    @property
    def otp_login_available(self) -> bool:
        """OTP sign-in is offered only when a code can actually be delivered."""
        return bool(self.otp_login_enabled and self.mail_configured)

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_root)
        return path if path.is_absolute() else Path.cwd() / path

    @property
    def calibration_file(self) -> Path:
        path = Path(self.resolver_calibration_path)
        if path.is_absolute():
            return path
        # In containers /app is the backend root; from source checkouts this resolves via cwd.
        return Path.cwd() / path

    @model_validator(mode="after")
    def production_guards(self):
        if self.is_production:
            if self.auth_disabled:
                raise ValueError("AUTH_DISABLED must never be enabled in production")
            unsafe = {"change_me", "change_me_minio", "admin"}
            if any(x in self.database_url for x in unsafe) or self.minio_secret_key in unsafe:
                raise ValueError("Refusing to start production with default/known credentials")
            if not self.antimalware_enabled or not self.antimalware_required:
                raise ValueError("Production requires antimalware scanning in fail-closed mode")
            if not self.rate_limit_enabled:
                raise ValueError("Production requires API rate limiting")
            if not self.security_headers_enabled:
                raise ValueError("Production requires the security response headers")
            if not self.mail_configured:
                raise ValueError(
                    "Production requires GMAIL_USER and GMAIL_APP_PASSWORD: issued passwords "
                    "are delivered by email and there is no other transport"
                )
        if self.otp_login_enabled:
            if not 20 <= self.otp_ttl_seconds <= 900:
                raise ValueError("OTP_TTL_SECONDS must be between 20 and 900")
            if not 6 <= self.otp_code_length <= 10:
                raise ValueError("OTP_CODE_LENGTH must be between 6 and 10")
            if not 1 <= self.otp_max_attempts <= 10:
                raise ValueError("OTP_MAX_ATTEMPTS must be between 1 and 10")
            # A cooldown shorter than the code's own lifetime would let one
            # caller queue a new message for every second the last one is valid.
            if self.otp_resend_cooldown_seconds < self.otp_ttl_seconds:
                raise ValueError("OTP_RESEND_COOLDOWN_SECONDS must be at least OTP_TTL_SECONDS")
            if self.otp_max_per_account_per_hour < 1 or self.otp_max_per_ip_per_hour < 1:
                raise ValueError("OTP per-hour caps must be at least 1")
        if self.runtime_profile.casefold() not in {"local", "docker"}:
            raise ValueError("RUNTIME_PROFILE must be 'local' or 'docker'")
        if self.storage_backend not in {"auto", "filesystem", "minio"}:
            raise ValueError("STORAGE_BACKEND must be 'auto', 'filesystem' or 'minio'")
        if self.queue_backend not in {"auto", "inline", "celery"}:
            raise ValueError("QUEUE_BACKEND must be 'auto', 'inline' or 'celery'")
        if self.max_upload_mb <= 0:
            raise ValueError("MAX_UPLOAD_MB must be positive")
        if not 0.0 <= self.ocr_min_confidence <= 1.0:
            raise ValueError("OCR_MIN_CONFIDENCE must be between 0 and 1")
        if not 0.0 <= self.document_parse_min_confidence <= 1.0:
            raise ValueError("DOCUMENT_PARSE_MIN_CONFIDENCE must be between 0 and 1")
        if not 0.0 <= self.extraction_min_confidence <= 1.0:
            raise ValueError("EXTRACTION_MIN_CONFIDENCE must be between 0 and 1")
        if not 0.0 <= self.document_failed_gate_confidence_cap <= 1.0:
            raise ValueError("DOCUMENT_FAILED_GATE_CONFIDENCE_CAP must be between 0 and 1")
        positive_limits = {
            "DOCUMENT_MAX_PDF_PAGES": self.document_max_pdf_pages,
            "DOCUMENT_MAX_OCR_PAGES": self.document_max_ocr_pages,
            "DOCUMENT_MAX_IMAGE_PIXELS": self.document_max_image_pixels,
            "DOCUMENT_MAX_RASTER_PIXELS": self.document_max_raster_pixels,
            "DOCUMENT_MAX_TABLES": self.document_max_tables,
            "DOCUMENT_MAX_WORKSHEETS": self.document_max_worksheets,
            "DOCUMENT_MAX_SPREADSHEET_ROWS": self.document_max_spreadsheet_rows,
            "BULK_MAX_ROWS": self.bulk_max_rows,
            "DOCUMENT_SOFT_TIMEOUT_SECONDS": self.document_soft_timeout_seconds,
        }
        for name, value in positive_limits.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if not 0.0 <= self.bulk_ocr_table_confidence_min <= 1.0:
            raise ValueError("BULK_OCR_TABLE_CONFIDENCE_MIN must be between 0 and 1")
        for name, value in {
            "BULK_HEADER_ALIAS_MIN": self.bulk_header_alias_min,
            "BULK_RECORD_NAME_VALUE_MIN": self.bulk_record_name_value_min,
            "BULK_TABLE_LABEL_ANTISIGNAL_MAX": self.bulk_table_label_antisignal_max,
        }.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.rate_limit_per_minute <= 0:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be positive")
        if self.rate_limit_ip_per_minute <= 0:
            raise ValueError("RATE_LIMIT_IP_PER_MINUTE must be positive")
        if self.rate_limit_auth_per_minute <= 0:
            raise ValueError("RATE_LIMIT_AUTH_PER_MINUTE must be positive")
        return self

    @property
    def trusted_proxies(self) -> tuple[IPv4Network | IPv6Network, ...]:
        """Proxy addresses allowed to name the client, as networks.

        A bare address is accepted and read as a single-host network, so
        "10.0.0.7" and "172.16.0.0/12" are both valid entries. A container
        network assigns the reverse proxy its address dynamically, which is why
        a range has to be expressible at all: pinning one address would leave
        every request looking like it came from an untrusted peer after a
        restart, collapsing every user into one rate-limit bucket.
        """
        networks: list[IPv4Network | IPv6Network] = []
        for raw in self.trusted_proxy_ips.split(","):
            entry = raw.strip()
            if not entry:
                continue
            try:
                networks.append(ip_network(entry, strict=False))
            except ValueError:
                # A malformed entry must not silently widen trust, and must not
                # take the process down either; it is dropped and reported.
                logging.getLogger(__name__).warning(
                    "invalid_trusted_proxy_entry", extra={"event": {"entry": entry}}
                )
        return tuple(networks)


@lru_cache
def get_settings() -> Settings:
    return Settings()
