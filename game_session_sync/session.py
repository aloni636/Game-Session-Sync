import asyncio
import logging
from asyncio import Event, Task
from datetime import datetime

import imagehash
from imagehash import ImageHash

from .config import SessionConfig
from .screenshot_producers import PeriodicSampler, ScreenshotBus, ScreenshotWatcher
from .types import LoggingQueue
from .uploader import Uploader


class Session:
    def __init__(
        self,
        title: str,
        uploader: Uploader,
        s_config: SessionConfig,
    ) -> None:
        self.title = title
        self.last_upload_time: datetime

        self._stop_evt = Event()
        self.is_active = False

        self._queue: ScreenshotBus = LoggingQueue()
        self._image_hash: ImageHash | None = None
        self._worker_task: Task | None = None

        self._phash_threshold = s_config.phash_threshold

        self._sampler = PeriodicSampler(self._queue, s_config.screenshot_interval_sec)
        self._watcher = ScreenshotWatcher(
            self._queue,
            s_config.screenshot_watch_path,
        )
        self._uploader = uploader
        self.log = logging.getLogger(f"{self.__class__.__name__}:{self.title!r}")

    async def consume(self):
        while not self._stop_evt.is_set():
            screenshot = await self._queue.get()
            image = screenshot.image
            image_hash = imagehash.average_hash(image)  # fastest method

            if self._image_hash is None:
                self.log.info(f"Uploading first screenshot: {screenshot!r}")
                self._image_hash = image_hash
                self.last_upload_time = screenshot.time
                await self._uploader.upload(self.title, screenshot)
            
            diff = image_hash - self._image_hash 
            if diff >= self._phash_threshold:
                self.log.info(
                    f"Uploading screenshot (delta={diff} threshold={self._phash_threshold})"
                )
                self._image_hash = image_hash
                self.last_upload_time = screenshot.time
                await self._uploader.upload(self.title, screenshot)
            else:
                self.log.debug(
                    f"Skipping similar screenshot (delta={diff} threshold={self._phash_threshold})"
                )
            self._queue.task_done()

    async def run(self):
        self.is_active = True
        self._stop_evt.clear()
        self.log.info("Session running...")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._sampler.run())
            tg.create_task(self._watcher.run())
            tg.create_task(self.consume())

    def stop(self):
        "Signal current session to stop"
        self.is_active = False
        self._stop_evt.set()
        self.log.info("Session stopping")

        # TODO: Why sampler still works after stop signal?
        self._sampler.stop()
        self._watcher.stop()
