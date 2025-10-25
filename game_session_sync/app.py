import asyncio
import logging
from asyncio import Event
from zoneinfo import ZoneInfo

from .config import Config
from .screenshot_producers import *
from .session import Session
from .uploader import Uploader
from .windows_producers import *


class GameSessionSync:
    def __init__(self, config: Config) -> None:
        self.queue: EventBus = EventBus()
        self.window_watcher = WindowEventWatcher(
            self.queue, config.monitor.game_process_regex_pattern
        )
        self.input_idle_watcher = InputIdleWatcher(
            self.queue,
            config.monitor.input_idle_sec,
        )

        self.s_config = config.session
        self.uploader = Uploader(
            config.connection,
            config.notion_properties,
            self.s_config.screenshot_staging_path,
            config.session.minimum_session_gap_min,
            config.session.minimum_session_length_min,
            config.session.delete_after_upload,
        )
        self.tz = ZoneInfo(config.connection.notion_user_tz)

        self.active_session: Session | None = None
        self._last_session_stop_event: BaseInputEvent | BaseWindowEvent | None = None
        self._stop_event = Event()
        self.log = logging.getLogger(self.__class__.__name__)

    async def _start_session(self, title: str):
        await self.uploader.stop()

        if self.active_session is None:
            self.active_session = Session(title, self.s_config, self.tz)

        same_title = self.active_session.title == title
        active = self.active_session.is_active

        if same_title and active:
            return
        if not same_title and active:
            self.log.warning(
                "Starting a new session while existing one hasn't been paused"
            )
            self.active_session.stop()
            active = False
        if not same_title and not active:
            self.active_session = Session(title, self.s_config, self.tz)
        await self.active_session.run()

    async def _resume_session(self):
        if self.active_session is not None:
            await self.active_session.run()

    def _pause_session(self, event: BaseInputEvent | BaseWindowEvent):
        if self.active_session is not None:
            self.active_session.stop()
            self._last_session_stop_event = event

    def _cleanup_session(self):
        if self.active_session is not None:
            self.active_session.stop()

    async def _stop_session(self, event: BaseInputEvent | BaseWindowEvent):
        self._pause_session(event)
        await self.uploader.upload()

    async def _run(self):
        # Task groups propagate errors instead of being isolated in Task objects
        # when creating them with asyncio.create_task
        async with asyncio.TaskGroup() as tg:
            while not self._stop_event.is_set():
                event = await self.queue.get()
                if isinstance(event, InputIdleEvent):
                    self._pause_session(event)

                # Don't activate when last event was WindowMinimizedEvent
                elif isinstance(event, InputActiveEvent) and isinstance(
                    self._last_session_stop_event,
                    InputIdleEvent,
                ):
                    tg.create_task(self._resume_session())

                if isinstance(event, GameFullscreenEvent):
                    tg.create_task(self._start_session(event.title))

                elif isinstance(event, GameMinimizedEvent):
                    self._pause_session(event)

                elif isinstance(event, GameCloseEvent):
                    tg.create_task(self._stop_session(event))

                self.last_event = event
                self.queue.task_done()

            self._cleanup_session()

    async def run(self):
        self._stop_event.clear()
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.window_watcher.run())
            tg.create_task(self.input_idle_watcher.run())
            tg.create_task(self._run())

    async def stop(self):
        self.log.info(
            f"Stopping; active_session={getattr(self.active_session, "title", None)}; last_event={self.last_event}"
        )
        self._stop_event.set()
        await self.window_watcher.stop()
        await self.input_idle_watcher.stop()
