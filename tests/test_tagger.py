from io import BytesIO

from mutagen.id3 import ID3
from PIL import Image

from backend.services.tagger import AudioTagger


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (12, 12), color=(64, 128, 192))
    buf = BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def test_tag_mp3_writes_expected_frames(tmp_path):
    filepath = tmp_path / "sample.mp3"

    # An ID3-only file is sufficient for mutagen ID3 frame round-trip testing.
    ID3().save(filepath)

    tagger = AudioTagger()
    ok = tagger.tag_mp3(
        str(filepath),
        title="Track Title",
        artist="Artist Name",
        album="Album Name",
        genre="House",
        year="2025",
        cover_data=_jpeg_bytes(),
    )
    assert ok is True

    tags = ID3(filepath)
    assert str(tags.get("TIT2")) == "Track Title"
    assert str(tags.get("TPE1")) == "Artist Name"
    assert str(tags.get("TALB")) == "Album Name"
    assert str(tags.get("TCON")) == "House"
    assert str(tags.get("TDRC")) == "2025"
    assert any(frame.startswith("APIC") for frame in tags.keys())


def test_tag_mp3_empty_string_clears_frame_none_leaves_unchanged(tmp_path):
    filepath = tmp_path / "clear.mp3"
    ID3().save(filepath)

    tagger = AudioTagger()
    tagger.tag_mp3(
        str(filepath),
        title="Track Title",
        artist="Artist Name",
        album="Album Name",
        genre="House",
        year="2025",
    )

    # "" clears the frame; None leaves it untouched.
    ok = tagger.tag_mp3(
        str(filepath),
        title="",
        artist=None,
        album="",
        genre=None,
        year="",
    )
    assert ok is True

    tags = ID3(filepath)
    assert "TIT2" not in tags
    assert "TALB" not in tags
    assert "TDRC" not in tags
    assert str(tags.get("TPE1")) == "Artist Name"
    assert str(tags.get("TCON")) == "House"


def test_get_current_tags_handles_non_audio_mp3_gracefully(tmp_path):
    filepath = tmp_path / "cover.mp3"
    ID3().save(filepath)

    tagger = AudioTagger()
    tagger.tag_mp3(str(filepath), title="Tagged", cover_data=_jpeg_bytes())

    current = tagger.get_current_tags(str(filepath))
    assert isinstance(current, dict)
    assert current["has_cover"] is False
    assert current["title"] is None
