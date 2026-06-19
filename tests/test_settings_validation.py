import pytest
from pydantic import ValidationError

from backend.api.settings import AppSettings, SettingsUpdate
from backend.config import Settings


def test_settings_rejects_invalid_values():
    with pytest.raises(ValidationError):
        Settings(fuzzy_threshold=101)

    with pytest.raises(ValidationError):
        Settings(tracklists_delay=-0.5)

    with pytest.raises(ValidationError):
        Settings(min_duration_minutes=-1)


def test_settings_normalizes_scan_extensions():
    cfg = Settings(scan_extensions=[" MP3 ", ".FlAc", ""])
    assert cfg.scan_extensions == ["mp3", "flac"]


def test_api_settings_models_validate_ranges():
    with pytest.raises(ValidationError):
        AppSettings(
            music_dir="/tmp",
            music_dirs=["/tmp"],
            scan_extensions=["mp3"],
            fuzzy_threshold=200,
            tracklists_delay=2.0,
            min_duration_minutes=0,
        )

    with pytest.raises(ValidationError):
        SettingsUpdate(tracklists_delay=-1)


def test_api_settings_update_allows_none_and_normalizes_extensions():
    update = SettingsUpdate(scan_extensions=[" OGG ", ".M4A"])
    assert update.scan_extensions == ["ogg", "m4a"]

    empty_update = SettingsUpdate(fuzzy_threshold=None)
    assert empty_update.fuzzy_threshold is None
