import re
from datetime import datetime
from zoneinfo import ZoneInfo


def screenshot_filename(
    title: str,
    suffix: str,
    zoneinfo: ZoneInfo,
    manual: bool = False,
    _timestamp: datetime | None = None,
):
    timestamp = _timestamp or datetime.now(zoneinfo)
    timestamp_str = timestamp.strftime("%Y.%m.%d %H.%M.%S.%f")[
        :-3
    ]  # keep 3 digits = milliseconds
    offset = timestamp.strftime("%z")
    manual_str = "manual" if manual else "auto"
    filename = f"{title} {timestamp_str} {offset} {manual_str}{suffix}"
    return filename


def parse_screenshot_filename(
    filename: str, zoneinfo: ZoneInfo
) -> tuple[str, datetime] | None:
    matches = re.match(
        r"^(.+?) (\d{4}\.\d{2}\.\d{2} \d{2}\.\d{2}\.\d{2}\.\d{3}) ([+-]\d{4}) (manual|auto)(.+)$",
        filename,
    )
    if not matches:
        return None

    title, timestamp_str, offset, manual_flag, suffix = matches.groups()

    timestamp_str = timestamp_str + "000"
    timestamp = datetime.strptime(
        f"{timestamp_str} {offset}", "%Y.%m.%d %H.%M.%S.%f %z"
    ).astimezone(zoneinfo)
    return title, timestamp


def build_session_name(title: str, start: datetime, zoneinfo: ZoneInfo) -> str:
    """
    Produce a canonical session name shared by Notion and Drive.
    Example: "Some Game 2024-03-14 21_45"
    """
    return f"{title} {start.astimezone(zoneinfo).strftime('%Y-%m-%d %H_%M')}"


def parse_session_name(name: str, zoneinfo: ZoneInfo) -> tuple[str, datetime] | None:
    matches = re.match(
        r"^(.+?) (\d{4}-\d{2}-\d{2}) (\d{2})_(\d{2})$",
        name,
    )
    if not matches:
        return None

    title, date_str, hour_str, minute_str = matches.groups()
    parsed = datetime.strptime(
        f"{date_str} {hour_str}:{minute_str}", "%Y-%m-%d %H:%M"
    ).astimezone(zoneinfo)
    return title, parsed
