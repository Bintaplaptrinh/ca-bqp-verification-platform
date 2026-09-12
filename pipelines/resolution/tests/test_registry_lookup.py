"""Tests for the CSV backed registry lookup against the published artifacts."""

from __future__ import annotations

from datetime import date

MANIFEST_REGISTRY_CHECKSUM = "751ebf50385c4f04b9c743be813a037fd49889ecc8905968b7843be761f7a13d"
MANIFEST_UNIT_COUNT = 1633
MANIFEST_ALIAS_COUNT = 10124


def test_snapshot_matches_published_manifest(dataset_lookup):
    report = dataset_lookup.integrity_report()
    assert report.unit_count == MANIFEST_UNIT_COUNT
    assert report.registry_version == "v2.0.0"
    assert report.content_checksum_sha256 == MANIFEST_REGISTRY_CHECKSUM
    assert report.alias_count == MANIFEST_ALIAS_COUNT + report.delta_alias_count


def test_unapproved_aliases_are_excluded_from_the_default_index(dataset_lookup):
    report = dataset_lookup.integrity_report()
    assert report.approved_alias_count < report.alias_count


def test_find_by_code_returns_single_active_unit(dataset_lookup):
    candidates = dataset_lookup.find_by_code("BCA_C08", date(2026, 1, 1))
    assert len(candidates) == 1
    assert candidates[0].unit.unit_id == 6
    assert candidates[0].unit.organization_type == "BCA"
    assert candidates[0].is_valid_at


def test_find_by_code_is_case_and_punctuation_insensitive(dataset_lookup):
    assert dataset_lookup.find_by_code(" bca_c08. ", date(2026, 1, 1))


def test_repeated_code_is_separated_by_validity_window(dataset_lookup):
    """BQP_F308 belongs to Quan doan 1 until 2023 and to Quan doan 12 from 2024."""
    in_2020 = [c for c in dataset_lookup.find_by_code("BQP_F308", date(2020, 6, 1)) if c.is_valid_at]
    in_2026 = [c for c in dataset_lookup.find_by_code("BQP_F308", date(2026, 6, 1)) if c.is_valid_at]
    assert len(in_2020) == 1
    assert len(in_2026) == 1
    assert in_2020[0].unit.unit_id == 764
    assert in_2026[0].unit.unit_id == 1631
    assert in_2020[0].unit.valid_to == date(2023, 12, 31)
    assert in_2026[0].unit.valid_from == date(2024, 1, 1)


def test_find_by_name_uses_strict_index_first(dataset_lookup):
    """This alias is stored without diacritics, so it matches at the strict level."""
    candidates = dataset_lookup.find_by_name("Cong an Ha Noi", date(2026, 1, 1))
    assert candidates
    assert all(str(c.normalization_level) == "STRICT" for c in candidates)
    assert {c.unit.unit_code for c in candidates} == {"BCA_CA_HN"}


def test_find_by_name_falls_back_to_ascii_folded_index(dataset_lookup):
    """No registry row spells this alias without diacritics, so folding is required."""
    candidates = dataset_lookup.find_by_name("Benh vien 108", date(2026, 1, 1))
    assert candidates
    assert all(str(c.normalization_level) == "ASCII_FOLDED" for c in candidates)
    assert {c.unit.unit_code for c in candidates} == {"BQP_BV108"}


def test_find_by_name_returns_expired_candidates_with_a_flag(dataset_lookup):
    candidates = dataset_lookup.find_by_code("BQP_QD1", date(2026, 1, 1))
    assert candidates
    assert all(not c.is_valid_at for c in candidates)
    assert all(str(c.validity_note) == "OUT_OF_WINDOW" for c in candidates)


def test_approved_alias_delta_file_is_loaded(dataset_lookup):
    candidates = dataset_lookup.find_by_name("CA HN", date(2026, 1, 1))
    assert len(candidates) == 1
    assert candidates[0].unit.unit_code == "BCA_CA_HN"


def test_known_registry_defect_is_reported(dataset_lookup):
    """The Ha Tay units carry valid_to earlier than valid_from."""
    report = dataset_lookup.integrity_report()
    assert "BCA_CA_HTAY" in report.inverted_validity_windows
    assert len(report.inverted_validity_windows) == 38


def test_no_code_is_duplicated_inside_one_validity_window(dataset_lookup):
    report = dataset_lookup.integrity_report()
    assert report.duplicate_codes_same_window == []
