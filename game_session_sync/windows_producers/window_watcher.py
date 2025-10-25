# run with: poetry run python -m experiments.accessability_events

# pip install pywin32
import asyncio
import logging
import re
import threading
from datetime import datetime, timedelta
from typing import Callable

import ctypes
import psutil
import pythoncom
import win32gui
import win32process
from ctypes import wintypes

import win32api
import win32con
import win32event

from game_session_sync.windows_producers.types import (
    EventBus,
    GameCloseEvent,
    GameFullscreenEvent,
    GameMinimizedEvent,
)
from game_session_sync.windows_producers.utils import async_debounce

log = logging.getLogger(__name__)


def _extract_title(exe: str | None, patterns: list[re.Pattern]) -> str | None:
    if exe:
        for p in patterns:
            matches = p.search(exe)
            if matches is not None and matches.group(1) is not None:
                title = matches.group(1)
                return title


def _pid_to_exe(pid: int) -> str | None:
    try:
        return psutil.Process(pid).exe()
    except psutil.NoSuchProcess:
        log.debug(f"Couldn't find process of pid {pid}")
        return None


def _hwnd_to_exe(hwnd: int) -> str | None:
    # NOTE: We may use the window title: https://stackoverflow.com/a/48857220
    # window_name = win32gui.GetWindowText(hwnd).replace("\u200b", "")
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return _pid_to_exe(pid)


class _ProcessExitWatcher:
    def __init__(self, queue: EventBus, exe_patterns: list[re.Pattern]) -> None:
        self.queue = queue
        self.exe_patterns = exe_patterns
        self._tasks: dict[int, tuple[asyncio.Task, Callable]] = {}

    def _wait_pid_exit(self, pid: int):
        # Minimal rights. Fails on protected processes but fine for most games.
        handle = win32api.OpenProcess(
            win32con.SYNCHRONIZE | win32con.PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        # NOTE: Block in a worker thread so the main loop stays free
        # NOTE: Ideally we wait for only pid, so no need to use WaitForMultipleObjects
        rc = win32event.WaitForSingleObject(handle, win32event.INFINITE)
        if not rc == win32con.WAIT_OBJECT_0:
            raise RuntimeError(
                f"Unexpected return value for win32event.WaitForSingleObject: {rc}"
            )
        return

    def add_pid(self, pid: int):
        if pid in self._tasks:
            return
        # Extract title while the process is available
        title = _extract_title(_pid_to_exe(pid), self.exe_patterns)
        if not title:
            # NOTE: add_pid normally gets called for valid process known to be games
            # If I cannot extract title it means something went horribly wrong
            raise RuntimeError("Couldn't extract title for a game process")
        task = asyncio.create_task(asyncio.to_thread(self._wait_pid_exit, pid))

        def done_callback(_):
            self._tasks.pop(pid)
            self.queue.put_nowait(GameCloseEvent(title))

        self._tasks[pid] = (task, done_callback)
        task.add_done_callback(done_callback)

    def add_hwnd(self, hwnd: int):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        self.add_pid(pid)

    def clear_all(self):
        for task, callback in self._tasks.values():
            task.remove_done_callback(callback)
            task.cancel()  # NOTE: to_thread coroutines are technically not cancelable


user32 = ctypes.windll.user32
GetTickCount64 = ctypes.windll.kernel32.GetTickCount64
GetTickCount64.restype = ctypes.c_ulonglong
GetSystemTimeAsFileTime = ctypes.windll.kernel32.GetSystemTimeAsFileTime

# DWM Enum https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
DWMWA_CLOAKED = 14
DWM_CLOAKED_APP = 0x1
DWM_CLOAKED_SHELL = 0x2
DwmGetWindowAttribute = ctypes.windll.dwmapi.DwmGetWindowAttribute


def _is_fullscreen(hwnd: int) -> bool:
    if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return False
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    mi = win32api.GetMonitorInfo(
        win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    )
    ml, mt, mr, mb = mi["Monitor"]
    return (l, t, r, b) == (ml, mt, mr, mb)


def _is_hidden(hwnd: int) -> bool:
    # Must be a valid, visible, top-level window
    if not win32gui.IsWindow(hwnd):
        log.debug(f"{hwnd}: win32gui.IsWindow")
        return True
    if not win32gui.IsWindowVisible(hwnd):
        log.debug(f"{hwnd}: win32gui.IsWindowVisible")
        return True
    if win32gui.IsIconic(hwnd):
        log.debug(f"{hwnd}: win32gui.IsIconic")
        return True
    if win32gui.GetParent(hwnd):  # has parent → not top-level
        log.debug(f"{hwnd}: win32gui.GetParent")
        return True

    # Must not be owned (tooltips, dialogs, etc.)
    if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
        log.debug(f"{hwnd}: win32gui.GetWindow")
        return True

    exstyle = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    style = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)

    # Tool or popup windows are not user-facing
    if exstyle & win32con.WS_EX_TOOLWINDOW:
        log.debug(f"{hwnd}: win32con.WS_EX_TOOLWINDOW")
        return True
    if not (style & win32con.WS_OVERLAPPEDWINDOW):
        log.debug(f"{hwnd}: win32con.WS_OVERLAPPEDWINDOW")
        return True

    # Skip cloaked (UWP, virtual desktop hidden)
    cloaked = wintypes.DWORD()
    DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_CLOAKED),
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    if cloaked.value != 0:
        log.debug(f"{hwnd}: cloaked")
        return True

    # Skip windows without a visible title
    title = win32gui.GetWindowText(hwnd)
    if not title.strip():
        log.debug(f"{hwnd}: win32gui.GetWindowText")
        return True

    # Skip off-screen or zero-area windows
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except win32gui.error:
        log.debug(f"{hwnd}: win32gui.GetWindowRect Error")
        return True
    if right - left < 50 or bottom - top < 50:
        log.debug(f"{hwnd}: win32gui.GetWindowRect")
        return True
    if win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL) == 0:
        log.debug(f"{hwnd}: win32api.MonitorFromWindow")
        return True

    # Pass only if it would appear in Alt+Tab
    # if exstyle & win32con.WS_EX_APPWINDOW or not (exstyle & win32con.WS_EX_TOOLWINDOW):
    #     return False

    return False


