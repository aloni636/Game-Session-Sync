import asyncio
import threading
from asyncio import Queue
from ctypes import windll
from datetime import datetime, timedelta, timezone

import psutil
import pythoncom
import win32gui
import win32process
from psutil import Process
from wmi import WMI, x_wmi_timed_out

WMI_DATETIME_BASE = datetime(1601, 1, 1, tzinfo=timezone.utc)

user32 = windll.user32
user32.SetProcessDPIAware()


class FullScreenTracker:
    def __init__(self, polling_interval_ms: int) -> None:
        self.current_foreground_hwnd = None
        self.current_is_fullscreen = False
        self.polling_interval_ms = polling_interval_ms
        self.full_screen_rect = (
            0,
            0,
            user32.GetSystemMetrics(0),
            user32.GetSystemMetrics(1),
        )

    async def run(self):
        while True:
            try:
                foreground_hwnd = user32.GetForegroundWindow()
                rect = win32gui.GetWindowRect(foreground_hwnd)
                _, pid = win32process.GetWindowThreadProcessId(foreground_hwnd)
                is_fullscreen = rect == self.full_screen_rect

                is_same_hwnd = self.current_foreground_hwnd == foreground_hwnd
                is_same_fullscreen_state = self.current_is_fullscreen == is_fullscreen

                p = Process(pid)

                log = " name=%s time=%s exe=%s" % (
                    p.name(),
                    datetime.now().time(),
                    p.exe(),
                )

                # same window, modified fullscreen state
                if not is_same_fullscreen_state and is_same_hwnd:
                    if is_fullscreen:
                        print("[maximized]" + log)
                    else:
                        print("[minimized]" + log)

                self.current_foreground_hwnd = foreground_hwnd
                self.current_is_fullscreen = is_fullscreen

            except Exception:
                pass
            await asyncio.sleep(self.polling_interval_ms / 1000)


class WmiProcessProducerThread(threading.Thread):
    def __init__(
        self, loop: asyncio.AbstractEventLoop, queue: Queue, stop_evt: threading.Event
    ) -> None:
        super().__init__(daemon=True)
        self.loop = loop
        self.queue = queue
        self.stop_evt = stop_evt

    def run(self) -> None:
        # COM must be initialized in the thread that uses it
        pythoncom.CoInitialize()
        try:
            c = WMI()
            watcher = c.Win32_ProcessStartTrace.watch_for()
            while not self.stop_evt.is_set():
                try:
                    evt = watcher(
                        timeout_ms=500
                    )  # small timeout to allow graceful stop
                except x_wmi_timed_out:
                    continue
                # Pass to asyncio world thread-safely
                self.loop.call_soon_threadsafe(self.queue.put_nowait, evt)
        finally:
            pythoncom.CoUninitialize()


class Consumer:
    def __init__(self, process_queue: Queue) -> None:
        self.process_queue = process_queue

    async def run(self):
        while True:
            e = await self.process_queue.get()
            try:
                try:
                    exe_path = psutil.Process(e.ProcessID).exe()
                except psutil.NoSuchProcess:
                    exe_path = "psutil.NoSuchProcess"
                ts = (
                    (
                        WMI_DATETIME_BASE
                        + timedelta(microseconds=int(e.TIME_CREATED) / 10)
                    )
                    .astimezone()
                    .time()
                )
                print(
                    "[+] pid=%s ppid=%s name=%s time=%s exe=%s"
                    % (e.ProcessID, e.ParentProcessID, e.ProcessName, ts, exe_path)
                )
            finally:
                self.process_queue.task_done()


async def main():
    queue = Queue()
    loop = asyncio.get_running_loop()
    stop_evt = threading.Event()
    producer = WmiProcessProducerThread(loop, queue, stop_evt)
    producer.start()
    try:
        await asyncio.gather(
            Consumer(queue).run(),
            FullScreenTracker(500).run(),
        )
    finally:
        stop_evt.set()
        producer.join(timeout=2)


if __name__ == "__main__":
    asyncio.run(main())
