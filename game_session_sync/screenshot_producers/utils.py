import re
from datetime import datetime


def screenshot_filename(
    title: str, suffix: str, manual: bool = False, timestamp: datetime | None = None
):
    timestamp = timestamp or datetime.now()  # NOTE: local timezone
    timestamp_str = timestamp.strftime("%Y.%m.%d - %H.%M.%S.%f")[
        :-3
    ]  # keep 3 digits = milliseconds
    manual_str = " [Manual]" if manual else ""
    filename = f"{title} {timestamp_str}{manual_str}{suffix}"
    return filename


def parse_screenshot_filename(filename: str) -> tuple[str, datetime, bool]:
    pattern = re.compile(
        r"^(.+?) (\d{4}\.\d{2}\.\d{2} - \d{2}\.\d{2}\.\d{2}\.\d{3})( \[Manual\])?(.+)$"
    )

    matches = pattern.match(filename)
    if not matches:
        raise ValueError(f"Invalid filename format: {filename}")

    title, timestamp_str, manual_flag, suffix = matches.groups()
    timestamp = datetime.strptime(timestamp_str, "%Y.%m.%d - %H.%M.%S.%f")
    manual = bool(manual_flag)

    return title, timestamp, manual


# def session_dirname(title: str, start: datetime, end: datetime | None = None):
#     start_str = start.strftime("%Y.%m.%d - %H.%M.%S")
#     end_str = ""
#     if end is not None:
#         end_str = " - " + end.strftime("%Y.%m.%d - %H.%M.%S")
#     dirname = f"{title} {start_str}{end_str}"
#     return dirname
