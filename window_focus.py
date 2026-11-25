"""Find an app's window and bring it to the front (measured 15/15 in the slice 1.0 spike)."""

from __future__ import annotations

import ctypes
import re
import time
from ctypes import wintypes
from pathlib import Path

# app name (lower case) -> (exe name, title word). WhatsApp runs as a Chrome app window, so it is found by its exact title.
WINDOWS = {
    "slack": ("slack.exe", None),
    "t3 code": ("t3 code (nightly).exe", None),
    "claude": ("claude.exe", None),
    "chatgpt": ("chatgpt.exe", None),
    "whatsapp": (None, "WhatsApp"),
    "terminal": ("windowsterminal.exe", None),
    "chrome": ("chrome.exe", None),
}
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.IsWindowVisible.argtypes = (wintypes.HWND,)
_user32.IsIconic.argtypes = (wintypes.HWND,)
_user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
_user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
_user32.BringWindowToTop.argtypes = (wintypes.HWND,)
_user32.SwitchToThisWindow.argtypes = (wintypes.HWND, wintypes.BOOL)
_user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
_user32.AllowSetForegroundWindow.argtypes = (wintypes.DWORD,)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD

def title_matches(word: str, title: str) -> bool:
    """The window is the app itself: its title is just the word, maybe with an unread count ("(3) WhatsApp").
    A browser tab adds " - Google Chrome" and never matches. WhatsApp's window is a Chrome app window, so its exe
    cannot tell it from a Chrome tab."""
    return re.fullmatch(rf"(\(\d+\) )?{re.escape(word)}", title) is not None


_ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _thread_of(hwnd) -> int:
    return _user32.GetWindowThreadProcessId(hwnd, None) if hwnd else 0


def _exe_name(hwnd) -> str:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = _kernel32.OpenProcess(0x1000, False, pid.value)
    if not process:
        return ""
    try:
        path = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(path))
        if _kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
            return Path(path.value).name.casefold()
    finally:
        _kernel32.CloseHandle(process)
    return ""


