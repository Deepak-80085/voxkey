"""Deterministic local text formatting for VoxKey dictation."""

from __future__ import annotations

import re

from vocabulary import normalize_vocabulary


class WritingModelUnavailable(RuntimeError):
    """No dictated text remains to paste."""


_SPOKEN_FILLER_RE = re.compile(r"(?i)(?<!\w)(?:um+|uh+|erm+)(?!\w)[,;:!?]?[ \t]*")
_BACKTRACK_RE = re.compile(
    r"(?i)\b(?P<old>[^\W_]+)(?:,\s*|\.{2,}\s*|…\s*)(?:actually(?:\s+no)?|I mean|sorry)\s+(?P<new>[^\W_]+)\b"
)
_EXPLICIT_BACKTRACK_RE = re.compile(r"(?i)\b[^\W_]+\s+actually no\s+([^\W_]+)\b")
_NUMBER_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve".split())
_WEEKDAYS = set("monday tuesday wednesday thursday friday saturday sunday".split())
_FORMAT_COMMAND_RE = re.compile(
    r"\b(start a new paragraph|new paragraph|new line|next line|line break|"
    r"bullet point|question mark|exclamation point|full stop)\b",
    re.IGNORECASE,
)
_FORMAT_COMMANDS = {
    "start a new paragraph": "\n\n",
    "new paragraph": "\n\n",
    "new line": "\n",
    "next line": "\n",
    "line break": "\n",
    "bullet point": "\n•",
    "question mark": "?",
    "exclamation point": "!",
    "full stop": ".",
}


def remove_spoken_fillers(text: str) -> str:
    """Remove only obvious vocal fillers while preserving dictated wording."""
    cleaned = _SPOKEN_FILLER_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"[ \t]+([,.;!?])", r"\1", cleaned)
    return cleaned.strip()


def apply_spoken_corrections(text: str) -> str:
    """Handle explicit, single-word backtracks without guessing intent."""
    def replace(match):
        old, new = match.group("old").casefold(), match.group("new").casefold()
        if ((old.isdigit() or old in _NUMBER_WORDS) and (new.isdigit() or new in _NUMBER_WORDS)) or (old in _WEEKDAYS and new in _WEEKDAYS):
            return match.group("new")
        return match.group()

    text = _BACKTRACK_RE.sub(replace, text)
    return _EXPLICIT_BACKTRACK_RE.sub(lambda match: match.group(1), text)


def format_spoken_commands(text: str) -> str:
    formatted = _FORMAT_COMMAND_RE.sub(
        lambda match: _FORMAT_COMMANDS[match.group().casefold()], text
    )
    formatted = re.sub(r"[ \t]+([?.!])", r"\1", formatted)
    return re.sub(r"[ \t]*\n[ \t]*", "\n", formatted).strip()






def _safe_format(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    formatted_lines = []
    for line in lines:
        first_word = re.match(r"(?:•\s*)?(\w+)", line)
        if first_word and not any(char.isupper() for char in first_word.group(1)[1:]):
            start = first_word.start(1)
            line = line[:start] + line[start].upper() + line[start + 1:]
        formatted_lines.append(line)
    formatted = "\n".join(formatted_lines).strip()
    formatted = re.sub(
        r"([.!?][ \t]+)(\w+)",
        lambda match: match.group(1) + (
            match.group(2) if any(char.isupper() for char in match.group(2)[1:])
            else match.group(2)[:1].upper() + match.group(2)[1:]
        ),
        formatted,
    )
    if formatted and formatted[-1] not in ".!?":
        formatted += "."
    return formatted




def _restore_vocabulary_casing(text: str, terms: list[str]) -> str:
    for term in sorted(normalize_vocabulary(terms), key=len, reverse=True):
        text = re.sub(r"(?<!\w)" + re.escape(term) + r"(?!\w)", term, text, flags=re.IGNORECASE)
    return text


class TextFormatter:
    """Rule-based formatting only. A local 0.8B LLM writer used to run here, but it changed
    words in 14/14 benchmark samples, so its output was always discarded for this formatting."""

    def __init__(self, vocabulary_provider=None):
        self.vocabulary_provider = vocabulary_provider or (lambda: [])

    def _finish(self, text: str) -> str:
        return _restore_vocabulary_casing(text, self.vocabulary_provider())

    def polish(self, transcript: str, style: str = "standard") -> str:
        if style not in ("standard", "minimal", "bullet notes"):
            raise ValueError("Unknown dictation style")
        text = format_spoken_commands(apply_spoken_corrections(remove_spoken_fillers(transcript.strip())))
        if not text:
            raise WritingModelUnavailable("No speech to polish")
        if style == "minimal":
            formatted = _safe_format(text)
            if not text.rstrip().endswith((".", "?", "!")) and formatted.endswith("."):
                formatted = formatted[:-1]
            return self._finish(formatted)
        if style == "bullet notes":
            lines = [line.strip().removeprefix("•").strip() for line in text.splitlines()]
            return self._finish("\n".join("• " + _safe_format(line) for line in lines if line))
        return self._finish(_safe_format(text))
