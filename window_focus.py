"""Find an app's window and bring it to the front (measured 15/15 in the slice 1.0 spike)."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from pathlib import Path

# app name (lower case) -> (exe name, title word). WhatsApp runs as a Chrome app window, so it is found by title.
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


def find_window(exe: str | None, title_word: str | None = None) -> int | None:
    """First visible, titled top-level window of that exe (or with that word in the title)."""
    found: list[int] = []

    def visit(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(hwnd, title, 256)
        if not title.value:
            return True
        name = _exe_name(hwnd)
        if (exe and name == exe) or (title_word and title_word in title.value):
            found.append(int(hwnd))
            return False
        return True

    _user32.EnumWindows(_ENUM(visit), 0)
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


def focus_app(name: str, find=find_window, bring=bring_to_front, timeout: float = 10.0,
              sleep=time.sleep, clock=time.monotonic) -> bool:
    """Wait up to `timeout` s for the app's window, then bring it to the front. True only when it is."""
    exe, word = WINDOWS.get(name.casefold(), (f"{name.casefold()}.exe", None))
    deadline = clock() + timeout
    while True:
        hwnd = find(exe, word)
        if hwnd:
            return bool(bring(hwnd))
        if clock() >= deadline:
            return False
        sleep(0.25)
