from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "datasets" / "samples"
BASE = "http://127.0.0.1:8000/api/v1"
POLL_SECONDS = 300


def detail_text(response: requests.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return response.text[:500]


def poll_case(case_id: str) -> dict:
    deadline = time.time() + POLL_SECONDS
    last: dict = {}
    while time.time() < deadline:
        response = requests.get(f"{BASE}/cases/{case_id}", timeout=15)
        response.raise_for_status()
        last = response.json()
        status = last.get("case", {}).get("workflow_status") or last.get("workflow_status")
        if last.get("extracted") or last.get("result") or status == "FAILED":
            return last
        time.sleep(1)
    return last


def poll_bulk(job_id: str) -> dict:
    deadline = time.time() + POLL_SECONDS
    last: dict = {}
    while time.time() < deadline:
        response = requests.get(f"{BASE}/bulk/{job_id}", timeout=15)
        response.raise_for_status()
        last = response.json()
        if last.get("job", {}).get("status") in {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"}:
            return last
        time.sleep(1)
    return last


def summarize_case(name: str, case_id: str, detail: dict) -> dict:
    case = detail.get("case") or {}
    extracted = detail.get("extracted") or {}
    result = detail.get("result") or {}
    evidence = detail.get("evidence") or result.get("evidence") or {}
    subject = detail.get("subject") or {}
    extracted_name = subject.get("name") or extracted.get("subject_name")
    extracted_code = subject.get("code") or extracted.get("subject_code")
    extracted_unit = detail.get("current_unit") or extracted.get("current_unit_raw")
    missing = []
    if not extracted_name:
        missing.append("subject_name")
    if not (extracted_code or extracted_unit):
        missing.append("subject_code_or_unit")
    workflow = case.get("workflow_status") or detail.get("workflow_status")
    return {
        "file": name,
        "route": "case",
        "http": 202,
        "case_id": case_id,
        "workflow": workflow,
        "parse_method": evidence.get("parse_method"),
        "name": extracted_name,
        "code": extracted_code,
        "position": subject.get("position") or extracted.get("position"),
        "unit": extracted_unit,
        "resolution": detail.get("resolution_status") or result.get("resolution_status"),
        "organization": detail.get("organization_type") or result.get("organization_type"),
        "quality_gate": (evidence.get("parse_quality") or {}).get("gate_result"),
        "split_blocks": (evidence.get("split_source") or {}).get("block_count"),
        "missing_entities": missing,
        "ok": workflow != "FAILED" and not missing,
    }


def submit_text(path: Path) -> dict:
    response = requests.post(
        f"{BASE}/cases/text",
        json={"text": path.read_text(encoding="utf-8")},
        headers={"Idempotency-Key": f"samples-{uuid.uuid4()}"},
        timeout=60,
    )
    if not response.ok:
        return {"file": path.name, "route": "text", "http": response.status_code, "error": detail_text(response), "ok": False}
    payload = response.json()
    case_ids=payload.get("case_ids") or [payload["case_id"]]
    details=[poll_case(case_id) for case_id in case_ids]
    row = summarize_case(path.name, payload["case_id"], details[0])
    row["route"] = "text"
    row["http"] = response.status_code
    row["subject_count"] = payload.get("subject_count",len(case_ids))
    row["subjects"] = [
        {
            "case_id":case_id,
            "name":((detail.get("subject") or {}).get("name") or (detail.get("extracted") or {}).get("subject_name")),
            "code":((detail.get("subject") or {}).get("code") or (detail.get("extracted") or {}).get("subject_code")),
        }
        for case_id,detail in zip(case_ids,details)
    ]
    if path.name == "10_text_multi_subject.txt":
        row["ok"] = row["subject_count"] == 2 and all(item["name"] and item["code"] for item in row["subjects"])
    return row


def submit_bulk(path: Path) -> dict:
    with path.open("rb") as handle:
        response = requests.post(f"{BASE}/bulk", files={"file": (path.name, handle)}, timeout=180)
    if not response.ok:
        return {"file": path.name, "route": "bulk", "http": response.status_code, "error": detail_text(response), "ok": False}
    payload = response.json()
    job_id = payload["job_id"]
    mapping = payload.get("mapping") or {}
    confirm = requests.post(f"{BASE}/bulk/{job_id}/confirm", json={"mapping": mapping}, timeout=180)
    if not confirm.ok:
        return {"file": path.name, "route": "bulk", "http": confirm.status_code, "job_id": job_id, "error": detail_text(confirm), "ok": False}
    detail = poll_bulk(job_id)
    job = detail.get("job") or {}
    total = job.get("total_rows")
    succeeded = job.get("succeeded")
    failed = job.get("failed")
    skipped = job.get("skipped")
    balanced = isinstance(total, int) and total > 0 and total == sum(x or 0 for x in (succeeded, failed, skipped))
    return {
        "file": path.name,
        "route": "bulk",
        "http": response.status_code,
        "job_id": job_id,
        "duplicate_file": bool(payload.get("duplicate_file")),
        "status": job.get("status") or confirm.json().get("status"),
        "rows": job.get("total_rows"),
        "processed": job.get("processed"),
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "validation": job.get("validation") or payload.get("validation"),
        "row_errors": detail.get("errors") or [],
        "balanced_rows": balanced,
        "ok": (job.get("status") or confirm.json().get("status")) in {"COMPLETED", "COMPLETED_WITH_ERRORS"} and balanced and (succeeded or 0) > 0,
    }


def submit_file(path: Path) -> dict:
    with path.open("rb") as handle:
        response = requests.post(
            f"{BASE}/cases/file",
            files={"file": (path.name, handle)},
            headers={"Idempotency-Key": f"samples-{uuid.uuid4()}"},
            timeout=180,
        )
    if response.status_code == 422 and "TABULAR_LIST" in json.dumps(detail_text(response)):
        return submit_bulk(path)
    if not response.ok:
        return {"file": path.name, "route": "case", "http": response.status_code, "error": detail_text(response), "ok": False}
    payload = response.json()
    detail = poll_case(payload["case_id"])
    row = summarize_case(path.name, payload["case_id"], detail)
    row["http"] = response.status_code
    return row


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rows: list[dict] = []
    for path in sorted(p for p in SAMPLES.iterdir() if p.is_file() and p.name != "README_TEST_INPUTS.md"):
        try:
            row = submit_text(path) if path.suffix.lower() == ".txt" else submit_file(path)
        except Exception as exc:  # keep running so one bad sample does not hide the rest
            row = {"file": path.name, "route": "unknown", "error": f"{type(exc).__name__}: {exc}", "ok": False}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    summary = {"total": len(rows), "passed": sum(bool(row.get("ok")) for row in rows), "failed": sum(not row.get("ok") for row in rows)}
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
