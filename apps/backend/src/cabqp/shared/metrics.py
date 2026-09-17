from __future__ import annotations

try:
    from prometheus_client import Counter
except Exception:  # pragma: no cover - optional in constrained dev envs
    Counter = None


class _Noop:
    def labels(self, **kwargs):
        return self

    def inc(self, amount: float = 1.0):
        return None


def _counter(name: str, doc: str, labels: list[str]):
    if Counter is None:
        return _Noop()
    try:
        return Counter(name, doc, labels)
    except ValueError:
        # Safe under test reloads where collectors may already be registered.
        return _Noop()


CASE_TRANSITIONS = _counter(
    "cabqp_case_transitions_total",
    "Case workflow transitions",
    ["status"],
)
RESOLUTION_RESULTS = _counter(
    "cabqp_resolution_results_total",
    "Unit resolution outcomes",
    ["status", "method", "organization_type"],
)
REVIEW_EVENTS = _counter(
    "cabqp_review_events_total",
    "Human review workflow events",
    ["event", "reason"],
)
DOCUMENT_PARSE = _counter(
    "cabqp_document_parse_total",
    "Document parsing/OCR outcomes",
    ["status", "method"],
)
POLICY_ASSESSMENTS = _counter(
    "cabqp_policy_assessments_total",
    "Policy engine assessment outcomes",
    ["status", "policy_type"],
)
OUTBOX_EVENTS = _counter(
    "cabqp_outbox_events_total",
    "Outbox dispatch outcomes",
    ["status", "event_type"],
)

INPUT_ROUTING = _counter(
    "cabqp_input_routing_total",
    "Input routing decisions",
    ["kind", "decision"],
)
OCR_QUALITY = _counter(
    "cabqp_ocr_quality_total",
    "OCR quality gate outcomes",
    ["engine", "gate_result"],
)
BULK_INGEST = _counter(
    "cabqp_bulk_ingest_total",
    "Bulk ingestion row outcomes",
    ["status"],
)
