import unittest
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import command_runner
from command_runner import CommandRunner, PynputKeys, known_from
from window_focus import EDIT_TYPES, looks_like_search
from voice_commands import AMBIGUOUS, Command

APPS = [
    {"Name": "Slack", "AppID": "Slack.App.Id"},
    {"Name": "Notes Pro (Nightly)", "AppID": "Notes.Nightly!App"},
    {"Name": "Notes", "AppID": "Notes.Exact!App"},
]


def runner(apps=APPS, launch=None, focus=None):
    return CommandRunner(Mock(), start_apps=lambda: apps, launch=launch or Mock(),
                         focus=focus or Mock(return_value=True))


class CommandRunnerTests(unittest.TestCase):
    def test_app_launches_through_explorer_without_a_shell(self):
        launch = Mock()
        ok, detail = runner(launch=launch).run(Command("app", "Slack"))
        self.assertTrue(ok)
        self.assertEqual(detail, "Opened Slack")
        launch.assert_called_once_with(["explorer.exe", r"shell:AppsFolder\Slack.App.Id"])

    def test_exact_name_beats_longer_name(self):
        launch = Mock()
        runner(launch=launch).run(Command("app", "Notes"))
        launch.assert_called_once_with(["explorer.exe", r"shell:AppsFolder\Notes.Exact!App"])

    def test_prefix_match_finds_app_with_extra_words(self):
        launch = Mock()
        ok, _ = runner(launch=launch).run(Command("app", "Notes Pro"))
        self.assertTrue(ok)

    def test_missing_app_fails_and_launches_nothing(self):
        launch = Mock()
        ok, detail = runner(launch=launch).run(Command("app", "Zed"))
        self.assertFalse(ok)
        self.assertEqual(detail, "Couldn't open Zed")
        launch.assert_not_called()

    def test_launch_error_fails(self):
        ok, detail = runner(launch=Mock(side_effect=OSError("no"))).run(Command("app", "Slack"))
        self.assertFalse(ok)
        self.assertEqual(detail, "Couldn't open Slack")

    def test_site_is_not_supported_yet(self):
        launch = Mock()
        ok, detail = runner(launch=launch).run(Command("site", "GitHub", account=AMBIGUOUS))
        self.assertEqual((ok, detail), (False, "Account not clear"))
        launch.assert_not_called()

    def test_success_only_when_the_window_is_in_front(self):
        focus = Mock(return_value=True)
        ok, _ = runner(focus=focus).run(Command("app", "Slack"))
        self.assertTrue(ok)
        focus.assert_called_once_with("Slack")
        ok, detail = runner(focus=Mock(return_value=False)).run(Command("app", "Slack"))
        self.assertEqual((ok, detail), (False, "Couldn't bring Slack to front"))

    def test_slow_start_apps_never_blocks_a_command_for_long(self):
        release = threading.Event()
        slow = CommandRunner(Mock(), start_apps=lambda: (release.wait(5), APPS)[1], launch=Mock(),
                             focus=Mock(return_value=True), wait=0.2)
        slow.warm()
        started = time.monotonic()
        ok, detail = slow.run(Command("app", "Slack"))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual((ok, detail), (False, "Apps still loading — try again"))
        release.set()
        self.assertTrue(slow._ready.wait(2))
        self.assertTrue(slow.run(Command("app", "Slack"))[0])

    def test_failed_load_retries_in_the_background(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise OSError("powershell missing")
            return APPS

        r = CommandRunner(Mock(), start_apps=flaky, launch=Mock(), focus=Mock(return_value=True),
                          wait=0.05, retry_delay=0.05)
        r.warm()
        self.assertTrue(r._ready.wait(2))
        self.assertEqual(len(calls), 2)

    def test_start_apps_output_is_read_as_utf8(self):
        payload = '[{"Name": "Café App", "AppID": "Cafe!App"}]'.encode("utf-8")
        with patch.object(command_runner.subprocess, "run", return_value=Mock(stdout=payload)) as run:
            apps = command_runner.get_start_apps()
        self.assertEqual(apps[0]["Name"], "Café App")
        self.assertIn("[Console]::OutputEncoding", run.call_args.args[0][-1])
        self.assertNotIn("text", run.call_args.kwargs)

    def test_known_comes_from_settings_and_chrome_emails(self):
        state = {"profile": {"info_cache": {"P1": {"user_name": "ann@acme.test"}, "P2": {"user_name": ""}}}}
        settings = {"self_name": "ann", "default_account": "ann@x.test", "orgs": {"acme": "acme.test"},
                    "workspaces": ["acme"]}
        known = known_from(settings, state)
        self.assertEqual(known.accounts, ("ann@acme.test",))
        self.assertEqual((known.self_name, known.default_account), ("ann", "ann@x.test"))
        self.assertEqual(known.orgs, {"acme": "acme.test"})
        self.assertEqual(known.workspaces, ("acme",))

    def test_known_survives_empty_or_bad_settings(self):
        known = known_from({}, None)
        self.assertEqual((known.self_name, known.accounts, known.orgs), ("", (), {}))
        self.assertEqual(known_from({"orgs": "bad", "workspaces": 3}, {}).orgs, {})


HWND = 42


class FakeApp:
    """One fake app window (hwnd 42): its keyboard and what UI Automation sees.

    The search box opens only when the right shortcut arrives; text typed while it is closed
    lands in the message box (`composer`), which is what the safety checks must prevent."""
    def __init__(self, shortcut=None, opens=True, stray="", lose_after=None, raise_on=None, echo=True):
        self.events, self.front, self.lose_after, self.raise_on = [], [True], lose_after, raise_on
        self.shortcut, self.opens, self.stray, self.echo = shortcut, opens, stray, echo
        self.open, self.value, self.composer, self.selected, self.released = False, "", "", False, False

    def _log(self, event):
        if event == self.raise_on:
            raise RuntimeError("key send failed")
        self.events.append(event)
        if self.lose_after is not None and len(self.events) >= self.lose_after:
            self.front[0] = False

    def chord(self, *names):
        self._log(("chord",) + names)
        if self.opens and names == self.shortcut:
            self.open, self.value = True, self.stray
        self.selected = names == ("ctrl", "a")

    def type_char(self, char):
        self._log(("type", char))
        if self.open:
            self.value += char if self.echo else ""
        else:
            self.composer += char

    def tap(self, name):
        self._log(("tap", name))
        if name == "backspace" and self.selected:
            self.value = ""
        if name == "esc":
            self.open = False

    def release_modifiers(self):
        self.released = True

    # UI Automation side
    def find(self, hwnd):
        return "BOX" if self.open and hwnd == HWND else None

    def value_of(self, element):
        return self.value if element == "BOX" and self.open else None

    def same(self, hwnd, element):
        return self.find(hwnd) == element


class SearchTests(unittest.TestCase):
    SHORTCUTS = {"Slack": ("ctrl", "k"), "T3 Code": ("ctrl", "k"), "WhatsApp": ("ctrl", "alt", "/")}

    def _run(self, command, focus_ok=True, front_at_start=True, **app):
        fake = FakeApp(shortcut=app.pop("shortcut", self.SHORTCUTS.get(command.name)), **app)
        fake.front[0] = front_at_start
        now = [0.0]
        r = CommandRunner(Mock(), start_apps=lambda: APPS + [{"Name": "WhatsApp", "AppID": "W"},
                                                 {"Name": "T3 Code (Nightly)", "AppID": "T"}],
                          launch=Mock(), focus=Mock(return_value=HWND if focus_ok else None), keys=fake,
                          in_front=lambda hwnd: fake.front[0] and hwnd == HWND, box=fake,
                          pause=lambda s: now.__setitem__(0, now[0] + s), clock=lambda: now[0])
        self.runner, self.now = r, now
        return r.run(command), fake

    def _typed(self, fake):
        return "".join(e[1] for e in fake.events if e[0] == "type")

    def test_slack_types_the_name_into_the_confirmed_box_then_presses_enter(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="hirefast"))
        self.assertEqual((ok, detail), (True, "Searched Slack for hirefast"))
        self.assertEqual(fake.events[0], ("chord", "ctrl", "k"))
        self.assertEqual(self._typed(fake), "hirefast")
        self.assertEqual(fake.events[-1], ("tap", "enter"))
        self.assertEqual(fake.composer, "")

    def test_t3_types_the_name_but_never_presses_enter(self):
        (ok, _), fake = self._run(Command("search", "T3 Code", target="voice command"))
        self.assertTrue(ok)
        self.assertEqual(fake.events[0], ("chord", "ctrl", "k"))
        self.assertEqual(self._typed(fake), "voice command")
        self.assertNotIn(("tap", "enter"), fake.events)

    def test_whatsapp_clears_a_stray_slash_before_typing(self):
        (ok, _), fake = self._run(Command("search", "WhatsApp", target="Puneet Jigsaw"), stray="/")
        self.assertTrue(ok)
        self.assertEqual(fake.events[:3], [("chord", "ctrl", "alt", "/"), ("chord", "ctrl", "a"),
                                           ("tap", "backspace")])
        self.assertEqual(fake.value, "Puneet Jigsaw")
        self.assertEqual(fake.events[-1], ("tap", "enter"))

    def test_box_is_cleared_even_when_it_reads_empty(self):
        # Measured: WhatsApp's "/" lands ~0.1 s after UI Automation already read the new box as empty.
        _, fake = self._run(Command("search", "WhatsApp", target="Puneet"))
        self.assertEqual(fake.events[1:3], [("chord", "ctrl", "a"), ("tap", "backspace")])
        self.assertEqual(self._typed(fake), "Puneet")

    def test_dropped_shortcut_types_nothing_and_presses_escape(self):
        # The review finding: shortcut lost -> the name went to the message box and Enter sent it.
        (ok, detail), fake = self._run(Command("search", "Slack", target="hirefast"), opens=False)
        self.assertEqual((ok, detail), (False, "Search box not found — nothing typed"))
        self.assertEqual(fake.events, [("chord", "ctrl", "k"), ("tap", "esc")])
        self.assertEqual(fake.composer, "")

    def test_wrong_shortcut_types_nothing(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="hirefast"), shortcut=("f13",))
        self.assertEqual(detail, "Search box not found — nothing typed")
        self.assertEqual(self._typed(fake), "")

    def test_search_box_wait_is_bounded(self):
        self._run(Command("search", "Slack", target="x"), opens=False)
        self.assertLessEqual(self.now[0], 1.6)

    def test_box_value_not_matching_the_name_sends_no_enter(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="hirefast"), echo=False)
        self.assertEqual((ok, detail), (False, "Search box not found — nothing sent"))
        self.assertNotIn(("tap", "enter"), fake.events)
        self.assertEqual(fake.events[-1], ("tap", "esc"))

    def test_focus_lost_mid_sequence_sends_no_more_keys(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="hirefast"), lose_after=3)
        self.assertFalse(ok)
        self.assertEqual(detail, "Couldn't focus Slack — nothing typed")
        self.assertEqual(len(fake.events), 3)

    def test_not_in_front_at_start_sends_nothing(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="x"), front_at_start=False)
        self.assertEqual((ok, fake.events), (False, []))
        self.assertEqual(detail, "Couldn't focus Slack — nothing typed")

    def test_front_check_uses_the_exact_window_that_was_focused(self):
        seen = []
        fake = FakeApp(shortcut=("ctrl", "k"))
        r = CommandRunner(Mock(), start_apps=lambda: APPS, launch=Mock(), focus=Mock(return_value=HWND),
                          keys=fake, box=fake, in_front=lambda hwnd: seen.append(hwnd) or True,
                          pause=lambda s: None)
        r.run(Command("search", "Slack", target="x"))
        self.assertTrue(seen)
        self.assertEqual(set(seen), {HWND})

    def test_error_mid_sequence_releases_modifiers(self):
        with self.assertRaises(RuntimeError):
            self._run(Command("search", "Slack", target="hirefast"), raise_on=("type", "r"))
        self.assertTrue(self.runner._keys.released)

    def test_window_not_focused_sends_nothing(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="x"), focus_ok=False)
        self.assertEqual((ok, fake.events), (False, []))

    def test_focused_at_is_recorded_when_the_app_is_in_front(self):
        self._run(Command("search", "Slack", target="x"))
        self.assertIsNotNone(self.runner.focused_at)
        self._run(Command("search", "Slack", target="x"), focus_ok=False)
        self.assertIsNone(self.runner.focused_at)

    def test_slack_workspace_is_not_supported_yet_and_sends_nothing(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="general", workspace="jigsaw"))
        self.assertEqual((ok, detail, fake.events), (False, "Workspace switch not supported yet", []))

    def test_app_without_a_search_shortcut_fails(self):
        (ok, _), fake = self._run(Command("search", "Notes", target="x"))
        self.assertEqual((ok, fake.events), (False, []))


