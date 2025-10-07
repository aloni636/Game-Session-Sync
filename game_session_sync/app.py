import asyncio
import logging
import re
from asyncio import Event

from .config import Config
from .session import Session
from .types import LoggingQueue
from .uploader import Uploader
from .windows_producers import *


class App:
    def __init__(self, config: Config) -> None:
        self.queue: EventBus = LoggingQueue()
        self.full_screen_watcher = FullScreenWatcher(
            self.queue, config.monitor.polling_interval_ms
        )
        self.input_idle_watcher = InputIdleWatcher(
            self.queue,
            config.monitor.polling_interval_ms,
            config.monitor.input_idle_sec,
        )
        self.process_watcher = ProcessWatcher(
            self.queue, config.monitor.polling_interval_ms
        )

        self.sessions: dict[str, Session] = dict()
        self.active_session: Session | None = None
        self.stop_event = None
        self.last_event = None

        self._stop_evt = Event()

        self.uploader = Uploader(
            config.connection,
            config.notion_properties,
            # TODO: drop session upload back to supervisor
            config.session.minimum_session_gap_min,
        )
        self.s_config = config.session
        self.patterns = [
            re.compile(p) for p in config.monitor.game_process_regex_pattern
        ]

        self.log = logging.getLogger(self.__class__.__name__)

    def extract_title(self, exe: str | None) -> str | None:
        if exe is None:
            return exe
        for p in self.patterns:
            matches = p.search(exe)
            if matches is not None and matches.group(1) is not None:
                title = matches.group(1)
                self.log.info(f"Extracted title {title!r} from: {exe!r}")
                return title
        return None

    async def consume(self):
        # Task groups propagate errors instead of being isolated in Task objects
        # when creating them with asyncio.create_task
        async with asyncio.TaskGroup() as tg:
            while not self._stop_evt.is_set():
                event = await self.queue.get()
                if isinstance(event, InputIdleEvent):
                    if self.active_session is not None:
                        self.log.info(
                            f"Input idle for {event.idle_seconds:.1f}s; stopping "
                            f"session {self.active_session.title}"
                        )
                        self.active_session.stop()
                        self.stop_event = event
                    else:
                        self.log.info("Ignoring idle event; no active session")

                elif isinstance(event, InputActiveEvent) and isinstance(
                    self.stop_event, InputIdleEvent
                ):
                    if (
                        self.active_session is not None
                        and not self.active_session.is_active
                        # don't activate when last event was WindowMinimizedEvent
                    ):
                        self.log.info(
                            f"Input activity detected; resuming session "
                            f"{self.active_session.title}"
                        )
                        tg.create_task(self.active_session.run())
                    else:
                        self.log.info(
                            f"Ignoring activity event; active_session={self.active_session} "
                            f"stop_event={self.stop_event}"
                        )

                elif isinstance(event, WindowOpenEvent):
                    pass

                elif isinstance(event, WindowFullscreenEvent):
                    title = self.extract_title(event.exe)
                    if title is not None:
                        if self.active_session is None:
                            self.log.info(
                                f"Creating session for fullscreen title {title}"
                            )
                            self.active_session = Session(
                                title, self.uploader, self.s_config
                            )
                        elif self.active_session.title != title:
                            self.log.info(
                                f"Switching session from {self.active_session.title} to {title}"
                            )
                            self.active_session.stop()
                            self.active_session = Session(
                                title, self.uploader, self.s_config
                            )
                        if not self.active_session.is_active:
                            tg.create_task(self.active_session.run())

                elif isinstance(event, WindowMinimizedEvent):
                    title = self.extract_title(event.exe)
                    if (
                        self.active_session is not None
                        and self.active_session.title == title
                    ):
                        self.log.info(
                            f"WindowMinimizedEvent: Stopping session {self.active_session.title!r}"
                        )
                        self.active_session.stop()
                        self.stop_event = event

                elif isinstance(event, WindowCloseEvent):
                    title = self.extract_title(event.exe)
                    if (
                        self.active_session is not None
                        and self.active_session.title == title
                    ):
                        self.log.info(
                            f"WindowCloseEvent: Stopping session {self.active_session.title!r}"
                        )
                        self.active_session.stop()
                        self.active_session = None
                        self.stop_event = event

                self.last_event = event
                self.queue.task_done()

    async def run_application(self):
        self._stop_evt.clear()
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.full_screen_watcher.run())
            tg.create_task(self.input_idle_watcher.run())
            tg.create_task(self.process_watcher.run())
            tg.create_task(self.consume())

    def stop(self):
        self.log.info(
            f"Stopping; active_session={getattr(self.active_session, "title", None)}; last_event={self.last_event}"
        )
        self._stop_evt.set()
        self.process_watcher.stop()
        self.full_screen_watcher.stop()
        self.input_idle_watcher.stop()
        if self.active_session is not None:
            self.active_session.stop()
