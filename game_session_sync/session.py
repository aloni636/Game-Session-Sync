from asyncio import TaskGroup
from zoneinfo import ZoneInfo

from windows_producers import *

from .config import SessionConfig
from .screenshot_producers import *


class Session:
    def __init__(self, title: str, s_config: SessionConfig, tz: ZoneInfo) -> None:
        self.title = title
        self.s_config = s_config
        self.tz = tz
        self.is_active: bool = False

    async def run(self):
        if self.is_active:
            return
        self._screenshot_sampler = PeriodicSampler(
            self.s_config.screenshot_interval_sec,
            self.s_config.screenshot_staging_path,
            self.title,
            self.tz,
        )
        self._screenshot_watcher = ScreenshotWatcher(
            self.s_config.screenshot_watch_path,
            self.s_config.screenshot_staging_path,
            self.title,
            self.tz,
        )
        self.is_active = True
        async with TaskGroup() as tg:
            tg.create_task(self._screenshot_sampler.run())
            tg.create_task(self._screenshot_watcher.run())

    def stop(self):
        self._screenshot_sampler.stop()
        self._screenshot_watcher.stop()
        self.is_active = False
