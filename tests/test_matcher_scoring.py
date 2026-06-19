"""Tests for TrackMatcher scoring: version-awareness and AcoustID weighting.

These exercise the pure scoring logic (no network/DB) via a lightweight stand-in
for the Track ORM object.
"""
from types import SimpleNamespace

from backend.services.matcher import TrackMatcher


def make_track(title=None, artist=None, filename="track.mp3", filepath=None):
    return SimpleNamespace(
        title=title, artist=artist, filename=filename, filepath=filepath
    )


def test_remix_scores_below_original_match():
    """A remix candidate should score lower than the true original candidate."""
    m = TrackMatcher()
    track = make_track(title="Strobe (Original Mix)", artist="deadmau5")

    original = {"title": "Strobe (Original Mix)", "artist": "deadmau5"}
    remix = {"title": "Strobe (Reece Low Remix)", "artist": "deadmau5"}

    assert m._score_candidate(track, original) > m._score_candidate(track, remix)


def test_acoustid_identity_boosts_agreeing_candidate():
    """A candidate matching the fingerprint identity should beat one that doesn't."""
    m = TrackMatcher()
    track = make_track(title="Unknown", artist=None, filename="white_label.mp3")

    identity = {"title": "Acid Renegade", "artist": "Reece Pritchard", "score": 0.95}

    agreeing = {"title": "Acid Renegade", "artist": "Reece Pritchard"}
    wrong = {"title": "Some Other Track", "artist": "Different Artist"}

    score_agree = m._score_candidate(track, agreeing, acoustid_identity=identity)
    score_wrong = m._score_candidate(track, wrong, acoustid_identity=identity)

    assert score_agree > score_wrong
    assert score_agree >= 85  # confident fingerprint agreement is auto-acceptable


def test_score_zero_when_no_signals():
    m = TrackMatcher()
    track = make_track(title="", artist="", filename="")
    assert m._score_candidate(track, {"title": "", "artist": ""}) == 0.0


def test_gap_aware_threshold_present():
    assert TrackMatcher().auto_accept_gap > 0