class FakeController:
    def __init__(self, fail_on=None):
        self.down, self.fail_on = [], fail_on

    def press(self, key):
        if key == self.fail_on:
            raise RuntimeError("press failed")
        self.down.append(key)

    def release(self, key):
        if key in self.down:
            self.down.remove(key)


class PynputKeysTests(unittest.TestCase):
    def test_chord_releases_pressed_keys_when_a_press_fails(self):
        c = FakeController(fail_on="k")
        keys = PynputKeys(controller=c)
        with self.assertRaises(RuntimeError):
            keys.chord("ctrl", "alt", "k")
        self.assertEqual(c.down, [])

    def test_release_modifiers_lets_go_of_ctrl_alt_shift(self):
        from pynput import keyboard
        c = FakeController()
        c.down = [keyboard.Key.ctrl, keyboard.Key.alt, keyboard.Key.shift]
        PynputKeys(controller=c).release_modifiers()
        self.assertEqual(c.down, [])


class SearchLabelTests(unittest.TestCase):
    """Real focused-element properties read by UI Automation on 2026-11-24 (probe, nothing typed)."""
    def test_measured_search_boxes_match(self):
        self.assertTrue(looks_like_search(EDIT_TYPES[1], "Query", "",  # Slack (combo box)
                                          "Search across people, channels, files, workflows, and more",
                                          "expanded=true;haspopup=listbox;multiline=false"))
        self.assertTrue(looks_like_search(EDIT_TYPES[1], "Search commands, projects, and threads...",  # T3
                                          "Search commands, projects, and threads...", "", "multiline=false"))
        self.assertTrue(looks_like_search(EDIT_TYPES[0], "Search or start a new chat",  # WhatsApp
                                          "Search or start a new chat", "", "multiline=false"))

    def test_measured_message_boxes_do_not_match(self):
        self.assertFalse(looks_like_search(EDIT_TYPES[0], "Message",  # T3 composer
                                           "Ask for changes, send follow-ups, or attach images", "",
                                           "multiline=true"))
        self.assertFalse(looks_like_search(EDIT_TYPES[0], "Type a message to Ann Example", "Type a message",
                                           "", "multiline=true"))  # WhatsApp composer
        self.assertFalse(looks_like_search(EDIT_TYPES[0], "Message to cl-example", "", "",
                                           "expanded=false;multiline=true"))  # Slack composer

    def test_browser_address_bar_does_not_match(self):
        # WhatsApp runs in a Chrome app window that also holds a hidden, read-only "Address and search bar".
        self.assertFalse(looks_like_search(EDIT_TYPES[0], "Address and search bar", "", "",
                                           "readonly=true;expanded=false;multiline=false"))

    def test_multiline_or_non_edit_never_matches_even_with_search_in_the_name(self):
        self.assertFalse(looks_like_search(EDIT_TYPES[0], "Search notes", "", "", "multiline=true"))
        self.assertFalse(looks_like_search(50000, "Search", "", "", ""))  # a button


class TerminalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.launch = Mock()
        self.focus_calls = []

    def make(self, focus_ok=True):
        def new_window(name, start):
            start()
            self.focus_calls.append(name)
            return 77 if focus_ok else None
        drives = {"t": self.root}
        return CommandRunner(Mock(), launch=self.launch, new_window=new_window,
                             drive_root=lambda letter: drives.get(letter, Path(f"{letter}:/not-here")))

    def test_drive_only_opens_terminal_there_with_an_argv_list(self):
        ok, detail = self.make().run(Command("terminal", "Terminal", drive="t"))
        self.assertTrue(ok)
        self.launch.assert_called_once_with(["wt.exe", "-w", "new", "-d", str(self.root)])
        self.assertEqual(self.focus_calls, ["terminal"])

    def test_run_claude_adds_cmd_k_claude(self):
        self.make().run(Command("terminal", "Terminal", drive="t", run_claude=True))
        self.launch.assert_called_once_with(["wt.exe", "-w", "new", "-d", str(self.root), "cmd", "/k", "claude"])

    def test_missing_drive_fails_and_launches_nothing(self):
        ok, detail = self.make().run(Command("terminal", "Terminal", drive="q"))
        self.assertEqual((ok, detail), (False, "Drive Q: not found"))
        self.launch.assert_not_called()

    def test_no_drive_and_no_roots_asks_which_drive(self):
        ok, detail = self.make().run(Command("terminal", "Terminal", words=("zebra",)))
        self.assertEqual((ok, detail), (False, "Say which drive"))
        self.launch.assert_not_called()

    def test_not_success_until_the_new_window_is_in_front(self):
        ok, detail = self.make(focus_ok=False).run(Command("terminal", "Terminal", drive="t"))
        self.assertEqual((ok, detail), (False, "Couldn't bring Terminal to front"))

    def test_launch_error_fails(self):
        self.launch.side_effect = OSError("no")
        ok, detail = self.make().run(Command("terminal", "Terminal", drive="t"))
        self.assertEqual((ok, detail), (False, "Couldn't open Terminal"))


if __name__ == "__main__":
    unittest.main()
