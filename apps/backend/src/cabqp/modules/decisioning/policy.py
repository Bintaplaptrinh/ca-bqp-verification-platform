from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cabqp.shared.metrics import POLICY_ASSESSMENTS
from cabqp.shared.models import EligibilityAssessment, PolicyRule


class PolicyEngine:
    def __init__(self, db: Session):
        self.db = db

    def evaluate(
        self,
        *,
        result_id: str,
        subject_group: str | None,
        facts: dict,
        as_of: date | None = None,
        replace_existing: bool = True,
    ):
        as_of = as_of or date.today()
        outputs = []
        if replace_existing:
            self.db.execute(delete(EligibilityAssessment).where(EligibilityAssessment.result_id == result_id))

        rules = list(self.db.scalars(select(PolicyRule).where(PolicyRule.active.is_(True))))
        for rule in rules:
            if rule.effective_from and as_of < rule.effective_from:
                continue
            if rule.effective_to and as_of > rule.effective_to:
                continue

            if not rule.subject_groups:
                # Fail closed. A rule with an empty subject scope is a configuration error,
                # not a global wildcard. Global rules must explicitly use ["*"].
                status = "NOT_APPLICABLE"
                reason = "Rule không khai báo subject_groups; hệ thống không tự mở rộng phạm vi áp dụng."
            elif subject_group is None:
                status = "INSUFFICIENT_DATA"
                reason = "Thiếu subject_group; không được suy ra chỉ từ tên đơn vị."
            elif "*" not in rule.subject_groups and subject_group not in rule.subject_groups:
                status = "NOT_APPLICABLE"
                reason = f"Nhóm {subject_group} không thuộc phạm vi rule."
            else:
                missing = [x for x in rule.required_fields if facts.get(x) in (None, "")]
                if missing:
                    status = "INSUFFICIENT_DATA"
                    reason = f"Thiếu trường bắt buộc: {', '.join(missing)}"
                else:
                    # The seeded official rules model legal scope/applicability only.
                    # No salary amount is invented here.
                    status = "ELIGIBLE"
                    reason = "Đủ dữ kiện để xác định thuộc phạm vi áp dụng của rule đã version hóa."

            a = EligibilityAssessment(
                result_id=result_id,
                policy_id=rule.id,
                status=status,
                reason=reason,
                evidence={
                    "facts_used": {k: facts.get(k) for k in rule.required_fields},
                    "source_ref": rule.source_ref,
                    "as_of_date": str(as_of),
                    "scope_only": bool((rule.rule_expression or {}).get("scope_only")),
                },
                policy_version=rule.policy_version,
                source_kind=rule.source_kind,
            )
            self.db.add(a)
            POLICY_ASSESSMENTS.labels(status=status, policy_type=rule.policy_type).inc()
            outputs.append(a)
        return outputs
