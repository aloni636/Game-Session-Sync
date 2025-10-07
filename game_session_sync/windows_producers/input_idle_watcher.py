import asyncio
import logging
from asyncio import Event

import ctypes
from ctypes import Structure, windll, wintypes

from ..types import Producer
from .types import EventBus, InputActiveEvent, InputIdleEvent

user32 = windll.user32
kernel32 = windll.kernel32


class InputIdleWatcher(Producer):
    # see https://docs.python.org/3/library/ctypes.html#structures-and-unions
    class LASTINPUTINFO(Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("dwTime", wintypes.DWORD),
        ]

    # see https://docs.python.org/3/library/ctypes.html#specifying-the-required-argument-types-function-prototypes
    kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    user32.GetLastInputInfo.restype = wintypes.BOOL

    def __init__(
        self, queue: EventBus, polling_interval_ms: float, idle_seconds: float
    ) -> None:
        self._queue = queue
        self._polling_interval_ms = polling_interval_ms
        self._idle_seconds = idle_seconds
        self._reported = False
        self._stop_event = Event()
        self.log = logging.getLogger(self.__class__.__name__)

    def _get_idle_seconds(self) -> float:
        info = InputIdleWatcher.LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(InputIdleWatcher.LASTINPUTINFO)

        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0

        tick_count = int(kernel32.GetTickCount64())
        last_input = int(info.dwTime)
        # dwTime is in milliseconds since system start
        idle_ms = (tick_count - last_input) if tick_count >= last_input else 0
        return idle_ms / 1000.0

    async def run(
        self,
    ) -> None:
        self.log.info("InputIdleWatcher running...")
        while not self._stop_event.is_set():
            idle_seconds = self._get_idle_seconds()

            if idle_seconds >= self._idle_seconds and not self._reported:
                event = InputIdleEvent(idle_seconds=idle_seconds)

                await self._queue.put(event)
                self._reported = True
            elif idle_seconds < self._idle_seconds and self._reported:
                event = InputActiveEvent(idle_seconds=idle_seconds)

                await self._queue.put(event)
                self._reported = False

            self.log.debug(
                f"State: idle_seconds={idle_seconds} reported={self._reported}"
            )
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._polling_interval_ms / 1000,
                )
            except asyncio.TimeoutError:
                continue