def _event_time_to_datetime(dwmsEventTime: int) -> datetime:
    now = datetime.now()
    tick_from_system_start: int = GetTickCount64()
    tick_diff = tick_from_system_start - dwmsEventTime
    return now - timedelta(milliseconds=tick_diff)


class WindowEventWatcher:
    TARGET_EVENTS = [
        # https://learn.microsoft.com/en-us/windows/win32/winauto/event-constants
        win32con.EVENT_SYSTEM_FOREGROUND,
        win32con.EVENT_OBJECT_LOCATIONCHANGE,
    ]
    # TODO: Use stop signal event to stop instead of polling
    STOP_EVENT_POLLING_MS = 250

    def __init__(
        self,
        queue: EventBus,
        exe_patterns: list[str],
    ) -> None:
        self.queue = queue
        self.exe_patterns = [re.compile(p) for p in exe_patterns]

        self._process_exit_watcher = _ProcessExitWatcher(queue, self.exe_patterns)
        self._last_foreground_title = None
        self._thread_stop_event = threading.Event()
        self.log = logging.getLogger(self.__class__.__name__)

    WIN_EVENT_PROC_TYPE = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    def _WinEventProc(
        self,
        hWinEventHook,
        event,
        hwnd,
        idObject,
        idChild,
        idEventThread,
        dwmsEventTime,
    ) -> None:
        if event == win32con.EVENT_SYSTEM_FOREGROUND:
            # call_soon_threadsafe for **synchronous** functions modifying awaitable objects (like queues etc.)
            self.loop.call_soon_threadsafe(self._handle_foreground, hwnd, dwmsEventTime)
        elif event == win32con.EVENT_OBJECT_LOCATIONCHANGE:
            # run_coroutine_threadsafe for awaitable objects
            asyncio.run_coroutine_threadsafe(
                self._handle_loc_change(hwnd, dwmsEventTime), self.loop
            )

    def _thread_run(self) -> None:
        # https://learn.microsoft.com/en-us/windows/win32/api/winuser/nc-winuser-wineventproc
        CWinEventProc = self.WIN_EVENT_PROC_TYPE(self._WinEventProc)
        hooks = []

        pythoncom.CoInitialize()
        try:
            for event_type in self.TARGET_EVENTS:
                hooks.append(
                    # https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwineventhook
                    user32.SetWinEventHook(
                        event_type,  # eventMin: lowest event value range
                        event_type,  # eventMax: highest event value range
                        0,  # hmodWinEventProc: hook function is using WINEVENT_OUTOFCONTEXT
                        CWinEventProc,  # pfnWinEventProc: pointer to hook function
                        0,  # idProcess: receive events from all processes of current desktop
                        0,  # idThread: receive events from all threads of current desktop
                        win32con.WINEVENT_OUTOFCONTEXT  # dwFlags: flags
                        | win32con.WINEVENT_SKIPOWNPROCESS,
                    )
                )
            # Message loop
            while not self._thread_stop_event.is_set():
                win32gui.PumpWaitingMessages()
                self._thread_stop_event.wait(
                    WindowEventWatcher.STOP_EVENT_POLLING_MS / 1000
                )
        finally:
            for hook in hooks:
                if hook:
                    user32.UnhookWinEvent(hook)
            pythoncom.CoUninitialize()

    def _handle_foreground(self, hwnd, dwmsEventTime):
        if _is_hidden(hwnd):
            return

        timestamp = _event_time_to_datetime(dwmsEventTime)
        title = _extract_title(_hwnd_to_exe(hwnd), self.exe_patterns)

        # new foreground window is not a game while the last window was a game
        if title is None and self._last_foreground_title is not None:
            self.queue.put_nowait(
                GameMinimizedEvent(self._last_foreground_title, timestamp)
            )
            self._last_foreground_title = None
        # new foreground window is a fullscreen game while the last window was not
        # the same game (avoid sending fullscreen after refocus from hidden windows)
        elif title and _is_fullscreen(hwnd) and self._last_foreground_title != title:
            self.queue.put_nowait(GameFullscreenEvent(title, timestamp))
            self._process_exit_watcher.add_hwnd(hwnd)
            self._last_foreground_title = title

    # EVENT_OBJECT_LOCATIONCHANGE events are sent in rapid bursts,
    # so debounce is used ease off events sent to controller
    @async_debounce(2)
    async def _handle_loc_change(self, hwnd, dwmsEventTime):
        if _is_hidden(hwnd):
            return

        timestamp = _event_time_to_datetime(dwmsEventTime)
        title = _extract_title(_hwnd_to_exe(hwnd), self.exe_patterns)

        if title is not None and _is_fullscreen(hwnd):
            self.queue.put_nowait(GameFullscreenEvent(title, timestamp))
            self._process_exit_watcher.add_hwnd(hwnd)

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self._thread_task = asyncio.create_task(asyncio.to_thread(self._thread_run))

    async def stop(self):
        self._thread_stop_event.set()
        self._process_exit_watcher.clear_all()
        await self._thread_task


# poetry run python -m game_session_sync.windows_producers.window_watcher
async def _main():
    from ..log_helpers import Console, setup_test_logging

    console = Console()
    setup_test_logging(console)

    queue: EventBus = EventBus()
    watcher = WindowEventWatcher(queue, [r"(Deus Ex Mankind Divided)"])

    try:
        asyncio.create_task(watcher.run())
        while True:
            user_input = (await asyncio.to_thread(input, "[q: quit] >")).strip()
            if user_input == "q":
                break
    finally:
        await watcher.stop()
        console.kill()


if __name__ == "__main__":
    asyncio.run(_main())
