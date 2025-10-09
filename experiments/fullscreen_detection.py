# fullscreen_probe_dedup.py
import time
from ctypes import windll, wintypes, byref, Structure, sizeof
import ctypes
import psutil
import win32gui
import win32process
from pathlib import Path

user32 = windll.user32
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

class RECT(Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
    def to_tuple(self): return (self.left, self.top, self.right, self.bottom)
    def width(self): return self.right - self.left
    def height(self): return self.bottom - self.top

GWL_STYLE   = -16
GWL_EXSTYLE = -20
WS_VISIBLE  = 0x10000000
WS_POPUP    = 0x80000000
WS_CAPTION  = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZE = 0x20000000
WS_MAXIMIZE = 0x01000000

DWMWA_EXTENDED_FRAME_BOUNDS = 9
MONITOR_DEFAULTTONEAREST = 2
GA_ROOT = 2

def get_rect(hwnd):
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return RECT(l, t, r, b)

def get_client_rect_screen(hwnd):
    r = RECT()
    user32.GetClientRect(hwnd, byref(r))
    pt = wintypes.POINT()
    user32.ClientToScreen(hwnd, byref(pt))
    return RECT(pt.x, pt.y, pt.x + r.right - r.left, pt.y + r.bottom - r.top)

def get_dwm_frame_rect(hwnd):
    r = RECT()
    hr = dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
        byref(r),
        wintypes.DWORD(sizeof(r)),
    )
    return r if hr == 0 else None  # S_OK == 0

def get_monitor_rect(hwnd):
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD)]
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(hmon, byref(mi))
    return mi.rcMonitor, mi.rcWork

def get_dpi(hwnd):
    try:
        return user32.GetDpiForWindow(hwnd)
    except AttributeError:
        hdc = user32.GetDC(0)
        LOGPIXELSX = 88
        dpi = windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
        user32.ReleaseDC(0, hdc)
        return dpi

def style_flags(hwnd):
    s = win32gui.GetWindowLong(hwnd, GWL_STYLE)
    ex = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
    flags = []
    for bit, name in [(WS_VISIBLE, "VISIBLE"), (WS_POPUP, "POPUP"),
                      (WS_CAPTION, "CAPTION"), (WS_THICKFRAME, "THICKFRAME"),
                      (WS_MINIMIZE, "MINIMIZE"), (WS_MAXIMIZE, "MAXIMIZE")]:
        if s & bit: flags.append(name)
    return s, ex, tuple(flags)

def eq_within(a: RECT, b: RECT, tol: int):
    return (abs(a.left - b.left)   <= tol and
            abs(a.top - b.top)     <= tol and
            abs(a.right - b.right) <= tol and
            abs(a.bottom - b.bottom)<= tol)

def deltas(a: RECT, b: RECT):
    return (a.left - b.left, a.top - b.top, a.right - b.right, a.bottom - b.bottom)

def main():
    user32.SetProcessDPIAware()
    prev_snapshot = None
    print("Polling... Ctrl+C to stop")
    while True:
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                time.sleep(0.25); continue

            # ensure top-level window
            hwnd_root = user32.GetAncestor(hwnd, GA_ROOT)

            win_r = get_rect(hwnd_root)
            cli_r = get_client_rect_screen(hwnd_root)
            frm_r = get_dwm_frame_rect(hwnd_root)
            mon_r, work_r = get_monitor_rect(hwnd_root)
            dpi = get_dpi(hwnd_root)
            tol = max(1, int(round(dpi / 96)))

            _, pid = win32process.GetWindowThreadProcessId(hwnd_root)
            try:
                p = psutil.Process(pid)
                name = p.name()
                exe = p.exe()
            except psutil.NoSuchProcess:
                name = "NoSuchProcess"
                exe = "NoSuchProcess"

            s, ex, flags = style_flags(hwnd_root)

            # snapshot without time
            snapshot = (
                int(hwnd_root), int(pid), name, exe,
                win_r.to_tuple(), cli_r.to_tuple(),
                (frm_r.to_tuple() if frm_r else None),
                mon_r.to_tuple(), work_r.to_tuple(),
                int(dpi), int(tol), int(s), int(ex), flags
            )

            if snapshot == prev_snapshot:
                time.sleep(0.25)
                continue
            prev_snapshot = snapshot

            eq_win   = eq_within(win_r, mon_r, tol)
            eq_frame = (eq_within(frm_r, mon_r, tol) if frm_r else None)
            eq_cli   = eq_within(cli_r, mon_r, tol)

            print(
                f"t={time.strftime('%H:%M:%S')} hwnd=0x{hwnd_root:08X} pid={pid} "
                f"name={name} exe={exe}\n"
                f"  monitor   : {mon_r.to_tuple()} {mon_r.width()}x{mon_r.height()} "
                f"(work={work_r.to_tuple()}) dpi={dpi} tol={tol}\n"
                f"  win rect  : {win_r.to_tuple()} {win_r.width()}x{win_r.height()} "
                f"Δ={deltas(win_r, mon_r)} eq≈mon={eq_win}\n"
                f"  client    : {cli_r.to_tuple()} {cli_r.width()}x{cli_r.height()} "
                f"Δ={deltas(cli_r, mon_r)} eq≈mon={eq_cli}\n"
                f"  frame ext : {(frm_r.to_tuple() if frm_r else None)} "
                f"{(str(frm_r.width())+'x'+str(frm_r.height())) if frm_r else ''} "
                f"Δ={(deltas(frm_r, mon_r) if frm_r else None)} eq≈mon={eq_frame}\n"
                f"  style     : style=0x{s:08X} ex=0x{ex:08X} flags={list(flags)}\n"
            )
            time.sleep(0.25)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("err:", repr(e))
            time.sleep(0.25)

if __name__ == "__main__":
    main()
