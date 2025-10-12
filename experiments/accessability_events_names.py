# https://learn.microsoft.com/en-us/windows/win32/winauto/event-constants
ACCESSABILITY_EVENTS_CONSTANTS = {
    0x8012: "EVENT_OBJECT_ACCELERATORCHANGE",
    # An object's KeyboardShortcut property has changed. Server applications send this event for their accessible objects.
    #
    0x8017: "EVENT_OBJECT_CLOAKED",
    # Sent when a window is cloaked. A cloaked window still exists, but is invisible to the user.
    #
    0x8015: "EVENT_OBJECT_CONTENTSCROLLED",
    # A window object's scrolling has ended. Unlike EVENT_SYSTEM_SCROLLINGEND, this event is associated with the scrolling window. Whether the scrolling is horizontal or vertical scrolling, this event should be sent whenever the scroll action is completed.
    # The hwnd parameter of the WinEventProc callback function describes the scrolling window; the idObject parameter is OBJID_CLIENT, and the idChild parameter is CHILDID_SELF.
    #
    0x8000: "EVENT_OBJECT_CREATE",
    # An object has been created. The system sends this event for the following user interface elements: caret, header control, list-view control, tab control, toolbar control, tree view control, and window object. Server applications send this event for their accessible objects.
    # Before sending the event for the parent object, servers must send it for all of an object's child objects. Servers must ensure that all child objects are fully created and ready to accept IAccessible calls from clients before the parent object sends this event.
    # Because a parent object is created after its child objects, clients must make sure that an object's parent has been created before calling IAccessible::get_accParent, particularly if in-context hook functions are used.
    #
    0x8011: "EVENT_OBJECT_DEFACTIONCHANGE",
    # An object's DefaultAction property has changed. The system sends this event for dialog boxes. Server applications send this event for their accessible objects.
    #
    0x800D: "EVENT_OBJECT_DESCRIPTIONCHANGE",
    # An object's Description property has changed. Server applications send this event for their accessible objects.
    #
    0x8001: "EVENT_OBJECT_DESTROY",
    # An object has been destroyed. The system sends this event for the following user interface elements: caret, header control, list-view control, tab control, toolbar control, tree view control, and window object. Server applications send this event for their accessible objects.
    # Clients assume that all of an object's children are destroyed when the parent object sends this event.
    # After receiving this event, clients do not call an object's IAccessible properties or methods. However, the interface pointer must remain valid as long as there is a reference count on it (due to COM rules), but the UI element may no longer be present. Further calls on the interface pointer may return failure errors; to prevent this, servers create proxy objects and monitor their life spans.
    #
    0x8021: "EVENT_OBJECT_DRAGSTART",
    # The user started to drag an element. The hwnd, idObject, and idChild parameters of the WinEventProc callback function identify the object being dragged.
    #
    0x8022: "EVENT_OBJECT_DRAGCANCEL",
    # The user has ended a drag operation before dropping the dragged element on a drop target. The hwnd, idObject, and idChild parameters of the WinEventProc callback function identify the object being dragged.
    #
    0x8023: "EVENT_OBJECT_DRAGCOMPLETE",
    # The user dropped an element on a drop target. The hwnd, idObject, and idChild parameters of the WinEventProc callback function identify the object being dragged.
    #
    0x8024: "EVENT_OBJECT_DRAGENTER",
    # The user dragged an element into a drop target's boundary. The hwnd, idObject, and idChild parameters of the WinEventProc callback function identify the drop target.
    #
    0x8025: "EVENT_OBJECT_DRAGLEAVE",
    # The user dragged an element out of a drop target's boundary. The hwnd, idObject, and idChild parameters of the WinEventProc callback function identify the drop target.
    #
    0x8026: "EVENT_OBJECT_DRAGDROPPED",
    # The user dropped an element on a drop target. The hwnd, idObject, and idChild parameters of the WinEventProc callback function identify the drop target.
    #
    0x80FF: "EVENT_OBJECT_END",
    # The highest object event value.
    #
    0x8005: "EVENT_OBJECT_FOCUS",
    # An object has received the keyboard focus. The system sends this event for the following user interface elements: list-view control, menu bar, pop-up menu, switch window, tab control, tree view control, and window object. Server applications send this event for their accessible objects.
    # The hwnd parameter of the WinEventProc callback function identifies the window that receives the keyboard focus.
    #
    0x8010: "EVENT_OBJECT_HELPCHANGE",
    # An object's Help property has changed. Server applications send this event for their accessible objects.
    #
    0x8003: "EVENT_OBJECT_HIDE",
    # An object is hidden. The system sends this event for the following user interface elements: caret and cursor. Server applications send this event for their accessible objects.
    # When this event is generated for a parent object, all child objects are already hidden. Server applications do not send this event for the child objects.
    # Hidden objects include the STATE_SYSTEM_INVISIBLE flag; shown objects do not include this flag. The EVENT_OBJECT_HIDE event also indicates that the STATE_SYSTEM_INVISIBLE flag is set. Therefore, servers do not send the EVENT_OBJECT_STATECHANGE event in this case.
    #
    0x8020: "EVENT_OBJECT_HOSTEDOBJECTSINVALIDATED",
    # A window that hosts other accessible objects has changed the hosted objects. A client might need to query the host window to discover the new hosted objects, especially if the client has been monitoring events from the window. A hosted object is an object from an accessibility framework (MSAA or UI Automation) that is different from that of the host. Changes in hosted objects that are from the same framework as the host should be handed with the structural change events, such as EVENT_OBJECT_CREATE for MSAA. For more info see comments within winuser.h.
    #
    0x8028: "EVENT_OBJECT_IME_HIDE",
    # An IME window has become hidden.
    #
    0x8027: "EVENT_OBJECT_IME_SHOW",
    # An IME window has become visible.
    #
    0x8029: "EVENT_OBJECT_IME_CHANGE",
    # The size or position of an IME window has changed.
    #
    0x8013: "EVENT_OBJECT_INVOKED",
    # An object has been invoked; for example, the user has clicked a button. This event is supported by common controls and is used by UI Automation.
    # For this event, the hwnd, ID, and idChild parameters of the WinEventProc callback function identify the item that is invoked.
    #
    0x8019: "EVENT_OBJECT_LIVEREGIONCHANGED",
    # An object that is part of a live region has changed. A live region is an area of an application that changes frequently and/or asynchronously.
    #
    0x800B: "EVENT_OBJECT_LOCATIONCHANGE",
    # An object has changed location, shape, or size. The system sends this event for the following user interface elements: caret and window objects. Server applications send this event for their accessible objects.
    # This event is generated in response to a change in the top-level object within the object hierarchy; it is not generated for any children that the object might have. For example, if the user resizes a window, the system sends this notification for the window, but not for the menu bar, title bar, scroll bar, or other objects that have also changed.
    # The system does not send this event for every non-floating child window when the parent moves. However, if an application explicitly resizes child windows as a result of resizing the parent window, the system sends multiple events for the resized children.
    # If an object's State property is set to STATE_SYSTEM_FLOATING, the server sends EVENT_OBJECT_LOCATIONCHANGE whenever the object changes location. If an object does not have this state, servers only trigger this event when the object moves in relation to its parent. For this event notification, the idChild parameter of the WinEventProc callback function identifies the child object that has changed.
    #
    0x800C: "EVENT_OBJECT_NAMECHANGE",
    # An object's Name property has changed. The system sends this event for the following user interface elements: check box, cursor, list-view control, push button, radio button, status bar control, tree view control, and window object. Server applications send this event for their accessible objects.
    #
    0x800F: "EVENT_OBJECT_PARENTCHANGE",
    # An object has a new parent object. Server applications send this event for their accessible objects.
    #
    0x8004: "EVENT_OBJECT_REORDER",
    # A container object has added, removed, or reordered its children. The system sends this event for the following user interface elements: header control, list-view control, toolbar control, and window object. Server applications send this event as appropriate for their accessible objects.
    # For example, this event is generated by a list-view object when the number of child elements or the order of the elements changes. This event is also sent by a parent window when the Z-order for the child windows changes.
    #
    0x8006: "EVENT_OBJECT_SELECTION",
    # The selection within a container object has changed. The system sends this event for the following user interface elements: list-view control, tab control, tree view control, and window object. Server applications send this event for their accessible objects.
    # This event signals a single selection: either a child is selected in a container that previously did not contain any selected children, or the selection has changed from one child to another.
    # The hwnd and idObject parameters of the WinEventProc callback function describe the container; the idChild parameter identifies the object that is selected. If the selected child is a window that also contains objects, the idChild parameter is OBJID_WINDOW.
    #
    0x8007: "EVENT_OBJECT_SELECTIONADD",
    # A child within a container object has been added to an existing selection. The system sends this event for the following user interface elements: list box, list-view control, and tree view control. Server applications send this event for their accessible objects.
    # The hwnd and idObject parameters of the WinEventProc callback function describe the container. The idChild parameter is the child that is added to the selection.
    #
    0x8008: "EVENT_OBJECT_SELECTIONREMOVE",
    # An item within a container object has been removed from the selection. The system sends this event for the following user interface elements: list box, list-view control, and tree view control. Server applications send this event for their accessible objects.
    # This event signals that a child is removed from an existing selection.
    # The hwnd and idObject parameters of the WinEventProc callback function describe the container; the idChild parameter identifies the child that has been removed from the selection.
    #
    0x8009: "EVENT_OBJECT_SELECTIONWITHIN",
    # Numerous selection changes have occurred within a container object. The system sends this event for list boxes; server applications send it for their accessible objects.
    # This event is sent when the selected items within a control have changed substantially. The event informs the client that many selection changes have occurred, and it is sent instead of several EVENT_OBJECT_SELECTIONADD or EVENT_OBJECT_SELECTIONREMOVE events. The client queries for the selected items by calling the container object's IAccessible::get_accSelection method and enumerating the selected items.
    # For this event notification, the hwnd and idObject parameters of the WinEventProc callback function describe the container in which the changes occurred.
    #
    0x8002: "EVENT_OBJECT_SHOW",
    # A hidden object is shown. The system sends this event for the following user interface elements: caret, cursor, and window object. Server applications send this event for their accessible objects.
    # Clients assume that when this event is sent by a parent object, all child objects are already displayed. Therefore, server applications do not send this event for the child objects.
    # Hidden objects include the STATE_SYSTEM_INVISIBLE flag; shown objects do not include this flag. The EVENT_OBJECT_SHOW event also indicates that the STATE_SYSTEM_INVISIBLE flag is cleared. Therefore, servers do not send the EVENT_OBJECT_STATECHANGE event in this case.
    #
    0x800A: "EVENT_OBJECT_STATECHANGE",
    # An object's state has changed. The system sends this event for the following user interface elements: check box, combo box, header control, push button, radio button, scroll bar, toolbar control, tree view control, up-down control, and window object. Server applications send this event for their accessible objects.
    # For example, a state change occurs when a button object is clicked or released, or when an object is enabled or disabled.
    # For this event notification, the idChild parameter of the WinEventProc callback function identifies the child object whose state has changed.
    #
    0x8030: "EVENT_OBJECT_TEXTEDIT_CONVERSIONTARGETCHANGED",
    # The conversion target within an IME composition has changed. The conversion target is the subset of the IME composition which is actively selected as the target for user-initiated conversions.
    #
    0x8014: "EVENT_OBJECT_TEXTSELECTIONCHANGED",
    # An object's text selection has changed. This event is supported by common controls and is used by UI Automation.
    # The hwnd, ID, and idChild parameters of the WinEventProc callback function describe the item that is contained in the updated text selection.
    #
    0x8018: "EVENT_OBJECT_UNCLOAKED",
    # Sent when a window is uncloaked. A cloaked window still exists, but is invisible to the user.
    #
    0x800E: "EVENT_OBJECT_VALUECHANGE",
    # An object's Value property has changed. The system sends this event for the user interface elements that include the scroll bar and the following controls: edit, header, hot key, progress bar, slider, and up-down. Server applications send this event for their accessible objects.
    #
    0x0002: "EVENT_SYSTEM_ALERT",
    # An alert has been generated. Server applications should not send this event.
    #
    0x8016: "EVENT_SYSTEM_ARRANGMENTPREVIEW",
    # A preview rectangle is being displayed.
    #
    0x0009: "EVENT_SYSTEM_CAPTUREEND",
    # A window has lost mouse capture. This event is sent by the system, never by servers.
    #
    0x0008: "EVENT_SYSTEM_CAPTURESTART",
    # A window has received mouse capture. This event is sent by the system, never by servers.
    #
    0x000D: "EVENT_SYSTEM_CONTEXTHELPEND",
    # A window has exited context-sensitive Help mode. This event is not sent consistently by the system.
    #
    0x000C: "EVENT_SYSTEM_CONTEXTHELPSTART",
    # A window has entered context-sensitive Help mode. This event is not sent consistently by the system.
    #
    0x0020: "EVENT_SYSTEM_DESKTOPSWITCH",
    # The active desktop has been switched.
    #
    0x0011: "EVENT_SYSTEM_DIALOGEND",
    # A dialog box has been closed. The system sends this event for standard dialog boxes; servers send it for custom dialog boxes. This event is not sent consistently by the system.
    #
    0x0010: "EVENT_SYSTEM_DIALOGSTART",
    # A dialog box has been displayed. The system sends this event for standard dialog boxes, which are created using resource templates or Win32 dialog box functions. Servers send this event for custom dialog boxes, which are windows that function as dialog boxes but are not created in the standard way.
    # This event is not sent consistently by the system.
    #
    0x000F: "EVENT_SYSTEM_DRAGDROPEND",
    # An application is about to exit drag-and-drop mode. Applications that support drag-and-drop operations must send this event; the system does not send this event.
    #
    0x000E: "EVENT_SYSTEM_DRAGDROPSTART",
    # An application is about to enter drag-and-drop mode. Applications that support drag-and-drop operations must send this event because the system does not send it.
    #
    0x00FF: "EVENT_SYSTEM_END",
    # The highest system event value.
    #
    0x0003: "EVENT_SYSTEM_FOREGROUND",
    # The foreground window has changed. The system sends this event even if the foreground window has changed to another window in the same thread. Server applications never send this event.
    # For this event, the WinEventProc callback function's hwnd parameter is the handle to the window that is in the foreground, the idObject parameter is OBJID_WINDOW, and the idChild parameter is CHILDID_SELF.
    #
    0x0007: "EVENT_SYSTEM_MENUPOPUPEND",
    # A pop-up menu has been closed. The system sends this event for standard menus; servers send it for custom menus.
    # When a pop-up menu is closed, the client receives this message, and then the EVENT_SYSTEM_MENUEND event.
    # This event is not sent consistently by the system.
    #
    0x0006: "EVENT_SYSTEM_MENUPOPUPSTART",
    # A pop-up menu has been displayed. The system sends this event for standard menus, which are identified by HMENU, and are created using menu-template resources or Win32 menu functions. Servers send this event for custom menus, which are user interface elements that function as menus but are not created in the standard way. This event is not sent consistently by the system.
    #
    0x0005: "EVENT_SYSTEM_MENUEND",
    # A menu from the menu bar has been closed. The system sends this event for standard menus; servers send it for custom menus.
    # For this event, the WinEventProc callback function's hwnd, idObject, and idChild parameters refer to the control that contains the menu bar or the control that activates the context menu. The hwnd parameter is the handle to the window that is related to the event. The idObject parameter is OBJID_MENU or OBJID_SYSMENU for a menu, or OBJID_WINDOW for a pop-up menu. The idChild parameter is CHILDID_SELF.
    #
    0x0004: "EVENT_SYSTEM_MENUSTART",
    # A menu item on the menu bar has been selected. The system sends this event for standard menus, which are identified by HMENU, created using menu-template resources or Win32 menu API elements. Servers send this event for custom menus, which are user interface elements that function as menus but are not created in the standard way.
    # For this event, the WinEventProc callback function's hwnd, idObject, and idChild parameters refer to the control that contains the menu bar or the control that activates the context menu. The hwnd parameter is the handle to the window related to the event. The idObject parameter is OBJID_MENU or OBJID_SYSMENU for a menu, or OBJID_WINDOW for a pop-up menu. The idChild parameter is CHILDID_SELF.
    # The system triggers more than one EVENT_SYSTEM_MENUSTART event that does not always correspond with the EVENT_SYSTEM_MENUEND event.
    #
    0x0017: "EVENT_SYSTEM_MINIMIZEEND",
    # A window object is about to be restored. This event is sent by the system, never by servers.
    #
    0x0016: "EVENT_SYSTEM_MINIMIZESTART",
    # A window object is about to be minimized. This event is sent by the system, never by servers.
    #
    0x000B: "EVENT_SYSTEM_MOVESIZEEND",
    # The movement or resizing of a window has finished. This event is sent by the system, never by servers.
    #
    0x000A: "EVENT_SYSTEM_MOVESIZESTART",
    # A window is being moved or resized. This event is sent by the system, never by servers.
    #
    0x0013: "EVENT_SYSTEM_SCROLLINGEND",
    # Scrolling has ended on a scroll bar. This event is sent by the system for standard scroll bar controls and for scroll bars that are attached to a window. Servers send this event for custom scroll bars, which are user interface elements that function as scroll bars but are not created in the standard way.
    # The idObject parameter that is sent to the WinEventProc callback function is OBJID_HSCROLL for horizontal scroll bars, and OBJID_VSCROLL for vertical scroll bars.
    #
    0x0012: "EVENT_SYSTEM_SCROLLINGSTART",
    # Scrolling has started on a scroll bar. The system sends this event for standard scroll bar controls and for scroll bars attached to a window. Servers send this event for custom scroll bars, which are user interface elements that function as scroll bars but are not created in the standard way.
    # The idObject parameter that is sent to the WinEventProc callback function is OBJID_HSCROLL for horizontal scrolls bars, and OBJID_VSCROLL for vertical scroll bars.
    #
    0x0001: "EVENT_SYSTEM_SOUND",
    # A sound has been played. The system sends this event when a system sound, such as one for a menu, is played even if no sound is audible (for example, due to the lack of a sound file or a sound card). Servers send this event whenever a custom UI element generates a sound.
    # For this event, the WinEventProc callback function receives the OBJID_SOUND value as the idObject parameter.
    #
    0x0015: "EVENT_SYSTEM_SWITCHEND",
    # The user has released ALT+TAB. This event is sent by the system, never by servers. The hwnd parameter of the WinEventProc callback function identifies the window to which the user has switched.
    # If only one application is running when the user presses ALT+TAB, the system sends this event without a corresponding EVENT_SYSTEM_SWITCHSTART event.
    #
    0x0014: "EVENT_SYSTEM_SWITCHSTART",
    # The user has pressed ALT+TAB, which activates the switch window. This event is sent by the system, never by servers. The hwnd parameter of the WinEventProc callback function identifies the window to which the user is switching.
    # If only one application is running when the user presses ALT+TAB, the system sends an EVENT_SYSTEM_SWITCHEND event without a corresponding EVENT_SYSTEM_SWITCHSTART event.
}


