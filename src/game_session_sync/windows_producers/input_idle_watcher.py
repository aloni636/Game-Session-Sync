# NOTE: I use RAWINPUTDEVICE with INPUTSINK instead of user32.GetLastInputInfo()
#       because games keep spamming user32.GetLastInputInfo(), so AFK detection must intercept
#       lower level **hardware** input

import asyncio
import logging
import time

import ctypes
import ctypes.wintypes as wt
import win32gui

import win32api
import win32con

from .types import EventBus, InputActiveEvent, InputIdleEvent

# ---- constants ----
WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RIDEV_INPUTSINK = 0x00000100


# ---- RAWINPUT structs ----
class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wt.DWORD),
        ("dwSize", wt.DWORD),
        ("hDevice", wt.HANDLE),
        ("wParam", wt.WPARAM),
    ]


class _RAWMOUSE_Buttons(ctypes.Structure):
    _fields_ = [("usButtonFlags", wt.USHORT), ("usButtonData", wt.USHORT)]


class RAWMOUSE_BUTTONS(ctypes.Union):
    _fields_ = [("ulButtons", wt.ULONG), ("s", _RAWMOUSE_Buttons)]


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("usFlags", wt.USHORT),
        ("u", RAWMOUSE_BUTTONS),
        ("ulRawButtons", wt.ULONG),
        ("lLastX", wt.LONG),
        ("lLastY", wt.LONG),
        ("ulExtraInformation", wt.ULONG),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [
        ("MakeCode", wt.USHORT),
        ("Flags", wt.USHORT),
        ("Reserved", wt.USHORT),
        ("VKey", wt.USHORT),
        ("Message", wt.UINT),
        ("ExtraInformation", wt.ULONG),
    ]


class RAWHID(ctypes.Structure):
    _fields_ = [
        ("dwSizeHid", wt.DWORD),
        ("dwCount", wt.DWORD),
        ("bRawData", wt.BYTE * 1),
    ]


class RAWINPUT_UNION(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD), ("hid", RAWHID)]


class RAWINPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("header", RAWINPUTHEADER), ("data", RAWINPUT_UNION)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wt.USHORT),
        ("usUsage", wt.USHORT),
        ("dwFlags", wt.DWORD),
        ("hwndTarget", wt.HWND),
    ]


class InputIdleWatcher:
    def __init__(self, queue: EventBus, max_idle_seconds: float) -> None:
        self.queue = queue
        self.max_idle_seconds = max_idle_seconds
        self._thread_task: asyncio.Task | None = None
        self._hwnd: int | None = None
        self.log = logging.getLogger(self.__class__.__name__)

    def wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            size = wt.UINT(0)
            ctypes.windll.user32.GetRawInputData(
                ctypes.c_void_p(lparam),
                RID_INPUT,
                None,
                ctypes.byref(size),
                ctypes.sizeof(RAWINPUTHEADER),
            )
            buf = (ctypes.c_byte * size.value)()
            if (
                ctypes.windll.user32.GetRawInputData(
                    ctypes.c_void_p(lparam),
                    RID_INPUT,
                    ctypes.byref(buf),
                    ctypes.byref(size),
                    ctypes.sizeof(RAWINPUTHEADER),
                )
                == size.value
            ):
                ri = ctypes.cast(ctypes.byref(buf), ctypes.POINTER(RAWINPUT)).contents
                if ri.header.dwType == RIM_TYPEMOUSE:
                    dx, dy = ri.mouse.lLastX, ri.mouse.lLastY
                    bf = ri.mouse.s.usButtonFlags
                    if dx or dy or bf:
                        # self.log.debug(f"MOUSE dx={dx} dy={dy} buttons=0x{bf:04x}")
                        asyncio.run_coroutine_threadsafe(
                            self._handle_raw_input(), self.loop
                        )

                elif ri.header.dwType == RIM_TYPEKEYBOARD:
                    if ri.keyboard.Message in (
                        win32con.WM_KEYDOWN,
                        win32con.WM_SYSKEYDOWN,
                    ):
                        # self.log.debug(f"KEY vkey={ri.keyboard.VKey}")
                        asyncio.run_coroutine_threadsafe(
                            self._handle_raw_input(), self.loop
                        )
            return 0
        if msg == win32con.WM_CLOSE:
            win32gui.DestroyWindow(hwnd)
            return 0
        if msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    async def _emit_idle(self):
        await asyncio.sleep(self.max_idle_seconds)
        self.queue.put_nowait(InputIdleEvent())

    async def _handle_raw_input(self):
        # _idle_task is done, meaning InputIdleEvent was emitted and InputActiveEvent is needed
        if self._idle_task.done():
            self.queue.put_nowait(InputActiveEvent())

        self._idle_task.cancel()
        self._idle_task = asyncio.create_task(self._emit_idle())
        self._last_input_ts = time.perf_counter()

    def _thread_run(self) -> None:
        hinst = win32api.GetModuleHandle(None)
        hwnd = win32gui.CreateWindow(
            "Static", "", 0, 0, 0, 0, 0, 0, 0, hinst, None
        )  # built-in class, no custom WNDCLASS
        self._hwnd = hwnd
        # each access self.windproc creates a new callable object,
        # so we need to preserve this exact object from getting nuked by the GC
        self._wndproc_ref = self.wndproc
        # subclass Static window class by overriding WindowProc
        win32gui.SetWindowLong(hwnd, win32con.GWL_WNDPROC, self._wndproc_ref)

        rids = (RAWINPUTDEVICE * 2)()
        rids[0].usUsagePage, rids[0].usUsage = 0x01, 0x02
        rids[1].usUsagePage, rids[1].usUsage = 0x01, 0x06
        for i in (0, 1):
            rids[i].dwFlags = RIDEV_INPUTSINK
            rids[i].hwndTarget = hwnd
        if not ctypes.windll.user32.RegisterRawInputDevices(
            ctypes.byref(rids), 2, ctypes.sizeof(RAWINPUTDEVICE)
        ):
            raise RuntimeError("RegisterRawInputDevices failed")

        win32gui.PumpMessages()

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self._idle_task = asyncio.create_task(self._emit_idle())
        self._last_input_ts = time.perf_counter()

        self._thread_task = asyncio.create_task(asyncio.to_thread(self._thread_run))

    async def stop(self) -> None:
        if self._hwnd is not None:
            win32api.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
        if self._thread_task:
            await self._thread_task


async def _main():
    from ..log_helpers import Console, setup_test_logging

    console = Console()
    setup_test_logging(console, logging.INFO)

    queue = EventBus()
    watcher = InputIdleWatcher(queue, 3)

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
