import logging
from dataclasses import dataclass
from pathlib import Path

import dacite
import yaml

from .log_helpers import dataclass_format

logger = logging.getLogger()


@dataclass(frozen=True)
class ConnectionConfig:
    notion_api_token: str
    notion_database_id: str
    drive_root_folder_id: str
    drive_settings_file: str
    notion_user_tz: str


@dataclass(frozen=True)
class SessionConfig:
    screenshot_watch_path: str
    screenshot_staging_path: str
    screenshot_interval_sec: int
    minimum_session_gap_min: int
    phash_threshold: int
    # minimum_session_length_min: int


@dataclass(frozen=True)
class NotionProperties:
    name: str
    title: str
    session_id: str
    start: str
    end: str
    drive_link: str


@dataclass(frozen=True)
class MonitorConfig:
    game_process_regex_pattern: list[str]
    input_idle_sec: int
    polling_interval_ms: int


@dataclass(frozen=True)
class Config:
    connection: ConnectionConfig
    session: SessionConfig
    notion_properties: NotionProperties
    monitor: MonitorConfig


def load_config(path: str) -> Config:
    yaml_dict = yaml.safe_load(Path(path).read_text())
    config = dacite.from_dict(Config, yaml_dict, dacite.Config(strict=True))
    logger.info(f"Loaded config from {path!r}")
    logger.debug(f"Parsed config:\n{dataclass_format(config)}")
    return config
