import ctypes
import ctypes.wintypes as wt
import win32gui

import win32api
import win32con

# ---- constants ----
WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RIDEV_INPUTSINK = 0x00000100

# ---- RAWINPUT structs ----
class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wt.DWORD), ("dwSize", wt.DWORD), ("hDevice", wt.HANDLE), ("wParam", wt.WPARAM)]

class _RAWMOUSE_Buttons(ctypes.Structure):
    _fields_ = [("usButtonFlags", wt.USHORT), ("usButtonData", wt.USHORT)]
class RAWMOUSE_BUTTONS(ctypes.Union):
    _fields_ = [("ulButtons", wt.ULONG), ("s", _RAWMOUSE_Buttons)]

class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("usFlags", wt.USHORT), ("u", RAWMOUSE_BUTTONS), ("ulRawButtons", wt.ULONG),
                ("lLastX", wt.LONG), ("lLastY", wt.LONG), ("ulExtraInformation", wt.ULONG)]

class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", wt.USHORT), ("Flags", wt.USHORT), ("Reserved", wt.USHORT),
                ("VKey", wt.USHORT), ("Message", wt.UINT), ("ExtraInformation", wt.ULONG)]

class RAWHID(ctypes.Structure):
    _fields_ = [("dwSizeHid", wt.DWORD), ("dwCount", wt.DWORD), ("bRawData", wt.BYTE * 1)]

class RAWINPUT_UNION(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD), ("hid", RAWHID)]

class RAWINPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("header", RAWINPUTHEADER), ("data", RAWINPUT_UNION)]

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT), ("dwFlags", wt.DWORD), ("hwndTarget", wt.HWND)]

# ---- wndproc ----
def wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_INPUT:
        size = wt.UINT(0)
        ctypes.windll.user32.GetRawInputData(ctypes.c_void_p(lparam), RID_INPUT, None, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        buf = (ctypes.c_byte * size.value)()
        if ctypes.windll.user32.GetRawInputData(ctypes.c_void_p(lparam), RID_INPUT, ctypes.byref(buf), ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER)) == size.value:
            ri = ctypes.cast(ctypes.byref(buf), ctypes.POINTER(RAWINPUT)).contents
            if ri.header.dwType == RIM_TYPEMOUSE:
                dx, dy = ri.mouse.lLastX, ri.mouse.lLastY
                bf = ri.mouse.s.usButtonFlags
                if dx or dy or bf:
                    print(f"MOUSE dx={dx} dy={dy} buttons=0x{bf:04x}")
            elif ri.header.dwType == RIM_TYPEKEYBOARD:
                if ri.keyboard.Message in (win32con.WM_KEYDOWN, win32con.WM_SYSKEYDOWN):
                    print(f"KEY vkey={ri.keyboard.VKey}")
        return 0
    if msg == win32con.WM_CLOSE:
        win32gui.DestroyWindow(hwnd); return 0
    if msg == win32con.WM_DESTROY:
        win32gui.PostQuitMessage(0); return 0
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

if __name__ == "__main__":
    hinst = win32api.GetModuleHandle(None)
    hwnd = win32gui.CreateWindow("Static", "", 0, 0, 0, 0, 0, 0, 0, hinst, None)  # built-in class, no custom WNDCLASS

    old_wndproc = win32gui.SetWindowLong(hwnd, win32con.GWL_WNDPROC, wndproc)   # subclass to receive WM_INPUT
    _keep_refs = (wndproc, old_wndproc)

    rids = (RAWINPUTDEVICE * 2)()
    rids[0].usUsagePage, rids[0].usUsage = 0x01, 0x02
    rids[1].usUsagePage, rids[1].usUsage = 0x01, 0x06
    for i in (0, 1):
        rids[i].dwFlags = RIDEV_INPUTSINK
        rids[i].hwndTarget = hwnd
    if not ctypes.windll.user32.RegisterRawInputDevices(ctypes.byref(rids), 2, ctypes.sizeof(RAWINPUTDEVICE)):
        raise SystemExit("RegisterRawInputDevices failed")

    win32gui.PumpMessages()
