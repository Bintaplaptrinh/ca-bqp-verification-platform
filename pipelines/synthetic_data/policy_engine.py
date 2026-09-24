from __future__ import annotations
from datetime import date


def evaluate(facts: dict, config: dict) -> dict:
    required = ["organization_type","subject_group","employment_status","assessment_date"]
    if any(facts.get(x) in (None,"") for x in required):
        return {
            "policy_id": "SYN-POL-MISSING",
            "salary_status": "INSUFFICIENT_DATA",
            "eligibility_status": "INSUFFICIENT_DATA",
            "policy_reason_code": "MISSING_REQUIRED_FIELDS",
        }

    d = date.fromisoformat(facts["assessment_date"])
    start = date.fromisoformat(config["effective_from"])
    end = date.fromisoformat(config["effective_to"]) if config.get("effective_to") else None

    if d < start or (end and d > end):
        return {
            "policy_id": "SYN-POL-NO-EFFECTIVE-RULE",
            "salary_status": "NOT_APPLICABLE",
            "eligibility_status": "NOT_ELIGIBLE",
            "policy_reason_code": "NO_EFFECTIVE_RULE",
        }

    if facts["subject_group"] == "CONTRACT_WORKER":
        return {
            "policy_id": "SYN-POL-CONTRACT",
            "salary_status": "NOT_APPLICABLE",
            "eligibility_status": "NOT_APPLICABLE",
            "policy_reason_code": "SYNTHETIC_CONTRACT_RULE",
        }

    if facts["organization_type"] in {"BCA","BQP"} and facts["employment_status"] in {"ACTIVE","TEMPORARY"}:
        return {
            "policy_id": "SYN-POL-ACTIVE",
            "salary_status": "APPLICABLE",
            "eligibility_status": "ELIGIBLE",
            "policy_reason_code": "SYNTHETIC_ACTIVE_RULE",
        }

    return {
        "policy_id": "SYN-POL-FALLBACK",
        "salary_status": "NOT_APPLICABLE",
        "eligibility_status": "NOT_ELIGIBLE",
        "policy_reason_code": "NO_SYNTHETIC_RULE_MATCH",
    }
