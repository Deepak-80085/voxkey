"""Local vocabulary helpers for English dictation prompt bias."""

from collections.abc import Iterable

MAX_VOCABULARY_ENTRIES = 100


def normalize_vocabulary(words: Iterable[str]) -> list[str]:
    normalized = []
    seen = set()
    for word in words:
        cleaned = " ".join(str(word).split())
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        normalized.append(cleaned)
        seen.add(key)
        if len(normalized) == MAX_VOCABULARY_ENTRIES:
            break
    return normalized


def build_initial_prompt(words: Iterable[str]) -> str:
    terms = normalize_vocabulary(words)
    if not terms:
        return ""
    return f"English dictation. Terms: {', '.join(terms)}."
