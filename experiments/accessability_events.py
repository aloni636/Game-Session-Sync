# run with: poetry run python -m experiments.accessability_events

# pip install pywin32
import asyncio
import threading
from concurrent.futures import thread
from datetime import datetime, timedelta, timezone
from typing import final

import ctypes
import pythoncom
import win32gui
import win32process
from ctypes import wintypes

import win32api
import win32con

from experiments import console
from experiments.console import Console

user32 = ctypes.windll.user32
GetTickCount64 = ctypes.windll.kernel32.GetTickCount64
GetTickCount64.restype = ctypes.c_ulonglong
GetSystemTimeAsFileTime = ctypes.windll.kernel32.GetSystemTimeAsFileTime

# DWM Enum https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
DWMWA_CLOAKED = 14
DWM_CLOAKED_APP = 0x1
DWM_CLOAKED_SHELL = 0x2
DwmGetWindowAttribute = ctypes.windll.dwmapi.DwmGetWindowAttribute


from .accessability_events_names import event_name

WinEventProcType = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)


def is_fullscreen(hwnd: int) -> bool:
    if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return False
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    mi = win32api.GetMonitorInfo(
        win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    )
    ml, mt, mr, mb = mi["Monitor"]
    return (l, t, r, b) == (ml, mt, mr, mb)


def detect_hidden(hwnd: int) -> str | None:
    # Must be a valid, visible, top-level window
    if not win32gui.IsWindow(hwnd):
        return "win32gui.IsWindow"
    if not win32gui.IsWindowVisible(hwnd):
        return "win32gui.IsWindowVisible"
    if win32gui.IsIconic(hwnd):
        return "win32gui.IsIconic"
    if win32gui.GetParent(hwnd):  # has parent → not top-level
        return "win32gui.GetParent"

    # Must not be owned (tooltips, dialogs, etc.)
    if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
        return "win32gui.GetWindow"

    exstyle = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    style = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)

    # Tool or popup windows are not user-facing
    if exstyle & win32con.WS_EX_TOOLWINDOW:
        return "win32con.WS_EX_TOOLWINDOW"
    if not (style & win32con.WS_OVERLAPPEDWINDOW):
        return "win32con.WS_OVERLAPPEDWINDOW"

    # Skip cloaked (UWP, virtual desktop hidden)
    cloaked = wintypes.DWORD()
    DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_CLOAKED),
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    if cloaked.value != 0:
        return "cloaked"

    # Skip windows without a visible title
    title = win32gui.GetWindowText(hwnd)
    if not title.strip():
        return "win32gui.GetWindowText"

    # Skip off-screen or zero-area windows
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except win32gui.error:
        return "win32gui.GetWindowRect Error"
    if right - left < 50 or bottom - top < 50:
        return "win32gui.GetWindowRect"
    if win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL) == 0:
        return "win32api.MonitorFromWindow"

    # Pass only if it would appear in Alt+Tab
    # if exstyle & win32con.WS_EX_APPWINDOW or not (exstyle & win32con.WS_EX_TOOLWINDOW):
    #     return None
    return None


def event_time_to_datetime(dwmsEventTime: int) -> datetime:
    now = datetime.now()
    tick_from_system_start: int = GetTickCount64()
    tick_diff = tick_from_system_start - dwmsEventTime
    return now - timedelta(milliseconds=tick_diff)


class WindowEventWatcher(threading.Thread):
    TARGET_EVENTS = [
        # win32con.EVENT_SYSTEM_MINIMIZESTART,
        # win32con.EVENT_SYSTEM_MINIMIZEEND,
        # win32con.EVENT_OBJECT_LOCATIONCHANGE,
        win32con.EVENT_OBJECT_DESTROY,
        win32con.EVENT_SYSTEM_FOREGROUND,
    ]
    STOP_EVENT_POLLING_MS = 250
    MINIMUM_WINDOW_SIZE = 1

    def __init__(self, console: Console) -> None:
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self._hide_hidden: bool = False
        self.console = console

    def toggle_user_facing(self) -> bool:
        self._hide_hidden = not self._hide_hidden
        return self._hide_hidden

    def _WinEventProc(
        self,
        hWinEventHook,
        event,
        hwnd,
        idObject,
        idChild,
        idEventThread,
        dwmsEventTime,
    ):
        if self._hide_hidden and detect_hidden(hwnd) is not None:
            return

        timestamp = event_time_to_datetime(dwmsEventTime)
        window_name = win32gui.GetWindowText(hwnd).replace("\u200b", "")
        # https://stackoverflow.com/a/48857220
        tid, pid = win32process.GetWindowThreadProcessId(hwnd)

        self.console.print(
            " | ".join(
                [
                    str(x)
                    for x in [
                        timestamp.strftime("%H:%M:%S.%f")[:-3],
                        event_name(event, ranges=False),
                        window_name or None,
                        pid,
                        detect_hidden(hwnd),
                    ]
                    if x is not None
                ],
            )
        )

    def stop(self):
        self.stop_event.set()

    def run(self) -> None:
        # https://learn.microsoft.com/en-us/windows/win32/api/winuser/nc-winuser-wineventproc
        CWinEventProc = WinEventProcType(self._WinEventProc)
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
            while not self.stop_event.is_set():
                win32gui.PumpWaitingMessages()
                self.stop_event.wait(WindowEventWatcher.STOP_EVENT_POLLING_MS / 1000)
        finally:
            for hook in hooks:
                if hook:
                    user32.UnhookWinEvent(hook)
            pythoncom.CoUninitialize()


async def main():
    console = Console()
    watcher = WindowEventWatcher(console)

    watcher.start()
    try:
        while True:
            user_input = await asyncio.to_thread(
                input, "[q: quit, u: toggle user-facing] > "
            )
            user_input = user_input.strip()
            if user_input == "q":
                print("Quitting")
                break
            elif user_input == "u":
                new_status = watcher.toggle_user_facing()
                print(
                    "{status} user facing".format(
                        status="Enabling" if new_status else "Disabling"
                    )
                )
            else:
                print("Unrecognized command")

    finally:
        watcher.stop()
        console.kill()


if __name__ == "__main__":
    asyncio.run(main())
