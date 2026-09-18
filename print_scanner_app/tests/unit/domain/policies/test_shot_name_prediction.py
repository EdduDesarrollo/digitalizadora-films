"""Tests de predicción de nombres CR3."""

from print_scanner_app.domain.policies.shot_name_prediction import (
    DEFAULT_FIRST_CR3_NAME,
    cr3_sequence_number,
    initial_predicted_cr3_name,
    max_cr3_name,
    predict_next_cr3_name,
)


def test_predict_next_cr3_name_basic():
    assert predict_next_cr3_name("_MG_0180.CR3") == "_MG_0181.CR3"
    assert predict_next_cr3_name("_MG_0009.cr3") == "_MG_0010.CR3"


def test_predict_next_cr3_name_invalid():
    assert predict_next_cr3_name(None) is None
    assert predict_next_cr3_name("") is None
    assert predict_next_cr3_name("nofile.CR3") is None


def test_cr3_sequence_and_max():
    assert cr3_sequence_number("_MG_0160.CR3") == 160
    assert max_cr3_name("_MG_0010.CR3", "_MG_0009.CR3", None) == "_MG_0010.CR3"
    assert max_cr3_name(None, "") is None


def test_initial_predicted_empty_card_starts_at_0001():
    assert initial_predicted_cr3_name(None, None) == DEFAULT_FIRST_CR3_NAME
    assert initial_predicted_cr3_name(None, "") == "_MG_0001.CR3"


def test_initial_predicted_from_latest():
    assert initial_predicted_cr3_name("_MG_0001.CR3") == "_MG_0002.CR3"
    assert initial_predicted_cr3_name(None, "_MG_0042.CR3") == "_MG_0043.CR3"
