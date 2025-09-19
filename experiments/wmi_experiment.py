import asyncio
import os
import threading
from asyncio import Event, Queue
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, TypeAlias

import ctypes
import psutil
import pythoncom
import win32gui
import win32process
from ctypes import Structure, windll, wintypes
from psutil import Process
from wmi import WMI, x_wmi_timed_out

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

user32 = windll.user32
kernel32 = windll.kernel32


GOG_ROOT = Path(r"C:\Program Files (x86)\GOG Galaxy\Games")


@dataclass
class NewScreenshotEvent:
    path: Path
    time: datetime = field(default_factory=lambda: datetime.now().astimezone())


@dataclass
class WindowEvent:
    exe: Path
    name: str
    state: Literal["open", "minimized", "fullscreen", "closed"]
    time: datetime = field(default_factory=lambda: datetime.now().astimezone())


@dataclass
class InputIdleEvent:
    idle_seconds: float
    timestamp: datetime = field(default_factory=lambda: datetime.now().astimezone())


@dataclass
class InputActiveEvent:
    idle_seconds: float
    timestamp: datetime = field(default_factory=lambda: datetime.now().astimezone())


EventBus: TypeAlias = Queue[
    NewScreenshotEvent | WindowEvent | InputIdleEvent | InputActiveEvent
]


# Polls the current foreground window and tracks its fullscreen bounds against the last sample.
# On any focus or fullscreen change, it enqueues a GameEvent describing the process state.
class FullScreenWatcher:
    user32.SetProcessDPIAware()

    def __init__(self, queue: EventBus, polling_interval_ms: int) -> None:
        self._queue = queue
        self._polling_interval_ms = polling_interval_ms
        self._current_foreground_hwnd: int | None = None
        self._current_pid: int | None = None
        self._current_is_fullscreen = False
        self._full_screen_rect = (
            0,
            0,
            user32.GetSystemMetrics(0),
            user32.GetSystemMetrics(1),
        )
        self._stop_event = Event()

    async def run(self):
        while not self._stop_event.is_set():
            prev_hwnd = self._current_foreground_hwnd
            prev_pid = self._current_pid
            prev_is_full = self._current_is_fullscreen

            hwnd = user32.GetForegroundWindow()
            rect = win32gui.GetWindowRect(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            is_full = rect == self._full_screen_rect

            is_same_hwnd = prev_hwnd == hwnd
            is_same_full = prev_is_full == is_full

            # Focus left the previous window: if it was fullscreen, report it as minimized
            if prev_hwnd is not None and not is_same_hwnd and prev_is_full:
                try:
                    p = Process(prev_pid)  # narrow catch
                    exe_path = Path(p.exe())
                    name = p.name()
                except psutil.NoSuchProcess:
                    exe_path = Path("psutil.NoSuchProcess")
                    name = "psutil.NoSuchProcess"
                await self._queue.put(
                    WindowEvent(
                        exe=exe_path,
                        name=name,
                        state="minimized",
                    )
                )

            # New window or fullscreen state flip: emit current state
            if (not is_same_hwnd) or (not is_same_full):
                try:
                    p = Process(pid)
                    exe_path = Path(p.exe())
                    name = p.name()
                except psutil.NoSuchProcess:
                    exe_path = Path("psutil.NoSuchProcess")
                    name = "psutil.NoSuchProcess"
                await self._queue.put(
                    WindowEvent(
                        exe=exe_path,
                        name=name,
                        state=("fullscreen" if is_full else "minimized"),
                    )
                )

            self._current_foreground_hwnd = hwnd
            self._current_pid = pid
            self._current_is_fullscreen = is_full

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._polling_interval_ms / 1000
                )
            except asyncio.TimeoutError:
                continue

    def close(self):
        self._stop_event.set()


