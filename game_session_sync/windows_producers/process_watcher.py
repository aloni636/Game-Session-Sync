import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone

import psutil
import pythoncom
from wmi import WMI, x_wmi_timed_out

from ..types import Producer
from .types import EventBus, WindowCloseEvent, WindowOpenEvent


# TODO: Use unprivileged SetWinEventHook EVENT_SYSTEM_FOREGROUND
class _WmiProcessWatcher(threading.Thread):
    WMI_DATETIME_BASE = datetime(1601, 1, 1, tzinfo=timezone.utc)

    def __init__(
        self, loop: asyncio.AbstractEventLoop, queue: EventBus, polling_interval_ms: int
    ) -> None:
        super().__init__(daemon=True)
        self._loop = loop
        self._queue = queue
        self._stop_evt = threading.Event()
        self._polling_interval_ms = polling_interval_ms
        # Retain mapping to resolve process metadata after it was killed.
        self._pid_to_meta: dict[int, tuple[str, str]] = {}
        self.log = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _wmi_ticks_to_dt(ticks: int) -> datetime:
        # TIME_CREATED is 100ns ticks since 1601-01-01 UTC
        return (
            _WmiProcessWatcher.WMI_DATETIME_BASE + timedelta(microseconds=ticks // 10)
        ).astimezone()

    def _wmi_process_info(self, wmi_event, use_cache: bool):
        dt = _WmiProcessWatcher._wmi_ticks_to_dt(int(wmi_event.TIME_CREATED))

        if use_cache:
            meta = self._pid_to_meta.pop(wmi_event.ProcessID, None)
            if meta is not None:
                (exe, name) = meta
                return exe, name, dt
            self.log.debug(f"Cache miss for PID: {wmi_event.ProcessID}")
        try:
            proc = psutil.Process(wmi_event.ProcessID)
            exe = proc.exe()
            name = proc.name()
            self._pid_to_meta[wmi_event.ProcessID] = (exe, name)

        except psutil.NoSuchProcess:
            self.log.debug(f"Couldn't find process name for: {wmi_event.ProcessID}")
            exe = None
            name: str = wmi_event.ProcessName

        return exe, name, dt

    def run(self) -> None:
        self.log.info("Thread starting...")
        timeout = int(self._polling_interval_ms / 2)
        pythoncom.CoInitialize()
        try:
            c = WMI()
            start_w = c.Win32_ProcessStartTrace.watch_for()
            stop_w = c.Win32_ProcessStopTrace.watch_for()

            # Alternate between monitoring processes creation and deletion
            while not self._stop_evt.is_set():
                # start
                try:
                    e = start_w(timeout_ms=timeout)
                    exe, name, dt = self._wmi_process_info(e, use_cache=False)

                    event = WindowOpenEvent(
                        exe=exe,
                        name=name,
                        time=dt,
                    )
                    # see https://docs.python.org/3/library/asyncio-dev.html#concurrency-and-multithreading
                    self._loop.call_soon_threadsafe(
                        self._queue.put_nowait,
                        event,
                    )
                except x_wmi_timed_out:
                    self.log.debug("Start trace poll timed out")

                # stop
                try:
                    e = stop_w(timeout_ms=timeout)
                    # we use cache because the process cannot be analyzed by psutils - it is dead
                    exe, name, dt = self._wmi_process_info(e, use_cache=True)

                    event = WindowCloseEvent(
                        exe=exe,
                        name=name,
                        time=self._wmi_ticks_to_dt(int(e.TIME_CREATED)),
                    )
                    self._loop.call_soon_threadsafe(
                        self._queue.put_nowait,
                        event,
                    )
                except x_wmi_timed_out:
                    self.log.debug("Stop trace poll timed out")
            self.log.info("Thread exiting...")
        finally:
            pythoncom.CoUninitialize()

    def stop(self):
        self._stop_evt.set()
        self.log.info("Stop signal received")


class ProcessWatcher(Producer):
    def __init__(self, queue: EventBus, polling_interval_ms: int) -> None:
        self._queue = queue
        self._polling_interval_ms = polling_interval_ms
        self.log = logging.getLogger(self.__class__.__name__)

    async def run(self):
        loop = asyncio.get_running_loop()
        wmi_process_watcher = _WmiProcessWatcher(
            loop, self._queue, self._polling_interval_ms
        )

        wmi_process_watcher.start()

        try:
            await self._stop_event.wait()
        finally:
            self.log.info("Stopping...")
            wmi_process_watcher.stop()
            await asyncio.to_thread(wmi_process_watcher.join)
            self.log.info("Fully stopped")
