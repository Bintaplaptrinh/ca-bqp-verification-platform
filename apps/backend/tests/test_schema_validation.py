"""Input-edge regressions for the request schemas.

`as_of_date` pins registry and policy effective-dating, and `text` is the only evidence a
text Case carries. Both were accepted in shapes that produce a Case with nothing to decide
on, so these pin the rejections.
"""
from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from cabqp.shared.schemas import BUSINESS_DATE_MIN, CaseCreate, LookupRequest


@pytest.mark.parametrize("blank", ["   ", "\t", "\n", " \t\n "])
def test_whitespace_only_text_is_rejected(blank):
    """min_length counts raw characters, so a blank body would otherwise be accepted."""
    with pytest.raises(ValidationError) as exc:
        CaseCreate(text=blank)
    assert "non-whitespace" in str(exc.value)


def test_empty_text_is_rejected():
    with pytest.raises(ValidationError):
        CaseCreate(text="")


def test_ordinary_text_is_accepted():
    assert CaseCreate(text="Đồng chí A hiện công tác tại Cục Kỹ thuật.").text


def test_blank_optional_fields_become_none():
    """A blank unit cell must not be treated as a unit named ' '."""
    case = CaseCreate(text="x", unit_name="   ", subject_code=" ", position="\t")
    assert case.unit_name is None
    assert case.subject_code is None
    assert case.position is None


def test_far_future_as_of_date_is_rejected():
    with pytest.raises(ValidationError) as exc:
        CaseCreate(text="x", as_of_date=dt.date(2999, 1, 1))
    assert "future" in str(exc.value)


def test_implausibly_old_as_of_date_is_rejected():
    with pytest.raises(ValidationError) as exc:
        CaseCreate(text="x", as_of_date=dt.date(1900, 1, 1))
    assert "earlier" in str(exc.value)


def test_today_and_near_future_are_accepted():
    """Back-dated and slightly forward-dated assessments are legitimate business cases."""
    assert CaseCreate(text="x", as_of_date=dt.date.today()).as_of_date
    assert CaseCreate(text="x", as_of_date=dt.date.today() + dt.timedelta(days=300)).as_of_date
    assert CaseCreate(text="x", as_of_date=BUSINESS_DATE_MIN).as_of_date == BUSINESS_DATE_MIN


def test_absent_as_of_date_stays_none():
    assert CaseCreate(text="x").as_of_date is None


def test_lookup_rejects_implausible_as_of_date():
    """The same guard has to hold on the lookup path, which resolves against the registry."""
    with pytest.raises(ValidationError):
        LookupRequest(unit_code="C08", as_of_date=dt.date(2999, 1, 1))


def test_lookup_still_requires_an_identifier():
    with pytest.raises(ValidationError):
        LookupRequest()
