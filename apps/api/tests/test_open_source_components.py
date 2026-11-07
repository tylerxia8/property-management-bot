from io import BytesIO

import pytest
from PIL import Image
from pillow_heif import from_pillow

from grok_bot.domain.listing_match import MAX_CANDIDATES, resolve_hint
from grok_bot.domain.media_scan import scan_stored_file, sha256_file


def row(label, identifier="listing"):
    return {"id": identifier, "display_label": label}


def test_typo_suggests_listing_without_creating_an_automatic_match():
    result = resolve_hint("10 Elmm Street", [row("10 Elm Street")])
    assert result["match"] is None and result["ambiguous"]
    assert "10 Elm Street" in result["clarification"]
    assert "please confirm" in result["clarification"]


def test_house_number_mismatch_does_not_auto_match_or_suggest():
    result = resolve_hint("10 Elm Street", [row("110 Elm Street")])
    assert result["match"] is None
    assert "110 Elm Street" not in result["clarification"]


@pytest.mark.parametrize("hint", ["%", "_", "", "x" * 513])
def test_wildcards_empty_and_oversized_hints_never_select_a_listing(hint):
    assert resolve_hint(hint, [row("10 Elm Street")])["match"] is None


def test_normalized_literal_match_and_ambiguity_are_preserved():
    first = row("10 Elm Street", "a")
    assert resolve_hint("１０ ELM STREET", [first])["match"] == first
    result = resolve_hint("Elm", [first, row("20 Elm Street", "b")])
    assert result["ambiguous"] and result["match"] is None
    assert resolve_hint("Elm", [first] * (MAX_CANDIDATES + 1))["match"] is None


def scan(path, *, allowed=True):
    return scan_stored_file(path=path, declared_content_type="image/heic",
                            expected_sha256=sha256_file(path), fixture_allowed=allowed)


def test_real_heic_becomes_metadata_free_jpeg_and_thumbnail(tmp_path):
    image = Image.new("RGB", (64, 32), "red")
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"
    image.info["exif"] = exif.tobytes()
    path = tmp_path / "original"
    from_pillow(image).save(path, quality=90)
    assert b"SecretCamera" in path.read_bytes()
    assert scan(path).ready
    for name in ["derivative.jpg", "thumbnail.jpg"]:
        data = (tmp_path / name).read_bytes()
        assert b"SecretCamera" not in data
        with Image.open(BytesIO(data)) as output:
            assert output.format == "JPEG"
            assert output.size == (64, 32)
            assert not output.getexif()


def test_heic_remains_disabled_without_scanner_configuration(tmp_path):
    path = tmp_path / "original"
    from_pillow(Image.new("RGB", (16, 16))).save(path)
    assert scan(path, allowed=False).code == "SCANNER_NOT_CONFIGURED"
    assert not (tmp_path / "derivative.jpg").exists()


def test_corrupt_heic_is_rejected(tmp_path):
    path = tmp_path / "original"
    path.write_bytes(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32)
    result = scan(path)
    assert not result.ready and result.code == "IMAGE_DECODE_FAILED"


def test_image_pixel_limit_prevents_derivative_creation(tmp_path, monkeypatch):
    from grok_bot.domain import media_scan
    path = tmp_path / "original"
    from_pillow(Image.new("RGB", (16, 16))).save(path)
    monkeypatch.setattr(media_scan, "MAX_IMAGE_PIXELS", 100)
    assert not scan(path).ready
    assert not (tmp_path / "derivative.jpg").exists()


def test_jpeg_orientation_is_applied_before_metadata_is_removed(tmp_path):
    image = Image.new("RGB", (64, 32), "red")
    exif = Image.Exif()
    exif[0x0112] = 6
    path = tmp_path / "original"
    image.save(path, format="JPEG", exif=exif)
    result = scan_stored_file(path=path, declared_content_type="image/jpeg",
                              expected_sha256=sha256_file(path), fixture_allowed=True)
    assert result.ready
    with Image.open(tmp_path / "derivative.jpg") as output:
        assert output.size == (32, 64)
        assert not output.getexif()
