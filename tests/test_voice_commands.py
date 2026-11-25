import unittest

from voice_commands import AMBIGUOUS, BUILTIN_SITES, UNKNOWN, Command, Known, parse

KNOWN = Known(
    sites={**BUILTIN_SITES, "sudo tracker": "https://tracker.example.test/#home"},
    accounts=("alex.rivera.7@mail.test", "alex@acme.test", "alex@globex.test",
              "sam@acme.test", "sam@initech.test", "robin@initech.test", "pat@globex.test"),
    self_name="alex",
    default_account="alex.rivera.7@mail.test",
    orgs={"work": "acme.test", "acme": "acme.test", "globex": "globex.test", "initech": "initech.test"},
    workspaces=("acme", "globex"),
)


class VoiceCommandTests(unittest.TestCase):
    def test_golden_examples(self):
        cases = {
            "Open Slack.": Command("app", "Slack"),
            "Open the roadmap channel in the Slack.": Command("search", "Slack", target="roadmap"),
            "Open the general channel in Globex Slack.":
                Command("search", "Slack", target="general", workspace="globex"),
            "Open my sudo tracker in my work Chrome.":
                Command("site", "sudo tracker", url="https://tracker.example.test/#home", account="alex@acme.test"),
            "Open YouTube on my Alex account.":
                Command("site", "YouTube", url="https://www.youtube.com", account="alex.rivera.7@mail.test"),
            "Open YouTube Music.": Command("site", "YouTube Music", url="https://music.youtube.com"),
            "Open GitHub in my account in Chrome.":
                Command("site", "GitHub", url="https://github.com", account="alex.rivera.7@mail.test"),
            "Open the terminal in D drive.": Command("terminal", "Terminal", drive="d"),
            "Open Claude Code in voxkey.":
                Command("terminal", "Terminal", words=("voxkey",), run_claude=True),
            "Open the terminal in E drive, clients folder, AI interview, and run Claude Code.":
                Command("terminal", "Terminal", drive="e", words=("clients", "ai interview"), run_claude=True),
            "Open Claude.": Command("app", "Claude"),
            "Open ChatGPT.": Command("app", "ChatGPT"),
            "Open T3 Code.": Command("app", "T3 Code"),
            "Open WhatsApp.": Command("app", "WhatsApp"),
            "Open WhatsApp and open the Sam Acme chat.": Command("search", "WhatsApp", target="sam acme"),
            "Open the voice command thread in T3 Code.":
                Command("search", "T3 Code", target="voice command"),
            "Hello, good morning.": None,
            "Open the PR and review it.": None,
        }
        for text, expected in cases.items():
            with self.subTest(text):
                self.assertEqual(parse(text, KNOWN), expected)

    def test_ignores_case_and_punctuation(self):
        self.assertEqual(parse("  OPEN... slack!!", KNOWN), Command("app", "Slack"))

    def test_real_shaped_mishearings(self):
        cases = {
            "Open the Slack.": Command("app", "Slack"),
            "Open Claude Desktop app.": Command("app", "Claude"),
            "Open the T3 code.": Command("app", "T3 Code"),
            "Open my sudo tracker in my workroom.":
                Command("site", "sudo tracker", url="https://tracker.example.test/#home", account="alex@acme.test"),
            "Open the terminal in eDrive, clients folder, in AI interview, run the Claude Code.":
                Command("terminal", "Terminal", drive="e", words=("clients", "ai interview"), run_claude=True),
            "Open the terminal in E drive clients folder in AI interview and run the Claude Code":
                Command("terminal", "Terminal", drive="e", words=("clients", "ai interview"), run_claude=True),
            "Open the beer and review it.": None,
        }
        for text, expected in cases.items():
            with self.subTest(text):
                self.assertEqual(parse(text, KNOWN), expected)

    def test_terminal_keeps_the_joined_phrase_for_one_word_folder_names(self):
        cases = {
            "Open the terminal in E drive, to-do folder.": ("to do", ("do",)),
            "Open the terminal in E drive, design and build folder.": ("design and build", ("design", "build")),
            "Open the terminal in E drive, Q&A folder.": ("q a", ("q",)),
            "Open Claude Code in VoxKey.": ("voxkey", ("voxkey",)),
            "Open the terminal in E drive, build folder.": ("build", ("build",)),
        }
        for text, (phrase, words) in cases.items():
            with self.subTest(text):
                command = parse(text, KNOWN)
                self.assertEqual((command.phrase, command.words), (phrase, words))

    def test_close_name_matches_but_near_miss_does_not(self):
        self.assertEqual(parse("open slab", KNOWN), Command("app", "Slack"))
        self.assertIsNone(parse("open slate", KNOWN))

    def test_accounts_resolve_by_person_and_org(self):
        gmail = lambda words: parse(f"Open Gmail {words}", KNOWN).account
        self.assertEqual(gmail("in Sam, acme account"), "sam@acme.test")
        self.assertEqual(gmail("in Robin account"), "robin@initech.test")
        self.assertEqual(gmail("in my globex account"), "alex@globex.test")
        self.assertIsNone(gmail(""))

    def test_never_guesses_a_profile(self):
        gmail = lambda words: parse(f"Open Gmail {words}", KNOWN).account
        self.assertEqual(gmail("in Sam account"), AMBIGUOUS)
        self.assertEqual(gmail("in Zed account"), UNKNOWN)
        self.assertEqual(gmail("in Pat acme account"), UNKNOWN)

    def test_only_whole_command_sentences_match(self):
        for text in ("open slack is down today", "Open the file and send it to Slack",
                     "Open a new tab and write the email", "Open Claude code review notes tomorrow",
                     "open the snack bar", "open the black", "open Slack in the morning",
                     "open to suggestions about Slack", "open the terminal of the problem",
                     "open Gmail please"):
            with self.subTest(text):
                self.assertIsNone(parse(text, KNOWN))

    def test_dictated_command_shapes_stay_commands(self):
        site = lambda name, url, account=None: Command("site", name, url=url, account=account)
        cases = {
            "Open GitHub in my account and grow.": site("GitHub", "https://github.com", "alex.rivera.7@mail.test"),
            "Open the Gmail in Sam, work again.": site("Gmail", "https://mail.google.com", "sam@acme.test"),
            "Open WhatsApp and Open Sam Globex Chat.": Command("search", "WhatsApp", target="sam globex"),
            "Open Claude Code in VoxKey.": Command("terminal", "Terminal", words=("voxkey",), run_claude=True),
            "Open the GitHub channel in Slack.": Command("search", "Slack", target="github"),
        }
        for text, expected in cases.items():
            with self.subTest(text):
                self.assertEqual(parse(text, KNOWN), expected)


if __name__ == "__main__":
    unittest.main()
