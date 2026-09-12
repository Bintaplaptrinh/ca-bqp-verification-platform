"""Tests for the shared normalization rules.

Vietnamese sample strings are written as escape sequences so that every source
file in this module stays pure ASCII. The plain reading of each constant is
given in the comment above it.
"""

from __future__ import annotations

from pipelines.resolution.text_normalize import (
    fold_ascii,
    is_blank,
    normalize_code,
    normalize_name,
)

# "Su doan 308" with diacritics and the d-stroke letter
SU_DOAN_308 = "S\u01b0 \u0111o\xe0n 308"
# "Cong an Thanh pho Ha Noi" with diacritics
CONG_AN_TP_HA_NOI = "C\xf4ng an Th\xe0nh ph\u1ed1 H\xe0 N\u1ed9i"
# "CATP Ho Chi Minh" with diacritics
CATP_HO_CHI_MINH = "CATP H\u1ed3 Ch\xed Minh"
# "Cong an Ha Noi" with diacritics, mixed case then lower case
CONG_AN_HA_NOI = "C\xf4ng an H\xe0 N\u1ed9i"
CONG_AN_HA_NOI_LOWER = "c\xf4ng an h\xe0 n\u1ed9i"
# the same word in composed and decomposed Unicode form
CONG_AN_COMPOSED = "C\xf4ng an"
CONG_AN_DECOMPOSED = "Co\u0302ng an"


def test_normalize_name_collapses_whitespace_and_case():
    assert normalize_name("  Cong   an\tHa Noi  ") == "cong an ha noi"


def test_normalize_name_keeps_diacritics():
    assert normalize_name(CONG_AN_HA_NOI) == CONG_AN_HA_NOI_LOWER


def test_normalize_name_is_stable_across_unicode_forms():
    assert normalize_name(CONG_AN_COMPOSED) == normalize_name(CONG_AN_DECOMPOSED)


def test_fold_ascii_removes_diacritics_and_d_stroke():
    assert fold_ascii(SU_DOAN_308) == "su doan 308"
    assert fold_ascii(CONG_AN_TP_HA_NOI) == "cong an thanh pho ha noi"


def test_fold_ascii_matches_upper_case_ascii_input():
    assert fold_ascii("CATP HO CHI MINH") == fold_ascii(CATP_HO_CHI_MINH)


def test_fold_ascii_is_idempotent():
    once = fold_ascii(CONG_AN_TP_HA_NOI)
    assert fold_ascii(once) == once


def test_normalize_code_upper_cases_and_trims_punctuation():
    assert normalize_code(" bca_c08. ") == "BCA_C08"
    assert normalize_code("(BQP_F308)") == "BQP_F308"


def test_normalize_code_keeps_internal_separators():
    assert normalize_code("bca_ca_hn") == "BCA_CA_HN"


def test_is_blank():
    assert is_blank(None)
    assert is_blank("   ")
    assert not is_blank("x")
