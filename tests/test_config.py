from pathlib import Path

import pytest

from ticketbot.config import ConfigError, Settings


def valid_env(reference: Path) -> dict[str, str]:
    return {
        "BOT_TOKEN": "123:test",
        "GEMINI_API_KEY": "gemini-test",
        "ADMIN_IDS": "123, 456,123",
        "REFERENCE_IMAGE_PATH": str(reference),
    }


def test_settings_parse_admins_and_defaults(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"image")

    settings = Settings.from_env(valid_env(reference), project_root=tmp_path)

    assert settings.admin_ids == frozenset({123, 456})
    assert settings.gemini_image_model == "gemini-3-pro-image"
    assert settings.gemini_image_size == "2K"
    assert settings.output_image_width == 705


@pytest.mark.parametrize("admin_ids", ["", "abc", "0", "-5"])
def test_settings_reject_invalid_admin_ids(tmp_path: Path, admin_ids: str) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"image")
    env = valid_env(reference)
    env["ADMIN_IDS"] = admin_ids

    with pytest.raises(ConfigError):
        Settings.from_env(env, project_root=tmp_path)


def test_settings_reject_missing_reference(tmp_path: Path) -> None:
    env = valid_env(tmp_path / "missing.png")

    with pytest.raises(ConfigError, match="REFERENCE_IMAGE_PATH"):
        Settings.from_env(env, project_root=tmp_path)


def test_settings_use_bundled_reference_when_override_is_blank(tmp_path: Path) -> None:
    env = valid_env(tmp_path / "unused.png")
    env["REFERENCE_IMAGE_PATH"] = ""

    settings = Settings.from_env(env, project_root=tmp_path)

    assert settings.reference_image_path.name == "invitation_reference.png"
    assert settings.reference_image_path.is_file()


def test_relative_reference_uses_current_directory_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"image")
    env = valid_env(reference)
    env["REFERENCE_IMAGE_PATH"] = "reference.png"
    monkeypatch.chdir(tmp_path)

    settings = Settings.from_env(env)

    assert settings.reference_image_path == reference.resolve()
