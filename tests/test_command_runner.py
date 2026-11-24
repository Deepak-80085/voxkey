import unittest
from unittest.mock import Mock

from command_runner import CommandRunner, known_from
from voice_commands import AMBIGUOUS, Command

APPS = [
    {"Name": "Slack", "AppID": "Slack.App.Id"},
    {"Name": "Notes Pro (Nightly)", "AppID": "Notes.Nightly!App"},
    {"Name": "Notes", "AppID": "Notes.Exact!App"},
]


def runner(apps=APPS, launch=None):
    return CommandRunner(Mock(), start_apps=lambda: apps, launch=launch or Mock())


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


if __name__ == "__main__":
    unittest.main()
