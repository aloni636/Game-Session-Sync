import asyncio
import logging
from asyncio import Event

import mss
from PIL import Image

from ..types import Producer
from .types import PeriodicScreenshot, ScreenshotBus


class PeriodicSampler(Producer):
    def __init__(self, queue: ScreenshotBus, interval_sec: int) -> None:
        self._queue = queue
        self._interval_sec = interval_sec
        self.log = logging.getLogger(self.__class__.__name__)

    async def run(self):
        while not self._stop_event.is_set():
            with mss.mss() as sct:
                # TODO: select the monitor based on the game (fullscreen) window
                sct_img = sct.grab(sct.monitors[0])  # all monitors combined
                self.log.info(f"Took screenshot: {sct_img.size}")
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                screenshot = PeriodicScreenshot(img)
                await self._queue.put(screenshot)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), self._interval_sec)
                except asyncio.TimeoutError:
                    continue
