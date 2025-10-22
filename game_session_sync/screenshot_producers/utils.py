import re
from datetime import datetime
from zoneinfo import ZoneInfo


def screenshot_filename(
    title: str, suffix: str, zoneinfo: ZoneInfo | None, manual: bool = False
):
    timestamp = datetime.now(zoneinfo)
    timestamp_str = timestamp.strftime("%Y.%m.%d %H.%M.%S.%f")[
        :-3
    ]  # keep 3 digits = milliseconds
    offset = timestamp.strftime("%z")
    manual_str = "manual" if manual else "auto"
    filename = f"{title} {timestamp_str} {offset} {manual_str}{suffix}"
    return filename


def parse_screenshot_filename(
    filename: str, zoneinfo: ZoneInfo | None
) -> tuple[str, datetime, bool]:
    matches = re.match(
        r"^(.+?) (\d{4}\.\d{2}\.\d{2} \d{2}\.\d{2}\.\d{2}\.\d{3}) ([+-]\d{4}) (manual|auto)(.+)$",
        filename,
    )
    if not matches:
        raise ValueError(f"Invalid filename format: {filename}")

    title, timestamp_str, offset, manual_flag, _ = matches.groups()

    timestamp_str = timestamp_str + "000"
    timestamp = datetime.strptime(
        f"{timestamp_str} {offset}", "%Y.%m.%d %H.%M.%S.%f %z"
    ).astimezone(zoneinfo)
    manual = manual_flag == "manual"
    return title, timestamp, manual


# def session_dirname(title: str, start: datetime, end: datetime | None = None):
#     start_str = start.strftime("%Y.%m.%d - %H.%M.%S")
#     end_str = ""
#     if end is not None:
#         end_str = " - " + end.strftime("%Y.%m.%d - %H.%M.%S")
#     dirname = f"{title} {start_str}{end_str}"
#     return dirname
