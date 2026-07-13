"""Guard application startup from recoverable local model failures."""


def start_transcriber(factory, logger):
    """Create a transcriber or return a user-safe repair message.

    Model caches can be absent or corrupt after interrupted downloads. Those
    failures must be logged and surfaced by the application UI, never allowed
    to reach the PyInstaller top-level exception handler.
    """
    try:
        return factory(), None
    except Exception:
        logger.exception("Speech model initialization failed")
        return None, "Speech model needs repair"