class WmiProcessWatcher(threading.Thread):
    WMI_DATETIME_BASE = datetime(1601, 1, 1, tzinfo=timezone.utc)

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: EventBus) -> None:
        super().__init__(daemon=True)
        self._loop = loop
        self._queue = queue
        self._stop_evt = threading.Event()
        # Retain mapping to resolve process metadata after it was killed.
        self._pid_to_meta: dict[int, tuple[Path, str]] = {}

    @staticmethod
    def _wmi_ticks_to_dt(ticks: int) -> datetime:
        # TIME_CREATED is 100ns ticks since 1601-01-01 UTC
        return (
            WmiProcessWatcher.WMI_DATETIME_BASE + timedelta(microseconds=ticks // 10)
        ).astimezone()

    def _wmi_process_info(self, e, use_cache: bool):
        dt = WmiProcessWatcher._wmi_ticks_to_dt(int(e.TIME_CREATED))

        if use_cache:
            meta = self._pid_to_meta.pop(e.ProcessID, None)
            if meta is not None:
                (exe, name) = meta
                return exe, name, dt
        try:
            proc = psutil.Process(e.ProcessID)
            exe = Path(proc.exe())
            name = proc.name()
            self._pid_to_meta[e.ProcessID] = (exe, name)

        except psutil.NoSuchProcess:
            exe = Path("psutil.NoSuchProcess")
            name: str = getattr(e, "ProcessName", "psutil.NoSuchProcess")

        return exe, name, dt

    def run(self) -> None:
        pythoncom.CoInitialize()
        try:
            c = WMI()
            start_w = c.Win32_ProcessStartTrace.watch_for()
            stop_w = c.Win32_ProcessStopTrace.watch_for()

            # Alternate between monitoring processes creation and deletion
            while not self._stop_evt.is_set():
                # start
                try:
                    e = start_w(timeout_ms=200)
                    exe, name, dt = self._wmi_process_info(e, use_cache=False)

                    # see https://docs.python.org/3/library/asyncio-dev.html#concurrency-and-multithreading
                    self._loop.call_soon_threadsafe(
                        self._queue.put_nowait,
                        WindowEvent(
                            exe=exe,
                            name=name,
                            state="open",
                            time=dt,
                        ),
                    )
                except x_wmi_timed_out:
                    pass

                # stop
                try:
                    e = stop_w(timeout_ms=200)
                    exe, name, dt = self._wmi_process_info(e, use_cache=True)

                    self._loop.call_soon_threadsafe(
                        self._queue.put_nowait,
                        WindowEvent(
                            exe=exe,
                            name=name,
                            state="closed",
                            time=self._wmi_ticks_to_dt(int(e.TIME_CREATED)),
                        ),
                    )
                except x_wmi_timed_out:
                    pass
        finally:
            pythoncom.CoUninitialize()

    def stop(self):
        self._stop_evt.set()


class FileWatcherHandler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: EventBus) -> None:
        super().__init__()
        self._loop = loop
        self._queue = queue

    def on_created(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        # watchdog may supply bytes on some backends; normalize to str.
        src = os.fsdecode(event.src_path)
        ev = NewScreenshotEvent(path=Path(src))
        self._loop.call_soon_threadsafe(self._queue.put_nowait, ev)


class InputIdleWatcher:
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

    async def run(
        self,
    ) -> None:
        while not self._stop_event.is_set():
            idle_seconds = self._get_idle_seconds()

            if idle_seconds >= self._idle_seconds and not self._reported:
                await self._queue.put(InputIdleEvent(idle_seconds=idle_seconds))
                self._reported = True
            elif idle_seconds < self._idle_seconds and self._reported:
                await self._queue.put(InputActiveEvent(idle_seconds=idle_seconds))
                self._reported = False

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._polling_interval_ms / 1000
                )
            except asyncio.TimeoutError:
                continue

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

    def stop(self):
        self._stop_event.set()


class Consumer:
    def __init__(self, event_queue: EventBus) -> None:
        self.event_queue = event_queue

    @staticmethod
    def _is_under(root: Path, p: Path) -> bool:
        try:
            root_s = os.path.normcase(str(root))
            p_s = os.path.normcase(str(p))
            return p_s == root_s or p_s.startswith(root_s + os.sep)
        except Exception:
            return False

    async def run(self):
        while True:
            e = await self.event_queue.get()
            try:
                if isinstance(e, WindowEvent):
                    # Filter to GOG install root
                    if self._is_under(GOG_ROOT, e.exe):
                        print(
                            "[window:%s] time=%s name=%s exe=%s"
                            % (e.state, e.time.time(), e.name, e.exe)
                        )
                elif isinstance(e, NewScreenshotEvent):
                    print("[screenshot] time=%s path=%s" % (e.time.time(), e.path))
                elif isinstance(e, InputIdleEvent):
                    print(
                        "[input-idle] time=%s idle_seconds=%.2f"
                        % (e.timestamp.time(), e.idle_seconds)
                    )
                elif isinstance(e, InputActiveEvent):
                    print(
                        "[input-active] time=%s idle_seconds=%.2f"
                        % (e.timestamp.time(), e.idle_seconds)
                    )
            finally:
                self.event_queue.task_done()


async def main():
    queue: EventBus = Queue()
    loop = asyncio.get_running_loop()

    producer = WmiProcessWatcher(loop, queue)
    producer.start()

    event_handler = FileWatcherHandler(loop, queue)
    observer = Observer()
    observer.schedule(event_handler, "./observatory", recursive=True)
    observer.start()
    try:
        await asyncio.gather(
            Consumer(queue).run(),
            FullScreenWatcher(queue, 500).run(),
            InputIdleWatcher(queue, 500, 5).run(),
        )
    finally:
        observer.stop()
        producer.stop()
        observer.join(timeout=2)
        producer.join(timeout=2)


if __name__ == "__main__":
    asyncio.run(main())
