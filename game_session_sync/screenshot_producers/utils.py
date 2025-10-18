from datetime import datetime


def screenshot_filename(
    title: str, suffix: str, manual: bool = False, timestamp: datetime | None = None
):
    timestamp = timestamp or datetime.now()  # NOTE: local timezone
    timestamp_str = timestamp.strftime("%Y.%m.%d - %H.%M.%S.%f")[
        :-3
    ]  # keep 3 digits = milliseconds
    manual_str = " [Manual] " if manual else ""
    filename = f"{title} {timestamp_str}{manual_str}{suffix}"
    return filename
