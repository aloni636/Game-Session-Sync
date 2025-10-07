import asyncio
import logging
from asyncio import Event
from pathlib import Path

import psutil
import win32gui
import win32process
from ctypes import windll
from psutil import Process

from ..types import Producer
from .types import EventBus, WindowFullscreenEvent, WindowMinimizedEvent

user32 = windll.user32


class FullScreenWatcher(Producer):
    """
    Polls the current foreground window and tracks its fullscreen bounds against the last sample.\\
    On any focus or fullscreen change, it enqueues a WindowEvent describing the process state.
    """

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
        self.log = logging.getLogger(self.__class__.__name__)

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
                    exe = p.exe()
                    name = p.name()
                except psutil.NoSuchProcess:
                    self.log.debug(f"Couldn't find process name for: {prev_pid}")
                    exe = None
                    name = None
                event = WindowMinimizedEvent(
                    exe=exe,
                    name=name,
                )
                await self._queue.put(event)

            # New window or fullscreen state flip: emit current state
            if (not is_same_hwnd) or (not is_same_full):
                try:
                    p = Process(pid)
                    exe = p.exe()
                    name = p.name()
                except psutil.NoSuchProcess:
                    self.log.debug(f"Couldn't find process name for: {pid}")
                    exe = None
                    name = None
                event = (
                    WindowFullscreenEvent(
                        exe=exe,
                        name=name,
                    )
                    if is_full
                    else WindowMinimizedEvent(
                        exe=exe,
                        name=name,
                    )
                )

                await self._queue.put(event)

            self._current_foreground_hwnd = hwnd
            self._current_pid = pid
            self._current_is_fullscreen = is_full
            self.log.debug(
                f"State: current_foreground_hwnd: {self._current_foreground_hwnd=}"
                f"State: current_pid: {self._current_pid=}"
                f"State: current_is_fullscreen: {self._current_is_fullscreen=}"
            )
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._polling_interval_ms / 1000,
                )
            except asyncio.TimeoutError:
                continue
