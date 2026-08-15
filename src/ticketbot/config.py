"""Environment-backed application configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def _positive_int(
    values: Mapping[str, str], name: str, default: int, *, maximum: int | None = None
) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < 1 or (maximum is not None and value > maximum):
        suffix = f" and at most {maximum}" if maximum is not None else ""
        raise ConfigError(f"{name} must be positive{suffix}")
    return value


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            user_id = int(candidate)
        except ValueError as exc:
            raise ConfigError("ADMIN_IDS must contain comma-separated integers") from exc
        if user_id <= 0:
            raise ConfigError("ADMIN_IDS values must be positive")
        ids.add(user_id)
    if not ids:
        raise ConfigError("ADMIN_IDS must contain at least one Telegram user ID")
    return frozenset(ids)


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime settings."""

    bot_token: str
    gemini_api_key: str
    admin_ids: frozenset[int]
    reference_image_path: Path
    gemini_image_model: str = "gemini-3-pro-image"
    gemini_image_size: str = "2K"
    gemini_image_aspect_ratio: str = "9:16"
    output_image_width: int = 705
    output_image_height: int = 1280
    generation_timeout_seconds: int = 240
    generation_max_attempts: int = 2
    max_concurrent_generations: int = 2
    log_level: str = "INFO"

    @classmethod
    def from_env(
        cls,
        values: Mapping[str, str] | None = None,
        *,
        project_root: Path | None = None,
    ) -> Settings:
        """Load and validate settings from a mapping or from ``.env``/OS variables."""

        if project_root is None:
            current_root = Path.cwd().resolve()
            source_env = PROJECT_ROOT / ".env"
            use_source_env = (
                values is None
                and not (current_root / ".env").is_file()
                and source_env.is_file()
            )
            project_root = PROJECT_ROOT if use_source_env else current_root
        if values is None:
            load_dotenv(project_root / ".env", override=False)
            values = os.environ

        reference_value = values.get("REFERENCE_IMAGE_PATH", "").strip()
        if reference_value:
            reference_path = Path(reference_value)
            if not reference_path.is_absolute():
                reference_path = project_root / reference_path
        else:
            reference_path = PACKAGE_ROOT / "assets" / "invitation_reference.png"
        reference_path = reference_path.resolve()

        image_size = values.get("GEMINI_IMAGE_SIZE", "2K").strip().upper()
        if image_size not in {"1K", "2K", "4K"}:
            raise ConfigError("GEMINI_IMAGE_SIZE must be one of: 1K, 2K, 4K")

        aspect_ratio = values.get("GEMINI_IMAGE_ASPECT_RATIO", "9:16").strip()
        supported_ratios = {
            "1:1",
            "2:3",
            "3:2",
            "3:4",
            "4:3",
            "4:5",
            "5:4",
            "9:16",
            "16:9",
            "21:9",
        }
        if aspect_ratio not in supported_ratios:
            raise ConfigError("GEMINI_IMAGE_ASPECT_RATIO is not supported")

        log_level = values.get("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ConfigError("LOG_LEVEL is invalid")

        settings = cls(
            bot_token=_required(values, "BOT_TOKEN"),
            gemini_api_key=_required(values, "GEMINI_API_KEY"),
            admin_ids=_parse_admin_ids(_required(values, "ADMIN_IDS")),
            reference_image_path=reference_path,
            gemini_image_model=values.get(
                "GEMINI_IMAGE_MODEL", "gemini-3-pro-image"
            ).strip()
            or "gemini-3-pro-image",
            gemini_image_size=image_size,
            gemini_image_aspect_ratio=aspect_ratio,
            output_image_width=_positive_int(values, "OUTPUT_IMAGE_WIDTH", 705, maximum=4096),
            output_image_height=_positive_int(
                values, "OUTPUT_IMAGE_HEIGHT", 1280, maximum=4096
            ),
            generation_timeout_seconds=_positive_int(
                values, "GENERATION_TIMEOUT_SECONDS", 240, maximum=900
            ),
            generation_max_attempts=_positive_int(
                values, "GENERATION_MAX_ATTEMPTS", 2, maximum=5
            ),
            max_concurrent_generations=_positive_int(
                values, "MAX_CONCURRENT_GENERATIONS", 2, maximum=10
            ),
            log_level=log_level,
        )

        if not settings.reference_image_path.is_file():
            raise ConfigError(
                f"REFERENCE_IMAGE_PATH does not exist: {settings.reference_image_path}"
            )
        return settings
