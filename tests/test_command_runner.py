import unittest
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, call, patch

import command_runner
from command_runner import CommandRunner, PynputKeys, known_from
from window_focus import EDIT_TYPES, looks_like_search
from voice_commands import AMBIGUOUS, UNKNOWN, Command, Known

APPS = [
    {"Name": "Slack", "AppID": "Slack.App.Id"},
    {"Name": "Notes Pro (Nightly)", "AppID": "Notes.Nightly!App"},
    {"Name": "Notes", "AppID": "Notes.Exact!App"},
]


CHROME = r"C:\Chrome\chrome.exe"
STATE = {"profile": {"info_cache": {"Default": {"user_name": "bob@acme.test"},
                                    "Profile 7": {"user_name": "ann@acme.test"}}}}


def site_runner(launch, state=STATE, chrome=CHROME, hwnd=77):
    def new_window(name, start):
        start()
        return hwnd
    new_window = Mock(side_effect=new_window)
    return CommandRunner(Mock(), launch=launch, new_window=new_window,
                         chrome_state=lambda: state, chrome_path=lambda: chrome), new_window


def runner(apps=APPS, launch=None, focus=None, has_window=lambda name: False):
    return CommandRunner(Mock(), start_apps=lambda: apps, launch=launch or Mock(), has_window=has_window,
                         focus=focus or Mock(side_effect=lambda name, timeout=None: timeout != 0))


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

    def test_unclear_account_fails_and_launches_nothing(self):
        for marker in (AMBIGUOUS, UNKNOWN):
            launch = Mock()
            command = Command("site", "GitHub", account=marker, heard="in sam account")
            ok, detail = site_runner(launch)[0].run(command)
            self.assertEqual((ok, detail), (False, "Account not clear: in sam account"))
            launch.assert_not_called()

    def test_site_opens_in_the_profile_of_the_account(self):
        launch = Mock()
        r, new_window = site_runner(launch)
        ok, detail = r.run(Command("site", "Gmail", url="https://mail.google.com", account="ann@acme.test"))
        self.assertTrue(ok)
        self.assertEqual(detail, "Opened Gmail")
        launch.assert_called_once_with([CHROME, "--profile-directory=Profile 7", "--new-window", "https://mail.google.com"])
        new_window.assert_called_once()
        self.assertEqual(new_window.call_args.args[0], "chrome")
        self.assertIsNotNone(r.focused_at)

    def test_account_match_ignores_case(self):
        launch = Mock()
        site_runner(launch)[0].run(Command("site", "Gmail", url="https://x.test", account="ANN@acme.TEST"))
        self.assertIn("--profile-directory=Profile 7", launch.call_args.args[0])

    def test_site_with_no_account_uses_the_default_account_profile(self):
        launch = Mock()
        r = site_runner(launch)[0]
        r.known = Known(default_account="ann@acme.test")
        ok, _ = r.run(Command("site", "YouTube", url="https://www.youtube.com"))
        self.assertTrue(ok)
        launch.assert_called_once_with([CHROME, "--profile-directory=Profile 7", "--new-window", "https://www.youtube.com"])

    def test_site_with_no_default_account_or_no_profile_sets_no_profile_flag(self):
        for known in (Known(), Known(default_account="zed@acme.test")):
            launch = Mock()
            r = site_runner(launch)[0]
            r.known = known
            ok, _ = r.run(Command("site", "YouTube", url="https://www.youtube.com"))
            self.assertTrue(ok)
            launch.assert_called_once_with([CHROME, "--new-window", "https://www.youtube.com"])

    def test_my_account_without_a_profile_opens_like_plain_open(self):
        launch = Mock()
        r = site_runner(launch)[0]
        r.known = Known(default_account="zed@acme.test")
        ok, _ = r.run(Command("site", "Gmail", url="https://x.test", account="zed@acme.test"))
        self.assertTrue(ok)
        launch.assert_called_once_with([CHROME, "--new-window", "https://x.test"])

    def test_no_account_pins_the_last_used_profile_so_a_cold_start_skips_the_picker(self):
        launch = Mock()
        state = {"profile": {**STATE["profile"], "last_used": "Profile 7"}}
        site_runner(launch, state=state)[0].run(Command("site", "YouTube", url="https://x.test"))
        launch.assert_called_once_with([CHROME, "--profile-directory=Profile 7", "--new-window", "https://x.test"])

    def test_site_refuses_a_url_that_is_not_http(self):
        for url in ("--disable-web-security", "file:///c:/x", "javascript:alert(1)", ""):
            launch = Mock()
            ok, detail = site_runner(launch)[0].run(Command("site", "Evil", url=url))
            self.assertEqual((ok, detail), (False, "Website address not allowed"))
            launch.assert_not_called()

    def test_profile_added_after_startup_resolves_without_restart(self):
        state = {"profile": {"info_cache": {}}}
        launch = Mock()
        r = CommandRunner(Mock(), launch=launch, new_window=lambda n, start: (start(), 5)[1],
                          chrome_state=lambda: state, chrome_path=lambda: CHROME,
                          known_provider=lambda: command_runner.known_from({"self_name": "ann", "orgs": {"acme": "acme.test"}}, state))
        self.assertEqual(r.parse("open gmail in ann acme").account, UNKNOWN)
        state["profile"]["info_cache"]["Profile 9"] = {"user_name": "ann@acme.test"}
        command = r.parse("open gmail in ann acme")
        self.assertEqual(command.account, "ann@acme.test")
        self.assertTrue(r.run(command)[0])
        self.assertIn("--profile-directory=Profile 9", launch.call_args.args[0])

    def test_account_without_a_chrome_profile_fails(self):
        launch = Mock()
        ok, detail = site_runner(launch)[0].run(Command("site", "Gmail", url="https://x.test", account="zed@acme.test"))
        self.assertEqual((ok, detail), (False, "No Chrome profile for zed@acme.test"))
        launch.assert_not_called()

    def test_site_fails_when_chrome_or_its_state_is_missing(self):
        launch = Mock()
        r, _ = site_runner(launch, chrome=None)
        self.assertEqual(r.run(Command("site", "G", url="https://x.test")), (False, "Couldn't find Chrome"))
        r, _ = site_runner(launch, state=None)
        self.assertEqual(r.run(Command("site", "G", url="https://x.test", account="ann@acme.test")),
                         (False, "No Chrome profile for ann@acme.test"))
        launch.assert_not_called()

    def test_site_is_a_failure_until_its_window_is_in_front(self):
        r, _ = site_runner(Mock(), hwnd=None)
        ok, detail = r.run(Command("site", "Gmail", url="https://x.test", account="ann@acme.test"))
        self.assertEqual((ok, detail), (False, "Couldn't bring Chrome to front"))
        self.assertIsNone(r.focused_at)
        r, _ = site_runner(Mock(side_effect=OSError("no")))
        self.assertEqual(r.run(Command("site", "G", url="https://x.test")), (False, "Couldn't open G"))

    def test_chrome_is_found_in_app_paths_then_program_files(self):
        found = command_runner.find_chrome(registry=lambda: r"D:\Chrome\chrome.exe", exists=lambda p: True, env={})
        self.assertEqual(found, r"D:\Chrome\chrome.exe")
        env = {"ProgramFiles": r"C:\PF", "ProgramFiles(x86)": r"C:\PF86", "LOCALAPPDATA": r"C:\L"}
        want = r"C:\PF86\Google\Chrome\Application\chrome.exe"
        found = command_runner.find_chrome(registry=lambda: None, exists=lambda p: p == want, env=env)
        self.assertEqual(found, want)
        self.assertIsNone(command_runner.find_chrome(registry=lambda: None, exists=lambda p: False, env=env))
        # a registry path that no longer exists is skipped
        found = command_runner.find_chrome(registry=lambda: r"D:\gone\chrome.exe", exists=lambda p: p == want, env=env)
        self.assertEqual(found, want)

    def test_profile_folder_comes_from_local_state(self):
        state = {"profile": {"info_cache": {"Default": {"user_name": "A@x.test"}, "Profile 2": {"user_name": "b@x.test"},
                                            "Profile 3": {}}}}
        self.assertEqual(command_runner.chrome_profile(state, "a@X.test"), "Default")
        self.assertEqual(command_runner.chrome_profile(state, "b@x.test"), "Profile 2")
        self.assertIsNone(command_runner.chrome_profile(state, "c@x.test"))
        self.assertIsNone(command_runner.chrome_profile(None, "a@x.test"))
        self.assertIsNone(command_runner.chrome_profile({"profile": 3}, "a@x.test"))

    def test_saved_sites_reach_the_parser_live(self):
        sites = {}
        r = CommandRunner(Mock(), sites_provider=lambda: sites)
        self.assertIsNone(r.parse("open acme board"))
        sites["Acme board"] = "https://board.example.com"
        self.assertEqual(r.parse("open acme board").url, "https://board.example.com")
        self.assertEqual(r.parse("open github").name, "GitHub")  # built-ins stay

    def test_success_only_when_the_window_is_in_front(self):
        focus = Mock(return_value=True)
        ok, _ = runner(focus=focus).run(Command("app", "Slack"))
        self.assertTrue(ok)
        focus.assert_called_once_with("Slack", timeout=0)
        ok, detail = runner(focus=Mock(return_value=False)).run(Command("app", "Slack"))
        self.assertEqual((ok, detail), (False, "Couldn't bring Slack to front"))

    def test_existing_window_is_focused_without_launching(self):
        launch, focus = Mock(), Mock(return_value=True)
        ok, detail = runner(launch=launch, focus=focus).run(Command("app", "Slack"))
        self.assertEqual((ok, detail), (True, "Opened Slack"))
        focus.assert_called_once_with("Slack", timeout=0)
        launch.assert_not_called()

    def test_window_that_will_not_focus_is_not_launched_again(self):
        launch, focus = Mock(), Mock(return_value=None)
        ok, detail = runner(launch=launch, focus=focus, has_window=lambda name: True).run(Command("app", "Slack"))
        self.assertEqual((ok, detail), (False, "Couldn't bring Slack to front"))
        launch.assert_not_called()
        focus.assert_called_once_with("Slack", timeout=0)

    def test_missing_window_is_launched_then_waited_for(self):
        launch, focus = Mock(), Mock(side_effect=[None, 1])
        ok, _ = runner(launch=launch, focus=focus).run(Command("app", "Slack"))
        self.assertTrue(ok)
        launch.assert_called_once()
        self.assertEqual(focus.call_args_list, [call("Slack", timeout=0), call("Slack")])

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
        (ok, detail), fake = self._run(Command("search", "Slack", target="roadmap"))
        self.assertEqual((ok, detail), (True, "Searched Slack for roadmap"))
        self.assertEqual(fake.events[0], ("chord", "ctrl", "k"))
        self.assertEqual(self._typed(fake), "roadmap")
        self.assertEqual(fake.events[-1], ("tap", "enter"))
        self.assertEqual(fake.composer, "")

    def test_t3_types_the_name_but_never_presses_enter(self):
        (ok, _), fake = self._run(Command("search", "T3 Code", target="voice command"))
        self.assertTrue(ok)
        self.assertEqual(fake.events[0], ("chord", "ctrl", "k"))
        self.assertEqual(self._typed(fake), "voice command")
        self.assertNotIn(("tap", "enter"), fake.events)

    def test_whatsapp_clears_a_stray_slash_before_typing(self):
        (ok, _), fake = self._run(Command("search", "WhatsApp", target="Sam Globex"), stray="/")
        self.assertTrue(ok)
        self.assertEqual(fake.events[:3], [("chord", "ctrl", "alt", "/"), ("chord", "ctrl", "a"),
                                           ("tap", "backspace")])
        self.assertEqual(fake.value, "Sam Globex")
        self.assertEqual(fake.events[-1], ("tap", "enter"))

    def test_box_is_cleared_even_when_it_reads_empty(self):
        # Measured: WhatsApp's "/" lands ~0.1 s after UI Automation already read the new box as empty.
        _, fake = self._run(Command("search", "WhatsApp", target="Sam"))
        self.assertEqual(fake.events[1:3], [("chord", "ctrl", "a"), ("tap", "backspace")])
        self.assertEqual(self._typed(fake), "Sam")

    def test_dropped_shortcut_types_nothing_and_presses_escape(self):
        # The review finding: shortcut lost -> the name went to the message box and Enter sent it.
        (ok, detail), fake = self._run(Command("search", "Slack", target="roadmap"), opens=False)
        self.assertEqual((ok, detail), (False, "Search box not found — nothing typed"))
        self.assertEqual(fake.events, [("chord", "ctrl", "k"), ("tap", "esc")])
        self.assertEqual(fake.composer, "")

    def test_wrong_shortcut_types_nothing(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="roadmap"), shortcut=("f13",))
        self.assertEqual(detail, "Search box not found — nothing typed")
        self.assertEqual(self._typed(fake), "")

    def test_search_box_wait_is_bounded(self):
        self._run(Command("search", "Slack", target="x"), opens=False)
        self.assertLessEqual(self.now[0], 1.6)

    def test_box_value_not_matching_the_name_sends_no_enter(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="roadmap"), echo=False)
        self.assertEqual((ok, detail), (False, "Search box not found — nothing sent"))
        self.assertNotIn(("tap", "enter"), fake.events)
        self.assertEqual(fake.events[-1], ("tap", "esc"))

    def test_focus_lost_mid_sequence_sends_no_more_keys(self):
        (ok, detail), fake = self._run(Command("search", "Slack", target="roadmap"), lose_after=3)
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
            self._run(Command("search", "Slack", target="roadmap"), raise_on=("type", "r"))
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

    def make(self, folder_roots=(), focus_ok=True, index_roots=None, wait=0.5):
        def new_window(name, start):
            start()
            self.focus_calls.append(name)
            return 77 if focus_ok else None
        drives = {"t": self.root}
        return CommandRunner(Mock(), launch=self.launch, new_window=new_window,
                             folder_roots=lambda: folder_roots, wait=wait,
                             index_roots=index_roots or (lambda: [self.root]),
                             drive_root=lambda letter: drives.get(letter, Path(f"{letter}:/not-here")))

    def mkdirs(self, *paths):
        for path in paths:
            (self.root / path).mkdir(parents=True)

    def run_words(self, *words, drive="t", run_claude=False, phrase="", **kw):
        return self.make(**kw).run(
            Command("terminal", "Terminal", drive=drive, words=words, phrase=phrase, run_claude=run_claude))

    def test_drive_only_opens_terminal_there_with_an_argv_list(self):
        ok, detail = self.make().run(Command("terminal", "Terminal", drive="t"))
        self.assertTrue(ok)
        self.launch.assert_called_once_with([command_runner.WT, "-w", "new", "-d", str(self.root)])
        self.assertEqual(self.focus_calls, ["terminal"])

    def test_run_claude_adds_cmd_k_claude(self):
        self.make().run(Command("terminal", "Terminal", drive="t", run_claude=True))
        self.launch.assert_called_once_with([command_runner.WT, "-w", "new", "-d", str(self.root), "cmd", "/k", "claude"])

    def test_wt_is_a_full_path_to_the_app_alias_when_it_is_not_on_path(self):
        self.assertTrue(command_runner.WT.lower().endswith("wt.exe"))
        self.assertTrue(command_runner.WT == "wt.exe" or Path(command_runner.WT).is_absolute())

    def test_missing_drive_fails_and_launches_nothing(self):
        ok, detail = self.make().run(Command("terminal", "Terminal", drive="q"))
        self.assertEqual((ok, detail), (False, "Drive Q: not found"))
        self.launch.assert_not_called()

    def test_no_drive_and_no_words_and_no_roots_asks_which_drive(self):
        ok, detail = self.make().run(Command("terminal", "Terminal"))
        self.assertEqual((ok, detail), (False, "Say which drive"))
        self.launch.assert_not_called()

    def test_not_success_until_the_new_window_is_in_front(self):
        ok, detail = self.make(focus_ok=False).run(Command("terminal", "Terminal", drive="t"))
        self.assertEqual((ok, detail), (False, "Couldn't bring Terminal to front"))

    def test_launch_error_fails(self):
        self.launch.side_effect = OSError("no")
        ok, detail = self.make().run(Command("terminal", "Terminal", drive="t"))
        self.assertEqual((ok, detail), (False, "Couldn't open Terminal"))

    def test_folder_words_find_one_folder_ignoring_case_and_underscores(self):
        self.mkdirs("work/clients/acme/AI_interview", "sudo/other/Zed")
        ok, _ = self.run_words("clients", "ai interview", run_claude=True)
        self.assertTrue(ok)
        self.launch.assert_called_once_with(
            [command_runner.WT, "-w", "new", "-d", str(self.root / "work/clients/acme/AI_interview"), "cmd", "/k", "claude"])

    def test_last_word_must_equal_the_folder_name_not_just_appear_in_it(self):
        self.mkdirs("clients/AI_interview_old")
        ok, detail = self.run_words("clients", "ai interview")
        self.assertEqual((ok, detail), (False, "Folder not found"))
        self.launch.assert_not_called()

    def test_earlier_words_are_hints_in_order(self):
        self.mkdirs("alpha/app", "beta/app")
        self.assertTrue(self.run_words("beta", "app")[0])
        self.launch.assert_called_once_with([command_runner.WT, "-w", "new", "-d", str(self.root / "beta/app")])
        self.assertEqual(self.run_words("beta", "alpha", "app")[1], "Folder not found")  # wrong order

    def test_several_matches_fail_and_list_up_to_three(self):
        self.mkdirs("a/app", "b/app", "c/app", "d/app")
        ok, detail = self.run_words("app")
        self.assertFalse(ok)
        listed = [d for d in "abcd" if str(self.root / d / "app") in detail]
        self.assertEqual(len(listed), 3)
        self.launch.assert_not_called()

    def test_skip_list_and_dot_folders_are_not_searched(self):
        self.mkdirs("node_modules/app", ".git/app", "$RECYCLE.BIN/app", "x/.hidden/app", "x/venv/app", "real/app")
        self.run_words("app")
        self.launch.assert_called_once_with([command_runner.WT, "-w", "new", "-d", str(self.root / "real/app")])

    def test_no_drive_searches_every_index_root(self):
        self.mkdirs("proj/voxkey")
        ok, _ = self.run_words("voxkey", drive="")
        self.assertTrue(ok)
        self.launch.assert_called_once_with([command_runner.WT, "-w", "new", "-d", str(self.root / "proj/voxkey")])

    def test_default_roots_use_the_setting_else_fixed_drives_without_the_system_drive(self):
        drive = lambda letter: Path(f"{letter.upper()}:\\")
        fixed = lambda: [Path("C:\\"), Path("D:\\"), Path("E:\\")]
        self.assertEqual(command_runner.default_index_roots(["e"], drive, fixed, "C:"), [Path("E:\\")])
        self.assertEqual(command_runner.default_index_roots([], drive, fixed, "C:"), [Path("D:\\"), Path("E:\\")])

    def test_a_folder_root_that_exists_is_kept_whole(self):
        self.mkdirs("work")
        roots = command_runner.default_index_roots([str(self.root / "work"), "e"], lambda l: Path(f"{l.upper()}:\\"))
        self.assertEqual(roots, [self.root / "work", Path("E:\\")])

    def test_spoken_drive_limits_results_to_that_drive(self):
        other = Path(self.root, "other")
        other.mkdir()
        self.mkdirs("one/voxkey")
        (other / "voxkey").mkdir()
        runner_ = self.make(index_roots=lambda: [self.root / "one", other])
        runner_._drive_root = lambda letter: other
        ok, detail = runner_.run(Command("terminal", "Terminal", drive="t", words=("voxkey",)))
        self.assertTrue(ok)
        self.assertIn(str(other / "voxkey"), detail)

    def test_command_before_the_index_is_ready_waits_then_fails(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.mkdirs("voxkey")
        def slow_roots():
            gate.wait(5)
            return [self.root]
        started = time.monotonic()
        ok, detail = self.make(index_roots=slow_roots, wait=0.1).run(
            Command("terminal", "Terminal", drive="t", words=("voxkey",)))
        self.assertEqual((ok, detail), (False, "Still indexing folders — try again in a moment"))
        self.assertLess(time.monotonic() - started, 1.0)
        self.launch.assert_not_called()

    def test_index_keeps_a_skipped_folders_own_name_but_does_not_descend(self):
        self.mkdirs("proj/build", "proj/build/inner", "proj/.hidden")
        self.assertTrue(self.run_words("build")[0])
        self.launch.assert_called_once_with([command_runner.WT, "-w", "new", "-d", str(self.root / "proj/build")])
        self.assertEqual(self.run_words("inner")[1], "Folder not found")
        self.assertTrue(self.run_words("hidden")[0])

    def test_whole_phrase_is_tried_as_one_folder_name(self):
        self.mkdirs("work/todo", "work/designandbuild", "work/qa")
        for phrase, words, name in [("to do", ("do",), "todo"), ("design and build", ("design", "build"), "designandbuild"),
                                    ("q a", ("q",), "qa")]:
            with self.subTest(phrase):
                self.launch.reset_mock()
                self.assertTrue(self.run_words(*words, phrase=phrase)[0])
                self.launch.assert_called_once_with([command_runner.WT, "-w", "new", "-d", str(self.root / "work" / name)])

    def test_phrase_falls_back_to_hint_words(self):
        self.mkdirs("clients/acme/AI_interview")
        ok, _ = self.run_words("clients", "ai interview", phrase="clients in ai interview")
        self.assertTrue(ok)

    def test_a_path_with_a_semicolon_is_never_passed_to_wt(self):
        self.mkdirs("a;b/app")
        ok, detail = self.run_words("app")
        self.assertEqual((ok, detail), (False, "Folder name has ';' — can't open in Terminal"))
        self.launch.assert_not_called()

    def test_search_time_is_logged(self):
        self.mkdirs("proj/voxkey")
        runner_ = self.make()
        runner_.run(Command("terminal", "Terminal", drive="t", words=("voxkey",)))
        self.assertIn("ms=", runner_.logger.info.call_args.args[0])



if __name__ == "__main__":
    unittest.main()
