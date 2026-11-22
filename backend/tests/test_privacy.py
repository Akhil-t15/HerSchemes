import pytest

from app.privacy import PRIVACY_NOTICE_EN, PRIVACY_NOTICE_TE, contains_sensitive, mask_sensitive


@pytest.mark.parametrize(
    "text, expected_category, leaked",
    [
        ("My Aadhaar is 2345 6789 0123", "aadhaar", "2345 6789 0123"),
        ("aadhaar 2345-6789-0123 ok", "aadhaar", "2345-6789-0123"),
        ("my aadhaar 234567890123", "aadhaar", "234567890123"),
        ("PAN ABCDE1234F", "pan", "ABCDE1234F"),
        ("my pan abcde1234f", "pan", "abcde1234f"),
        ("voter ABC1234567", "voter_id", "ABC1234567"),
        ("account 123456789012", "bank_account", "123456789012"),
        ("ration card 1234567890", "ration_card", "1234567890"),
    ],
)
def test_each_id_type_is_hidden(text, expected_category, leaked):
    masked, categories = mask_sensitive(text)
    assert expected_category in categories
    assert leaked not in masked
    assert contains_sensitive(text) is True


def test_clean_text_is_unchanged():
    text = "I want to start a tailoring shop in Warangal"
    assert mask_sensitive(text) == (text, [])
    assert contains_sensitive(text) is False


def test_empty_input():
    assert mask_sensitive("") == ("", [])
    assert mask_sensitive(None) == ("", [])
    assert contains_sensitive("") is False


def test_telugu_ration_word_masks_number():
    masked, categories = mask_sensitive("రేషన్ 1234567890")
    assert "ration_card" in categories
    assert "1234567890" not in masked


def test_plain_number_without_context_is_not_ration_card():
    # 10 digits with no ration-card word nearby should not be called a ration card.
    _, categories = mask_sensitive("I sold 1234567890 pickles")
    assert "ration_card" not in categories


def test_mask_never_returns_raw_values_in_categories():
    _, categories = mask_sensitive("PAN ABCDE1234F and Aadhaar 2345 6789 0123")
    for c in categories:
        assert "ABCDE1234F" not in c
        assert "2345" not in c


def test_notices_present_in_both_languages():
    assert "Aadhaar" in PRIVACY_NOTICE_EN
    assert PRIVACY_NOTICE_TE.strip()
