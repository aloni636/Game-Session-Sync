import logging
from dataclasses import dataclass
from pathlib import Path

import dacite
import yaml

from .log_helpers import dataclass_format

log = logging.getLogger()


def _resolve_path(
    path: str | Path,
) -> Path:
    """Resolve a path into an absolute Path."""
    return Path(path).expanduser().resolve(strict=True)


@dataclass(frozen=True)
class ConnectionConfig:
    notion_api_token: str
    notion_database_id: str
    drive_root_folder_id: str
    drive_settings_file: Path
    notion_user_tz: str


@dataclass(frozen=True)
class SessionConfig:
    screenshot_watch_path: Path
    screenshot_staging_path: Path
    screenshot_interval_sec: int
    minimum_session_gap_min: int
    minimum_session_length_min: int
    phash_threshold: int
    delete_after_upload: bool


@dataclass(frozen=True)
class NotionProperties:
    name: str
    title: str
    start: str
    end: str
    drive_link: str


@dataclass(frozen=True)
class MonitorConfig:
    game_process_regex_pattern: list[str]
    input_idle_sec: int


@dataclass(frozen=True)
class Config:
    connection: ConnectionConfig
    session: SessionConfig
    notion_properties: NotionProperties
    monitor: MonitorConfig


def load_config(path: Path) -> Config:
    config_path = _resolve_path(path)
    yaml_dict = yaml.safe_load(config_path.read_text())
    config = dacite.from_dict(
        Config,
        yaml_dict,
        dacite.Config(
            strict=True,
            type_hooks={Path: _resolve_path},
        ),
    )

    log.info(f"Loaded config from {str(config_path)!r}")
    log.debug(f"Parsed config:\n{dataclass_format(config)}")
    return config