def list_windows(exe: str | None, title_word: str | None = None, limit: int | None = None) -> list[int]:
    """Visible, titled top-level windows of that exe (or with that word in the title), up to `limit`."""
    found: list[int] = []

    def visit(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(hwnd, title, 256)
        if not title.value:
            return True
        if (exe and _exe_name(hwnd) == exe) or (title_word and title_matches(title_word, title.value)):
            found.append(int(hwnd))
            return limit is None or len(found) < limit
        return True

    _user32.EnumWindows(_ENUM(visit), 0)
    return found


def find_window(exe: str | None, title_word: str | None = None) -> int | None:
    found = list_windows(exe, title_word, limit=1)
    return found[0] if found else None


def bring_to_front(hwnd: int, timeout: float = 1.5) -> bool:
    """Attach to the foreground and target threads, raise the window, poll until it is in front."""
    deadline = time.monotonic() + timeout
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    me = _kernel32.GetCurrentThreadId()
    while True:
        threads = {_thread_of(_user32.GetForegroundWindow()), _thread_of(hwnd)} - {0, me}
        for thread in threads:
            _user32.AttachThreadInput(me, thread, True)
        try:
            _user32.AllowSetForegroundWindow(0xFFFFFFFF)  # ASFW_ANY
            _user32.SetForegroundWindow(hwnd)
            _user32.BringWindowToTop(hwnd)
            _user32.SwitchToThisWindow(hwnd, True)
        finally:
            for thread in threads:
                _user32.AttachThreadInput(me, thread, False)
        time.sleep(0.03)
        if (_user32.GetForegroundWindow() or 0) == hwnd:
            return True
        if time.monotonic() >= deadline:
            return False


def is_foreground(hwnd: int) -> bool:
    """True only when the window in front right now is exactly that window."""
    return bool(hwnd) and (_user32.GetForegroundWindow() or 0) == hwnd


def focus_app(name: str, find=find_window, bring=bring_to_front, timeout: float = 10.0,
              sleep=time.sleep, clock=time.monotonic) -> int | None:
    """Wait up to `timeout` s for the app's window, then bring it to the front. Its handle only when it is."""
    exe, word = WINDOWS.get(name.casefold(), (f"{name.casefold()}.exe", None))
    deadline = clock() + timeout
    while True:
        hwnd = find(exe, word)
        if hwnd:
            return hwnd if bring(hwnd) else None
        if clock() >= deadline:
            return None
        sleep(0.25)


def focus_new(name: str, start, find=list_windows, bring=bring_to_front, timeout: float = 10.0,
              sleep=time.sleep, clock=time.monotonic) -> int | None:
    """Run start(), then bring to the front the app window that was not there before. Its handle only when it is.
    For apps that run all windows in one process (Windows Terminal), so the new one is told apart by handle."""
    exe, word = WINDOWS.get(name.casefold(), (f"{name.casefold()}.exe", None))
    before = set(find(exe, word))
    start()
    deadline = clock() + timeout
    while True:
        new = [h for h in find(exe, word) if h not in before]
        if new:
            return new[0] if bring(new[0]) else None
        if clock() >= deadline:
            return None
        sleep(0.25)


EDIT_TYPES = (50004, 50003)  # UIA Edit, ComboBox
_LIST_ITEM = 50007


def looks_like_search(control_type: int, name: str, help_text: str, description: str, aria: str) -> bool:
    """A one-line edit/combo box labelled "search". Measured 2026-11-24 (UI Automation, nothing typed):
    Slack = combo box "Query", description "Search across people, channels…"; T3 Code = combo box
    "Search commands, projects, and threads..."; WhatsApp = edit "Search or start a new chat".
    Their message boxes ("Message", "Type a message to …") are multi-line and never say "search".
    WhatsApp's Chrome window also has a read-only "Address and search bar"; read-only never matches."""
    return (control_type in EDIT_TYPES and "multiline=true" not in aria and "readonly=true" not in aria
            and "search" in f"{name} {help_text} {description}".casefold())


class UiaSearchBox:
    """Reads the focused element of one window through Windows UI Automation (same approach as edit learning).
    Create it on the thread that uses it."""

    def __init__(self):
        import comtypes
        from edit_learning import _WindowsEditReader

        comtypes.CoInitialize()
        reader = _WindowsEditReader()
        self.u, self.automation = reader.u, reader.automation

    def _focused_input(self, hwnd: int):
        """The text box with keyboard focus inside exactly this window, or None."""
        u, a = self.u, self.automation
        root = a.ElementFromHandle(hwnd)
        element = root.FindFirst(u.TreeScope_Descendants,
                                 a.CreatePropertyCondition(u.UIA_HasKeyboardFocusPropertyId, True))
        if element and element.CurrentControlType == _LIST_ITEM:
            # T3 Code: focus shows on the highlighted result; the box is the edit in the same dialog.
            walker, dialog = a.RawViewWalker, element
            for _ in range(12):
                dialog = walker.GetParentElement(dialog)
                if not dialog or dialog.GetCurrentPropertyValue(u.UIA_AriaRolePropertyId) == "dialog":
                    break
            if not dialog:
                return None
            boxes = a.CreateOrCondition(
                a.CreatePropertyCondition(u.UIA_ControlTypePropertyId, EDIT_TYPES[0]),
                a.CreatePropertyCondition(u.UIA_ControlTypePropertyId, EDIT_TYPES[1]))
            element = dialog.FindFirst(u.TreeScope_Descendants, boxes)
        if not element or element.CurrentIsPassword or element.CurrentControlType not in EDIT_TYPES:
            return None
        return element

    def _in_whatsapp_side(self, element) -> bool:
        # WhatsApp hides its "Search…" label once the box has text; its box sits in the chat list pane "side".
        walker = self.automation.RawViewWalker
        for _ in range(12):
            element = walker.GetParentElement(element)
            if not element:
                return False
            if element.CurrentAutomationId == "side":
                return True
        return False

    def find(self, hwnd: int):
        """The focused box if it is the window's search box, else None. Never raises."""
        try:
            element = self._focused_input(hwnd)
            if not element:
                return None
            aria = element.GetCurrentPropertyValue(self.u.UIA_AriaPropertiesPropertyId) or ""
            if looks_like_search(element.CurrentControlType, element.CurrentName, element.CurrentHelpText,
                                 element.GetCurrentPropertyValue(self.u.UIA_FullDescriptionPropertyId) or "",
                                 aria):
                return element
            value = self.value_of(element)
            if (value or "").strip() and "multiline=true" not in aria and self._in_whatsapp_side(element):
                return element  # text left in it; the runner clears it and confirms the label again
        except Exception:
            pass
        return None

    def value_of(self, element) -> str | None:
        try:
            pattern = element.GetCurrentPattern(self.u.UIA_ValuePatternId)
            return pattern.QueryInterface(self.u.IUIAutomationValuePattern).CurrentValue
        except Exception:
            return None

    def same(self, hwnd: int, element) -> bool:
        """The box still has keyboard focus inside that window."""
        try:
            current = self._focused_input(hwnd)
            return bool(current) and bool(self.automation.CompareElements(current, element))
        except Exception:
            return False
