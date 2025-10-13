# NOTE: Doesn't work because it doesn't catch close events

# pip install comtypes pywin32
import asyncio
import threading

import psutil
import pythoncom

import comtypes
from comtypes.client import CreateObject, GetModule

from experiments.console import Console

# generate wrappers once
GetModule("UIAutomationCore.dll")
from comtypes.gen.UIAutomationClient import (  # CoClasses
    CUIAutomation8,
    IUIAutomationEventHandler,
    IUIAutomationFocusChangedEventHandler,
    IUIAutomationPropertyChangedEventHandler,
    TreeScope_Subtree,
    UIA_BoundingRectanglePropertyId,
    UIA_Window_WindowClosedEventId,
    UIA_Window_WindowOpenedEventId,
)


class UIAWatcher(threading.Thread):
    def __init__(self, console: Console):
        super().__init__(daemon=True)
        self.console = console
        self.stop_evt = threading.Event()

    def stop(self):
        self.stop_evt.set()

    def run(self):
        self.stop_evt.clear()
        console = self.console

        pythoncom.CoInitialize()  # init COM on this thread

        class WindowEvt(comtypes.COMObject):
            _com_interfaces_ = [IUIAutomationEventHandler]

            def HandleAutomationEvent(self, sender, eventId):
                if eventId == UIA_Window_WindowOpenedEventId:
                    name = psutil.Process(sender.CurrentProcessId).name()
                    console.print(f"OPEN: {sender.CurrentProcessId} {name!r}")
                elif eventId == UIA_Window_WindowClosedEventId:
                    # sender may already be invalid here; only read what’s safe
                    pid = getattr(sender, "CurrentProcessId", 0)
                    exe = psutil.Process(pid).exe()
                    console.print(f"CLOSE: {pid} {exe!r}")

        class FocusEvt(comtypes.COMObject):
            _com_interfaces_ = [IUIAutomationFocusChangedEventHandler]

            def HandleFocusChangedEvent(self, sender):
                console.print(
                    f"FOCUS: {sender.CurrentProcessId} {hex(sender.CurrentNativeWindowHandle)}"
                )

        class PropEvt(comtypes.COMObject):
            _com_interfaces_ = [IUIAutomationPropertyChangedEventHandler]

            def HandlePropertyChangedEvent(self, sender, propId, newVal):
                if propId == UIA_BoundingRectanglePropertyId:
                    rect = sender.get_CurrentBoundingRectangle
                    console.print(
                        f"WIN_SIZE: {sender.CurrentProcessId} "
                        f"HWND: {sender.CurrentNativeWindowHandle} "
                        f"Rect: {rect} "
                    )
                return 0

        # instantiate automation (either one works)
        # uia = CreateObject("UIAutomationClient.CUIAutomation")     # returns IUIAutomation
        uia = CreateObject(CUIAutomation8)  # returns IUIAutomation2 but compatible
        root = uia.GetRootElement()

        win_h = WindowEvt()
        focus_h = FocusEvt()
        # prop_h = PropEvt()

        uia.AddAutomationEventHandler(
            UIA_Window_WindowOpenedEventId, root, TreeScope_Subtree, None, win_h
        )
        uia.AddAutomationEventHandler(
            UIA_Window_WindowClosedEventId, root, TreeScope_Subtree, None, win_h
        )
        uia.AddFocusChangedEventHandler(None, focus_h)
        # NOTE: PropEvt is crashing Python; IDK why...
        # uia.AddPropertyChangedEventHandler(
        #     root, TreeScope_Subtree, None, prop_h, (UIA_BoundingRectanglePropertyId,)
        # )

        try:
            while not self.stop_evt.is_set():
                pythoncom.PumpWaitingMessages()
                self.stop_evt.wait(0.01)
        finally:
            uia.RemoveAutomationEventHandler(
                UIA_Window_WindowOpenedEventId, root, win_h
            )
            uia.RemoveAutomationEventHandler(
                UIA_Window_WindowClosedEventId, root, win_h
            )
            uia.RemoveFocusChangedEventHandler(focus_h)
            # uia.RemovePropertyChangedEventHandler(root, prop_h)
            pythoncom.CoUninitialize()


async def main():
    console = Console()
    watcher = UIAWatcher(console)

    watcher.start()
    try:
        while True:
            user_input = await asyncio.to_thread(input, "[q: quit] > ")
            user_input = user_input.strip()
            if user_input == "q":
                print("Quitting")
                break
            else:
                print("Unrecognized command")
    finally:
        watcher.stop()
        console.kill()


if __name__ == "__main__":
    asyncio.run(main())
