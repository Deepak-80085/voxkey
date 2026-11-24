import unittest
import threading
import time
from unittest.mock import Mock, patch

import command_runner
from command_runner import CommandRunner, known_from
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

    def test_other_kinds_are_not_supported_yet(self):
        launch = Mock()
        ok, detail = runner(launch=launch).run(Command("terminal", "Terminal"))
        self.assertEqual((ok, detail), (False, "Not supported yet"))
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


class FakeKeys:
    """Records every key event; `lose_after` flips the foreground away after that many events."""
    def __init__(self, front, lose_after=None):
        self.events, self.front, self.lose_after = [], front, lose_after

    def _log(self, event):
        self.events.append(event)
        if self.lose_after is not None and len(self.events) >= self.lose_after:
            self.front[0] = False

    def chord(self, *names):
        self._log(("chord",) + names)

    def type_char(self, char):
        self._log(("type", char))

    def tap(self, name):
        self._log(("tap", name))


class SearchTests(unittest.TestCase):
    def _run(self, command, lose_after=None, focus_ok=True, front_at_start=True):
        front = [front_at_start]
        keys = FakeKeys(front, lose_after)
        r = CommandRunner(Mock(), start_apps=lambda: APPS + [{"Name": "WhatsApp", "AppID": "W"},
                                                 {"Name": "T3 Code (Nightly)", "AppID": "T"}],
                          launch=Mock(), focus=Mock(return_value=focus_ok), keys=keys,
                          in_front=lambda name: front[0], pause=lambda s: None)
        return r.run(command), keys.events

    def _typed(self, events):
        return "".join(e[1] for e in events if e[0] == "type")

    def test_slack_sends_ctrl_k_then_the_name_then_enter(self):
        (ok, detail), events = self._run(Command("search", "Slack", target="hirefast"))
        self.assertTrue(ok)
        self.assertEqual(events[0], ("chord", "ctrl", "k"))
        self.assertEqual(self._typed(events), "hirefast")
        self.assertEqual(events[-1], ("tap", "enter"))

    def test_t3_uses_ctrl_k(self):
        _, events = self._run(Command("search", "T3 Code", target="voice command"))
        self.assertEqual(events[0], ("chord", "ctrl", "k"))
        self.assertEqual(self._typed(events), "voice command")

    def test_whatsapp_uses_its_shortcut_and_clears_the_box_first(self):
        _, events = self._run(Command("search", "WhatsApp", target="Puneet Jigsaw"))
        self.assertEqual(events[:2], [("chord", "ctrl", "alt", "/"), ("chord", "ctrl", "a")])
        self.assertEqual(self._typed(events), "Puneet Jigsaw")

    def test_focus_lost_mid_sequence_sends_no_more_keys(self):
        (ok, detail), events = self._run(Command("search", "Slack", target="hirefast"), lose_after=3)
        self.assertFalse(ok)
        self.assertEqual(detail, "Couldn't focus Slack — nothing typed")
        self.assertEqual(len(events), 3)

    def test_not_in_front_at_start_sends_nothing(self):
        (ok, detail), events = self._run(Command("search", "Slack", target="x"), front_at_start=False)
        self.assertEqual((ok, events), (False, []))
        self.assertEqual(detail, "Couldn't focus Slack — nothing typed")

    def test_window_not_focused_sends_nothing(self):
        (ok, detail), events = self._run(Command("search", "Slack", target="x"), focus_ok=False)
        self.assertEqual((ok, events), (False, []))

    def test_slack_workspace_is_not_supported_yet_and_sends_nothing(self):
        (ok, detail), events = self._run(Command("search", "Slack", target="general", workspace="jigsaw"))
        self.assertEqual((ok, detail, events), (False, "Workspace switch not supported yet", []))

    def test_app_without_a_search_shortcut_fails(self):
        (ok, _), events = self._run(Command("search", "Notes", target="x"))
        self.assertEqual((ok, events), (False, []))


if __name__ == "__main__":
    unittest.main()
