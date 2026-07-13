import unittest

from ui import status_view
from voxkey_runtime import AppState


class UiStateTests(unittest.TestCase):
    def test_repair_state_exposes_repair_action_and_reason(self):
        view = status_view(AppState.NEEDS_REPAIR, "Speech model needs repair")

        self.assertEqual(view.title, "Needs repair")
        self.assertTrue(view.can_repair)
        self.assertIn("Speech model needs repair", view.detail)

    def test_ready_state_is_local_and_can_dictate(self):
        view = status_view(AppState.READY, None)

        self.assertEqual(view.title, "Ready")
        self.assertFalse(view.can_repair)
        self.assertIn("local", view.detail.lower())


if __name__ == "__main__":
    unittest.main()
