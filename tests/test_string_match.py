"""Unit tests for the DJ-tuned string matching helpers."""
from backend.services import string_match as sm


def test_original_vs_remix_not_identical():
    """The core fix: an original must not score 100 against a remix."""
    score = sm.title_similarity("Strobe (Original Mix)", "Strobe (Reece Low Remix)")
    assert score < 85, f"expected remix mismatch penalty, got {score}"


def test_same_remix_scores_full():
    assert sm.title_similarity(
        "Strobe (Reece Low Remix)", "Strobe (Reece Low Remix)"
    ) == 100.0


def test_original_variants_treated_equal():
    """'Original Mix' and a bare title should be treated as the same version."""
    assert sm.title_similarity("Strobe (Original Mix)", "Strobe") == 100.0


def test_different_remixes_penalised():
    score = sm.title_similarity(
        "Strobe (Reece Low Remix)", "Strobe (Mha Iri Remix)"
    )
    assert score < 90


def test_accented_artist_normalises():
    assert sm.artist_similarity("Étienne de Crécy", "Etienne de Crecy") == 100.0


def test_split_version_extracts_remix():
    base, version = sm.split_version("Acid Renegade (Mha Iri Remix)")
    assert base == "Acid Renegade"
    assert "Mha Iri Remix" in version


def test_split_version_ignores_non_version_brackets():
    base, version = sm.split_version("Acid Renegade [RP003]")
    assert base == "Acid Renegade"
    assert version == ""


def test_parse_filename_full():
    parsed = sm.parse_filename(
        "Reece Pritchard - Acid Renegade (Mha Iri Remix) [RP003].mp3"
    )
    assert parsed["artist"] == "Reece Pritchard"
    assert parsed["base_title"] == "Acid Renegade"
    assert parsed["version"] == "Mha Iri Remix"
    assert parsed["catalog"] == "RP003"


def test_parse_filename_feat():
    parsed = sm.parse_filename("Daft Punk - One More Time feat Romanthony.flac")
    assert parsed["artist"] == "Daft Punk"
    assert parsed["feat"] == "Romanthony"


def test_parse_filename_no_separator():
    parsed = sm.parse_filename("untitled_white_label.wav")
    assert parsed["artist"] is None
    assert parsed["title"] == "untitled_white_label"


def test_levenshtein_sim_bounds():
    assert sm.levenshtein_sim("abc", "abc") == 1.0
    assert sm.levenshtein_sim("abc", "") == 0.0
