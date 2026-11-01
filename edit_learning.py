"""Opt-in learning from a brief edit to VoxKey's own recent paste."""

from __future__ import annotations

import threading
import time
from difflib import SequenceMatcher

from voxkey_events import UiEvent


def edited_phrase(before: str, after: str, pasted: str) -> tuple[str, str] | None:
    """Find one short replacement wholly inside a unique VoxKey paste."""
    if not pasted or before.count(pasted) != 1 or len(before) > 5000 or len(after) > 5000:
        return None
    paste_start = before.index(pasted)
    paste_end = paste_start + len(pasted)
    left = 0
    while left < min(len(before), len(after)) and before[left] == after[left]:
        left += 1
    right = 0
    while (right < len(before) - left and right < len(after) - left
           and before[-right - 1] == after[-right - 1]):
        right += 1
    old_end = len(before) - right
    new_end = len(after) - right
    new_start = old_start = left
    if old_start < paste_start or old_end > paste_end:
        return None
    if old_start == old_end and old_start in (paste_start, paste_end):
        return None

    # A changed capital inside a word must teach the whole word, not one letter.
    while (old_start > paste_start and new_start > 0
           and before[old_start - 1].isalnum()
           and before[old_start - 1] == after[new_start - 1]):
        old_start -= 1
        new_start -= 1
    while (old_end < paste_end and new_end < len(after)
           and before[old_end].isalnum()
           and before[old_end] == after[new_end]):
        old_end += 1
        new_end += 1

    heard = before[old_start:old_end].strip()
    intended = after[new_start:new_end].strip()
    if (not heard or not intended or heard == intended
            or max(len(heard), len(intended)) > 60
            or "\n" in heard or "\n" in intended
            or not any(char.isalnum() for char in heard + intended)):
        return None
    if ((old_start and before[old_start - 1].isalnum())
            or (old_end < len(before) and before[old_end].isalnum())
            or (new_start and after[new_start - 1].isalnum())
            or (new_end < len(after) and after[new_end].isalnum())):
        return None
    return heard, intended


def safe_to_learn(heard: str, intended: str, preferred=()) -> bool:
    """Auto-apply close word spellings; leave broad rewrites for review."""
    if any(char.isupper() for char in intended[1:]):
        return True
    if heard.casefold() == intended.casefold():
        return intended in preferred
    if intended.casefold().startswith(heard.casefold()) and intended[len(heard):].casefold() in {"s", "d", "ed", "ing"}:
        return False
    return (heard.isalpha() and intended.isalpha()
            and min(len(heard), len(intended)) >= 3
            and SequenceMatcher(None, heard.casefold(), intended.casefold()).ratio() >= 0.6)


class _WindowsEditReader:
    def __init__(self):
        import comtypes.client

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as u

        self.u = u
        self.automation = comtypes.client.CreateObject(u.CUIAutomation, interface=u.IUIAutomation)
        self._range = None

    def capture(self, hwnd: int, pasted: str):
        u = self.u
        root = self.automation.ElementFromHandle(hwnd)
        focused = self.automation.CreatePropertyCondition(u.UIA_HasKeyboardFocusPropertyId, True)
        element = root.FindFirst(u.TreeScope_Descendants, focused)
        if not element and root.CurrentHasKeyboardFocus:
            element = root
        if not element or element.CurrentIsPassword:
            return None
        value = self.read(element)
        if value is not None and value.count(pasted) == 1:
            return element, value
        try:
            pattern = element.GetCurrentPattern(u.UIA_TextPatternId)
            text = pattern.QueryInterface(u.IUIAutomationTextPattern)
            selection = text.GetSelection()
            if not selection.Length:
                return None
            region = selection.GetElement(0).Clone()
            region.MoveEndpointByUnit(u.TextPatternRangeEndpoint_Start, u.TextUnit_Character,
                                      -min(len(pasted) + 128, 4800))
            region.MoveEndpointByUnit(u.TextPatternRangeEndpoint_End, u.TextUnit_Character, 128)
            self._range = region
            value = self.read(element)
            return (element, value) if value is not None and value.count(pasted) == 1 else None
        except Exception:
            return None

    def read(self, element) -> str | None:
        try:
            if not element.CurrentHasKeyboardFocus or element.CurrentIsPassword:
                return None
            if self._range is not None:
                value = self._range.GetText(5001)
            else:
                pattern = element.GetCurrentPattern(self.u.UIA_ValuePatternId)
                value = pattern.QueryInterface(self.u.IUIAutomationValuePattern).CurrentValue
        except Exception:
            return None
        return value if len(value) <= 5000 else None


class EditLearningWatcher:
    def __init__(self, memory, enabled, foreground, logger=None, events=None, preferred=None):
        self.memory = memory
        self.enabled = enabled
        self.foreground = foreground
        self.logger = logger
        self.events = events
        self.preferred = preferred or (lambda: ())
        self._generation = 0
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._generation += 1

    def watch(self, hwnd: int | None, pasted: str, app: str | None) -> None:
        if not hwnd or not self.enabled():
            return
        with self._lock:
            self._generation += 1
            generation = self._generation
        threading.Thread(target=self._observe, args=(generation, hwnd, pasted, app), daemon=True).start()

    def _observe(self, generation: int, hwnd: int, pasted: str, app: str | None) -> None:
        import comtypes

        comtypes.CoInitialize()
        try:
            if self.foreground() != hwnd:
                return
            reader = _WindowsEditReader()
            captured = reader.capture(hwnd, pasted)
            if not captured:
                if self.logger:
                    self.logger.info("Edit learning skipped; app=%s; focused text unavailable", app)
                return
            element, baseline = captured
            if baseline.count(pasted) != 1:
                if self.logger:
                    self.logger.info("Edit learning skipped; app=%s; paste not unique", app)
                return
            until = time.monotonic() + 120
            changed_at = None
            previous = baseline
            while time.monotonic() < until:
                time.sleep(0.4)
                with self._lock:
                    cancelled = generation != self._generation
                if cancelled or not self.enabled():
                    return
                if self.foreground() != hwnd:
                    continue
                current = reader.read(element)
                if current is None:
                    continue
                if current != previous:
                    changed_at = time.monotonic()
                    previous = current
                if changed_at is None or time.monotonic() - changed_at < 1.2:
                    continue
                correction = edited_phrase(baseline, current, pasted)
                if correction:
                    heard, intended = correction
                    global_term = any(char.isupper() for char in intended[1:]) or intended in self.preferred()
                    if safe_to_learn(heard, intended, self.preferred()) and (app or global_term):
                        learned = self.memory.learn_edit(heard, intended, None if global_term else app)
                        kind = "correction_learned" if learned else "correction_suggested"
                    else:
                        self.memory.suggest_correction(heard, intended, app)
                        kind = "correction_suggested"
                    if self.events:
                        self.events.publish(UiEvent(kind))
                    if self.logger:
                        self.logger.info("Edit learning %s; app=%s", kind, app)
                return
        except Exception:
            if self.logger:
                self.logger.exception("Edit learning stopped")
        finally:
            comtypes.CoUninitialize()
