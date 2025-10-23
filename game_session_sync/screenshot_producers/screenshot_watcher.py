import asyncio
import logging
import os
from asyncio import Event
from pathlib import Path
from zoneinfo import ZoneInfo

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from game_session_sync.screenshot_producers.utils import screenshot_filename

from ..types import Producer


def resolve_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=True))


class _FileWatcherHandler(FileSystemEventHandler):
    def __init__(self, target_dir: str, title: str, tz: ZoneInfo) -> None:
        super().__init__()
        self.target_dir: Path = Path(target_dir)
        self.title = title
        self.tz = tz
        self.log = logging.getLogger(self.__class__.__name__)

    # NOTE: on_closed does not actually provide any events in Windows for my use case
    # def on_closed(self, event: FileClosedEvent) -> None:

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        # watchdog may supply bytes on some backends; normalize to str.
        src_path = Path(os.fsdecode(event.src_path))

        if src_path.suffix != ".png":
            self.log.warning(f"Manual screenshot with unexpected suffix: {src_path!r}")
            return

        dst_path = self.target_dir / screenshot_filename(
            self.title, src_path.suffix, self.tz, manual=True
        )
        self.log.info(f"Moving: {src_path!r} ---> {dst_path!r}")
        src_path.rename(dst_path)


class ScreenshotWatcher(Producer):
    def __init__(
        self, source_dir: str, target_dir: str, title: str, tz: ZoneInfo
    ) -> None:
        self.source_dir = resolve_path(source_dir)
        self.target_dir = resolve_path(target_dir)
        self.title = title
        self.tz = tz
        self._stop_evt = Event()

    # wrap observer start and stop with async semantics
    async def run(self):
        event_handler = _FileWatcherHandler(self.target_dir, self.title, self.tz)
        observer = Observer()
        observer.schedule(event_handler, self.source_dir, recursive=True)

        observer.start()
        try:
            await self._stop_evt.wait()
        finally:
            observer.stop()
            await asyncio.to_thread(observer.join)


if __name__ == "__main__":
    import tzlocal

    from game_session_sync.test_helpers import producer_test_run

    watcher = ScreenshotWatcher(
        r"~\Pictures\Screenshots",
        "./images",
        "Deus Ex Mankind Divided",
        tzlocal.get_localzone(),
    )
    asyncio.run(producer_test_run(watcher))
