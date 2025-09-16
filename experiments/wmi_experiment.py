import asyncio
import os
import threading
from asyncio import Queue
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, TypeAlias

import psutil
import pythoncom
import win32gui
import win32process
from ctypes import windll
from psutil import Process
from wmi import WMI, x_wmi_timed_out

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

WMI_DATETIME_BASE = datetime(1601, 1, 1, tzinfo=timezone.utc)

user32 = windll.user32
user32.SetProcessDPIAware()

GOG_ROOT = Path(r"C:\Program Files (x86)\GOG Galaxy\Games")


@dataclass
class NewScreenshotEvent:
    path: Path
    time: datetime


@dataclass
class GameEvent:
    exe: Path
    name: str
    state: Literal["open", "minimized", "fullscreen", "closed"]
    time: datetime


EventBus: TypeAlias = Queue[NewScreenshotEvent | GameEvent]


class FullScreenTracker:
    def __init__(self, polling_interval_ms: int, queue: EventBus) -> None:
        self.queue = queue
        self.polling_interval_ms = polling_interval_ms
        self.current_foreground_hwnd: int | None = None
        self.current_pid: int | None = None
        self.current_is_fullscreen = False
        self.full_screen_rect = (
            0,
            0,
            user32.GetSystemMetrics(0),
            user32.GetSystemMetrics(1),
        )

    async def run(self):
        while True:
            try:
                prev_hwnd = self.current_foreground_hwnd
                prev_pid = self.current_pid
                prev_is_full = self.current_is_fullscreen

                hwnd = user32.GetForegroundWindow()
                rect = win32gui.GetWindowRect(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                is_full = rect == self.full_screen_rect

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
                    await self.queue.put(
                        GameEvent(
                            exe=exe_path,
                            name=name,
                            state="minimized",
                            time=datetime.now().astimezone(),
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
                    await self.queue.put(
                        GameEvent(
                            exe=exe_path,
                            name=name,
                            state=("fullscreen" if is_full else "minimized"),
                            time=datetime.now().astimezone(),
                        )
                    )

                self.current_foreground_hwnd = hwnd
                self.current_pid = pid
                self.current_is_fullscreen = is_full

            except Exception:
                pass
            await asyncio.sleep(self.polling_interval_ms / 1000)


class WmiProcessProducerThread(threading.Thread):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: EventBus) -> None:
        super().__init__(daemon=True)
        self.loop = loop
        self.queue = queue
        self.stop_evt = threading.Event()
        # Retain mapping to resolve process metadata after it was killed.
        self._pid_to_meta: dict[int, tuple[Path, str]] = {}

    @staticmethod
    def _ticks_to_dt(ticks: int) -> datetime:
        # TIME_CREATED is 100ns ticks since 1601-01-01 UTC
        return (WMI_DATETIME_BASE + timedelta(microseconds=ticks // 10)).astimezone()

    def run(self) -> None:
        pythoncom.CoInitialize()
        try:
            c = WMI()
            start_w = c.Win32_ProcessStartTrace.watch_for()
            stop_w = c.Win32_ProcessStopTrace.watch_for()

            # Alternate between monitoring processes creation and deletion
            while not self.stop_evt.is_set():
                # start
                try:
                    e = start_w(timeout_ms=200)
                    try:
                        proc = psutil.Process(e.ProcessID)
                        exe = Path(proc.exe())
                        name = proc.name()
                    except psutil.NoSuchProcess:
                        exe = Path("psutil.NoSuchProcess")
                        name = getattr(e, "ProcessName", "psutil.NoSuchProcess")

                    self._pid_to_meta[e.ProcessID] = (exe, name)

                    self.loop.call_soon_threadsafe(
                        self.queue.put_nowait,
                        GameEvent(
                            exe=exe,
                            name=name,
                            state="open",
                            time=self._ticks_to_dt(int(e.TIME_CREATED)),
                        ),
                    )
                except x_wmi_timed_out:
                    pass

                # stop
                try:
                    e = stop_w(timeout_ms=200)
                    meta = self._pid_to_meta.pop(e.ProcessID, None)
                    if meta is not None:
                        exe, name = meta
                    else:
                        # Try psutil once; narrow exception.
                        try:
                            proc = psutil.Process(e.ProcessID)
                            exe = Path(proc.exe())
                            name = proc.name()
                        except psutil.NoSuchProcess:
                            exe = Path("psutil.NoSuchProcess")
                            name = getattr(e, "ProcessName", "psutil.NoSuchProcess")

                    self.loop.call_soon_threadsafe(
                        self.queue.put_nowait,
                        GameEvent(
                            exe=exe,
                            name=name,
                            state="closed",
                            time=self._ticks_to_dt(int(e.TIME_CREATED)),
                        ),
                    )
                except x_wmi_timed_out:
                    pass
        finally:
            pythoncom.CoUninitialize()

    def stop(self):
        self.stop_evt.set()


class FileWatcherHandler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: EventBus) -> None:
        super().__init__()
        self.loop = loop
        self.queue = queue

    def on_created(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        # watchdog may supply bytes on some backends; normalize to str.
        src = os.fsdecode(event.src_path)
        ev = NewScreenshotEvent(path=Path(src), time=datetime.now().astimezone())
        self.loop.call_soon_threadsafe(self.queue.put_nowait, ev)


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
                if isinstance(e, GameEvent):
                    # Filter to GOG install root
                    if self._is_under(GOG_ROOT, e.exe):
                        print(
                            "[game:%s] time=%s name=%s exe=%s"
                            % (e.state, e.time.time(), e.name, e.exe)
                        )
                elif isinstance(e, NewScreenshotEvent):
                    print("[screenshot] time=%s path=%s" % (e.time.time(), e.path))
            finally:
                self.event_queue.task_done()


async def main():
    queue: EventBus = Queue()
    loop = asyncio.get_running_loop()

    producer = WmiProcessProducerThread(loop, queue)
    producer.start()

    event_handler = FileWatcherHandler(loop, queue)
    observer = Observer()
    observer.schedule(event_handler, "./observatory", recursive=True)
    observer.start()
    try:
        await asyncio.gather(
            Consumer(queue).run(),
            FullScreenTracker(500, queue).run(),
        )
    finally:
        observer.stop()
        producer.stop()
        observer.join(timeout=2)
        producer.join(timeout=2)


if __name__ == "__main__":
    asyncio.run(main())
