from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from cabqp.shared.enums import OrganizationType, QAStatus

# A business effective date pins registry and policy resolution. Dates outside a
# plausible administrative range would resolve against a registry state that never
# existed, so they are rejected at the edge rather than silently honoured.
BUSINESS_DATE_MIN = date(1945, 9, 2)
BUSINESS_DATE_FUTURE_DAYS = 366


def _validate_business_date(value: date | None) -> date | None:
    if value is None:
        return None
    if value < BUSINESS_DATE_MIN:
        raise ValueError(f"as_of_date must not be earlier than {BUSINESS_DATE_MIN.isoformat()}")
    latest = date.today() + timedelta(days=BUSINESS_DATE_FUTURE_DAYS)
    if value > latest:
        raise ValueError("as_of_date must not be more than a year in the future")
    return value


class CaseCreate(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    subject_name: str | None = Field(default=None, max_length=300)
    subject_code: str | None = Field(default=None, max_length=160)
    unit_name: str | None = Field(default=None, max_length=500)
    unit_code: str | None = Field(default=None, max_length=160)
    position: str | None = Field(default=None, max_length=300)
    as_of_date: date | None = None
    business_fields: dict = Field(default_factory=dict)

    #: TEXT is the free-text lookup box: anything goes, extraction does the work.
    #: FORM is the structured entry form, where the operator has told us which
    #: field is which — so the fields the rules actually need are required.
    input_mode: Literal["TEXT", "FORM"] = "TEXT"

    #: Set when this Case re-runs an earlier one with operator-corrected fields.
    #: The server reads the original's extraction to record what changed, rather
    #: than trusting the client's account of it.
    corrected_from_case_id: str | None = Field(default=None, max_length=64)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        # min_length counts raw characters, so a whitespace-only body would otherwise
        # create a Case with nothing to extract.
        if not value.strip():
            raise ValueError("text must contain non-whitespace content")
        return value

    @field_validator("subject_name", "subject_code", "unit_name", "unit_code", "position")
    @classmethod
    def blank_optional_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("as_of_date")
    @classmethod
    def as_of_date_must_be_plausible(cls, value: date | None) -> date | None:
        # as_of_date pins registry and policy effective-dating, so an implausible date
        # silently resolves against a registry state that never existed.
        return _validate_business_date(value)

    @model_validator(mode="after")
    def form_mode_requires_identifiers(self):
        """In FORM mode, refuse a submission the rules cannot act on.

        Resolution needs a unit to resolve, and a result needs a subject to
        attach to — with neither a name nor a personnel code there is nobody to
        report on. Enforced here rather than only in the browser so the rule
        holds for any client.
        """
        if self.input_mode != "FORM":
            return self
        if not (self.subject_name or self.subject_code):
            raise ValueError("Phải nhập ít nhất một trong hai: mã số cán bộ hoặc họ và tên")
        if not (self.unit_name or self.unit_code):
            raise ValueError("Đơn vị công tác là bắt buộc")
        return self


class LookupRequest(BaseModel):
    unit_name: str | None = Field(default=None, max_length=500)
    unit_code: str | None = Field(default=None, max_length=160)
    as_of_date: date | None = None

    @field_validator("unit_name", "unit_code")
    @classmethod
    def strip_blank(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("as_of_date")
    @classmethod
    def as_of_date_must_be_plausible(cls, value: date | None) -> date | None:
        return _validate_business_date(value)

    @model_validator(mode="after")
    def one_identifier(self):
        if not self.unit_name and not self.unit_code:
            raise ValueError("unit_name or unit_code is required")
        return self


class ReviewDecision(BaseModel):
    decision: Literal["CONFIRM", "UNKNOWN", "INSUFFICIENT", "DISMISS"]
    unit_id: str | None = None
    corrected_current_unit: str | None = Field(default=None, max_length=500)
    subject_group: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)
    propose_alias: bool = False
    expected_version: int = Field(ge=1)


class ReviewAssign(BaseModel):
    assigned_to: str | None = Field(default=None, max_length=255)
    coverage_group: str | None = Field(default=None, max_length=120)
    expected_version: int = Field(ge=1)


class UnitCreate(BaseModel):
    canonical_name: str = Field(min_length=2, max_length=500)
    organization_type: OrganizationType
    unit_level: str | None = Field(default=None, max_length=80)
    coverage_group: str | None = Field(default=None, max_length=120)
    parent_unit_id: str | None = None
    source_url: str | None = Field(default=None, max_length=4000)
    source_authority: str | None = Field(default=None, max_length=255)
    qa_status: QAStatus = QAStatus.PENDING_QA
    draft_version: str | None = Field(default=None, max_length=100)
    valid_from: date | None = None
    valid_to: date | None = None

    @field_validator("qa_status")
    @classmethod
    def new_unit_starts_pending(cls, value):
        if value != QAStatus.PENDING_QA:
            raise ValueError("New manual units must start as PENDING_QA")
        return value

    @model_validator(mode="after")
    def validity_order(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be <= valid_to")
        return self


class UnitUpdate(BaseModel):
    canonical_name: str | None = Field(default=None, min_length=2, max_length=500)
    organization_type: OrganizationType | None = None
    unit_level: str | None = Field(default=None, max_length=80)
    coverage_group: str | None = Field(default=None, max_length=120)
    parent_unit_id: str | None = None
    active: bool | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def validity_order(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be <= valid_to")
        return self


class UnitQADecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    draft_version: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)


class AliasCreate(BaseModel):
    name: str = Field(min_length=2, max_length=500)
    name_type: Literal["ALIAS", "HISTORICAL", "COMMON"] = "ALIAS"
    source_url: str | None = Field(default=None, max_length=4000)
    valid_from: date | None = None
    valid_to: date | None = None


class AliasQADecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    draft_version: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)


class UnitCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=160)
    code_type: str = Field(default="UNIT_CODE", max_length=80)
    namespace: str = Field(default="DEFAULT", max_length=80)
    source_url: str | None = Field(default=None, max_length=4000)
    valid_from: date | None = None
    valid_to: date | None = None


class UnitCodeQADecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    draft_version: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)


class CandidateDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    canonical_name: str | None = Field(default=None, max_length=500)
    draft_version: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)


class RegistryVersionCreate(BaseModel):
    version: str = Field(min_length=2, max_length=100)
    base_version: str | None = Field(default=None, max_length=100)
    notes: str = Field(default="", max_length=4000)


class RegistryVersionAction(BaseModel):
    notes: str = Field(default="", max_length=4000)


class RegistryPublish(BaseModel):
    version: str = Field(min_length=2, max_length=100)
    notes: str = Field(default="", max_length=4000)


class RegistryRollback(BaseModel):
    target_version: str = Field(min_length=2, max_length=100)
    new_version: str | None = Field(default=None, max_length=100)
    notes: str = Field(default="", max_length=4000)


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


PersonEmploymentStatus = Literal["ACTIVE", "CONTRACT", "TEMPORARY", "INACTIVE", "RETIRED", "UNKNOWN"]
PersonSourceKind = Literal["OFFICIAL", "PROVIDED", "SYNTHETIC_DEMO"]


class PersonCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=500)
    birth_year: int | None = Field(default=None, ge=1900, le=2200)
    canonical_unit_id: str = Field(min_length=1, max_length=64)
    subject_group_hint: str | None = Field(default=None, max_length=100)
    employment_status: PersonEmploymentStatus = "UNKNOWN"
    source_url: str | None = Field(default=None, max_length=4000)
    source_authority: str | None = Field(default=None, max_length=255)
    source_kind: PersonSourceKind = "PROVIDED"
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def validity_order(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be <= valid_to")
        return self


class PersonUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=500)
    birth_year: int | None = Field(default=None, ge=1900, le=2200)
    canonical_unit_id: str | None = Field(default=None, max_length=64)
    subject_group_hint: str | None = Field(default=None, max_length=100)
    employment_status: PersonEmploymentStatus | None = None
    active: bool | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def validity_order(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be <= valid_to")
        return self


class PersonQADecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    draft_version: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)


class PersonAliasCreate(BaseModel):
    name: str = Field(min_length=2, max_length=500)
    name_type: Literal["ALIAS", "HISTORICAL", "COMMON"] = "ALIAS"
    source_url: str | None = Field(default=None, max_length=4000)


class PersonAliasQADecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    draft_version: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)


class PersonCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=160)
    code_type: str = Field(default="PERSON_CODE", max_length=80)
    namespace: str = Field(default="DEFAULT", max_length=80)
    source_url: str | None = Field(default=None, max_length=4000)


class PersonCodeQADecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    draft_version: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)


class PersonCandidateDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    full_name: str | None = Field(default=None, max_length=500)
    canonical_unit_id: str | None = Field(default=None, max_length=64)
    draft_version: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=4000)