def event_name(event: int, ranges: bool = False):
    out = ""
    # RANGES
    if ranges:
        if event >= 0xA000 or event <= 0xAFFF:
            out += "EVENT_AIA_START / EVENT_AIA_END | "
            # The range of WinEvent constant values specified by the Accessibility Interoperability Alliance (AIA) for use across the industry. For more information, see Allocation of WinEvent IDs.
            #
        if event >= 0x00000001 or event <= 0x7FFFFFFF:
            out += "EVENT_MIN / EVENT_MAX | "
            # The lowest and highest possible event values.
            #
        if event >= 0x0101 or event <= 0x01FF:
            out += "EVENT_OEM_DEFINED_START / EVENT_OEM_DEFINED_END | "
            # The range of event constant values reserved for OEMs. For more information, see Allocation of WinEvent IDs.
            #
        if event >= 0x4E00 or event <= 0x4EFF:
            out += "EVENT_UIA_EVENTID_START / EVENT_UIA_EVENTID_END | "
            # The range of event constant values reserved for UI Automation event identifiers. For more information, see Allocation of WinEvent IDs.
            #
        if event >= 0x7500 or event <= 0x75FF:
            out += "EVENT_UIA_PROPID_START / EVENT_UIA_PROPID_END | "
            # The range of event constant values reserved for UI Automation property-changed event identifiers. For more information, see Allocation of WinEvent IDs.
            #

    out += ACCESSABILITY_EVENTS_CONSTANTS[event]
    return out
