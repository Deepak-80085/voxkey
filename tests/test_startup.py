import unittest
from unittest.mock import Mock

from startup import start_transcriber


class StartupTests(unittest.TestCase):
    def test_model_initialization_failure_returns_repair_message(self):
        logger = Mock()

        transcriber, message = start_transcriber(
            lambda: (_ for _ in ()).throw(RuntimeError("Unable to open file model.bin")),
            logger=logger,
        )

        self.assertIsNone(transcriber)
        self.assertEqual(message, "Speech model needs repair")
        logger.exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
