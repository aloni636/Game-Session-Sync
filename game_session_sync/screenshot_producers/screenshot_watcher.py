import asyncio
import logging
import os
from asyncio import Event
from pathlib import Path

from PIL import Image
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..types import Producer
from .types import ManualScreenshot, ScreenshotBus


def resolve_path(path: str):
    return str(Path(path).expanduser().resolve(strict=True))


class _FileWatcherHandler(FileSystemEventHandler):
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: ScreenshotBus,
        delete_after_push: bool,
    ) -> None:
        super().__init__()
        self._loop = loop
        self._queue = queue
        self._delete_after_push = delete_after_push
        self.log = logging.getLogger(self.__class__.__name__)

    def on_created(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return

        # watchdog may supply bytes on some backends; normalize to str.
        src_path = os.fsdecode(event.src_path)
        if not src_path.endswith(".png"):
            self.log.warning(f"Found screenshot with unexpected prefix: {src_path}")
            return
        img = Image.open(src_path)
        screenshot = ManualScreenshot(img)
        self._loop.call_soon_threadsafe(self._queue.put_nowait, screenshot)
        if self._delete_after_push:
            os.remove(src_path)


class ScreenshotWatcher(Producer):
    def __init__(
        self,
        queue: ScreenshotBus,
        target_dir: str,
        delete_after_push: bool = False,
    ) -> None:
        self._queue = queue
        self._target_dir = resolve_path(target_dir)
        self._delete_after_push = delete_after_push
        self._stop_evt = Event()
        self.log = logging.getLogger(self.__class__.__name__)

    # wrap observer start and stop with async semantics
    async def run(self):
        self._stop_evt.clear()
        loop = asyncio.get_running_loop()
        event_handler = _FileWatcherHandler(loop, self._queue, self._delete_after_push)
        observer = Observer()
        observer.schedule(event_handler, self._target_dir, recursive=True)

        self.log.info("Starting watchdog observer")
        observer.start()

        try:
            await self._stop_evt.wait()
        finally:
            observer.stop()
            await asyncio.to_thread(observer.join)
            self.log.info("Watchdog observer fully stopped")
