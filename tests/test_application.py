import asyncio
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from game_session_sync.config import load_config
from game_session_sync.log_helpers import setup_logging
from game_session_sync.naming_utils import build_screenshot_filename, parse_session_name
from game_session_sync.uploader import Uploader, _SessionInfo


class EnhancedUploader(Uploader):
    async def drop_all_sessions(self) -> None:
        sessions = await self._query_sessions()
        if sessions:
            await asyncio.gather(*(self._drop_session(s) for s in sessions))

    async def list_all_sessions(self) -> list[tuple[str, datetime, datetime]]:
        sessions = await self._query_sessions()
        if sessions:
            session_rows: list[tuple[str, datetime, datetime]] = []
            for session in sessions:
                parsed = parse_session_name(session.page_name, self.user_tz)
                title = parsed[0] if parsed else session.page_name
                session_rows.append((title, session.start, session.end))
            return session_rows
        else:
            raise RuntimeError(
                "Testing environment assumes there are sessions in staging notion."
            )


# --- integration testing ---
class TestApplication:
    @pytest.mark.asyncio
    async def test_uploader(self, tmp_path: Path):
        setup_logging("./app_test_uploader.log")
        config = load_config(Path("config.staging.yaml"))
        uploader = EnhancedUploader(
            config.connection,
            config.notion_properties,
            tmp_path,
            minimum_session_gap_min=5,
            minimum_session_length_min=5,
            delete_after_upload=False,
        )
        tz = ZoneInfo(config.connection.notion_user_tz)

        screenshot_timestamps_1: list[tuple[str, datetime]] = [
            # should be merged into one, and not be deleted at 2nd pass
            ("Integration Test Beta", datetime(2024, 7, 2, 20, 5, tzinfo=tz)),
            ("Integration Test Beta", datetime(2024, 7, 2, 20, 6, tzinfo=tz)),
            ("Integration Test Beta", datetime(2024, 7, 2, 20, 9, tzinfo=tz)),
            ("Integration Test Beta", datetime(2024, 7, 2, 20, 12, tzinfo=tz)),
            # should be merged into one, and be deleted at 2nd pass
            ("Integration Test Alpha", datetime(2024, 7, 1, 19, 0, tzinfo=tz)),
            ("Integration Test Alpha", datetime(2024, 7, 1, 19, 1, tzinfo=tz)),
            ("Integration Test Alpha", datetime(2024, 7, 1, 19, 3, tzinfo=tz)),
        ]
        expected_sessions_1: list[tuple[str, datetime, datetime]] = [
            (
                "Integration Test Beta",
                datetime(2024, 7, 2, 20, 5, tzinfo=tz),
                datetime(2024, 7, 2, 20, 12, tzinfo=tz),
            ),
            (
                "Integration Test Alpha",
                datetime(2024, 7, 1, 19, 0, tzinfo=tz),
                datetime(2024, 7, 1, 19, 3, tzinfo=tz),
            ),
        ]

        screenshot_timestamps_2: list[tuple[str, datetime]] = [
            # should be merged into one, and not delete last 'Integration Test Beta'
            ("Integration Test Beta", datetime(2024, 7, 3, 1, 5, tzinfo=tz)),
            ("Integration Test Beta", datetime(2024, 7, 3, 1, 6, tzinfo=tz)),
            ("Integration Test Beta", datetime(2024, 7, 3, 1, 8, tzinfo=tz)),
            ("Integration Test Beta", datetime(2024, 7, 3, 1, 9, tzinfo=tz)),
            ("Integration Test Beta", datetime(2024, 7, 3, 1, 12, tzinfo=tz)),
            # should be merged into one, and delete last 'Integration Test Alpha'
            ("Integration Test Alpha", datetime(2024, 7, 3, 0, 0, tzinfo=tz)),
            ("Integration Test Alpha", datetime(2024, 7, 3, 0, 2, tzinfo=tz)),
            ("Integration Test Alpha", datetime(2024, 7, 3, 0, 4, tzinfo=tz)),
            ("Integration Test Alpha", datetime(2024, 7, 3, 0, 8, tzinfo=tz)),
            ("Integration Test Alpha", datetime(2024, 7, 3, 0, 12, tzinfo=tz)),
        ]
        expected_sessions_2: list[tuple[str, datetime, datetime]] = [
            (
                "Integration Test Beta",
                datetime(2024, 7, 2, 20, 5, tzinfo=tz),
                datetime(2024, 7, 2, 20, 12, tzinfo=tz),
            ),
            (
                "Integration Test Beta",
                datetime(2024, 7, 3, 20, 5, tzinfo=tz),
                datetime(2024, 7, 3, 20, 12, tzinfo=tz),
            ),
            (
                "Integration Test Alpha",
                datetime(2024, 7, 3, 0, 0, tzinfo=tz),
                datetime(2024, 7, 3, 0, 12, tzinfo=tz),
            ),
        ]

        for title, timestamp in screenshot_timestamps_1:
            screenshot_file = tmp_path / build_screenshot_filename(
                title, ".txt", uploader.user_tz, timestamp=timestamp
            )
            screenshot_file.touch()

        await uploader.drop_all_sessions()

        await uploader.upload()
        sessions_1 = await uploader.list_all_sessions()
        assert sorted(sessions_1) == sorted(expected_sessions_1)

        for title, timestamp in screenshot_timestamps_2:
            screenshot_file = tmp_path / build_screenshot_filename(
                title, ".txt", uploader.user_tz, timestamp=timestamp
            )
            screenshot_file.touch()

        await uploader.upload()
        sessions_2 = await uploader.list_all_sessions()
        assert sorted(sessions_2) == sorted(expected_sessions_2)
